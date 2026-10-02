#!/usr/bin/env python3
"""
Regenerate _bibliography/papers.bib from the arXiv API.

How it works
------------
1. Reads settings from _data/arxiv.yml (author query, allowed categories,
   excluded / extra arXiv IDs, per-paper overrides such as `selected: true`).
2. Queries the arXiv API for every paper matching the author query. When the
   API is unreachable (arXiv blocks it from cloud IPs such as GitHub Actions),
   it lists the papers from the arxiv.org author-search page and fetches each
   record through OAI-PMH instead - same data, different door.
3. Converts each result to a BibTeX entry in the format al-folio expects
   (journal reference and DOI when arXiv knows them, otherwise "arXiv preprint").
4. Applies your overrides, appends the hand-written entries from
   _bibliography/manual.bib, and writes _bibliography/papers.bib.
5. Optionally (see `news:` and `previews:` in _data/arxiv.yml) writes a
   one-line news item into _news/ for every new preprint (and for papers
   that just got published), and downloads Figure 1 of each paper from its
   arXiv HTML version into assets/img/publication_preview/ as a thumbnail.

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

Dependencies: PyYAML (pip install pyyaml); optionally cairosvg to rasterise
SVG thumbnails, and an ANTHROPIC_API_KEY environment variable for the
one-line news highlights (without it the first sentence of the abstract is used).
"""

from __future__ import annotations

import argparse
import json
import os
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
NEWS_DIR = ROOT / "_news"
MEMBERS_PATH = ROOT / "_data" / "members.yml"
MEMBER_PAPERS_PATH = ROOT / "_data" / "member_papers.yml"
HTML_URL = "https://arxiv.org/html/"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

API_HOSTS = ["export.arxiv.org", "arxiv.org"]  # alternated on retry
RETRY_DELAYS = [10, 20, 40]  # seconds between API attempts before falling back to OAI-PMH
RETRYABLE_STATUS = {403, 406, 408, 425, 429, 500, 502, 503, 504}
REQUEST_HEADERS = {
    "Accept": "application/atom+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.7",
    "User-Agent": "al-folio publication sync (https://github.com/yeon-lee/yeon-lee.github.io)",
}
# Fallback path. arXiv blocks the query API from cloud IP ranges such as GitHub
# Actions runners (HTTP 406), but the author-search page and OAI-PMH still work
# there, so we list IDs via search and fetch each record via OAI-PMH.
SEARCH_URL = "https://arxiv.org/search/"
OAI_URL = "https://oaipmh.arxiv.org/oai"
OAI_DELAY_SECONDS = 1.5  # politeness delay between OAI-PMH requests
NS_OAI = {"o": "http://www.openarchives.org/OAI/2.0/", "ax": "http://arxiv.org/OAI/arXiv/"}
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
    news = cfg.get("news") or {}
    news.setdefault("enabled", False)
    news.setdefault("since", "")
    news.setdefault("members", [])
    news.setdefault("announce_published", True)
    news.setdefault("model", "claude-sonnet-5-5")
    news.setdefault("max_words", 30)
    cfg["news"] = news
    previews = cfg.get("previews") or {}
    previews.setdefault("enabled", False)
    previews.setdefault("max_per_run", 12)
    previews.setdefault("max_bytes", 600_000)
    previews.setdefault("png_width", 900)
    cfg["previews"] = previews
    if not cfg.get("author_search"):
        # arXiv search wants "Last, First"; derive it from the first author_names entry
        first = (cfg["author_names"] or [""])[0]
        parts = first.split()
        cfg["author_search"] = f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) > 1 else first
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


def _http_get(url: str, tries: int = 4) -> bytes:
    """GET with a small retry loop honouring Retry-After (OAI-PMH answers 503 when busy)."""
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=REQUEST_HEADERS)
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE_STATUS:
                raise
            wait = e.headers.get("Retry-After") if e.headers else None
            delay = int(wait) if wait and wait.isdigit() else 10 * (attempt + 1)
            last = e
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            delay = 10 * (attempt + 1)
            last = e
        if attempt < tries - 1:
            log(f"  {url[:80]}... failed ({last}); retrying in {delay}s")
            time.sleep(min(delay, 120))
    raise ArxivUnavailable(f"{url[:80]}... unavailable: {last}")


