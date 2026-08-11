"""Backend-owned pipeline-stage read-model contract tests."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.pipeline_stage import (
    PipelineStage,
    compute_pipeline_stage,
    derive_pipeline_stage,
    pipeline_stage_contract,
    pipeline_stage_from_snapshot,
    pipeline_stage_readiness_message,
    pipeline_stage_readiness_summary,
    workflow_command_label,
)
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
    RawStateSnapshot,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication

STAGE_CASES = [
    (
        "empty",
        {},
        PipelineStage.EMPTY,
        "No data loaded",
        "scan_source",
    ),
    (
        "raw",
        {"has_raw_data": True},
        PipelineStage.DATA_LOADED,
        "Ready for preprocessing",
        "preprocess",
    ),
    (
        "preprocessed",
        {"has_raw_data": True, "has_preprocessed_data": True},
        PipelineStage.PREPROCESSED,
        "Ready for EEG epoching",
        "create_epoch",
    ),
    (
        "epoch",
        {
            "has_raw_data": True,
            "has_preprocessed_data": True,
            "has_epoch_data": True,
        },
        PipelineStage.EPOCH_READY,
        "Ready to configure split",
        "configure_dataset_split",
    ),
    (
        "dataset",
        {
            "has_raw_data": True,
            "has_preprocessed_data": True,
            "has_epoch_data": True,
            "has_datasets": True,
        },
        PipelineStage.DATASET_READY,
        "Dataset ready",
        "configure_training",
    ),
    (
        "training",
        {
            "has_raw_data": True,
            "has_preprocessed_data": True,
            "has_epoch_data": True,
            "has_datasets": True,
            "has_trainer": True,
            "is_training": True,
        },
        PipelineStage.TRAINING,
        "Training running",
        None,
    ),
    (
        "trained",
        {
            "has_raw_data": True,
            "has_preprocessed_data": True,
            "has_epoch_data": True,
            "has_datasets": True,
            "has_trainer": True,
            "finished_run_count": 1,
        },
        PipelineStage.TRAINED,
        "Results available",
        "evaluate",
    ),
]


@pytest.mark.parametrize(
    ("_case_name", "flags", "expected", "_status_label", "_next_command"),
    STAGE_CASES,
)
def test_snapshot_stage_mapper_preserves_public_stage_values(
    _case_name: str,
    flags: dict[str, bool],
    expected: PipelineStage,
    _status_label: str,
    _next_command: str | None,
) -> None:
    del flags
    snapshot = replace(ApplicationStateSnapshot.empty(), pipeline_stage=expected.value)

    assert pipeline_stage_from_snapshot(snapshot) is expected


@pytest.mark.parametrize(
    ("_case_name", "flags", "expected", "status_label", "next_command"),
    STAGE_CASES,
)
def test_stage_contract_derives_all_workflow_stages(
    _case_name: str,
    flags: dict[str, bool],
    expected: PipelineStage,
    status_label: str,
    next_command: str | None,
) -> None:
    stage = derive_pipeline_stage(**flags)
    contract = pipeline_stage_contract(stage)

    assert stage is expected
    assert contract.status_label == status_label
    assert contract.next_command == next_command


def test_trainer_without_finished_runs_is_not_a_trained_stage() -> None:
    assert (
        derive_pipeline_stage(
            has_raw_data=True,
            has_preprocessed_data=True,
            has_epoch_data=True,
            has_datasets=True,
            has_trainer=True,
            finished_run_count=0,
        )
        is PipelineStage.DATASET_READY
    )


def test_saved_split_without_generated_dataset_remains_epoch_ready() -> None:
    assert (
        derive_pipeline_stage(
            has_raw_data=True,
            has_preprocessed_data=True,
            has_epoch_data=True,
            has_datasets=False,
            has_saved_split=True,
        )
        is PipelineStage.EPOCH_READY
    )


def test_snapshot_stage_mapper_rejects_unknown_or_missing_stage() -> None:
    unknown = replace(ApplicationStateSnapshot.empty(), pipeline_stage="unknown")

    assert pipeline_stage_from_snapshot(unknown) is None


def test_pipeline_readiness_summary_is_user_facing_and_actionable() -> None:
    empty = ApplicationStateSnapshot.empty()
    loaded = replace(
        empty,
        pipeline_stage="data_loaded",
        raw=RawStateSnapshot(loaded=True, count=3),
    )

    assert pipeline_stage_readiness_summary(empty) == (
        "No data loaded. Next: Scan data source."
    )
    assert pipeline_stage_readiness_summary(loaded) == (
        "Ready for preprocessing: 3 EEG files loaded. Next: Preprocess data."
    )


def test_eeg_epoch_stage_and_command_labels_are_domain_explicit() -> None:
    contract = pipeline_stage_contract(PipelineStage.EPOCH_READY)

    assert contract.prompt_label == "EEG epochs ready"
    assert workflow_command_label("create_epoch") == "Create EEG epochs"
    assert pipeline_stage_readiness_message(PipelineStage.PREPROCESSED) == (
        "Ready for EEG epoching. Next: Create EEG epochs."
    )


def test_legacy_study_stage_priority_is_preserved() -> None:
    trainer = MagicMock()
    trainer.is_running.return_value = True
    study = SimpleNamespace(
        loaded_data_list=[object()],
        preprocessed_data_list=[object()],
        epoch_data=object(),
        datasets=[object()],
        trainer=trainer,
    )

    assert compute_pipeline_stage(study) is PipelineStage.TRAINING


@pytest.mark.parametrize("invalid_runs", [None, object(), "not-a-run-list"])
def test_legacy_stage_ignores_non_iterable_or_text_run_collections(
    invalid_runs: object,
) -> None:
    trainer = MagicMock()
    trainer.is_running.return_value = False
    trainer.get_training_plan_holders.return_value = invalid_runs
    study = SimpleNamespace(
        loaded_data_list=[object()],
        preprocessed_data_list=[object()],
        epoch_data=object(),
        datasets=[object()],
        trainer=trainer,
    )

    assert compute_pipeline_stage(study) is PipelineStage.DATASET_READY


def test_real_study_stage_requires_explicit_publication() -> None:
    from XBrainLab.backend.study import Study

    study = Study()
    study.loaded_data_list = [MagicMock()]

    assert study._application_service is None
    assert compute_pipeline_stage(study) is PipelineStage.EMPTY
    assert study._application_service is None


def test_explicit_publication_is_the_only_stage_read_for_real_study() -> None:
    from XBrainLab.backend.study import Study

    study = Study()
    study.datasets = [MagicMock()]
    snapshot = replace(ApplicationStateSnapshot.empty(), pipeline_stage="trained")
    publication = ApplicationViewPublication(
        generation=4,
        state=snapshot,
        capabilities=build_capability_policy(snapshot),
    )

    assert (
        compute_pipeline_stage(study, publication=publication) is PipelineStage.TRAINED
    )


def test_real_study_stage_rejects_non_publication_objects() -> None:
    from XBrainLab.backend.study import Study

    study = Study()

    assert (
        compute_pipeline_stage(
            study,
            publication=SimpleNamespace(
                state=SimpleNamespace(pipeline_stage="dataset_ready"),
            ),
        )
        is PipelineStage.EMPTY
    )


def test_study_does_not_expose_pipeline_stage_property() -> None:
    from XBrainLab.backend.study import Study

    assert "pipeline_stage" not in Study.__dict__
