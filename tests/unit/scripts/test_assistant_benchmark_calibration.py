"""Offline scorer calibration, not model or product success measurements."""

import copy
import json

import pytest

from scripts.dev.assistant_benchmark_calibration import (
    DEFAULT_CASES,
    calibrate,
    load_calibration,
    main,
    score_observation,
)


@pytest.fixture
def corpus():
    return load_calibration(DEFAULT_CASES)


def example(corpus, case_id):
    case = next(case for case in corpus["cases"] if case["id"] == case_id)
    observation = next(
        item
        for item in corpus["observations"]
        if item["case_id"] == case_id and item["id"].endswith(".pass")
    )
    return copy.deepcopy(case), copy.deepcopy(observation)


def response(tool="resample_data", parameters=None, stage="data_loaded"):
    return json.dumps(
        {
            "workflow_stage": stage,
            "tool_name": tool,
            "parameters": {"rate": 128} if parameters is None else parameters,
        }
    )


def test_checked_in_calibration_has_three_decisions_and_no_product_claim(corpus):
    report = calibrate(corpus)
    assert report["calibration"]["passed"] is True
    assert report["calibration"]["observation_count"] == 8
    assert report["evidence_kind"] == "synthetic_development_calibration"
    assert report["model_executed"] is False
    assert report["product_benchmark_score"] is None
    assert report["human_agreement"] is None
    assert {case["decision"] for case in corpus["cases"]} == {
        "no_call",
        "clarification",
        "action",
    }
    assert all(case["split"] == "development" for case in corpus["cases"])
    assert all(
        case["source"] == "agent_authored_calibration" for case in corpus["cases"]
    )


@pytest.mark.parametrize(
    "raw",
    [
        response(stage="empty"),
        response(tool="apply_notch_filter", parameters={"freq": 128}),
        response(parameters={"rate": 64}),
        response(parameters={"rate": True}),
        response(parameters={"rate": "128"}),
        response(parameters={"rate": 128, "extra": 1}),
        response(parameters={}),
        "I will do it. " + response(),
        response() + response(),
        '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
        '"parameters":{"rate":128,"rate":64}}',
    ],
)
def test_wrong_raw_decision_is_not_rescued_by_correct_host_outcome(corpus, raw):
    case, observation = example(corpus, "resample")
    observation["raw_response"] = raw
    score = score_observation(case, observation)
    assert score["raw"]["passed"] is False
    assert score["agent"]["passed"] is True
    assert score["outcome"]["passed"] is True


def test_correct_raw_decision_does_not_mask_incorrect_admitted_decision(corpus):
    case, observation = example(corpus, "resample")
    observation["agent_response"] = response(parameters={"rate": 64})
    score = score_observation(case, observation)
    assert score["raw"]["passed"] is True
    assert score["agent"]["passed"] is False
    assert score["outcome"]["passed"] is False


@pytest.mark.parametrize("effect", ["proposal", "confirmation", "execution", "gui"])
def test_no_call_rejects_every_unexpected_action_effect(corpus, effect):
    case, observation = example(corpus, "explain")
    observation["effects"].append({"kind": effect, "tool": "resample_data"})
    assert score_observation(case, observation)["outcome"]["passed"] is False


@pytest.mark.parametrize("case_id", ["explain", "clarify", "resample", "open_import"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("complete", False),
        ("complete", "true"),
        ("terminal", "cancelled"),
        ("terminal", "pending"),
        ("terminal", "error"),
        ("errors", ["worker failed"]),
        ("before", {"generation": 99}),
        ("after", {"generation": 99}),
        ("case_id", "some_other_case"),
    ],
)
def test_incomplete_wrong_state_or_wrong_case_never_passes(
    corpus, case_id, field, value
):
    case, observation = example(corpus, case_id)
    observation[field] = value
    assert score_observation(case, observation)["outcome"]["passed"] is False


@pytest.mark.parametrize(
    "field",
    [
        "complete",
        "before",
        "after",
        "effects",
        "pending",
        "errors",
        "terminal",
        "ui",
        "execution",
    ],
)
def test_missing_observation_is_not_assumed_safe(corpus, field):
    case, observation = example(corpus, "explain")
    del observation[field]
    assert score_observation(case, observation)["outcome"]["passed"] is False


