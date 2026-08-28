"""Stable-v2 local-model selection evaluation contracts."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.dev.run_stable_assistant_model_eval import (
    DEFAULT_CHALLENGES,
    DEFAULT_CLARIFICATION_CASES,
    DEFAULT_PRECISION_CASES,
    CaseTrajectoryResult,
    ModelGenerationAttempt,
    TargetEvalScore,
    _build_report,
    _evaluation_generation_policy,
    _experiment_identity,
    _stable_eval_config,
    admit_clarification_receipt,
    build_case_messages,
    build_clarification_messages,
    evaluate_case_trajectory,
    evaluate_clarification_trajectory,
    evaluate_discriminated_clarification_trajectory,
    load_challenge_cases,
    load_clarification_cases,
    load_precision_cases,
    load_target_cases,
    run_eval,
    score_challenge_response,
    score_missing_parameter_host_guard,
    score_model_response,
    score_positive_parameter_host_guard,
    score_precision_response,
    score_raw_precision_response,
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


def test_target_case_loader_rejects_duplicate_normalized_inputs(tmp_path: Path) -> None:
    payload = json.loads(GOLD_SET.read_text(encoding="utf-8"))
    payload[1]["input"] = payload[0]["input"].upper()
    cases_path = tmp_path / "duplicate-input.json"
    cases_path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        load_target_cases(cases_path)
    except ValueError as exc:
        assert "duplicates a normalized user input" in str(exc)
    else:  # pragma: no cover - assertion branch documents the required rejection
        raise AssertionError("Duplicate normalized inputs must be rejected.")


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


def test_precision_cases_cover_tools_and_english_no_action_categories() -> None:
    cases = load_precision_cases(DEFAULT_PRECISION_CASES)

    assert len(cases) == 24
    assert {case.requested_tool for case in cases if case.requested_tool} == (
        AGENT_ACTION_CONTRACTS.model_tool_names()
    )
    assert {case.category for case in cases} == {
        "ambiguous",
        "general",
        "missing_parameter",
        "multi_action",
        "negated",
        "out_of_stage",
    }
    assert sum(case.category == "general" for case in cases) == 2
    assert sum(case.category == "ambiguous" for case in cases) == 2
    assert sum(case.category == "multi_action" for case in cases) == 2


def test_clarification_cases_cover_each_direct_parameter_tool_once() -> None:
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )

    direct_cases = [case for case in cases if case.trajectory_kind == "direct"]
    assert len(cases) == 7
    assert {case.expected_tool for case in direct_cases} == {
        "apply_bandpass_filter",
        "apply_notch_filter",
        "resample_data",
        "set_reference",
        "normalize_data",
    }
    assert {case.source_case_id for case in direct_cases} == {
        case.case_id for case in precision_cases if case.category == "missing_parameter"
    }
    assert {
        case.trajectory_kind for case in cases if case.trajectory_kind != "direct"
    } == {
        "generic_filter_selection",
        "partial_bandpass_accumulation",
    }


def test_active_assistant_evidence_cases_are_english_only() -> None:
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    clarification_cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )
    inputs = [
        *(case.user_input for case in load_target_cases(GOLD_SET)),
        *(case.user_input for case in load_challenge_cases(DEFAULT_CHALLENGES)),
        *(case.user_input for case in precision_cases),
        *(case.reply for case in clarification_cases),
        *(turn for case in clarification_cases for turn in case.turns),
    ]

    assert all(text.isascii() for text in inputs)


def test_run_eval_admits_direct_receipts_from_serialized_final_response(
    monkeypatch,
) -> None:
    response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"Please provide the required value.",'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )
    score = TargetEvalScore(
        True,
        "",
        response,
        "data_loaded",
        "respond_to_user",
        {"message": "Please provide the required value."},
        "accepted",
    )
    trajectory = CaseTrajectoryResult(
        raw_score=score,
        post_recovery_score=score,
        final_score=score,
        final_response=response,
        attempts=(
            ModelGenerationAttempt(
                attempt_number=1,
                response=response,
                envelope_status="no_tool",
                workflow_stage="data_loaded",
                recovery_action="accept",
                taxonomy="respond",
                recovery_attempts_after=0,
            ),
        ),
    )
    config = _stable_eval_config(LLMConfig(), device="cpu")
    monkeypatch.setattr(config, "local_backend_ready", lambda _model_id: True)
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    clarification_cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )
    engine = MagicMock()

    with (
        patch(
            "scripts.dev.run_stable_assistant_model_eval.LLMEngine",
            return_value=engine,
        ),
        patch(
            "scripts.dev.run_stable_assistant_model_eval.evaluate_case_trajectory",
            return_value=trajectory,
        ),
        patch(
            "scripts.dev.run_stable_assistant_model_eval."
            "evaluate_clarification_trajectory",
            return_value=trajectory,
        ),
        patch(
            "scripts.dev.run_stable_assistant_model_eval."
            "evaluate_discriminated_clarification_trajectory",
            return_value=trajectory,
        ),
        patch(
            "scripts.dev.run_stable_assistant_model_eval.admit_clarification_receipt",
            return_value=object(),
        ) as admit_receipt,
    ):
        run_eval(
            config,
            (),
            precision_cases=precision_cases,
            clarification_cases=clarification_cases,
        )

    assert len(admit_receipt.call_args_list) == 5
    assert {call.args[1] for call in admit_receipt.call_args_list} == {response}


def test_clarification_prompt_and_score_use_product_receipt_boundary() -> None:
    registry = target_tool_registry()
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    case = next(
        item
        for item in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=precision_cases,
        )
        if item.expected_tool == "resample_data"
    )
    source = next(
        item for item in precision_cases if item.case_id == case.source_case_id
    )
    first_response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What resampling rate should I use?",'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )
    admission = admit_clarification_receipt(
        source,
        first_response,
        expected_tool=case.expected_tool,
        registry=registry,
    )
    assert admission is not None
    receipt = admission.receipt
    messages, _prompt_publication, _backend_publication = build_clarification_messages(
        case,
        source,
        receipt=receipt,
        registry=registry,
    )

    assert messages[-1] == {"role": "user", "content": "128 Hz"}
    assert "tool_input_clarification" in messages[1]["content"]
    response = (
        '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
        '"parameters":{"rate":128}}'
    )
    trajectory = evaluate_clarification_trajectory(
        case,
        source,
        admission=admission,
        registry=registry,
        generate_response=lambda _messages: response,
    )

    assert trajectory.final_score.passed is True
    assert trajectory.final_score.product_outcome is not None
    assert trajectory.final_score.product_outcome.disposition == "execute_boundary"
    assert trajectory.final_score.product_outcome.tool_executor_permitted is True


def test_clarification_admission_rejects_incomplete_tool_call_fixture() -> None:
    registry = target_tool_registry()
    source = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "missing_resample_en"
    )

    admission = admit_clarification_receipt(
        source,
        (
            '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
            '"parameters":{}}'
        ),
        expected_tool="resample_data",
        registry=registry,
    )

    assert admission is None


def test_clarification_trajectory_uses_product_format_recovery() -> None:
    registry = target_tool_registry()
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    case = next(
        item
        for item in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=precision_cases,
        )
        if item.expected_tool == "resample_data"
    )
    source = next(
        item for item in precision_cases if item.case_id == case.source_case_id
    )
    responses = iter(
        (
            '{"workflow_stage":"data_loaded","tool_name":"resample_data",',
            (
                '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
                '"parameters":{"rate":128}}'
            ),
        )
    )

    first_response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What resampling rate should I use?",'
        '"pending_action":"resample_data","missing_inputs":["rate"]}}'
    )
    admission = admit_clarification_receipt(
        source,
        first_response,
        expected_tool=case.expected_tool,
        registry=registry,
    )
    assert admission is not None
    trajectory = evaluate_clarification_trajectory(
        case,
        source,
        admission=admission,
        registry=registry,
        generate_response=lambda _messages: next(responses),
    )

    assert trajectory.raw_score.passed is False
    assert trajectory.final_score.passed is True
    assert len(trajectory.attempts) == 2
    assert trajectory.attempts[0].recovery_action == "retry_format"


def test_discriminated_clarification_trajectories_use_scripted_model_turns() -> None:
    registry = target_tool_registry()
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    cases = load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    )
    generic = next(
        case for case in cases if case.trajectory_kind == "generic_filter_selection"
    )
    partial = next(
        case
        for case in cases
        if case.trajectory_kind == "partial_bandpass_accumulation"
    )
    generic_responses = iter(
        (
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"Should I apply a bandpass or notch filter?"}}',
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"What low and high cutoffs should I use?",'
            '"pending_action":"apply_bandpass_filter",'
            '"missing_inputs":["low_freq","high_freq"]}}',
            '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
            '"parameters":{"low_freq":12,"high_freq":40}}',
        )
    )
    partial_responses = iter(
        (
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"What low and high cutoffs should I use?",'
            '"pending_action":"apply_bandpass_filter",'
            '"missing_inputs":["low_freq","high_freq"]}}',
            '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
            '"parameters":{"low_freq":12}}',
            '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
            '"parameters":{"high_freq":128}}',
        )
    )

    generic_result = evaluate_discriminated_clarification_trajectory(
        generic, registry, lambda _messages: next(generic_responses)
    )
    partial_result = evaluate_discriminated_clarification_trajectory(
        partial, registry, lambda _messages: next(partial_responses)
    )

    assert generic_result.final_score.passed is True
    assert partial_result.final_score.passed is True
    assert generic_result.final_score.product_outcome is not None
    assert partial_result.final_score.product_outcome is not None


def test_partial_trajectory_fails_when_controller_rejects_the_partial_proposal() -> (
    None
):
    registry = target_tool_registry()
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    partial = next(
        case
        for case in load_clarification_cases(
            DEFAULT_CLARIFICATION_CASES,
            precision_cases=precision_cases,
        )
        if case.trajectory_kind == "partial_bandpass_accumulation"
    )
    responses = iter(
        (
            '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
            '"parameters":{"message":"What low and high cutoffs should I use?",'
            '"pending_action":"apply_bandpass_filter",'
            '"missing_inputs":["low_freq","high_freq"]}}',
            '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
            '"parameters":{"low_freq":12}}',
        )
    )

    with patch(
        "scripts.dev.run_stable_assistant_model_eval.LLMController._evaluate_tool_proposal",
        return_value=None,
    ):
        result = evaluate_discriminated_clarification_trajectory(
            partial,
            registry,
            lambda _messages: next(responses),
        )

    assert result.final_score.passed is False
    assert result.final_score.failure_type == "partial_accumulation"


def test_precision_scoring_uses_parser_and_host_attempt_outcome_not_keywords() -> None:
    registry = target_tool_registry()
    cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    missing = next(case for case in cases if case.case_id == "missing_bandpass_en")
    out_of_stage = next(
        case for case in cases if case.case_id == "start_before_setup_en"
    )
    general = next(case for case in cases if case.case_id == "general_en")

    direct_response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"Please provide the cutoff values."}}'
    )
    false_completion = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"The filter has been completed."}}'
    )
    placeholder_response = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"<concise response or one clarifying question>"}}'
    )
    model_default = (
        '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
        '"parameters":{"low_freq":0.5,"high_freq":45}}'
    )
    blocked_start = (
        '{"workflow_stage":"data_loaded","tool_name":"start_training","parameters":{}}'
    )
    accidental_navigation = (
        '{"workflow_stage":"empty","tool_name":"switch_panel",'
        '"parameters":{"panel_name":"training"}}'
    )
    wrong_stage_block = (
        '{"workflow_stage":"training","tool_name":"start_training","parameters":{}}'
    )

    direct_score = score_precision_response(missing, direct_response, registry)
    guarded_score = score_precision_response(missing, model_default, registry)
    blocked_score = score_precision_response(out_of_stage, blocked_start, registry)

    assert direct_score.passed is True
    assert score_precision_response(missing, false_completion, registry).passed is False
    assert (
        score_precision_response(missing, placeholder_response, registry).passed
        is False
    )
    assert guarded_score.passed is True
    assert blocked_score.passed is True
    assert (
        score_precision_response(general, accidental_navigation, registry).passed
        is False
    )
    assert (
        score_precision_response(out_of_stage, wrong_stage_block, registry).passed
        is False
    )
    assert direct_score.product_outcome is not None
    assert direct_score.product_outcome.disposition == "respond"
    assert guarded_score.product_outcome is not None
    assert guarded_score.product_outcome.disposition == "respond"
    assert guarded_score.product_outcome.message
    assert blocked_score.product_outcome is not None
    assert blocked_score.product_outcome.disposition == "blocked"
    assert blocked_score.product_outcome.message
    for score in (direct_score, guarded_score, blocked_score):
        outcome = score.product_outcome
        assert outcome is not None
        assert outcome.confirmation_requested is False
        assert outcome.gui_handoff_permitted is False
        assert outcome.application_service_permitted is False
        assert outcome.tool_executor_permitted is False
        assert outcome.state_mutation_permitted is False


def test_raw_missing_parameter_score_requires_the_exact_missing_fields() -> None:
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "missing_bandpass_en"
    )
    incomplete_question = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"Which bandpass filter should I apply?"}}'
    )
    exact_question = (
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What low and high bandpass cutoffs should I use?"}}'
    )
    invented_default = (
        '{"workflow_stage":"data_loaded","tool_name":"apply_bandpass_filter",'
        '"parameters":{"low_freq":1,"high_freq":40}}'
    )

    assert (
        score_raw_precision_response(case, incomplete_question, registry).passed
        is False
    )
    assert score_raw_precision_response(case, exact_question, registry).passed is True
    assert score_precision_response(case, invented_default, registry).passed is True
    assert (
        score_raw_precision_response(case, invented_default, registry).passed is False
    )


def test_raw_model_gate_allows_only_three_noncritical_challenge_wording_failures() -> (
    None
):
    results = [
        {
            "suite": "positive",
            "score": {"passed": True},
            "first_generation_score": {"passed": True, "failure_type": "none"},
        }
        for _ in range(36)
    ]
    results.extend(
        {
            "suite": "challenge",
            "score": {"passed": False},
            "first_generation_score": {
                "passed": index >= 4,
                "failure_type": "response_content" if index < 4 else "none",
            },
        }
        for index in range(14)
    )

    report = _build_report(
        model_id="ibm-granite/granite-4.0-micro",
        results=results,
        expected_case_count=50,
        complete=True,
    )

    assert report["raw_model_gate"]["challenge_decision"] == {
        "required": 14,
        "critical_failures": 0,
        "wording_failures": 4,
        "max_wording_failures": 3,
        "unclassified_failures": 0,
    }
    assert report["raw_model_gate"]["passed"] is False


def test_format_recovery_never_repairs_the_first_generation_raw_model_gate() -> None:
    results = [
        {
            "suite": "positive",
            "score": {"passed": True},
            "first_generation_score": {"passed": True, "failure_type": "none"},
            "post_recovery_score": {"passed": True, "failure_type": "none"},
            **(
                {"parameter_origin_guard": {"applicable": True, "passed": True}}
                if index < 10
                else {}
            ),
        }
        for index in range(36)
    ]
    results.extend(
        {
            "suite": "challenge",
            "score": {"passed": False},
            "first_generation_score": {"passed": True, "failure_type": "none"},
            "post_recovery_score": {"passed": True, "failure_type": "none"},
            **(
                {"host_guard": {"applicable": True, "passed": True}}
                if index < 5
                else {}
            ),
        }
        for index in range(14)
    )
    results.extend(
        {
            "suite": "precision",
            "score": {"passed": True},
            "first_generation_score": {"passed": True, "failure_type": "none"},
            "post_recovery_score": {"passed": True, "failure_type": "none"},
        }
        for _ in range(24)
    )
    results.extend(
        {
            "suite": "clarification",
            "score": {"passed": True},
            "first_generation_score": {
                "passed": index != 0,
                "failure_type": "none" if index else "output_format",
            },
            "post_recovery_score": {"passed": True, "failure_type": "none"},
        }
        for index in range(7)
    )

    report = _build_report(
        model_id="ibm-granite/granite-4.0-micro",
        results=results,
        expected_case_count=50,
        complete=True,
    )

    assert report["first_generation_summary"]["clarification"] == {
        "case_count": 7,
        "passed_count": 6,
        "failed_count": 1,
    }
    assert report["post_recovery_summary"]["clarification"]["passed_count"] == 7
    assert report["raw_model_gate"]["clarification_continuation"] == {
        "required": 7,
        "passed": 6,
    }
    assert report["raw_model_gate"]["passed"] is False


def test_trajectory_retries_format_error_with_product_policy_and_scores_final() -> None:
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "general_en"
    )
    responses = iter(
        (
            '{"workflow_stage":"empty","tool_name":"respond_to_user",',
            (
                '{"workflow_stage":"empty","tool_name":"respond_to_user",'
                '"parameters":{"message":"I can explain the EEG workflow; '
                'which part would you like to understand?"}}'
            ),
        )
    )
    generated_messages: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> str:
        generated_messages.append(messages)
        return next(responses)

    trajectory = evaluate_case_trajectory(case, registry, generate)

    assert trajectory.raw_score.passed is False
    assert trajectory.post_recovery_score.passed is True
    assert trajectory.final_score.passed is True
    assert trajectory.final_response.endswith("}}")
    assert [attempt.recovery_action for attempt in trajectory.attempts] == [
        "retry_format",
        "accept_no_tool",
    ]
    assert [attempt.taxonomy for attempt in trajectory.attempts] == [
        "format_error_retry",
        "recovered_plain_text",
    ]
    assert len(generated_messages) == 2
    assert "FORMAT CORRECTION REQUIRED" in generated_messages[1][1]["content"]
    assert generated_messages[1][-1] == {
        "role": "user",
        "content": case.user_input,
    }


def test_trajectory_exhaustion_is_visible_safe_failure_after_two_retries() -> None:
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "multi_en"
    )
    generated_messages: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> str:
        generated_messages.append(messages)
        return "not one JSON object"

    trajectory = evaluate_case_trajectory(case, registry, generate)

    assert trajectory.raw_score.passed is False
    assert trajectory.final_score.passed is False
    assert trajectory.final_score.failure_type == "output_format"
    assert len(generated_messages) == 3
    assert generated_messages[2][1]["content"].count("FORMAT CORRECTION REQUIRED") == 2
    assert [attempt.recovery_action for attempt in trajectory.attempts] == [
        "retry_format",
        "retry_format",
        "exhausted",
    ]
    outcome = trajectory.final_score.product_outcome
    assert outcome is not None
    assert outcome.disposition == "format_recovery_exhausted"
    assert outcome.message
    assert outcome.confirmation_requested is False
    assert outcome.gui_handoff_permitted is False
    assert outcome.application_service_permitted is False
    assert outcome.tool_executor_permitted is False
    assert outcome.state_mutation_permitted is False


def test_trajectory_retries_stage_mismatch_like_product_controller() -> None:
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "general_en"
    )
    responses = iter(
        (
            (
                '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
                '"parameters":{"message":"How can I help?"}}'
            ),
            (
                '{"workflow_stage":"empty","tool_name":"respond_to_user",'
                '"parameters":{"message":"How can I help with your EEG workflow?"}}'
            ),
        )
    )

    trajectory = evaluate_case_trajectory(
        case,
        registry,
        lambda _messages: next(responses),
    )

    assert trajectory.raw_score.failure_type == "workflow_stage"
    assert trajectory.final_score.passed is True
    assert trajectory.attempts[0].workflow_stage == "data_loaded"
    assert trajectory.attempts[0].envelope_status == "format_error"
    assert trajectory.attempts[0].recovery_action == "retry_format"


def test_trajectory_does_not_turn_recovered_unsafe_action_into_a_pass() -> None:
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "general_en"
    )
    responses = iter(
        (
            "not one JSON object",
            (
                '{"workflow_stage":"empty","tool_name":"switch_panel",'
                '"parameters":{"panel_name":"training"}}'
            ),
        )
    )

    trajectory = evaluate_case_trajectory(
        case,
        registry,
        lambda _messages: next(responses),
    )

    assert trajectory.raw_score.passed is False
    assert trajectory.final_score.passed is False
    assert trajectory.final_score.parsed_tool == "switch_panel"
    assert trajectory.final_score.product_outcome is not None
    assert trajectory.final_score.product_outcome.disposition in {
        "confirmation",
        "execute",
    }


def test_evaluation_uses_product_structured_generation_budget_not_legacy_128_cap() -> (
    None
):
    config = LLMConfig(max_new_tokens=384, do_sample=True)

    policy = _evaluation_generation_policy(config)

    assert policy == {
        "profile": "structured_decision",
        "max_new_tokens": 384,
        "do_sample": False,
        "max_format_recovery_attempts": 2,
    }

    config.max_new_tokens = 1_024
    assert _evaluation_generation_policy(config)["max_new_tokens"] == 512


def test_report_separates_raw_model_host_safety_and_product_outcomes() -> None:
    core_results = (
        [
            {
                "suite": "positive",
                "score": {"passed": True},
                "first_generation_score": {"passed": True, "failure_type": "none"},
                **(
                    {"parameter_origin_guard": {"applicable": True, "passed": True}}
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
                "first_generation_score": {"passed": True, "failure_type": "none"},
                "host_guard": {"applicable": True, "passed": True},
            }
            for _ in range(5)
        ]
        + [
            {
                "suite": "challenge",
                "score": {"passed": False},
                "first_generation_score": {"passed": True, "failure_type": "none"},
            }
            for _ in range(9)
        ]
    )
    report = _build_report(
        model_id="ibm-granite/granite-3.3-2b-instruct",
        results=[
            *core_results,
            *[
                {
                    "suite": "precision",
                    "first_generation_score": {"passed": True, "failure_type": "none"},
                    "score": {"passed": True},
                }
                for index in range(24)
            ],
            *[
                {
                    "suite": "clarification",
                    "first_generation_score": {"passed": True, "failure_type": "none"},
                    "score": {"passed": True},
                }
                for _ in range(7)
            ],
        ],
        expected_case_count=50,
        complete=True,
    )

    assert report["schema_version"] == "xbrainlab.stable_assistant_model_eval.v9"
    assert report["suite_summary"]["positive"]["case_count"] == 36
    assert report["suite_summary"]["challenge"]["case_count"] == 14
    assert report["summary"] == {
        "expected_case_count": 50,
        "case_count": 50,
        "passed_count": 36,
        "failed_count": 14,
        "complete": True,
        "passed": True,
    }
    assert report["precision_summary"] == {
        "expected_case_count": 24,
        "case_count": 24,
        "passed_count": 24,
        "failed_count": 0,
        "complete": True,
        "passed": True,
    }
    assert report["raw_model_gate"]["passed"] is True
    assert report["host_safety_gate"]["passed"] is True
    assert report["product_outcome_gate"]["passed"] is True
    assert report["candidate_gate"]["passed"] is True
    assert report["first_generation_summary"] == {
        "positive": {"case_count": 36, "passed_count": 36, "failed_count": 0},
        "challenge": {"case_count": 14, "passed_count": 14, "failed_count": 0},
        "precision": {"case_count": 24, "passed_count": 24, "failed_count": 0},
        "clarification": {"case_count": 7, "passed_count": 7, "failed_count": 0},
    }
    assert report["clarification_summary"] == {
        "expected_case_count": 7,
        "case_count": 7,
        "passed_count": 7,
        "failed_count": 0,
        "complete": True,
        "passed": True,
    }


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
        '"parameters":{"message":"Please provide the bandpass low and high cutoffs."}}'
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


def test_precision_messages_project_backend_unavailable_actions_without_schemas() -> (
    None
):
    registry = target_tool_registry()
    cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    epochs = next(case for case in cases if case.case_id == "epochs_before_data_en")
    model = next(case for case in cases if case.case_id == "model_before_epochs_en")

    epochs_system = build_case_messages(epochs, registry)[0]["content"]
    model_system = build_case_messages(model, registry)[0]["content"]

    assert "Unavailable Action Reference (not callable):" in epochs_system
    assert (
        '"create_epochs": "Load raw data before creating EEG epochs."' in epochs_system
    )
    assert '"name": "create_epochs"' not in epochs_system
    assert (
        '"select_model": "This action is not callable in workflow stage '
        "'data_loaded'.\"" in model_system
    )
    assert '"name": "select_model"' not in model_system


def test_precision_first_turn_messages_use_the_product_context_projection() -> None:
    """Precision scoring must include the state card that production publishes."""
    registry = target_tool_registry()
    case = next(
        item
        for item in load_precision_cases(DEFAULT_PRECISION_CASES)
        if item.case_id == "missing_bandpass_en"
    )

    messages = build_case_messages(case, registry)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert '"type":"state_card"' in messages[1]["content"]
    assert messages[-1] == {"role": "user", "content": case.user_input}


def test_precision_exact_unavailable_call_uses_backend_reason_at_attempt_boundary() -> (
    None
):
    registry = target_tool_registry()
    case = next(
        case
        for case in load_precision_cases(DEFAULT_PRECISION_CASES)
        if case.case_id == "epochs_before_data_en"
    )
    response = '{"workflow_stage":"empty","tool_name":"create_epochs","parameters":{}}'

    score = score_precision_response(case, response, registry)

    assert score.passed is True
    assert score.product_outcome is not None
    assert score.product_outcome.disposition == "blocked"
    assert score.product_outcome.message is not None
    assert "Load raw data before creating EEG epochs." in score.product_outcome.message


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
                "first_generation_score": {"passed": True, "failure_type": "none"},
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
                "first_generation_score": {"passed": True, "failure_type": "none"},
                "host_guard": {"applicable": True, "passed": True},
            }
            for _ in range(5)
        ]
        + [
            {
                "suite": "challenge",
                "score": {"passed": False},
                "first_generation_score": {"passed": True, "failure_type": "none"},
            }
            for _ in range(9)
        ]
    )

    report = _build_report(
        model_id="ibm-granite/granite-3.3-2b-instruct",
        results=results,
        expected_case_count=50,
        complete=True,
    )

    assert report["candidate_gate"] == {
        "raw_model": False,
        "host_safety": True,
        "product_outcome": False,
        "passed": False,
    }
    assert report["host_safety_gate"]["continuation_boundaries"] == {
        "not_counted_in_model_report": [
            "cancel",
            "topic_switch",
            "stale_receipt",
            "different_tool",
            "partial_reply",
            "multi_action",
        ],
        "report_status": "not_measured_by_this_model_report",
        "external_evidence": "controller unit/integration coverage required",
    }
    assert report["summary"]["passed"] is False
    assert report["precision_summary"] == {
        "expected_case_count": 24,
        "case_count": 0,
        "passed_count": 0,
        "failed_count": 0,
        "complete": False,
        "passed": False,
    }


def test_experiment_identity_binds_source_and_ignores_only_protected_settings(
    tmp_path: Path,
) -> None:
    positives = tmp_path / "positive.json"
    challenges = tmp_path / "challenge.json"
    precision = tmp_path / "precision.json"
    clarification = tmp_path / "clarification.json"
    positives.write_text("positive\n", encoding="utf-8")
    challenges.write_text("challenge\n", encoding="utf-8")
    precision.write_text("precision\n", encoding="utf-8")
    clarification.write_text("clarification\n", encoding="utf-8")

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
            precision_cases_path=precision,
            clarification_cases_path=clarification,
        )

    assert identity["source_sha"] == "abc123"
    assert identity["source_changes_excluding_protected_settings"] == [
        " M scripts/dev/run_stable_assistant_model_eval.py"
    ]
    assert len(identity["positive_cases_sha256"]) == 64
    assert len(identity["challenge_cases_sha256"]) == 64
    assert len(identity["precision_cases_sha256"]) == 64
    assert len(identity["clarification_cases_sha256"]) == 64
