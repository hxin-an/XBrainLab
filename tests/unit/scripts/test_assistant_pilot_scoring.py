"""Research decision scoring only; no model, UI or product outcome claims."""

import copy
import json

import pytest

from scripts.dev.assistant_pilot_scoring import score_case_decisions, score_decision


def case(decision="Action", tool="resample_data", parameters=None):
    return {
        "case_id": "DEV-A10-01-V0",
        "family_id": "DEV-A10-01",
        "split": "DEV",
        "decision": decision,
        "expected_tool": tool,
        "expected_parameters": {"rate": 128} if parameters is None else parameters,
        "expected_workflow_stage": "data_loaded",
    }


def response(tool="resample_data", parameters=None, stage="data_loaded"):
    return json.dumps(
        {
            "workflow_stage": stage,
            "tool_name": tool,
            "parameters": {"rate": 128} if parameters is None else parameters,
        }
    )


def non_action(decision):
    return {
        **case(decision, "respond_to_user"),
        "expected_parameters": None,
    }


def test_numeric_values_match_without_coercing_strings_or_booleans():
    oracle = case(
        tool="apply_bandpass_filter", parameters={"low_freq": 1, "high_freq": 35}
    )
    assert score_decision(
        oracle, response("apply_bandpass_filter", {"low_freq": 1.0, "high_freq": 35.0})
    )["correct"]
    for value in ["1", True, 2]:
        assert not score_decision(
            oracle,
            response("apply_bandpass_filter", {"low_freq": value, "high_freq": 35}),
        )["correct"]


def test_integer_only_product_schema_is_not_relaxed_by_numeric_equality():
    assert not score_decision(case(), response(parameters={"rate": 128.0}))["correct"]


@pytest.mark.parametrize("label", ["json", ""])
def test_whole_fence_uses_same_product_parser_and_decision_score(label):
    raw = response()
    assert score_decision(case(), f"```{label}\n{raw}\n```") == score_decision(
        case(), raw
    )


@pytest.mark.parametrize(
    "raw",
    [
        response(tool="unknown_tool"),
        response(parameters={"rate": 128.0}),
        response(parameters={"rate": 128, "extra": 1}),
        response(stage="empty"),
        response() + response(),
        "Some explanation " + response(),
    ],
)
def test_fence_does_not_rescue_wrong_tool_parameters_stage_or_malformed_decision(raw):
    assert score_decision(case(), "```json\n" + raw + "\n```")["correct"] is False


def test_string_enum_parameters_match_exactly_without_normalization():
    oracle = case(tool="normalize_data", parameters={"method": "z-score"})
    assert score_decision(oracle, response("normalize_data", {"method": "z-score"}))[
        "correct"
    ]
    for method in ["min-max", "Z-score", " z-score "]:
        assert not score_decision(
            oracle, response("normalize_data", {"method": method})
        )["correct"]


@pytest.mark.parametrize(
    "raw",
    [
        response(tool="apply_notch_filter", parameters={"freq": 128}),
        response(parameters={}),
        response(parameters={"rate": 128, "extra": 1}),
        response(stage="empty"),
        response(tool="unknown_tool"),
        "Some explanation " + response(),
        response() + response(),
        '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
        '"parameters":{"rate":128,"rate":64}}',
        '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
        '"parameters":{"rate":NaN}}',
        "null",
        "[]",
        "",
        "  ",
        None,
    ],
)
def test_wrong_or_malformed_action_never_passes(raw):
    assert score_decision(case(), raw)["correct"] is False


@pytest.mark.parametrize("decision", ["Clarification", "No-call"])
def test_normal_non_action_does_not_require_typed_pending_or_exact_message(decision):
    for message in ["Please provide the missing value.", "Here is an explanation."]:
        assert (
            score_decision(
                non_action(decision), response("respond_to_user", {"message": message})
            )["correct"]
            is True
        )


@pytest.mark.parametrize("decision", ["Clarification", "No-call"])
def test_optional_structured_pending_is_not_a_new_semantic_oracle(decision):
    raw = response(
        "respond_to_user",
        {
            "message": "Which sampling rate?",
            "pending_action": "resample_data",
            "missing_inputs": ["rate"],
        },
    )
    assert score_decision(non_action(decision), raw)["correct"] is True


