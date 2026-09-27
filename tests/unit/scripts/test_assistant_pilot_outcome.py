"""Product evidence must not turn Host protection or driver work into model credit."""

import json

import pytest

from scripts.dev.assistant_pilot_outcome import (
    score_product_outcome,
    ui_measurement_issues,
)
from scripts.dev.assistant_pilot_scoring import score_case_decisions


def evidence(tool="apply_bandpass_filter", *, correct=True, decision="Action"):
    case = {"case_id": "engineering", "decision": decision, "expected_tool": tool}
    result = {
        "case_id": case["case_id"],
        "issues": [],
        "scores": {"measurement_valid": True, "final_decision_correct": correct},
        "trace": {
            "case_id": case["case_id"],
            "events": [],
            "turn_terminal": {"outcome": "completed"},
        },
        "ui": {"events": [], "issues": [], "pending_count": 0},
        "runtime_evidence": {
            "jobs": {},
            "training": {},
            "issues": [],
            "waiting": False,
        },
        "before_state": {},
        "after_state": {},
    }
    return case, result


def event(result, event_kind, **payload):
    result["trace"]["events"].append({"kind": event_kind, "payload": payload})


def admitted(result, tool, action="execute"):
    event(result, "host_decision", kind="admission", command_name=tool, action=action)


def command(result, tool, *, ok=True):
    admitted(result, tool)
    event(result, "command_result", tool_name=tool, ok=ok, state={})


def ui_request(result, tool, *, kind="decision_required"):
    admitted(result, tool)
    event(
        result,
        "ui_requested",
        kind=kind,
        request_id="request",
        command="action",
        tool_name=tool,
    )


def test_actual_command_and_state_complete_separately_from_raw_score():
    case, result = evidence()
    command(result, case["expected_tool"])
    score = score_product_outcome(case, result)
    assert score["measurement_valid"] and score["decision_correct"]
    assert score["execution"] == score["outcome"] == "completed"


def test_host_rescue_and_fixture_cancel_never_credit_stop():
    case, result = evidence("stop_training")
    admitted(result, "stop_training", "publication_blocked")
    result["fixture_cancel_requested"] = {"accepted": True}
    result["runtime_evidence"]["training"] = {
        "outcome": {"state": "cancelled"},
        "matched": False,
    }
    score = score_product_outcome(case, result)
    assert score["decision_correct"] and score["measurement_valid"]
    assert score["execution"] == "not_started"
    assert score["outcome"] == "blocked"


def test_dialog_driver_cancel_is_successful_handoff_not_complete_import():
    case, result = evidence("import_eeg_data")
    ui_request(result, case["expected_tool"])
    result["ui"]["events"] = [
        {"kind": "dialog_ready", "request_id": "request"},
        {"kind": "driver_action", "request_id": "request", "action": "reject_dialog"},
    ]
    event(
        result,
        "ui_resolution",
        request_id="request",
        tool_name=case["expected_tool"],
        status="cancelled",
    )
    score = score_product_outcome(case, result)
    assert score["measurement_valid"]
    assert score["ui_handoff"] == "ready"
    assert score["execution"] == "not_evaluated"
    assert score["outcome"] == "handoff_ready"


def saliency():
    case, result = evidence("compute_saliency")
    ui_request(result, case["expected_tool"], kind="action_requested")
    event(
        result,
        "ui_resolution",
        request_id="request",
        tool_name="compute_saliency",
        status="completed",
    )
    result["ui"]["events"] = [
        {
            "kind": "panel_ready",
            "request_id": "request",
            "projection_ready": True,
            "render_ready": True,
            "operation_id": "render-job",
        }
    ]
    result["runtime_evidence"]["jobs"] = {
        "compute-job": {"kind": "saliency", "phase": "completed"}
    }
    result["runtime_evidence"]["saliency_operation_id"] = "compute-job"
    return case, result


def test_old_successful_saliency_does_not_cover_new_failed_operation():
    case, result = saliency()
    result["runtime_evidence"]["jobs"]["old-job"] = {
        "kind": "saliency",
        "phase": "completed",
    }
    result["runtime_evidence"]["jobs"]["compute-job"]["phase"] = "failed"
    score = score_product_outcome(case, result)
    assert score["outcome"] != "completed"
    assert not score["measurement_valid"]  # Contradictory completed UI resolution.


