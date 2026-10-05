"""Regression tests for authorship, safe sync failure, and deduplication."""

import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import arxiv_id, filter_publications, is_first_author, merge_publications, validate_publication
from sync_publications import SourceError, parse_arxiv, parse_scholar_detail, parse_scholar_profile, scholar_get, scholar_publication, sync
from build import build, publication_list
from check_site import check_site


def paper(**overrides):
    return {"title": "A quantum test paper", "authors": ["Chengkai Zhu", "Xin Wang"], "date": "2026-09-01", "venue": "arXiv:2609.12345 (2026)", "kind": "preprint", "abstract_url": "https://arxiv.org/abs/2609.12345", "pdf_url": "https://arxiv.org/pdf/2609.12345", **overrides}


PROFILE = {"name": "Chengkai Zhu", "author_aliases": ["Chengkai Zhu", "C Zhu"], "scholar_id": "2c0ZBk8AAAAJ", "arxiv_author": "Chengkai_Zhu"}
ARXIV = '''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/">
<o:totalResults>2</o:totalResults>
<entry><id>http://arxiv.org/abs/2609.12345v2</id><title>A quantum test paper</title><published>2026-09-01T00:00:00Z</published><author><name>Chengkai Zhu</name></author><author><name>Xin Wang</name></author></entry>
<entry><id>http://arxiv.org/abs/2609.54321v1</id><title>A collaboration</title><published>2026-09-02T00:00:00Z</published><author><name>Chenghong Zhu</name></author><author><name>Chengkai Zhu</name></author></entry>
</feed>'''


