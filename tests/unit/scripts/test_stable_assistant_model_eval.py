"""Stable-v2 local-model selection evaluation contracts."""

from pathlib import Path
from unittest.mock import patch

from scripts.dev.run_stable_assistant_model_eval import (
    DEFAULT_CHALLENGES,
    _build_report,
    _experiment_identity,
    _stable_eval_config,
    build_case_messages,
    load_challenge_cases,
    load_target_cases,
    score_challenge_response,
    score_missing_parameter_host_guard,
    score_model_response,
    score_positive_parameter_host_guard,
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


def test_missing_parameter_model_default_is_blocked_by_host_guard() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_challenge_cases(DEFAULT_CHALLENGES)
        if item.case_id == "missing_resample_rate_01"
    )
    response = (
        '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
        '"parameters":{"rate":256}}'
    )

    host_guard = score_missing_parameter_host_guard(case, response, registry)

    assert host_guard == {
        "applicable": True,
        "passed": True,
        "execution_allowed": False,
        "tool_name": "resample_data",
        "message": "What resampling rate should I use?",
        "detail": "The host rejected model-supplied values absent from the latest user request.",
    }


def test_explicit_positive_values_pass_the_same_host_guard() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_target_cases(GOLD_SET)
        if item.case_id == "apply_bandpass_filter_01"
    )
    response = (
        '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
        '"parameters":{"low_freq":4,"high_freq":38}}'
    )

    host_guard = score_positive_parameter_host_guard(case, response, registry)

    assert host_guard == {
        "applicable": True,
        "passed": True,
        "execution_allowed": True,
        "tool_name": "apply_bandpass_filter",
        "message": None,
    }


def test_candidate_report_requires_positive_and_host_guard_gates() -> None:
    results = (
        [
            {
                "suite": "positive",
                "score": {"passed": True},
                **(
                    {
                        "parameter_origin_guard": {
                            "applicable": True,
                            "passed": True,
                        }
                    }
                    if index < 10
                    else {}
                ),
            }
            for index in range(36)
        ]
        + [
            {
                "suite": "challenge",
                "score": {"passed": False},
                "host_guard": {"applicable": True, "passed": True},
            }
            for _ in range(5)
        ]
        + [{"suite": "challenge", "score": {"passed": False}} for _ in range(9)]
    )

    report = _build_report(
        model_id="ibm-granite/granite-3.3-2b-instruct",
        results=results,
        expected_case_count=50,
        complete=True,
    )

    assert report["candidate_gate"] == {
        "positive_exact": {"required": 36, "passed": 36},
        "explicit_parameter_host_guard": {"required": 10, "passed": 10},
        "missing_parameter_host_guard": {"required": 5, "passed": 5},
        "passed": True,
    }
    assert report["summary"]["passed"] is True


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
