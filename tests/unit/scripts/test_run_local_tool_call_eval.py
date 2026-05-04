from __future__ import annotations

import json
from pathlib import Path

from scripts.agent.evals.run_local_tool_call_eval import (
    build_prompt_messages,
    prediction_from_model_output,
    run_local_eval,
    score_local_case,
    write_local_artifacts,
)
from scripts.agent.evals.run_tool_call_eval import build_eval_cases


def _case(case_id: str):
    return next(case for case in build_eval_cases() if case.case_id == case_id)


def test_prompt_includes_available_tools_and_blocked_reasons():
    case = _case("empty-scan-source-folder")
    messages = build_prompt_messages(case)

    prompt = messages[-1]["content"]
    assert "scan_source" in prompt
    assert "start_training" not in prompt
    assert "Generate datasets before training" in prompt
    assert "Never invent placeholder paths" in messages[0]["content"]
    assert "do not call a different tool" in messages[0]["content"]
    assert "apply_standard_preprocess for" in messages[0]["content"]
    assert "training_mode values" in messages[0]["content"]
    assert (
        "Data Interpretation is the primary data entry workflow"
        in messages[0]["content"]
    )
    assert "legacy direct-load and label-attach paths" in messages[0]["content"]
    assert "Inferred latest user intent: scan_source" in prompt
    assert "Direct workflow command for latest intent: scan_source" in prompt
    assert '"taxonomy": "Data Interpretation"' in prompt
    assert '"additionalProperties": false' in prompt


def test_scores_local_tool_call_output():
    case = _case("empty-scan-source-folder")
    raw_output = (
        '{"tool_name":"scan_source","parameters":{"source_path":"/datasets/bci_iv_2a"}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {
            "tool_name": "scan_source",
            "arguments": {"source_path": "/datasets/bci_iv_2a"},
        }
    ]
    assert "tool_name" not in score.visible_response
    assert score.score_breakdown["local_llm_reliability"]


def test_scores_missing_input_text_as_repair():
    case = _case("empty-scan-source-missing-path")
    raw_output = "Please provide the source path before scanning."

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "missing_input"
    assert score.parsed_tool_calls == []


