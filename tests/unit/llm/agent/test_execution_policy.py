"""Tests for the one-action host safety boundary."""

from types import SimpleNamespace

from XBrainLab.llm.agent.execution_policy import HostExecutionPolicy


def test_only_first_model_proposal_is_eligible_for_execution() -> None:
    policy = HostExecutionPolicy()

    assert policy.first_command([("one", {}), ("two", {})]) == ("one", {})


def test_every_turn_is_limited_to_one_action() -> None:
    policy = HostExecutionPolicy()

    first = policy.before_command(
        execution_count=0,
        cancelled=False,
    )
    second = policy.before_command(
        execution_count=1,
        cancelled=False,
    )

    assert (first.continue_workflow, first.reason) == (True, "execute")
    assert (second.continue_workflow, second.reason) == (False, "tool_cap")


def test_cancelled_turn_never_starts_an_action() -> None:
    decision = HostExecutionPolicy().before_command(
        execution_count=0,
        cancelled=True,
    )

    assert (decision.continue_workflow, decision.reason) == (False, "cancelled")


def test_backend_capability_remains_confirmation_authority() -> None:
    availability = SimpleNamespace(
        requires_confirmation=False,
        confirmation_required=False,
        long_running=False,
        destructive=False,
        can_auto_execute=False,
    )

    assert HostExecutionPolicy.needs_confirmation(
        availability,
        tool_requires_confirmation=False,
    )
