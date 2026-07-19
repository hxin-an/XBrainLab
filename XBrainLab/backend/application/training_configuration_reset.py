"""Lightweight owner for resetting application training configuration."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.utils.logger import logger

from .training_runtime import TrainingConfigurationControlPort


class TrainingConfigurationResetService:
    """Clear model, optimizer, and saliency choices without loading training code."""

    def __init__(
        self,
        *,
        training: Any,
        training_runtime: TrainingConfigurationControlPort,
    ) -> None:
        self.training = training
        self.training_runtime = training_runtime

    def clear(self) -> None:
        """Reset the active configuration and publish one configuration change."""
        self.training_runtime.clear_configuration()
        try:
            self.training.notify("config_changed")
        except Exception:
            logger.debug("Training config reset notification failed", exc_info=True)