def test_blocked_text_is_not_scored_as_missing_input():
    case = _case("empty-preview-before-scan-block")
    raw_output = (
        "The preview step is blocked because you must scan a data source before "
        "previewing interpretation."
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "blocked"


def test_placeholder_tool_argument_is_scored_as_missing_input():
    case = _case("empty-scan-source-missing-path")
    raw_output = (
        '{"tool_name":"scan_source","parameters":{"source_path":"path_to_eeg_dataset"}}'
    )

    prediction = prediction_from_model_output(case, raw_output)

    assert prediction.tool_calls == []
    assert prediction.asks_clarification
    assert "actual path" in prediction.blocked_reason


def test_blocked_requested_step_rejects_substitute_tool():
    case = _case("empty-train-block")
    raw_output = '{"tool_name":"set_model","parameters":{"model_name":"EEGNet"}}'

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == []
    assert "Generate datasets before training" in score.visible_response


def test_generate_dataset_default_val_ratio_is_counted():
    case = _case("epoched-generate-dataset")
    raw_output = (
        '{"tool_name":"generate_dataset",'
        '"parameters":{"split_strategy":"trial",'
        '"training_mode":"individual","test_ratio":0.2}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls[0]["arguments"]["val_ratio"] == 0.2


def test_scores_command_only_json_as_tool_call_when_available():
    case = _case("previewed-safe-validate")
    raw_output = '{"command": "validate_interpretation", "reasons": []}'

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {"tool_name": "validate_interpretation", "arguments": {}}
    ]


def test_scores_latest_turn_intent_not_joined_history():
    case = _case("multi-turn-validate-apply-safe")
    raw_output = '{"tool_name":"apply_interpretation","parameters":{}}'

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.prediction["intent"] == "apply_interpretation"


def test_scores_backend_result_interpretation_for_success_summary():
    case = _case("successful-load-summary")
    raw_output = '{"tool_name":"load_data","parameters":{"paths":["/data/S03.fif"]}}'

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.prediction["result_interpretation"] == "success_summary"


def test_scores_blocked_text_with_backend_policy_reason():
    case = _case("validated-blocked-apply-block")
    raw_output = (
        'The command "apply_interpretation" is blocked due to missing label '
        "carriers. Please load raw data first."
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert "Interpretation is blocked" in score.visible_response


def test_scores_missing_recipe_path_with_path_label():
    case = _case("empty-reload-recipe-missing-path")
    raw_output = '{"tool_name":"reload_interpretation_recipe","parameters":{}}'

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert "recipe path" in score.visible_response


def test_scores_relative_scan_source_as_missing_input():
    case = _case("empty-scan-source-relative-missing")
    raw_output = (
        '{"tool_name":"scan_source","parameters":{"source_path":"data/session01"}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "missing_input"
    assert "source path" in score.visible_response


def test_scores_visualization_ui_route_as_service_summary():
    case = _case("visualize-before-trained-block")
    raw_output = (
        '{"tool_name":"switch_panel","parameters":{"panel_name":"visualization"}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == []
    assert score.prediction["result_interpretation"] == "service_query_summary"


def test_scores_saliency_setup_tool_as_service_summary():
    case = _case("dataset-saliency-readiness-summary")
    raw_output = '{"tool_name":"set_model","parameters":{"model_name":"EEGNet"}}'

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == []
    assert score.prediction["result_interpretation"] == "service_query_summary"


def test_scores_saliency_tool_name_as_service_summary():
    case = _case("dataset-saliency-readiness-summary")
    raw_output = '{"tool_name":"saliency","parameters":{}}'

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == []
    assert score.prediction["result_interpretation"] == "service_query_summary"


def test_scores_chinese_missing_input_and_no_call_cases():
    missing = _case("zh-scan-missing-source")
    missing_score = score_local_case(
        missing,
        ["請提供資料來源路徑後, 我才能掃描。"] * 3,
    )

    assert missing_score.passed
    assert missing_score.score_breakdown["clarification_behavior"]

    no_tool = _case("no-tool-what-is-epoch")
    no_tool_score = score_local_case(
        no_tool,
        ["Epoch 是圍繞事件切出的 EEG 時間窗。"] * 3,
    )

    assert no_tool_score.passed
    assert no_tool_score.score_breakdown["tool_or_no_tool_decision"]
    assert no_tool_score.verification_result == "no_tool"


def test_scores_json_clarification_as_missing_input_without_visible_syntax():
    case = _case("zh-ambiguous-workflow-clarification")
    raw_output = (
        '{"tool_name": "ask_clarification", '
        '"parameters": "Could you please specify the data step?"}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "missing_input"
    assert "tool_name" not in score.visible_response


def test_scores_only_first_tool_call():
    case = _case("query-state-empty")
    raw_output = (
        '{"command":"query_state","reasons":[]}\n'
        '{"command":"configure_training","reasons":["not the selected tool"]}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {"tool_name": "query_state", "arguments": {"query": "state"}}
    ]


def test_run_local_eval_with_fake_generator_and_writes_artifacts(tmp_path: Path):
    def fake_generator(messages: list[dict[str, str]]) -> str:
        assert messages
        return (
            '{"tool_name":"scan_source",'
            '"arguments":{"source_path":"/datasets/bci_iv_2a"}}'
        )

    result = run_local_eval(
        model_id="microsoft/Phi-4-mini-instruct",
        repeat_count=3,
        case_ids=["empty-scan-source-folder"],
        generator=fake_generator,
    )
    json_path, md_path = write_local_artifacts(result, tmp_path)

    assert result["runner"] == "local-llm"
    assert result["summary"]["failed_cases"] == 0
    assert result["exploratory"] is True
    assert json_path.exists()
    assert md_path.exists()
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["cases"][0]["runs"][0]["parsed_tool_calls"] == [
        {
            "tool_name": "scan_source",
            "arguments": {"source_path": "/datasets/bci_iv_2a"},
        }
    ]
    assert saved["cases"][0]["runs"][0]["schema_verification"] == [
        {"tool_name": "scan_source", "is_valid": True, "error_message": None}
    ]
    assert "XBrainLab Local Tool-Call Eval" in md_path.read_text(encoding="utf-8")
