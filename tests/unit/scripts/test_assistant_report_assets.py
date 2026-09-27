"""Readable source assets remain inline, offline and identified in report audits."""

import csv
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import pytest

from scripts.dev import assistant_pilot_presentation as presentation
from scripts.dev import assistant_pilot_report as report
from tests.unit.scripts.test_assistant_pilot_report import _change_result, _run


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


def test_experiment_labels_escape_text_keep_filter_keys_and_omit_dev_repeat():
    key = 'model"<script>__candidate-2__DEV__repeat-0'
    condition = {
        "identity": {
            "condition": 'model"<script>-rag-on',
            "candidate_index": 2,
            "split": "DEV",
            "repeat": 0,
        },
        "macro": {"first": None, "final": None},
        "decision_latency_seconds": {"overall": {}},
    }
    page = presentation.render_overview({"conditions": {key: condition}})
    controls = presentation._case_filters({key: condition, "legacy-rag-off": {}})
    assert "model&quot;&lt;script&gt; · candidate 2" in page
    assert "repeat" not in page and "__candidate-" not in page
    assert "<script>" not in page + controls
    assert ">legacy-rag-off</option>" in controls

    class Options(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "option":
                self.keys.append(dict(attrs).get("value"))

    parsed = Options()
    parsed.keys = []
    parsed.feed(controls)
    assert key in parsed.keys
    assert ">model&quot;&lt;script&gt; · candidate 2</option>" in controls


def test_entry_and_report_present_only_identity_and_result_tables(tmp_path):
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
        assert "Technical details" not in page
        assert "Earlier attempts" not in page
        assert "Download CSV" not in page
        assert 'href="results.csv"' not in page
        assert "Evaluation complete" not in page
        assert 'id="evidence"' not in page
    assert "View D0 report" not in root_page
    assert 'id="case-index"' in root_page
    assert "1 question · " in root_page
    assert 'class="report-nav"' not in root_page
    assert 'class="metric"' not in root_page
    assert "First-answer accuracy" in root_page
    assert "Accuracy after format repair" in root_page
    assert root_page.index('id="overview"') < root_page.index('id="cases"')
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
    assert links.targets
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
    markdown = saved_report.with_name("README.md").read_text(encoding="utf-8")
    assert "Condition scores" in markdown and "Latency denominator" in markdown
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


@pytest.mark.parametrize("unclassified_id", ["unrecognized-case", "DEV-C02-01-V0"])
def test_group_tables_keep_final_denominators_and_unclassified_cases(
    tmp_path, unclassified_id
):
    root = _run(
        tmp_path,
        [
            ("Action", False, True, "completed"),
            ("Action", False, False, "completed"),
            ("Action", None, None, "missing"),
            ("Clarification", True, True, "completed"),
            ("No-call", False, False, "completed"),
            ("Action", None, None, "invalid_measurement"),
        ],
        dev=True,
        all_models=True,
        case_ids=[
            "DEV-A08-01-V0",
            "DEV-A08-01-V1",
            "DEV-A08-02-V0",
            "DEV-C01-01-V0",
            "DEV-N02-01-V0",
            unclassified_id,
        ],
    )
    _change_result(
        root, lambda result: result["scores"].update(final_decision_correct=False)
    )
    baseline = report.build_report(root)
    output = tmp_path / "report"
    assert report.write_report(root, output) == baseline

    class GroupTables(HTMLParser):
        def __init__(self):
            super().__init__()
            self.section = None
            self.tables = {}
            self.row = None
            self.cell = None

        def handle_starttag(self, tag, attrs):
            if tag == "section":
                self.section = dict(attrs).get("id")
            if tag == "tr" and self.section in {"category-accuracy", "group-accuracy"}:
                self.row = []
            if tag in {"th", "td"} and self.row is not None:
                self.cell = ""

        def handle_data(self, data):
            if self.cell is not None:
                self.cell += data

        def handle_endtag(self, tag):
            if tag in {"th", "td"} and self.cell is not None:
                self.row.append(self.cell)
                self.cell = None
            if tag == "tr" and self.row is not None:
                self.tables.setdefault(self.section, []).append(self.row)
                self.row = None
            if tag == "section":
                self.section = None

    parsed = GroupTables()
    parsed.feed((output / "index.html").read_text(encoding="utf-8"))
    assert set(parsed.tables) == {"category-accuracy", "group-accuracy"}
    for table in parsed.tables.values():
        assert table[0][1:] == list(baseline["conditions"])
    categories = {row[0]: row[1:] for row in parsed.tables["category-accuracy"][1:]}
    assert (
        categories["Action"]
        == ["0 / 2 (0.0%); 2 unavailable"] + ["1 / 2 (50.0%); 2 unavailable"] * 4
    )
    assert categories["Clarification"] == ["1 / 1 (100.0%)"] * 5
    assert categories["No-call"] == ["0 / 1 (0.0%)"] * 5
    groups = {row[0]: row[1:] for row in parsed.tables["group-accuracy"][1:]}
    assert groups == {
        "A08 / Action": ["0 / 2 (0.0%); 1 unavailable"]
        + ["1 / 2 (50.0%); 1 unavailable"] * 4,
        "C01 / Clarification": ["1 / 1 (100.0%)"] * 5,
        "N02 / No-call": ["0 / 1 (0.0%)"] * 5,
        "Unclassified": ["0 / 0 (n/a); 1 unavailable"] * 5,
    }


def test_group_labels_use_only_consistent_action_oracle_tools(tmp_path):
    root = _run(
        tmp_path,
        [
            ("Action", True, True, "completed"),
            ("Action", True, True, "completed"),
            ("Clarification", True, True, "completed"),
            ("No-call", True, True, "completed"),
        ],
        dev=True,
        case_ids=[
            "DEV-A08-01-V0",
            "DEV-A08-01-V1",
            "DEV-C01-01-V0",
            "DEV-N01-01-V0",
        ],
    )
    saved = report.build_report(root)
    details = {row["id"]: presentation._details(root, row) for row in saved["cases"]}
    for detail in details.values():
        detail["request"]["case"]["expected_tool"] = "apply_bandpass_filter"
    page = presentation._render_accuracy_breakdowns(saved, details)
    assert "A08 / Action — apply bandpass filter" in page
    assert "C01 / Clarification —" not in page and "N01 / No-call —" not in page
    details[saved["cases"][0]["id"]]["request"]["case"]["expected_tool"] = (
        "resample_data"
    )
    conflict = presentation._render_accuracy_breakdowns(saved, details)
    assert "A08 / Action — metadata mismatch" in conflict
    assert "A08 / Action — apply bandpass filter" not in conflict
