"""Focused tests for lifecycle reset command handlers."""

from __future__ import annotations

from typing import Any, cast

import pytest

from XBrainLab.backend.application.commands import (
    NewSessionCommand,
    ResetPreprocessCommand,
    ResetSessionCommand,
)
from XBrainLab.backend.application.lifecycle_service import (
    HandlerResult,
    LifecycleCommandService,
)
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    DatasetStateSnapshot,
    EpochStateSnapshot,
    EvaluationStateSnapshot,
    InterpretationStateSnapshot,
    PreprocessedStateSnapshot,
    RawStateSnapshot,
    TrainingStateSnapshot,
    VisualizationStateSnapshot,
)


class _DataManager:
    def __init__(self) -> None:
        self.loaded_data_list: list[Any] = []
        self.backup_loaded_data_list: list[Any] | None = None
        self.preprocessed_data_list: list[Any] = []
        self.epoch_data: Any | None = None
        self.datasets: list[Any] = []
        self.dataset_generator: Any | None = None
        self.dataset_locked = False


class _TrainingManager:
    def __init__(self) -> None:
        self.trainer: Any | None = None


class _Study:
    def __init__(self) -> None:
        self.data_manager = _DataManager()
        self.training_manager = _TrainingManager()
        self.fail_reset = False
        self.reset_called = False

    @property
    def preprocessed_data_list(self) -> list[Any]:
        return self.data_manager.preprocessed_data_list

    @property
    def epoch_data(self) -> Any | None:
        return self.data_manager.epoch_data

    @property
    def datasets(self) -> list[Any]:
        return self.data_manager.datasets

    @property
    def dataset_generator(self) -> Any | None:
        return self.data_manager.dataset_generator

    @property
    def trainer(self) -> Any | None:
        return self.training_manager.trainer

    def reset_preprocess(self, *, force_update: bool) -> None:
        assert force_update is True
        self.reset_called = True
        if self.data_manager.backup_loaded_data_list:
            self.data_manager.loaded_data_list = (
                self.data_manager.backup_loaded_data_list
            )
            self.data_manager.backup_loaded_data_list = None
            self.data_manager.dataset_locked = False
        self.data_manager.preprocessed_data_list = []
        self.data_manager.epoch_data = None
        if self.fail_reset:
            raise RuntimeError("reset failed")


class _DatasetController:
    def __init__(self) -> None:
        self.notifications: list[tuple[Any, ...]] = []
        self.cleaned = False

    def notify(self, *args: Any) -> None:
        self.notifications.append(args)

    def clean_dataset(self) -> None:
        self.cleaned = True


class _PreprocessController:
    def __init__(self) -> None:
        self.notifications: list[str] = []

    def notify(self, event_name: str) -> None:
        self.notifications.append(event_name)


class _TrainingController:
    def __init__(self, study: _Study) -> None:
        self.study = study
        self.cleaned = False

    def clean_datasets(self, *, force_update: bool) -> None:
        assert force_update is True
        self.cleaned = True
        self.study.data_manager.datasets = []
        self.study.training_manager.trainer = None


class _TrainingCommands:
    def __init__(self) -> None:
        self.cleared_managers: list[Any] = []

    def clear_configuration(self, training_manager: Any | None) -> None:
        self.cleared_managers.append(training_manager)


class _InterpretationCommands:
    def __init__(self) -> None:
        self.cleared = False

    def clear(self) -> None:
        self.cleared = True


