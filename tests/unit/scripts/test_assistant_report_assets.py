"""Readable source assets remain inline, offline and identified in report audits."""

import hashlib
import json
from html.parser import HTMLParser

from scripts.dev import assistant_pilot_presentation as presentation
from scripts.dev import assistant_pilot_report as report
from tests.unit.scripts.test_assistant_pilot_report import _run


class _InlineAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = None
        self.contents = {"style": [], "script": []}
        self.external = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in self.contents:
            self.active = tag
        if (tag == "script" and "src" in attributes) or (
            tag == "link" and attributes.get("rel") == "stylesheet"
        ):
            self.external.append(attributes)

    def handle_data(self, data):
        if self.active:
            self.contents[self.active].append(data)

    def handle_endtag(self, tag):
        if tag == self.active:
            self.active = None


def test_inline_assets_match_loaded_bytes_and_audit_hashes(tmp_path):
    root = _run(tmp_path, [("Action", True, True, "completed")], dev=True)
    output = tmp_path / "report"
    report.write_report(root, output)
    page = _InlineAssets()
    page.feed((output / "index.html").read_text(encoding="utf-8"))
    audit = json.loads((output / "presentation-audit.json").read_text(encoding="utf-8"))

    assert page.external == []
    for tag, filename in (("style", "report.css"), ("script", "cases.js")):
        loaded = presentation._ASSET_BYTES[filename]
        assert loaded == (presentation._ASSET_DIRECTORY / filename).read_bytes()
        assert "".join(page.contents[tag]) == loaded.decode("utf-8")
        assert (
            audit["presentation_assets_sha256"][filename]
            == hashlib.sha256(loaded).hexdigest()
        )


def test_shared_page_uses_inline_css_without_requiring_external_assets():
    page = _InlineAssets()
    page.feed(presentation.render_page("Copied report", "<h1>Case evidence</h1>"))
    assert page.external == []
    assert "".join(page.contents["style"]) == presentation._ASSET_BYTES[
        "report.css"
    ].decode("utf-8")
    assert page.contents["script"] == []