def test_unavailable_model_stage_is_wrong_decision_not_a_measurement_exception():
    raw = response(
        "respond_to_user",
        {
            "message": "Which sampling rate?",
            "pending_action": "resample_data",
            "missing_inputs": ["rate"],
        },
        stage="unavailable",
    )
    score = score_decision(non_action("Clarification"), raw)
    assert score["correct"] is False
    assert score["observed_stage"] == "unavailable"


@pytest.mark.parametrize(
    "raw",
    [
        '```json\n{\n  "workflow_stage": "empty",\n  "tool_name": "respond_to_user",\n  "parameters": {\n    "message": "To apply a bandpass filter, you must first load the raw EEG data.  Please use the Import EEG Data action to load the data before applying the filter.",\n    "pending_action": "import_eeg_data",\n    "missing_inputs": [\n      "panel_name",\n      "view_mode"\n    ]\n  }\n}\n```',
        '```json\n{\n  "workflow_stage": "empty",\n  "tool_name": "respond_to_user",\n  "parameters": {\n    "message": "To begin preprocessing, you must first load the raw EEG data. Before applying any filters, such as bandpass filtering, you need to load the data.",\n    "pending_action": "create_epochs",\n    "missing_inputs": [\n      "raw_data_path"\n    ]\n  }\n}\n```',
    ],
)
def test_frozen_gemma_invalid_typed_metadata_is_not_a_correct_no_call(raw):
    """p0-ae482c41 / gemma3-rag-on / DEV-N03-01-V3 raw generations."""
    oracle = {**non_action("No-call"), "expected_workflow_stage": "empty"}
    score = score_decision(oracle, raw)
    assert score["correct"] is False
    assert score["reason"] == "invalid_envelope"


@pytest.mark.parametrize(
    "pending,missing,stage",
    [
        ("unknown_tool", ["rate"], "data_loaded"),
        ("import_eeg_data", ["panel_name", "view_mode"], "data_loaded"),
        ("create_epochs", ["raw_data_path"], "data_loaded"),
        ("resample_data", ["invented_rate"], "data_loaded"),
        ("apply_bandpass_filter", ["low_freq", "invented_high"], "data_loaded"),
        ("resample_data", ["rate"], "empty"),
        ("resample_data", ["rate"], "epoch_ready"),
    ],
)
def test_invalid_typed_metadata_never_passes_on_nonempty_message(
    pending, missing, stage
):
    oracle = {**non_action("Clarification"), "expected_workflow_stage": stage}
    raw = response(
        "respond_to_user",
        {
            "message": "Please provide the value.",
            "pending_action": pending,
            "missing_inputs": missing,
        },
        stage=stage,
    )
    assert score_decision(oracle, raw)["reason"] == "invalid_envelope"


@pytest.mark.parametrize(
    "pending,missing",
    [
        ("apply_bandpass_filter", ["low_freq"]),
        ("apply_notch_filter", ["freq"]),
        ("resample_data", ["rate"]),
        ("set_reference", ["method"]),
        ("normalize_data", ["method"]),
    ],
)
@pytest.mark.parametrize("stage", ["data_loaded", "preprocessed"])
def test_typed_metadata_reuses_direct_schema_and_accepts_required_subset(
    pending, missing, stage
):
    oracle = {**non_action("Clarification"), "expected_workflow_stage": stage}
    raw = response(
        "respond_to_user",
        {
            "message": "Please provide the value.",
            "pending_action": pending,
            "missing_inputs": missing,
        },
        stage=stage,
    )
    assert score_decision(oracle, raw)["correct"] is True


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        " ",
        "I will not execute anything.",
        response("respond_to_user", {"message": ""}),
        response("respond_to_user", {"message": "  "}),
        response("respond_to_user", {"message": "No", "extra": 1}),
        response("respond_to_user", {"message": "No"}, stage="empty"),
        response(),
    ],
)
@pytest.mark.parametrize("decision", ["Clarification", "No-call"])
def test_no_side_effect_cannot_rescue_invalid_or_wrong_model_decision(decision, raw):
    assert score_decision(non_action(decision), raw)["correct"] is False


