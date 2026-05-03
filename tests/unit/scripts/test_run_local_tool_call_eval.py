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
