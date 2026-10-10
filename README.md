# Chengkai Zhu

Personal website of Chengkai Zhu, Research Scientist at QudeLeap: [chengkaizhu.site](https://chengkaizhu.site).

A custom static site with About, Research, Talks, and Teaching pages, light/dark themes, and a soft pointer glow. Built with Python, HTML, CSS, and vanilla JavaScript.

## Local preview

Requires Python 3.9+.

```sh
python3 scripts/build.py
python3 scripts/check_site.py
python3 -m http.server 8000 --directory _site
```

Open [localhost:8000](http://localhost:8000). Build output: `_site/`.

## Content

Edit `data/` for profile, publications, and talks; `templates/` and `assets/` for layout and styling.

MIT license. Font licenses are included in `assets/fonts/`.
