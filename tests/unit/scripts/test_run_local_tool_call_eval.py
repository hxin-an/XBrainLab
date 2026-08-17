from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts.agent.evals.run_local_tool_call_eval import (
    PHI4_DECISION_DEVELOPMENT_CASE_IDS,
    PHI4_DECISION_HELD_OUT_CASE_IDS,
    _available_tool_schemas,
    _primary_prompt_state_snapshot,
    _resolve_case_suite_ids,
    build_local_eval_cli_gate,
    build_local_eval_resource_preflight,
    build_prompt_messages,
    configure_strict_generation_constraints,
    main,
    prediction_from_model_output,
    raw_prediction_from_model_output,
    run_local_eval,
    score_host_assisted_local_case,
    score_local_case,
    write_local_artifacts,
)
from scripts.agent.evals.run_tool_call_eval import ExpectedToolCall, build_eval_cases
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.prompt_policy import DIRECT_ACTION_TOOL_NAMES
from XBrainLab.llm.core.model_catalog import PRIMARY_LOCAL_MODEL_ID


def _case(case_id: str):
    return next(case for case in build_eval_cases() if case.case_id == case_id)


def test_phi4_decision_case_suites_are_disjoint_and_resolve_existing_cases():
    known_case_ids = {case.case_id for case in build_eval_cases()}

    assert len(PHI4_DECISION_DEVELOPMENT_CASE_IDS) == 12
    assert len(PHI4_DECISION_HELD_OUT_CASE_IDS) == 7
    assert set(PHI4_DECISION_DEVELOPMENT_CASE_IDS).isdisjoint(
        PHI4_DECISION_HELD_OUT_CASE_IDS
    )
    assert set(PHI4_DECISION_DEVELOPMENT_CASE_IDS) <= known_case_ids
    assert set(PHI4_DECISION_HELD_OUT_CASE_IDS) <= known_case_ids


def test_named_case_suite_cannot_be_combined_with_explicit_case_ids():
    with pytest.raises(ValueError, match="cannot be combined"):
        _resolve_case_suite_ids(
            case_suite="held-out",
            case_ids=["empty-train-block"],
        )

    assert _resolve_case_suite_ids(
        case_suite="development",
        case_ids=None,
    ) == list(PHI4_DECISION_DEVELOPMENT_CASE_IDS)
    assert _resolve_case_suite_ids(
        case_suite="held-out",
        case_ids=None,
    ) == list(PHI4_DECISION_HELD_OUT_CASE_IDS)
    assert _resolve_case_suite_ids(
        case_suite="all",
        case_ids=["empty-train-block"],
    ) == ["empty-train-block"]


def test_direct_action_taxonomy_covers_every_benchmark_tool():
    mapped_tools = {
        tool_name
        for tool_names in DIRECT_ACTION_TOOL_NAMES.values()
        for tool_name in tool_names
    }
    expected_tools = {
        call.tool_name for case in build_eval_cases() for call in case.expected_tools
    }

    assert expected_tools <= mapped_tools


def test_every_expected_tool_is_exposed_in_the_case_prompt_state() -> None:
    model_tools = AGENT_ACTION_CONTRACTS.model_tool_names()
    for case in build_eval_cases():
        exposed = {
            str(tool["name"]) for tool in _available_tool_schemas(case.state_name)
        }
        expected = {call.tool_name for call in case.expected_tools}
        expected_model_tools = expected & model_tools
        expected_runtime_only_tools = expected - model_tools

        assert expected_model_tools <= exposed, (
            f"{case.case_id} expects unexposed model tools: "
            f"{sorted(expected_model_tools - exposed)}"
        )
        assert expected_runtime_only_tools.isdisjoint(exposed)


def test_local_eval_catalog_uses_canonical_model_facing_projection() -> None:
    model_tools = AGENT_ACTION_CONTRACTS.model_tool_names()
    unpublished = AGENT_ACTION_CONTRACTS.tool_names() - model_tools
    exposed: set[str] = set()

    for case in build_eval_cases():
        exposed.update(
            str(tool["name"]) for tool in _available_tool_schemas(case.state_name)
        )

    assert exposed - {"respond_to_user"} <= model_tools
    assert "respond_to_user" in exposed
    assert "switch_panel" in exposed
    assert exposed.isdisjoint(unpublished)


def test_training_ready_state_exposes_start_only_after_deferred_split_is_saved():
    state = _primary_prompt_state_snapshot("training_ready")
    exposed = {str(tool["name"]) for tool in _available_tool_schemas("training_ready")}
    missing_config_exposed = {
        str(tool["name"])
        for tool in _available_tool_schemas("dataset_without_training_config")
    }

    assert state["dataset"] == {
        "available": False,
        "count": 0,
        "split_spec_saved": True,
        "split_materialized": False,
    }
    assert "start_training" in exposed
    assert "start_training" not in missing_config_exposed


def test_primary_prompt_includes_state_enabled_tools_without_answer_fields():
    case = _case("empty-scan-source-folder")
    messages = build_prompt_messages(case)

    prompt = messages[-1]["content"]
    assert "scan_source" in prompt
    assert "start_training" not in prompt
    assert "Never invent placeholder paths" in messages[0]["content"]
    assert (
        "If the latest user turn contains an explicit absolute path"
        in (messages[0]["content"])
    )
    assert "do not call a different tool" in messages[0]["content"]
    assert (
        "Data Interpretation is the primary data entry workflow"
        in messages[0]["content"]
    )
    assert "legacy direct-load and label-attach paths" in messages[0]["content"]
    assert "Inferred latest user intent" not in prompt
    assert "Direct workflow command" not in prompt
    assert "Blocked commands and reasons" not in prompt
    assert '"taxonomy": "Data Interpretation"' in prompt
    assert '"name": "respond_to_user"' in prompt
    assert '"oneOf": [' in prompt
    assert '"const": "blocked"' in prompt
    assert '"const": "missing_input"' in prompt
    assert '"const": "answer"' in prompt
    assert '"additionalProperties": false' in prompt
    assert "Do not call it as a prerequisite or substitute" in prompt


def test_primary_prompt_uses_product_stage_tools_and_excludes_legacy_routes():
    empty_messages = build_prompt_messages(_case("empty-load-path"))
    loaded_messages = build_prompt_messages(_case("loaded-preprocess"))
    empty_prompt = empty_messages[-1]["content"]
    loaded_prompt = loaded_messages[-1]["content"]

    assert '"name": "scan_source"' in empty_prompt
    assert '"name": "load_data"' not in empty_prompt
    assert '"name": "set_model"' not in empty_prompt
    assert '"name": "configure_training"' not in empty_prompt
    assert '"name": "apply_standard_preprocess"' in loaded_prompt
    assert '"name": "load_data"' not in loaded_prompt
    assert '"name": "attach_labels"' not in loaded_prompt
    assert '"name": "set_model"' not in loaded_prompt


