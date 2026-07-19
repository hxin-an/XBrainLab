"""Adversarial contract tests for the assistant UI turn state machine."""

from __future__ import annotations

from XBrainLab.llm.agent.assistant_activity import AssistantTurnActivityPhase
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation, AssistantTurnTerminal
from XBrainLab.ui.chat.turn_state import (
    AssistantUiTurnPhase,
    AssistantUiTurnStateMachine,
)


def _correlation(generation: int, turn_id: int) -> AssistantTurnCorrelation:
    return AssistantTurnCorrelation(generation=generation, turn_id=turn_id)


def test_rejected_provisional_submission_preserves_exact_stopping_lease() -> None:
    state = AssistantUiTurnStateMachine()
    first = state.begin_submission()
    stopped = _correlation(first.generation, 17)
    assert state.accept_admission(first, stopped)
    assert state.latch_stop(stopped)

    provisional = state.begin_submission()
    assert state.phase is AssistantUiTurnPhase.STOPPING
    assert not state.accepts_activity(
        _correlation(provisional.generation, 18),
        AssistantTurnActivityPhase.THINKING,
    )
    assert state.reject_admission(provisional)

    assert state.phase is AssistantUiTurnPhase.STOPPING
    assert state.lease == stopped


def test_only_successful_admission_may_supersede_a_stopping_generation() -> None:
    state = AssistantUiTurnStateMachine()
    first = state.begin_submission()
    stopped = _correlation(first.generation, 20)
    assert state.accept_admission(first, stopped)
    assert state.latch_stop(stopped)

    replacement = state.begin_submission()
    admitted = _correlation(replacement.generation, 21)
    assert state.accept_admission(replacement, admitted)

    assert state.phase is AssistantUiTurnPhase.ACTIVE
    assert state.lease == admitted
    assert not state.accepts_activity(
        stopped,
        AssistantTurnActivityPhase.RUNNING_COMMAND,
    )


def test_missing_correlation_is_never_a_wildcard_and_double_stop_is_idempotent() -> (
    None
):
    state = AssistantUiTurnStateMachine()
    submission = state.begin_submission()
    active = _correlation(submission.generation, 30)
    assert state.accept_admission(submission, active)

    assert not state.accepts_activity(None, AssistantTurnActivityPhase.THINKING)
    assert state.latch_stop(active)
    assert not state.latch_stop(active)
    assert state.phase is AssistantUiTurnPhase.STOPPING
    assert state.lease == active


def test_stopping_accepts_only_the_correlated_terminal_cancellation_response() -> None:
    state = AssistantUiTurnStateMachine()
    submission = state.begin_submission()
    active = _correlation(submission.generation, 31)
    assert state.accept_admission(submission, active)

    assert state.accepts_response(active)
    assert state.latch_stop(active)
    assert not state.accepts_response(active)
    assert state.accepts_response(active, terminal_cancellation=True)
    assert not state.accepts_response(
        _correlation(active.generation, active.turn_id + 1),
        terminal_cancellation=True,
    )


def test_reused_runtime_turn_id_is_scoped_by_ui_generation_not_poisoned_globally() -> (
    None
):
    state = AssistantUiTurnStateMachine()
    first_submission = state.begin_submission()
    first = _correlation(first_submission.generation, 44)
    assert state.accept_admission(first_submission, first)
    assert state.accept_terminal(
        AssistantTurnTerminal(correlation=first, outcome="completed")
    )

    second_submission = state.begin_submission()
    reused = _correlation(second_submission.generation, 44)
    assert state.accept_admission(second_submission, reused)

    assert state.accepts_activity(reused, AssistantTurnActivityPhase.THINKING)
    assert not state.accepts_activity(first, AssistantTurnActivityPhase.THINKING)


def test_shutdown_requires_a_typed_terminal_before_the_state_becomes_idle() -> None:
    state = AssistantUiTurnStateMachine()
    submission = state.begin_submission()
    active = _correlation(submission.generation, 55)
    assert state.accept_admission(submission, active)
    assert state.latch_stop(active)

    terminal = state.shutdown_terminal()

    assert terminal is not None
    assert terminal == AssistantTurnTerminal(
        correlation=active,
        outcome="shutdown_cancelled",
    )
    assert state.phase is AssistantUiTurnPhase.STOPPING
    assert state.accept_terminal(terminal)
    assert state.phase is AssistantUiTurnPhase.IDLE
