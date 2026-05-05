from __future__ import annotations

import json
from pathlib import Path

from scripts.agent.evals.run_local_tool_call_eval import (
    build_local_eval_resource_preflight,
    build_prompt_messages,
    main,
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
    assert (
        "If the latest user turn contains an explicit absolute path"
        in (messages[0]["content"])
    )
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


def test_prompt_hides_substitute_tools_when_direct_command_is_blocked():
    case = _case("wrong-tool-temptation-apply-after-epoch")
    messages = build_prompt_messages(case)

    prompt = messages[-1]["content"]
    assert "Direct workflow command for latest intent: apply_interpretation" in prompt
    assert "Direct workflow command blocked reason:" in prompt
    assert '"name": "scan_source"' not in prompt
    assert '"name": "clear_dataset"' not in prompt


def test_prompt_includes_recipe_remap_choices_for_preview():
    case = _case("recipe-preview-eeg-file-remap")
    messages = build_prompt_messages(case)

    assert "choices.eeg_file_remap" in messages[0]["content"]
    assert "choices.label_carrier_remap" in messages[0]["content"]
    assert "never as tool_name" in messages[0]["content"]
    assert '"eeg_file_remap"' in messages[-1]["content"]
    assert '"label_carrier_remap"' in messages[-1]["content"]


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


def test_blocked_requested_step_substitute_tool_fails_score():
    case = _case("empty-train-block")
    raw_output = '{"tool_name":"set_model","parameters":{"model_name":"EEGNet"}}'

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert not score.passed
    assert score.parsed_tool_calls == [
        {"tool_name": "set_model", "arguments": {"model_name": "EEGNet"}}
    ]
    assert "tool/no-tool decision mismatch" in score.failures
    assert "Generate datasets before training" in score.visible_response


def test_blocked_requested_direct_tool_is_scored_as_blocked_response():
    case = _case("wrong-tool-temptation-apply-after-epoch")
    raw_output = (
        '{"command": "apply_interpretation", '
        '"reasons": ["Reset the session before changing raw files"]}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == []
    assert "Reset the session before changing raw files" in score.visible_response


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


def test_scores_generate_dataset_missing_test_ratio_from_latest_text():
    case = _case("epoched-generate-dataset")
    raw_output = (
        '{"tool_name":"generate_dataset",'
        '"parameters":{"split_strategy":"trial",'
        '"training_mode":"individual"}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls[0]["arguments"]["test_ratio"] == 0.2


def test_scores_preview_metadata_overrides_string_map_as_choices():
    case = _case("scanned-preview-session-override")
    raw_output = (
        '{"tool_name":"preview_interpretation","parameters":{'
        '"subject":"subject-01","session":"ses-01",'
        '"metadata_overrides":{"subject":"subject-01","session":"ses-01"}}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "allowed"
    assert score.parsed_tool_calls == [
        {
            "tool_name": "preview_interpretation",
            "arguments": {"choices": {"session": "ses-01"}},
        }
    ]


def test_scores_preview_unrequested_label_review_noise_as_metadata_choice():
    case = _case("multi-turn-preview-metadata-choice")
    raw_output = (
        '{"tool_name":"preview_interpretation","parameters":{'
        '"scan_id":"latest","subject":"S02","choices":{'
        '"label_carrier":"external_file","event_role":"stimulus",'
        '"class_map":{},"anchor":"onset_seconds","granularity":"trial",'
        '"role":"class cue labels"}}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {
            "tool_name": "preview_interpretation",
            "arguments": {"choices": {"subject": "S02"}},
        }
    ]


def test_scores_preview_task_run_with_generated_prefix_noise():
    case = _case("multi-turn-preview-task-run-choice")
    raw_output = (
        '{"tool_name":"preview_interpretation","parameters":{"choices":{'
        '"label_carrier":"external_file","event_role":"stimulus",'
        '"subject":"subject1","session":"session1",'
        '"task":"task_imagery","run":"run03"}}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {
            "tool_name": "preview_interpretation",
            "arguments": {"choices": {"task": "imagery", "run": "03"}},
        }
    ]


def test_scores_command_only_json_as_tool_call_when_available():
    case = _case("previewed-safe-validate")
    raw_output = '{"command": "validate_interpretation", "reasons": []}'

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {"tool_name": "validate_interpretation", "arguments": {}}
    ]


def test_scores_recipe_eeg_file_remap_tool_call():
    case = _case("recipe-preview-eeg-file-remap")
    raw_output = (
        '{"tool_name":"preview_interpretation","parameters":{"choices":{'
        '"eeg_file_remap":{"/recipe/old_raw.fif":"/data/new_raw.fif"}}}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {
            "tool_name": "preview_interpretation",
            "arguments": {
                "choices": {
                    "eeg_file_remap": {
                        "/recipe/old_raw.fif": "/data/new_raw.fif",
                    }
                }
            },
        }
    ]