@pytest.mark.parametrize(
    "code,kind,status",
    [
        ("readiness_timeout", "readiness_timeout", "timed_out"),
        ("visualization_render_failed", "render_failed", "failed"),
    ],
)
def test_observed_ui_failure_is_product_failure_not_exclusion(code, kind, status):
    case, result = evidence("import_eeg_data")
    ui_request(result, case["expected_tool"])
    result["ui"]["issues"] = [code]
    result["issues"] = [code]
    result["ui"]["events"] = [
        {"kind": "request_observed", "request_id": "request", "monotonic_ns": 1},
        {
            "kind": kind,
            "request_id": "request",
            "monotonic_ns": 2,
            "screenshot": "failure.png",
        },
    ]
    assert ui_measurement_issues(result["ui"]) == []
    score = score_product_outcome(case, result)
    assert score["measurement_valid"]
    assert score["ui_handoff"] == status
    assert score["outcome"] == "failed"
    del result["ui"]["events"][1]["screenshot"]
    assert ui_measurement_issues(result["ui"]) == [code]
    assert not score_product_outcome(case, result)["measurement_valid"]


def test_uncorrelated_ui_failure_does_not_excuse_missing_observation():
    ui = {
        "issues": ["readiness_timeout"],
        "events": [
            {"kind": "request_observed", "request_id": "new", "monotonic_ns": 1},
            {
                "kind": "readiness_timeout",
                "request_id": "old",
                "monotonic_ns": 2,
                "screenshot": "failure.png",
            },
        ],
    }
    assert ui_measurement_issues(ui) == ["readiness_timeout"]


def test_saliency_render_and_compute_have_distinct_operation_ids():
    case, result = saliency()
    score = score_product_outcome(case, result)
    assert score["measurement_valid"]
    assert score["outcome"] == "completed"


@pytest.mark.parametrize("missing", ["jobs", "render", "resolution"])
def test_saliency_requires_each_actual_completion_layer(missing):
    case, result = saliency()
    if missing == "jobs":
        result["runtime_evidence"]["jobs"] = {
            "fixture": {"kind": "training", "phase": "completed"}
        }
    elif missing == "render":
        result["ui"]["events"] = []
    else:
        result["trace"]["events"] = [
            e for e in result["trace"]["events"] if e["kind"] != "ui_resolution"
        ]
    score = score_product_outcome(case, result)
    assert not score["measurement_valid"]
    assert score["outcome"] == "invalid_measurement"


@pytest.mark.parametrize("decision", ["No-call", "Clarification"])
def test_normal_nonexecution_requires_valid_response_without_action(decision):
    case, result = evidence("respond_to_user", decision=decision)
    score = score_product_outcome(case, result)
    assert score["outcome"] == "correct_nonexecution"
    command(result, "apply_bandpass_filter")
    assert score_product_outcome(case, result)["outcome"] == "unexpected_execution"


def test_format_exhausted_noncall_is_measured_model_failure():
    case, result = evidence("respond_to_user", correct=False, decision="No-call")
    result["trace"]["turn_terminal"]["outcome"] = "invalid_action"
    score = score_product_outcome(case, result)
    assert score["measurement_valid"] and not score["decision_correct"]
    assert score["outcome"] == "decision_incorrect"


def _rejected_typed_nonaction_trace():
    """Observed failure shape, with synthetic copy rather than a bank question."""
    case, result = evidence("respond_to_user", decision="No-call")
    case.update(expected_parameters=None, expected_workflow_stage="empty")
    trace = result["trace"]
    trace["generations"] = []
    correlation = {"generation": 6, "turn_id": 6}
    for number, pending, missing in (
        (6, "import_eeg_data", ["panel_name", "view_mode"]),
        (7, "create_epochs", ["raw_data_path"]),
    ):
        raw = (
            "```json\n"
            + json.dumps(
                {
                    "workflow_stage": "empty",
                    "tool_name": "respond_to_user",
                    "parameters": {
                        "message": "Load data first.",
                        "pending_action": pending,
                        "missing_inputs": missing,
                    },
                }
            )
            + "\n```"
        )
        request = {
            "generation_id": number,
            "response_contract": "structured_action",
            "messages": [[["role", "user"], ["content", "No data is loaded."]]],
        }
        trace["generations"].append(
            {
                "generation_id": number,
                "request": request,
                "raw_response": raw,
                "terminal": "finished",
                "started": True,
            }
        )
        event(result, "generation_request", **request)
        for phase, text in (("started", ""), ("chunk", raw), ("finished", "")):
            event(
                result, "generation_event", generation_id=number, phase=phase, text=text
            )
        event(
            result,
            "host_decision",
            kind="envelope",
            correlation=correlation,
            generation_id=number,
            status="format_error",
            recovery_action="retry_format" if number == 6 else "exhausted",
        )
    trace["turn_terminal"] = {"correlation": correlation, "outcome": "invalid_action"}
    event(result, "turn_terminal", **trace["turn_terminal"])
    return case, result


