"""Application boundary: dataset split behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import pytest

from tests.unit.backend.application.application_test_support import (
    _positive_epoch_data,
    _raw_mock,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ClearDatasetsCommand,
    CommandName,
    ErrorType,
    SaveDatasetSplitCommand,
)
from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.backend.dataset import (
    Dataset,
    DataSplittingConfig,
    TrainingType,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    Trainer,
)


def test_configure_dataset_split_save_preserves_existing_dataset_without_confirmation():
    service = ApplicationService(Study())
    raw = _raw_mock()
    existing_dataset = MagicMock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.study.data_manager.datasets = [existing_dataset]

    result = service.execute(
        SaveDatasetSplitCommand(),
    )

    assert result.ok is True
    assert service.study.data_manager.datasets == [existing_dataset]
    capability = service.get_capabilities().get(CommandName.CONFIGURE_DATASET_SPLIT)
    assert capability.enabled is True
    assert capability.requires_confirmation is False
    assert capability.destructive is False


def test_configure_dataset_split_save_is_non_destructive_with_existing_generator():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.study.data_manager.dataset_generator = MagicMock()
    service.get_state()

    capability = service.get_capabilities().get(CommandName.CONFIGURE_DATASET_SPLIT)

    assert capability.enabled is True
    assert capability.requires_confirmation is False
    assert capability.destructive is False


def test_deferred_dataset_replacement_failure_restores_previous_training_state(
    monkeypatch,
):
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    epoch_data = _positive_epoch_data()
    service.study.data_manager.epoch_data = epoch_data

    old_dataset = MagicMock(name="old_dataset")
    old_dataset.get_name.return_value = "existing_split"
    old_dataset.train_mask = np.array([True, False, False])
    old_dataset.val_mask = np.array([False, True, False])
    old_dataset.test_mask = np.array([False, False, True])
    old_generator = MagicMock(name="old_generator")
    old_trainer = Trainer([])
    old_history = [MagicMock(name="completed_training_record")]
    old_history[0].get_plans.return_value = []
    old_trainer.training_plan_holders = cast(Any, list(old_history))
    service.study.data_manager.datasets = [old_dataset]
    service.study.data_manager.dataset_generator = old_generator
    service.study.training_manager.trainer = old_trainer

    replacement_dataset = MagicMock(name="replacement_dataset")
    replacement_dataset.get_name.return_value = "replacement_split"
    replacement_dataset.get_epoch_data.return_value = epoch_data
    replacement_dataset.train_mask = np.array([True, True, False, False, False, False])
    replacement_dataset.val_mask = np.array([False, False, True, True, False, False])
    replacement_dataset.test_mask = np.array([False, False, False, False, True, True])
    replacement_generator = MagicMock(name="replacement_generator")
    replacement_generator.prepare_result.return_value = [replacement_dataset]
    partial_dataset = MagicMock(name="partial_dataset")
    partial_generator = MagicMock(name="partial_generator")

    def fail_after_partial_publication(_datasets, _generator):
        service.study.data_manager.datasets = [partial_dataset]
        service.study.data_manager.dataset_generator = partial_generator
        raise RuntimeError("dataset publication failed")

    service.study.get_datasets_generator = MagicMock(
        return_value=replacement_generator,
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.dataset_generation_service.audit_dataset_splits",
        lambda *_args, **_kwargs: SimpleNamespace(
            ok=True,
            dataset_count=1,
            issues=[],
        ),
    )
    service.pipeline_transaction.publish_datasets = MagicMock(
        side_effect=fail_after_partial_publication,
    )

    saved = service.execute(
        SaveDatasetSplitCommand(),
    )

    assert saved.ok is True
    assert service.study.data_manager.datasets == [old_dataset]
    assert service.study.data_manager.dataset_generator is old_generator
    assert service.study.training_manager.trainer is old_trainer
    candidate = service.dataset_generation.prepare_saved_split_candidate()
    with pytest.raises(ApplicationError) as exc_info:
        service.dataset_generation.commit_prepared_split(candidate)

    assert service.study.data_manager.datasets == [old_dataset]
    assert service.study.data_manager.dataset_generator is old_generator
    assert service.study.training_manager.trainer is old_trainer
    assert old_trainer.get_training_plan_holders() == old_history
    assert exc_info.value.diagnostics["state_preserved"] is True
    assert exc_info.value.diagnostics["replacement_mode"] == "replace_existing"


def test_configure_dataset_split_blocks_while_training_is_running():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.study.training_manager.is_training = MagicMock(return_value=True)

    result = service.execute(SaveDatasetSplitCommand())

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Stop training before changing data splitting." in result.message


def test_clear_datasets_blocks_while_training_is_running():
    service = ApplicationService(Study())
    service.study.data_manager.datasets = [MagicMock()]
    service.study.training_manager.is_training = MagicMock(return_value=True)
    service.training.clean_datasets = MagicMock()

    result = service.execute(ClearDatasetsCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Stop training before clearing generated datasets." in result.message
    service.training.clean_datasets.assert_not_called()


def test_training_split_preparation_fails_for_empty_or_leaking_splits():
    service = ApplicationService(Study())
    epoch_data = _positive_epoch_data()
    service.study.data_manager.epoch_data = epoch_data
    leaking = MagicMock()
    leaking.get_name.return_value = "bad_split"
    leaking.train_mask = np.array([True, True, False, False, False, False])
    leaking.val_mask = np.array([False, True, False, False, False, False])
    leaking.test_mask = np.zeros(6, dtype=bool)
    leaking.get_epoch_data.return_value = epoch_data
    generator = MagicMock()
    generator.prepare_result.return_value = [leaking]
    service.study.get_datasets_generator = MagicMock(return_value=generator)

    saved = service.execute(
        SaveDatasetSplitCommand(split_strategy="trial"),
    )

    assert saved.ok is True
    with pytest.raises(ApplicationError) as exc_info:
        service.dataset_generation.prepare_saved_split_candidate()

    error = exc_info.value
    state = service.get_state()
    assert error.error_type == ErrorType.DATA_MISMATCH
    assert "split audit" in error.message
    assert state.dataset.available is False
    assert state.dataset.generator_exists is False
    assert state.training.has_trainer is False
    assert error.diagnostics["state_preserved"] is True
    assert error.diagnostics["split_audit"]["ok"] is False
    assert any(
        "split is empty" in issue["message"]
        for issue in error.diagnostics["split_audit"]["issues"]
    )


def test_training_split_preparation_rolls_back_stale_apply(monkeypatch):
    service = ApplicationService(Study())
    epoch_data = _positive_epoch_data()
    service.study.data_manager.epoch_data = epoch_data
    replacement_dataset = MagicMock(name="replacement_dataset")
    replacement_dataset.get_name.return_value = "replacement_split"
    replacement_dataset.get_epoch_data.return_value = epoch_data
    replacement_dataset.train_mask = np.array([True, True, False, False, False, False])
    replacement_dataset.val_mask = np.array([False, False, True, True, False, False])
    replacement_dataset.test_mask = np.array([False, False, False, False, True, True])
    replacement_trainer = Trainer([])

    def prepare_after_new_trainer_started():
        service.study.training_manager.trainer = replacement_trainer
        return [replacement_dataset]

    generator = MagicMock()
    generator.prepare_result.side_effect = prepare_after_new_trainer_started
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    monkeypatch.setattr(
        "XBrainLab.backend.application.dataset_generation_service.audit_dataset_splits",
        lambda *_args, **_kwargs: SimpleNamespace(
            ok=True,
            dataset_count=1,
            issues=[],
        ),
    )

    saved = service.execute(SaveDatasetSplitCommand())

    assert saved.ok is True
    candidate = service.dataset_generation.prepare_saved_split_candidate()
    with pytest.raises(ApplicationError):
        service.dataset_generation.commit_prepared_split(candidate)
    state = service.get_state()
    assert state.dataset.available is False
    assert state.dataset.generator_exists is False
    assert state.training.has_trainer is True
    assert service.study.training_manager.trainer is replacement_trainer


def test_training_split_preparation_audits_custom_trial_protocol():
    service = ApplicationService(Study())
    epoch_data = _positive_epoch_data()
    service.study.data_manager.epoch_data = epoch_data
    dataset = Dataset(
        epoch_data,
        DataSplittingConfig(TrainingType.IND, False, [], []),
    )
    dataset.name = "trial_split"
    dataset.train_mask = np.array([True, True, False, False, False, False])
    dataset.val_mask = np.array([False, False, True, True, False, False])
    dataset.test_mask = np.array([False, False, False, False, True, True])
    generator = MagicMock()
    generator.prepare_result.return_value = [dataset]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    saved = service.execute(
        SaveDatasetSplitCommand(
            split_config={
                "train_type": "Individual",
                "is_cross_validation": False,
                "val_splitters": [
                    {
                        "split_type": "By Trial",
                        "split_unit": "Ratio",
                        "value": "0.2",
                    },
                ],
                "test_splitters": [
                    {
                        "split_type": "By Trial",
                        "split_unit": "Ratio",
                        "value": "0.2",
                    },
                ],
            },
        ),
    )

    assert saved.ok is True
    candidate = service.dataset_generation.prepare_saved_split_candidate()
    prepared = service.dataset_generation.commit_prepared_split(candidate)
    assert prepared["protocol"] == "trial-wise"
    assert service.get_state().dataset.available is True