def test_primary_prompt_defines_model_owned_discriminated_decision_contract():
    messages = build_prompt_messages(_case("empty-train-block"))
    system = messages[0]["content"]

    assert "DECISION ORDER" in system
    assert "exact requested action" in system
    assert "one DECISION ENVELOPE" in system
    assert 'root object must be exactly {"tool_name"' in system
    assert "missing_inputs" in system
    assert '"decision":"blocked"' in system
    assert '"decision":"answer"' in system
    assert "intent" not in system.lower()
    assert "Never call a prerequisite or substitute" in system
    assert "Broad workflow continuation" in system
    assert "PLAIN TEXT mode" not in system


@pytest.mark.parametrize(
    ("case_id", "expected_stage"),
    [
        ("empty-load-path", "empty"),
        ("loaded-preprocess", "data_loaded"),
        ("preprocessed-create-epoch", "preprocessed"),
        ("epoched-generate-dataset", "epoch_ready"),
        ("dataset-set-model", "dataset_ready"),
    ],
)
def test_primary_prompt_uses_backend_pipeline_stage_contract(
    case_id: str,
    expected_stage: str,
):
    prompt = build_prompt_messages(_case(case_id))[-1]["content"]

    assert f'"pipeline_stage": "{expected_stage}"' in prompt


def test_primary_prompt_distinguishes_recommendation_from_requested_action():
    prompt = build_prompt_messages(_case("empty-preprocess-block"))[-1]["content"]

    assert '"workflow_mode": "step_by_step"' in prompt
    assert '"broad_continuation": null' in prompt
    assert '"recommended_next_step"' not in prompt
    assert '"decision_needed"' not in prompt
    assert '"action_policy":' in prompt
    assert '"request_category": "preprocess"' in prompt
    assert '"status": "blocked"' in prompt
    assert "Load raw data before preprocessing." in prompt
    assert '"unavailable_operations"' not in prompt
    assert '"operation_labels_are_tool_names"' not in prompt


def test_primary_prompt_publishes_state_only_contracts_and_blockers():
    prompts = {
        case_id: build_prompt_messages(_case(case_id))[-1]["content"]
        for case_id in (
            "empty-load-path",
            "empty-preprocess-block",
            "empty-train-block",
        )
    }

    state_contexts = {
        case_id: prompt.split(
            "\n\nEarlier user-authored turns (context only):\n",
            maxsplit=1,
        )[0]
        for case_id, prompt in prompts.items()
    }
    assert len(set(state_contexts.values())) == 1
    context = next(iter(state_contexts.values()))
    assert '"name": "scan_source"' in context
    assert '"action_policy":' in context
    assert '"request_category": "scan source"' in context
    assert '"callable_tool_names": ["scan_source"]' in context
    assert "Load raw data before preprocessing." in context
    assert "Preprocess data before creating EEG epochs." in context
    assert "Create EEG epochs before building the training dataset." in context
    assert "Load raw data before training." in context
    assert '"unavailable_operations"' not in context


def test_primary_prompt_publishes_continue_mode_without_host_intent_hint():
    prompt = build_prompt_messages(_case("workflow-continue-empty-scan"))[-1]["content"]

    assert '"workflow_mode": "continue_until_decision"' in prompt
    assert '"broad_continuation":' in prompt
    assert '"allowed": false' in prompt
    assert "Inferred latest user intent" not in prompt
    assert "Direct workflow command" not in prompt


def test_primary_prompt_does_not_bias_decisions_with_a_concrete_tool_example():
    messages = build_prompt_messages(_case("epoched-generate-dataset"))

    assert messages[-1]["role"] == "user"
    assert "Earlier user-authored turns (context only):" in messages[-1]["content"]
    assert "Latest user-authored request (authoritative):" in (messages[-1]["content"])
    assert len(messages) == 2
    assert messages[1]["role"] == "user"
    assert "FORMAT EXAMPLE ONLY" not in messages[0]["content"]
    assert "list_files is enabled" not in messages[0]["content"]


def test_primary_prompt_separates_latest_turn_from_earlier_context():
    prompt = build_prompt_messages(_case("multi-turn-load-recovery"))[-1]["content"]

    assert 'Earlier user-authored turns (context only):\n["Load my EEG file."]' in (
        prompt
    )
    assert 'Latest user-authored request (authoritative):\n"Use /data/S02.edf"' in (
        prompt
    )
    assert prompt.count("/data/S02.edf") == 1


def test_huggingface_generator_constrains_fences_and_placeholder_paths():
    class _Tokenizer:
        @staticmethod
        def encode(text: str, *, add_special_tokens: bool) -> list[int]:
            assert add_special_tokens is False
            canonical = {
                "`": [63],
                "```": [168394],
                " ```": [101822],
                "/absolute/path": [200, 201],
                "/absolute": [210, 211],
                "/absolute/": [208, 209],
                "/path/to": [202, 203],
                "user_provided_path": [204, 205],
                "example_path": [206, 207],
            }
            if text in canonical:
                return canonical[text]
            for prefix, prefix_token in (('"', 301), (" ", 302), ('": "', 303)):
                if text.startswith(prefix) and text[len(prefix) :] in canonical:
                    return [prefix_token, *canonical[text[len(prefix) :]][1:]]
            raise KeyError(text)

    generation_config = SimpleNamespace(bad_words_ids=[[7]])
    engine = SimpleNamespace(
        active_backend=SimpleNamespace(
            tokenizer=_Tokenizer(),
            model=SimpleNamespace(generation_config=generation_config),
        )
    )

    report = configure_strict_generation_constraints(engine)

    assert report["mode"] == "hf_lexical_constraint"
    assert report["raw_output_postprocessed"] is False
    assert report["blocked_token_ids"] == [63, 101822, 168394]
    assert report["blocked_phrases"] == [
        "`",
        "```",
        " ```",
        "/absolute/path",
        "/absolute",
        "/absolute/",
        "/path/to",
        "user_provided_path",
        "example_path",
    ]
    assert generation_config.bad_words_ids == [
        [7],
        [63],
        [168394],
        [101822],
        [200, 201],
        [301, 201],
        [302, 201],
        [303, 201],
        [210, 211],
        [301, 211],
        [302, 211],
        [303, 211],
        [208, 209],
        [301, 209],
        [302, 209],
        [303, 209],
        [202, 203],
        [301, 203],
        [302, 203],
        [303, 203],
        [204, 205],
        [301, 205],
        [302, 205],
        [303, 205],
        [206, 207],
        [301, 207],
        [302, 207],
        [303, 207],
    ]


def test_generation_constraint_falls_back_when_backend_has_no_hf_generation_config():
    report = configure_strict_generation_constraints(
        SimpleNamespace(active_backend=object())
    )

    assert report == {
        "mode": "bounded_recovery_only",
        "raw_output_postprocessed": False,
        "blocked_token_ids": [],
        "blocked_phrases": [],
    }


