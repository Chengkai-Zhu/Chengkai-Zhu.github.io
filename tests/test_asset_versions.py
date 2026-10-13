"""Prevent newly deployed pages from reusing cached appearance assets."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build as site_build
from check_site import Document


def asset_link(output, filename, page="index.html"):
    links = Document((output / page).read_text()).links
    return next(link for link in links if urlsplit(link).path == "/assets/" + filename)


class AssetVersionTests(unittest.TestCase):
    def test_style_change_invalidates_cache_across_every_page(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            for folder in ("assets", "templates", "data"):
                shutil.copytree(site_build.ROOT / folder, source / folder)
            shutil.copyfile(site_build.ROOT / "CNAME", source / "CNAME")
            first, second = base / "first", base / "second"
            with patch.object(site_build, "ROOT", source):
                site_build.build(first)
                style = source / "assets/style.css"
                style.write_text(style.read_text() + "\n/* A new deployment. */\n")
                site_build.build(second)

            new_style = asset_link(second, "style.css")
            self.assertTrue(parse_qs(urlsplit(new_style).query).get("v"))
            self.assertNotEqual(asset_link(first, "style.css"), new_style)
            for page in ("research/index.html", "talks/index.html", "teaching/index.html", "404.html"):
                self.assertEqual(asset_link(second, "style.css", page), new_style)
            for filename in ("appearance.js", "visitor-globe.html"):
                self.assertEqual(asset_link(first, filename), asset_link(second, filename))
                self.assertTrue(parse_qs(urlsplit(asset_link(second, filename)).query).get("v"))
