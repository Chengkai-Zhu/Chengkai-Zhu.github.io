#!/usr/bin/env python3
"""Sync first-author papers from Google Scholar, with an arXiv fallback."""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

from bs4 import BeautifulSoup

from common import ROOT, arxiv_id, is_first_author, load_json, merge_publications, normalize, validate_publication, write_json

ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom", "o": "http://a9.com/-/spec/opensearch/1.1/"}


class SourceError(RuntimeError):
    pass


class Client:
    def __init__(self, email):
        self.agent = f"ChengkaiZhuHomepage/1.0 (+https://chengkaizhu.site; {email})"
        self.last_request = {}

    def get(self, url):
        host = urllib.parse.urlparse(url).hostname
        interval = 3.1 if host and host.endswith("arxiv.org") else 1.1
        pause = interval - (time.monotonic() - self.last_request.get(host, 0))
        if pause > 0:
            time.sleep(pause)
        for attempt in range(2):
            try:
                self.last_request[host] = time.monotonic()
                request = urllib.request.Request(url, headers={"User-Agent": self.agent})
                with urllib.request.urlopen(request, timeout=25) as response:
                    return response.read().decode("utf-8")
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 429):
                    raise SourceError(f"{host} rejected automated access (HTTP {exc.code}).") from None
                if attempt == 1:
                    raise SourceError(f"{host} could not be reached ({type(exc).__name__}).") from None
                time.sleep(4)
        raise SourceError(f"No response from {host}.")


def parse_arxiv(xml, author_name):
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise SourceError("arXiv returned invalid XML.") from exc
    if root.tag != "{http://www.w3.org/2005/Atom}feed":
        raise SourceError("arXiv did not return an Atom feed.")
    papers = []
    for entry in root.findall("a:entry", ATOM):
        identifier = entry.findtext("a:id", "", ATOM)
        if "/api/errors" in identifier:
            raise SourceError("arXiv returned an API error.")
        authors = [node.findtext("a:name", "", ATOM).strip() for node in entry.findall("a:author", ATOM)]
        # arXiv is a global author search: require the full name, not initials.
        if not is_first_author(authors, [author_name]):
            continue
        aid = arxiv_id(identifier)
        if not aid:
            raise SourceError("arXiv returned an unrecognized paper identifier.")
        published = entry.findtext("a:published", "", ATOM)[:10]
        journal = entry.findtext("arxiv:journal_ref", "", ATOM).strip()
        paper = {
            "title": " ".join(entry.findtext("a:title", "", ATOM).split()),
            "authors": authors,
            "date": published,
            "venue": journal or f"arXiv:{aid} ({published[:4]})",
            "kind": "published" if journal else "preprint",
            "abstract_url": f"https://arxiv.org/abs/{aid}",
            "pdf_url": f"https://arxiv.org/pdf/{aid}",
            "source": "arxiv"
        }
        doi = entry.findtext("arxiv:doi", "", ATOM).strip()
        if doi:
            paper["doi_url"] = "https://doi.org/" + doi
        validate_publication(paper)
        papers.append(paper)
    return papers, int(root.findtext("o:totalResults", "0", ATOM))


def fetch_arxiv(client, profile):
    papers = []
    for start in range(0, 2000, 100):
        query = urllib.parse.urlencode({"search_query": f'au:"{profile["arxiv_author"]}"', "start": start, "max_results": 100, "sortBy": "submittedDate", "sortOrder": "descending"})
        try:
            xml = client.get("https://export.arxiv.org/api/query?" + query)
        except SourceError:
            xml = client.get("https://arxiv.org/api/query?" + query)
        batch, total = parse_arxiv(xml, profile["name"])
        papers = merge_publications(papers, batch)
        if start + 100 >= total:
            return papers
    raise SourceError("arXiv exceeded the pagination limit; refusing an incomplete sync.")


