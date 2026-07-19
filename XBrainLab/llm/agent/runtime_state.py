"""Typed lifecycle contract for the local assistant runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from XBrainLab.llm.core.runtime_selection import AssistantRuntimeSelectionOutcome


class AssistantRuntimePhase(str, Enum):
    """User-observable lifecycle phases for the local model runtime."""

    IDLE = "idle"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class AssistantRuntimeSnapshot:
    """Serializable runtime state published across Qt thread boundaries."""

    phase: AssistantRuntimePhase
    initialized: bool
    backend_mode: str = ""
    model_id: str = ""
    requested_model_id: str = ""
    selection_outcome: AssistantRuntimeSelectionOutcome | None = None
    selection_detail: str = ""
    error: str = ""
    activation_id: int = 0

    @property
    def fallback_used(self) -> bool:
        return self.selection_outcome is AssistantRuntimeSelectionOutcome.FALLBACK

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

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["phase"] = self.phase.value
        payload["selection_outcome"] = (
            self.selection_outcome.value if self.selection_outcome is not None else ""
        )
        return payload

    @classmethod
    def from_payload(cls, payload: object) -> AssistantRuntimeSnapshot:
        if isinstance(payload, cls):
            return payload
        data = payload if isinstance(payload, dict) else {}
        raw_phase = str(data.get("phase") or "").strip().lower()
        initialized = bool(data.get("initialized"))
        if not raw_phase:
            raw_phase = (
                AssistantRuntimePhase.READY.value
                if initialized
                else AssistantRuntimePhase.IDLE.value
            )
        try:
            phase = AssistantRuntimePhase(raw_phase)
        except ValueError:
            phase = AssistantRuntimePhase.FAILED
        raw_outcome = data.get("selection_outcome")
        if isinstance(raw_outcome, AssistantRuntimeSelectionOutcome):
            selection_outcome = raw_outcome
        else:
            try:
                selection_outcome = AssistantRuntimeSelectionOutcome(
                    str(raw_outcome or "").strip().lower()
                )
            except ValueError:
                selection_outcome = None
        raw_activation_id = data.get("activation_id")
        if isinstance(raw_activation_id, bool):
            activation_id = 0
        else:
            try:
                activation_id = max(0, int(raw_activation_id or 0))
            except (TypeError, ValueError):
                activation_id = 0
        snapshot = cls(
            phase=phase,
            initialized=initialized,
            backend_mode=str(data.get("backend_mode") or ""),
            model_id=str(data.get("model_id") or ""),
            requested_model_id=str(data.get("requested_model_id") or ""),
            selection_outcome=selection_outcome,
            selection_detail=str(data.get("selection_detail") or ""),
            error=str(data.get("error") or ""),
            activation_id=activation_id,
        )
        error = snapshot.validation_error()
        if error:
            raise ValueError(error)
        return snapshot
