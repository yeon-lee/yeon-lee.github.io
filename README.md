# Lee Group @ UIUC — website

Source of <https://yeon-lee.github.io>, built with [Jekyll](https://jekyllrb.com/) and the
[al-folio](https://github.com/alshedivat/al-folio) theme, hosted on GitHub Pages.

**Nothing needs to be built by hand.** Every push to `main` triggers the *Deploy site* workflow, which
builds the site and publishes it to the `gh-pages` branch (2–4 minutes). Publications are pulled from
arXiv automatically every night.

## Where things live

| I want to…                              | Edit…                                                                                                                     |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| change the bio / home page              | `_pages/about.md` (text) · `assets/img/prof_pic.jpg` (photo)                                                              |
| add / remove a group member             | `_pages/group.md` (one block per person) · `_pages/people/<name>.md` (their blurb) · `assets/img/people/<name>.jpg`       |
| edit the research page                  | `_pages/research.md`                                                                                                      |
| mark a paper as *selected* (home page)  | `_data/arxiv.yml` → `overrides:` → `"<arXiv id>": {selected: true}`                                                       |
| add a thumbnail to a paper              | drop `assets/img/publication_preview/<arXiv id>.png` (picked up automatically)                                            |
| hide a paper / add a non-arXiv paper    | `_data/arxiv.yml` → `exclude:` / `_bibliography/manual.bib`                                                               |
| add a course                            | new file in `_teachings/` (copy `2025-spring-physics-598.md`)                                                             |
| update the CV / talks                   | `_data/cv.yml` — the PDF is regenerated automatically                                                                     |
| post news (home page + `/news/`)        | new file in `_news/` (copy an existing one; `inline: true` = one-liner)                                                   |
| write a note / blog post                | new file `_posts/YYYY-MM-DD-title.md` (copy `2026-09-27-new-website.md`)                                                  |
| change contact / social icons           | `_data/socials.yml`                                                                                                       |
| site title, description, colours, flags | `_config.yml`                                                                                                             |

Do **not** edit `_bibliography/papers.bib` — it is generated and will be overwritten (see below).

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
- Journal references come from arXiv's `journal-ref` field, which authors fill in themselves — if a
  published paper still shows as a preprint, update the journal-ref on arXiv (or add a `journal:` override
  in `_data/arxiv.yml`).

To run it locally: `pip install pyyaml && python3 bin/update_arxiv.py --dry-run`.

## Workflows

| Workflow                                   | When                                             | What                                              |
| ------------------------------------------ | ------------------------------------------------ | ------------------------------------------------- |
| `deploy.yml` — Deploy site                 | every push to `main`                             | builds the site, publishes to `gh-pages`          |
| `update-arxiv.yml` — Update publications   | nightly, on demand, when `_data/arxiv.yml` changes | regenerates `papers.bib`, commits, redeploys     |
| `render-cv.yml` — Render a CV              | when `_data/cv.yml` changes                      | renders `assets/rendercv/rendercv_output/Jong_Yeon_Lee_CV.pdf`, commits, redeploys |

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

## License

The site content (text, photos, CV) is © Jong Yeon Lee. The theme is MIT-licensed (see `LICENSE`).