def test_primary_prompt_does_not_read_evaluator_expected_answer_fields():
    base = _case("empty-scan-source-folder")
    poisoned = replace(
        base,
        expected_intent="EVALUATOR_INTENT_SENTINEL",
        expected_tools=[
            ExpectedToolCall(
                "EVALUATOR_EXPECTED_TOOL_SENTINEL",
                {"answer": "EVALUATOR_ARGUMENT_SENTINEL"},
            )
        ],
        expected_blocked=True,
        expected_reason_terms=["EVALUATOR_BLOCKED_REASON_SENTINEL"],
    )

    base_messages = build_prompt_messages(base)
    poisoned_messages = build_prompt_messages(poisoned)
    combined = "\n".join(message["content"] for message in poisoned_messages)

    assert base_messages == poisoned_messages
    assert "EVALUATOR_INTENT_SENTINEL" not in combined
    assert "EVALUATOR_EXPECTED_TOOL_SENTINEL" not in combined
    assert "EVALUATOR_ARGUMENT_SENTINEL" not in combined
    assert "EVALUATOR_BLOCKED_REASON_SENTINEL" not in combined


def test_primary_prompt_uses_state_decision_context_without_case_expected_fields():
    case = _case("empty-train-block")

    combined = "\n".join(message["content"] for message in build_prompt_messages(case))

    assert "Backend workflow decision context" in combined
    assert '"broad_continuation": null' in combined
    assert '"recommended_next_step"' not in combined
    assert "CURRENT WORKFLOW STAGE GUIDANCE" not in combined
    assert "Direct workflow command blocked reason" not in combined


def test_primary_prompt_uses_canonical_training_intent_with_distinct_tools():
    prompt = build_prompt_messages(_case("dataset-set-model"))[-1]["content"]

    assert '"name": "set_model"' in prompt
    assert '"name": "configure_training"' in prompt
    assert '"request_category": "configure training"' in prompt
    assert '"callable_tool_names": ["configure_training", "set_model"]' in prompt
    assert '"unavailable_operations"' not in prompt


def test_primary_prompt_capability_context_depends_on_state_not_case_intent():
    cases = [
        _case("empty-scan-source-folder"),
        _case("empty-train-block"),
        _case("no-tool-why-train-blocked"),
    ]

    messages = [build_prompt_messages(case) for case in cases]
    state_and_tools = [
        item[-1]["content"].split(
            "\n\nEarlier user-authored turns (context only):\n",
            maxsplit=1,
        )[0]
        for item in messages
    ]

    assert messages[0][0] == messages[1][0] == messages[2][0]
    assert state_and_tools[0] == state_and_tools[1] == state_and_tools[2]
    assert '"name": "scan_source"' in state_and_tools[0]


def test_prompt_includes_recipe_remap_choices_for_preview():
    case = _case("recipe-preview-eeg-file-remap")
    messages = build_prompt_messages(case)

    assert "preview_interpretation with choices" not in messages[0]["content"]
    assert '"eeg_file_remap"' in messages[-1]["content"]
    assert '"label_carrier_remap"' in messages[-1]["content"]


def test_scores_local_tool_call_output():
    case = _case("empty-scan-source-folder")
    raw_output = (
        '{"tool_name":"scan_source","parameters":{"source_path":"/datasets/bci_iv_2a"}}'
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {
            "tool_name": "scan_source",
            "arguments": {"source_path": "/datasets/bci_iv_2a"},
        }
    ]
    assert "tool_name" not in score.visible_response
    assert score.score_breakdown["local_llm_reliability"]
    assert score.score_breakdown["output_format"]


@pytest.mark.parametrize(
    "raw_output",
    [
        (
            "I will scan it now.\n"
            '{"tool_name":"scan_source","parameters":'
            '{"source_path":"/datasets/bci_iv_2a"}}'
        ),
        (
            '```json\n{"tool_name":"scan_source","parameters":'
            '{"source_path":"/datasets/bci_iv_2a"}}\n```'
        ),
        "scan_source: /datasets/bci_iv_2a",
        (
            '{"tool_name":"scan_source","parameters":'
            '{"source_path":"/datasets/bci_iv_2a"}'
        ),
    ],
)
def test_strict_scorer_records_tool_envelope_format_failure(raw_output):
    case = _case("empty-scan-source-folder")

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert not score.passed
    assert not score.output_format
    assert not score.score_breakdown["output_format"]
    assert "tool envelope format failure" in score.failures
    assert score.parsed_tool_calls == []
    assert score.prediction["format_error"]


def test_scores_missing_input_text_as_repair():
    case = _case("empty-scan-source-missing-path")
    raw_output = "Please provide the source path before scanning."

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "missing_input"
    assert score.parsed_tool_calls == []
    assert score.prediction["ui_handoff"] is True
    assert score.prediction["asks_clarification"] is False


