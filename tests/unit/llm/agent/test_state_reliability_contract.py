"""Fail-closed state reliability contracts for assistant workflow execution."""

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.tools.application_surface import ToolCommandResult


def test_only_typed_application_snapshot_can_be_reliable() -> None:
    assert LLMController._state_snapshot_reliable(ApplicationStateSnapshot.empty())
    assert not LLMController._state_snapshot_reliable(
        SimpleNamespace(state_reliable=True, read_errors=[])
    )
    assert not LLMController._state_snapshot_reliable(
        SimpleNamespace(to_dict=lambda: {"state_reliable": True})
    )


def test_typed_snapshot_reliability_requires_exact_true_and_no_read_errors() -> None:
    snapshot = ApplicationStateSnapshot.empty()

    assert not LLMController._state_snapshot_reliable(
        replace(snapshot, state_reliable=False)
    )
    assert not LLMController._state_snapshot_reliable(
        replace(snapshot, read_errors=["partial state read failed"])
    )
    assert not LLMController._state_snapshot_reliable(
        replace(snapshot, state_reliable=cast(Any, 1))
    )


def test_recoverable_failure_without_explicit_reliable_state_waits_for_user() -> None:
    reliable = ApplicationStateSnapshot.empty().to_dict()
    contradictory = {**reliable, "read_errors": ["state read failed"]}
    malformed_errors = {**reliable, "read_errors": "state read failed"}
    for state in (
        {},
        {"state_reliable": True},
        {"state_reliable": "true"},
        contradictory,
        malformed_errors,
        None,
    ):
        result = ToolCommandResult.failure(
            "query_state",
            "State could not be verified.",
            recoverable=True,
            state=cast(Any, state),
        )

        assert LLMController._should_wait_for_user_after_tool_failure(result)


def test_recoverable_failure_with_explicit_reliable_state_can_retry() -> None:
    result = ToolCommandResult.failure(
        "query_state",
        "Temporary backend failure.",
        recoverable=True,
        state=ApplicationStateSnapshot.empty().to_dict(),
    )

    assert not LLMController._should_wait_for_user_after_tool_failure(result)