def search_author_ids(author_search: str, max_results: int) -> list[str]:
    """List arXiv IDs for an author from the arxiv.org search pages (newest first)."""
    ids: list[str] = []
    start = 0
    total: int | None = None
    while start < max_results:
        params = {"searchtype": "author", "query": author_search, "size": 200, "order": "-announced_date_first", "start": start}
        url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
        log(f"GET {url}")
        html = _http_get(url).decode("utf-8", "replace")
        page = re.findall(r'href="https://arxiv\.org/abs/([^"]+)"\s*>\s*arXiv:', html)
        page = [strip_version(i) for i in page]
        if total is None:
            m = re.search(r"of\s+([\d,]+)\s+results", html)
            total = int(m.group(1).replace(",", "")) if m else len(page)
            if re.search(r"Sorry, your query returned no results", html):
                total = 0
        ids.extend(i for i in page if i not in ids)
        start += 200
        if not page or len(ids) >= total:
            break
        time.sleep(OAI_DELAY_SECONDS)
    log(f"search: {len(ids)} ids for author \"{author_search}\"")
    return ids


def oai_record(arxiv_id: str) -> dict | None:
    """Fetch one paper's metadata via OAI-PMH and shape it like entry_to_record()."""
    url = OAI_URL + "?" + urllib.parse.urlencode({"verb": "GetRecord", "identifier": f"oai:arXiv.org:{arxiv_id}", "metadataPrefix": "arXiv"})
    root = ET.fromstring(_http_get(url))
    meta = root.find(".//ax:arXiv", NS_OAI)
    if meta is None:
        err = root.findtext("o:error", default="", namespaces=NS_OAI)
        log(f"  OAI: no record for {arxiv_id} ({err.strip()[:80]})")
        return None
    def text(tag: str) -> str:
        return " ".join((meta.findtext(f"ax:{tag}", default="", namespaces=NS_OAI) or "").split())
    authors = []
    for a in meta.findall("ax:authors/ax:author", NS_OAI):
        fore = " ".join((a.findtext("ax:forenames", default="", namespaces=NS_OAI) or "").split())
        key = " ".join((a.findtext("ax:keyname", default="", namespaces=NS_OAI) or "").split())
        suffix = " ".join((a.findtext("ax:suffix", default="", namespaces=NS_OAI) or "").split())
        authors.append(" ".join(x for x in (fore, key, suffix) if x))
    cats = text("categories").split()
    return {
        "arxiv_id": strip_version(text("id") or arxiv_id),
        "version_id": text("id") or arxiv_id,
        "title": text("title"),
        "abstract": text("abstract"),
        "authors": authors,
        "published": published_from_id(text("id") or arxiv_id, text("created")),
        "submitted": (text("created") or "")[:10],
        "updated": text("updated") or text("created"),
        "primary_category": cats[0] if cats else "",
        "categories": cats,
        "doi": text("doi") or None,
        "journal_ref": text("journal-ref") or None,
        "comment": text("comments") or None,
    }


def published_from_id(arxiv_id: str, fallback: str = "") -> str:
    """First-submission month from a new-style ID (YYMM.NNNNN); the day is unknown, so use 01."""
    m = re.match(r"(\d{2})(\d{2})\.\d{4,5}", strip_version(arxiv_id))
    if m:
        return f"20{m.group(1)}-{m.group(2)}-01"
    return fallback[:10] if fallback else ""


