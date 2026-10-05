#!/usr/bin/env python3
"""Build the complete static website using only the Python standard library."""

import argparse
import html
import json
import shutil
from datetime import datetime
from pathlib import Path
from string import Template

from common import ROOT, is_first_author, load_json, publications


def esc(value):
    return html.escape(str(value), quote=True)


def template(filename, **values):
    source = (ROOT / "templates" / filename).read_text(encoding="utf-8")
    return Template(source).substitute(values)


def publication_list(papers, profile):
    entries = []
    aliases = profile["author_aliases"]
    for paper in papers:
        authors = ", ".join(
            f"<strong>{esc(author)}</strong>" if is_first_author([author], aliases) else esc(author)
            for author in paper["authors"]
        )
        links = []
        for label, key in (("Abstract", "abstract_url"), ("PDF", "pdf_url"), ("Journal", "doi_url"), ("Code", "code_url")):
            if paper.get(key):
                links.append(f'<a href="{esc(paper[key])}" aria-label="{label}: {esc(paper["title"])}">{label}</a>')
        entries.append(
            '<li class="publication"><article>'
            f'<h3>{esc(paper["title"])}</h3>'
            '<div class="publication-meta">'
            f'<p class="publication-authors">{authors}</p>'
            f'<p class="publication-venue">{esc(paper["venue"])}</p>'
            '</div>'
            f'<div class="publication-links">{"".join(links)}</div>'
            '</article></li>'
        )
    return '<ol class="publication-list">' + "\n".join(entries) + '</ol>'


def grouped_publications(papers, profile):
    years = sorted({p["date"][:4] for p in papers}, reverse=True)
    return "\n".join(
        f'<h3 class="year-heading">{year}</h3>'
        + publication_list([p for p in papers if p["date"].startswith(year)], profile)
        for year in years
    )


def talk_list(talks):
    entries = []
    for talk in sorted(talks, key=lambda talk: talk["date"], reverse=True):
        date = datetime.strptime(talk["date"], "%Y-%m").strftime("%b %Y")
        kind = {"invited": "Invited Talk", "contributed": "Contributed Talk"}[talk["kind"]]
        venue = f'<p class="talk-venue">{esc(talk["venue"])}</p>' if talk.get("venue") else ""
        entries.append(
            '<li class="talk"><article class="talk-row">'
            f'<time class="talk-date" datetime="{esc(talk["date"])}">{date}</time>'
            f'<span class="talk-type">{kind}</span>'
            f'<div class="talk-content"><h2 class="talk-event">{esc(talk["event"])}</h2>'
            f'{venue}<p class="talk-title">{esc(talk["title"])}</p></div>'
            f'<p class="talk-location">{esc(talk["location"])}</p>'
            '</article></li>'
        )
    return '<ol class="talk-list">' + "\n".join(entries) + '</ol>'


