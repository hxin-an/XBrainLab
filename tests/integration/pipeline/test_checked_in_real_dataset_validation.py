"""Validation slices for checked-in real GDF fixtures plus attached labels."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    AttachLabelsCommand,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
    TrainCommand,
)
from XBrainLab.backend.training.record import RecordKey

TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "data"
CHECKED_IN_GDF_STEMS = ("A01T", "A02T", "A03T")
EXPECTED_LABEL_EVENT_ID = {"1": 1, "2": 2, "3": 3, "4": 4}
EXPECTED_EPOCH_EVENT_IDS = {"1": 0, "2": 1, "3": 2, "4": 3}
EXPECTED_EPOCH_COUNTS = {
    "A01T": 276,
    "A02T": 280,
    "A03T": 277,
}
EXPECTED_SPLIT_SUMMARIES = {
    "A01T": {
        "count": 1,
        "train_count": 177,
        "val_count": 44,
        "test_count": 55,
        "audit": {"ok": True, "dataset_count": 1, "issues": []},
    },
    "A02T": {
        "count": 1,
        "train_count": 180,
        "val_count": 44,
        "test_count": 56,
        "audit": {"ok": True, "dataset_count": 1, "issues": []},
    },
    "A03T": {
        "count": 1,
        "train_count": 178,
        "val_count": 44,
        "test_count": 55,
        "audit": {"ok": True, "dataset_count": 1, "issues": []},
    },
}


def _checked_in_fixture_pair(stem: str) -> tuple[str, str]:
    return (
        str(TEST_DATA_DIR / f"{stem}.gdf"),
        str(TEST_DATA_DIR / "label" / f"{stem}.mat"),
    )


def _build_label_attached_service(stem: str) -> ApplicationService:
    gdf_path, label_path = _checked_in_fixture_pair(stem)
    if not os.path.exists(gdf_path):
        pytest.skip(f"Test data not found at {gdf_path}")
    if not os.path.exists(label_path):
        pytest.skip(f"Label data not found at {label_path}")

    service = ApplicationService()
    load_result = service.execute(LoadDataCommand(paths=[gdf_path]))
    assert load_result.ok is True
    assert load_result.diagnostics["success_count"] == 1
    attach_result = service.execute(
        AttachLabelsCommand(mapping={f"{stem}.gdf": label_path}),
    )
    assert attach_result.ok is True
    assert attach_result.diagnostics["success_count"] == 1
    return service


def _query_first_preprocessed(service: ApplicationService):
    result = service.execute(
        QueryStateCommand(query="data_lists", include_objects=True)
    )
    assert result.ok is True
    preprocessed = result.diagnostics["preprocessed_data_list"]
    assert preprocessed
    return preprocessed[0]


def _generate_trial_split(service: ApplicationService, stem: str):
    assert (
        service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.BANDPASS,
                low_freq=4,
                high_freq=38,
            ),
        ).ok
        is True
    )
    assert (
        service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE,
                method="z score",
            ),
        ).ok
        is True
    )
    epoch_result = service.execute(
        CreateEpochCommand(0, 4, event_ids=["1", "2", "3", "4"]),
    )
    assert epoch_result.ok is True
    assert epoch_result.state.epoch.epoch_count == EXPECTED_EPOCH_COUNTS[stem]
    assert epoch_result.state.epoch.n_channels == 25
    assert epoch_result.state.epoch.n_times == 1001
    assert epoch_result.state.epoch.event_ids == EXPECTED_EPOCH_EVENT_IDS
    dataset_result = service.execute(
        GenerateDatasetCommand(
            test_ratio=0.2,
            val_ratio=0.2,
            split_strategy="trial",
            training_mode="individual",
        ),
    )
    assert dataset_result.ok is True
    assert dataset_result.diagnostics["split_audit"]["ok"] is True
    assert dataset_result.state.dataset.count == EXPECTED_SPLIT_SUMMARIES[stem]["count"]
    assert dataset_result.state.dataset.split_summary == EXPECTED_SPLIT_SUMMARIES[stem]
    return dataset_result


def _configure_and_train(service: ApplicationService, output_dir: Path):
    assert service.execute(ConfigureTrainingCommand(model_name="EEGNet")).ok is True
    assert (
        service.execute(
            ConfigureTrainingCommand(
                output_dir=str(output_dir),
                device="cpu",
                epoch=1,
                batch_size=16,
                learning_rate=0.001,
                save_checkpoints_every=1,
                evaluation_option="test_acc",
            ),
        ).ok
        is True
    )
    assert service.get_capabilities().get(CommandName.TRAIN).available is True
    with (
        patch("matplotlib.pyplot.savefig"),
        patch("torch.save"),
        patch("numpy.savetxt"),
        patch("os.makedirs"),
    ):
        train_result = service.execute(
            TrainCommand(confirmed=True, interactive=False),
        )
    assert train_result.ok is True
    assert train_result.state.training.plan_count == 1
    assert train_result.state.training.run_count == 1
    assert train_result.state.training.finished_run_count == 1
    history = service.execute(
        QueryStateCommand(query="training_history", include_objects=True),
    )
    assert history.ok is True
    assert history.diagnostics["row_count"] == 1
    return history.diagnostics["rows"][0]["record"]


@pytest.mark.parametrize("stem", CHECKED_IN_GDF_STEMS)
def test_checked_in_label_attached_dataset_generation(stem):
    """Each checked-in GDF+MAT pair should support dataset generation."""
    service = _build_label_attached_service(stem)

    preprocessed = _query_first_preprocessed(service)
    events, event_id = preprocessed.get_event_list()
    assert event_id == EXPECTED_LABEL_EVENT_ID
    assert events.shape == (288, 3)
    assert preprocessed.is_labels_imported() is True

    dataset_result = _generate_trial_split(service, stem)

    assert dataset_result.state.dataset.available is True
    assert dataset_result.state.dataset.count == EXPECTED_SPLIT_SUMMARIES[stem]["count"]
    assert dataset_result.state.dataset.split_summary == EXPECTED_SPLIT_SUMMARIES[stem]


@pytest.mark.parametrize("stem", CHECKED_IN_GDF_STEMS)
def test_checked_in_label_attached_training_smoke(stem, tmp_path):
    """Each checked-in GDF+MAT pair should support a one-epoch training smoke."""
    service = _build_label_attached_service(stem)
    _generate_trial_split(service, stem)

    record = _configure_and_train(service, tmp_path / "test-real-output")

    assert RecordKey.LOSS in record.train
    assert RecordKey.ACC in record.train