def parse_scholar_profile(document, expected_name):
    soup = BeautifulSoup(document, "html.parser")
    name = soup.select_one("#gsc_prf_in")
    if not name or normalize(name.get_text()) != normalize(expected_name):
        raise SourceError("Google Scholar did not return the expected public profile (it may be blocking automated access).")
    rows = []
    for row in soup.select(".gsc_a_tr"):
        title = row.select_one(".gsc_a_at")
        details = row.select(".gs_gray")
        year = row.select_one(".gsc_a_y")
        if not title or not title.get("href") or not details:
            raise SourceError("Google Scholar returned an incomplete publication row.")
        rows.append({"title": title.get_text(" ", strip=True), "detail_url": urllib.parse.urljoin("https://scholar.google.com", title["href"]), "first_author": details[0].get_text(" ", strip=True).split(",")[0], "year": year.get_text(strip=True) if year else ""})
    more = soup.select_one("#gsc_bpf_more")
    return rows, bool(more and not more.has_attr("disabled"))


def parse_scholar_detail(document):
    soup = BeautifulSoup(document, "html.parser")
    title = soup.select_one("#gsc_oci_title")
    fields = {}
    for row in soup.select(".gs_scl"):
        label, value = row.select_one(".gsc_oci_field"), row.select_one(".gsc_oci_value")
        if label and value:
            fields[label.get_text(strip=True)] = value.get_text(" ", strip=True)
    if not title or not fields.get("Authors"):
        raise SourceError("Google Scholar did not return full author metadata.")
    authors = [a.strip() for a in fields["Authors"].split(",")]
    if any("…" in a or "..." in a or a.lower() == "et al." for a in authors):
        raise SourceError("Google Scholar truncated the author list; first authorship is not verified.")
    links = [urllib.parse.urljoin("https://scholar.google.com", a["href"]) for a in soup.select("#gsc_oci_title[href], #gsc_oci_title a[href], .gsc_oci_title_link[href], #gsc_oci_table a[href], #gsc_oci_merged a[href]")]
    return {"title": title.get_text(" ", strip=True), "authors": authors, "publication_date": fields.get("Publication date", ""), "venue": fields.get("Journal") or fields.get("Conference") or fields.get("Source") or "", "links": links}


def scholar_get(client, url):
    """Use the public page by default, or raw Scholar HTML from an optional API."""
    api_key = os.environ.get("SERPAPI_API_KEY", "")
    if not api_key:
        return client.get(url)
    original = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    query = {"engine": "google_scholar_author", "api_key": api_key, "output": "html", "hl": "en"}
    for old, new in (("user", "author_id"), ("sortby", "sort"), ("pagesize", "num"), ("cstart", "start"), ("view_op", "view_op"), ("citation_for_view", "citation_id")):
        if original.get(old):
            query[new] = original[old]
    return client.get("https://serpapi.com/search?" + urllib.parse.urlencode(query))


def fetch_scholar(client, profile):
    rows = []
    for start in range(0, 1000, 100):
        query = urllib.parse.urlencode({"user": profile["scholar_id"], "hl": "en", "pagesize": 100, "cstart": start, "sortby": "pubdate"})
        batch, more = parse_scholar_profile(scholar_get(client, "https://scholar.google.com/citations?" + query), profile["name"])
        rows.extend(batch)
        if not more:
            break
    else:
        raise SourceError("Google Scholar exceeded the pagination limit.")
    details = []
    for row in rows:
        if not is_first_author([row["first_author"]], profile["author_aliases"]):
            continue
        detail = parse_scholar_detail(scholar_get(client, row["detail_url"]))
        if is_first_author(detail["authors"], profile["author_aliases"]):
            detail["year"] = row["year"]
            details.append(detail)
    return details


def publication_date(value, year=""):
    parts = re.split(r"[/\-]", value.strip() or year.strip())
    if not parts or not re.fullmatch(r"\d{4}", parts[0]):
        raise ValueError("Publication date is missing.")
    return date(int(parts[0]), int(parts[1]) if len(parts) > 1 else 1, int(parts[2]) if len(parts) > 2 else 1).isoformat()


