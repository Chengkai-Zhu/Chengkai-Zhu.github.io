# Chengkai Zhu

Personal website of Chengkai Zhu, Research Scientist at QudeLeap: [chengkaizhu.site](https://chengkaizhu.site).

A custom static site with About, Research, Talks, and Teaching pages. Built with Python, HTML, CSS, and vanilla JavaScript. Fonts are hosted locally; the original visitor map is preserved.

The top-right control switches between light and dark themes and remembers the choice. The initial theme follows the system. A soft glow follows the pointer on desktop, with reduced-motion preferences respected.

## Local preview

Python 3.9+ is sufficient to build the site:

```sh
python3 scripts/build.py
python3 scripts/check_site.py
python3 -m http.server 8000 --directory _site
```

Open [localhost:8000](http://localhost:8000). Generated files in `_site/` are not committed.

## Content

- `data/profile.json`: biography, education, and teaching.
- `data/publications.json`: selected publications.
- `data/publication_exclusions.json`: papers omitted from the site and future syncs.
- `data/talks.json`: talks.
- `templates/` and `assets/`: page content, layout, styles, and fonts.

## Publication updates

GitHub Actions checks Google Scholar and arXiv on the first of each month at 09:17 Asia/Shanghai. It verifies first authorship, preserves existing data when sources fail, and respects the exclusion list. Automatically discovered papers are saved in `data/synced_publications.json`.

Syncing requires `requirements.txt`; an optional `SERPAPI_API_KEY` repository secret supports Scholar access through SerpApi. Direct requests can be rate limited, and a complete live sync remains unverified. See [deployment notes](docs/deployment.md) for setup and manual runs.

## Validation

```sh
.venv/bin/python -m unittest discover -s tests -v
```

MIT license. Font licenses are included in `assets/fonts/`.
