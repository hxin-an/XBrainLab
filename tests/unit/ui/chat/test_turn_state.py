"""Adversarial contract tests for the assistant UI turn state machine."""

from __future__ import annotations

from XBrainLab.llm.agent.assistant_activity import (
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
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
    assert state.complete_admission(first, stopped) is not None
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
    assert state.complete_admission(first, stopped) is not None
    assert state.latch_stop(stopped)

    replacement = state.begin_submission()
    admitted = _correlation(replacement.generation, 21)
    assert state.complete_admission(replacement, admitted) is not None

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
    assert state.complete_admission(submission, active) is not None

    assert not state.accepts_activity(None, AssistantTurnActivityPhase.THINKING)
    assert state.latch_stop(active)
    assert not state.latch_stop(active)
    assert state.phase is AssistantUiTurnPhase.STOPPING
    assert state.lease == active


def test_stopping_accepts_only_the_correlated_terminal_cancellation_response() -> None:
    state = AssistantUiTurnStateMachine()
    submission = state.begin_submission()
    active = _correlation(submission.generation, 31)
    assert state.complete_admission(submission, active) is not None

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
    assert state.complete_admission(first_submission, first) is not None
    assert state.accept_terminal(
        AssistantTurnTerminal(correlation=first, outcome="completed")
    )

    second_submission = state.begin_submission()
    reused = _correlation(second_submission.generation, 44)
    assert state.complete_admission(second_submission, reused) is not None

    assert state.accepts_activity(reused, AssistantTurnActivityPhase.THINKING)
    assert not state.accepts_activity(first, AssistantTurnActivityPhase.THINKING)


def test_shutdown_requires_a_typed_terminal_before_the_state_becomes_idle() -> None:
    state = AssistantUiTurnStateMachine()
    submission = state.begin_submission()
    active = _correlation(submission.generation, 55)
    assert state.complete_admission(submission, active) is not None
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


def test_superseded_completion_cannot_clear_the_newer_provisional_batch() -> None:
    state = AssistantUiTurnStateMachine()
    older = state.begin_submission()
    assert state.defer_controller_event("confirmation", "older")

    newer = state.begin_submission()
    assert state.defer_controller_event("workflow_handoff", "newer")

    assert state.complete_admission(older, _correlation(older.generation, 61)) is None
    assert state.submission == newer
    assert state.complete_admission(
        newer,
        _correlation(newer.generation, 62),
    ) == (("workflow_handoff", "newer"),)


def test_turn_presentation_state_survives_terminal_acceptance_until_rendering_finishes() -> (
    None
):
    state = AssistantUiTurnStateMachine()
    submission = state.begin_submission()
    correlation = _correlation(submission.generation, 63)
    assert state.complete_admission(submission, correlation) is not None
    activity = AssistantTurnActivity(
        AssistantTurnActivityPhase.THINKING,
        turn_id=correlation.turn_id,
        generation=correlation.generation,
    )
    state.record_activity(activity)
    state.set_prune_notice_pending(True)

    assert state.accept_terminal(AssistantTurnTerminal(correlation=correlation))
    assert state.last_activity is activity
    assert state.pending_prune_notice is True

    state.clear_prune_notice()
    state.clear_activity()
    assert state.last_activity is None
    assert state.pending_prune_notice is False


def test_stale_rejection_cannot_clear_the_newer_provisional_batch() -> None:
    state = AssistantUiTurnStateMachine()
    older = state.begin_submission()
    newer = state.begin_submission()

    assert not state.reject_admission(older)
    assert state.submission == newer
    assert state.defer_controller_event("confirmation", "newer")
    assert state.complete_admission(
        newer,
        _correlation(newer.generation, 64),
    ) == (("confirmation", "newer"),)