def records_via_search_and_oai(cfg: dict) -> list[dict]:
    ids = search_author_ids(cfg["author_search"], int(cfg["max_results"]))
    ids += [i for i in cfg["include"] if i not in ids]
    records: list[dict] = []
    for n, aid in enumerate(ids):
        if aid in cfg["exclude"]:
            continue
        if n:
            time.sleep(OAI_DELAY_SECONDS)
        rec = oai_record(aid)
        if rec:
            records.append(rec)
    log(f"OAI-PMH: fetched {len(records)} records")
    return records


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
# news items and thumbnails
# --------------------------------------------------------------------------- #
NEWS_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(arxiv|published)-(\d{4}\.\d{4,5})\.md$")


def announced(kind: str) -> set[str]:
    """arXiv IDs that already have a news item of this kind (arxiv|published)."""
    ids: set[str] = set()
    if NEWS_DIR.is_dir():
        for f in NEWS_DIR.iterdir():
            m = NEWS_FILE_RE.match(f.name)
            if m and m.group(1) == kind:
                ids.add(m.group(2))
    return ids


def member_coauthors(rec: dict, members: list[str], pi_names: list[str]) -> list[str]:
    """Group members (other than the PI) on the paper, in author order, as written on arXiv."""
    wanted = {normalise_name(m) for m in members} - {normalise_name(p) for p in pi_names}
    return [a for a in rec["authors"] if normalise_name(a) in wanted]


def fallback_highlight(abstract: str, max_words: int) -> str:
    """First sentence of the abstract, trimmed, used when no API key is available."""
    text = re.sub(r"\$[^$]*\$", "", abstract)  # drop inline math
    first = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    words = first.split()
    if len(words) > max_words:
        first = " ".join(words[:max_words]).rstrip(",;:") + "..."
    return first