def test_no_call_rejects_unnecessary_pending_action(corpus):
    case, observation = example(corpus, "explain")
    observation["pending"] = {"tool": "resample_data", "missing_inputs": ["rate"]}
    assert score_observation(case, observation)["outcome"]["passed"] is False


@pytest.mark.parametrize("missing", [["low_freq"], ["high_freq"], ["rate"], []])
def test_clarification_requires_exact_structured_missing_fields(corpus, missing):
    case, observation = example(corpus, "clarify")
    observation["raw_response"] = response(
        "respond_to_user",
        {
            "message": "Which cutoffs?",
            "pending_action": "apply_bandpass_filter",
            "missing_inputs": missing,
        },
    )
    assert score_observation(case, observation)["raw"]["passed"] is False


def test_clarification_is_not_a_keyword_matching_task(corpus):
    case, observation = example(corpus, "clarify")
    observation["raw_response"] = response(
        "respond_to_user",
        {
            "message": "Please provide both cutoffs.",
            "pending_action": "apply_bandpass_filter",
            "missing_inputs": ["high_freq", "low_freq"],
        },
    )
    assert score_observation(case, observation)["raw"]["passed"] is True
    observation["raw_response"] = response(
        "respond_to_user",
        {"message": "What low and high bandpass cutoffs should I use?"},
    )
    assert score_observation(case, observation)["raw"]["passed"] is False


def test_clarification_needs_observed_receipt_and_cannot_execute(corpus):
    case, observation = example(corpus, "clarify")
    observation["pending"] = None
    assert score_observation(case, observation)["outcome"]["passed"] is False
    case, observation = example(corpus, "clarify")
    observation["effects"].append(
        {"kind": "execution", "tool": "apply_bandpass_filter"}
    )
    assert score_observation(case, observation)["outcome"]["passed"] is False


def test_action_needs_verification_and_completion_not_just_proposal(corpus):
    case, observation = example(corpus, "resample")
    observation["host_verified"] = False
    assert score_observation(case, observation)["outcome"]["passed"] is False
    case, observation = example(corpus, "resample")
    observation["effects"] = [{"kind": "proposal", "tool": "resample_data"}]
    assert score_observation(case, observation)["outcome"]["passed"] is False


def test_gui_opening_requires_usable_requested_surface_and_is_not_backend_success(
    corpus,
):
    case, observation = example(corpus, "open_import")
    observation["ui"]["enabled"] = False
    assert score_observation(case, observation)["outcome"]["passed"] is False
    case, observation = example(corpus, "resample")
    observation["terminal"] = "gui_ready"
    observation["effects"] = [{"kind": "gui", "tool": "resample_data"}]
    assert score_observation(case, observation)["outcome"]["passed"] is False


def test_effect_identity_order_and_multiplicity_are_part_of_oracle(corpus):
    case, observation = example(corpus, "resample")
    observation["effects"].append(observation["effects"][-1])
    assert score_observation(case, observation)["outcome"]["passed"] is False
    case, observation = example(corpus, "resample")
    observation["effects"].reverse()
    assert score_observation(case, observation)["outcome"]["passed"] is False
    case, observation = example(corpus, "resample")
    observation["effects"][-1]["tool"] = "normalize_data"
    assert score_observation(case, observation)["outcome"]["passed"] is False


@pytest.mark.parametrize(
    "result",
    [
        None,
        {"tool": "resample_data", "parameters": {"rate": 64}, "success": True},
        {"tool": "resample_data", "parameters": {"rate": 128}, "success": False},
    ],
)
def test_completed_action_needs_correct_observed_execution_result(corpus, result):
    case, observation = example(corpus, "resample")
    observation["execution"] = result
    assert score_observation(case, observation)["outcome"]["passed"] is False


def test_case_mismatch_cannot_credit_any_layer(corpus):
    case, observation = example(corpus, "resample")
    observation["case_id"] = "foreign_case"
    assert all(
        not result["passed"] for result in score_observation(case, observation).values()
    )


