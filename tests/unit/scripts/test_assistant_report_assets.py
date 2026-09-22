"""Readable source assets remain inline, offline and identified in report audits."""

import csv
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

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


def test_entry_and_report_name_the_experiment_and_fold_technical_details(tmp_path):
    from scripts.dev import run_assistant_dev as entry

    raw = _run(tmp_path, [("Action", True, True, "completed")], dev=True)
    run = tmp_path / "d0"
    run.mkdir()
    raw = raw.rename(run / "raw")
    manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    assert entry.run_attempt(manifest, {}, run, resume=False, report_only=True) == 0
    root_page = (run / "index.html").read_text(encoding="utf-8")
    report_page = next((run / "reports").glob("*/index.html")).read_text(
        encoding="utf-8"
    )
    for page in (root_page, report_page):
        assert "D0 | DEV initial baseline" in page
        assert "1 model" in page and "RAG on" in page
        assert "latest report" not in page.lower()
        assert "<summary>Technical details</summary>" in page
    assert "View D0 report" not in root_page
    assert 'id="case-index"' in root_page
    assert "1 question · " in root_page
    assert 'class="report-nav"' not in root_page
    assert 'class="metric"' not in root_page
    assert "First-answer accuracy" in root_page
    assert "Accuracy after format repair" in root_page
    assert root_page.index('id="overview"') < root_page.index('id="cases"')
    assert root_page.index('id="cases"') < root_page.index('id="evidence"')
    assert "Evaluation complete" in root_page
    assert "Selected results complete" not in root_page

    # The stable entry presents all content, but links resolve in the report's
    # versioned directory. Verify actual targets, not just the base-tag spelling.
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.base = (run / "index.html").as_uri()
            self.targets = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "base":
                self.base = urljoin(self.base, attrs["href"])
            elif tag == "a":
                self.targets.append(urljoin(self.base, attrs["href"]))

    links = Links()
    links.feed(root_page)
    for target in links.targets:
        path = unquote(urlsplit(target).path)
        if len(path) > 2 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        assert Path(path).is_file(), target
        fragment = unquote(urlsplit(target).fragment)
        if fragment:
            assert f'id="{fragment}"' in Path(path).read_text(encoding="utf-8")
    assert manifest["source"]["head"] not in root_page
    assert manifest["source"]["head"] not in report_page
    saved_report = next((run / "reports").glob("*/report.json"))
    recorded = json.loads(saved_report.read_text(encoding="utf-8"))["cases"][0]
    with saved_report.with_name("results.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        exported = next(csv.DictReader(stream))
    case_page = next((saved_report.parent / "cases").glob("*.html")).read_text(
        encoding="utf-8"
    )
    for field in ("request_sha256", "result_sha256"):
        assert exported[field] == recorded[field]
        assert recorded[field] not in case_page


def test_evidence_notice_distinguishes_current_issues_from_retained_history():
    historical = presentation.render_evidence_notice({"superseded:old": ["missing"]})
    assert historical == ""
    selected = presentation.render_evidence_notice({"current": ["missing"]})
    assert "1 selected result" in selected
    assert "excluded" not in selected
    assert presentation.render_evidence_notice({}) == ""