def llm_highlight(rec: dict, ncfg: dict) -> str | None:
    """One-sentence plain-language highlight from the abstract via the Anthropic API."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    prompt = (
        "Write ONE sentence (at most {n} words) that tells a physicist what this paper's main result is, "
        "in plain language, no hype, no leading 'This paper' or 'We'. Start with a noun phrase or a verb "
        "such as 'Shows that ...', 'Introduces ...'. No LaTeX; write math in words. Output only the sentence.\n\n"
        "Title: {title}\n\nAbstract: {abstract}"
    ).format(n=ncfg["max_words"], title=rec["title"], abstract=rec["abstract"])
    body = json.dumps({
        "model": ncfg["model"],
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        text = " ".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")
        text = " ".join(text.split()).strip().strip('"')
        return text or None
    except Exception as e:  # network, auth, quota: fall back rather than fail the run
        log(f"  highlight for {rec['arxiv_id']} failed ({str(e)[:100]}); using the abstract instead")
        return None


def highlight_for(rec: dict, ncfg: dict) -> str:
    text = llm_highlight(rec, ncfg) or fallback_highlight(rec["abstract"], int(ncfg["max_words"]))
    return text.rstrip(".") + "."


def join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def write_news(path: Path, date: str, body: str) -> None:
    path.write_text(
        "---\n"
        "layout: post\n"
        f"date: {date} 09:00:00-0500\n"
        "inline: true\n"
        "related_posts: false\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    log(f"wrote {path.relative_to(ROOT)}")


def preprint_news(rec: dict, cfg: dict) -> Path | None:
    ncfg = cfg["news"]
    date = rec.get("submitted") or rec["published"]
    if ncfg.get("since") and date < str(ncfg["since"]):
        return None
    path = NEWS_DIR / f"{date}-arxiv-{rec['arxiv_id']}.md"
    with_members = member_coauthors(rec, ncfg["members"], cfg["author_names"])
    lead = f"New preprint with {join_names(with_members)}" if with_members else "New preprint"
    body = f"{lead}: [{rec['title']}](https://arxiv.org/abs/{rec['arxiv_id']}) — {highlight_for(rec, ncfg)}"
    NEWS_DIR.mkdir(exist_ok=True)
    write_news(path, date, body)
    return path


def published_news(rec: dict, cfg: dict, journal: str, today: str) -> Path | None:
    url = f"https://doi.org/{rec['doi']}" if rec.get("doi") else f"https://arxiv.org/abs/{rec['arxiv_id']}"
    path = NEWS_DIR / f"{today}-published-{rec['arxiv_id']}.md"
    body = f"Published in {journal}: [{rec['title']}]({url})."
    NEWS_DIR.mkdir(exist_ok=True)
    write_news(path, today, body)
    return path


def old_bib_published() -> dict[str, bool]:
    """arXiv ID -> whether the current papers.bib already lists a journal (not 'arXiv preprint') for it."""
    out: dict[str, bool] = {}
    if not OUTPUT_PATH.exists():
        return out
    for chunk in OUTPUT_PATH.read_text(encoding="utf-8").split("\n@")[1:]:
        m_id = re.search(r"\barxiv\s*=\s*\{([^}]*)\}", chunk)
        m_j = re.search(r"\bjournal\s*=\s*\{([^}]*)\}", chunk)
        if m_id:
            out[m_id.group(1).strip()] = bool(m_j) and not m_j.group(1).strip().lower().startswith("arxiv preprint")
    return out


def generate_news(ordered: list[dict], cfg: dict, before: dict[str, bool], dry_run: bool) -> int:
    """Write news items for new preprints and newly published papers. Returns the number written."""
    ncfg = cfg["news"]
    if not ncfg.get("enabled") or dry_run:
        return 0
    n = 0
    done_arxiv = announced("arxiv")
    done_pub = announced("published")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for rec in ordered:
        aid = rec["arxiv_id"]
        if aid not in done_arxiv and preprint_news(rec, cfg):
            n += 1
        jr = parse_journal_ref(rec["journal_ref"])
        if ncfg.get("announce_published") and jr.get("journal") and aid in before and not before[aid] and aid not in done_pub:
            if published_news(rec, cfg, jr["journal"], today):
                n += 1
    return n


FIGURE_RE = re.compile(r'<figure[^>]*class="[^"]*ltx_figure[^"]*"[^>]*>(.*?)</figure>', re.S)
GRAPHIC_RE = re.compile(r'<(?:object|img)[^>]*\b(?:data|src)="([^"]+)"', re.S)


def fetch_preview(rec: dict, pcfg: dict) -> Path | None:
    """Download Figure 1 (falling back to 2, 3) from the paper's arXiv HTML page as its thumbnail."""
    aid = rec["arxiv_id"]
    m = re.match(r"(\d{2})(\d{2})\.", aid)
    if not m or int(m.group(1) + m.group(2)) < 2312:
        return None  # arXiv only renders HTML for submissions from December 2023 on
    try:
        page = _http_get(HTML_URL + aid, tries=1).decode("utf-8", "replace")
    except Exception as e:
        log(f"  no HTML version for {aid} ({str(e)[:60]})")
        return None
    for fig in FIGURE_RE.findall(page)[:3]:
        m = GRAPHIC_RE.search(fig)
        if not m:
            continue
        src = m.group(1)
        url = src if src.startswith("http") else HTML_URL + src.lstrip("/")
        try:
            data = _http_get(url, tries=1)
        except Exception as e:
            log(f"  figure download failed for {aid} ({str(e)[:60]})")
            continue
        if len(data) > int(pcfg["max_bytes"]):
            log(f"  figure too large for {aid} ({len(data)} bytes); trying the next one")
            continue
        ext = src.rsplit(".", 1)[-1].lower()
        if ext not in ("svg", "png", "jpg", "jpeg", "gif", "webp"):
            continue
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        if ext == "svg":
            try:
                import cairosvg  # type: ignore

                png = cairosvg.svg2png(bytestring=data, output_width=int(pcfg["png_width"]), background_color="white")
                out = PREVIEW_DIR / f"{aid}.png"
                out.write_bytes(png)
                log(f"wrote {out.relative_to(ROOT)} (rasterised from SVG)")
                return out
            except Exception as e:
                log(f"  cairosvg unavailable or failed ({str(e)[:60]}); keeping the SVG")
        out = PREVIEW_DIR / f"{aid}.{'jpg' if ext == 'jpeg' else ext}"
        out.write_bytes(data)
        log(f"wrote {out.relative_to(ROOT)}")
        return out
    return None


