"""Exact state machine for one UI generation and runtime turn lease."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from XBrainLab.llm.agent.assistant_activity import (
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation, AssistantTurnTerminal


class AssistantUiTurnPhase(str, Enum):
    """Durable UI ownership phase for one assistant turn."""

    IDLE = "idle"
    ACTIVE = "active"
    STOPPING = "stopping"


@dataclass(frozen=True, slots=True)
class AssistantUiTurnSubmission:
    """Provisional UI generation awaiting runtime admission."""

    generation: int

    def __post_init__(self) -> None:
        if isinstance(self.generation, bool) or not isinstance(self.generation, int):
            raise TypeError("Assistant UI generations must be integers.")
        if self.generation <= 0:
            raise ValueError("Assistant UI generations must be positive.")


class AssistantUiTurnStateMachine:
    """Own provisional admission and one exact admitted turn correlation."""

    def __init__(self) -> None:
        self._generation = 0
        self._submission: AssistantUiTurnSubmission | None = None
        self._provisional_events: list[tuple[str, object]] | None = None
        self._lease: AssistantTurnCorrelation | None = None
        self._phase = AssistantUiTurnPhase.IDLE
        self._last_activity: AssistantTurnActivity | None = None
        self._pending_prune_notice = False

    @property
    def phase(self) -> AssistantUiTurnPhase:
        return self._phase

    @property
    def submission(self) -> AssistantUiTurnSubmission | None:
        return self._submission

    @property
    def lease(self) -> AssistantTurnCorrelation | None:
        return self._lease

    @property
    def last_activity(self) -> AssistantTurnActivity | None:
        """Return the accepted activity for the current UI turn."""
        return self._last_activity

    @property
    def pending_prune_notice(self) -> bool:
        """Whether the admitted transcript turn still owns its prune notice."""
        return self._pending_prune_notice

    def begin_submission(self) -> AssistantUiTurnSubmission:
        self._generation += 1
        submission = AssistantUiTurnSubmission(self._generation)
        self._submission = submission
        self._provisional_events = []
        return submission

    def reject_admission(self, submission: AssistantUiTurnSubmission) -> bool:
        if submission != self._submission:
            return False
        self._submission = None
        self._provisional_events = None
        return True

    def complete_admission(
        self,
        submission: AssistantUiTurnSubmission,
        correlation: AssistantTurnCorrelation,
    ) -> tuple[tuple[str, object], ...] | None:
        """Commit one matching admission and return its ordered event batch.

        ``None`` rejects an invalid or superseded admission.  An empty tuple is
        a successful admission with no synchronous controller events.
        """
        if not isinstance(correlation, AssistantTurnCorrelation):
            return None
        if submission != self._submission:
            return None
        if correlation.generation != submission.generation:
            return None
        events = tuple(self._provisional_events or ())
        self._submission = None
        self._provisional_events = None
        self._lease = correlation
        self._phase = AssistantUiTurnPhase.ACTIVE
        return events

    def defer_turn_event(
        self,
        event_kind: str,
        payload: object,
        correlation: AssistantTurnCorrelation | None,
    ) -> bool:
        """Queue a synchronous correlated event for its provisional generation."""
        submission = self._submission
        events = self._provisional_events
        if (
            events is None
            or submission is None
            or correlation is None
            or correlation.generation != submission.generation
        ):
            return False
        events.append((event_kind, payload))
        return True

    def defer_controller_event(self, event_kind: str, payload: object) -> bool:
        """Queue a synchronous controller decision until admission has a lease."""
        events = self._provisional_events
        if events is None or self._submission is None:
            return False
        events.append((event_kind, payload))
        return True

    def set_prune_notice_pending(self, pending: bool) -> None:
        """Record the current admitted transcript's bounded-history notice."""
        self._pending_prune_notice = bool(pending)

    def record_activity(self, activity: AssistantTurnActivity) -> None:
        """Retain an already accepted activity for turn-local UI decisions."""
        self._last_activity = activity

    def clear_prune_notice(self) -> None:
        """Release the admitted transcript's prune notice."""
        self._pending_prune_notice = False

    def clear_activity(self) -> None:
        """Release the accepted activity after its terminal UI work finishes."""
        self._last_activity = None

    def latch_stop(self, correlation: AssistantTurnCorrelation) -> bool:
        if correlation != self._lease:
            return False
        if self._phase is AssistantUiTurnPhase.STOPPING:
            return False
        if self._phase is not AssistantUiTurnPhase.ACTIVE:
            return False
        self._phase = AssistantUiTurnPhase.STOPPING
        return True

    def accepts_activity(
        self,
        correlation: AssistantTurnCorrelation | None,
        phase: AssistantTurnActivityPhase,
    ) -> bool:
        if not isinstance(phase, AssistantTurnActivityPhase):
            return False
        if correlation is None or correlation != self._lease:
            return False
        if self._phase is AssistantUiTurnPhase.STOPPING:
            return phase is AssistantTurnActivityPhase.STOPPING
        return self._phase is AssistantUiTurnPhase.ACTIVE

    def accepts_response(
        self,
        correlation: AssistantTurnCorrelation | None,
        *,
        terminal_cancellation: bool = False,
    ) -> bool:
        """Accept normal responses while active and one typed Stop conclusion."""
        if correlation is None or correlation != self._lease:
            return False
        if self._phase is AssistantUiTurnPhase.ACTIVE:
            return True
        return bool(
            self._phase is AssistantUiTurnPhase.STOPPING and terminal_cancellation
        )

    def accept_terminal(self, terminal: AssistantTurnTerminal) -> bool:
        if not isinstance(terminal, AssistantTurnTerminal):
            return False
        if terminal.correlation != self._lease:
            return False
        self._lease = None
        self._phase = AssistantUiTurnPhase.IDLE
        return True

    def shutdown_terminal(self) -> AssistantTurnTerminal | None:
        if self._lease is None:
            return None
        return AssistantTurnTerminal(
            correlation=self._lease,
            outcome="shutdown_cancelled",
        )

    def reset_idle(self) -> bool:
        if self._lease is not None or self._submission is not None:
            return False
        self._phase = AssistantUiTurnPhase.IDLE
        self._provisional_events = None
        self.clear_prune_notice()
        self.clear_activity()
        return True