def test_blocked_text_is_not_scored_as_missing_input():
    case = _case("empty-preview-before-scan-block")
    raw_output = (
        "The preview step is blocked because you must scan a data source before "
        "previewing interpretation."
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

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


def test_host_admission_blocks_substitute_before_model_without_hiding_raw_failure():
    case = _case("empty-train-block")
    raw_output = '{"tool_name":"set_model","parameters":{"model_name":"EEGNet"}}'

    raw_score = score_local_case(case, [raw_output, raw_output, raw_output])
    assisted_score = score_host_assisted_local_case(
        case,
        [raw_output, raw_output, raw_output],
    )

    assert not raw_score.passed
    assert raw_score.parsed_tool_calls == [
        {"tool_name": "set_model", "arguments": {"model_name": "EEGNet"}}
    ]
    assert assisted_score.passed
    assert assisted_score.parsed_tool_calls == []
    assert assisted_score.prediction["ui_handoff"] is False
    assert (
        "Save a valid data splitting specification before training"
        in assisted_score.visible_response
    )


def test_raw_blocked_direct_tool_call_is_preserved_and_fails_no_tool_decision():
    case = _case("loaded-create-epoch-block")
    raw_output = (
        '{"tool_name":"epoch_data","parameters":'
        '{"t_min":-0.1,"t_max":1.0,"event_id":["769"]}}'
    )

    raw_prediction = raw_prediction_from_model_output(case, raw_output)
    raw_score = score_local_case(case, [raw_output] * 3)
    assisted_score = score_host_assisted_local_case(case, [raw_output] * 3)

    assert len(raw_prediction.tool_calls) == 1
    assert raw_prediction.tool_calls[0].tool_name == "epoch_data"
    assert raw_prediction.tool_calls[0].arguments == {
        "t_min": -0.1,
        "t_max": 1.0,
        "event_id": ["769"],
    }
    assert not raw_score.passed
    assert not raw_score.tool_or_no_tool_decision
    assert "tool/no-tool decision mismatch" in raw_score.failures
    assert assisted_score.passed


def test_raw_blocked_prose_does_not_claim_host_inferred_intent_accuracy():
    case = _case("empty-train-block")
    raw_output = "Training is unavailable until you load EEG data."

    raw_score = score_local_case(case, [raw_output, raw_output, raw_output])
    assisted_score = score_host_assisted_local_case(
        case,
        [raw_output, raw_output, raw_output],
    )

    assert not raw_score.passed
    assert raw_score.intent is False
    assert raw_score.dimension_applicability["intent"]
    assert raw_score.verification_result == "allowed"
    assert not raw_score.prediction["format_valid"]
    assert "tool envelope format failure" in raw_score.failures
    assert assisted_score.passed
    assert assisted_score.intent is True


def test_raw_structured_blocked_decision_uses_model_owned_intent():
    case = _case("empty-train-block")
    raw_output = (
        '{"tool_name":"respond_to_user","parameters":{'
        '"decision":"blocked",'
        '"message":"Load EEG data before training."}}'
    )

    score = score_local_case(case, [raw_output] * 3)

    assert score.passed
    assert score.intent is None
    assert not score.dimension_applicability["intent"]
    assert score.prediction["intent"] == "no_tool"
    assert score.prediction["blocked"] is True
    assert score.parsed_tool_calls == []


def test_raw_structured_missing_input_decision_uses_model_owned_intent():
    case = _case("empty-load-missing-path")
    raw_output = (
        '{"tool_name":"respond_to_user","parameters":{'
        '"decision":"missing_input","missing_inputs":["source_path"],'
        '"message":"Please provide the EEG source path."}}'
    )

    score = score_local_case(case, [raw_output] * 3)

    assert score.passed
    assert score.intent is None
    assert score.prediction["intent"] == "no_tool"
    assert score.prediction["asks_clarification"] is True
    assert score.verification_result == "missing_input"


def test_missing_input_scores_exact_field_ids_in_raw_and_assisted_scopes():
    case = _case("empty-reload-recipe-missing-path")
    correct = (
        '{"tool_name":"respond_to_user","parameters":{'
        '"decision":"missing_input","missing_inputs":["recipe_path"],'
        '"message":"Please provide the recipe path."}}'
    )
    wrong = (
        '{"tool_name":"respond_to_user","parameters":{'
        '"decision":"missing_input","missing_inputs":["source_path"],'
        '"message":"Please provide the recipe path."}}'
    )

    correct_raw = score_local_case(case, [correct] * 3)
    wrong_raw = score_local_case(case, [wrong] * 3)
    correct_assisted = score_host_assisted_local_case(case, [correct] * 3)

    assert correct_raw.passed
    assert correct_raw.missing_input_fields is True
    assert correct_raw.prediction["missing_inputs"] == ("recipe_path",)
    assert not wrong_raw.passed
    assert wrong_raw.missing_input_fields is False
    assert "missing-input field mismatch" in wrong_raw.failures
    assert correct_assisted.missing_input_fields is True


def test_host_admission_preserves_exact_missing_input_fields() -> None:
    case = _case("empty-load-missing-path")

    score = score_host_assisted_local_case(
        case,
        ['{"tool_name":"scan_source","parameters":{}}'] * 3,
    )

    assert score.passed
    assert score.prediction["missing_inputs"] == ("source_path",)
    assert score.missing_input_fields is True


def test_raw_tool_call_does_not_claim_host_confirmation_state() -> None:
    case = _case("ready-train-confirmation")
    output = '{"tool_name":"start_training","parameters":{}}'

    raw = score_local_case(case, [output] * 3)
    assisted = score_host_assisted_local_case(case, [output] * 3)

    assert raw.passed
    assert raw.prediction["confirmation_required"] is False
    assert raw.verification_result == "allowed"
    assert raw.confirmation_boundary is None
    assert assisted.passed
    assert assisted.prediction["confirmation_required"] is True
    assert assisted.verification_result == "confirmation_required"


def test_raw_and_host_assisted_scores_do_not_hide_tool_alias_normalization():
    case = _case("preprocessed-create-epoch")
    raw_output = (
        '{"tool_name":"create_epoch","parameters":'
        '{"t_min":-0.2,"t_max":0.8,"event_id":["769"]}}'
    )

    raw_score = score_local_case(case, [raw_output] * 3)
    assisted_score = score_host_assisted_local_case(case, [raw_output] * 3)

    assert not raw_score.passed
    assert not raw_score.tool_selection
    assert raw_score.parsed_tool_calls[0]["tool_name"] == "create_epoch"
    assert assisted_score.passed
    assert assisted_score.parsed_tool_calls[0]["tool_name"] == "epoch_data"


def test_raw_prediction_and_decision_score_are_outcome_mutation_invariant():
    case = _case("successful-load-summary")
    mutated_case = replace(
        case,
        expected_result_interpretation="recoverable_failure",
        expected_state_delta={"interpretation_changed": True},
    )
    raw_output = (
        '{"tool_name":"scan_source","parameters":{"source_path":"/data/S03.fif"}}'
    )

    prediction = raw_prediction_from_model_output(case, raw_output)
    mutated_prediction = raw_prediction_from_model_output(mutated_case, raw_output)
    score = score_local_case(case, [raw_output] * 3)
    mutated_score = score_local_case(mutated_case, [raw_output] * 3)

    assert (
        prediction.trajectory_signature() == mutated_prediction.trajectory_signature()
    )
    for field_name in (
        "actual_model_output",
        "parsed_tool_calls",
        "verification_result",
        "visible_response",
        "prediction",
    ):
        assert getattr(score, field_name) == getattr(mutated_score, field_name)

    raw_decision_dimensions = (
        "intent",
        "tool_selection",
        "argument_correctness",
        "state_aware",
        "blocked_command",
        "recovery",
        "trajectory_quality",
        "local_llm_reliability",
        "tool_or_no_tool_decision",
        "clarification_behavior",
        "visible_response_quality",
        "output_format",
    )
    assert score.passed == mutated_score.passed
    assert score.failures == mutated_score.failures
    assert score.score_scope == "raw_model_decision"
    for dimension in raw_decision_dimensions:
        assert score.dimension_applicability[dimension]
        assert (
            score.score_breakdown[dimension]
            == (mutated_score.score_breakdown[dimension])
        )

    for outcome_dimension in ("state_delta", "tool_result_interpretation"):
        assert not score.dimension_applicability[outcome_dimension]
        assert score.score_breakdown[outcome_dimension] is None
        assert mutated_score.score_breakdown[outcome_dimension] is None


def test_raw_summary_reports_unmeasured_outcomes_as_excluded():
    raw_output = (
        '{"tool_name":"scan_source","parameters":{"source_path":"/data/S03.fif"}}'
    )

    result = run_local_eval(
        model_id=PRIMARY_LOCAL_MODEL_ID,
        repeat_count=1,
        case_ids=["successful-load-summary"],
        generator=MagicMock(return_value=raw_output),
    )

    summary = result["raw_model_summary"]
    assert summary["score_scope"] == "raw_model_decision"
    assert summary["state_delta_accuracy"] is None
    assert summary["tool_result_interpretation_accuracy"] is None
    assert summary["dimension_metrics"]["state_delta"] == {
        "accuracy": None,
        "applicable_cases": 0,
        "excluded_cases": 1,
        "status": "excluded",
    }
    assert set(summary["excluded_dimensions"]) == {
        "verification_result",
        "runtime_safety",
        "confirmation_boundary",
        "missing_input_fields",
        "state_delta",
        "tool_result_interpretation",
    }
    host_summary = result["host_assisted_summary"]
    assert host_summary["score_scope"] == "host_assisted_decision"
    assert host_summary["dimension_metrics"]["verification_result"]["status"] == (
        "measured"
    )
    assert set(host_summary["excluded_dimensions"]) == {
        "missing_input_fields",
        "state_delta",
        "tool_result_interpretation",
    }
    raw_score = result["cases"][0]["raw_model_score"]
    assert raw_score["backend_result"]["execution_observed"] is False
    assert raw_score["backend_result"]["observed_state_delta"] is None
    assert raw_score["backend_result"]["result_interpretation"] is None


def test_blocked_requested_direct_tool_is_scored_as_blocked_response():
    case = _case("wrong-tool-temptation-apply-after-epoch")
    raw_output = (
        "Applying this interpretation is blocked. Reset the session before "
        "changing raw files."
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == []
    assert "Reset the session before changing raw files" in score.visible_response


def test_configure_dataset_split_default_val_ratio_is_counted():
    case = _case("epoched-generate-dataset")
    raw_output = (
        '{"tool_name":"configure_dataset_split",'
        '"parameters":{"split_strategy":"trial",'
        '"training_mode":"individual","test_ratio":0.2}}'
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls[0]["arguments"]["val_ratio"] == 0.2


def test_raw_configure_dataset_split_accepts_omitted_optional_schema_default():
    case = _case("epoched-generate-dataset")
    raw_output = (
        '{"tool_name":"configure_dataset_split",'
        '"parameters":{"split_strategy":"trial",'
        '"training_mode":"individual","test_ratio":0.2}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert "val_ratio" not in score.parsed_tool_calls[0]["arguments"]


def test_unspecified_dataset_split_strategy_requires_named_missing_field():
    case = _case("epoched-generate-dataset-missing-strategy")
    clarification = (
        '{"tool_name":"respond_to_user","parameters":{'
        '"decision":"missing_input","missing_inputs":["split_strategy"],'
        '"message":"Please specify which split strategy to use."}}'
    )

    score = score_local_case(case, [clarification, clarification, clarification])

    assert score.passed
    assert score.parsed_tool_calls == []
    assert score.verification_result == "missing_input"


def test_unspecified_dataset_split_strategy_rejects_invented_trial_call():
    case = _case("epoched-generate-dataset-missing-strategy")
    invented = (
        '{"tool_name":"configure_dataset_split",'
        '"parameters":{"split_strategy":"trial",'
        '"training_mode":"individual","test_ratio":0.2}}'
    )

    score = score_local_case(case, [invented, invented, invented])

    assert not score.passed
    assert not score.tool_or_no_tool_decision
    assert "tool/no-tool decision mismatch" in score.failures


def test_scores_configure_dataset_split_missing_test_ratio_from_latest_text():
    case = _case("epoched-generate-dataset")
    raw_output = (
        '{"tool_name":"configure_dataset_split",'
        '"parameters":{"split_strategy":"trial",'
        '"training_mode":"individual"}}'
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls[0]["arguments"]["test_ratio"] == 0.2


def test_scores_preview_metadata_overrides_string_map_as_choices():
    case = _case("scanned-preview-session-override")
    raw_output = (
        '{"tool_name":"preview_interpretation","parameters":{'
        '"subject":"subject-01","session":"ses-01",'
        '"metadata_overrides":{"subject":"subject-01","session":"ses-01"}}}'
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

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

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

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

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {
            "tool_name": "preview_interpretation",
            "arguments": {"choices": {"task": "imagery", "run": "03"}},
        }
    ]


def test_scores_strict_empty_parameter_tool_call_when_available():
    case = _case("previewed-safe-validate")
    raw_output = '{"tool_name":"validate_interpretation","parameters":{}}'

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {"tool_name": "validate_interpretation", "arguments": {}}
    ]


def test_legacy_command_alias_is_a_format_failure_not_a_tool_call():
    case = _case("previewed-safe-validate")
    raw_output = '{"command":"validate_interpretation","parameters":{}}'

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert not score.passed
    assert not score.output_format
    assert score.parsed_tool_calls == []
    assert "tool envelope format failure" in score.failures


def test_scores_recipe_eeg_file_remap_tool_call():
    case = _case("recipe-preview-eeg-file-remap")
    raw_output = (
        '{"tool_name":"preview_interpretation","parameters":{"choices":{'
        '"eeg_file_remap":{"/recipe/old_raw.fif":"/data/new_raw.fif"}}}}'
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

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


def test_scores_recipe_remap_missing_target_with_named_field():
    case = _case("recipe-preview-remap-missing-target")
    raw_output = (
        '{"tool_name":"respond_to_user","parameters":{'
        '"decision":"missing_input","missing_inputs":["eeg_file_remap"],'
        '"message":"Please provide the saved file and replacement remap target."}}'
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

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

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

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

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

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

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [
        {"tool_name": "preview_interpretation", "arguments": {}}
    ]


def test_scores_preview_with_unrequested_placeholder_choices_as_plain_preview():
    case = _case("scanned-preview-auto")
    raw_output = (
        '{"tool_name":"preview_interpretation","parameters":{"choices":{'
        '"subject":"subject_id","session":"session_id","task":"task_id",'
        '"run":"run_id",'
        '"eeg_file_remap":{"/recipe/old_raw.fif":"/data/current_raw.fif"},'
        '"label_carrier_remap":{"/recipe/events.tsv":"/data/events.tsv"},'
        '"required_label_carriers":["/data/label1.tsv","/data/label2.tsv"]'
        "}}}"
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "allowed"
    assert score.parsed_tool_calls == [
        {"tool_name": "preview_interpretation", "arguments": {}}
    ]


def test_scores_policy_reason_subset_as_blocked_command_handling():
    case = _case("zh-blocked-train-empty")
    raw_output = "Training is blocked. Load raw data before training."

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "blocked"
    assert score.parsed_tool_calls == []
    assert (
        "Save a valid data splitting specification before training"
        in score.visible_response
    )


def test_scores_latest_turn_intent_not_joined_history():
    case = _case("multi-turn-validate-apply-safe")
    raw_output = '{"tool_name":"apply_interpretation","parameters":{}}'

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.prediction["intent"] == "apply_interpretation"


def test_host_assisted_score_does_not_infer_unexecuted_success_outcome():
    case = _case("successful-load-summary")
    raw_output = (
        '{"tool_name":"scan_source","parameters":{"source_path":"/data/S03.fif"}}'
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.prediction["result_interpretation"] is None
    assert score.tool_result_interpretation is None
    assert not score.dimension_applicability["tool_result_interpretation"]
    assert score.backend_result["execution_observed"] is False
    assert score.backend_result["result_interpretation"] is None


def test_scores_blocked_text_with_backend_policy_reason():
    case = _case("validated-blocked-apply-block")
    raw_output = (
        'The command "apply_interpretation" is blocked due to missing label '
        "carriers. Please load raw data first."
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert "Interpretation is blocked" in score.visible_response


def test_scores_missing_recipe_path_with_path_label():
    case = _case("empty-reload-recipe-missing-path")
    raw_output = '{"tool_name":"reload_interpretation_recipe","parameters":{}}'

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert "recipe path" in score.visible_response


def test_scores_relative_scan_source_as_missing_input():
    case = _case("empty-scan-source-relative-missing")
    raw_output = (
        '{"tool_name":"scan_source","parameters":{"source_path":"data/session01"}}'
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "missing_input"
    assert "source path" in score.visible_response


def test_switch_panel_output_fails_visualize_case_with_tool_selection_mismatch():
    case = _case("visualize-before-trained-block")
    raw_output = (
        '{"tool_name":"switch_panel","parameters":{"panel_name":"visualization"}}'
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert not score.passed
    assert score.parsed_tool_calls == []
    assert "tool selection mismatch" in score.failures


def test_set_model_output_fails_saliency_case_with_tool_selection_mismatch():
    case = _case("dataset-saliency-readiness-summary")
    raw_output = '{"tool_name":"set_model","parameters":{"model_name":"EEGNet"}}'

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert not score.passed
    assert score.parsed_tool_calls == []
    assert "tool selection mismatch" in score.failures


def test_scores_published_saliency_tool_directly():
    case = _case("dataset-saliency-readiness-summary")
    raw_output = '{"tool_name":"saliency","parameters":{}}'

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.parsed_tool_calls == [{"tool_name": "saliency", "arguments": {}}]


def test_scores_chinese_missing_input_and_no_call_cases():
    missing = _case("zh-scan-missing-source")
    missing_score = score_host_assisted_local_case(
        missing,
        ["請提供資料來源路徑後, 我才能掃描。"] * 3,
    )

    assert missing_score.passed
    assert missing_score.score_breakdown["clarification_behavior"]

    no_tool = _case("no-tool-what-is-epoch")
    no_tool_score = score_host_assisted_local_case(
        no_tool,
        [
            '{"tool_name":"respond_to_user","parameters":{'
            '"decision":"answer",'
            '"message":"Epoch 是圍繞事件切出的 EEG 時間窗。"}}'
        ]
        * 3,
    )

    assert no_tool_score.passed
    assert no_tool_score.score_breakdown["tool_or_no_tool_decision"]
    assert no_tool_score.verification_result == "no_tool"


def test_scores_structured_clarification_without_visible_tool_syntax():
    case = _case("zh-ambiguous-workflow-clarification")
    raw_output = (
        '{"tool_name":"respond_to_user","parameters":{'
        '"decision":"missing_input","missing_inputs":["workflow_step"],'
        '"message":"Could you please specify the data step?"}}'
    )

    score = score_host_assisted_local_case(case, [raw_output, raw_output, raw_output])

    assert score.passed
    assert score.verification_result == "missing_input"
    assert "tool_name" not in score.visible_response


def test_multiple_json_objects_fail_instead_of_executing_first_tool_call():
    case = _case("empty-scan-source-folder")
    raw_output = (
        '{"tool_name":"scan_source","parameters":{"source_path":"/data"}}\n'
        '{"tool_name":"configure_training","parameters":{}}'
    )

    score = score_local_case(case, [raw_output, raw_output, raw_output])

    assert not score.passed
    assert not score.output_format
    assert score.parsed_tool_calls == []
    assert "tool envelope format failure" in score.failures


def test_run_local_eval_with_fake_generator_and_writes_artifacts(tmp_path: Path):
    def fake_generator(messages: list[dict[str, str]]) -> str:
        assert messages
        return (
            '{"tool_name":"scan_source",'
            '"parameters":{"source_path":"/datasets/bci_iv_2a"}}'
        )

    result = run_local_eval(
        model_id=PRIMARY_LOCAL_MODEL_ID,
        repeat_count=3,
        case_ids=["empty-scan-source-folder"],
        generator=fake_generator,
    )
    json_path, md_path = write_local_artifacts(result, tmp_path)

    assert result["runner"] == "local-llm"
    assert result["schema_version"] == "xbrainlab.local_tool_call_eval.v5"
    assert result["prompt_condition"]["name"] == ("state_capability_unassisted")
    assert result["prompt_condition"]["primary_raw_accuracy"] is True
    assert result["prompt_condition"]["evaluator_answer_fields_included"] is False
    assert result["evidence_status"]["thesis_candidate_protocol_complete"] is False
    assert result["evidence_status"]["backend_outcome_claim_supported"] is False
    assert result["measurement_contract"]["raw_model_score_scope"] == (
        "raw_model_decision"
    )
    assert result["measurement_contract"]["host_assisted_score_scope"] == (
        "host_assisted_decision"
    )
    assert result["measurement_contract"]["backend_execution_observed"] is False
    assert result["measurement_contract"]["host_intent_filtering_used"] is False
    assert result["generated_at"].endswith("+00:00")
    assert result["summary"]["failed_cases"] == 0
    assert result["exploratory"] is True
    provenance = result["provenance"]
    assert provenance["prompt_condition"] == result["prompt_condition"]
    assert len(provenance["prompt_condition_fingerprint"]) == 64
    assert len(provenance["case_fingerprint"]) == 64
    assert len(provenance["prompt_fingerprint"]) == 64
    assert len(provenance["tool_contract_fingerprint"]) == 64
    assert len(provenance["evaluation_fingerprint"]) == 64
    assert {
        "parser",
        "normalizer",
        "verifier",
        "capability_policy",
    } <= set(provenance["source_fingerprints"])
    assert provenance["git"]["commit"]
    assert isinstance(provenance["git"]["dirty"], bool)
    assert json_path.exists()
    assert md_path.exists()
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["cli_gate"] == {
        "mode": "report_only",
        "score_scope": "raw_model_decision",
        "passed": True,
        "total_cases": 1,
        "passed_cases": 1,
        "failed_cases": 0,
        "exit_code": 0,
    }
    assert saved["cases"][0]["runs"][0]["parsed_tool_calls"] == [
        {
            "tool_name": "scan_source",
            "arguments": {"source_path": "/datasets/bci_iv_2a"},
        }
    ]
    assert saved["cases"][0]["runs"][0]["schema_verification"] == [
        {"tool_name": "scan_source", "is_valid": True, "error_message": None}
    ]
    assert saved["cases"][0]["runs"][0]["tool_envelope_status"] == "valid"
    assert saved["cases"][0]["runs"][0]["tool_envelope_error"] == ""
    assert saved["cases"][0]["runs"][0]["recovery_taxonomy"] == ("first_attempt_tool")
    attempts = saved["cases"][0]["runs"][0]["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["attempt_index"] == 0
    assert attempts[0]["raw_output"] == saved["cases"][0]["runs"][0]["raw_output"]
    assert attempts[0]["recovery_action"] == "accept_tool"
    markdown = md_path.read_text(encoding="utf-8")
    assert "XBrainLab Local Tool-Call Eval" in markdown
    assert "Raw Model Score" in markdown
    assert "Host-Assisted Product Score" in markdown
    assert "backend outcome dimensions are N/A/excluded" in markdown
    assert "| state delta | N/A | 0 | 1 | excluded |" in markdown
    assert "state_capability_unassisted" in markdown
    assert "primary raw-accuracy condition" in markdown
    assert "CLI gate mode: `report_only`" in markdown
    assert "CLI gate passed: `True`" in markdown
    assert "case fingerprint" in markdown
    latest = json.loads((tmp_path / "local_latest.json").read_text(encoding="utf-8"))
    assert latest["generated_at"] == result["generated_at"]
    assert (
        latest["provenance"]["evaluation_fingerprint"]
        == provenance["evaluation_fingerprint"]
    )
    assert latest["raw_model_summary"] == result["raw_model_summary"]
    assert latest["host_assisted_summary"] == result["host_assisted_summary"]
    assert latest["schema_version"] == result["schema_version"]
    assert latest["prompt_condition"] == result["prompt_condition"]
    assert latest["evidence_status"] == result["evidence_status"]
    assert latest["measurement_contract"] == result["measurement_contract"]
    assert latest["cli_gate"] == saved["cli_gate"]


def test_run_local_eval_closes_owned_engine_generator(monkeypatch):
    generator = MagicMock(
        return_value=(
            '{"tool_name":"scan_source",'
            '"parameters":{"source_path":"/datasets/bci_iv_2a"}}'
        )
    )
    generator.close = MagicMock()
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval._build_engine_generator",
        lambda _config: generator,
    )

    result = run_local_eval(
        model_id=PRIMARY_LOCAL_MODEL_ID,
        repeat_count=1,
        case_ids=["empty-scan-source-folder"],
    )

    assert result["summary"]["failed_cases"] == 0
    generator.close.assert_called_once_with()


def test_local_eval_recovers_malformed_then_valid_and_scores_final_output():
    outputs = iter(
        [
            (
                '```json\n{"tool_name":"scan_source","parameters":'
                '{"source_path":"/datasets/bci_iv_2a"}}\n```'
            ),
            (
                '{"tool_name":"scan_source","parameters":'
                '{"source_path":"/datasets/bci_iv_2a"}}'
            ),
        ]
    )
    seen_messages: list[list[dict[str, str]]] = []

    def recovering_generator(messages: list[dict[str, str]]) -> str:
        seen_messages.append(messages)
        return next(outputs)

    result = run_local_eval(
        model_id=PRIMARY_LOCAL_MODEL_ID,
        repeat_count=1,
        case_ids=["empty-scan-source-folder"],
        generator=recovering_generator,
    )

    assert result["summary"]["failed_cases"] == 0
    assert result["summary"]["output_format_accuracy"] == 1.0
    assert result["recovery_taxonomy"] == {"recovered_tool": 1}
    run = result["cases"][0]["runs"][0]
    assert run["tool_envelope_status"] == "valid"
    assert run["recovery_taxonomy"] == "recovered_tool"
    assert len(run["attempts"]) == 2
    assert run["attempts"][0]["tool_envelope_status"] == "format_error"
    assert run["attempts"][0]["recovery_action"] == "retry_format"
    assert run["attempts"][1]["tool_envelope_status"] == "valid"
    assert run["attempts"][1]["recovery_action"] == "accept_tool"
    assert "exactly one JSON object" in seen_messages[1][0]["content"]


def test_local_eval_exhausts_malformed_output_after_one_recovery_attempt():
    malformed = (
        '```json\n{"tool_name":"scan_source","parameters":'
        '{"source_path":"/datasets/bci_iv_2a"}}\n```'
    )
    generator = MagicMock(return_value=malformed)

    result = run_local_eval(
        model_id=PRIMARY_LOCAL_MODEL_ID,
        repeat_count=1,
        case_ids=["empty-scan-source-folder"],
        generator=generator,
    )

    assert generator.call_count == 2
    assert result["summary"]["failed_cases"] == 1
    assert result["summary"]["output_format_accuracy"] == 0.0
    assert result["failure_taxonomy"]["tool envelope format failure"] == 1
    assert result["recovery_taxonomy"] == {"format_recovery_exhausted": 1}
    run = result["cases"][0]["runs"][0]
    assert run["recovery_taxonomy"] == "format_recovery_exhausted"
    assert [attempt["recovery_action"] for attempt in run["attempts"]] == [
        "retry_format",
        "exhausted",
    ]
    assert all(attempt["raw_output"] == malformed for attempt in run["attempts"])
    assert all(attempt["tool_envelope_error"] for attempt in run["attempts"])
    assert all(attempt["latency_seconds"] >= 0 for attempt in run["attempts"])


def test_local_eval_no_tool_prose_retries_then_fails_strict_envelope():
    generator = MagicMock(return_value="Epoch 是圍繞事件切出的 EEG 時間窗。")

    result = run_local_eval(
        model_id=PRIMARY_LOCAL_MODEL_ID,
        repeat_count=1,
        case_ids=["no-tool-what-is-epoch"],
        generator=generator,
    )

    assert generator.call_count == 2
    assert result["summary"]["failed_cases"] == 1
    assert result["recovery_taxonomy"] == {"format_recovery_exhausted": 1}
    run = result["cases"][0]["runs"][0]
    assert run["recovery_taxonomy"] == "format_recovery_exhausted"
    assert len(run["attempts"]) == 2
    assert [attempt["recovery_action"] for attempt in run["attempts"]] == [
        "retry_format",
        "exhausted",
    ]


def test_local_eval_generation_error_fails_even_for_expected_no_tool_case():
    def failing_generator(messages: list[dict[str, str]]) -> str:
        del messages
        raise RuntimeError("boom")

    result = run_local_eval(
        model_id=PRIMARY_LOCAL_MODEL_ID,
        repeat_count=1,
        case_ids=["no-tool-what-is-epoch"],
        generator=failing_generator,
    )

    assert result["summary"]["failed_cases"] == 1
    assert result["raw_model_summary"]["failed_cases"] == 1
    assert result["host_assisted_summary"]["failed_cases"] == 1
    score = result["cases"][0]["score"]
    assert score["passed"] is False
    assert score["output_format"] is False
    assert "generation failed" in score["failures"]
    run = result["cases"][0]["runs"][0]
    assert run["error"] == "boom"


def test_local_eval_reports_raw_failure_and_safe_host_block_separately():
    raw_output = (
        '{"tool_name":"epoch_data","parameters":'
        '{"t_min":-0.1,"t_max":1.0,"event_id":["769"]}}'
    )

    result = run_local_eval(
        model_id=PRIMARY_LOCAL_MODEL_ID,
        repeat_count=1,
        case_ids=["loaded-create-epoch-block"],
        generator=MagicMock(return_value=raw_output),
    )

    assert result["summary"] == result["raw_model_summary"]
    assert result["raw_model_summary"]["failed_cases"] == 1
    assert result["host_assisted_summary"]["passed_cases"] == 1
    case = result["cases"][0]
    assert case["score"]["passed"] is False
    assert case["host_assisted_score"]["passed"] is True
    run = case["runs"][0]
    assert run["host_safely_blocked"] is True
    assert run["host_admission_action"] == "blocked"
    assert run["host_model_generation_required"] is False
    assert run["normalization_applied"] is False
    assert run["raw_parsed_tool_calls"][0]["tool_name"] == "epoch_data"
    assert run["host_assisted_parsed_tool_calls"] == []


def test_product_publication_blocks_wrong_browse_tool_without_claiming_completion():
    raw_output = '{"tool_name":"list_files","parameters":{"directory":"/data/S04.edf"}}'

    result = run_local_eval(
        model_id=PRIMARY_LOCAL_MODEL_ID,
        repeat_count=1,
        case_ids=["workflow-continue-empty-scan"],
        generator=MagicMock(return_value=raw_output),
    )

    assert result["raw_model_summary"]["failed_cases"] == 1
    assert result["host_assisted_summary"]["failed_cases"] == 1
    run = result["cases"][0]["runs"][0]
    assert run["host_safely_blocked"] is True
    assert run["host_assisted_parsed_tool_calls"] == []
    assert result["cases"][0]["host_assisted_score"]["passed"] is False


def test_local_eval_ui_handoff_is_not_failed_by_unused_model_generation():
    def failing_generator(messages: list[dict[str, str]]) -> str:
        del messages
        raise RuntimeError("model should not be required by product admission")

    result = run_local_eval(
        model_id=PRIMARY_LOCAL_MODEL_ID,
        repeat_count=1,
        case_ids=["empty-scan-source-missing-path"],
        generator=failing_generator,
    )

    assert result["raw_model_summary"]["failed_cases"] == 1
    assert result["host_assisted_summary"]["passed_cases"] == 1
    run = result["cases"][0]["runs"][0]
    assert run["host_admission_action"] == "ui_handoff"
    assert run["host_model_generation_required"] is False
    assert run["host_assisted_parsed_tool_calls"] == []


def test_run_local_eval_closes_owned_engine_when_evaluation_aborts(monkeypatch):
    generator = MagicMock()
    generator.close = MagicMock()
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval._build_engine_generator",
        lambda _config: generator,
    )
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval._evaluate_local_cases",
        MagicMock(side_effect=RuntimeError("scorer failed")),
    )

    with pytest.raises(RuntimeError, match="scorer failed"):
        run_local_eval(
            model_id=PRIMARY_LOCAL_MODEL_ID,
            repeat_count=1,
            case_ids=["empty-scan-source-folder"],
        )

    generator.close.assert_called_once_with()


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


def _stub_completed_cli_eval(
    monkeypatch,
    tmp_path: Path,
    *,
    failed_cases: int,
) -> dict[str, Any]:
    total_cases = 1
    summary = {
        "total_cases": total_cases,
        "passed_cases": total_cases - failed_cases,
        "failed_cases": failed_cases,
        "pass_rate": float(total_cases - failed_cases) / total_cases,
    }
    result: dict[str, object] = {
        "summary": summary,
        "raw_model_summary": summary,
    }
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval.build_local_eval_resource_preflight",
        lambda **_kwargs: {"ok": True},
    )
    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval.run_local_eval",
        lambda **_kwargs: result,
    )

    def capture_artifacts(
        artifact_result: dict[str, object],
        output_dir: Path,
    ) -> tuple[Path, Path]:
        captured["result"] = artifact_result
        return output_dir / "local.json", output_dir / "local.md"

    monkeypatch.setattr(
        "scripts.agent.evals.run_local_tool_call_eval.write_local_artifacts",
        capture_artifacts,
    )
    return captured


def test_strict_gate_failure_contract_is_persisted_in_artifacts(tmp_path: Path):
    result = run_local_eval(
        model_id=PRIMARY_LOCAL_MODEL_ID,
        repeat_count=1,
        case_ids=["empty-scan-source-folder"],
        generator=MagicMock(
            return_value=('{"tool_name":"query_state","parameters":{"query":"state"}}'),
        ),
    )
    result["cli_gate"] = build_local_eval_cli_gate(result, strict=True)

    json_path, markdown_path = write_local_artifacts(result, tmp_path)

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["cli_gate"]["passed"] is False
    assert saved["cli_gate"]["failed_cases"] == 1
    assert saved["cli_gate"]["exit_code"] == 1
    latest = json.loads((tmp_path / "local_latest.json").read_text(encoding="utf-8"))
    assert latest["cli_gate"] == saved["cli_gate"]
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "CLI gate mode: `strict`" in markdown
    assert "CLI gate exit code: `1`" in markdown


def test_cli_strict_gate_returns_nonzero_when_raw_model_cases_fail(
    tmp_path: Path,
    monkeypatch,
):
    captured = _stub_completed_cli_eval(
        monkeypatch,
        tmp_path,
        failed_cases=1,
    )

    exit_code = main(
        [
            "--model",
            "microsoft/Phi-4-mini-instruct",
            "--repeat-count",
            "1",
            "--case-limit",
            "1",
            "--strict",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert exit_code == 1
    assert captured["result"]["cli_gate"] == {
        "mode": "strict",
        "score_scope": "raw_model_decision",
        "passed": False,
        "total_cases": 1,
        "passed_cases": 0,
        "failed_cases": 1,
        "exit_code": 1,
    }


def test_cli_strict_gate_returns_zero_when_every_raw_model_case_passes(
    tmp_path: Path,
    monkeypatch,
):
    captured = _stub_completed_cli_eval(
        monkeypatch,
        tmp_path,
        failed_cases=0,
    )

    exit_code = main(
        [
            "--model",
            "microsoft/Phi-4-mini-instruct",
            "--repeat-count",
            "1",
            "--case-limit",
            "1",
            "--strict",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert exit_code == 0
    assert captured["result"]["cli_gate"]["passed"] is True


def test_cli_report_only_mode_writes_failed_report_but_returns_zero(
    tmp_path: Path,
    monkeypatch,
):
    captured = _stub_completed_cli_eval(
        monkeypatch,
        tmp_path,
        failed_cases=1,
    )

    exit_code = main(
        [
            "--model",
            "microsoft/Phi-4-mini-instruct",
            "--repeat-count",
            "1",
            "--case-limit",
            "1",
            "--report-only",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert exit_code == 0
    assert captured["result"]["cli_gate"] == {
        "mode": "report_only",
        "score_scope": "raw_model_decision",
        "passed": False,
        "total_cases": 1,
        "passed_cases": 0,
        "failed_cases": 1,
        "exit_code": 0,
    }


def test_cli_candidate_gate_defaults_to_report_only(
    tmp_path: Path,
    monkeypatch,
):
    captured = _stub_completed_cli_eval(
        monkeypatch,
        tmp_path,
        failed_cases=1,
    )

    exit_code = main(
        [
            "--model",
            "microsoft/Phi-4-mini-instruct",
            "--eval-gate",
            "candidate",
            "--repeat-count",
            "1",
            "--case-limit",
            "1",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert exit_code == 0
    assert captured["result"]["cli_gate"]["mode"] == "report_only"
    assert captured["result"]["cli_gate"]["passed"] is False


def test_cli_release_gate_is_strict_unless_report_only_is_explicit(
    tmp_path: Path,
    monkeypatch,
):
    captured = _stub_completed_cli_eval(
        monkeypatch,
        tmp_path,
        failed_cases=1,
    )

    exit_code = main(
        [
            "--model",
            "microsoft/Phi-4-mini-instruct",
            "--eval-gate",
            "release",
            "--repeat-count",
            "1",
            "--case-limit",
            "1",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert exit_code == 1
    assert captured["result"]["cli_gate"]["mode"] == "strict"

    report_exit_code = main(
        [
            "--model",
            "microsoft/Phi-4-mini-instruct",
            "--eval-gate",
            "release",
            "--repeat-count",
            "1",
            "--case-limit",
            "1",
            "--report-only",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert report_exit_code == 0
    assert captured["result"]["cli_gate"]["mode"] == "report_only"
