#!/usr/bin/env python3
"""Check built HTML for broken local links and missing paper links."""

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from common import ROOT, publications


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = set()
        self.links = []
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get("id"):
            if attrs["id"] in self.ids:
                raise ValueError(f"Duplicate HTML ID: {attrs['id']}")
            self.ids.add(attrs["id"])
        for key in ("href", "src"):
            if attrs.get(key):
                self.links.append(attrs[key])


def check_site(output):
    publications()
    pages = {path.resolve(): Document(path.read_text(encoding="utf-8")) for path in output.rglob("*.html")}
    errors = []
    for path, doc in pages.items():
        for url in doc.links:
            split = urlsplit(url)
            if split.scheme or split.netloc:
                continue
            target = (output / unquote(split.path).lstrip("/")) if split.path.startswith("/") else path.parent / unquote(split.path)
            if not split.path:
                target = path
            elif target.is_dir() or split.path.endswith("/"):
                target /= "index.html"
            target = target.resolve()
            if not target.is_file():
                errors.append(f"{path.relative_to(output)}: missing {url}")
            elif split.fragment and target in pages and unquote(split.fragment) not in pages[target].ids:
                errors.append(f"{path.relative_to(output)}: missing anchor {url}")
    research = (output / "research/index.html").read_text(encoding="utf-8")
    count = len(publications())
    if research.count('class="publication"') != count:
        errors.append("Research does not render every publication exactly once.")
    for label in ("Abstract", "PDF"):
        if research.count(f'>{label}</a>') != count:
            errors.append(f"Research must have a {label} link for every publication.")
    if errors:
        raise ValueError("\n".join(errors))
    print(f"Validated {len(pages)} HTML files, all local links and anchors, and {count} Abstract/PDF pairs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    check_site(parser.parse_args().output.resolve())
