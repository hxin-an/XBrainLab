"""Lifecycle reset command handlers for the application command spine."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from XBrainLab.backend.utils.logger import logger

from .commands import (
    Command,
    NewSessionCommand,
    ResetPreprocessCommand,
    ResetSessionCommand,
)
from .pipeline_transaction import PipelineStateTransaction
from .state import ApplicationStateSnapshot

HandlerResult = str | tuple[str, dict[str, Any]]


class LifecycleCommandService:
    """Handle reset and new-session commands without owning dispatch policy."""

    def __init__(
        self,
        *,
        study: Any,
        dataset: Any,
        preprocess: Any,
        training: Any,
        training_commands: Any,
        interpretation: Any,
        get_state: Callable[[], ApplicationStateSnapshot],
        pipeline_transaction: PipelineStateTransaction | None = None,
    ) -> None:
        self.study = study
        self.dataset = dataset
        self.preprocess = preprocess
        self.training = training
        self.training_commands = training_commands
        self.interpretation = interpretation
        self._get_state = get_state
        self._pipeline_transaction = pipeline_transaction or PipelineStateTransaction(
            study
        )

    def handle_reset_preprocess(self, command: Command) -> HandlerResult:
        if not isinstance(command, ResetPreprocessCommand):
            raise TypeError("Invalid command for reset_preprocess")
        before = self._get_state()
        snapshot = self._pipeline_transaction.capture()
        try:
            self.study.reset_preprocess(force_update=True)
            self.training.clean_datasets(force_update=True)
        except Exception:
            self._pipeline_transaction.restore(snapshot)
            raise
        try:
            self.preprocess.notify("preprocess_changed")
            self.dataset.notify("data_changed")
            self.dataset.notify("dataset_locked", False)
        except Exception:
            logger.debug("Preprocess reset notification failed", exc_info=True)
        return (
            "Preprocessing reset to loaded raw data.",
            {
                "preprocess_operations_before": before.preprocessed.operations,
                "had_epoch_data": before.epoch.exists,
                "dataset_count_before": before.dataset.count,
                "trainer_cleared": before.training.has_trainer,
            },
        )

    def handle_reset_session(self, command: Command) -> HandlerResult:
        if not isinstance(command, ResetSessionCommand):
            raise TypeError("Invalid command for reset_session")
        self.dataset.clean_dataset()
        self._clear_training_configuration()
        self._clear_interpretation_state()
        return "Session reset."

    def handle_new_session(self, command: Command) -> HandlerResult:
        if not isinstance(command, NewSessionCommand):
            raise TypeError("Invalid command for new_session")
        self.dataset.clean_dataset()
        self._clear_training_configuration()
        self._clear_interpretation_state()
        return "New session started.", {"single_session_backend": True}

    def _clear_training_configuration(self) -> None:
        self.training_commands.clear_configuration(
            getattr(self.study, "training_manager", None),
        )

    def _clear_interpretation_state(self) -> None:
        self.interpretation.clear()