def _state() -> ApplicationStateSnapshot:
    return ApplicationStateSnapshot(
        pipeline_stage="dataset_ready",
        raw=RawStateSnapshot(loaded=True, count=1),
        preprocessed=PreprocessedStateSnapshot(
            available=True,
            count=1,
            operations=["filter"],
        ),
        epoch=EpochStateSnapshot(available=True, exists=True),
        dataset=DatasetStateSnapshot(available=True, count=2),
        training=TrainingStateSnapshot(has_trainer=True),
        evaluation=EvaluationStateSnapshot(),
        visualization=VisualizationStateSnapshot(),
        interpretation=InterpretationStateSnapshot(),
        active_dataset=ActiveDatasetSnapshot(has_datasets=True),
        active_training=ActiveTrainingSnapshot(),
    )


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def _service() -> tuple[
    LifecycleCommandService,
    _Study,
    _DatasetController,
    _PreprocessController,
    _TrainingController,
    _TrainingCommands,
    _InterpretationCommands,
]:
    study = _Study()
    dataset = _DatasetController()
    preprocess = _PreprocessController()
    training = _TrainingController(study)
    training_commands = _TrainingCommands()
    interpretation = _InterpretationCommands()
    return (
        LifecycleCommandService(
            study=study,
            dataset=dataset,
            preprocess=preprocess,
            training=training,
            training_commands=training_commands,
            interpretation=interpretation,
            get_state=_state,
        ),
        study,
        dataset,
        preprocess,
        training,
        training_commands,
        interpretation,
    )


def test_lifecycle_service_resets_preprocess_and_clears_downstream_state() -> None:
    service, _study, dataset, preprocess, training, _, _ = _service()

    message, payload = _expect_payload(
        service.handle_reset_preprocess(ResetPreprocessCommand(confirmed=True)),
    )

    assert message == "Preprocessing reset to loaded raw data."
    assert payload == {
        "preprocess_operations_before": ["filter"],
        "had_epoch_data": True,
        "dataset_count_before": 2,
        "trainer_cleared": True,
    }
    assert training.cleaned is True
    assert preprocess.notifications == ["preprocess_changed"]
    assert dataset.notifications == [
        ("data_changed",),
        ("dataset_locked", False),
    ]


def test_lifecycle_service_rolls_back_reset_preprocess_failure() -> None:
    service, study, _dataset, _preprocess, _training, _, _ = _service()
    previous_preprocessed = [object()]
    previous_loaded = [object()]
    previous_backup = [object()]
    previous_epoch = object()
    previous_dataset = object()
    previous_generator = object()
    previous_trainer = object()
    study.data_manager.preprocessed_data_list = previous_preprocessed
    study.data_manager.loaded_data_list = previous_loaded
    study.data_manager.backup_loaded_data_list = previous_backup
    study.data_manager.dataset_locked = True
    study.data_manager.epoch_data = previous_epoch
    study.data_manager.datasets = [previous_dataset]
    study.data_manager.dataset_generator = previous_generator
    study.training_manager.trainer = previous_trainer
    study.fail_reset = True

    with pytest.raises(RuntimeError, match="reset failed"):
        service.handle_reset_preprocess(ResetPreprocessCommand(confirmed=True))

    assert study.data_manager.preprocessed_data_list == previous_preprocessed
    assert study.data_manager.loaded_data_list == previous_loaded
    assert study.data_manager.backup_loaded_data_list == previous_backup
    assert study.data_manager.dataset_locked is True
    assert study.data_manager.epoch_data is previous_epoch
    assert study.data_manager.datasets == [previous_dataset]
    assert study.data_manager.dataset_generator is previous_generator
    assert study.training_manager.trainer is previous_trainer


def test_lifecycle_service_reset_session_and_new_session_clear_dependent_state() -> (
    None
):
    (
        service,
        study,
        dataset,
        _preprocess,
        _training,
        training_commands,
        interpretation,
    ) = _service()

    reset_message = service.handle_reset_session(ResetSessionCommand(confirmed=True))
    new_message, new_payload = _expect_payload(
        service.handle_new_session(NewSessionCommand(confirmed=True)),
    )

    assert reset_message == "Session reset."
    assert new_message == "New session started."
    assert new_payload == {"single_session_backend": True}
    assert dataset.cleaned is True
    assert training_commands.cleared_managers == [
        study.training_manager,
        study.training_manager,
    ]
    assert interpretation.cleared is True