def fetch_previews(ordered: list[dict], cfg: dict, dry_run: bool) -> int:
    pcfg = cfg["previews"]
    if not pcfg.get("enabled") or dry_run:
        return 0
    n = 0
    for rec in ordered:
        if n >= int(pcfg["max_per_run"]):
            log(f"preview limit reached ({n} this run); the rest will follow on later runs")
            break
        if find_preview(rec["arxiv_id"]):
            continue
        if fetch_preview(rec, pcfg):
            n += 1
            time.sleep(OAI_DELAY_SECONDS)
    return n


# --------------------------------------------------------------------------- #
# group members' recent papers (_data/members.yml -> _data/member_papers.yml)
# --------------------------------------------------------------------------- #
DOI_PHYSREV_RE = re.compile(r"^10\.1103/(PhysRev[A-Za-z]*|RevModPhys)\.(\d+)\.(\d+)$")
PHYSREV_NAMES = {
    "PhysRevLett": "Phys. Rev. Lett.", "PhysRevX": "Phys. Rev. X", "PhysRevB": "Phys. Rev. B",
    "PhysRevA": "Phys. Rev. A", "PhysRevE": "Phys. Rev. E", "PhysRevD": "Phys. Rev. D",
    "PhysRevResearch": "Phys. Rev. Research", "PhysRevApplied": "Phys. Rev. Applied",
    "PRXQuantum": "PRX Quantum", "RevModPhys": "Rev. Mod. Phys.",
}


def load_members() -> dict:
    if not MEMBERS_PATH.exists():
        return {}
    with MEMBERS_PATH.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    members = {}
    for key, m in raw.items():
        m = m or {}
        names = [n for n in (m.get("arxiv_names") or []) if n]
        if not names:
            continue
        members[str(key)] = {
            "names": names,
            "exclude": {strip_version(str(x)) for x in (m.get("exclude") or [])},
            "count": int(m.get("count") or 3),
        }
    return members


def member_venue(rec: dict, cfg: dict) -> str:
    """Journal reference for display: site override > arXiv journal-ref > Phys. Rev. DOI > 'arXiv:<id>'."""
    ov = cfg["overrides"].get(rec["arxiv_id"]) or {}
    if ov.get("journal") and "accepted" not in str(ov["journal"]).lower():
        parts = str(ov["journal"])
        if ov.get("volume"):
            parts += f" {ov['volume']}"
        if ov.get("pages"):
            parts += f", {ov['pages']}"
        if ov.get("year"):
            parts += f" ({ov['year']})"
        return parts
    if rec.get("journal_ref"):
        return " ".join(str(rec["journal_ref"]).split())
    m = DOI_PHYSREV_RE.match(rec.get("doi") or "")
    if m:
        return f"{PHYSREV_NAMES.get(m.group(1), m.group(1))} {m.group(2)}, {m.group(3)}"
    return f"arXiv:{rec['arxiv_id']}"


def member_entry(rec: dict, cfg: dict) -> dict:
    return {
        "id": rec["arxiv_id"],
        "title": rec["title"],
        "venue": member_venue(rec, cfg),
        "date": rec.get("submitted") or rec.get("published") or "",
        "url": f"https://arxiv.org/abs/{rec['arxiv_id']}",
        "authors": rec["authors"],
        "primary": rec.get("primary_category", ""),
    }


def entry_to_member_rec(e: dict) -> dict:
    """Turn a cached member_papers.yml entry back into the minimal record shape."""
    return {
        "arxiv_id": str(e["id"]), "title": e["title"], "authors": e.get("authors") or [],
        "submitted": str(e.get("date") or ""), "published": str(e.get("date") or ""),
        "primary_category": e.get("primary") or "", "journal_ref": None, "doi": None,
        "_venue": e.get("venue"),
    }


