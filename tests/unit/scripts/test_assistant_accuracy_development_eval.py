"""Development-only product-path accuracy evaluator contracts."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scripts.dev.assistant_accuracy_case_packs import load_development_cases
from scripts.dev.run_assistant_accuracy_development_eval import (
    DevelopmentCaseOutcome,
    EvaluatorLifecycleOutcome,
    development_experiment_identity,
    evaluate_development_case,
    run_development_eval,
)
from scripts.dev.run_stable_assistant_model_eval import target_tool_registry


def _expected_response(case, turn) -> str:
    if turn.expected_boundary == "typed_receipt":
        assert turn.receipt is not None
        if turn.receipt.verified_values:
            return json.dumps(
                {
                    "workflow_stage": case.workflow_stage,
                    "tool_name": turn.expected_tool,
                    "parameters": turn.expected_parameters,
                }
            )
        return json.dumps(
            {
                "workflow_stage": case.workflow_stage,
                "tool_name": "respond_to_user",
                "parameters": {
                    "message": "Please provide the remaining value.",
                    "pending_action": turn.expected_tool,
                    "missing_inputs": list(turn.receipt.missing_inputs),
                },
            }
        )
    if turn.expected_boundary == "verified_execute":
        return json.dumps(
            {
                "workflow_stage": case.workflow_stage,
                "tool_name": turn.expected_tool,
                "parameters": turn.expected_parameters,
            }
        )
    return json.dumps(
        {
            "workflow_stage": case.workflow_stage,
            "tool_name": "respond_to_user",
            "parameters": {"message": "I will not run an action."},
        }
    )


def _oracle_response(case, turn_index: int, turn) -> str:
    if turn_index == 1 and case.category == "different_tool":
        return json.dumps(
            {
                "workflow_stage": case.workflow_stage,
                "tool_name": "resample_data",
                "parameters": {"rate": 128},
            }
        )
    if turn_index == 1 and case.category == "stale_generation":
        return json.dumps(
            {
                "workflow_stage": case.workflow_stage,
                "tool_name": "resample_data",
                "parameters": {"rate": 100},
            }
        )
    return _expected_response(case, turn)


def _oracle_responses(case):
    """Yield the frozen development oracle, including its format repair turn."""
    for index, turn in enumerate(case.turns):
        if case.category == "format_recovery" and index == 0:
            yield "{not-json"
        yield _oracle_response(case, index, turn)


def _evaluate_oracle_case(case):
    responses = iter(_oracle_responses(case))
    return evaluate_development_case(
        case,
        target_tool_registry(),
        lambda _messages: next(responses),
    )


@pytest.mark.parametrize(
    "category",
    ("cancellation", "different_tool", "stale_generation"),
)
def test_response_terminal_clears_a_real_receipt_without_execution(
    category: str,
) -> None:
    case = next(item for item in load_development_cases() if item.category == category)
    responses = iter(
        _oracle_response(case, index, turn) for index, turn in enumerate(case.turns)
    )

    result = evaluate_development_case(
        case,
        target_tool_registry(),
        lambda _messages: next(responses),
    )

    response_turns = [
        turn for turn in result.turns if turn.expected_boundary == "respond"
    ]
    assert response_turns
    assert all(turn.composed.boundary == "respond" for turn in response_turns)
    assert all(turn.composed.receipt_active is False for turn in response_turns)
    assert all(turn.composed.receipt_pending is False for turn in response_turns)
    assert all(
        turn.safety.verified_execute_boundary_intercepted == 0
        for turn in response_turns
    )
    assert all(turn.safety.executable_path_guard_calls == 0 for turn in response_turns)
    if category != "cancellation":
        assert all(turn.composed.attempt_action == "respond" for turn in response_turns)
    assert result.lifecycle.controller_closed is True
    assert result.lifecycle.worker_cleared is True
    assert result.lifecycle.worker_thread_stopped is True


def test_partial_accumulation_and_exact_continuation_reach_only_the_sentinel() -> None:
    case = next(
        item
        for item in load_development_cases()
        if item.category == "partial_accumulation"
    )
    responses = iter(_expected_response(case, turn) for turn in case.turns)

    result = evaluate_development_case(
        case,
        target_tool_registry(),
        lambda _messages: next(responses),
    )

    assert result.passed is True
    assert result.turns[-1].composed.boundary == "verified_execute"
    assert result.turns[-1].safety.verified_execute_boundary_intercepted == 1
    assert result.turns[-1].safety.executable_path_guard_calls == 0
    assert result.turns[-1].safety.tool_executor_guard_calls == 0
    assert result.turns[-1].safety.application_command_started_signals == 0
    assert result.turns[-1].safety.publication_state_changed is False


def test_full_primary_and_each_repair_output_are_retained_separately() -> None:
    case = next(item for item in load_development_cases() if item.category == "general")
    turn = case.turns[0]
    raw_primary = "  {" + ("not-json" * 300) + "  "
    responses = iter((raw_primary, _expected_response(case, turn)))

    result = evaluate_development_case(
        case,
        target_tool_registry(),
        lambda _messages: next(responses),
    )

    outcome = result.turns[0]
    assert outcome.raw_primary.response == raw_primary
    assert outcome.raw_primary.recovery_action == "retry_format"
    assert len(outcome.strict_recovery.repair_attempts) == 1
    repair = outcome.strict_recovery.repair_attempts[0]
    assert repair.attempt_number == 2
    assert repair.response == _expected_response(case, turn)
    assert repair.recovery_action == "accept_no_tool"
    assert repair.taxonomy
    assert outcome.composed.boundary == "respond"


def test_all_development_oracle_trajectories_use_real_terminal_lifecycle() -> None:
    results = tuple(_evaluate_oracle_case(case) for case in load_development_cases())

    assert len(results) == 48
    failures = {
        result.case_id: [
            (
                turn.expected_boundary,
                turn.composed.boundary,
                turn.composed.detail,
                turn.raw_primary.recovery_action,
                turn.strict_recovery.exhausted,
                turn.composed.attempt_action,
                turn.safety.verified_execute_boundary_intercepted,
                turn.safety.controller_terminal_signals,
            )
            for turn in result.turns
            if not turn.composed.passed
        ]
        for result in results
        if not result.passed
    }
    assert not failures, failures
    assert all(
        result.lifecycle.controller_closed
        and result.lifecycle.worker_cleared
        and result.lifecycle.worker_thread_stopped
        and result.lifecycle.shutdown_signal_count == 1
        for result in results
    )


def test_identity_binds_the_development_only_scorer_inputs() -> None:
    identity = development_experiment_identity(
        model_id="ibm-granite/granite-4.0-micro",
        generation_policy={"profile": "structured_decision"},
    )

    assert identity["development_cases_sha256"]
    assert identity["source_sha"]
    assert identity["model"]["revision"]
    assert identity["prompt_policy_sha256"]
    assert identity["context_assembler_sha256"]
    assert identity["parser_sha256"]
    assert identity["strict_recovery_policy_sha256"]
    assert identity["verification_layer_sha256"]
    assert identity["tool_attempt_coordinator_sha256"]
    assert identity["pending_interaction_coordinator_sha256"]
    assert identity["application_view_publication_sha256"]
    assert identity["capability_policy_sha256"]
    assert identity["scorer_sha256"]
    assert "source_changes_excluding_protected_settings" in identity
    assert isinstance(identity["source_is_clean_excluding_protected_settings"], bool)


def test_identity_excludes_only_the_protected_root_settings_file() -> None:
    with patch(
        "scripts.dev.run_assistant_accuracy_development_eval.subprocess.check_output",
        side_effect=[
            "abc123\n",
            " M settings.json\n M scripts/dev/run_assistant_accuracy_development_eval.py\n",
        ],
    ):
        identity = development_experiment_identity(
            model_id="ibm-granite/granite-4.0-micro",
            generation_policy={"profile": "structured_decision"},
        )

    assert identity["source_sha"] == "abc123"
    assert identity["source_changes_excluding_protected_settings"] == [
        " M scripts/dev/run_assistant_accuracy_development_eval.py"
    ]
    assert identity["source_is_clean_excluding_protected_settings"] is False


def test_development_runner_checkpoints_every_completed_case_and_reports_progress(
    tmp_path, capsys
) -> None:
    """A crash-resilient run exposes bounded progress before final completion."""
    checkpoints: list[tuple[bool, int]] = []
    config = MagicMock()
    config.assistant_runtime_selection.return_value = SimpleNamespace(
        backend_mode="local",
        model_id="ibm-granite/granite-4.0-micro",
    )
    config.local_backend_ready.return_value = True

    def fake_case_outcome(case, _registry, _generate_response):
        return DevelopmentCaseOutcome(
            case.case_id,
            (),
            EvaluatorLifecycleOutcome(1, True, True, True),
        )

    def record_checkpoint(_path, report) -> None:
        checkpoints.append((report["complete"], report["summary"]["case_count"]))

    with (
        patch(
            "scripts.dev.run_assistant_accuracy_development_eval.LLMEngine"
        ) as engine_type,
        patch(
            "scripts.dev.run_assistant_accuracy_development_eval."
            "_evaluation_generation_policy",
            return_value={"profile": "structured_decision"},
        ),
        patch(
            "scripts.dev.run_assistant_accuracy_development_eval."
            "development_experiment_identity",
            return_value={"source_sha": "test"},
        ),
        patch(
            "scripts.dev.run_assistant_accuracy_development_eval."
            "evaluate_development_case",
            side_effect=fake_case_outcome,
        ),
        patch(
            "scripts.dev.run_assistant_accuracy_development_eval."
            "_write_development_report",
            side_effect=record_checkpoint,
        ),
    ):
        report = run_development_eval(config, checkpoint_path=tmp_path / "report.json")

    assert checkpoints == [(False, index) for index in range(1, 49)] + [(True, 48)]
    progress_lines = capsys.readouterr().err.splitlines()
    assert len(progress_lines) == 48
    assert progress_lines[0].startswith("Assistant development eval 1/48:")
    assert progress_lines[-1].startswith("Assistant development eval 48/48:")
    assert report["complete"] is True
    engine_type.return_value.load_model.assert_called_once_with()
    engine_type.return_value.close.assert_called_once_with()
