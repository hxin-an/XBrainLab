"""Per-turn agent metrics and structured logging.

Tracks conversation turns, token estimates, tool execution timing,
and emits structured log records for observability.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger("XBrainLab.LLM.Metrics")


@dataclass
class ToolExecution:
    """Record of a single tool call within a turn."""

    name: str
    success: bool
    duration_ms: float
    error: str | None = None


@dataclass
class TurnMetrics:
    """Accumulated metrics for one user-turn → agent-response cycle.

    Attributes:
        turn_id: UUID for this turn.
        conversation_id: UUID for the whole conversation session.
        input_chars: Total characters sent to the LLM across all
            generation calls in this turn.
        output_chars: Total characters received from the LLM across
            all generation calls in this turn.
        llm_calls: Number of LLM generation calls (initial + retries).
        tool_executions: Ordered list of tool execution records.
        start_time: Wall-clock start time (``time.monotonic``).
        end_time: Wall-clock end time (``time.monotonic``).

    """

    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    conversation_id: str = ""
    input_chars: int = 0
    output_chars: int = 0
    llm_calls: int = 0
    tool_executions: list[ToolExecution] = field(default_factory=list)
    start_time: float = field(default_factory=time.monotonic)
    end_time: float = 0.0

    # --- Convenience helpers ---

    @property
    def duration_ms(self) -> float:
        """Total turn duration in milliseconds."""
        if self.end_time <= 0:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    @property
    def tool_count(self) -> int:
        return len(self.tool_executions)

    @property
    def tool_success_count(self) -> int:
        return sum(1 for t in self.tool_executions if t.success)

    @property
    def estimated_input_tokens(self) -> int:
        """Rough token estimate (1 token ≈ 4 chars for English)."""
        return self.input_chars // 4

    @property
    def estimated_output_tokens(self) -> int:
        return self.output_chars // 4

    def record_tool(
        self,
        name: str,
        success: bool,
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        """Append a tool execution record."""
        self.tool_executions.append(
            ToolExecution(
                name=name,
                success=success,
                duration_ms=duration_ms,
                error=error,
            ),
        )

    def finalize(self) -> None:
        """Mark the turn as finished and log the summary."""
        self.end_time = time.monotonic()
        self._log_summary()

    def _log_summary(self) -> None:
        logger.info(
            "turn_complete | turn=%s conv=%s duration=%.0fms "
            "llm_calls=%d in_tok≈%d out_tok≈%d "
            "tools=%d/%d",
            self.turn_id,
            self.conversation_id,
            self.duration_ms,
            self.llm_calls,
            self.estimated_input_tokens,
            self.estimated_output_tokens,
            self.tool_success_count,
            self.tool_count,
        )
        for te in self.tool_executions:
            status = "OK" if te.success else f"FAIL({te.error})"
            logger.info(
                "  tool | turn=%s name=%s status=%s duration=%.0fms",
                self.turn_id,
                te.name,
                status,
                te.duration_ms,
            )


class AgentMetricsTracker:
    """Session-level tracker that creates and manages ``TurnMetrics``.

    Usage::

        tracker = AgentMetricsTracker()
        turn = tracker.start_turn()
        turn.llm_calls += 1
        turn.input_chars += len(prompt_text)
        ...
        turn.finalize()

    """

    def __init__(self) -> None:
        self.conversation_id: str = uuid.uuid4().hex[:12]
        self._current_turn: TurnMetrics | None = None
        self._completed_turns: list[TurnMetrics] = []

    def start_turn(self) -> TurnMetrics:
        """Begin a new turn, finalizing any in-progress turn."""
        if self._current_turn is not None and self._current_turn.end_time <= 0:
            self._current_turn.finalize()
            self._completed_turns.append(self._current_turn)
        self._current_turn = TurnMetrics(conversation_id=self.conversation_id)
        return self._current_turn

    def finish_turn(self) -> TurnMetrics | None:
        """Finalize current turn and return it."""
        if self._current_turn is None:
            return None
        self._current_turn.finalize()
        self._completed_turns.append(self._current_turn)
        turn = self._current_turn
        self._current_turn = None
        return turn

    @property
    def current_turn(self) -> TurnMetrics | None:
        return self._current_turn

    @property
    def total_turns(self) -> int:
        return len(self._completed_turns)

    @property
    def total_estimated_tokens(self) -> int:
        """Sum of estimated input+output tokens across all completed turns."""
        return sum(
            t.estimated_input_tokens + t.estimated_output_tokens
            for t in self._completed_turns
        )

    def reset(self) -> None:
        """Reset the tracker for a new conversation session."""
        self.conversation_id = uuid.uuid4().hex[:12]
        self._current_turn = None
        self._completed_turns = []
