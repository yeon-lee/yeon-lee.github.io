#!/usr/bin/env python3
"""
Regenerate _bibliography/papers.bib from the arXiv API.

How it works
------------
1. Reads settings from _data/arxiv.yml (author query, allowed categories,
   excluded / extra arXiv IDs, per-paper overrides such as `selected: true`).
2. Queries the arXiv API for every paper matching the author query.
3. Converts each result to a BibTeX entry in the format al-folio expects
   (journal reference and DOI when arXiv knows them, otherwise "arXiv preprint").
4. Applies your overrides, appends the hand-written entries from
   _bibliography/manual.bib, and writes _bibliography/papers.bib.

papers.bib is therefore GENERATED. Do not edit it by hand:
  * to tweak a paper (mark it selected, add a thumbnail, slides, award...),
    add an entry under `overrides:` in _data/arxiv.yml;
  * to add a paper that is not on arXiv, put it in _bibliography/manual.bib;
  * to hide a paper, list its arXiv ID under `exclude:` in _data/arxiv.yml.

Usage
-----
    python3 bin/update_arxiv.py                # fetch from arXiv and rewrite papers.bib
    python3 bin/update_arxiv.py --dry-run      # print the result instead of writing it
    python3 bin/update_arxiv.py --from-file feed.xml   # offline: parse a saved Atom feed

Only dependency: PyYAML (pip install pyyaml).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "_data" / "arxiv.yml"
OUTPUT_PATH = ROOT / "_bibliography" / "papers.bib"
MANUAL_PATH = ROOT / "_bibliography" / "manual.bib"
PREVIEW_DIR = ROOT / "assets" / "img" / "publication_preview"

API_HOSTS = ["export.arxiv.org", "arxiv.org"]  # alternated on retry
RETRY_DELAYS = [15, 30, 60, 120, 180, 240]  # seconds between attempts (~10 min total)
RETRYABLE_STATUS = {403, 406, 408, 425, 429, 500, 502, 503, 504}
# Plain headers: arXiv's edge is pickier about "bot-looking" clients than about
# unadorned urllib, and it wants an Accept that admits Atom.
REQUEST_HEADERS = {"Accept": "application/atom+xml, application/xml;q=0.9, */*;q=0.8"}
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "os": "http://a9.com/-/spec/opensearch/1.1/",
}
PAGE_SIZE = 200
PAGE_DELAY_SECONDS = 3  # arXiv asks clients to wait between requests

# Journal name -> short badge shown on the publications page (al-folio `abbr`).
# Matching is case-insensitive on the start of the journal name; first hit wins.
JOURNAL_ABBR = [
    ("phys. rev. lett", "PRL"),
    ("physical review letters", "PRL"),
    ("prx quantum", "PRX Quantum"),
    ("phys. rev. x", "PRX"),
    ("physical review x", "PRX"),
    ("phys. rev. research", "PRR"),
    ("phys. rev. res", "PRR"),
    ("physical review research", "PRR"),
    ("phys. rev. b", "PRB"),
    ("physical review b", "PRB"),
    ("phys. rev. a", "PRA"),
    ("physical review a", "PRA"),
    ("phys. rev. d", "PRD"),
    ("phys. rev. e", "PRE"),
    ("phys. rev.", "Phys. Rev."),
    ("nature communications", "Nat. Commun."),
    ("nat commun", "Nat. Commun."),
    ("nat. commun", "Nat. Commun."),
    ("nature physics", "Nat. Phys."),
    ("nat. phys", "Nat. Phys."),
    ("nat phys", "Nat. Phys."),
    ("nature", "Nature"),
    ("science advances", "Sci. Adv."),
    ("science", "Science"),
    ("npj quantum information", "npj QI"),
    ("npj quantum inf", "npj QI"),
    ("quantum", "Quantum"),
    ("scipost", "SciPost"),
    ("optica", "Optica"),
    ("annals of physics", "Ann. Phys."),
    ("communications in mathematical physics", "CMP"),
    ("j. high energ. phys", "JHEP"),
    ("jhep", "JHEP"),
    ("new j. phys", "NJP"),
    ("new journal of physics", "NJP"),
    ("j. stat. mech", "JSTAT"),
    ("proceedings of the national academy", "PNAS"),
    ("pnas", "PNAS"),
]

# "Journal 12, 3456 (2020)", "Journal 12, L3456-3460 (2020)", "Journal 8 (2025)"
JREF_RE = re.compile(
    r"""^\s*(?P<journal>.+?)\s+
        (?P<volume>\d+[A-Za-z]?)
        (?:\s*,\s*(?P<pages>[A-Za-z]?\d+(?:\s*[-–—]+\s*[A-Za-z]?\d+)?))?
        \s*\(\s*(?P<year>\d{4})\s*\)""",
    re.VERBOSE,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"Missing {CONFIG_PATH}")
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    cfg.setdefault("author_query", "")
    cfg.setdefault("author_names", [])
    cfg.setdefault("categories", [])
    cfg.setdefault("exclude", [])
    cfg.setdefault("include", [])
    cfg.setdefault("overrides", {}) or {}
    cfg.setdefault("dimensions_badge", False)
    cfg.setdefault("include_abstract", True)
    cfg.setdefault("max_results", 1000)
    cfg.setdefault("year_source", "journal")
    if not cfg["author_query"]:
        sys.exit("author_query is empty in _data/arxiv.yml")
    # YAML may parse "2609.30069" as a float; normalise everything to strings.
    cfg["exclude"] = [strip_version(str(x)) for x in cfg["exclude"] or []]
    cfg["include"] = [strip_version(str(x)) for x in cfg["include"] or []]
    cfg["overrides"] = {strip_version(str(k)): (v or {}) for k, v in (cfg["overrides"] or {}).items()}
    return cfg


def strip_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id.strip())


class ArxivUnavailable(RuntimeError):
    """arXiv kept refusing us (throttling / outage); nothing was changed."""


def _parse_feed(data: bytes) -> ET.Element | None:
    """Return the Atom <feed> root if `data` is a parseable arXiv feed, else None."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    return root if root.tag == f"{{{NS['a']}}}feed" else None


