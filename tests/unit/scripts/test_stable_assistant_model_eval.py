"""Stable-v2 local-model selection evaluation contracts."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.dev.run_stable_assistant_model_eval import (
    DEFAULT_CHALLENGES,
    ActionabilityGate,
    _build_report,
    _evaluate_ab_adoption,
    _experiment_identity,
    _stable_eval_config,
    build_actionability_gate_messages,
    build_case_messages,
    build_final_messages_for_gate,
    load_challenge_cases,
    load_target_cases,
    parse_actionability_gate,
    run_ab_eval,
    score_challenge_response,
    score_model_response,
    target_tool_registry,
)
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.core.config import LLMConfig

GOLD_SET = Path("XBrainLab/llm/rag/data/gold_set.json")


def test_eval_config_uses_fixed_product_model_without_mutating_user_settings() -> None:
    user_config = LLMConfig(
        model_name="microsoft/Phi-4-mini-instruct",
        cache_dir="/tmp/xbrainlab-model-cache",
        device="cpu",
        local_model_enabled=False,
    )

    eval_config = _stable_eval_config(user_config, device="cuda")

    assert eval_config is user_config
    assert eval_config.model_name == LLMConfig.default_local_model_id()
    assert eval_config.cache_dir == "/tmp/xbrainlab-model-cache"
    assert eval_config.device == "cuda"
    assert eval_config.local_model_enabled is True
    assert eval_config.assistant_runtime_selection().backend_mode == "local"


def test_target_cases_cover_each_approved_tool_twice() -> None:
    cases = load_target_cases(GOLD_SET)

    counts = {
        tool_name: sum(case.expected_tool == tool_name for case in cases)
        for tool_name in AGENT_ACTION_CONTRACTS.model_tool_names()
    }

    assert len(cases) == 36
    assert set(counts) == AGENT_ACTION_CONTRACTS.model_tool_names()
    assert set(counts.values()) == {2}


def test_challenge_cases_extend_positive_matrix_to_exact_50_case_gate() -> None:
    cases = load_challenge_cases(DEFAULT_CHALLENGES)

    assert len(cases) == 14
    assert len({case.case_id for case in cases}) == 14
    assert {case.category for case in cases} == {
        "ambiguous",
        "general",
        "missing_parameter",
        "multi_action",
        "out_of_stage",
    }
    assert len(load_target_cases(GOLD_SET)) + len(cases) == 50


def test_challenge_score_requires_strict_response_envelope_and_message_contract() -> (
    None
):
    case = next(
        item
        for item in load_challenge_cases(DEFAULT_CHALLENGES)
        if item.case_id == "missing_bandpass_bounds_01"
    )
    registry = target_tool_registry()
    valid = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"請提供 bandpass 的 low 和 high 頻率。"}}'
    )

    assert score_challenge_response(case, valid, registry).passed is True

    failures = (
        (
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"請補充設定。"}}'
        ),
        (
            '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
            '"parameters":{"low_freq":4,"high_freq":38}}'
        ),
        (
            '{"workflow_stage":"preprocessed","tool_name":"respond_to_user",'
            '"parameters":{"message":"請提供 bandpass 的 low 和 high 頻率。"}}'
        ),
    )
    for response in failures:
        assert score_challenge_response(case, response, registry).passed is False

    lifecycle_case = next(
        item
        for item in load_challenge_cases(DEFAULT_CHALLENGES)
        if item.case_id == "start_before_setup_01"
    )
    false_completion = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"Training has been initiated; finish setup '
        'before starting."}}'
    )
    assert (
        score_challenge_response(lifecycle_case, false_completion, registry).passed
        is False
    )


def test_case_messages_publish_stage_tools_without_retired_surface() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_target_cases(GOLD_SET)
        if item.case_id == "create_epochs_01"
    )

    messages = build_case_messages(case, registry)
    system = messages[0]["content"]

    assert case.workflow_stage == "data_loaded"
    assert '"name": "create_epochs"' in system
    assert '"name": "switch_panel"' in system
    assert '"name": "query_state"' not in system
    assert messages[-1] == {"role": "user", "content": case.user_input}


def test_score_accepts_only_exact_stage_tool_and_schema() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_target_cases(GOLD_SET)
        if item.case_id == "switch_panel_01"
    )
    valid = (
        '{"workflow_stage":"empty","tool_name":"switch_panel",'
        '"parameters":{"panel_name":"evaluation"}}'
    )

    assert score_model_response(case, valid, registry).passed is True

    failures = (
        '{"workflow_stage":"empty","tool_name":"query_state","parameters":{}}',
        (
            '{"workflow_stage":"trained","tool_name":"switch_panel",'
            '"parameters":{"panel_name":"evaluation"}}'
        ),
        (
            '{"workflow_stage":"empty","tool_name":"switch_panel",'
            '"parameters":{"panel_name":"dashboard"}}'
        ),
        (
            '{"workflow_stage":"empty","tool_name":"switch_panel",'
            '"parameters":{"panel_name":"evaluation","extra":true}}'
        ),
    )
    for response in failures:
        assert score_model_response(case, response, registry).passed is False


def test_partial_report_never_claims_the_suite_passed() -> None:
    report = _build_report(
        model_id="ibm-granite/granite-3.3-2b-instruct",
        results=[],
        expected_case_count=50,
        complete=False,
    )

    assert report["summary"] == {
        "expected_case_count": 50,
        "case_count": 0,
        "passed_count": 0,
        "failed_count": 0,
        "complete": False,
        "passed": False,
    }


def test_report_separates_positive_and_challenge_results() -> None:
    report = _build_report(
        model_id="ibm-granite/granite-3.3-2b-instruct",
        results=[
            {"suite": "positive", "score": {"passed": True}},
            {"suite": "challenge", "score": {"passed": False}},
        ],
        expected_case_count=50,
        complete=False,
    )

    assert report["suite_summary"] == {
        "positive": {"case_count": 1, "passed_count": 1, "failed_count": 0},
        "challenge": {"case_count": 1, "passed_count": 0, "failed_count": 1},
    }


def test_actionability_gate_parser_requires_exact_model_owned_schema() -> None:
    valid = (
        '{"workflow_stage":"data_loaded","decision":"respond",'
        '"reason_class":"missing_required"}'
    )

    assert parse_actionability_gate(valid, expected_stage="data_loaded") == (
        ActionabilityGate(
            workflow_stage="data_loaded",
            decision="respond",
            reason_class="missing_required",
        )
    )

    invalid = (
        '{"workflow_stage":"preprocessed","decision":"respond",'
        '"reason_class":"missing_required"}',
        '{"workflow_stage":"data_loaded","decision":"execute_one",'
        '"reason_class":"missing_required"}',
        '{"workflow_stage":"data_loaded","decision":"respond",'
        '"reason_class":"complete"}',
        '{"workflow_stage":"data_loaded","decision":"respond",'
        '"reason_class":"missing_required","tool_name":"apply_bandpass_filter"}',
        '{"workflow_stage":"data_loaded","decision":"respond"}',
        "not json",
    )
    for response in invalid:
        with pytest.raises(ValueError):
            parse_actionability_gate(response, expected_stage="data_loaded")


def test_actionability_gate_prompt_is_generic_and_contains_no_case_oracle() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_challenge_cases(DEFAULT_CHALLENGES)
        if item.case_id == "missing_bandpass_bounds_01"
    )

    messages = build_actionability_gate_messages(case, registry)
    system = messages[0]["content"]

    assert messages[-1] == {"role": "user", "content": case.user_input}
    assert case.case_id not in system
    assert "required_concepts" not in system
    assert "forbidden_concepts" not in system
    assert "STRICT RESPONSE CONTRACT" not in system
    assert '"decision":"DECISION"' in system
    assert "Replace DECISION with exactly execute_one or respond" in system
    assert '"reason_class"' in system
    assert '"name": "apply_bandpass_filter"' in system


def test_final_pass_uses_same_request_and_model_gate_without_host_tool_choice() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_target_cases(GOLD_SET)
        if item.case_id == "apply_bandpass_filter_01"
    )
    gate = ActionabilityGate(
        workflow_stage=case.workflow_stage,
        decision="execute_one",
        reason_class="complete",
    )

    messages = build_final_messages_for_gate(case, registry, gate)
    system = messages[0]["content"]

    assert messages[-1] == {"role": "user", "content": case.user_input}
    assert "model-owned actionability draft" in system
    assert '"decision":"execute_one"' in system
    assert (
        case.expected_tool
        not in system.split("model-owned actionability draft", maxsplit=1)[1]
    )


def test_respond_gate_limits_final_branch_without_inventing_a_substitute() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_challenge_cases(DEFAULT_CHALLENGES)
        if item.case_id == "multi_preprocess_request_01"
    )
    gate = ActionabilityGate(
        workflow_stage=case.workflow_stage,
        decision="respond",
        reason_class="multiple_actions",
    )

    messages = build_final_messages_for_gate(case, registry, gate)
    final_instruction = messages[0]["content"].split(
        "model-owned actionability draft", maxsplit=1
    )[1]

    assert "respond_to_user" in final_instruction
    assert "Do not execute an action" in final_instruction
    assert "apply_bandpass_filter" not in final_instruction
    assert "resample_data" not in final_instruction


def test_ab_adoption_requires_exact_two_pass_score_and_latency_limits() -> None:
    passing = _evaluate_ab_adoption(
        one_pass_report={"summary": {"passed": False}},
        two_pass_report={"summary": {"passed": True}},
        one_pass_warm_p95_ms=3000.0,
        two_pass_warm_p95_ms=4400.0,
    )

    assert passing["score_gate"] is True
    assert passing["relative_latency_gate"] is True
    assert passing["warm_p95_gate"] is True
    assert passing["passed"] is True

    too_slow = _evaluate_ab_adoption(
        one_pass_report={"summary": {"passed": True}},
        two_pass_report={"summary": {"passed": True}},
        one_pass_warm_p95_ms=3000.0,
        two_pass_warm_p95_ms=4600.0,
    )
    assert too_slow["relative_latency_multiplier"] > 1.5
    assert too_slow["relative_latency_gate"] is False
    assert too_slow["passed"] is False

    absolute_slow = _evaluate_ab_adoption(
        one_pass_report={"summary": {"passed": True}},
        two_pass_report={"summary": {"passed": True}},
        one_pass_warm_p95_ms=5000.0,
        two_pass_warm_p95_ms=6000.1,
    )
    assert absolute_slow["warm_p95_gate"] is False
    assert absolute_slow["passed"] is False


def test_ab_runner_reuses_one_engine_and_scores_both_model_owned_passes() -> None:
    registry = target_tool_registry()
    positive = next(
        item
        for item in load_target_cases(GOLD_SET)
        if item.case_id == "switch_panel_01"
    )
    challenge = next(
        item
        for item in load_challenge_cases(DEFAULT_CHALLENGES)
        if item.case_id == "missing_bandpass_bounds_01"
    )
    positive_response = (
        '{"workflow_stage":"empty","tool_name":"switch_panel",'
        '"parameters":{"panel_name":"evaluation"}}'
    )
    challenge_response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"Please provide the bandpass low and high '
        'frequencies."}}'
    )
    generated = [
        positive_response,
        '{"workflow_stage":"empty","decision":"execute_one","reason_class":"complete"}',
        positive_response,
        challenge_response,
        '{"workflow_stage":"data_loaded","decision":"respond",'
        '"reason_class":"missing_required"}',
        challenge_response,
    ]
    config = _stable_eval_config(
        LLMConfig(cache_dir="/tmp/xbrainlab-model-cache"),
        device="cpu",
    )

    with (
        patch.object(config, "local_backend_ready", return_value=True),
        patch("scripts.dev.run_stable_assistant_model_eval.LLMEngine") as engine_type,
    ):
        engine = engine_type.return_value
        engine.generate_stream.side_effect = [iter([item]) for item in generated]
        report = run_ab_eval(
            config,
            (positive,),
            challenge_cases=(challenge,),
        )

    assert registry.get_tool("switch_panel") is not None
    engine.load_model.assert_called_once_with()
    assert engine.generate_stream.call_count == 6
    assert report["arms"]["one_pass"]["summary"]["passed"] is True
    assert report["arms"]["two_pass"]["summary"]["passed"] is True
    assert report["arms"]["two_pass"]["results"][0]["gate"]["parsed"] == {
        "workflow_stage": "empty",
        "decision": "execute_one",
        "reason_class": "complete",
    }
    assert report["arms"]["two_pass"]["results"][1]["gate"]["parsed"] == {
        "workflow_stage": "data_loaded",
        "decision": "respond",
        "reason_class": "missing_required",
    }


def test_experiment_identity_binds_source_and_ignores_only_protected_settings(
    tmp_path: Path,
) -> None:
    positives = tmp_path / "positive.json"
    challenges = tmp_path / "challenge.json"
    positives.write_text("positive\n", encoding="utf-8")
    challenges.write_text("challenge\n", encoding="utf-8")

    with patch(
        "scripts.dev.run_stable_assistant_model_eval.subprocess.check_output",
        side_effect=[
            "abc123\n",
            " M settings.json\n M scripts/dev/run_stable_assistant_model_eval.py\n",
        ],
    ):
        identity = _experiment_identity(
            cases_path=positives,
            challenges_path=challenges,
        )

    assert identity["source_sha"] == "abc123"
    assert identity["source_changes_excluding_protected_settings"] == [
        " M scripts/dev/run_stable_assistant_model_eval.py"
    ]
    assert len(identity["positive_cases_sha256"]) == 64
    assert len(identity["challenge_cases_sha256"]) == 64