def test_first_and_later_decisions_remain_separate_without_host_rescue():
    oracle = case()
    first = score_decision(oracle, response(parameters={"rate": 64}))
    final = score_decision(oracle, response())
    assert first["correct"] is False
    assert final["correct"] is True
    assert "outcome" not in final
    assert "host_verified" not in final


def test_opening_tool_decision_does_not_claim_window_or_operation_completion():
    result = score_decision(
        case(tool="import_eeg_data", parameters={}),
        response("import_eeg_data", {}),
    )
    assert result["correct"] is True
    assert set(result) == {"correct", "reason", "observed_tool", "observed_stage"}


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "unknown"},
        {"decision": []},
        {"expected_workflow_stage": {}},
        {"expected_workflow_stage": "made_up_stage"},
        {"expected_tool": "unknown_tool"},
        {"expected_parameters": {"rate": True}},
        {"expected_parameters": {"rate": float("nan")}},
        {"expected_parameters": {"rate": float("inf")}},
        {"expected_parameters": {"rate": "128"}},
        {"expected_parameters": {}},
        {"expected_parameters": {"rate": 128, "extra": 1}},
        {
            "decision": "No-call",
            "expected_tool": "resample_data",
            "expected_parameters": None,
        },
    ],
)
def test_invalid_oracle_is_measurement_error_not_model_failure(changes):
    with pytest.raises(ValueError, match="oracle"):
        score_decision({**case(), **changes}, response())


def test_scorer_does_not_mutate_or_consume_other_case_metadata():
    oracle = case()
    oracle["input"] = "Do not send an oracle to the model."
    oracle["metadata"] = {"host_verified": True, "outcome": "completed"}
    before = copy.deepcopy(oracle)
    assert score_decision(oracle, response(parameters={"rate": 64}))["correct"] is False
    assert oracle == before


def complete_trace(raws, *, last_phase="finished", outcome="completed"):
    generations, events = [], []
    for number, raw in enumerate(raws, 1):
        phase = last_phase if number == len(raws) else "finished"
        request = {
            "generation_id": number,
            "response_contract": "structured_action",
            "messages": [[["role", "user"], ["content", "User request"]]],
        }
        generations.append(
            {
                "generation_id": number,
                "request": request,
                "raw_response": raw,
                "terminal": phase,
                "started": True,
            }
        )
        events.extend(
            [
                {"kind": "generation_request", "payload": request},
                {
                    "kind": "generation_event",
                    "payload": {
                        "generation_id": number,
                        "phase": "started",
                        "text": "",
                    },
                },
                {
                    "kind": "generation_event",
                    "payload": {"generation_id": number, "phase": "chunk", "text": raw},
                },
                {
                    "kind": "generation_event",
                    "payload": {"generation_id": number, "phase": phase, "text": ""},
                },
            ]
        )
    events.append({"kind": "turn_terminal", "payload": {"outcome": outcome}})
    return {
        "case_id": case()["case_id"],
        "measurement_issues": [],
        "generations": generations,
        "events": events,
        "turn_terminal": {"outcome": outcome},
    }


def test_complete_case_keeps_first_final_and_host_separate():
    trace = complete_trace([response(parameters={"rate": 64}), response()])
    trace["events"].append({"kind": "host_decision", "payload": {"action": "execute"}})
    result = score_case_decisions(case(), trace)
    assert result["measurement_valid"] is True
    assert result["first_decision_correct"] is False
    assert result["final_decision_correct"] is True
    assert result["repair_count"] == 1
    assert "product_success" not in result
    assert result["host_observations"] == [{"action": "execute"}]


@pytest.mark.parametrize(
    "last_phase,outcome,timed_out,status",
    [
        ("error", "failed", False, "model_error"),
        ("cancelled", "cancelled", True, "decision_timeout"),
    ],
)
def test_complete_runtime_failure_is_not_discarded_as_measurement_fault(
    last_phase, outcome, timed_out, status
):
    trace = complete_trace([response()], last_phase=last_phase, outcome=outcome)
    result = score_case_decisions(case(), trace, decision_timed_out=timed_out)
    assert result["measurement_valid"] is True
    assert result["final_decision_correct"] is False
    assert result["execution_status"] == status


