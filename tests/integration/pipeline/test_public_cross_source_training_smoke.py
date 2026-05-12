"""Cross-source one-epoch training smoke for event-rich public local-only fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict
from unittest.mock import patch

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
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

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DATA_DIR = ROOT / "fixtures" / "data" / "public"


class PublicTrainingFixture(TypedDict):
    name: str
    filename: str
    event_ids: list[str]
    tmin: float
    tmax: float
    split_ratio: float


PUBLIC_TRAINING_FIXTURES: tuple[PublicTrainingFixture, ...] = (
    {
        "name": "physionet-edf",
        "filename": "physionet-eegmmidb-S008R04.edf",
        "event_ids": ["T1", "T2"],
        "tmin": 0,
        "tmax": 2,
        "split_ratio": 0.2,
    },
    {
        "name": "bbci-gdf",
        "filename": "bbci-competition-iii-O3VR.gdf",
        "event_ids": ["769", "770"],
        "tmin": 0,
        "tmax": 2,
        "split_ratio": 0.2,
    },
    {
        "name": "sccn-eeglab",
        "filename": "sccn-eeglab_data.set",
        "event_ids": ["rt", "square"],
        "tmin": 0,
        "tmax": 2,
        "split_ratio": 0.2,
    },
    {
        "name": "mne-cnt",
        "filename": "scan41_short.cnt",
        "event_ids": ["0", "109", "7"],
        "tmin": 0,
        "tmax": 2,
        "split_ratio": 0.5,
    },
)


def _build_public_training_service(
    fixture: PublicTrainingFixture,
) -> ApplicationService:
    filepath = PUBLIC_DATA_DIR / str(fixture["filename"])
    if not filepath.exists():
        pytest.skip(f"Public fixture not downloaded at {filepath}")

    service = ApplicationService()
    load_result = service.execute(LoadDataCommand(paths=[str(filepath)]))
    assert load_result.ok is True
    assert load_result.diagnostics["success_count"] == 1
    return service


@pytest.mark.parametrize("fixture", PUBLIC_TRAINING_FIXTURES, ids=lambda f: f["name"])
def test_public_cross_source_training_smoke(
    fixture: PublicTrainingFixture,
    tmp_path: Path,
) -> None:
    """Event-rich public fixtures should support a one-epoch training smoke."""
    service = _build_public_training_service(fixture)

    filter_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=4,
            high_freq=38,
        ),
    )
    normalize_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z score",
        ),
    )
    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=float(fixture["tmin"]),
            t_max=float(fixture["tmax"]),
            event_ids=list(fixture["event_ids"]),
        ),
    )
    split_ratio = float(fixture["split_ratio"])
    dataset_result = service.execute(
        GenerateDatasetCommand(
            test_ratio=split_ratio,
            val_ratio=split_ratio,
            split_strategy="trial",
            training_mode="individual",
        ),
    )

    assert filter_result.ok is True
    assert normalize_result.ok is True
    assert epoch_result.ok is True
    assert dataset_result.ok is True
    assert dataset_result.diagnostics["split_audit"]["ok"] is True
    assert dataset_result.state.dataset.available is True
    assert dataset_result.state.dataset.count > 0
    assert dataset_result.state.dataset.split_summary["train_count"] > 0
    assert dataset_result.state.dataset.split_summary["val_count"] > 0
    assert dataset_result.state.dataset.split_summary["test_count"] > 0

    assert service.execute(ConfigureTrainingCommand(model_name="EEGNet")).ok is True
    assert (
        service.execute(
            ConfigureTrainingCommand(
                output_dir=str(tmp_path / "test-public-output"),
                device="cpu",
                epoch=1,
                batch_size=8,
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
    history = service.execute(
        QueryStateCommand(query="training_history", include_objects=True),
    )
    assert history.ok is True
    assert history.diagnostics["row_count"] > 0
    record = history.diagnostics["rows"][0]["record"]
    assert RecordKey.LOSS in record.train
    assert RecordKey.ACC in record.train
