"""Exact state machine for one UI generation and runtime turn lease."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from XBrainLab.llm.agent.assistant_activity import (
    AssistantDecisionOwner,
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation, AssistantTurnTerminal
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffKind,
    WorkflowUiHandoffRequest,
)


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
        return submission

    def reject_admission(self, submission: AssistantUiTurnSubmission) -> bool:
        if submission != self._submission:
            return False
        self._submission = None
        return True

    def complete_admission(
        self,
        submission: AssistantUiTurnSubmission,
        correlation: AssistantTurnCorrelation,
    ) -> bool:
        """Commit the exact reservation before queued controller events arrive."""
        if not isinstance(correlation, AssistantTurnCorrelation):
            return False
        if submission != self._submission:
            return False
        if correlation.generation != submission.generation:
            return False
        self._submission = None
        self._lease = correlation
        self._phase = AssistantUiTurnPhase.ACTIVE
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

    def accepts_confirmation(self, *, request_id: str, command_name: str) -> bool:
        """Bind one confirmation card to the exact active UI/runtime turn."""
        activity = self._last_activity
        lease = self._lease
        return bool(
            lease is not None
            and isinstance(activity, AssistantTurnActivity)
            and activity.phase is AssistantTurnActivityPhase.WAITING_FOR_DECISION
            and activity.decision_owner is AssistantDecisionOwner.CONFIRMATION_CARD
            and activity.correlation == lease
            and activity.request_id == request_id
            and activity.command_name == command_name
        )

    def accepts_workflow_handoff(self, request: WorkflowUiHandoffRequest) -> bool:
        """Bind one product-UI request to its exact active waiting lease."""
        activity = self._last_activity
        lease = self._lease
        if request.kind is WorkflowUiHandoffKind.ACTION_REQUESTED:
            phase_matches = bool(
                isinstance(activity, AssistantTurnActivity)
                and activity.phase is AssistantTurnActivityPhase.RUNNING_COMMAND
                and activity.decision_owner is None
            )
        else:
            phase_matches = bool(
                isinstance(activity, AssistantTurnActivity)
                and activity.phase is AssistantTurnActivityPhase.WAITING_FOR_DECISION
                and activity.decision_owner is AssistantDecisionOwner.GUI_DIALOG
            )
        return bool(
            lease is not None
            and isinstance(activity, AssistantTurnActivity)
            and phase_matches
            and activity.correlation == lease
            and activity.request_id == request.request_id
            and activity.command_name == request.tool_name
        )

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
        self.clear_prune_notice()
        self.clear_activity()
        return True
