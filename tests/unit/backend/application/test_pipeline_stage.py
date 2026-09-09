"""Backend-owned pipeline-stage read-model contract tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.pipeline_stage import (
    PipelineStage,
    compute_pipeline_stage,
    derive_pipeline_stage,
    pipeline_stage_contract,
    pipeline_stage_from_snapshot,
    pipeline_stage_from_snapshots,
    pipeline_stage_readiness_message,
    pipeline_stage_readiness_summary,
    workflow_command_label,
)
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
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
        "EEG data loaded · Ready for preprocessing or epoching",
        None,
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
            "has_saved_split": True,
            "has_model": True,
            "has_training_option": True,
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
    ("_case_name", "flags", "expected", "_status_label", "_next_command"),
    STAGE_CASES,
)
def test_compute_pipeline_stage_reads_all_typed_published_stage_values(
    _case_name: str,
    flags: dict[str, bool],
    expected: PipelineStage,
    _status_label: str,
    _next_command: str | None,
) -> None:
    del flags
    snapshot = replace(ApplicationStateSnapshot.empty(), pipeline_stage=expected.value)
    publication = ApplicationViewPublication(
        generation=4,
        state=snapshot,
        capabilities=build_capability_policy(snapshot),
    )

    assert compute_pipeline_stage(publication) is expected


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
            has_saved_split=True,
            has_model=True,
            has_training_option=True,
            has_trainer=True,
            finished_run_count=0,
        )
        is PipelineStage.DATASET_READY
    )


def test_complete_setup_is_dataset_ready_before_dataset_materialization() -> None:
    assert (
        derive_pipeline_stage(
            has_raw_data=True,
            has_preprocessed_data=True,
            has_epoch_data=True,
            has_datasets=False,
            has_saved_split=True,
            has_model=True,
            has_training_option=True,
        )
        is PipelineStage.DATASET_READY
    )


@pytest.mark.parametrize(
    ("has_saved_split", "has_model", "has_training_option"),
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
    ],
)
def test_dataset_ready_requires_split_model_and_training_settings(
    has_saved_split: bool,
    has_model: bool,
    has_training_option: bool,
) -> None:
    assert (
        derive_pipeline_stage(
            has_raw_data=True,
            has_preprocessed_data=True,
            has_epoch_data=True,
            has_datasets=True,
            has_saved_split=has_saved_split,
            has_model=has_model,
            has_training_option=has_training_option,
        )
        is PipelineStage.EPOCH_READY
    )


def test_published_snapshots_use_complete_setup_as_dataset_ready_truth() -> None:
    assert (
        pipeline_stage_from_snapshots(
            ActiveDatasetSnapshot(
                has_raw_data=True,
                has_preprocessed_data=True,
                has_epoch_data=True,
                has_saved_split=True,
            ),
            ActiveTrainingSnapshot(
                has_model=True,
                has_training_option=True,
            ),
        )
        is PipelineStage.DATASET_READY
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
        "EEG data loaded · Ready for preprocessing or epoching: 3 EEG files loaded."
    )


def test_eeg_epoch_stage_and_command_labels_are_domain_explicit() -> None:
    contract = pipeline_stage_contract(PipelineStage.EPOCH_READY)

    assert contract.prompt_label == "EEG epochs ready"
    assert workflow_command_label("create_epoch") == "Create EEG epochs"
    assert pipeline_stage_readiness_message(PipelineStage.PREPROCESSED) == (
        "Ready for EEG epoching. Next: Create EEG epochs."
    )


def test_compute_pipeline_stage_fails_closed_for_missing_invalid_or_unknown_publication() -> (
    None
):
    unknown_snapshot = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="unknown",
    )
    unknown_publication = ApplicationViewPublication(
        generation=5,
        state=unknown_snapshot,
        capabilities=build_capability_policy(unknown_snapshot),
    )

    assert compute_pipeline_stage(None) is PipelineStage.EMPTY
    assert compute_pipeline_stage(object()) is PipelineStage.EMPTY
    assert compute_pipeline_stage(unknown_publication) is PipelineStage.EMPTY


def test_study_does_not_expose_pipeline_stage_property() -> None:
    from XBrainLab.backend.study import Study

    assert "pipeline_stage" not in Study.__dict__
