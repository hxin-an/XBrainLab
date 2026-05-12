"""Focused tests for dataset-generation command handlers."""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pytest

from XBrainLab.backend.application.commands import (
    ClearDatasetsCommand,
    GenerateDatasetCommand,
)
from XBrainLab.backend.application.dataset_generation_service import (
    DatasetGenerationCommandService,
    HandlerResult,
)
from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.backend.dataset import (
    DataSplittingConfig,
    SplitByType,
    TrainingType,
    ValSplitByType,
)


class _Epoch:
    def __init__(self) -> None:
        self.subjects = np.asarray([1, 1, 2, 3])
        self.sessions = np.asarray([1, 1, 2, 3])
        self.labels = np.asarray([1, 2, 1, 2])

    def get_subject_list_by_mask(self, mask: np.ndarray) -> np.ndarray:
        return self.subjects[mask]

    def get_session_list_by_mask(self, mask: np.ndarray) -> np.ndarray:
        return self.sessions[mask]

    def get_label_list_by_mask(self, mask: np.ndarray) -> np.ndarray:
        return self.labels[mask]


class _Dataset:
    def __init__(
        self,
        *,
        train: list[bool],
        val: list[bool],
        test: list[bool],
    ) -> None:
        self.train_mask = np.asarray(train)
        self.val_mask = np.asarray(val)
        self.test_mask = np.asarray(test)
        self._epoch = _Epoch()

    def get_name(self) -> str:
        return "focused-dataset"

    def get_epoch_data(self) -> _Epoch:
        return self._epoch


class _DataManager:
    def __init__(self) -> None:
        self.datasets: list[Any] = []
        self.dataset_generator: Any | None = None


class _TrainingManager:
    def __init__(self) -> None:
        self.trainer: Any | None = None


class _Study:
    def __init__(self) -> None:
        self.data_manager = _DataManager()
        self.training_manager = _TrainingManager()
        self.generated_config: DataSplittingConfig | None = None

    @property
    def datasets(self) -> list[Any]:
        return self.data_manager.datasets

    @property
    def dataset_generator(self) -> Any | None:
        return self.data_manager.dataset_generator

    @property
    def trainer(self) -> Any | None:
        return self.training_manager.trainer

    def get_datasets_generator(self, config: DataSplittingConfig) -> object:
        self.generated_config = config
        return object()


class _TrainingController:
    def __init__(self, study: _Study) -> None:
        self.study = study
        self.next_datasets: list[Any] = []
        self.next_trainer: Any | None = object()
        self.cleaned = False
        self.force_update: bool | None = None

    def apply_data_splitting(self, generator: Any) -> None:
        self.study.data_manager.dataset_generator = generator
        self.study.data_manager.datasets = self.next_datasets
        self.study.training_manager.trainer = self.next_trainer

    def clean_datasets(self, *, force_update: bool) -> None:
        self.cleaned = True
        self.force_update = force_update


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def _service() -> tuple[DatasetGenerationCommandService, _Study, _TrainingController]:
    study = _Study()
    training = _TrainingController(study)
    return (
        DatasetGenerationCommandService(study=study, training=training),
        study,
        training,
    )


def test_dataset_generation_service_builds_config_audits_and_summarizes() -> None:
    service, study, training = _service()
    training.next_datasets = [
        _Dataset(
            train=[True, True, False, False],
            val=[False, False, True, False],
            test=[False, False, False, True],
        ),
    ]

    message, payload = _expect_payload(
        service.handle_generate_dataset(
            GenerateDatasetCommand(
                split_strategy="trial",
                training_mode="group",
                test_ratio=0.25,
                val_ratio=0.25,
            ),
        ),
    )

    assert message == "Generated 1 dataset(s)."
    assert study.generated_config is not None
    assert study.generated_config.train_type == TrainingType.FULL
    assert payload["dataset_count"] == 1
    assert payload["protocol"] == "trial-wise"
    assert payload["split_audit"]["ok"] is True
    assert payload["split_summary"]["train_count"] == 2
    assert payload["split_summary"]["val_count"] == 1
    assert payload["split_summary"]["test_count"] == 1


