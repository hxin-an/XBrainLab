"""Cross-source one-epoch training smoke for event-rich public local-only fixtures."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import torch

from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.model_base import EEGNet
from XBrainLab.backend.training import (
    ModelHolder,
    TrainingEvaluation,
    TrainingOption,
)
from XBrainLab.backend.training.record import RecordKey

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DATA_DIR = ROOT / "fixtures" / "data" / "public"
PUBLIC_TRAINING_FIXTURES = (
    {
        "name": "physionet-edf",
        "filename": "physionet-eegmmidb-S008R04.edf",
        "event_ids": ["T1", "T2"],
        "tmin": 0,
        "tmax": 2,
    },
    {
        "name": "bbci-gdf",
        "filename": "bbci-competition-iii-O3VR.gdf",
        "event_ids": ["769", "770"],
        "tmin": 0,
        "tmax": 2,
    },
    {
        "name": "sccn-eeglab",
        "filename": "sccn-eeglab_data.set",
        "event_ids": ["rt", "square"],
        "tmin": 0,
        "tmax": 2,
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


def _build_public_training_facade(fixture: dict[str, object]) -> BackendFacade:
    filepath = PUBLIC_DATA_DIR / str(fixture["filename"])
    if not filepath.exists():
        pytest.skip(f"Public fixture not downloaded at {filepath}")

    facade = BackendFacade()
    success_count, errors = facade.load_data([str(filepath)])
    assert success_count == 1
    assert errors == []
    return facade


@pytest.mark.parametrize("fixture", PUBLIC_TRAINING_FIXTURES, ids=lambda f: f["name"])
def test_public_cross_source_training_smoke(fixture: dict[str, object]) -> None:
    """Event-rich public fixtures should support a one-epoch training smoke."""
    facade = _build_public_training_facade(fixture)

    facade.apply_filter(4, 38)
    facade.normalize_data("z score")
    facade.epoch_data(
        fixture["tmin"],
        fixture["tmax"],
        event_ids=list(fixture["event_ids"]),
    )
    split_ratio = float(fixture.get("split_ratio", 0.2))
    facade.generate_dataset(
        test_ratio=split_ratio,
        val_ratio=split_ratio,
        split_strategy="trial",
        training_mode="individual",
    )

    datasets = facade.study.datasets
    assert datasets is not None
    assert len(datasets) > 0
    assert all(dataset.get_epoch_data().get_data().shape[0] > 0 for dataset in datasets)

    facade.study.set_model_holder(ModelHolder(EEGNet, {}, None))
    facade.study.set_training_option(
        TrainingOption(
            output_dir="test_public_output",
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch=1,
            bs=8,
            lr=0.001,
            checkpoint_epoch=1,
            evaluation_option=TrainingEvaluation.TEST_ACC,
            repeat_num=1,
        ),
    )
    facade.study.set_saliency_params(
        {
            "SmoothGrad": {"nt_samples": 1, "stdevs": 0.1},
            "SmoothGrad_Squared": {"nt_samples": 1, "stdevs": 0.1},
            "VarGrad": {"nt_samples": 1, "stdevs": 0.1},
        },
    )

    with (
        patch("matplotlib.pyplot.savefig"),
        patch("torch.save"),
        patch("numpy.savetxt"),
        patch("os.makedirs"),
    ):
        facade.study.generate_plan()
        facade.study.train(interact=False)

    assert facade.study.trainer is not None
    plan_holders = facade.study.trainer.get_training_plan_holders()
    assert len(plan_holders) > 0
    record = plan_holders[0].train_record_list[0]
    assert RecordKey.LOSS in record.train
    assert RecordKey.ACC in record.train