def test_typed_nonaction_rejection_is_wrong_decision_not_missing_measurement():
    case, result = _rejected_typed_nonaction_trace()
    result["scores"] = score_case_decisions(case, result["trace"])
    assert result["scores"]["measurement_valid"]
    assert result["scores"]["first_decision_correct"] is False
    assert result["scores"]["final_decision_correct"] is False
    actual = score_product_outcome(case, result)
    assert actual["measurement_valid"] and actual["issues"] == []
    assert actual["outcome"] == "decision_incorrect"
    assert actual["execution"] == "not_started"
    assert actual["unexpected_action"] is False


@pytest.mark.parametrize("damage", ["missing", "mismatched"])
def test_known_rejection_cannot_excuse_missing_or_wrong_terminal(damage):
    case, result = _rejected_typed_nonaction_trace()
    if damage == "missing":
        result["trace"]["turn_terminal"] = None
    else:
        result["trace"]["turn_terminal"] = {
            "correlation": {"generation": 99, "turn_id": 99},
            "outcome": "invalid_action",
        }
    result["scores"] = score_case_decisions(case, result["trace"])
    assert result["scores"]["measurement_valid"] is False
    actual = score_product_outcome(case, result)
    assert actual["measurement_valid"] is False
    assert actual["outcome"] == "invalid_measurement"


def test_missing_command_result_is_not_completed_by_turn_terminal():
    case, result = evidence()
    admitted(result, case["expected_tool"])
    assert not score_product_outcome(case, result)["measurement_valid"]


def test_failed_command_is_valid_failure_not_recorder_fault():
    case, result = evidence()
    command(result, case["expected_tool"], ok=False)
    score = score_product_outcome(case, result)
    assert score["measurement_valid"] and score["outcome"] == "failed"


def test_wrong_tool_success_does_not_become_requested_outcome():
    case, result = evidence(correct=False)
    command(result, "apply_notch_filter")
    score = score_product_outcome(case, result)
    assert score["measurement_valid"] and not score["decision_correct"]
    assert score["outcome"] == "decision_incorrect"
    assert score["observed_execution"] == "command_result_received"
    assert score["observed_actions"] == [
        {"kind": "command_result", "tool_name": "apply_notch_filter", "ok": True}
    ]
    assert score["execution"] != "not_started"


def test_incorrect_noncall_retains_unexpected_side_effect():
    case, result = evidence("respond_to_user", correct=False, decision="No-call")
    command(result, "apply_notch_filter")
    score = score_product_outcome(case, result)
    assert score["outcome"] == "decision_incorrect"
    assert score["unexpected_action"] is True
    assert score["observed_execution"] == "command_result_received"


def test_navigation_requires_same_request_and_visible_projection():
    case, result = evidence("switch_panel")
    admitted(result, "switch_panel")
    event(
        result,
        "navigation_requested",
        target="evaluation",
        view_mode=None,
        correlation={"turn_id": 1},
    )
    result["ui"]["events"] = [
        {
            "kind": "panel_ready",
            "target": "evaluation",
            "view_mode": None,
            "correlation": {"turn_id": 1},
            "projection_ready": True,
            "render_ready": None,
        }
    ]
    assert score_product_outcome(case, result)["outcome"] == "completed"
    result["ui"]["events"][0]["correlation"]["turn_id"] = 2
    assert not score_product_outcome(case, result)["measurement_valid"]


def test_ui_ready_for_other_request_is_missing_evidence():
    case, result = evidence("import_eeg_data")
    ui_request(result, case["expected_tool"])
    result["ui"]["events"] = [{"kind": "dialog_ready", "request_id": "other"}]
    assert not score_product_outcome(case, result)["measurement_valid"]


@pytest.mark.parametrize(
    "tool,state", [("start_training", "completed"), ("stop_training", "cancelled")]
)
def test_training_requires_bound_terminal_not_accepted_command(tool, state):
    case, result = evidence(tool)
    command(result, tool)
    assert not score_product_outcome(case, result)["measurement_valid"]
    result["runtime_evidence"]["training"] = {
        "action": tool,
        "matched": True,
        "expected_run": {"run_id": 1},
        "outcome": {"state": state, "run": {"run_id": 1}},
    }
    assert score_product_outcome(case, result)["outcome"] == "completed"
    result["fixture_cancel_requested"] = {"accepted": True}
    assert score_product_outcome(case, result)["outcome"] != "completed"


@pytest.mark.parametrize("field", ["scores", "before_state", "after_state"])
def test_missing_required_evidence_invalidates_measurement(field):
    case, result = evidence()
    command(result, case["expected_tool"])
    del result[field]
    assert not score_product_outcome(case, result)["measurement_valid"]


def test_case_identity_mismatch_invalidates_measurement():
    case, result = evidence()
    result["case_id"] = "other"
    assert not score_product_outcome(case, result)["measurement_valid"]
