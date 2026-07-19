"""Explicit workflow state shared by one assembled mock tool set."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MockWorkflowState:
    """Track only the product prerequisites needed by mock workflows."""

    data_loaded: bool = False
    epochs_ready: bool = False
    dataset_generated: bool = False
    model_name: str | None = None
    training_options_configured: bool = False
    training_running: bool = False

    def mark_data_loaded(self) -> None:
        """Publish new raw data and invalidate derived dataset state."""
        self.data_loaded = True
        self.epochs_ready = False
        self.dataset_generated = False

    def mark_epochs_ready(self) -> None:
        """Publish epochs and invalidate any previously generated dataset."""
        self.epochs_ready = True
        self.dataset_generated = False

    def clear_dataset(self) -> None:
        """Reset the mock session like the real reset-session command."""
        self.data_loaded = False
        self.epochs_ready = False
        self.dataset_generated = False
        self.model_name = None
        self.training_options_configured = False
        self.training_running = False

    def reset_preprocess(self) -> None:
        """Retain loaded raw data while clearing all downstream mock state."""
        self.epochs_ready = False
        self.dataset_generated = False
        self.model_name = None
        self.training_options_configured = False
        self.training_running = False

    def missing_training_prerequisites(self) -> tuple[str, ...]:
        """Return user-facing names for absent training prerequisites."""
        missing: list[str] = []
        if not self.dataset_generated:
            missing.append("generated dataset")
        if self.model_name is None:
            missing.append("model")
        if not self.training_options_configured:
            missing.append("training options")
        return tuple(missing)
