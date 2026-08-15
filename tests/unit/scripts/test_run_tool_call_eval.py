from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from scripts.agent.evals.run_tool_call_eval import (
    RAW_MODEL_DECISION_SCORE_SCOPE,
    EvalCase,
    ExpectedToolCall,
    PredictedToolCall,
    Prediction,
    build_deterministic_eval_gate_preflight,
    build_eval_cases,
    expected_decision_verification_result_for,
    main,
    predict_case,
    run_eval,
    score_case,
    summarize_scores,
    verification_result_for,
)
from XBrainLab.backend.application import CommandName
from XBrainLab.llm.agent.intent import resolve_blocked_explanation_intent


def test_run_eval_filters_by_case_id() -> None:
    result = run_eval(repeat_count=1, case_ids=["empty-load-path"])

    assert result["summary"]["total_cases"] == 1
    assert result["repeat_count"] == 1
    assert result["selected_case_ids"] == ["empty-load-path"]
    assert "data_interpretation" in result["selected_case_families"]
    assert result["exploratory"] is True
    assert result["summary"]["failed_cases"] == 0


def test_fast_gate_blocks_full_suite_default(tmp_path: Path) -> None:
    exit_code = main(["--output-dir", str(tmp_path)])

    assert exit_code == 2
    gate_artifact = tmp_path / "deterministic_gate.json"
    assert gate_artifact.exists()
    payload = json.loads(gate_artifact.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["eval_gate"] == "fast"
    assert payload["full_suite"] is True
    assert not (tmp_path / "latest.json").exists()


def test_fast_gate_allows_case_subset(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--output-dir",
            str(tmp_path),
            "--case-id",
            "empty-load-path",
        ],
    )

    assert exit_code == 0
    payload = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert payload["eval_gate"] == "fast"
    assert payload["summary"]["total_cases"] == 1
    assert payload["repeat_count"] == 1
    assert payload["selected_case_ids"] == ["empty-load-path"]


def test_release_gate_allows_full_suite_repeat_two() -> None:
    preflight = build_deterministic_eval_gate_preflight(
        eval_gate="release",
        repeat_count=2,
    )

    assert preflight["ok"] is True
    assert preflight["full_suite"] is True


def test_case_limit_zero_is_rejected() -> None:
    try:
        run_eval(repeat_count=1, case_limit=0)
    except ValueError as exc:
        assert "No eval cases selected" in str(exc)
    else:
        raise AssertionError("Expected empty deterministic eval selection to fail")


def test_strict_candidate_contract_uses_actionable_blocker_and_explicit_split() -> None:
    cases = {case.case_id: case for case in build_eval_cases()}

    train = cases["empty-train-block"]
    assert train.expected_reason_terms == ["load", "training"]

    dataset = cases["epoched-generate-dataset"]
    assert "trial-wise" in dataset.user_turns[-1]
    assert dataset.expected_tools[0].arguments == {
        "test_ratio": 0.2,
        "training_mode": "individual",
        "split_strategy": "trial",
    }


def test_epoch_cases_without_user_bounds_require_missing_input() -> None:
    cases = {case.case_id: case for case in build_eval_cases()}

    for case_id in (
        "preprocessed-epoch-default-window",
        "multi-turn-preprocessed-create-epoch",
        "zh-epoch-domain-phrasing",
    ):
        case = cases[case_id]
        assert case.expected_tools == []
        assert case.expected_blocked is True
        assert case.expected_verification_result == "missing_input"
        assert case.expected_missing_inputs == ("epoch_window",)
        assert "epoch window" in " ".join(case.expected_reason_terms).lower()


def test_missing_input_cases_name_exact_machine_readable_fields() -> None:
    cases = {case.case_id: case for case in build_eval_cases()}

    assert cases["empty-load-missing-path"].expected_missing_inputs == ("source_path",)
    assert cases[
        "epoched-generate-dataset-missing-strategy"
    ].expected_missing_inputs == ("split_strategy",)
    assert cases["empty-reload-recipe-missing-path"].expected_missing_inputs == (
        "recipe_path",
    )
    assert cases["recipe-preview-remap-missing-target"].expected_missing_inputs == (
        "eeg_file_remap",
    )


def test_state_questions_are_answer_cases_without_unpublished_query_tool() -> None:
    cases = {case.case_id: case for case in build_eval_cases()}

    for case_id in (
        "query-state-trained",
        "multi-turn-query-after-training-ready",
        "query-state-empty",
        "multi-turn-query-after-apply",
    ):
        case = cases[case_id]
        assert case.expected_intent == "no_tool"
        assert case.expected_tools == []
        assert case.expected_verification_result == "no_tool"


def test_reset_requests_are_blocked_without_exposing_the_retired_tool() -> None:
    cases = {case.case_id: case for case in build_eval_cases()}

    for case_id in (
        "reset-request-confirmation",
        "training-ready-reset-confirmation",
        "zh-reset-confirmation",
    ):
        case = cases[case_id]
        prediction = predict_case(case)

        assert case.expected_intent == "reset_session"
        assert case.expected_tools == []
        assert case.expected_blocked is True
        assert case.expected_confirmation_required is False
        assert prediction.intent == "reset_session"
        assert prediction.tool_calls == []
        assert prediction.blocked is True
        assert prediction.confirmation_required is False
        assert "not available from the interface or Assistant" in (
            prediction.final_message
        )
        assert "No session state was changed" in prediction.final_message


