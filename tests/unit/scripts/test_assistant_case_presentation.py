"""Case-page reading order and evidence boundaries, without inference or rescoring."""

import copy

from scripts.dev.assistant_pilot_presentation import _case_page


def _render(tmp_path, *, missing=False, issue=False):
    output = tmp_path / "report"
    (output / "cases").mkdir(parents=True)
    row = {
        "id": "phi4-rag-on__DEV-A01",
        "case_id": "DEV-A01",
        "condition": "phi4-rag-on",
        "decision": "Action",
        "evidence_status": "missing" if missing else "verified",
        "decision_valid": not missing,
        "first": False,
        "final": None if missing else True,
    }
    detail = {
        "request": {
            "case": {
                "input": "Open <script>alert('request')</script>",
                "expected_workflow_stage": "empty",
                "expected_tool": "import_eeg_data",
                "expected_parameters": {},
            }
        },
        "result": {
            "scores": {
                "attempt_decisions": [
                    {
                        "observed_stage": "empty",
                        "observed_tool": "import_eeg_data",
                        "reason": "matched",
                        "correct": True,
                    }
                ]
            },
            "product_outcome": {
                "measurement_valid": False,
                "outcome": "invalid_measurement",
            },
            "trace": {
                "generations": [{"raw_response": "untrusted output", "request": {}}]
            },
        },
        "captures": []
        if issue
        else [
            {
                "prompt": "prompt <script>bad()</script>",
                "raw-output": "raw <script>bad()</script>",
                "path": tmp_path / "capture",
            }
        ],
        "issues": ["Capture hash mismatch"] if issue else [],
    }
    if missing:
        detail = {
            "request": {},
            "result": {},
            "captures": [],
            "issues": ["Missing evidence"],
        }
    before = copy.deepcopy((row, detail))
    _case_page(tmp_path, output, row, detail)
    assert (row, detail) == before
    return (output / "cases" / f"{row['id']}.html").read_text(encoding="utf-8")


def test_case_page_compares_recorded_decision_without_claiming_execution(tmp_path):
    page = _render(tmp_path)
    assert page.index("Actual user request") < page.index("Expected decision")
    assert "Recorded final decision" in page
    assert "import_eeg_data" in page and "matched" in page
    assert "First decision: Incorrect" in page
    assert "Final decision: Correct" in page
    assert "Product outcome — separate evidence" in page
    assert "invalid_measurement" in page
    assert "does not establish execution success" in page
    assert "Final rendered prompt — hash verified" in page
    assert "&lt;script&gt;" in page
    assert "<script>" not in page


def test_missing_case_evidence_is_not_rendered_as_success(tmp_path):
    page = _render(tmp_path, missing=True)
    assert "Final decision: Unavailable" in page
    assert "no result inferred" in page
    assert "Expected decision" not in page


def test_failed_capture_is_visible_and_untrusted_output_is_not_promoted(tmp_path):
    page = _render(tmp_path, issue=True)
    assert "Capture integrity: FAILED" in page
    assert "Capture hash mismatch" in page
    assert "capture integrity unavailable" in page
    assert "Raw model output — hash verified" not in page
