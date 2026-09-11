"""Explicit workflow state shared by one assembled mock tool set."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MockWorkflowState:
    """Track only the product prerequisites needed by mock workflows."""

    data_loaded: bool = False
    split_spec_saved: bool = False
    model_name: str | None = None
    training_options_configured: bool = False
    training_running: bool = False

    def missing_training_prerequisites(self) -> tuple[str, ...]:
        """Return user-facing names for absent training prerequisites."""
        missing: list[str] = []
        if not self.split_spec_saved:
            missing.append("saved data splitting settings")
        if self.model_name is None:
            missing.append("model")
        if not self.training_options_configured:
            missing.append("training options")
        return tuple(missing)
