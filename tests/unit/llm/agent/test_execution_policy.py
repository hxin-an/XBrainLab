"""Host-side execution policy tests for Ask and Workflow modes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from XBrainLab.llm.agent.execution_policy import (
    ExecutionSnapshot,
    HostExecutionPolicy,
)


def _availability(**overrides):
    values = {
        "requires_confirmation": False,
        "confirmation_required": False,
        "decision_boundary": None,
        "continue_allowed_after_success": True,
        "stop_after_success": False,
        "long_running": False,
        "destructive": False,
        "retry_limit": 2,
        "can_auto_execute": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _snapshot(**overrides) -> ExecutionSnapshot:
    values = {
        "state_reliable": True,
        "decision_needed": (),
        "can_auto_continue": True,
        "next_requires_confirmation": False,
        "next_decision_boundary": None,
        "next_long_running": False,
        "next_destructive": False,
        "next_continue_allowed_after_success": True,
        "next_stop_after_success": False,
        "read_error": None,
    }
    values.update(overrides)
    return ExecutionSnapshot(**values)


def test_only_first_model_proposal_is_eligible_for_execution() -> None:
    policy = HostExecutionPolicy()

    assert policy.first_command([("one", {}), ("two", {})]) == ("one", {})


def test_ask_prevents_a_second_tool_attempt_in_same_user_turn() -> None:
    decision = HostExecutionPolicy().before_command(
        mode="single",
        execution_count=1,
        workflow_tool_cap=5,
        cancelled=False,
    )

    assert decision.continue_workflow is False
    assert decision.reason == "tool_cap"


def test_non_auto_executable_command_requires_host_confirmation() -> None:
    assert HostExecutionPolicy().needs_confirmation(
        _availability(can_auto_execute=False),
        tool_requires_confirmation=False,
    )


def test_ask_never_continues_after_a_tool_attempt() -> None:
    policy = HostExecutionPolicy()

    decision = policy.after_success(
        mode="single",
        availability=_availability(),
        snapshot=_snapshot(),
        execution_count=1,
        tool_cap=5,
    )

    assert decision.continue_workflow is False
    assert decision.reason == "ask_tool_limit"


@pytest.mark.parametrize(
    ("availability", "snapshot", "reason"),
    [
        (_availability(), _snapshot(state_reliable=False), "state_unreliable"),
        (
            _availability(),
            _snapshot(decision_needed=("epoch_window",)),
            "decision_needed",
        ),
        (
            _availability(requires_confirmation=True),
            _snapshot(),
            "requires_confirmation",
        ),
        (
            _availability(stop_after_success=True),
            _snapshot(),
            "stop_after_success",
        ),
        (
            _availability(continue_allowed_after_success=False),
            _snapshot(),
            "continuation_disallowed",
        ),
        (_availability(long_running=True), _snapshot(), "long_running"),
        (_availability(destructive=True), _snapshot(), "destructive"),
        (
            _availability(),
            _snapshot(next_requires_confirmation=True),
            "next_requires_confirmation",
        ),
    ],
)
def test_workflow_host_stop_conditions(availability, snapshot, reason) -> None:
    decision = HostExecutionPolicy().after_success(
        mode="multi",
        availability=availability,
        snapshot=snapshot,
        execution_count=1,
        tool_cap=5,
    )

    assert decision.continue_workflow is False
    assert decision.reason == reason


def test_descriptive_boundary_does_not_override_auto_continue_policy() -> None:
    decision = HostExecutionPolicy().after_success(
        mode="multi",
        availability=_availability(
            decision_boundary="semantic_preview",
            can_auto_execute=True,
            continue_allowed_after_success=True,
        ),
        snapshot=_snapshot(
            can_auto_continue=True,
            next_decision_boundary="semantic_validation",
        ),
        execution_count=1,
        tool_cap=5,
    )

    assert decision.continue_workflow is True
    assert decision.reason == "continue"


def test_workflow_can_continue_only_after_safe_refresh() -> None:
    decision = HostExecutionPolicy().after_success(
        mode="multi",
        availability=_availability(),
        snapshot=_snapshot(),
        execution_count=1,
        tool_cap=5,
    )

    assert decision.continue_workflow is True
    assert decision.reason == "continue"


def test_confirmation_boundary_always_stops_the_original_batch() -> None:
    decision = HostExecutionPolicy().after_success(
        mode="multi",
        availability=_availability(),
        snapshot=_snapshot(),
        execution_count=1,
        tool_cap=5,
        after_confirmation=True,
    )

    assert decision.continue_workflow is False
    assert decision.reason == "confirmed_boundary"


@pytest.mark.parametrize(
    ("mode", "failure_count", "retry_limit", "cancelled", "expected"),
    [
        ("single", 0, 2, False, False),
        ("multi", 1, 2, False, True),
        ("multi", 2, 2, False, False),
        ("multi", 0, 2, True, False),
    ],
)
def test_retry_policy_is_host_enforced(
    mode: str,
    failure_count: int,
    retry_limit: int,
    cancelled: bool,
    expected: bool,
) -> None:
    decision = HostExecutionPolicy().after_failure(
        mode=mode,
        availability=_availability(retry_limit=retry_limit),
        failure_count=failure_count,
        global_retry_limit=3,
        execution_count=1,
        tool_cap=5,
        cancelled=cancelled,
    )

    assert decision.continue_workflow is expected
