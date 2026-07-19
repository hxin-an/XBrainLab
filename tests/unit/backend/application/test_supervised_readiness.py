"""Shared supervised-readiness policy regressions."""

from __future__ import annotations

from dataclasses import replace

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    DatasetStateSnapshot,
    EpochStateSnapshot,
    TrainingStateSnapshot,
)


def _training_ready_state(*, event_ids: dict[str, int]) -> ApplicationStateSnapshot:
    state = ApplicationStateSnapshot.empty()
    return replace(
        state,
        epoch=EpochStateSnapshot(
            available=True,
            exists=True,
            epoch_count=12,
            event_names=list(event_ids),
            event_ids=event_ids,
        ),
        dataset=DatasetStateSnapshot(
            available=True,
            count=1,
            names=["split-0"],
            generator_exists=True,
            split_summary={"audit": {"ok": True, "dataset_count": 1, "issues": []}},
        ),
        training=TrainingStateSnapshot(
            has_model=True,
            model_name="EEGNet",
            has_training_option=True,
        ),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
            has_epoch_data=True,
            has_datasets=True,
        ),
        active_training=ActiveTrainingSnapshot(
            has_model=True,
            has_training_option=True,
        ),
    )


def test_one_class_epoch_disables_dataset_and_training_capabilities() -> None:
    policy = build_capability_policy(_training_ready_state(event_ids={"Left hand": 0}))

    for command_name in (
        CommandName.GENERATE_DATASET.value,
        CommandName.TRAIN.value,
    ):
        capability = policy.get(command_name)
        assert capability.enabled is False
        assert any(
            "at least 2" in reason and "usable trials" in reason
            for reason in capability.reasons
        )


def test_two_class_epoch_keeps_supervised_capabilities_available() -> None:
    policy = build_capability_policy(
        _training_ready_state(event_ids={"Left hand": 0, "Right hand": 1})
    )

    assert policy.get(CommandName.GENERATE_DATASET.value).enabled is True
    assert policy.get(CommandName.TRAIN.value).enabled is True
