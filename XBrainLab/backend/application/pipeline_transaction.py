"""Transactional snapshots for active EEG pipeline mutations."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from XBrainLab.backend.training_state_contract import TrainingPipelineMutationBoundary

from .training_runtime import StudyTrainingRuntime, TrainingPipelineMutationPort


@dataclass(frozen=True)
class PipelineStateSnapshot:
    """Data references needed to restore a failed speculative pipeline mutation."""

    loaded_data: tuple[Any, ...]
    backup_loaded_data: tuple[Any, ...] | None
    preprocessed_data: tuple[Any, ...]
    epoch_data: Any | None
    datasets: tuple[Any, ...]
    dataset_generator: Any | None
    dataset_locked: bool
    dataset_sequence: int
    epoch_trial_selection_evidence_present: bool
    epoch_trial_selection_evidence: Any
    epoch_trial_selection_evidence_dropped: int | None


@dataclass(frozen=True, slots=True)
class PipelineStateIdentity:
    """Object identity boundary for one captured EEG pipeline state."""

    loaded_data: tuple[int, ...]
    backup_loaded_data: tuple[int, ...] | None
    preprocessed_data: tuple[int, ...]
    epoch_data: int | None
    datasets: tuple[int, ...]
    dataset_generator: int | None
    dataset_locked: bool
    dataset_sequence: int

    @classmethod
    def from_snapshot(cls, snapshot: PipelineStateSnapshot) -> PipelineStateIdentity:
        return cls(
            loaded_data=tuple(id(item) for item in snapshot.loaded_data),
            backup_loaded_data=(
                None
                if snapshot.backup_loaded_data is None
                else tuple(id(item) for item in snapshot.backup_loaded_data)
            ),
            preprocessed_data=tuple(id(item) for item in snapshot.preprocessed_data),
            epoch_data=None if snapshot.epoch_data is None else id(snapshot.epoch_data),
            datasets=tuple(id(item) for item in snapshot.datasets),
            dataset_generator=(
                None
                if snapshot.dataset_generator is None
                else id(snapshot.dataset_generator)
            ),
            dataset_locked=snapshot.dataset_locked,
            dataset_sequence=snapshot.dataset_sequence,
        )


@dataclass(frozen=True)
class DatasetPublicationSnapshot:
    """Bounded references required to restore one dataset publication."""

    datasets: tuple[Any, ...]
    dataset_generator: Any | None
    dataset_locked: bool
    dataset_sequence: int
    epoch_data: Any | None
    epoch_trial_selection_evidence_present: bool
    epoch_trial_selection_evidence: Any
    epoch_trial_selection_evidence_dropped: int | None


class PipelineStateTransaction:
    """Coordinate data rollback with typed training-runtime invalidation."""

    def __init__(
        self,
        study: Any,
        *,
        training_runtime: TrainingPipelineMutationPort | None = None,
    ) -> None:
        self._study = study
        self._training_runtime = training_runtime or StudyTrainingRuntime(study)

    def capture(self) -> PipelineStateSnapshot:
        data_manager = self._study.data_manager
        backup = getattr(data_manager, "backup_loaded_data_list", None)
        epoch_data = getattr(data_manager, "epoch_data", None)
        epoch_data_runtime: Any = epoch_data
        evidence_present = bool(
            epoch_data is not None and hasattr(epoch_data, "trial_selection_evidence")
        )
        trial_selection_evidence = (
            deepcopy(epoch_data_runtime.trial_selection_evidence)
            if evidence_present
            else None
        )
        from XBrainLab.backend.dataset.dataset import Dataset  # noqa: PLC0415

        return PipelineStateSnapshot(
            loaded_data=tuple(getattr(data_manager, "loaded_data_list", []) or []),
            backup_loaded_data=None if backup is None else tuple(backup),
            preprocessed_data=tuple(
                getattr(data_manager, "preprocessed_data_list", []) or []
            ),
            epoch_data=epoch_data,
            datasets=tuple(getattr(data_manager, "datasets", []) or []),
            dataset_generator=getattr(data_manager, "dataset_generator", None),
            dataset_locked=bool(getattr(data_manager, "dataset_locked", False)),
            dataset_sequence=int(Dataset.SEQ),
            epoch_trial_selection_evidence_present=evidence_present,
            epoch_trial_selection_evidence=trial_selection_evidence,
            epoch_trial_selection_evidence_dropped=(
                int(getattr(epoch_data, "trial_selection_evidence_dropped", 0))
                if evidence_present
                else None
            ),
        )

    def prepare_raw_replacement(self) -> None:
        """Detach only data references so an import can be committed or rolled back."""
        data_manager = self._study.data_manager
        data_manager.loaded_data_list = []
        data_manager.backup_loaded_data_list = None
        data_manager.preprocessed_data_list = []
        data_manager.epoch_data = None
        data_manager.datasets = []
        data_manager.dataset_generator = None
        data_manager.dataset_locked = False

    def restore(self, snapshot: PipelineStateSnapshot) -> None:
        """Restore previously captured data without rewriting training runtime."""
        data_manager = self._study.data_manager
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
        from XBrainLab.backend.dataset.dataset import Dataset  # noqa: PLC0415

        Dataset.SEQ = snapshot.dataset_sequence
        if (
            snapshot.epoch_trial_selection_evidence_present
            and snapshot.epoch_data is not None
        ):
            snapshot.epoch_data.trial_selection_evidence = deepcopy(
                snapshot.epoch_trial_selection_evidence
            )
            snapshot.epoch_data.trial_selection_evidence_dropped = int(
                snapshot.epoch_trial_selection_evidence_dropped or 0
            )
        elif snapshot.epoch_data is not None:
            for attribute in (
                "trial_selection_evidence",
                "trial_selection_evidence_dropped",
            ):
                if hasattr(snapshot.epoch_data, attribute):
                    delattr(snapshot.epoch_data, attribute)

    def publish_datasets(self, datasets: list[Any], generator: Any) -> None:
        """Publish already-generated datasets without touching training runtime."""
        data_manager = self._study.data_manager
        setter = getattr(data_manager, "set_datasets", None)
        if callable(setter):
            setter(list(datasets), force_update=True)
        else:
            data_manager.datasets = list(datasets)
        data_manager.dataset_generator = generator

    def publish_dataset_candidate(
        self,
        snapshot: DatasetPublicationSnapshot,
    ) -> None:
        """Publish one prepared split with its sequence and epoch evidence."""
        data_manager = self._study.data_manager
        if getattr(data_manager, "epoch_data", None) is not snapshot.epoch_data:
            raise RuntimeError(
                "Epoch data changed before the prepared dataset split was published."
            )
        self.publish_datasets(list(snapshot.datasets), snapshot.dataset_generator)
        data_manager.dataset_locked = snapshot.dataset_locked
        self._restore_dataset_provenance(snapshot)

    def capture_dataset_publication(self) -> DatasetPublicationSnapshot:
        """Capture dataset identities without copying epochs, masks, or history."""
        data_manager = self._study.data_manager
        epoch_data = getattr(data_manager, "epoch_data", None)
        epoch_data_runtime: Any = epoch_data
        evidence_present = bool(
            epoch_data is not None and hasattr(epoch_data, "trial_selection_evidence")
        )
        trial_selection_evidence = (
            deepcopy(epoch_data_runtime.trial_selection_evidence)
            if evidence_present
            else None
        )
        from XBrainLab.backend.dataset.dataset import Dataset  # noqa: PLC0415

        return DatasetPublicationSnapshot(
            datasets=tuple(getattr(data_manager, "datasets", []) or []),
            dataset_generator=getattr(data_manager, "dataset_generator", None),
            dataset_locked=bool(getattr(data_manager, "dataset_locked", False)),
            dataset_sequence=int(Dataset.SEQ),
            epoch_data=epoch_data,
            epoch_trial_selection_evidence_present=evidence_present,
            epoch_trial_selection_evidence=trial_selection_evidence,
            epoch_trial_selection_evidence_dropped=(
                int(getattr(epoch_data, "trial_selection_evidence_dropped", 0))
                if evidence_present
                else None
            ),
        )

    def restore_dataset_publication(
        self,
        snapshot: DatasetPublicationSnapshot,
    ) -> None:
        """Restore one failed dataset publish while leaving epochs untouched."""
        data_manager = self._study.data_manager
        if getattr(data_manager, "epoch_data", None) is not snapshot.epoch_data:
            raise RuntimeError(
                "Epoch data changed before dataset publication could be restored."
            )
        data_manager.datasets = list(snapshot.datasets)
        data_manager.dataset_generator = snapshot.dataset_generator
        data_manager.dataset_locked = snapshot.dataset_locked
        self._restore_dataset_provenance(snapshot)

    @staticmethod
    def _restore_dataset_provenance(snapshot: DatasetPublicationSnapshot) -> None:
        """Restore dataset sequence and detached trial-selection evidence."""
        from XBrainLab.backend.dataset.dataset import Dataset  # noqa: PLC0415

        Dataset.SEQ = snapshot.dataset_sequence
        if snapshot.epoch_trial_selection_evidence_present:
            epoch_data = snapshot.epoch_data
            if epoch_data is None:
                raise RuntimeError("Dataset publication evidence has no epoch data.")
            epoch_data.trial_selection_evidence = deepcopy(
                snapshot.epoch_trial_selection_evidence
            )
            epoch_data.trial_selection_evidence_dropped = int(
                snapshot.epoch_trial_selection_evidence_dropped or 0
            )
        elif snapshot.epoch_data is not None:
            for attribute in (
                "trial_selection_evidence",
                "trial_selection_evidence_dropped",
            ):
                if hasattr(snapshot.epoch_data, attribute):
                    delattr(snapshot.epoch_data, attribute)

    def commit_dataset_replacement(
        self,
        candidate: DatasetPublicationSnapshot,
        *,
        expected: TrainingPipelineMutationBoundary,
    ) -> bool:
        """Publish datasets and retire dependent training under one runtime lease."""
        return self._training_runtime.commit_pipeline_replacement(
            expected,
            publish=lambda: self.publish_dataset_candidate(candidate),
        )

    def capture_training_startup_snapshot(self) -> Any:
        """Capture complete quiescent training truth through the runtime port."""
        return self._training_runtime.capture_startup_rollback_snapshot()

    def restore_training_startup_snapshot(self, snapshot: Any) -> None:
        """Restore complete training truth after a failed dataset commit."""
        self._training_runtime.restore_startup_rollback_snapshot(snapshot)

    def begin_raw_replacement(self) -> TrainingPipelineMutationBoundary:
        """Capture a typed boundary that requires no trainer."""
        return self._training_runtime.begin_raw_replacement()

    def begin_downstream_replacement(self) -> TrainingPipelineMutationBoundary:
        """Capture a typed boundary for dataset/preprocess replacement."""
        return self._training_runtime.begin_downstream_replacement()

    def commit_pipeline_invalidation(
        self,
        expected: TrainingPipelineMutationBoundary,
    ) -> bool:
        """Compare-and-retire training truth after data mutation succeeds."""
        return self._training_runtime.commit_pipeline_invalidation(expected)

    def commit_pipeline_replacement(
        self,
        expected: TrainingPipelineMutationBoundary,
        *,
        publish: Callable[[], None],
    ) -> bool:
        """Publish prepared raw state under the training-runtime mutation lease."""
        if not callable(publish):
            raise TypeError("publish must be callable")
        return self._training_runtime.commit_pipeline_replacement(
            expected,
            publish=publish,
        )