def scholar_publication(detail, known):
    match = next((p for p in known if normalize(p["title"]) == normalize(detail["title"]) or any(arxiv_id(url) and arxiv_id(url) == arxiv_id(p["abstract_url"]) for url in detail["links"])), None)
    # Reuse verified PDF links; never invent a PDF from a generic DOI.
    abstract_url = match["abstract_url"] if match else None
    pdf_url = match["pdf_url"] if match else None
    for url in detail["links"]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            continue
        aid = arxiv_id(url)
        if aid:
            abstract_url, pdf_url = f"https://arxiv.org/abs/{aid}", f"https://arxiv.org/pdf/{aid}"
            break
        if parsed.hostname == "journals.aps.org" and "/abstract/" in parsed.path:
            abstract_url, pdf_url = url, url.replace("/abstract/", "/pdf/")
        elif parsed.hostname == "www.nature.com" and "/articles/" in parsed.path and not parsed.path.endswith(".pdf"):
            abstract_url, pdf_url = url, url.split("?")[0] + ".pdf"
        elif parsed.path.lower().endswith(".pdf"):
            pdf_url = url
        elif not abstract_url and parsed.hostname not in ("scholar.google.com", "www.google.com"):
            abstract_url = url
    if not abstract_url or not pdf_url:
        raise ValueError("No verified Abstract/PDF pair was found.")
    paper = dict(match or {})
    paper.update(title=detail["title"], authors=detail["authors"], abstract_url=abstract_url, pdf_url=pdf_url, source="google_scholar")
    venue = detail["venue"]
    is_journal = bool(venue and not venue.lower().startswith("arxiv"))
    if is_journal or not match:
        paper["date"] = publication_date(detail["publication_date"], detail.get("year", ""))
        paper["venue"] = f'{venue} ({paper["date"][:4]})' if venue else f'Preprint ({paper["date"][:4]})'
        paper["kind"] = "published" if is_journal else "preprint"
    validate_publication(paper)
    return paper


def sync(client, profile, existing, curated):
    status, incoming, pending = {}, [], []
    try:
        incoming = fetch_arxiv(client, profile)
        status["arxiv"] = {"state": "success", "first_author_papers": len(incoming)}
    except (SourceError, ValueError) as exc:
        status["arxiv"] = {"state": "failed", "reason": str(exc)}
    try:
        scholar = fetch_scholar(client, profile)
        known = merge_publications(merge_publications(existing, incoming), curated)
        for detail in scholar:
            try:
                incoming = merge_publications(incoming, [scholar_publication(detail, known)])
            except ValueError as exc:
                pending.append({"title": detail["title"], "reason": str(exc)})
        status["google_scholar"] = {"state": "success", "first_author_papers": len(scholar), "access": "serpapi" if os.environ.get("SERPAPI_API_KEY") else "public_html"}
    except (SourceError, ValueError) as exc:
        status["google_scholar"] = {"state": "failed", "reason": str(exc)}
    if all(source["state"] == "failed" for source in status.values()):
        raise SourceError("All sources failed. Existing publication files were left untouched. " + " ".join(source["reason"] for source in status.values()))
    # Use all existing records as a safety net when a source temporarily loses entries.
    papers = merge_publications(existing, incoming)
    papers = [p for p in papers if is_first_author(p["authors"], profile["author_aliases"])]
    report = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": status, "pending": pending, "synced_first_author_papers": len(papers)}
    return papers, report


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the result without changing files.")
    args = parser.parse_args()
    profile = load_json(ROOT / "data/profile.json")
    try:
        papers, report = sync(Client(profile["email"]), profile, load_json(ROOT / "data/synced_publications.json"), load_json(ROOT / "data/publications.json"))
    except SourceError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    for source, result in report["sources"].items():
        if result["state"] == "failed":
            print(f"::warning::{source}: {result['reason']}")
    if report["pending"]:
        print(f"::warning::{len(report['pending'])} papers need a verified PDF link; see data/sync_status.json.")
    if args.dry_run:
        print(json.dumps({"publications": papers, "status": report}, ensure_ascii=False, indent=2))
    else:
        write_json(ROOT / "data/synced_publications.json", papers)
        write_json(ROOT / "data/sync_status.json", report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## Publication sync\n\n" + "\n".join(f"- {name}: {value['state']}" for name, value in report["sources"].items()) + f"\n- Synced first-author records: {len(papers)}\n- Records requiring a PDF link: {len(report['pending'])}\n")
    print(f"Synced {len(papers)} first-author papers.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
