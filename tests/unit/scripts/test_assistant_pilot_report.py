"""Research reports preserve denominators and never turn missing evidence into scores."""

import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from scripts.dev import assistant_pilot_report as report
from scripts.dev.assistant_pilot_presentation import _link
from scripts.dev.run_assistant_pilot import CONDITIONS, SCHEMA


def _write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(tmp_path, observations):
    root = tmp_path / "run"
    root.mkdir()
    (root / "cases").mkdir()
    jobs, journal = [], []
    for index, observation in enumerate(observations):
        category, first, final, status = observation
        case_id, condition = f"DEV-{index}", "phi4-rag-off"
        job = {
            "id": f"{condition}__{case_id}",
            "case_id": case_id,
            "condition": condition,
            "decision": category,
            "phase": 1,
        }
        jobs.append(job)
        if status == "missing":
            continue
        case = {"case_id": case_id, "split": "DEV", "decision": category}
        request = {
            "case": case,
            "model_id": CONDITIONS[condition][0],
            "rag_enabled": False,
            "seed": 0,
            "repeat": 0,
        }
        request_sha = _write(root / "cases" / f"{job['id']}.request.json", request)
        journal.append(
            {
                "event": "case_start",
                "session": "s",
                "elapsed_seconds": index + 1,
                "id": job["id"],
                "request_sha256": request_sha,
                "timeout_seconds": 450,
            }
        )
        if status == "unresolved":
            continue
        destination = root / "cases" / job["id"]
        destination.mkdir()
        result = {
            "schema": "xbrainlab.assistant_pilot_case.v1",
            "case": case,
            "case_id": case_id,
            "model_id": request["model_id"],
            "rag_enabled": False,
            "status": "recorded",
            "cleanup_ok": True,
            "decision_timed_out": status == "decision_timeout",
            "input_audit": {"issues": []},
            "capture_audit": {"issues": []},
            "product_outcome": {
                "measurement_valid": True,
                "outcome": "completed",
                "execution": "completed",
                "ui_handoff": "not_requested",
                "issues": [],
            },
            "scores": {
                "measurement_valid": status != "invalid_measurement",
                "first_decision_correct": first,
                "final_decision_correct": final,
                "execution_status": status,
                "attempt_decisions": [],
            },
            "decision_seconds": 10 + index,
            "model_load_seconds": 2,
            "warmup": {"seconds": 3},
            "cleanup_seconds": 1,
            "fixture_seconds": 1,
            "case_operation_seconds": 1,
            "case_turn_seconds": 12 + index,
            "total_seconds": 20 + index,
        }
        digest = _write(destination / "result.json", result)
        journal.append(
            {
                "event": "case_end",
                "session": "s",
                "elapsed_seconds": index + 2,
                "id": job["id"],
                "status": "recorded",
                "result_sha256": digest,
                "cleanup_certified": True,
                "returncode": 0,
            }
        )
    journal.append(
        {
            "event": "session_end",
            "session": "s",
            "elapsed_seconds": 100,
            "cleanup_certified": True,
        }
    )
    _write(
        root / "manifest.json",
        {
            "schema": SCHEMA,
            "source": {"head": "a" * 40, "dirty": []},
            "environment": {},
            "jobs": jobs,
            "budget_seconds": 14400,
        },
    )
    (root / "journal.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in journal), encoding="utf-8"
    )
    return root


def test_macro_equal_weights_categories_and_first_final_are_separate(tmp_path):
    root = _run(
        tmp_path,
        [
            ("Action", True, True, "completed"),
            ("Action", False, True, "completed"),
            ("Action", False, False, "completed"),
            ("Clarification", True, True, "completed"),
            ("No-call", False, False, "completed"),
        ],
    )
    actual = report.build_report(root)
    condition = actual["conditions"]["phi4-rag-off"]
    assert condition["categories"]["Action"]["final"] == {
        "numerator": 2,
        "denominator": 3,
        "rate": 2 / 3,
    }
    assert condition["macro"]["first"] == pytest.approx((1 / 3 + 1 + 0) / 3)
    assert condition["macro"]["final"] == pytest.approx((2 / 3 + 1 + 0) / 3)
    assert condition["decision_latency_seconds"]["success"]["n"] == 3
    assert condition["decision_latency_seconds"]["failure"] == {
        "n": 2,
        "p50": 13,
        "max": 14,
    }
    assert actual["pilot_complete"] is False and actual["ranking_allowed"] is False
    assert actual["active_budget"]["charged_seconds"] == 100