def member_candidate_ids(names: list[str], api_ok: bool) -> tuple[list[str], dict[str, dict]]:
    """arXiv IDs (newest first) for a member, plus any full records the API returned."""
    recs: dict[str, dict] = {}
    if api_ok:
        query = " OR ".join(f'au:"{n}"' for n in names)
        for e in query_arxiv(query, 30):
            r = entry_to_record(e)
            recs[r["arxiv_id"]] = r
        ids = list(recs)
    else:
        ids = []
        for n in names:
            last, first = split_name(n)
            for i in search_author_ids(f"{last}, {first}", 30):
                if i not in ids:
                    ids.append(i)
            time.sleep(OAI_DELAY_SECONDS)
    # new-style IDs sort chronologically (YYMM.NNNNN)
    ids.sort(key=lambda i: tuple(int(x) for x in re.findall(r"\d+", i)[:2]) if re.match(r"\d{4}\.\d{4,5}$", i) else (0, 0), reverse=True)
    return ids, recs


def update_member_papers(cfg: dict, pi_records: dict[str, dict], api_ok: bool, seed: list[dict] | None, dry_run: bool) -> int:
    """Refresh _data/member_papers.yml. Returns the number of members whose list changed."""
    members = load_members()
    if not members:
        return 0
    old = {}
    if MEMBER_PAPERS_PATH.exists():
        old = yaml.safe_load(MEMBER_PAPERS_PATH.read_text(encoding="utf-8")) or {}
    cache: dict[str, dict] = {}
    for entries in old.values():
        for e in entries or []:
            cache[str(e["id"])] = entry_to_member_rec(e)
    seed_recs = {r["arxiv_id"]: r for r in (seed or [])}

    new: dict[str, list] = {}
    for key, m in members.items():
        try:
            if seed is not None:
                ids = sorted((i for i, r in seed_recs.items() if author_matches(r["authors"], m["names"])), reverse=True)
                api_recs = {}
            else:
                ids, api_recs = member_candidate_ids(m["names"], api_ok)
            picked: list[dict] = []
            for aid in ids:
                if len(picked) >= m["count"]:
                    break
                if aid in m["exclude"]:
                    continue
                rec = api_recs.get(aid) or seed_recs.get(aid) or pi_records.get(aid) or cache.get(aid)
                if rec is None:
                    rec = oai_record(aid)
                    time.sleep(OAI_DELAY_SECONDS)
                    if rec is None:
                        continue
                if not author_matches(rec["authors"], m["names"]):
                    continue  # the search matched a different person
                if not category_allowed(rec.get("primary_category", ""), cfg["categories"]):
                    continue
                entry = member_entry(rec, cfg)
                if rec.get("_venue") and entry["venue"].startswith("arXiv:"):
                    entry["venue"] = rec["_venue"]  # keep a venue from the cache when nothing better is known
                picked.append(entry)
            new[key] = picked
            log(f"member {key}: {', '.join(p['id'] for p in picked) or 'no papers'}")
        except Exception as e:  # one member failing must not break the nightly run
            log(f"member {key}: lookup failed ({str(e)[:120]}); keeping the previous list")
            new[key] = old.get(key) or []

    changed = sum(1 for k in new if new[k] != (old.get(k) or []))
    if dry_run:
        sys.stdout.write(yaml.safe_dump(new, allow_unicode=True, sort_keys=False, width=1000))
        return changed
    if new == old:
        log("member_papers.yml unchanged")
        return 0
    header = (
        "# GENERATED by bin/update_arxiv.py from _data/members.yml - do not edit by hand.\n"
        "# Each member's most recent arXiv papers, shown on the group page by\n"
        "# _includes/member_papers.liquid. To hide a paper, add its arXiv ID to the\n"
        "# member's `exclude:` list in _data/members.yml.\n"
    )
    MEMBER_PAPERS_PATH.write_text(header + yaml.safe_dump(new, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    log(f"wrote {MEMBER_PAPERS_PATH.relative_to(ROOT)} ({changed} member(s) changed)")
    return changed


# --------------------------------------------------------------------------- #
# conversion
# --------------------------------------------------------------------------- #
def entry_to_record(entry: ET.Element) -> dict:
    raw_id = entry.findtext("a:id", default="", namespaces=NS).rsplit("/abs/", 1)[-1]
    arxiv_id = strip_version(raw_id)
    title = " ".join((entry.findtext("a:title", default="", namespaces=NS) or "").split())
    abstract = " ".join((entry.findtext("a:summary", default="", namespaces=NS) or "").split())
    authors = [a.findtext("a:name", default="", namespaces=NS) for a in entry.findall("a:author", NS)]
    submitted = entry.findtext("a:published", default="", namespaces=NS)[:10]
    published = published_from_id(raw_id, submitted)
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
        "submitted": submitted,
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
    ov = cfg["overrides"].get(rec["arxiv_id"]) or {}
    if "year" in ov and "month" not in ov:
        fields.pop("month", None)  # the arXiv month would not match an overridden (journal) year
    for k, v in ov.items():
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
    ap.add_argument("--members-seed", metavar="RECORDS.json", help="offline: build _data/member_papers.yml from a JSON list of arXiv records")
    ap.add_argument("--members-only", action="store_true", help="only refresh _data/member_papers.yml")
    args = ap.parse_args()

    cfg = load_config()

    fetched: list[dict] = []
    api_ok = True
    if args.members_only and args.members_seed:
        seed = json.loads(Path(args.members_seed).read_text(encoding="utf-8"))
        seed = [{"arxiv_id": strip_version(r["id"]), "title": r["title"], "authors": r["authors"], "submitted": r.get("submitted", ""),
                 "published": r.get("submitted", ""), "primary_category": r.get("primary", ""), "journal_ref": r.get("journal_ref") or None,
                 "doi": r.get("doi") or None} for r in seed]
        update_member_papers(cfg, {}, False, seed, args.dry_run)
        return 0
    if args.from_file:
        root = ET.fromstring(Path(args.from_file).read_bytes())
        fetched = [entry_to_record(e) for e in root.findall("a:entry", NS)]
    else:
        try:
            raw_entries = query_arxiv(cfg["author_query"], int(cfg["max_results"]))
            seen_ids = {strip_version(e.findtext("a:id", default="", namespaces=NS).rsplit("/abs/", 1)[-1]) for e in raw_entries}
            extra = [i for i in cfg["include"] if i not in seen_ids]
            if extra:
                time.sleep(PAGE_DELAY_SECONDS)
                raw_entries.extend(fetch_by_ids(extra))
            fetched = [entry_to_record(e) for e in raw_entries]
            log(f"API: fetched {len(fetched)} records")
        except ArxivUnavailable as e:
            api_ok = False
            log(f"API unavailable ({e}); falling back to arxiv.org search + OAI-PMH")
            try:
                fetched = records_via_search_and_oai(cfg)
            except ArxivUnavailable as e2:
                # Leave papers.bib untouched and let the next scheduled run try again.
                # Printed as a GitHub Actions warning annotation; exit 0 so the run is not marked failed.
                print(f"::warning title=arXiv unavailable::{e2} - papers.bib left unchanged.")
                log(str(e2))
                return 0

    if not fetched and not args.from_file:
        print("::warning title=arXiv returned no papers::query matched nothing; papers.bib left unchanged.")
        return 0

    records: dict[str, dict] = {}
    skipped: list[str] = []
    for rec in fetched:
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

    # thumbnails first, so that build_fields() sees the new files
    before = old_bib_published()
    n_previews = fetch_previews(ordered, cfg, args.dry_run)
    n_news = generate_news(ordered, cfg, before, args.dry_run)
    if n_previews or n_news:
        log(f"{n_previews} thumbnails, {n_news} news items added")
    if not args.from_file:
        try:
            update_member_papers(cfg, records, api_ok, None, args.dry_run)
        except Exception as e:  # never let the members' lists break the publication update
            log(f"member papers skipped ({str(e)[:120]})")

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