def build(output):
    profile = load_json(ROOT / "data/profile.json")
    talks = load_json(ROOT / "data/talks.json")
    papers = publications()
    talk_cutoff = max((int(talk["date"][:4]) for talk in talks), default=0) - 1
    recent_talks = [talk for talk in talks if int(talk["date"][:4]) >= talk_cutoff]
    previous_talks = [talk for talk in talks if int(talk["date"][:4]) < talk_cutoff]
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "assets", output / "assets", dirs_exist_ok=True)
    shutil.copyfile(ROOT / "CNAME", output / "CNAME")
    (output / ".nojekyll").touch()
    scholar = f'https://scholar.google.com/citations?user={profile["scholar_id"]}&hl=en'
    education = "\n".join(
        '<div class="education-entry"><div class="education-title">'
        f'<h3>{esc(e["institution"])}</h3><time>{esc(e["years"])}</time></div>'
        f'<p>{esc(e["degree"])}</p>'
        + (f'<p class="education-note">{esc(e["note"])}</p>' if e["note"] else "")
        + '</div>' for e in profile["education"]
    )
    courses = '<ul class="course-list">' + "\n".join(
        '<li class="course">'
        f'<h3>{esc(c["title"])}</h3><p class="course-meta"><span>{esc(c["level"])}</span>'
        f'<span>{esc(c["term"])}</span></p></li>' for c in profile["teaching"]
    ) + '</ul>'
    pages = {
        "/": ("About", template("about.html", role=esc(profile["role"]), affiliation=esc(profile["affiliation"]), education=education)),
        "/research/": ("Research", template("research.html", scholar_url=esc(scholar), selected_publications=grouped_publications(papers, profile))),
        "/talks/": ("Talks", template("talks.html", recent_talks=talk_list(recent_talks), previous_talks=talk_list(previous_talks))),
        "/teaching/": ("Teaching", template("teaching.html", courses=courses)),
        "/404.html": ("Page not found", '<div class="page-heading"><p class="eyebrow">404</p><h1>That page has moved.</h1></div><p>Visit the <a href="/">homepage</a> or browse my <a href="/research/">research</a>.</p>')
    }
    identity = {key: esc(profile[key]) for key in ("name", "chinese_name", "role", "affiliation", "email", "github_url")}
    sidebar = template("profile.html", scholar_url=esc(scholar), **identity)
    for path, (label, content) in pages.items():
        navigation = "".join(
            f'<a href="{url}"' + (' aria-current="page"' if url == path else '') + f'>{name}</a>'
            for url, name in (("/", "About"), ("/research/", "Research"), ("/talks/", "Talks"), ("/teaching/", "Teaching"))
        )
        person = json.dumps({"@context": "https://schema.org", "@type": "Person", "name": profile["name"], "alternateName": profile["chinese_name"], "jobTitle": profile["role"], "worksFor": {"@type": "Organization", "name": profile["affiliation"]}, "url": profile["url"], "sameAs": [scholar, profile["github_url"]]}, ensure_ascii=False).replace("<", "\\u003c")
        rendered = template("base.html", title=esc(profile["name"] if path == "/" else f'{label} · {profile["name"]}'), description=esc(profile["description"]), canonical=esc(profile["url"] + path), site_url=esc(profile["url"]), person_json=person, navigation=navigation, content=content, profile="" if path == "/talks/" else sidebar, layout_class="page-shell--wide" if path == "/talks/" else "", year=datetime.now().year, **identity)
        destination = output / (path.lstrip("/") if path.endswith(".html") else path.lstrip("/") + "index.html")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    # Keep useful old URLs, without retaining the old theme or placeholder pages.
    redirects = {"/about/": "/", "/about.html": "/", "/index.html": None, "/research.html": "/research/", "/publications/": "/research/", "/publications.html": "/research/", "/talks.html": "/talks/", "/teaching.html": "/teaching/", "/cv/": "/#education-heading", "/resume/": "/#education-heading", "/publication/24-QNN/": "/research/", "/publication/24-virtualcomb/": "/research/#first-author", "/publication/2010-10-01-paper-title-number-2/": "/research/#first-author", "/publication/2015-10-01-paper-title-number-3/": "/research/#first-author"}
    for source, target in redirects.items():
        if target is None:
            continue
        destination = output / (source.lstrip("/") if source.endswith(".html") else source.lstrip("/") + "index.html")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={target}"><link rel="canonical" href="{esc(profile["url"] + target)}"><title>Page moved · {esc(profile["name"])}</title></head><body><a href="{target}">Continue to {esc(target)}</a></body></html>\n', encoding="utf-8")
    (output / "robots.txt").write_text(f'User-agent: *\nAllow: /\nSitemap: {profile["url"]}/sitemap.xml\n', encoding="utf-8")
    (output / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f'<url><loc>{esc(profile["url"] + path)}</loc></url>' for path in pages if path != "/404.html") + '</urlset>\n', encoding="utf-8")
    print(f"Built {len(pages)} pages, {len(papers)} selected publications, and {len(talks)} talks in {output}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        parser.error("Output must be a separate build directory.")
    build(output)