def test_scores_recipe_remap_missing_target_as_clarification():
    case = _case("recipe-preview-remap-missing-target")
    raw_output = "Please provide the saved file and the replacement remap target."

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "missing_input"
    assert score.score_breakdown["clarification_behavior"]


def test_scores_placeholder_recipe_remap_alias_tool_as_clarification():
    case = _case("recipe-preview-remap-missing-target")
    raw_output = (
        '{"tool_name":"choices.eeg_file_remap","parameters":{'
        '"saved_item":"missing saved EEG file",'
        '"replacement":"current replacement EEG file path/name"}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "missing_input"
    assert score.parsed_tool_calls == []
    assert "remap target" in score.visible_response.lower()


def test_scores_hallucinated_recipe_remap_paths_as_clarification():
    case = _case("recipe-preview-remap-missing-target")
    raw_output = (
        '{"tool_name":"preview_interpretation","parameters":{'
        '"eeg_file_remap":{"/missing/saved_eeg.fif":"/data/current_eeg.fif"}}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "missing_input"
    assert score.parsed_tool_calls == []
    assert "remap target" in score.visible_response.lower()


def test_scores_preview_with_stale_source_path_as_latest_preview():
    case = _case("multi-turn-scan-preview")
    raw_output = (
        '{"tool_name":"preview_interpretation",'
        '"parameters":{"source_path":"/data/bids_mi"}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {"tool_name": "preview_interpretation", "arguments": {}}
    ]


def test_scores_preview_with_unrequested_placeholder_choices_as_plain_preview():
    case = _case("scanned-preview-auto")
    raw_output = (
        '{"tool":"preview_interpretation","parameters":{"choices":{'
        '"subject":"subject_id","session":"session_id","task":"task_id",'
        '"run":"run_id",'
        '"eeg_file_remap":{"/recipe/old_raw.fif":"/data/current_raw.fif"},'
        '"label_carrier_remap":{"/recipe/events.tsv":"/data/events.tsv"},'
        '"required_label_carriers":["/data/label1.tsv","/data/label2.tsv"]'
        "}}}"
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "allowed"
    assert score.parsed_tool_calls == [
        {"tool_name": "preview_interpretation", "arguments": {}}
    ]


def test_scores_policy_reason_subset_as_blocked_command_handling():
    case = _case("zh-blocked-train-empty")
    raw_output = '{"reason":"Load raw data before training.","action":"No tool call"}'

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "blocked"
    assert score.parsed_tool_calls == []


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


def test_resource_preflight_blocks_full_local_gate_under_vram_pressure():
    preflight = build_local_eval_resource_preflight(
        model_id="microsoft/Phi-3.5-mini-instruct",
        model_role="fallback",
        repeat_count=3,
        case_ids=None,
        case_limit=None,
        cache_dir="/tmp/xbrainlab-models",
        cache_usage_bytes_value=0,
        available_disk_bytes_value=100_000_000_000,
        gpu_snapshot={
            "available": True,
            "index": 0,
            "name": "RTX 5070 Ti",
            "total_mib": 16_384,
            "used_mib": 16_152,
            "free_mib": 232,
        },
    )

    assert preflight["ok"] is False
    assert preflight["resource_pressure"] == "high"
    assert preflight["full_local_gate"] is True
    assert "full local" in preflight["message"]


def test_resource_preflight_allows_changed_case_gate_under_vram_pressure():
    preflight = build_local_eval_resource_preflight(
        model_id="microsoft/Phi-3.5-mini-instruct",
        model_role="fallback",
        eval_gate="candidate",
        repeat_count=1,
        case_ids=["empty-scan-source-folder"],
        case_limit=None,
        cache_dir="/tmp/xbrainlab-models",
        cache_usage_bytes_value=0,
        available_disk_bytes_value=100_000_000_000,
        gpu_snapshot={
            "available": True,
            "index": 0,
            "name": "RTX 5070 Ti",
            "total_mib": 16_384,
            "used_mib": 16_152,
            "free_mib": 232,
        },
    )

    assert preflight["ok"] is True
    assert preflight["resource_pressure"] == "high"
    assert preflight["full_local_gate"] is False
    assert preflight["selected_cases"] == 1


def test_resource_preflight_requires_release_gate_for_full_suite_x3():
    preflight = build_local_eval_resource_preflight(
        model_id="microsoft/Phi-3.5-mini-instruct",
        model_role="fallback",
        eval_gate="candidate",
        repeat_count=3,
        case_ids=None,
        case_limit=None,
        cache_dir="/tmp/xbrainlab-models",
        cache_usage_bytes_value=0,
        available_disk_bytes_value=100_000_000_000,
        gpu_snapshot={
            "available": True,
            "index": 0,
            "name": "RTX 5070 Ti",
            "total_mib": 16_384,
            "used_mib": 1_024,
            "free_mib": 15_360,
        },
    )

    assert preflight["ok"] is False
    assert preflight["eval_gate"] == "candidate"
    assert preflight["resource_pressure"] == "normal"
    assert preflight["full_local_gate"] is True
    assert "release/thesis" in preflight["message"]


def test_cli_writes_preflight_artifact_and_aborts_full_fallback(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval._collect_gpu_memory_snapshot",
        lambda: {
            "available": True,
            "index": 0,
            "name": "RTX 5070 Ti",
            "total_mib": 16_384,
            "used_mib": 16_152,
            "free_mib": 232,
        },
    )
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval.cache_usage_bytes",
        lambda _cache_dir: 0,
    )
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval.available_disk_bytes",
        lambda _cache_dir: 100_000_000_000,
    )
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval.run_local_eval",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("local eval should not start under pressure"),
        ),
    )

    exit_code = main(
        [
            "--model-role",
            "fallback",
            "--repeat-count",
            "3",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert exit_code == 2
    artifact = tmp_path / "resource_preflight.json"
    assert artifact.exists()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["resource_pressure"] == "high"


def test_cli_requires_explicit_release_gate_before_full_local_x3(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval._collect_gpu_memory_snapshot",
        lambda: {
            "available": True,
            "index": 0,
            "name": "RTX 5070 Ti",
            "total_mib": 16_384,
            "used_mib": 1_024,
            "free_mib": 15_360,
        },
    )
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval.cache_usage_bytes",
        lambda _cache_dir: 0,
    )
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval.available_disk_bytes",
        lambda _cache_dir: 100_000_000_000,
    )
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval.run_local_eval",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("local eval should require an explicit release gate"),
        ),
    )

    exit_code = main(
        [
            "--model-role",
            "fallback",
            "--repeat-count",
            "3",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert exit_code == 2
    artifact = tmp_path / "resource_preflight.json"
    assert artifact.exists()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["eval_gate"] == "candidate"
    assert "release/thesis" in payload["message"]