def test_schema_number_equivalence_is_not_python_boolean_equivalence(corpus):
    case, observation = example(corpus, "resample")
    case["tool"] = "apply_bandpass_filter"
    case["parameters"] = {"low_freq": 4, "high_freq": 38}
    for effect in case["effects"]:
        effect["tool"] = case["tool"]
    observation["raw_response"] = response(
        case["tool"], {"high_freq": 38.0, "low_freq": 4.0}
    )
    assert score_observation(case, observation)["raw"]["passed"] is True
    observation["raw_response"] = response(
        case["tool"], {"high_freq": 38, "low_freq": True}
    )
    assert score_observation(case, observation)["raw"]["passed"] is False


def test_case_cannot_omit_product_required_confirmation(corpus):
    case, observation = example(corpus, "resample")
    case["tool"] = "start_training"
    case["parameters"] = {}
    for effect in case["effects"]:
        effect["tool"] = case["tool"]
    with pytest.raises(ValueError, match="confirmation"):
        score_observation(case, observation)


def test_successful_action_requires_an_explicit_execution_record(corpus):
    case, observation = example(corpus, "resample")
    observation["execution"] = {
        "tool": "resample_data",
        "parameters": {"rate": 128},
        "success": True,
    }
    assert score_observation(case, observation)["outcome"]["passed"] is True


def test_confirmation_must_precede_actual_execution(corpus):
    case, observation = example(corpus, "resample")
    case["requires_confirmation"] = True
    approved = {"kind": "confirmation_approved", "tool": case["tool"]}
    case["effects"].insert(1, approved)
    observation["effects"].insert(1, approved)
    assert score_observation(case, observation)["outcome"]["passed"] is True
    observation["effects"].reverse()
    assert score_observation(case, observation)["outcome"]["passed"] is False


@pytest.mark.parametrize(
    "mutation",
    ["missing_row", "duplicate_row", "missing_label", "unknown_case", "empty"],
)
def test_incomplete_or_duplicate_calibration_inventory_is_rejected(corpus, mutation):
    if mutation == "missing_row":
        corpus["observations"].pop()
    elif mutation == "duplicate_row":
        corpus["observations"].append(corpus["observations"][0])
    elif mutation == "missing_label":
        corpus["expected_scores"].pop(next(iter(corpus["expected_scores"])))
    elif mutation == "unknown_case":
        corpus["observations"][0]["case_id"] = "unknown"
    else:
        corpus["cases"] = []
        corpus["observations"] = []
        corpus["expected_scores"] = {}
    with pytest.raises(ValueError):
        calibrate(corpus)


@pytest.mark.parametrize("split", ["validation", "sealed_test"])
def test_calibration_never_reads_validation_or_sealed_cases(corpus, split):
    corpus["cases"][0]["split"] = split
    with pytest.raises(ValueError, match="development"):
        calibrate(corpus)


def test_invalid_oracle_cannot_make_missing_backend_evidence_pass(corpus):
    corpus["cases"][2]["effects"] = [{"kind": "proposal", "tool": "resample_data"}]
    with pytest.raises(ValueError, match="execution"):
        calibrate(corpus)


def test_calibration_reports_false_positive_without_becoming_product_score(corpus):
    corpus["expected_scores"]["resample.pass"]["outcome"] = False
    report = calibrate(corpus)
    assert report["calibration"]["passed"] is False
    assert report["calibration"]["layers"]["outcome"]["false_positive"] == 1
    assert report["product_benchmark_score"] is None


def test_cli_preserves_manifest_hash_and_fails_on_mismatched_labels(
    corpus, tmp_path, capsys
):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")
    assert main(["--cases", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report["case_file_sha256"]) == 64
    corpus["expected_scores"]["resample.pass"]["outcome"] = False
    path.write_text(json.dumps(corpus), encoding="utf-8")
    assert main(["--cases", str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["calibration"]["passed"] is False


@pytest.mark.parametrize("text", ['{"schema":"a","schema":"b"}', '{"value":NaN}', "{}"])
def test_cli_rejects_malformed_manifest(text, tmp_path, capsys):
    path = tmp_path / "cases.json"
    path.write_text(text, encoding="utf-8")
    assert main(["--cases", str(path)]) == 2
    assert json.loads(capsys.readouterr().out)["calibration"]["passed"] is False
