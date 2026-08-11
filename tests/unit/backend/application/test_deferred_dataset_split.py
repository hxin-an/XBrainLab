"""Deferred dataset-split materialization through the public command spine."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
import torch

from XBrainLab.backend.application import (
    ApplicationService,
    CommandName,
    ConfigureTrainingCommand,
    DiscardTrainingPreparationCommand,
    SaveDatasetSplitCommand,
    TrainCommand,
    execute_automation_payload,
)
from XBrainLab.backend.application.dataset_split_preview import (
    DATASET_SPLIT_PREVIEW_ROW_LIMIT,
    DatasetSplitPreviewPublication,
    DatasetSplitPreviewRequest,
    DatasetSplitPreviewRow,
    DatasetSplitSpecification,
)
from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.backend.application.resource_guard import ResourcePreflightResult
from XBrainLab.backend.application.training_recommendation import (
    LAST_EPOCH_STRATEGY,
    TrainingRecommendationField,
    TrainingSettingProvenance,
)
from XBrainLab.backend.application.training_submission import (
    attach_training_submission_provenance,
)
from XBrainLab.backend.dataset import (
    Dataset,
    DataSplittingConfig,
    Epochs,
    EpochWindowProvenance,
    TrainingType,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    Trainer,
    TrainingEvaluation,
    TrainingOption,
)
from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
    TrainingRunIdentity,
)


def _epoch_data() -> Epochs:
    labels = np.asarray([0, 1] * 6, dtype=int)
    epoch = Epochs([])
    epoch.data = np.zeros((len(labels), 2, 512), dtype=np.float32)
    epoch.event_id = {"Left": 0, "Right": 1}
    epoch.label_map = {0: "Left", 1: "Right"}
    epoch.label = labels
    epoch.subject = np.zeros(len(labels), dtype=int)
    epoch.session = np.zeros(len(labels), dtype=int)
    epoch.idx = np.arange(len(labels), dtype=int)
    epoch.trial_group = np.arange(len(labels), dtype=int)
    epoch.subject_map = {0: "S01"}
    epoch.session_map = {0: "001"}
    epoch.ch_names = ["C3", "C4"]
    epoch.sfreq = 128.0
    epoch.epoch_window_provenance = tuple(
        EpochWindowProvenance(
            source_recording_id=f"content-sha256:{index:064x}",
            event_sample=index * 64,
            window_start_sample=index * 64,
            window_end_sample_exclusive=index * 64 + 512,
            source_sfreq=128.0,
            epoch_sfreq=128.0,
            tmin_seconds=0.0,
            tmax_seconds=511 / 128,
            source_coordinates_verified=True,
        )
        for index in range(len(labels))
    )
    return epoch


def _raw() -> MagicMock:
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    raw.get_subject_name.return_value = "S01"
    raw.get_session_name.return_value = "001"
    raw.is_raw.return_value = True
    mne_raw = MagicMock()
    mne_raw.ch_names = ["C3", "C4"]
    raw.get_mne.return_value = mne_raw
    return raw


def _specification(*, ratio: str = "0.2") -> DatasetSplitSpecification:
    return DatasetSplitSpecification.from_payload(
        {
            "train_type": "Individual",
            "is_cross_validation": False,
            "val_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "Ratio",
                    "value": ratio,
                }
            ],
            "test_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "Ratio",
                    "value": ratio,
                }
            ],
        }
    )


def _receipt(
    specification: DatasetSplitSpecification,
    *,
    generation: int,
    epoch: Epochs,
) -> Any:
    request = DatasetSplitPreviewRequest(
        request_id=f"preview-{generation}",
        publication_generation=generation,
        specification=specification,
    )
    publication = DatasetSplitPreviewPublication(
        request=request,
        generation=generation,
        epoch_token=id(epoch),
        rows=(
            DatasetSplitPreviewRow(
                name="S01",
                train_count=8,
                validation_count=2,
                test_count=2,
            ),
        ),
    )
    return publication.receipt


def _service_with_epoch(
    epoch: Epochs | None = None,
) -> tuple[ApplicationService, Epochs]:
    study = Study()
    raw = _raw()
    epoch = epoch or _epoch_data()
    study.data_manager.loaded_data_list = [raw]
    study.data_manager.preprocessed_data_list = [raw]
    study.data_manager.epoch_data = epoch
    study.set_training_option(
        TrainingOption(
            output_dir="./test-output",
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch=1,
            bs=4,
            lr=0.001,
            checkpoint_epoch=0,
            evaluation_option=TrainingEvaluation.LAST_EPOCH,
            repeat_num=1,
        )
    )
    return ApplicationService(study), epoch


def _two_subject_epoch_data() -> Epochs:
    epoch = _epoch_data()
    epoch.subject = np.asarray([0] * 6 + [1] * 6, dtype=int)
    epoch.subject_map = {0: "S01", 1: "S02"}
    return epoch


def _configure_training(service: ApplicationService) -> None:
    result = service.execute(
        ConfigureTrainingCommand(
            model_name="EEGNet",
            epoch=1,
            batch_size=4,
            learning_rate=0.001,
            device="cpu",
        )
    )
    assert result.ok is True


def _materialized_dataset(epoch: Epochs) -> Dataset:
    dataset = Dataset(
        epoch,
        DataSplittingConfig(
            train_type=TrainingType.IND,
            is_cross_validation=False,
            val_splitter_list=[],
            test_splitter_list=[],
        ),
    )
    dataset.name = "S01"
    dataset.train_mask[:6] = True
    dataset.val_mask[6:9] = True
    dataset.test_mask[9:] = True
    return dataset


def _publish_training_identity(service: ApplicationService) -> int:
    trainer = Trainer([])
    trainer.run(interact=False)
    service.study.training_manager.trainer = trainer
    return 1


def test_split_confirmation_saves_typed_summary_without_materializing_masks() -> None:
    service, epoch = _service_with_epoch()
    generation = service.get_view_publication().generation
    specification = _specification()
    service.study.get_datasets_generator = MagicMock(
        side_effect=AssertionError("split confirmation must not create a generator")
    )

    result = service.execute(
        SaveDatasetSplitCommand(
            split_config=specification.to_payload(),
            preview_receipt=_receipt(
                specification,
                generation=generation,
                epoch=epoch,
            ),
        ),
        expected_publication_generation=generation,
    )

    assert result.ok is True
    assert result.message == "Data splitting specification saved."
    assert result.state.dataset.available is False
    assert result.state.dataset.generator_exists is False
    assert result.state.dataset.split_spec_saved is True
    assert result.state.dataset.split_materialized is False
    assert result.state.dataset.split_preview_summary == {
        "dataset_count": 1,
        "total_count": 1,
        "truncated_count": 0,
        "train_count": 8,
        "validation_count": 2,
        "test_count": 2,
        "rows": [
            {
                "name": "S01",
                "train_count": 8,
                "validation_count": 2,
                "test_count": 2,
            }
        ],
    }
    assert result.state.dataset.split_lifecycle.value == "saved"
    assert result.state.dataset.active_split_summary == {}
    assert result.state.dataset.last_split_attempt == {}
    service.study.get_datasets_generator.assert_not_called()


def test_saved_split_publishes_consistent_training_readiness_before_materialization() -> (
    None
):
    service, epoch = _service_with_epoch()
    specification = _specification()
    generation = service.get_view_publication().generation

    saved = service.execute(
        SaveDatasetSplitCommand(
            split_config=specification.to_payload(),
            preview_receipt=_receipt(
                specification,
                generation=generation,
                epoch=epoch,
            ),
        ),
        expected_publication_generation=generation,
    )
    assert saved.ok is True
    _configure_training(service)

    state = service.get_state()
    train_capability = service.get_capabilities().get(CommandName.TRAIN)

    assert state.dataset.split_spec_saved is True
    assert state.dataset.split_materialized is False
    assert train_capability.enabled is True
    assert state.training.missing_requirements == []


def test_real_preview_receipt_round_trips_to_deferred_materialization(
    monkeypatch,
) -> None:
    service, _epoch = _service_with_epoch(_two_subject_epoch_data())
    specification = _specification()
    generation = service.get_view_publication().generation
    preview = service.get_dataset_split_preview(
        DatasetSplitPreviewRequest(
            request_id="real-two-subject-preview",
            publication_generation=generation,
            specification=specification,
        )
    )

    saved = service.execute(
        SaveDatasetSplitCommand(
            split_config=specification.to_payload(),
            preview_receipt=preview.receipt,
        ),
        expected_publication_generation=generation,
    )
    _configure_training(service)
    service.training.start_training = MagicMock(
        side_effect=lambda **_kwargs: _publish_training_identity(service)
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda *_args, **_kwargs: ResourcePreflightResult(
            issues=(), diagnostics={"risk_level": "safe"}
        ),
    )

    trained = service.execute(TrainCommand(confirmed=True))

    assert saved.ok is True
    assert trained.ok is True, trained.diagnostics
    preview_counts = {
        row.name: (row.train_count, row.validation_count, row.test_count)
        for row in preview.rows
    }
    materialized_counts = {
        str(dataset.get_name()): (
            int(np.count_nonzero(dataset.train_mask)),
            int(np.count_nonzero(dataset.val_mask)),
            int(np.count_nonzero(dataset.test_mask)),
        )
        for dataset in service.study.datasets
    }
    assert len(preview.rows) == 2
    assert materialized_counts == preview_counts
    assert trained.state.dataset.split_lifecycle.value == "verified"


def test_recommendation_preserves_only_manual_fields_across_split_transition(
    monkeypatch,
) -> None:
    service, epoch = _service_with_epoch()
    initial_specification = _specification()
    initial_generation = service.get_view_publication().generation
    initial_saved = service.execute(
        SaveDatasetSplitCommand(
            split_config=initial_specification.to_payload(),
            preview_receipt=_receipt(
                initial_specification,
                generation=initial_generation,
                epoch=epoch,
            ),
        ),
        expected_publication_generation=initial_generation,
    )
    assert initial_saved.ok is True
    initial = service.get_training_recommendation(
        prospective_model_name="EEGNet",
    )
    manual_epochs = initial.values.epochs + 7
    configured = service.execute(
        attach_training_submission_provenance(
            ConfigureTrainingCommand(
                model_name="EEGNet",
                epoch=manual_epochs,
                batch_size=initial.values.batch_size,
                learning_rate=initial.values.learning_rate,
                device="cpu",
                optimizer=initial.values.optimizer,
                evaluation_option=initial.values.evaluation_strategy,
            ),
            frozenset({TrainingRecommendationField.EPOCHS}),
        )
    )
    assert configured.ok is True
    assert configured.state.training.recommendation is not None
    assert configured.state.training.recommendation.manual_fields == (
        TrainingRecommendationField.EPOCHS,
    )

    no_validation_specification = DatasetSplitSpecification.from_payload(
        {
            "train_type": "Individual",
            "is_cross_validation": False,
            "val_splitters": [],
            "test_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "Ratio",
                    "value": "0.2",
                }
            ],
        }
    )
    next_generation = service.get_view_publication().generation
    no_validation_receipt = DatasetSplitPreviewPublication(
        request=DatasetSplitPreviewRequest(
            request_id="no-validation-preview",
            publication_generation=next_generation,
            specification=no_validation_specification,
        ),
        generation=next_generation,
        epoch_token=id(epoch),
        rows=(
            DatasetSplitPreviewRow(
                name="S01",
                train_count=10,
                validation_count=0,
                test_count=2,
            ),
        ),
    ).receipt
    changed = service.execute(
        SaveDatasetSplitCommand(
            split_config=no_validation_specification.to_payload(),
            preview_receipt=no_validation_receipt,
        ),
        expected_publication_generation=next_generation,
    )
    assert changed.ok is True

    refreshed = service.get_training_recommendation(
        prospective_model_name="Deep4Net",
    )
    assert refreshed.values.epochs == manual_epochs
    assert refreshed.provenance["epochs"] is TrainingSettingProvenance.MANUAL
    assert refreshed.values.evaluation_strategy == LAST_EPOCH_STRATEGY
    assert refreshed.provenance["evaluation_strategy"] is (
        TrainingSettingProvenance.RECOMMENDED
    )

    materialized = _materialized_dataset(epoch)
    materialized.train_mask[:] = False
    materialized.val_mask[:] = False
    materialized.test_mask[:] = False
    materialized.train_mask[:8] = True
    materialized.test_mask[8:] = True
    generator = MagicMock()
    generator.prepare_result.return_value = [materialized]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    service.training.start_training = MagicMock(
        side_effect=lambda **_kwargs: _publish_training_identity(service)
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda *_args, **_kwargs: ResourcePreflightResult(
            issues=(), diagnostics={"risk_level": "safe"}
        ),
    )

    trained = service.execute(TrainCommand(confirmed=True))
    final_recommendation = service.get_training_recommendation(
        prospective_model_name="Deep4Net",
    )

    assert trained.ok is True, trained.diagnostics.get("split_audit")
    assert final_recommendation.values.epochs == manual_epochs
    assert final_recommendation.values.evaluation_strategy == LAST_EPOCH_STRATEGY
    assert final_recommendation.manual_fields == (TrainingRecommendationField.EPOCHS,)


def test_train_materializes_once_and_state_reads_skip_epoch_payload(
    monkeypatch,
) -> None:
    service, epoch = _service_with_epoch()
    specification = _specification()
    generation = service.get_view_publication().generation
    saved = service.execute(
        SaveDatasetSplitCommand(
            split_config=specification.to_payload(),
            preview_receipt=_receipt(
                specification,
                generation=generation,
                epoch=epoch,
            ),
        ),
        expected_publication_generation=generation,
    )
    assert saved.ok is True
    _configure_training(service)
    train_capability = service.get_capabilities().get(CommandName.TRAIN)
    assert train_capability.enabled is True
    assert "Save a valid data splitting specification before training." not in (
        train_capability.reasons
    )

    dataset = _materialized_dataset(epoch)
    generator = MagicMock()
    generator.prepare_result.return_value = [dataset]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    service.training.start_training = MagicMock(
        side_effect=lambda **_kwargs: _publish_training_identity(service)
    )

    import XBrainLab.backend.application.dataset_generation_service as split_service

    real_audit = split_service.audit_dataset_splits
    audit_calls = 0

    def counting_audit(*args, **kwargs):
        nonlocal audit_calls
        audit_calls += 1
        return real_audit(*args, **kwargs)

    monkeypatch.setattr(split_service, "audit_dataset_splits", counting_audit)
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda *_args, **_kwargs: ResourcePreflightResult(
            issues=(), diagnostics={"risk_level": "safe"}
        ),
    )

    first = service.execute(TrainCommand(confirmed=True))
    hostile_epoch_getter = MagicMock(
        side_effect=AssertionError("state reads must not access epoch payload")
    )
    dataset.get_epoch_data = hostile_epoch_getter  # type: ignore[method-assign]
    direct_state = service.dataset_generation.dataset_split_state([dataset])
    first_snapshot = service.get_state()
    second_snapshot = service.get_state()
    hostile_epoch_getter.assert_not_called()

    unchanged_generation = service.get_view_publication().generation
    unchanged = service.execute(
        SaveDatasetSplitCommand(
            split_config=specification.to_payload(),
            preview_receipt=_receipt(
                specification,
                generation=unchanged_generation,
                epoch=epoch,
            ),
        ),
        expected_publication_generation=unchanged_generation,
    )
    second = service.execute(TrainCommand(confirmed=True))

    assert first.ok is True
    assert second.ok is True
    assert generator.prepare_result.call_count == 1
    assert audit_calls == 1
    assert first.diagnostics["split_preparation"]["materialized"] is True
    assert second.diagnostics["split_preparation"]["cache_reused"] is True
    assert unchanged.ok is True
    assert unchanged.state.dataset.split_materialized is True
    assert direct_state["split_materialized"] is True
    assert (
        first_snapshot.dataset.active_split_summary
        == second_snapshot.dataset.active_split_summary
    )
    assert first_snapshot.dataset.active_split_summary["audit"]["ok"] is True


def test_changed_split_spec_invalidates_materialized_masks_without_regeneration(
    monkeypatch,
) -> None:
    service, epoch = _service_with_epoch()
    first_spec = _specification(ratio="0.2")
    generation = service.get_view_publication().generation
    service.execute(
        SaveDatasetSplitCommand(
            split_config=first_spec.to_payload(),
            preview_receipt=_receipt(
                first_spec,
                generation=generation,
                epoch=epoch,
            ),
        ),
        expected_publication_generation=generation,
    )
    _configure_training(service)
    generator = MagicMock()
    generator.prepare_result.return_value = [_materialized_dataset(epoch)]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    service.training.start_training = MagicMock(
        side_effect=lambda **_kwargs: _publish_training_identity(service)
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda *_args, **_kwargs: ResourcePreflightResult(
            issues=(), diagnostics={"risk_level": "safe"}
        ),
    )
    assert service.execute(TrainCommand(confirmed=True)).ok is True
    previous_datasets = list(service.study.datasets)
    previous_trainer = service.study.training_manager.trainer
    previous_summary = service.get_state().dataset.active_split_summary

    next_spec = _specification(ratio="0.25")
    next_generation = service.get_view_publication().generation
    changed = service.execute(
        SaveDatasetSplitCommand(
            split_config=next_spec.to_payload(),
            preview_receipt=_receipt(
                next_spec,
                generation=next_generation,
                epoch=epoch,
            ),
        ),
        expected_publication_generation=next_generation,
    )

    assert changed.ok is True
    assert changed.state.dataset.split_spec_saved is True
    assert changed.state.dataset.split_materialized is False
    assert changed.state.dataset.available is True
    assert changed.state.dataset.split_lifecycle.value == "saved"
    assert changed.state.dataset.active_split_summary == previous_summary
    assert service.study.datasets == previous_datasets
    assert service.study.training_manager.trainer is previous_trainer
    assert generator.prepare_result.call_count == 1


def test_train_blocks_existing_datasets_without_saved_split_specification() -> None:
    study = Study()
    raw = _raw()
    epoch = _epoch_data()
    study.data_manager.loaded_data_list = [raw]
    study.data_manager.preprocessed_data_list = [raw]
    study.data_manager.epoch_data = epoch
    study.data_manager.datasets = [_materialized_dataset(epoch)]
    service = ApplicationService(study)
    _configure_training(service)

    capability = service.get_capabilities().get(CommandName.TRAIN)
    result = service.execute(TrainCommand(confirmed=True))

    assert capability.enabled is False
    assert "Save a valid data splitting specification before training." in (
        capability.reasons
    )
    assert result.failed is True
    assert (
        "Save a valid data splitting specification before training." in result.message
    )


def test_changed_epoch_invalidates_saved_split_and_train_capability() -> None:
    service, epoch = _service_with_epoch()
    specification = _specification()
    generation = service.get_view_publication().generation
    saved = service.execute(
        SaveDatasetSplitCommand(
            split_config=specification.to_payload(),
            preview_receipt=_receipt(
                specification,
                generation=generation,
                epoch=epoch,
            ),
        ),
        expected_publication_generation=generation,
    )
    assert saved.ok is True

    service.study.data_manager.epoch_data = _epoch_data()
    state = service.get_state()
    train_capability = service.get_capabilities().get(CommandName.TRAIN)

    assert state.dataset.split_spec_saved is False
    assert state.dataset.split_preview_summary == {}
    assert train_capability.enabled is False
    assert "Save a valid data splitting specification before training." in (
        train_capability.reasons
    )


def test_mismatched_preview_receipt_is_rejected_without_saving_stale_rows() -> None:
    service, epoch = _service_with_epoch()
    generation = service.get_view_publication().generation
    previewed = _specification(ratio="0.2")
    submitted = _specification(ratio="0.25")

    result = service.execute(
        SaveDatasetSplitCommand(
            split_config=submitted.to_payload(),
            preview_receipt=_receipt(
                previewed,
                generation=generation,
                epoch=epoch,
            ),
        ),
        expected_publication_generation=generation,
    )

    assert result.failed is True
    assert "preview receipt" in result.message.casefold()
    assert result.state.dataset.split_spec_saved is False
    assert result.state.dataset.split_preview_summary == {}


def test_stale_publication_and_epoch_preview_receipts_are_rejected() -> None:
    service, epoch = _service_with_epoch()
    specification = _specification()
    original_generation = service.get_view_publication().generation
    publication_receipt = _receipt(
        specification,
        generation=original_generation,
        epoch=epoch,
    )
    _configure_training(service)
    current_generation = service.get_view_publication().generation

    stale_publication = service.execute(
        SaveDatasetSplitCommand(
            split_config=specification.to_payload(),
            preview_receipt=publication_receipt,
        ),
        expected_publication_generation=current_generation,
    )

    epoch_generation = service.get_view_publication().generation
    epoch_receipt = _receipt(
        specification,
        generation=epoch_generation,
        epoch=epoch,
    )
    service.study.data_manager.epoch_data = _epoch_data()
    stale_epoch = service.execute(
        SaveDatasetSplitCommand(
            split_config=specification.to_payload(),
            preview_receipt=epoch_receipt,
        ),
        expected_publication_generation=epoch_generation,
    )

    assert stale_publication.failed is True
    assert "stale" in stale_publication.message.casefold()
    assert stale_epoch.failed is True
    assert "current EEG epochs" in stale_epoch.message


def test_automation_json_saves_split_then_train_materializes_once(monkeypatch) -> None:
    service, epoch = _service_with_epoch()
    generator = MagicMock()
    generator.prepare_result.return_value = [_materialized_dataset(epoch)]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    service.training.start_training = MagicMock(
        side_effect=lambda **_kwargs: _publish_training_identity(service)
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda *_args, **_kwargs: ResourcePreflightResult(
            issues=(), diagnostics={"risk_level": "safe"}
        ),
    )

    saved = execute_automation_payload(
        service,
        {
            "command": "configure_dataset_split",
            "arguments": {"split_config": _specification().to_payload()},
        },
    )
    configured = execute_automation_payload(
        service,
        {
            "command": "configure_training",
            "arguments": {
                "model_name": "EEGNet",
                "epoch": 1,
                "batch_size": 4,
                "learning_rate": 0.001,
                "device": "cpu",
            },
        },
    )
    trained = execute_automation_payload(
        service,
        {"command": "train", "arguments": {"confirmed": True}},
    )

    assert saved.result is not None and saved.result["status"] == "ok"
    assert saved.state["dataset"]["split_spec_saved"] is True
    assert saved.state["dataset"]["available"] is False
    assert configured.result is not None and configured.result["status"] == "ok"
    assert trained.result is not None and trained.result["status"] == "ok"
    assert generator.prepare_result.call_count == 1


def test_train_failure_result_and_state_share_bounded_audit_and_preserve_old_state(
    monkeypatch,
) -> None:
    service, epoch = _service_with_epoch()
    specification = _specification()
    generation = service.get_view_publication().generation
    saved = service.execute(
        SaveDatasetSplitCommand(
            split_config=specification.to_payload(),
            preview_receipt=_receipt(
                specification,
                generation=generation,
                epoch=epoch,
            ),
        ),
        expected_publication_generation=generation,
    )
    assert saved.ok is True
    _configure_training(service)

    old_dataset = _materialized_dataset(epoch)
    old_trainer = Trainer([])
    old_trainer.run(interact=False)
    service.study.data_manager.datasets = [old_dataset]
    service.study.data_manager.dataset_generator = MagicMock(name="old_generator")
    service.study.training_manager.trainer = old_trainer

    candidate = _materialized_dataset(epoch)
    generator = MagicMock()
    generator.prepare_result.return_value = [candidate]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    issues = [
        SimpleNamespace(
            dataset_name=f"candidate-{index}",
            severity="error",
            message="train and test splits overlap",
            indices=list(range(1_000)),
            details={"samples": list(range(1_000)), "kind": "overlap"},
        )
        for index in range(30)
    ]
    full_serializer = MagicMock(
        side_effect=AssertionError("failed audits must not serialize full payloads")
    )
    audit = SimpleNamespace(
        ok=False,
        dataset_count=1,
        issues=issues,
        to_dict=full_serializer,
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.dataset_generation_service.audit_dataset_splits",
        lambda *_args, **_kwargs: audit,
    )

    result = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.diagnostics["state_preserved"] is True
    result_audit = result.diagnostics["split_audit"]
    state_audit = result.state.dataset.last_split_attempt["audit"]
    assert result_audit == state_audit
    assert len(result_audit["issues"]) == 20
    assert result_audit["truncated_issue_count"] == 10
    assert all(len(issue["indices"]) == 10 for issue in result_audit["issues"])
    assert all(
        len(issue["details"]["samples"]) == 10 for issue in result_audit["issues"]
    )
    assert service.study.datasets == [old_dataset]
    assert service.study.datasets[0] is old_dataset
    assert service.study.training_manager.trainer is old_trainer
    assert result.state.dataset.split_lifecycle.value == "failed"
    assert result.state.dataset.active_split_summary == {}
    full_serializer.assert_not_called()


def _install_existing_training_state(
    service: ApplicationService,
    epoch: Epochs,
) -> tuple[Dataset, Trainer, Any]:
    old_dataset = _materialized_dataset(epoch)
    old_trainer = Trainer([])
    old_trainer.run(interact=False)
    completed_history = MagicMock(name="completed_training_history")
    completed_history.get_name.return_value = "completed sentinel"
    completed_history.get_plans.return_value = []
    old_trainer.training_plan_holders = [completed_history]
    service.study.data_manager.datasets = [old_dataset]
    service.study.data_manager.dataset_generator = MagicMock(name="old_generator")
    service.study.training_manager.trainer = old_trainer
    return old_dataset, old_trainer, completed_history


def _save_split_and_configure_training(
    service: ApplicationService,
    epoch: Epochs,
) -> None:
    specification = _specification()
    generation = service.get_view_publication().generation
    saved = service.execute(
        SaveDatasetSplitCommand(
            split_config=specification.to_payload(),
            preview_receipt=_receipt(
                specification,
                generation=generation,
                epoch=epoch,
            ),
        ),
        expected_publication_generation=generation,
    )
    assert saved.ok is True
    _configure_training(service)


def test_training_resource_block_preserves_active_dataset_and_trainer(
    monkeypatch,
) -> None:
    service, epoch = _service_with_epoch()
    _save_split_and_configure_training(service, epoch)
    old_dataset, old_trainer, _history = _install_existing_training_state(
        service, epoch
    )
    candidate = _materialized_dataset(epoch)
    generator = MagicMock()
    generator.prepare_result.return_value = [candidate]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    service.training.start_training = MagicMock()
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda datasets, *_args: ResourcePreflightResult(
            issues=("Candidate split exceeds available memory.",),
            diagnostics={
                "risk_level": "blocking",
                "dataset_ids": [id(dataset) for dataset in datasets],
            },
        ),
    )

    result = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.diagnostics["state_preserved"] is True
    assert result.diagnostics["resource_preflight"]["risk_level"] == "blocking"
    assert result.diagnostics["resource_preflight"]["dataset_ids"] == [id(candidate)]
    assert service.study.datasets[0] is old_dataset
    assert service.study.training_manager.trainer is old_trainer
    assert generator.prepare_result.call_count == 1
    assert service.dataset_generation.discard_prepared_split() is False
    service.training.start_training.assert_not_called()


def test_training_start_failure_restores_active_dataset_trainer_and_history(
    monkeypatch,
) -> None:
    service, epoch = _service_with_epoch()
    _save_split_and_configure_training(service, epoch)
    old_dataset, old_trainer, history = _install_existing_training_state(service, epoch)
    old_generator = service.study.data_manager.dataset_generator
    history_before = old_trainer.training_plan_holders

    candidate = _materialized_dataset(epoch)
    generator = MagicMock()
    generator.prepare_result.return_value = [candidate]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    failed_replacement_trainer = MagicMock(name="failed_replacement_trainer")

    def fail_after_replacement_trainer_is_published(**_kwargs) -> None:
        service.study.training_manager.trainer = failed_replacement_trainer
        raise RuntimeError("training startup failed")

    service.training.start_training = MagicMock(
        side_effect=fail_after_replacement_trainer_is_published
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda datasets, *_args: ResourcePreflightResult(
            issues=(),
            diagnostics={
                "risk_level": "safe",
                "dataset_ids": [id(dataset) for dataset in datasets],
            },
        ),
    )

    result = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.diagnostics["state_preserved"] is True
    assert result.diagnostics["split_rollback"] is True
    assert service.study.datasets == [old_dataset]
    assert service.study.datasets[0] is old_dataset
    assert service.study.data_manager.dataset_generator is old_generator
    assert service.study.training_manager.trainer is old_trainer
    assert old_trainer.training_plan_holders is history_before
    assert old_trainer.training_plan_holders == [history]
    failed_replacement_trainer.clean.assert_called_once_with(force_update=True)
    assert service.dataset_generation.discard_prepared_split() is False


def test_split_commit_cleanup_failure_restores_trainer_and_dataset(
    monkeypatch,
) -> None:
    service, epoch = _service_with_epoch()
    _save_split_and_configure_training(service, epoch)
    old_dataset, old_trainer, history = _install_existing_training_state(service, epoch)
    old_generator = service.study.data_manager.dataset_generator
    candidate_dataset = _materialized_dataset(epoch)
    generator = MagicMock()
    generator.prepare_result.return_value = [candidate_dataset]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    candidate = service.dataset_generation.prepare_saved_split_candidate()
    original_clean = old_trainer.clean
    clean_attempts = 0

    def fail_once(*, force_update: bool) -> None:
        nonlocal clean_attempts
        clean_attempts += 1
        if clean_attempts == 1:
            old_trainer.training_plan_holders = []
            raise RuntimeError("trainer cleanup failed")
        original_clean(force_update=force_update)

    monkeypatch.setattr(old_trainer, "clean", fail_once)

    with pytest.raises(ApplicationError) as exc_info:
        service.dataset_generation.commit_prepared_split(candidate)

    assert exc_info.value.diagnostics["state_preserved"] is True
    assert clean_attempts == 2
    assert service.study.datasets == [old_dataset]
    assert service.study.data_manager.dataset_generator is old_generator
    assert service.study.training_manager.trainer is old_trainer
    assert old_trainer.training_plan_holders == [history]


def test_real_deferred_start_failure_restores_saliency_and_pipeline_identities(
    monkeypatch,
) -> None:
    service, _epoch = _service_with_epoch()
    initial_specification = _specification(ratio="0.2")
    assert service.execute(
        SaveDatasetSplitCommand(split_config=initial_specification.to_payload())
    ).ok
    initial_candidate = service.dataset_generation.prepare_saved_split_candidate()
    service.dataset_generation.commit_prepared_split(initial_candidate)
    _configure_training(service)

    service.study.generate_plan(force_update=True, append=False)
    manager = service.study.training_manager
    previous_trainer = manager.trainer
    assert previous_trainer is not None
    previous_dataset = service.study.datasets[0]
    previous_generator = service.study.data_manager.dataset_generator
    dataset_generation = service.dataset_generation._service()
    previous_active_split = dataset_generation._active_split
    previous_split_summary = service.get_state().dataset.active_split_summary
    previous_record = previous_trainer.get_training_plan_holders()[0].get_plans()[0]
    saliency_result = EvalRecord(
        label=np.asarray([0, 1], dtype=int),
        output=np.asarray([[0.9, 0.1], [0.2, 0.8]], dtype=np.float32),
        gradient={0: np.ones((1, 2, 4), dtype=np.float32)},
        gradient_input={},
        smoothgrad={},
        smoothgrad_sq={},
        vargrad={},
        evaluation_split="test",
    )
    previous_record.set_eval_record(saliency_result)
    training_generation = previous_trainer.get_state_snapshot_token().generation
    previous_saliency_status = (
        PostTrainingSaliencyStatus.pending(
            generation=7,
            run=TrainingRunIdentity(
                trainer_id=previous_trainer.get_state_snapshot_identity(),
                run_id=1,
            ),
            training_generation=training_generation,
            methods=("Gradient",),
        )
        .transition(
            generation=7,
            phase=PostTrainingSaliencyPhase.RUNNING,
            message="Automatic saliency is running.",
        )
        .transition(
            generation=7,
            phase=PostTrainingSaliencyPhase.SUCCEEDED,
            message="Automatic saliency finished.",
        )
    )
    manager._saliency_request_sequence = previous_saliency_status.generation
    manager._saliency_job_sequence = previous_saliency_status.generation
    manager._post_training_saliency_status = previous_saliency_status

    replacement_specification = _specification(ratio="0.25")
    assert service.execute(
        SaveDatasetSplitCommand(split_config=replacement_specification.to_payload())
    ).ok
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda *_args, **_kwargs: ResourcePreflightResult(
            issues=(), diagnostics={"risk_level": "safe"}
        ),
    )
    failed_trainers: list[Trainer] = []

    def fail_after_real_plan_generation(*, interact: bool = False) -> None:
        del interact
        replacement_trainer = manager.trainer
        assert replacement_trainer is not None
        assert replacement_trainer is not previous_trainer
        failed_trainers.append(replacement_trainer)
        raise RuntimeError("injected training start failure")

    monkeypatch.setattr(service.study, "train", fail_after_real_plan_generation)

    result = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.diagnostics["state_preserved"] is True
    assert result.diagnostics["split_rollback"] is True
    assert len(failed_trainers) == 1
    assert failed_trainers[0].interrupt is True
    assert all(
        holder.interrupt for holder in failed_trainers[0].get_training_plan_holders()
    )
    assert service.study.datasets[0] is previous_dataset
    assert service.study.data_manager.dataset_generator is previous_generator
    assert manager.trainer is previous_trainer
    assert dataset_generation._active_split is previous_active_split
    assert service.get_state().dataset.active_split_summary == previous_split_summary
    assert manager.get_post_training_saliency_status() is previous_saliency_status
    restored_record = previous_trainer.get_training_plan_holders()[0].get_plans()[0]
    assert restored_record is previous_record
    assert restored_record.get_saliency_eval_record() is saliency_result


def test_training_restart_failure_restores_verified_split_history(monkeypatch) -> None:
    service, epoch = _service_with_epoch()
    _save_split_and_configure_training(service, epoch)
    candidate = _materialized_dataset(epoch)
    generator = MagicMock()
    generator.prepare_result.return_value = [candidate]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda datasets, *_args: ResourcePreflightResult(
            issues=(),
            diagnostics={
                "risk_level": "safe",
                "dataset_ids": [id(dataset) for dataset in datasets],
            },
        ),
    )
    service.training.start_training = MagicMock(
        side_effect=lambda **_kwargs: _publish_training_identity(service)
    )
    assert service.execute(TrainCommand(confirmed=True)).ok is True

    verified_dataset = service.study.datasets[0]
    verified_generator = service.study.data_manager.dataset_generator
    previous_trainer = service.study.training_manager.trainer
    assert previous_trainer is not None
    history = MagicMock(name="verified_training_history")
    previous_trainer.training_plan_holders = [history]
    failed_replacement_trainer = MagicMock(name="failed_restart_trainer")

    def fail_restart_after_replacement(**_kwargs) -> None:
        service.study.training_manager.trainer = failed_replacement_trainer
        raise RuntimeError("training restart failed")

    service.training.start_training = MagicMock(
        side_effect=fail_restart_after_replacement
    )

    result = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.diagnostics["state_preserved"] is True
    assert result.diagnostics["split_rollback"] is True
    assert service.study.datasets[0] is verified_dataset
    assert service.study.data_manager.dataset_generator is verified_generator
    assert service.study.training_manager.trainer is previous_trainer
    assert previous_trainer.training_plan_holders == [history]
    failed_replacement_trainer.clean.assert_called_once_with(force_update=True)


def test_real_append_restart_failure_removes_only_new_training_plans(
    monkeypatch,
) -> None:
    service, epoch = _service_with_epoch()
    _save_split_and_configure_training(service, epoch)
    candidate = _materialized_dataset(epoch)
    generator = MagicMock()
    generator.prepare_result.return_value = [candidate]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda *_args, **_kwargs: ResourcePreflightResult(
            issues=(), diagnostics={"risk_level": "safe"}
        ),
    )
    real_start_training = service.training.start_training
    service.training.start_training = MagicMock(
        side_effect=lambda **_kwargs: _publish_training_identity(service)
    )
    assert service.execute(TrainCommand(confirmed=True)).ok is True

    previous_trainer = Trainer([])
    completed_history = MagicMock(name="completed_history")
    previous_trainer.training_plan_holders.append(completed_history)
    previous_trainer.current_idx = 1
    service.study.training_manager.trainer = previous_trainer
    service.training.start_training = real_start_training
    monkeypatch.setattr(
        service.study,
        "train",
        MagicMock(side_effect=RuntimeError("training admission failed")),
    )

    result = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.diagnostics["state_preserved"] is True
    assert result.diagnostics["split_rollback"] is True
    assert service.study.training_manager.trainer is previous_trainer
    assert previous_trainer.training_plan_holders == [completed_history]
    assert previous_trainer.current_idx == 1


def test_cleanup_failure_keeps_candidate_dataset_and_trainer_paired(
    monkeypatch,
) -> None:
    service, epoch = _service_with_epoch()
    _save_split_and_configure_training(service, epoch)
    old_dataset, old_trainer, _history = _install_existing_training_state(
        service,
        epoch,
    )
    candidate = _materialized_dataset(epoch)
    generator = MagicMock()
    generator.prepare_result.return_value = [candidate]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    failed_trainer = MagicMock(name="failed_trainer")
    failed_trainer.clean.side_effect = RuntimeError("cleanup failed")

    def fail_after_replacement(**_kwargs) -> None:
        service.study.training_manager.trainer = failed_trainer
        raise RuntimeError("training startup failed")

    service.training.start_training = MagicMock(side_effect=fail_after_replacement)
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda *_args, **_kwargs: ResourcePreflightResult(
            issues=(), diagnostics={"risk_level": "safe"}
        ),
    )

    result = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.diagnostics["state_preserved"] is False
    assert result.diagnostics["split_rollback"] is False
    assert result.diagnostics["rollback_failed"] is True
    assert service.study.datasets == [candidate]
    assert service.study.training_manager.trainer is failed_trainer
    assert service.study.datasets != [old_dataset]
    assert service.study.training_manager.trainer is not old_trainer


def test_training_resource_warning_and_cancel_preserve_active_identity(
    monkeypatch,
) -> None:
    service, epoch = _service_with_epoch()
    _save_split_and_configure_training(service, epoch)
    old_dataset, old_trainer, history = _install_existing_training_state(service, epoch)
    candidate = _materialized_dataset(epoch)
    generator = MagicMock()
    generator.prepare_result.return_value = [candidate]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    service.training.start_training = MagicMock()
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda datasets, *_args: ResourcePreflightResult(
            issues=(),
            warnings=("Candidate split may use most available memory.",),
            diagnostics={
                "risk_level": "warning",
                "dataset_ids": [id(dataset) for dataset in datasets],
            },
        ),
    )

    active_summary_before = service.get_state().dataset.active_split_summary
    history_before = old_trainer.training_plan_holders
    warning = service.execute(TrainCommand(confirmed=True))
    token = warning.diagnostics["resource_preflight"]["confirmation_token"]
    state_after_warning = service.get_state()
    cancelled = service.execute(
        DiscardTrainingPreparationCommand(resource_preflight_token=token)
    )
    candidate_remained_after_cancel = (
        service.dataset_generation.discard_prepared_split()
    )
    replay = service.execute(
        TrainCommand(
            confirmed=True,
            resource_preflight_confirmed=True,
            resource_preflight_token=token,
        )
    )
    state_after_cancel = service.get_state()

    assert warning.failed is True
    assert warning.error_type.value == "confirmation_required"
    assert cancelled.ok is True
    assert cancelled.diagnostics["candidate_discarded"] is True
    assert candidate_remained_after_cancel is False
    assert replay.failed is True
    assert replay.error_type.value == "confirmation_required"
    assert replay.diagnostics["resource_preflight"]["confirmation_token"] != token
    assert warning.diagnostics["resource_preflight"]["dataset_ids"] == [id(candidate)]
    assert service.study.datasets[0] is old_dataset
    assert service.study.training_manager.trainer is old_trainer
    assert old_trainer.training_plan_holders is history_before
    assert old_trainer.training_plan_holders == [history]
    assert state_after_warning.dataset.active_split_summary == active_summary_before
    assert state_after_warning.dataset.split_materialized is False
    assert state_after_cancel.dataset.active_split_summary == active_summary_before
    assert state_after_cancel.dataset.split_materialized is False
    assert generator.prepare_result.call_count == 2
    service.training.start_training.assert_not_called()


def test_confirmed_resource_retry_reuses_candidate_and_commits_once(
    monkeypatch,
) -> None:
    service, epoch = _service_with_epoch()
    _save_split_and_configure_training(service, epoch)
    _old_dataset, old_trainer, _history = _install_existing_training_state(
        service, epoch
    )
    candidate = _materialized_dataset(epoch)
    generator = MagicMock()
    generator.prepare_result.return_value = [candidate]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    service.training.start_training = MagicMock(
        side_effect=lambda **_kwargs: _publish_training_identity(service)
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.training_service.check_training_resource_preflight",
        lambda datasets, *_args: ResourcePreflightResult(
            issues=(),
            warnings=("Candidate split may use most available memory.",),
            diagnostics={
                "risk_level": "warning",
                "dataset_ids": [id(dataset) for dataset in datasets],
            },
        ),
    )
    original_commit = service.pipeline_transaction.commit_dataset_replacement
    commit = MagicMock(wraps=original_commit)
    service.pipeline_transaction.commit_dataset_replacement = commit

    warning = service.execute(TrainCommand(confirmed=True))
    token = warning.diagnostics["resource_preflight"]["confirmation_token"]
    confirmed = service.execute(
        TrainCommand(
            confirmed=True,
            resource_preflight_confirmed=True,
            resource_preflight_token=token,
        )
    )

    assert warning.failed is True
    assert confirmed.ok is True
    assert generator.prepare_result.call_count == 1
    assert commit.call_count == 1
    assert service.study.datasets[0] is candidate
    assert service.study.training_manager.trainer is not old_trainer
    assert confirmed.diagnostics["split_preparation"]["materialized"] is True
    assert (
        confirmed.diagnostics["resource_preflight"]["confirmation_receipt_reused"]
        is True
    )
    assert confirmed.state.dataset.split_lifecycle.value == "verified"
    assert confirmed.state.dataset.active_split_summary["audit"]["ok"] is True
    assert confirmed.state.dataset.last_split_attempt == {}


def test_preview_receipt_serialization_has_fixed_row_and_truncation_bounds() -> None:
    specification = _specification()
    rows = tuple(
        DatasetSplitPreviewRow(
            name=f"subject-{index}",
            train_count=8,
            validation_count=2,
            test_count=2,
        )
        for index in range(DATASET_SPLIT_PREVIEW_ROW_LIMIT)
    )
    publication = DatasetSplitPreviewPublication(
        request=DatasetSplitPreviewRequest(
            request_id="bounded-preview",
            publication_generation=1,
            specification=specification,
        ),
        generation=1,
        epoch_token=1,
        rows=rows,
        total_count=1_000,
        truncated_count=1_000 - DATASET_SPLIT_PREVIEW_ROW_LIMIT,
        train_count=8_000,
        validation_count=2_000,
        test_count=2_000,
    )

    payload = publication.receipt.summary_payload()
    serialized = json.loads(json.dumps(payload))

    assert len(serialized["rows"]) == DATASET_SPLIT_PREVIEW_ROW_LIMIT
    assert serialized["dataset_count"] == 1_000
    assert serialized["total_count"] == 1_000
    assert serialized["truncated_count"] == 950
    assert serialized["train_count"] == 8_000

    with pytest.raises(ValueError, match="row limit"):
        DatasetSplitPreviewPublication(
            request=publication.request,
            generation=1,
            epoch_token=1,
            rows=(
                *rows,
                DatasetSplitPreviewRow(
                    name="overflow",
                    train_count=1,
                    validation_count=0,
                    test_count=0,
                ),
            ),
            total_count=1_001,
            truncated_count=950,
            train_count=8_001,
            validation_count=2_000,
            test_count=2_000,
        )