@pytest.mark.parametrize(
    ("split_strategy", "expected_test_split", "expected_val_split", "protocol"),
    [
        ("trial", SplitByType.TRIAL, ValSplitByType.TRIAL, "trial-wise"),
        ("session", SplitByType.SESSION, ValSplitByType.SESSION, "session-wise"),
        ("subject", SplitByType.SUBJECT, ValSplitByType.SUBJECT, "subject-wise"),
    ],
)
def test_dataset_generation_service_maps_command_split_strategies_without_facade(
    split_strategy: str,
    expected_test_split: SplitByType,
    expected_val_split: ValSplitByType,
    protocol: str,
) -> None:
    service, study, training = _service()
    training.next_datasets = [
        _Dataset(
            train=[True, True, False, False],
            val=[False, False, True, False],
            test=[False, False, False, True],
        ),
    ]

    _message, payload = _expect_payload(
        service.handle_generate_dataset(
            GenerateDatasetCommand(
                split_strategy=split_strategy,
                test_ratio=0.25,
                val_ratio=0.25,
            ),
        ),
    )

    assert study.generated_config is not None
    assert (
        study.generated_config.test_splitter_list[0].split_type == expected_test_split
    )
    assert study.generated_config.val_splitter_list[0].split_type == expected_val_split
    assert payload["protocol"] == protocol
    assert payload["split_audit"]["ok"] is True


@pytest.mark.parametrize(
    ("training_mode", "expected_train_type"),
    [
        ("individual", TrainingType.IND),
        ("group", TrainingType.FULL),
    ],
)
def test_dataset_generation_service_maps_command_training_modes_without_facade(
    training_mode: str,
    expected_train_type: TrainingType,
) -> None:
    service, study, training = _service()
    training.next_datasets = [
        _Dataset(
            train=[True, True, False, False],
            val=[False, False, True, False],
            test=[False, False, False, True],
        ),
    ]

    _message, payload = _expect_payload(
        service.handle_generate_dataset(
            GenerateDatasetCommand(training_mode=training_mode),
        ),
    )

    assert study.generated_config is not None
    assert study.generated_config.train_type == expected_train_type
    assert payload["split_audit"]["ok"] is True


def test_dataset_generation_service_rolls_back_failed_split_audit() -> None:
    service, study, training = _service()
    previous_dataset = object()
    previous_generator = object()
    previous_trainer = object()
    study.data_manager.datasets = [previous_dataset]
    study.data_manager.dataset_generator = previous_generator
    study.training_manager.trainer = previous_trainer
    training.next_datasets = [
        _Dataset(
            train=[True, False, False],
            val=[False, False, False],
            test=[False, True, False],
        ),
    ]

    with pytest.raises(ApplicationError) as exc_info:
        service.handle_generate_dataset(
            GenerateDatasetCommand(generator=object(), split_strategy="trial"),
        )

    error = exc_info.value
    assert error.error_type == ErrorType.DATA_MISMATCH
    assert error.diagnostics["rolled_back"] is True
    assert any(
        "split is empty" in issue["message"]
        for issue in error.diagnostics["split_audit"]["issues"]
    )
    assert study.data_manager.datasets == [previous_dataset]
    assert study.data_manager.dataset_generator is previous_generator
    assert study.training_manager.trainer is previous_trainer


def test_dataset_generation_service_clears_dataset_state() -> None:
    service, study, training = _service()
    study.data_manager.datasets = [object(), object()]
    study.training_manager.trainer = object()

    message, payload = _expect_payload(
        service.handle_clear_datasets(ClearDatasetsCommand(confirmed=True)),
    )

    assert message == "Datasets and dependent training plans cleared."
    assert payload == {
        "dataset_count_before": 2,
        "trainer_cleared": True,
    }
    assert training.cleaned is True
    assert training.force_update is True
