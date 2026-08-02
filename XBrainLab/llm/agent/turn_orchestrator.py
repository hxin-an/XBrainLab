"""Non-Qt lifecycle owners for one assistant turn and its tool attempts."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field

from XBrainLab.backend.application import CommandName

from .assembler import PromptToolPublication
from .response_presentation import AssistantResponseKind
from .turn import (
    AssistantGenerationDispatchPhase,
    AssistantGenerationEventPhase,
    AssistantTurnCorrelation,
    AssistantTurnRequest,
    AssistantTurnScope,
)


@dataclass
class AssistantTurnOrchestrator:
    """Own correlated host, RAG, generation, and cancellation transitions."""

    host_turn_id: int | None = None
    host_turn_generation: int | None = None
    scope: AssistantTurnScope | None = None
    terminal_command: str | None = None
    excluded_commands: frozenset[CommandName] = field(default_factory=frozenset)
    generation_sequence: int = 0
    active_generation_id: int | None = None
    dispatch_phase: AssistantGenerationDispatchPhase | None = None
    dispatch_in_progress: bool = False
    stopping_generation_id: int | None = None
    rag_sequence: int = 0
    active_rag_turn_id: int | None = None
    waiting_for_rag: bool = False
    admitted_command_name: str | None = None
    admitted_publication_generation: int | None = None
    active_publication: PromptToolPublication = field(
        default_factory=PromptToolPublication.empty
    )
    cancelled: bool = False
    cancellation_response_sent: bool = False

    @property
    def correlation(self) -> AssistantTurnCorrelation | None:
        if self.host_turn_id is None or self.host_turn_generation is None:
            return None
        return AssistantTurnCorrelation(
            generation=self.host_turn_generation,
            turn_id=self.host_turn_id,
        )

    @property
    def has_active_host_turn(self) -> bool:
        return self.host_turn_id is not None

    def bind_host_turn(self, request: AssistantTurnRequest) -> None:
        """Bind one typed host turn and its immutable endpoint policy."""
        if self.has_active_host_turn:
            raise RuntimeError("An assistant host turn is already active.")
        self.host_turn_id = request.turn_id
        self.host_turn_generation = request.generation
        self.scope = request.scope
        self.terminal_command = request.terminal_command
        self.excluded_commands = frozenset(request.excluded_commands)

    def bind_correlation(self, correlation: AssistantTurnCorrelation) -> None:
        """Bind a host correlation for diagnostic requests without turn policy."""
        if self.has_active_host_turn:
            raise RuntimeError("An assistant host turn is already active.")
        self.host_turn_id = correlation.turn_id
        self.host_turn_generation = correlation.generation

    def finish_host_turn(self) -> AssistantTurnCorrelation | None:
        """Consume the active correlation once and clear terminal turn state."""
        correlation = self.correlation
        self.host_turn_id = None
        self.host_turn_generation = None
        self.scope = None
        self.terminal_command = None
        self.excluded_commands = frozenset()
        self.active_generation_id = None
        self.dispatch_phase = None
        self.stopping_generation_id = None
        return correlation

    def begin_rag_turn(self) -> int:
        self.rag_sequence += 1
        self.active_rag_turn_id = self.rag_sequence
        self.waiting_for_rag = True
        return self.rag_sequence

    def invalidate_rag_turn(self) -> int | None:
        active_turn_id = self.active_rag_turn_id
        self.rag_sequence += 1
        self.active_rag_turn_id = None
        self.waiting_for_rag = False
        return active_turn_id

    def accept_rag_result(self, turn_id: int) -> bool:
        if turn_id != self.active_rag_turn_id or not self.waiting_for_rag:
            return False
        self.active_rag_turn_id = None
        self.waiting_for_rag = False
        return True

    def record_admission(
        self,
        command_name: str | None,
        publication_generation: int | None,
    ) -> None:
        self.admitted_command_name = command_name
        self.admitted_publication_generation = publication_generation

    def set_active_publication(self, publication: PromptToolPublication) -> None:
        self.active_publication = publication

    def begin_generation(self) -> int:
        self.generation_sequence += 1
        self.active_generation_id = self.generation_sequence
        self.dispatch_phase = None
        return self.generation_sequence

    def begin_generation_dispatch(self) -> bool:
        """Reserve the controller-to-worker dispatch boundary once."""
        if self.dispatch_in_progress:
            return False
        self.dispatch_in_progress = True
        return True

    def finish_generation_dispatch(self) -> None:
        self.dispatch_in_progress = False

    def acknowledge_generation_dispatch(
        self,
        generation_id: int,
        phase: AssistantGenerationDispatchPhase,
    ) -> bool:
        """Accept only ordered dispatch transitions for the active generation."""
        if (
            generation_id != self.active_generation_id
            or self.cancelled
            or phase
            not in {
                AssistantGenerationDispatchPhase.ACCEPTED,
                AssistantGenerationDispatchPhase.STARTED,
            }
        ):
            return False
        if phase is AssistantGenerationDispatchPhase.ACCEPTED:
            if self.dispatch_phase is not None:
                return False
            self.dispatch_phase = phase
            return True
        if self.dispatch_phase is not AssistantGenerationDispatchPhase.ACCEPTED:
            return False
        self.dispatch_phase = phase
        return True

    def accept_generation_terminal(
        self,
        generation_id: int,
        phase: AssistantGenerationEventPhase,
    ) -> bool:
        """Commit one terminal while preserving cancellation priority."""
        if generation_id != self.active_generation_id:
            return False
        if self.cancelled:
            if phase is not AssistantGenerationEventPhase.CANCELLED:
                return False
        elif phase is AssistantGenerationEventPhase.CANCELLED:
            return False
        self.active_generation_id = None
        self.dispatch_phase = None
        return True

    def request_cancellation(self) -> bool:
        """Mark a turn cancelled and report whether this was the first request."""
        if self.cancelled:
            return False
        self.cancelled = True
        return True

    def begin_stopping_generation(self) -> int | None:
        """Bind cancellation to the generation that currently owns work."""
        generation_id = self.stopping_generation_id or self.active_generation_id
        if generation_id is not None:
            self.stopping_generation_id = generation_id
        return generation_id

    def accepts_stop_acknowledgement(self, generation_id: int) -> bool:
        return (
            self.cancelled
            and generation_id == self.stopping_generation_id
            and generation_id == self.active_generation_id
        )

    def accept_cancellation_terminal(self) -> bool:
        """Commit a visible cancellation once after generation has stopped."""
        if not self.cancelled or self.cancellation_response_sent:
            return False
        generation_id = self.active_generation_id
        if generation_id is not None and not self.accept_generation_terminal(
            generation_id,
            AssistantGenerationEventPhase.CANCELLED,
        ):
            return False
        self.cancellation_response_sent = True
        return True

    def reset_for_user_turn(self) -> None:
        """Reset mutable state that cannot cross a user-authored turn."""
        self.stopping_generation_id = None
        self.admitted_command_name = None
        self.admitted_publication_generation = None
        self.active_publication = PromptToolPublication.empty()
        self.cancelled = False
        self.cancellation_response_sent = False

    def reset_failed_setup(self) -> None:
        """Unwind partial setup while retaining correlation for terminal publish."""
        self.active_generation_id = None
        self.dispatch_phase = None
        self.dispatch_in_progress = False
        self.stopping_generation_id = None
        self.admitted_command_name = None
        self.admitted_publication_generation = None
        self.scope = None
        self.terminal_command = None
        self.excluded_commands = frozenset()
        self.active_publication = PromptToolPublication.empty()
        self.cancelled = False
        self.cancellation_response_sent = False

    def reset_conversation(self) -> None:
        """Reset non-active turn state after the host has admitted a reset."""
        self.reset_for_user_turn()
        self.scope = None
        self.terminal_command = None
        self.excluded_commands = frozenset()

    def reset_for_shutdown(self) -> None:
        """Clear active generation state when controller teardown owns no turn."""
        self.cancelled = False
        self.active_generation_id = None
        self.dispatch_phase = None
        self.stopping_generation_id = None


@dataclass
class AssistantToolAttemptSession:
    """Own counters and visible feedback scoped to one assistant request."""

    retry_count: int = 0
    tool_failure_count: int = 0
    loop_break_count: int = 0
    successful_tool_count: int = 0
    execution_count: int = 0
    visible_response_sent: bool = False
    last_tool_summary: str | None = None
    last_tool_summary_kind: AssistantResponseKind = AssistantResponseKind.MESSAGE
    recent_tool_calls: deque[tuple[str, str]] = field(
        default_factory=lambda: deque(maxlen=10),
        repr=False,
    )

    def begin_generation(self) -> None:
        """Reset presentation accounting for one newly dispatched generation."""
        self.visible_response_sent = False
        self.last_tool_summary = None
        self.last_tool_summary_kind = AssistantResponseKind.MESSAGE

    def mark_response_visible(self) -> None:
        self.visible_response_sent = True

    def record_summary(
        self,
        summary: str,
        kind: AssistantResponseKind,
    ) -> None:
        self.last_tool_summary = summary
        self.last_tool_summary_kind = kind

    def clear_summary(self) -> None:
        self.last_tool_summary = None
        self.last_tool_summary_kind = AssistantResponseKind.MESSAGE

    def record_format_retry(self, recovery_attempts_after: int) -> None:
        if recovery_attempts_after < 0:
            raise ValueError("Recovery attempts cannot be negative.")
        self.retry_count = recovery_attempts_after

    def clear_format_retries(self) -> None:
        self.retry_count = 0

    def begin_execution(self) -> int:
        self.execution_count += 1
        return self.execution_count

    def record_guided_repair(self) -> None:
        """Consume the one repair slot for an invented published tool name."""
        self.tool_failure_count = 1

    def record_failure(self) -> int:
        self.tool_failure_count += 1
        return self.tool_failure_count

    def record_success(self) -> int:
        self.tool_failure_count = 0
        self.successful_tool_count += 1
        return self.successful_tool_count

    def record_loop_break(self, *, limit: int) -> bool:
        if limit < 1:
            raise ValueError("Loop-break limit must be positive.")
        self.loop_break_count += 1
        return self.loop_break_count >= limit

    def record_tool_proposal(
        self,
        command_name: str,
        params: dict[str, object],
        *,
        repeat_limit: int = 3,
    ) -> bool:
        """Record one proposal and report a bounded same-signature loop."""
        if repeat_limit < 2:
            raise ValueError("Tool repeat limit must be at least two.")
        try:
            stable_params = json.dumps(params, sort_keys=True)
        except (TypeError, ValueError):
            stable_params = str(params)
        signature = (command_name, stable_params)
        self.recent_tool_calls.append(signature)
        return sum(call == signature for call in self.recent_tool_calls) >= repeat_limit

    def arbitrate_terminal_response(
        self,
        default_summary: str,
    ) -> AssistantToolTerminalResponseDecision:
        """Choose a terminal response without claiming that the UI rendered it."""
        if self.visible_response_sent:
            return AssistantToolTerminalResponseDecision()
        return AssistantToolTerminalResponseDecision(
            text=self.last_tool_summary or default_summary,
            kind=self.last_tool_summary_kind,
        )

    def commit_terminal_response(
        self,
        decision: AssistantToolTerminalResponseDecision,
    ) -> bool:
        """Commit one terminal decision only after presentation publication succeeds."""
        if not isinstance(decision, AssistantToolTerminalResponseDecision):
            raise TypeError("Terminal response decision is invalid.")
        self.successful_tool_count = 0
        if decision.text is None:
            return False
        if self.visible_response_sent:
            return False
        self.visible_response_sent = True
        return True

    def reset_for_user_turn(self) -> None:
        self.retry_count = 0
        self.tool_failure_count = 0
        self.loop_break_count = 0
        self.successful_tool_count = 0
        self.execution_count = 0
        self.visible_response_sent = False
        self.last_tool_summary = None
        self.last_tool_summary_kind = AssistantResponseKind.MESSAGE
        self.recent_tool_calls.clear()


@dataclass(frozen=True)
class AssistantToolTerminalResponseDecision:
    """Presentation effect chosen by the non-Qt tool-attempt owner."""

    text: str | None = None
    kind: AssistantResponseKind = AssistantResponseKind.MESSAGE