def test_blocked_workflow_question_keeps_target_intent_without_calling_tool() -> None:
    case = {case.case_id: case for case in build_eval_cases()}[
        "no-tool-why-train-blocked"
    ]

    resolution = resolve_blocked_explanation_intent(case.user_turns[-1])

    assert resolution is not None
    assert resolution.target_intent == "train"
    assert resolution.target_command is CommandName.TRAIN
    assert case.expected_intent == "no_tool"
    assert case.expected_tools == []
    assert case.expected_verification_result == "no_tool"

    prediction = predict_case(case)

    assert prediction.intent == "no_tool"
    assert prediction.tool_calls == []
    assert prediction.blocked is False
    assert prediction.response_decision == "answer"
    assert verification_result_for(prediction) == "no_tool"


def test_visualization_and_saliency_requests_expect_the_published_direct_tool() -> None:
    cases = {case.case_id: case for case in build_eval_cases()}
    expected = {
        "saliency-before-trained-block": "saliency",
        "visualize-before-trained-block": "visualize",
        "trained-visualize-ready-summary": "visualize",
        "trained-saliency-ready-summary": "saliency",
        "dataset-saliency-readiness-summary": "saliency",
        "zh-saliency-domain-phrasing": "saliency",
    }

    for case_id, tool_name in expected.items():
        assert cases[case_id].expected_tools == [ExpectedToolCall(tool_name, {})]


def test_argument_metric_excludes_no_tool_and_wrong_selection_denominators() -> None:
    no_tool_case = EvalCase(
        case_id="answer",
        title="Answer without a tool",
        state_name="empty",
        user_turns=["What is an epoch?"],
        expected_intent="no_tool",
        expected_verification_result="no_tool",
    )
    wrong_tool_case = EvalCase(
        case_id="wrong-tool",
        title="Wrong selected tool",
        state_name="empty",
        user_turns=["Scan /data/session"],
        expected_intent="scan_source",
        expected_tools=[
            ExpectedToolCall("scan_source", {"source_path": "/data/session"})
        ],
    )
    correct_tool_wrong_args_case = EvalCase(
        case_id="wrong-args",
        title="Correct tool with wrong arguments",
        state_name="empty",
        user_turns=["Scan /data/session"],
        expected_intent="scan_source",
        expected_tools=[
            ExpectedToolCall("scan_source", {"source_path": "/data/session"})
        ],
    )
    scores = [
        score_case(
            no_tool_case,
            [Prediction(intent="no_tool", tool_calls=[])],
            score_scope=RAW_MODEL_DECISION_SCORE_SCOPE,
        ),
        score_case(
            wrong_tool_case,
            [
                Prediction(
                    intent="scan_source",
                    tool_calls=[
                        PredictedToolCall("list_files", {"directory": "/data"})
                    ],
                )
            ],
            score_scope=RAW_MODEL_DECISION_SCORE_SCOPE,
        ),
        score_case(
            correct_tool_wrong_args_case,
            [
                Prediction(
                    intent="scan_source",
                    tool_calls=[
                        PredictedToolCall(
                            "scan_source",
                            {"source_path": "/data/other"},
                        )
                    ],
                )
            ],
            score_scope=RAW_MODEL_DECISION_SCORE_SCOPE,
        ),
    ]

    summary = summarize_scores(scores)

    assert scores[0].dimension_applicability["tool_selection"] is False
    assert scores[0].dimension_applicability["argument_correctness"] is False
    assert scores[1].dimension_applicability["tool_selection"] is True
    assert scores[1].dimension_applicability["argument_correctness"] is False
    assert scores[2].dimension_applicability["argument_correctness"] is True
    assert summary["dimension_metrics"]["tool_selection"]["applicable_cases"] == 2
    assert summary["dimension_metrics"]["argument_correctness"] == {
        "accuracy": 0.0,
        "applicable_cases": 1,
        "excluded_cases": 2,
        "status": "partial",
    }


def test_missing_input_decision_does_not_depend_on_case_id_wording() -> None:
    case = next(
        case
        for case in build_eval_cases()
        if case.case_id == "epoched-generate-dataset-missing-strategy"
    )
    renamed = replace(
        case,
        case_id="dataset-choice-required",
        expected_verification_result=None,
    )

    assert expected_decision_verification_result_for(renamed) == "missing_input"


def test_blocked_paraphrase_and_continue_mode_cases_cover_substitution_boundary() -> (
    None
):
    cases = {case.case_id: case for case in build_eval_cases()}
    blocked_ids = {
        "empty-preprocess-block-paraphrase",
        "loaded-create-epoch-block-paraphrase",
        "loaded-generate-dataset-block-paraphrase",
        "dataset-train-missing-config-paraphrase",
        "workflow-continue-loaded-epoch-block",
    }

    for case_id in blocked_ids:
        case = cases[case_id]
        assert case.expected_blocked
        assert case.expected_tools == []

    assert cases["workflow-continue-empty-scan"].workflow_mode == (
        "continue_until_decision"
    )
    assert cases["workflow-continue-empty-scan"].expected_tools[0].tool_name == (
        "scan_source"
    )
    assert cases["workflow-continue-loaded-epoch-block"].workflow_mode == (
        "continue_until_decision"
    )
