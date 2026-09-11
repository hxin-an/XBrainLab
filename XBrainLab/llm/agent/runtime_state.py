"""Typed lifecycle contract for the local assistant runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from XBrainLab.llm.core.runtime_selection import AssistantRuntimeSelectionOutcome


class AssistantRuntimePhase(str, Enum):
    """User-observable lifecycle phases for the local model runtime."""

    IDLE = "idle"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class AssistantRuntimeSnapshot:
    """Typed runtime state published across Qt thread boundaries."""

    phase: AssistantRuntimePhase
    initialized: bool
    backend_mode: str = ""
    model_id: str = ""
    requested_model_id: str = ""
    selection_outcome: AssistantRuntimeSelectionOutcome | None = None
    selection_detail: str = ""
    execution_device: str = ""
    device_fallback_reason: str = ""
    error: str = ""
    activation_id: int = 0

    def validation_error(self) -> str:
        """Return why this snapshot cannot represent a runtime lifecycle state."""
        if not isinstance(self.phase, AssistantRuntimePhase):
            return "runtime phase is not typed"
        if self.phase is AssistantRuntimePhase.READY and not self.initialized:
            return "ready runtime must be initialized"
        if self.phase is AssistantRuntimePhase.IDLE and self.initialized:
            return "idle runtime cannot retain an initialized engine"
        if (
            isinstance(self.activation_id, bool)
            or not isinstance(self.activation_id, int)
            or self.activation_id < 0
        ):
            return "activation id must be a non-negative integer"
        return ""
