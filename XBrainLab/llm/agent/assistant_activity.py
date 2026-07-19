"""Typed, turn-local activity published by the assistant runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .turn import AssistantTurnCorrelation


class AssistantTurnActivityPhase(str, Enum):
    """Transient phase of one assistant turn, independent of pipeline readiness."""

    IDLE = "idle"
    PREPARING = "preparing"
    THINKING = "thinking"
    WAITING_FOR_DECISION = "waiting_for_decision"
    RUNNING_COMMAND = "running_command"
    STOPPING = "stopping"
    NEEDS_ATTENTION = "needs_attention"


class AssistantAttentionKind(str, Enum):
    """Typed meaning of a turn that needs user-visible attention."""

    ATTENTION = "attention"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AssistantTurnActivity:
    """Correlated transient activity that never represents backend workflow state."""

    phase: AssistantTurnActivityPhase
    command_name: str = ""
    request_id: str = ""
    message: str = ""
    turn_id: int | None = None
    generation: int | None = None
    attention_kind: AssistantAttentionKind = AssistantAttentionKind.ATTENTION

    def __post_init__(self) -> None:
        if not isinstance(self.phase, AssistantTurnActivityPhase):
            raise TypeError("Assistant turn activity phase must be typed.")
        if not isinstance(self.attention_kind, AssistantAttentionKind):
            raise TypeError("Assistant turn attention kind must be typed.")
        if self.turn_id is not None:
            if isinstance(self.turn_id, bool) or not isinstance(self.turn_id, int):
                raise TypeError("Assistant turn activity turn id must be an integer.")
            if self.turn_id <= 0:
                raise ValueError("Assistant turn activity turn id must be positive.")
        if self.generation is not None:
            if isinstance(self.generation, bool) or not isinstance(
                self.generation,
                int,
            ):
                raise TypeError(
                    "Assistant turn activity generation must be an integer."
                )
            if self.generation <= 0:
                raise ValueError("Assistant turn activity generation must be positive.")

        for field_name in ("command_name", "request_id", "message"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                label = field_name.replace("_", " ")
                raise TypeError(f"Assistant turn activity {label} must be a string.")
            object.__setattr__(self, field_name, " ".join(value.split()))

    @property
    def correlation(self) -> AssistantTurnCorrelation | None:
        """Return exact correlation only when both lease components are present."""
        if self.turn_id is None or self.generation is None:
            return None
        return AssistantTurnCorrelation(
            generation=self.generation,
            turn_id=self.turn_id,
        )