def test_timeout_stays_wrong_in_denominator_but_not_completed_latency(tmp_path):
    root = _run(
        tmp_path,
        [
            ("Action", False, False, "decision_timeout"),
            ("Clarification", None, None, "invalid_measurement"),
            ("No-call", None, None, "missing"),
        ],
    )
    condition = report.build_report(root)["conditions"]["phi4-rag-off"]
    assert condition["categories"]["Action"]["final"]["denominator"] == 1
    assert condition["counts"]["decision_timeout"] == 1
    assert condition["counts"]["invalid_measurement"] == 1
    assert condition["counts"]["missing"] == 1
    assert condition["decision_latency_seconds"]["failure"]["n"] == 0
    assert condition["macro"]["final"] is None


def test_batched_runtime_load_and_warmup_are_counted_once_per_condition(tmp_path):
    root = _run(
        tmp_path,
        [
            ("Action", True, True, "completed"),
            ("Clarification", True, True, "completed"),
        ],
    )
    evidence = {
        "model_load_seconds": 7.5,
        "warmup": {"seconds": 1.25, "output": "READY"},
        "rag_warmup": None,
        "runtime": {"model_id": CONDITIONS["phi4-rag-off"][0]},
    }
    records = [
        json.loads(line) for line in (root / "journal.jsonl").read_text().splitlines()
    ]
    for index in range(2):
        case_id = f"phi4-rag-off__DEV-{index}"
        path = root / "cases" / case_id / "result.json"
        result = json.loads(path.read_text())
        result["condition_evidence"] = evidence
        digest = _write(path, result)
        next(
            row
            for row in records
            if row["event"] == "case_end" and row["id"] == case_id
        )["result_sha256"] = digest
    (root / "journal.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in records), encoding="utf-8"
    )

    overhead = report.build_report(root)["conditions"]["phi4-rag-off"][
        "overhead_seconds"
    ]
    assert overhead["model_load"] == {"n": 1, "p50": 7.5, "max": 7.5, "total": 7.5}
    assert overhead["warmup"] == {
        "n": 1,
        "p50": 1.25,
        "max": 1.25,
        "total": 1.25,
    }


@pytest.mark.parametrize("artifact", ["request", "result"])
def test_changed_artifact_is_invalid_not_model_wrong(tmp_path, artifact):
    root = _run(tmp_path, [("Action", True, True, "completed")])
    stem = "phi4-rag-off__DEV-0"
    path = (
        root
        / "cases"
        / (f"{stem}.request.json" if artifact == "request" else f"{stem}/result.json")
    )
    path.write_text("{}", encoding="utf-8")
    condition = report.build_report(root)["conditions"]["phi4-rag-off"]
    assert condition["counts"]["invalid_evidence"] == 1
    assert condition["categories"]["Action"]["final"]["denominator"] == 0


def test_unresolved_case_preserves_budget_reservation(tmp_path):
    root = _run(tmp_path, [("Action", None, None, "unresolved")])
    actual = report.build_report(root)
    assert actual["conditions"]["phi4-rag-off"]["counts"]["unresolved"] == 1
    assert actual["active_budget"]["charged_seconds"] == 451


def test_new_output_only_and_source_identity_retained(tmp_path):
    root = _run(tmp_path, [("Action", True, True, "completed")])
    output = tmp_path / "report"
    report.write_report(root, output)
    actual = json.loads((output / "report.json").read_text())
    assert actual["frozen_source"]["head"] == "a" * 40
    assert (output / "README.md").is_file()
    with pytest.raises(FileExistsError):
        report.write_report(root, output)