class PublicationTests(unittest.TestCase):
    def test_optional_scholar_api_maps_profile_and_citation_parameters(self):
        client = Mock()
        with patch.dict("os.environ", {"SERPAPI_API_KEY": "test-placeholder"}):
            scholar_get(client, "https://scholar.google.com/citations?user=2c0ZBk8AAAAJ&sortby=pubdate&pagesize=100&cstart=100")
            query = parse_qs(urlparse(client.get.call_args.args[0]).query)
            self.assertEqual(query["author_id"], ["2c0ZBk8AAAAJ"])
            self.assertEqual(query["start"], ["100"])
            self.assertEqual(query["output"], ["html"])
            scholar_get(client, "https://scholar.google.com/citations?user=2c0ZBk8AAAAJ&view_op=view_citation&citation_for_view=2c0ZBk8AAAAJ:example")
            query = parse_qs(urlparse(client.get.call_args.args[0]).query)
            self.assertEqual(query["citation_id"], ["2c0ZBk8AAAAJ:example"])

    def test_public_scholar_needs_no_api_key(self):
        client = Mock()
        url = "https://scholar.google.com/citations?user=2c0ZBk8AAAAJ"
        with patch.dict("os.environ", {"SERPAPI_API_KEY": ""}):
            scholar_get(client, url)
        client.get.assert_called_once_with(url)

    def test_only_first_position_counts(self):
        self.assertTrue(is_first_author(["C. Zhu", "Xin Wang"], PROFILE["author_aliases"]))
        self.assertFalse(is_first_author(["Chenghong Zhu", "Chengkai Zhu"], PROFILE["author_aliases"]))
        self.assertFalse(is_first_author(["Hao-Kai Zhang", "Chengkai Zhu"], PROFILE["author_aliases"]))

    def test_arxiv_requires_full_name_and_preserves_order(self):
        records, total = parse_arxiv(ARXIV, "Chengkai Zhu")
        self.assertEqual(total, 2)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["authors"], ["Chengkai Zhu", "Xin Wang"])
        self.assertEqual(records[0]["pdf_url"], "https://arxiv.org/pdf/2609.12345")
        self.assertEqual(parse_arxiv(ARXIV.replace("Chengkai Zhu", "C. Zhu"), "Chengkai Zhu")[0], [])

    def test_arxiv_errors_are_failures(self):
        with self.assertRaises(SourceError):
            parse_arxiv("<html>Blocked</html>", "Chengkai Zhu")
        with self.assertRaises(SourceError):
            parse_arxiv('<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/api/errors#bad_query</id></entry></feed>', "Chengkai Zhu")

    def test_version_and_changed_title_do_not_duplicate(self):
        records = merge_publications([paper()], [paper(title="A revised title", abstract_url="https://arxiv.org/abs/2609.12345v3")])
        self.assertEqual(len(records), 1)
        self.assertEqual(arxiv_id(records[0]["abstract_url"]), "2609.12345")

    def test_journal_does_not_regress_to_preprint(self):
        published = paper(kind="published", venue="Example Journal (2026)")
        self.assertEqual(merge_publications([published], [paper()])[0]["venue"], published["venue"])
        self.assertEqual(merge_publications([paper()], [published])[0]["kind"], "published")

    def test_previous_papers_are_not_lost(self):
        old = paper(title="An older work", abstract_url="https://arxiv.org/abs/2401.12345", date="2024-01-01")
        self.assertEqual(len(merge_publications([old], [paper()])), 2)

    def test_exclusions_survive_title_and_arxiv_version_changes(self):
        exclusions = [{"title": "Amortized Stabilizer Rényi Entropy", "arxiv_id": "2409.06659"}]
        by_title = paper(title="AMORTIZED STABILIZER RENYI ENTROPY")
        by_identifier = paper(title="A renamed journal version", abstract_url="https://arxiv.org/abs/2409.06659v3")
        kept = paper(title="A different paper")
        self.assertEqual(filter_publications([by_title, by_identifier, kept], exclusions), [kept])

    def test_monthly_sync_cannot_restore_excluded_records(self):
        removed = paper(title="An omitted paper")
        kept = paper(title="Another paper", abstract_url="https://arxiv.org/abs/2609.54321", pdf_url="https://arxiv.org/pdf/2609.54321")
        exclusions = [{"title": removed["title"], "arxiv_id": "2609.12345"}]
        detail = {"title": "A renamed version", "authors": removed["authors"], "links": [removed["abstract_url"]]}
        with patch("sync_publications.fetch_arxiv", return_value=[removed, kept]), patch("sync_publications.fetch_scholar", return_value=[detail]):
            records, status = sync(None, PROFILE, [removed], [], exclusions)
        self.assertEqual(records, [kept])
        self.assertEqual(status["synced_first_author_papers"], 1)
        self.assertEqual(status["pending"], [])

    def test_scholar_detects_blocked_or_wrong_profile(self):
        for document in ("<html>captcha</html>", '<div id="gsc_prf_in">Someone else</div>'):
            with self.assertRaises(SourceError):
                parse_scholar_profile(document, "Chengkai Zhu")

    def test_scholar_pagination(self):
        document = '<div id="gsc_prf_in">Chengkai Zhu</div><tr class="gsc_a_tr"><td><a class="gsc_a_at" href="/citations?view_op=view_citation">Test</a><div class="gs_gray">C Zhu, X Wang</div></td><td class="gsc_a_y">2026</td></tr><button id="gsc_bpf_more">More</button>'
        rows, more = parse_scholar_profile(document, "Chengkai Zhu")
        self.assertEqual(rows[0]["first_author"], "C Zhu")
        self.assertTrue(more)
        self.assertFalse(parse_scholar_profile(document.replace('id="gsc_bpf_more"', 'id="gsc_bpf_more" disabled'), "Chengkai Zhu")[1])

    def test_full_scholar_author_order(self):
        document = '<a id="gsc_oci_title" href="https://arxiv.org/abs/2609.12345">Test</a><div class="gs_scl"><div class="gsc_oci_field">Authors</div><div class="gsc_oci_value">Chengkai Zhu, Xin Wang</div></div>'
        detail = parse_scholar_detail(document)
        self.assertEqual(detail["authors"], ["Chengkai Zhu", "Xin Wang"])
        self.assertEqual(detail["links"], ["https://arxiv.org/abs/2609.12345"])
        with self.assertRaises(SourceError):
            parse_scholar_detail(document.replace("Xin Wang", "..."))

    def test_unknown_pdf_is_not_invented(self):
        detail = {"title": "A new journal paper", "authors": PROFILE["author_aliases"][:1], "publication_date": "2026/09/01", "year": "2026", "venue": "Example Journal", "links": ["https://doi.org/10.1234/example"]}
        with self.assertRaises(ValueError):
            scholar_publication(detail, [])
        detail["links"] = ["https://arxiv.org/abs/2609.12345v2"]
        self.assertEqual(scholar_publication(detail, [])["pdf_url"], "https://arxiv.org/pdf/2609.12345")

    def test_fallback_keeps_existing_records(self):
        with patch("sync_publications.fetch_arxiv", return_value=[paper()]), patch("sync_publications.fetch_scholar", side_effect=SourceError("Blocked")):
            records, status = sync(None, PROFILE, [paper(title="Older", abstract_url="https://arxiv.org/abs/2401.12345")], [])
        self.assertEqual(len(records), 2)
        self.assertEqual(status["sources"]["google_scholar"]["state"], "failed")

    def test_complete_failure_cannot_replace_data(self):
        existing = [paper()]
        with patch("sync_publications.fetch_arxiv", side_effect=SourceError("Offline")), patch("sync_publications.fetch_scholar", side_effect=SourceError("Blocked")):
            with self.assertRaises(SourceError):
                sync(None, PROFILE, existing, [])
        self.assertEqual(existing, [paper()])

    def test_scholar_works_when_arxiv_is_down(self):
        detail = {"title": paper()["title"], "authors": paper()["authors"], "publication_date": "2026/09/01", "year": "2026", "venue": "Example Journal", "links": [paper()["abstract_url"]]}
        with patch("sync_publications.fetch_arxiv", side_effect=SourceError("Offline")), patch("sync_publications.fetch_scholar", return_value=[detail]):
            records, status = sync(None, PROFILE, [], [])
        self.assertEqual(len(records), 1)
        self.assertEqual(status["sources"]["google_scholar"]["state"], "success")

    def test_incomplete_links_are_reported(self):
        detail = {"title": "New paper", "authors": paper()["authors"], "publication_date": "2026", "year": "2026", "venue": "Example Journal", "links": []}
        with patch("sync_publications.fetch_arxiv", return_value=[]), patch("sync_publications.fetch_scholar", return_value=[detail]):
            records, status = sync(None, PROFILE, [paper()], [])
        self.assertEqual(records, [paper()])
        self.assertEqual(status["pending"][0]["title"], "New paper")

    def test_external_metadata_is_escaped(self):
        output = publication_list([paper(title='<script>alert("x")</script>')], PROFILE)
        self.assertNotIn("<script>", output)
        self.assertIn("&lt;script&gt;", output)
        with self.assertRaises(ValueError):
            validate_publication(paper(pdf_url="javascript:alert(1)"))

    def test_complete_build_has_no_broken_internal_links(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build(output)
            check_site(output)
            self.assertIn("Scientist", (output / "index.html").read_text())
            self.assertIn("QudeLeap", (output / "index.html").read_text())


if __name__ == "__main__":
    unittest.main()