def fetch_feed(query: str) -> ET.Element:
    """
    GET an arXiv API query and return the parsed feed.

    arXiv's edge intermittently answers 403/406/429/5xx to scripted clients for
    a few minutes at a time, and a 406 sometimes still carries a valid feed. So:
    retry with exponential backoff (~10 minutes in total), alternate between the
    two API hosts, and accept any response body that parses as an Atom feed.
    """
    last_error: Exception | None = None
    for attempt, delay in enumerate(RETRY_DELAYS + [None]):
        host = API_HOSTS[attempt % len(API_HOSTS)]
        url = f"https://{host}/api/query?{query}"
        log(f"GET {url}")
        try:
            req = urllib.request.Request(url, headers=REQUEST_HEADERS)
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
            feed = _parse_feed(body)
            if feed is not None:
                return feed
            last_error = RuntimeError("response was not an Atom feed")
        except urllib.error.HTTPError as e:
            body = e.read() if e.fp else b""
            feed = _parse_feed(body)
            if feed is not None:
                log(f"  HTTP {e.code} but the body is a valid feed; using it")
                return feed
            if e.code not in RETRYABLE_STATUS:
                raise
            last_error = e
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last_error = e
        if delay is None:
            break
        log(f"  attempt {attempt + 1} failed ({last_error}); retrying in {delay}s")
        time.sleep(delay)
    raise ArxivUnavailable(f"arXiv API unavailable after {len(RETRY_DELAYS) + 1} attempts: {last_error}")