def _presentation_run(tmp_path):
    root = _run(tmp_path, [("Action", False, False, "completed")])
    stem = "phi4-rag-off__DEV-0"
    request_path = root / "cases" / f"{stem}.request.json"
    request = json.loads(request_path.read_text())
    request["case"].update(
        input='=HYPERLINK("bad") <script>alert(1)</script>',
        expected_tool="apply_bandpass_filter",
    )
    request_sha = _write(request_path, request)
    capture = root / "conditions" / "phi4-rag-off" / "prompts" / "session-1" / "2"
    capture.mkdir(parents=True)
    prompt, raw = "rendered <script> prompt", "```json\n{}\n```"
    (capture / "prompt.txt").write_bytes(prompt.encode())
    (capture / "raw-output.txt").write_bytes(raw.encode())
    metadata = {
        "session_id": "session-1",
        "sequence": 2,
        "status": "completed",
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "raw_output_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }
    _write(capture / "metadata.json", metadata)

    def mutate(result):
        result["case"] = request["case"]
        result["condition_evidence"] = {
            "model_load_seconds": 2,
            "warmup": {"seconds": 3},
            "runtime": {"model_id": result["model_id"]},
        }
        result["trace"] = {
            "generations": [
                {
                    "generation_id": 1,
                    "request": {
                        "messages": [[["role", "user"], ["content", "actual message"]]]
                    },
                    "raw_response": raw,
                    "terminal": "completed",
                }
            ],
            "events": [],
        }
        result["scores"]["attempt_decisions"] = [
            {"correct": False, "reason": "invalid_envelope"}
        ]
        result["scores"]["repair_count"] = 0
        result["capture_audit"]["captures"] = [
            {"path": "Z:/untrusted/not-used", "metadata": metadata}
        ]

    _change_result(root, mutate)
    journal_path = root / "journal.jsonl"
    records = [json.loads(line) for line in journal_path.read_text().splitlines()]
    records[0]["request_sha256"] = request_sha
    journal_path.write_text("".join(json.dumps(row) + "\n" for row in records))
    return root, capture


def test_readable_report_preserves_scores_and_exposes_verified_inputs(tmp_path):
    root, _ = _presentation_run(tmp_path)
    baseline = report.build_report(root)
    output = tmp_path / "readable"
    report.write_report(root, output)
    assert json.loads((output / "report.json").read_text()) == baseline
    assert (output / "index.html").is_file()
    page = (output / "cases" / "phi4-rag-off__DEV-0.html").read_text(encoding="utf-8")
    assert "&lt;script&gt;" in page and "<script>alert" not in page
    assert "actual message" in page and "rendered &lt;script&gt; prompt" in page
    assert "Oracle" in page and "apply_bandpass_filter" in page
    assert "invalid_envelope" in page and "```json" in page
    assert "Z:/untrusted" not in page
    assert (output / "results.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    with (output / "results.csv").open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 1 and rows[0]["request"].startswith("'=HYPERLINK")
    assert rows[0]["final_correct"] == "False"
    assert rows[0]["capture_integrity"] == "verified"
    markdown = (output / "README.md").read_text(encoding="utf-8")
    assert "0 / 1" in markdown and "model_load" in markdown
    assert "invalid_envelope" in markdown and "p50" in markdown


def test_relocated_raw_evidence_uses_relative_links(tmp_path):
    root, _ = _presentation_run(tmp_path)
    relocated = tmp_path / "archive" / "raw"
    shutil.copytree(root, relocated)
    output = relocated.parent / "report"
    report.write_report(relocated, output)
    page = (output / "cases" / "phi4-rag-off__DEV-0.html").read_text(encoding="utf-8")
    assert "../../raw/conditions/phi4-rag-off/prompts/session-1/2/prompt.txt" in page


@pytest.mark.skipif(sys.platform != "win32", reason="Windows drive-root behavior")
def test_cross_drive_evidence_links_remain_openable():
    link = _link(
        Path("D:/raw evidence/prompt.txt"), Path("E:/report/case.html"), "Prompt"
    )
    assert link == '<a href="file:///D:/raw%20evidence/prompt.txt">Prompt</a>'


@pytest.mark.parametrize("damage", ["prompt", "metadata", "traversal", "symlink"])
def test_untrusted_captures_are_flagged_and_not_rendered(tmp_path, damage):
    root, capture = _presentation_run(tmp_path)
    if damage == "prompt":
        (capture / "prompt.txt").write_text("TAMPERED-CONTENT")
    elif damage == "metadata":
        _write(capture / "metadata.json", {"forged": True})
    elif damage == "traversal":
        _change_result(
            root,
            lambda result: result["capture_audit"]["captures"][0]["metadata"].update(
                session_id="../../outside"
            ),
        )
    else:
        outside = tmp_path / "outside.txt"
        outside.write_text("TAMPERED-CONTENT")
        (capture / "prompt.txt").unlink()
        try:
            (capture / "prompt.txt").symlink_to(outside)
        except OSError:
            pytest.skip("Creating symlinks is unavailable on this host")
    output = tmp_path / "report"
    report.write_report(root, output)
    page = (output / "cases" / "phi4-rag-off__DEV-0.html").read_text(encoding="utf-8")
    assert "Capture integrity: FAILED" in page
    assert "TAMPERED-CONTENT" not in page
    assert "Evidence presentation incomplete" in (output / "index.html").read_text(
        encoding="utf-8"
    )


def test_missing_case_has_page_without_invented_model_result(tmp_path):
    root = _run(tmp_path, [("Action", None, None, "missing")])
    output = tmp_path / "report"
    report.write_report(root, output)
    page = (output / "cases" / "phi4-rag-off__DEV-0.html").read_text(encoding="utf-8")
    assert "missing" in page and "unavailable" in page


@pytest.mark.parametrize(
    "capture_status, expected", [("completed", "FAILED"), ("cancelled", "verified")]
)
def test_cancelled_prefix_requires_cancelled_capture_too(
    tmp_path, capture_status, expected
):
    root, capture = _presentation_run(tmp_path)
    metadata_path = capture / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["status"] = capture_status
    _write(metadata_path, metadata)

    def mutate(result):
        result["capture_audit"]["captures"][0]["metadata"] = metadata
        generation = result["trace"]["generations"][0]
        generation.update(terminal="cancelled", raw_response="```")

    _change_result(root, mutate)
    output = tmp_path / "report"
    report.write_report(root, output)
    page = (output / "cases" / "phi4-rag-off__DEV-0.html").read_text(encoding="utf-8")
    assert f"Capture integrity: {expected}" in page


def test_unknown_or_duplicate_job_identity_refuses_report(tmp_path):
    root = _run(tmp_path, [("Action", True, True, "completed")])
    path = root / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["jobs"].append(manifest["jobs"][0])
    _write(path, manifest)
    with pytest.raises(ValueError, match="manifest"):
        report.build_report(root)


def _change_result(root, mutate):
    path = root / "cases" / "phi4-rag-off__DEV-0" / "result.json"
    result = json.loads(path.read_text())
    mutate(result)
    digest = _write(path, result)
    path = root / "journal.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    for row in records:
        if row["event"] == "case_end":
            row["result_sha256"] = digest
    path.write_text("".join(json.dumps(row) + "\n" for row in records))


@pytest.mark.parametrize(
    "audit,missing",
    [
        ("input_audit", True),
        ("input_audit", False),
        ("capture_audit", True),
        ("capture_audit", False),
    ],
)
def test_missing_or_failed_provenance_is_excluded_from_decision_denominator(
    tmp_path, audit, missing
):
    root = _run(tmp_path, [("Action", True, True, "completed")])

    def mutate(result):
        if missing:
            result.pop(audit)
        else:
            result[audit]["issues"].append("mismatch")

    _change_result(root, mutate)
    actual = report.build_report(root)
    condition = actual["conditions"]["phi4-rag-off"]
    assert condition["counts"]["invalid_measurement"] == 1
    assert condition["categories"]["Action"]["final"]["denominator"] == 0
    assert actual["complete_selected_schedule"] is False


def test_product_failure_does_not_erase_a_verified_model_decision(tmp_path):
    root = _run(tmp_path, [("Action", True, True, "completed")])

    def mutate(result):
        result.update(status="measurement_failed", issues=["backend_failure"])

    _change_result(root, mutate)
    actual = report.build_report(root)
    condition = actual["conditions"]["phi4-rag-off"]
    assert condition["categories"]["Action"]["final"]["numerator"] == 1
    assert condition["counts"]["case_measurement_failed"] == 1
    assert actual["complete_selected_schedule"] is False


@pytest.mark.parametrize(
    "attempts,first_added,second_added",
    [([False, True], 1, 0), ([False, False, True], 0, 1), ([True], 0, 0)],
)
def test_repairs_report_incremental_rescue_without_double_counting(
    tmp_path, attempts, first_added, second_added
):
    root = _run(tmp_path, [("Action", attempts[0], attempts[-1], "completed")])

    def mutate(result):
        result["scores"].update(
            repair_count=len(attempts) - 1,
            attempt_decisions=[{"correct": correct} for correct in attempts],
        )

    _change_result(root, mutate)
    repairs = report.build_report(root)["conditions"]["phi4-rag-off"]["repairs"]
    assert repairs["histogram"][str(len(attempts) - 1)] == 1
    assert repairs["first_new_correct"] == first_added
    assert repairs["second_new_correct"] == second_added


def test_ui_handoff_latency_requires_unique_request_and_monotonic_pair(tmp_path):
    root = _run(tmp_path, [("Action", True, True, "completed")])

    def mutate(result):
        result["ui"] = {
            "events": [
                {
                    "kind": "request_observed",
                    "request_id": "one",
                    "signal_observed_ns": 1_000_000_000,
                },
                {
                    "kind": "dialog_ready",
                    "request_id": "one",
                    "ready_observed_ns": 3_000_000_000,
                    "monotonic_ns": 8_000_000_000,
                },
                {
                    "kind": "panel_ready",
                    "request_id": "missing",
                    "monotonic_ns": 10_000_000_000,
                },
            ]
        }

    _change_result(root, mutate)
    actual = report.build_report(root)
    assert actual["conditions"]["phi4-rag-off"]["ui_handoff_latency_seconds"] == {
        "n": 1,
        "p50": 2,
        "max": 2,
    }
    assert "ui_latency_unpaired" in actual["cases"][0]["timing_issues"]
    assert actual["complete_selected_schedule"] is False


def test_missing_actual_readiness_clock_is_not_replaced_by_screenshot_time(tmp_path):
    root = _run(tmp_path, [("Action", True, True, "completed")])

    def mutate(result):
        result["ui"] = {
            "events": [
                {
                    "kind": "request_observed",
                    "request_id": "one",
                    "signal_observed_ns": 1,
                },
                {"kind": "dialog_ready", "request_id": "one", "monotonic_ns": 10},
            ]
        }

    _change_result(root, mutate)
    actual = report.build_report(root)
    assert actual["conditions"]["phi4-rag-off"]["ui_handoff_latency_seconds"]["n"] == 0
    assert actual["complete_selected_schedule"] is False


def test_navigation_pairs_existing_turn_target_and_view_without_fabricated_id(tmp_path):
    root = _run(tmp_path, [("Action", True, True, "completed")])
    identity = {
        "route": "panel_navigation",
        "request_id": None,
        "correlation": {"generation": 1, "turn_id": 2},
        "target": "visualization",
        "view_mode": "saliency_map",
    }

    def mutate(result):
        result["ui"] = {
            "events": [
                {
                    **identity,
                    "kind": "request_observed",
                    "signal_observed_ns": 1_000_000_000,
                },
                {
                    **identity,
                    "kind": "request_observed",
                    "view_mode": "spectrogram",
                    "signal_observed_ns": 9_000_000_000,
                },
                {
                    **identity,
                    "kind": "panel_ready",
                    "ready_observed_ns": 4_000_000_000,
                    "monotonic_ns": 8_000_000_000,
                },
            ]
        }

    _change_result(root, mutate)
    actual = report.build_report(root)
    assert actual["conditions"]["phi4-rag-off"]["ui_handoff_latency_seconds"] == {
        "n": 1,
        "p50": 3,
        "max": 3,
    }
    assert actual["cases"][0]["timing_complete"] is True


@pytest.mark.parametrize("duplicate", [None, "request", "ready"])
def test_uncorrelated_companion_navigation_requires_unique_pair(tmp_path, duplicate):
    root = _run(tmp_path, [("Action", True, True, "completed")])
    identity = {
        "route": "panel_navigation",
        "request_id": None,
        "correlation": None,
        "target": "preprocess",
        "view_mode": None,
    }
    request = {
        **identity,
        "kind": "request_observed",
        "signal_observed_ns": 1_000_000_000,
    }
    ready = {**identity, "kind": "panel_ready", "ready_observed_ns": 2_000_000_000}

    def mutate(result):
        events = [request, ready]
        if duplicate:
            events.append(request if duplicate == "request" else ready)
        result["ui"] = {"events": events}

    _change_result(root, mutate)
    actual = report.build_report(root)
    assert actual["conditions"]["phi4-rag-off"]["ui_handoff_latency_seconds"]["n"] == (
        0 if duplicate else 1
    )
    assert actual["cases"][0]["timing_complete"] is (duplicate is None)


@pytest.mark.parametrize(
    "product",
    [
        None,
        {
            "measurement_valid": False,
            "outcome": "invalid_measurement",
            "execution": "unknown",
            "ui_handoff": "not_requested",
            "issues": ["missing_command_result"],
        },
    ],
)
def test_missing_or_invalid_product_observation_blocks_complete_not_model_score(
    tmp_path, product
):
    root = _run(tmp_path, [("Action", True, True, "completed")])
    _change_result(root, lambda result: result.update(product_outcome=product))
    actual = report.build_report(root)
    condition = actual["conditions"]["phi4-rag-off"]
    assert condition["categories"]["Action"]["final"]["numerator"] == 1
    assert condition["counts"]["product_measurement_invalid"] == 1
    assert actual["complete_selected_schedule"] is False
    assert actual["cases"][0]["product_outcome"] == product


def test_product_counts_use_saved_policy_without_reclassifying_handoff(tmp_path):
    root = _run(tmp_path, [("Action", True, True, "completed")])
    product = {
        "measurement_valid": True,
        "outcome": "handoff_ready",
        "execution": "not_evaluated",
        "ui_handoff": "ready",
        "issues": [],
    }
    _change_result(root, lambda result: result.update(product_outcome=product))
    actual = report.build_report(root)
    assert actual["conditions"]["phi4-rag-off"]["product_counts"] == {
        "outcome": {"handoff_ready": 1},
        "execution": {"not_evaluated": 1},
        "ui_handoff": {"ready": 1},
    }
    assert actual["cases"][0]["product_outcome"] == product


@pytest.mark.parametrize("timing", [None, float("nan"), -1])
def test_missing_or_invalid_timing_preserves_accuracy_but_never_completeness(
    tmp_path, timing
):
    root = _run(tmp_path, [("Action", True, True, "completed")])
    assert report.build_report(root)["complete_selected_schedule"] is True
    _change_result(root, lambda result: result.update(decision_seconds=timing))
    actual = report.build_report(root)
    condition = actual["conditions"]["phi4-rag-off"]
    assert condition["categories"]["Action"]["final"]["numerator"] == 1
    assert condition["counts"]["timing_incomplete"] == 1
    assert actual["complete_selected_schedule"] is False
