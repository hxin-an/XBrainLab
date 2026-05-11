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
        dataset_generation: Any,
        training_commands: Any,
        interpretation: Any,
        get_state: Callable[[], ApplicationStateSnapshot],
    ) -> None:
        self.study = study
        self.dataset = dataset
        self.preprocess = preprocess
        self.training = training
        self.dataset_generation = dataset_generation
        self.training_commands = training_commands
        self.interpretation = interpretation
        self._get_state = get_state

    def handle_reset_preprocess(self, command: Command) -> HandlerResult:
        if not isinstance(command, ResetPreprocessCommand):
            raise TypeError("Invalid command for reset_preprocess")
        before = self._get_state()
        previous_preprocessed = list(getattr(self.study, "preprocessed_data_list", []))
        previous_epoch = getattr(self.study, "epoch_data", None)
        previous_datasets = list(getattr(self.study, "datasets", []) or [])
        previous_generator = getattr(self.study, "dataset_generator", None)
        previous_trainer = getattr(self.study, "trainer", None)
        try:
            self.study.reset_preprocess(force_update=True)
            self.training.clean_datasets(force_update=True)
        except Exception:
            data_manager = getattr(self.study, "data_manager", None)
            if data_manager is not None:
                data_manager.preprocessed_data_list = previous_preprocessed
                data_manager.epoch_data = previous_epoch
            else:
                self.study.preprocessed_data_list = previous_preprocessed
                self.study.epoch_data = previous_epoch
            self.dataset_generation.restore_generation_state(
                datasets=previous_datasets,
                generator=previous_generator,
                trainer=previous_trainer,
            )
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
