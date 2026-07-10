"""Transactional snapshots for active EEG pipeline mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PipelineStateSnapshot:
    """References needed to restore the active data and training pipeline."""

    loaded_data: tuple[Any, ...]
    backup_loaded_data: tuple[Any, ...] | None
    preprocessed_data: tuple[Any, ...]
    epoch_data: Any | None
    datasets: tuple[Any, ...]
    dataset_generator: Any | None
    dataset_locked: bool
    trainer: Any | None


class PipelineStateTransaction:
    """Capture and restore Study-owned state without controller introspection."""

    def __init__(self, study: Any) -> None:
        self._study = study

    def capture(self) -> PipelineStateSnapshot:
        data_manager = self._study.data_manager
        training_manager = self._study.training_manager
        backup = getattr(data_manager, "backup_loaded_data_list", None)
        return PipelineStateSnapshot(
            loaded_data=tuple(getattr(data_manager, "loaded_data_list", []) or []),
            backup_loaded_data=None if backup is None else tuple(backup),
            preprocessed_data=tuple(
                getattr(data_manager, "preprocessed_data_list", []) or []
            ),
            epoch_data=getattr(data_manager, "epoch_data", None),
            datasets=tuple(getattr(data_manager, "datasets", []) or []),
            dataset_generator=getattr(data_manager, "dataset_generator", None),
            dataset_locked=bool(getattr(data_manager, "dataset_locked", False)),
            trainer=getattr(training_manager, "trainer", None),
        )

    def prepare_raw_replacement(self) -> None:
        """Detach current references so an import can be committed or rolled back."""
        data_manager = self._study.data_manager
        training_manager = self._study.training_manager
        data_manager.loaded_data_list = []
        data_manager.backup_loaded_data_list = None
        data_manager.preprocessed_data_list = []
        data_manager.epoch_data = None
        data_manager.datasets = []
        data_manager.dataset_generator = None
        data_manager.dataset_locked = False
        training_manager.trainer = None

    def restore(self, snapshot: PipelineStateSnapshot) -> None:
        """Restore a previously captured active pipeline snapshot."""
        data_manager = self._study.data_manager
        training_manager = self._study.training_manager
        data_manager.loaded_data_list = list(snapshot.loaded_data)
        data_manager.backup_loaded_data_list = (
            None
            if snapshot.backup_loaded_data is None
            else list(snapshot.backup_loaded_data)
        )
        data_manager.preprocessed_data_list = list(snapshot.preprocessed_data)
        data_manager.epoch_data = snapshot.epoch_data
        data_manager.datasets = list(snapshot.datasets)
        data_manager.dataset_generator = snapshot.dataset_generator
        data_manager.dataset_locked = snapshot.dataset_locked
        training_manager.trainer = snapshot.trainer
