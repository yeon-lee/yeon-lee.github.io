# Lee Group @ UIUC — website

Source of <https://yeon-lee.github.io>, built with [Jekyll](https://jekyllrb.com/) and the
[al-folio](https://github.com/alshedivat/al-folio) theme, hosted on GitHub Pages.

**Nothing needs to be built by hand.** Every push to `main` triggers the *Deploy site* workflow, which
builds the site and publishes it to the `gh-pages` branch (2–4 minutes). Publications are pulled from
arXiv automatically every night.

## Where things live

| I want to…                              | Edit…                                                                                                                     |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| edit the home page text                 | `_pages/about.md`                                                                                                         |
| change the *featured work* cards        | `_data/featured.yml` (one block per card) · `assets/img/featured/<name>.png` (1200×800, white background)                 |
| edit the bio                            | `_pages/bio.md` (text) · `assets/img/prof_pic.jpg` (photo)                                                                |
| add / remove a group member             | `_pages/group.md` (one block per person) · `_pages/people/<name>.md` (their blurb) · `assets/img/people/<name>.jpg`       |
| member's "Recent papers" / Scholar link | `_data/members.yml` (arXiv name, wrong-person exclusions; lists refresh nightly) · Scholar link in `_pages/group.md` |
| edit the research text                  | `_pages/research.md` (one `<section class="topic">` per direction)                                                        |
| change the research map                 | `bin/make_research_map.py` (topics, keywords, positions) → `python3 bin/make_research_map.py --style glow > _includes/research_map.svg` and `--style cards > _includes/research_cards.html` (phone version); other styles: ink, radial, pastel |
| mark a paper as *selected* (home page)  | `_data/arxiv.yml` → `overrides:` → `"<arXiv id>": {selected: true}`                                                       |
| add a thumbnail to a paper              | drop `assets/img/publication_preview/<arXiv id>.png` (picked up automatically)                                            |
| hide a paper / add a non-arXiv paper    | `_data/arxiv.yml` → `exclude:` / `_bibliography/manual.bib`                                                               |
| add a course                            | new file in `_teachings/` (copy `2025-spring-physics-598.md`)                                                             |
| update the CV / talks                   | `_data/cv.yml` — the PDF is regenerated automatically                                                                     |
| post news (home page + `/news/`)        | new file in `_news/` (copy an existing one; `inline: true` = one-liner). New preprints get a news item automatically — see below |
| edit the join page                      | `_pages/join.md`                                                                                                          |
| write a note / blog post                | new file `_posts/YYYY-MM-DD-title.md` (copy `2026-09-27-new-website.md`)                                                  |
| change contact / social icons           | `_data/socials.yml`                                                                                                       |
| site title, description, colours, flags | `_config.yml`                                                                                                             |
| fonts, featured grid, map styling       | `_sass/_custom.scss` (loaded last by `assets/css/main.scss`)                                                              |

Do **not** edit `_bibliography/papers.bib` — it is generated and will be overwritten (see below).

The QID 2025 workshop site lives in the separate repo [`yeon-lee/qid2025`](https://github.com/yeon-lee/qid2025) and is served at
<https://yeon-lee.github.io/qid2025/>; `_pages/moved/` holds redirect stubs for its old root-level URLs.

## How publications stay up to date

```
_data/arxiv.yml  ──►  bin/update_arxiv.py  ──►  _bibliography/papers.bib  ──►  /publications/
(query, filters,       (GitHub Action,            (generated; do not edit)
 per-paper overrides)   nightly + on demand)
```

- `.github/workflows/update-arxiv.yml` runs every night (06:17 UTC), whenever `_data/arxiv.yml`,
  `_bibliography/manual.bib` or the script changes, or on demand from **Actions → Update publications
  from arXiv → Run workflow**.
- The script queries arXiv for `au:"Jong Yeon Lee"`, keeps papers in the configured categories,
  converts them to BibTeX (journal reference + DOI when arXiv has them), applies the overrides, appends
  `manual.bib`, and commits `papers.bib` if anything changed. It then triggers a site deploy.
- arXiv blocks its query API from cloud IP ranges (GitHub Actions gets HTTP 406), so on the runner the
  script automatically falls back to the arxiv.org author-search page for the list of IDs and OAI-PMH
  (`oaipmh.arxiv.org`) for each record. Same data, different door. If arXiv is unreachable altogether the
  run logs a warning and leaves `papers.bib` untouched. `diag-arxiv.yml` (Actions → *Diagnose arXiv
  access* → Run workflow) prints which arXiv endpoints the runner can reach, for debugging.
- **News items.** For every preprint submitted after `news.since` (in `_data/arxiv.yml`) the script writes
  `_news/<date>-arxiv-<id>.md`: "New preprint with <group members>: *title* — one-line highlight". The
  highlight is written by Claude when the repository secret `ANTHROPIC_API_KEY` is set (**Settings → Secrets and
  variables → Actions → New repository secret**); without it the first sentence of the abstract is used. When a paper
  later gains a journal reference, a "Published in …" item follows. Existing files are never rewritten, so edit or
  delete them freely; group members are listed under `news.members`.
- **Thumbnails.** Figure 1 of each paper is downloaded from its arXiv HTML version into
  `assets/img/publication_preview/<id>.png` (at most `previews.max_per_run` per run, so the backlog takes a few
  nights). Papers without an HTML version (before 2024) get none unless you drop a `<id>.png` there yourself.
- Journal references come from arXiv's `journal-ref` field, which authors fill in themselves — if a
  published paper still shows as a preprint, update the journal-ref on arXiv (or add a `journal:` override
  in `_data/arxiv.yml`).

To run it locally: `pip install pyyaml && python3 bin/update_arxiv.py --dry-run`.

## Workflows

| Workflow                                   | When                                             | What                                              |
| ------------------------------------------ | ------------------------------------------------ | ------------------------------------------------- |
| `deploy.yml` — Deploy site                 | every push to `main`                             | builds the site, publishes to `gh-pages`          |
| `update-arxiv.yml` — Update publications   | nightly, on demand, when `_data/arxiv.yml` changes | regenerates `papers.bib`, news items and thumbnails, commits, redeploys |
| `render-cv.yml` — Render a CV              | when `_data/cv.yml` changes                      | renders `assets/rendercv/rendercv_output/Jong_Yeon_Lee_CV.pdf`, commits, redeploys |
| `diag-arxiv.yml` — Diagnose arXiv access   | on demand                                        | probes arXiv endpoints from the runner (debugging only)   |

One-time GitHub settings (already done if the site is live): **Settings → Actions → General → Workflow
permissions → Read and write**, and **Settings → Pages → Source: Deploy from a branch → `gh-pages` / root**.

## Previewing locally (optional)

With Docker installed:

```bash
docker compose up
# then open http://localhost:8080
```

Or with Ruby ≥ 3.3: `bundle install && bundle exec jekyll serve` → <http://localhost:4000>.

## Upgrading the theme

al-folio v1 keeps all layouts in versioned gems, so upgrading is a matter of bumping the `al_*` gem
versions in `Gemfile` (they must match the `plugins:` list in `_config.yml`). `bundle exec al-folio upgrade audit`
reports what would change. See the [al-folio docs](https://github.com/alshedivat/al-folio/tree/main/docs).

Two theme files are overridden locally on purpose: `assets/css/main.scss` (a copy of the gem's file plus
`@use "custom";`, which pulls in `_sass/_custom.scss` for the serif font, featured grid and research map) and
`_includes/featured.liquid` / `_includes/research_map*.{liquid,svg}` (site-specific includes, not in the
theme). After bumping `al_folio_core`, re-copy its `assets/css/main.scss` and re-add the `@use "custom";` line
if the upgrade audit flags it.

## License

The site content (text, photos, CV) is © Jong Yeon Lee. The theme is MIT-licensed (see `LICENSE`).