@pytest.mark.parametrize(
    "damage",
    ["wrong_case", "missing_trace", "raw_mismatch", "excess_repairs", "wrong_profile"],
)
def test_corrupt_or_out_of_protocol_case_is_not_model_incorrect(damage):
    trace = complete_trace([response()])
    if damage == "wrong_case":
        trace["case_id"] = "another-case"
    elif damage == "missing_trace":
        trace["measurement_issues"] = ["missing_turn_terminal"]
    elif damage == "raw_mismatch":
        trace["generations"][0]["raw_response"] = "overwritten"
    elif damage == "excess_repairs":
        trace = complete_trace([response()] * 4)
    else:
        trace["generations"][0]["request"]["response_contract"] = "natural_language"
    result = score_case_decisions(case(), trace)
    assert result["measurement_valid"] is False
    assert result["final_decision_correct"] is None


def test_timeout_without_actual_cancel_cannot_rescue_incomplete_record():
    result = score_case_decisions(
        case(), complete_trace([response()]), decision_timed_out=True
    )
    assert result["measurement_valid"] is False


def test_aggregate_cancel_flag_without_terminal_event_is_not_evidence():
    trace = complete_trace([response()], last_phase="cancelled", outcome="cancelled")
    trace["events"] = [
        event for event in trace["events"] if event["kind"] != "turn_terminal"
    ]
    result = score_case_decisions(case(), trace, decision_timed_out=True)
    assert result["measurement_valid"] is False
    assert "turn_terminal_trace_mismatch" in result["measurement_issues"]


def test_timeout_before_generation_is_measured_failure_only_with_real_terminal():
    trace = complete_trace([], outcome="cancelled")
    trace["measurement_issues"] = ["missing_generation"]
    result = score_case_decisions(case(), trace, decision_timed_out=True)
    assert result["measurement_valid"] is True
    assert result["final_decision_correct"] is False


@pytest.mark.parametrize("limit", [0, 1, 2])
def test_frozen_repair_policy_controls_measured_generation_budget(limit):
    trace = complete_trace(["invalid"] * limit + [response()])
    result = score_case_decisions(case(), trace, max_format_recovery_attempts=limit)
    assert result["measurement_valid"] is True
    assert result["final_decision_correct"] is True
    assert result["scorer_schema"] == "xbrainlab.assistant_decision_scores.v2"
    assert result["max_format_recovery_attempts"] == limit
    excess = score_case_decisions(
        case(),
        complete_trace(["invalid"] * (limit + 1) + [response()]),
        max_format_recovery_attempts=limit,
    )
    assert excess["measurement_valid"] is False
    assert excess["final_decision_correct"] is None
    assert "repair_budget_exceeded" in excess["measurement_issues"]


@pytest.mark.parametrize("limit", [-1, True, 1.5, "1"])
def test_frozen_repair_policy_rejects_invalid_limits(limit):
    with pytest.raises(ValueError, match="recovery"):
        score_case_decisions(
            case(), complete_trace([response()]), max_format_recovery_attempts=limit
        )


def test_new_score_explains_parameter_mismatch_without_changing_legacy_decision():
    trace = complete_trace([response(parameters={"rate": 64})])
    legacy = score_case_decisions(case(), trace)
    current = score_case_decisions(case(), trace, max_format_recovery_attempts=1)
    assert "scorer_schema" not in legacy
    assert (
        current["first_decision_correct"] == legacy["first_decision_correct"] is False
    )
    attempt = current["attempt_decisions"][0]
    assert attempt["reason"] == legacy["attempt_decisions"][0]["reason"]
    assert attempt["explanation"]["expected"]["parameters"] == {"rate": 128}
    assert attempt["explanation"]["observed"]["parameters"] == {"rate": 64}
    assert attempt["explanation"]["mismatches"] == ["parameters"]


def test_new_score_explains_parameter_schema_even_when_numbers_compare_equal():
    result = score_case_decisions(
        case(),
        complete_trace([response(parameters={"rate": 128.0})]),
        max_format_recovery_attempts=1,
    )
    assert result["final_decision_correct"] is False
    assert result["attempt_decisions"][0]["explanation"]["mismatches"] == [
        "parameter_schema"
    ]