def query_arxiv(search_query: str, max_results: int) -> list[ET.Element]:
    """Page through the arXiv API and return all <entry> elements."""
    entries: list[ET.Element] = []
    start = 0
    while start < max_results:
        params = {
            "search_query": search_query,
            "start": start,
            "max_results": min(PAGE_SIZE, max_results - start),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        root = fetch_feed(urllib.parse.urlencode(params))
        page = root.findall("a:entry", NS)
        total = int(root.findtext("os:totalResults", default="0", namespaces=NS) or 0)
        entries.extend(page)
        start += len(page)
        if not page or start >= total:
            break
        time.sleep(PAGE_DELAY_SECONDS)
    return entries


def fetch_by_ids(ids: list[str]) -> list[ET.Element]:
    if not ids:
        return []
    root = fetch_feed(urllib.parse.urlencode({"id_list": ",".join(ids), "max_results": len(ids)}))
    return root.findall("a:entry", NS)


def normalise_name(name: str) -> str:
    """'Jong-Yeon Lee' / 'Jong Yeon  Lee' / 'jong yeon lee' -> 'jong yeon lee'."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[-.]", " ", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def split_name(full: str) -> tuple[str, str]:
    """Return (last, first). Handles 'First Middle Last' and 'Last, First'."""
    full = " ".join(full.split())
    if "," in full:
        last, first = [p.strip() for p in full.split(",", 1)]
        return last, first
    parts = full.split(" ")
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def bib_escape(text: str) -> str:
    """Escape characters that break BibTeX fields (braces are left alone for LaTeX)."""
    text = " ".join(text.split())
    return text.replace("&", r"\&").replace("%", r"\%").replace("#", r"\#")


def ascii_slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


STOPWORDS = {"a", "an", "the", "on", "of", "in", "for", "to", "and", "from", "at", "with", "via", "toward", "towards"}


def first_title_word(title: str) -> str:
    title = re.sub(r"\$[^$]*\$", " ", title)  # drop inline math
    title = re.sub(r"\\[A-Za-z]+", " ", title)  # drop latex commands
    for word in re.findall(r"[A-Za-z][A-Za-z0-9-]*", title):
        w = ascii_slug(word)
        if w and w not in STOPWORDS:
            return w
    return "paper"


def parse_journal_ref(jref: str | None) -> dict:
    """Split 'Phys. Rev. B 113, 085139 (2026)' into journal / volume / pages / year."""
    if not jref:
        return {}
    jref = " ".join(jref.split())
    m = JREF_RE.match(jref)
    if not m:
        return {"journal": jref}
    out = {"journal": m.group("journal").rstrip(", "), "volume": m.group("volume"), "year": m.group("year")}
    if m.group("pages"):
        out["pages"] = re.sub(r"\s*[-–—]+\s*", "--", m.group("pages"))
    return out


def journal_abbr(journal: str | None) -> str | None:
    if not journal:
        return None
    j = journal.lower().strip()
    for prefix, abbr in JOURNAL_ABBR:
        if j.startswith(prefix):
            return abbr
    return None


def find_preview(arxiv_id: str) -> str | None:
    if not PREVIEW_DIR.is_dir():
        return None
    for ext in ("png", "jpg", "jpeg", "gif", "webp", "svg"):
        candidate = PREVIEW_DIR / f"{arxiv_id}.{ext}"
        if candidate.exists():
            return candidate.name
    return None


# --------------------------------------------------------------------------- #
# conversion
# --------------------------------------------------------------------------- #
def entry_to_record(entry: ET.Element) -> dict:
    raw_id = entry.findtext("a:id", default="", namespaces=NS).rsplit("/abs/", 1)[-1]
    arxiv_id = strip_version(raw_id)
    title = " ".join((entry.findtext("a:title", default="", namespaces=NS) or "").split())
    abstract = " ".join((entry.findtext("a:summary", default="", namespaces=NS) or "").split())
    authors = [a.findtext("a:name", default="", namespaces=NS) for a in entry.findall("a:author", NS)]
    published = entry.findtext("a:published", default="", namespaces=NS)[:10]
    updated = entry.findtext("a:updated", default="", namespaces=NS)[:10]
    primary = entry.find("arxiv:primary_category", NS)
    primary_cat = primary.get("term") if primary is not None else ""
    categories = [c.get("term") for c in entry.findall("a:category", NS)]
    doi = (entry.findtext("arxiv:doi", default="", namespaces=NS) or "").strip() or None
    jref = (entry.findtext("arxiv:journal_ref", default="", namespaces=NS) or "").strip() or None
    comment = (entry.findtext("arxiv:comment", default="", namespaces=NS) or "").strip() or None
    return {
        "arxiv_id": arxiv_id,
        "version_id": raw_id,
        "title": title,
        "abstract": abstract,
        "authors": [" ".join(a.split()) for a in authors if a],
        "published": published,
        "updated": updated,
        "primary_category": primary_cat,
        "categories": categories,
        "doi": doi,
        "journal_ref": jref,
        "comment": comment,
    }


def category_allowed(primary: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    return any(primary == a or primary.startswith(a + ".") for a in allowed)


def author_matches(authors: list[str], wanted: list[str]) -> bool:
    if not wanted:
        return True
    norm_wanted = {normalise_name(w) for w in wanted}
    return any(normalise_name(a) in norm_wanted for a in authors)


def make_key(rec: dict, used: set[str]) -> str:
    last, _ = split_name(rec["authors"][0]) if rec["authors"] else ("anon", "")
    year = rec["published"][:4] or "0000"
    base = f"{ascii_slug(last) or 'anon'}{year}{first_title_word(rec['title'])}"
    key = base
    suffix = "b"
    while key in used:
        key = base + suffix
        suffix = chr(ord(suffix) + 1)
    used.add(key)
    return key


def build_fields(rec: dict, cfg: dict) -> dict:
    jr = parse_journal_ref(rec["journal_ref"])
    year = rec["published"][:4]
    month = rec["published"][5:7]
    if cfg.get("year_source") == "journal" and jr.get("year"):
        year, month = jr["year"], ""  # journal year; arXiv month would be misleading
    fields: dict[str, str] = {}

    abbr = journal_abbr(jr.get("journal")) or ("arXiv" if not jr else None)
    if abbr:
        fields["abbr"] = abbr
    fields["title"] = bib_escape(rec["title"])
    fields["author"] = " and ".join(bib_escape(a) for a in rec["authors"])
    if jr:
        fields["journal"] = bib_escape(jr["journal"])
        if jr.get("volume"):
            fields["volume"] = jr["volume"]
        if jr.get("pages"):
            fields["pages"] = jr["pages"]
    else:
        fields["journal"] = f"arXiv preprint arXiv:{rec['arxiv_id']}"
    fields["year"] = year
    if month:
        fields["month"] = datetime(2000, int(month), 1).strftime("%b").lower()
    if rec["doi"]:
        fields["doi"] = rec["doi"]
        fields["html"] = f"https://doi.org/{rec['doi']}"
    else:
        fields["html"] = f"https://arxiv.org/abs/{rec['arxiv_id']}"
    fields["arxiv"] = rec["arxiv_id"]
    fields["pdf"] = f"https://arxiv.org/pdf/{rec['arxiv_id']}"
    if cfg.get("include_abstract") and rec["abstract"]:
        fields["abstract"] = bib_escape(rec["abstract"])
    if cfg.get("dimensions_badge") and rec["doi"]:
        fields["dimensions"] = "true"
    preview = find_preview(rec["arxiv_id"])
    if preview:
        fields["preview"] = preview
    fields["bibtex_show"] = "true"

    # user overrides win over everything derived above
    for k, v in (cfg["overrides"].get(rec["arxiv_id"]) or {}).items():
        if v is None or v is False or v == "":
            fields.pop(k, None)
        elif v is True:
            fields[k] = "true"
        else:
            fields[k] = str(v)
    return fields


def format_entry(key: str, fields: dict) -> str:
    width = max(len(k) for k in fields)
    lines = [f"@article{{{key},"]
    for k, v in fields.items():
        lines.append(f"  {k.ljust(width)} = {{{v}}},")
    lines[-1] = lines[-1].rstrip(",")
    lines.append("}")
    return "\n".join(lines)


def read_manual_bib() -> str:
    if not MANUAL_PATH.exists():
        return ""
    text = MANUAL_PATH.read_text(encoding="utf-8")
    # drop the "---\n---" front matter if someone copied it in
    text = re.sub(r"\A---\s*\n---\s*\n", "", text)
    # drop pure comment lines (% ...) so the generated file stays tidy
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("%"))
    return body.strip()


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print papers.bib to stdout instead of writing it")
    ap.add_argument("--from-file", metavar="FEED.xml", help="parse a saved arXiv Atom feed instead of querying the API")
    args = ap.parse_args()

    cfg = load_config()

    try:
        if args.from_file:
            root = ET.fromstring(Path(args.from_file).read_bytes())
            raw_entries = root.findall("a:entry", NS)
        else:
            raw_entries = query_arxiv(cfg["author_query"], int(cfg["max_results"]))
            seen_ids = {strip_version(e.findtext("a:id", default="", namespaces=NS).rsplit("/abs/", 1)[-1]) for e in raw_entries}
            extra = [i for i in cfg["include"] if i not in seen_ids]
            if extra:
                time.sleep(PAGE_DELAY_SECONDS)
                raw_entries.extend(fetch_by_ids(extra))
    except ArxivUnavailable as e:
        # Transient: leave papers.bib untouched and let the next scheduled run try again.
        # Printed as a GitHub Actions warning annotation; exit 0 so the run is not marked failed.
        print(f"::warning title=arXiv unavailable::{e} - papers.bib left unchanged.")
        log(str(e))
        return 0

    if not raw_entries and not args.from_file:
        print("::warning title=arXiv returned no papers::query matched nothing; papers.bib left unchanged.")
        return 0

    records: dict[str, dict] = {}
    skipped: list[str] = []
    for e in raw_entries:
        rec = entry_to_record(e)
        aid = rec["arxiv_id"]
        if not aid or not rec["title"]:
            continue
        forced = aid in cfg["include"]
        if aid in cfg["exclude"]:
            skipped.append(f"{aid} (excluded)")
            continue
        if not forced and not category_allowed(rec["primary_category"], cfg["categories"]):
            skipped.append(f"{aid} (category {rec['primary_category']})")
            continue
        if not forced and not author_matches(rec["authors"], cfg["author_names"]):
            skipped.append(f"{aid} (author name mismatch)")
            continue
        records[aid] = rec  # later duplicates (same id) simply overwrite

    ordered = sorted(records.values(), key=lambda r: (r["published"], r["arxiv_id"]), reverse=True)
    used_keys: set[str] = set()
    entries = [format_entry(make_key(r, used_keys), build_fields(r, cfg)) for r in ordered]

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = "\n".join(
        [
            "---",
            "---",
            "",
            "% ======================================================================",
            "% GENERATED FILE - do not edit by hand.",
            f"% Built by bin/update_arxiv.py on {generated} from the arXiv API",
            f"% (query: {cfg['author_query']}).",
            "%   * tweak a paper  -> _data/arxiv.yml  (overrides:)",
            "%   * hide a paper   -> _data/arxiv.yml  (exclude:)",
            "%   * non-arXiv paper -> _bibliography/manual.bib",
            "% ======================================================================",
            "",
        ]
    )
    manual = read_manual_bib()
    parts = [header]
    if manual:
        parts.append("% ---- entries from _bibliography/manual.bib ----\n\n" + manual + "\n")
    parts.append("% ---- entries from arXiv ----\n\n" + "\n\n".join(entries) + "\n")
    output = "\n".join(parts)

    log(f"{len(ordered)} papers kept, {len(skipped)} skipped")
    for s in skipped:
        log(f"  skipped {s}")

    if args.dry_run:
        sys.stdout.write(output)
        return 0

    old = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
    # ignore the date line when deciding whether anything changed
    strip_date = lambda s: re.sub(r"% Built by .*\n", "", s)  # noqa: E731
    if strip_date(old) == strip_date(output):
        log("papers.bib unchanged")
        return 0
    OUTPUT_PATH.write_text(output, encoding="utf-8")
    log(f"wrote {OUTPUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
