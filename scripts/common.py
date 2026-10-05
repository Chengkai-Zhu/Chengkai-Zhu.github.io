"""Shared publication validation, identity matching, and safe merging."""

import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize(value):
    value = unicodedata.normalize("NFKD", value).casefold()
    return "".join(c for c in value if c.isalnum())


def is_first_author(authors, aliases):
    return bool(authors) and normalize(authors[0]) in {normalize(a) for a in aliases}


def arxiv_id(url):
    match = re.search(r"(?:arxiv\.org/(?:abs|pdf)/|arXiv:)\s*(\d{4}\.\d{4,5})(?:v\d+)?", url, re.I)
    return match.group(1) if match else None


def validate_publication(paper):
    for field in ("title", "authors", "date", "venue", "abstract_url", "pdf_url"):
        if not paper.get(field):
            raise ValueError(f"Publication is missing {field}: {paper.get('title', '(untitled)')}")
    if not isinstance(paper["authors"], list) or any(not isinstance(a, str) or not a.strip() for a in paper["authors"]):
        raise ValueError(f"Invalid authors: {paper['title']}")
    date.fromisoformat(paper["date"])
    for key in ("abstract_url", "pdf_url", "doi_url", "code_url"):
        if paper.get(key):
            parsed = urlparse(paper[key])
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError(f"Invalid HTTPS link in {key}: {paper['title']}")


def same_paper(left, right):
    left_id, right_id = arxiv_id(left["abstract_url"]), arxiv_id(right["abstract_url"])
    return (left_id and left_id == right_id) or normalize(left["title"]) == normalize(right["title"])


def merge_publications(existing, incoming):
    """Never discard existing papers; prefer a journal record over a preprint."""
    result = [dict(p) for p in existing]
    for paper in incoming:
        validate_publication(paper)
        match = next((i for i, old in enumerate(result) if same_paper(old, paper)), None)
        if match is None:
            result.append(dict(paper))
        elif not (result[match].get("kind") == "published" and paper.get("kind") != "published"):
            result[match] = {**result[match], **paper}
    return sorted(result, key=lambda p: (p["date"], p["title"]), reverse=True)


def publications():
    profile = load_json(ROOT / "data/profile.json")
    synced = load_json(ROOT / "data/synced_publications.json")
    if any(not is_first_author(p.get("authors"), profile["author_aliases"]) for p in synced):
        raise ValueError("Automatically synced data contains a non-first-author paper.")
    # Curated metadata overrides automatic metadata, including publication dates.
    papers = merge_publications(synced, load_json(ROOT / "data/publications.json"))
    for paper in papers:
        validate_publication(paper)
    return papers


def write_json(path, value):
    path = Path(path)
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
