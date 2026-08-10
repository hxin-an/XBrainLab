"""Explicit workflow state shared by one assembled mock tool set."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MockWorkflowState:
    """Track only the product prerequisites needed by mock workflows."""

    data_loaded: bool = False
    epochs_ready: bool = False
    split_spec_saved: bool = False
    model_name: str | None = None
    training_options_configured: bool = False
    training_running: bool = False

    def mark_data_loaded(self) -> None:
        """Publish new raw data and invalidate saved split state."""
        self.data_loaded = True
        self.epochs_ready = False
        self.split_spec_saved = False

    def mark_epochs_ready(self) -> None:
        """Publish epochs and invalidate any previously saved split."""
        self.epochs_ready = True
        self.split_spec_saved = False

    def clear_dataset(self) -> None:
        """Reset the mock session like the real reset-session command."""
        self.data_loaded = False
        self.epochs_ready = False
        self.split_spec_saved = False
        self.model_name = None
        self.training_options_configured = False
        self.training_running = False

    def reset_preprocess(self) -> None:
        """Retain loaded raw data while clearing all downstream mock state."""
        self.epochs_ready = False
        self.split_spec_saved = False
        self.model_name = None
        self.training_options_configured = False
        self.training_running = False

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
