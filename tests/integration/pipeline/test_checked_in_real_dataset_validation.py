"""Validation slices for checked-in real GDF fixtures plus attached labels."""

from __future__ import annotations

import os
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

TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "data"
CHECKED_IN_GDF_STEMS = ("A01T", "A02T", "A03T")


def _checked_in_fixture_pair(stem: str) -> tuple[str, str]:
    return (
        str(TEST_DATA_DIR / f"{stem}.gdf"),
        str(TEST_DATA_DIR / "label" / f"{stem}.mat"),
    )


def _build_label_attached_facade(stem: str) -> BackendFacade:
    gdf_path, label_path = _checked_in_fixture_pair(stem)
    if not os.path.exists(gdf_path):
        pytest.skip(f"Test data not found at {gdf_path}")
    if not os.path.exists(label_path):
        pytest.skip(f"Label data not found at {label_path}")

    facade = BackendFacade()
    success_count, errors = facade.load_data([gdf_path])
    assert success_count == 1
    assert errors == []
    assert facade.attach_labels({f"{stem}.gdf": label_path}) == 1
    return facade


@pytest.mark.parametrize("stem", CHECKED_IN_GDF_STEMS)
def test_checked_in_label_attached_dataset_generation(stem):
    """Each checked-in GDF+MAT pair should support dataset generation."""
    facade = _build_label_attached_facade(stem)

    preprocessed = facade.preprocess.get_first_data()
    assert preprocessed is not None
    _, event_id = preprocessed.get_event_list()
    assert set(event_id) == {"1", "2", "3", "4"}
    assert preprocessed.is_labels_imported() is True

    facade.apply_filter(4, 38)
    facade.normalize_data("z score")
    facade.epoch_data(0, 4, event_ids=["1", "2", "3", "4"])
    facade.generate_dataset(
        test_ratio=0.2,
        val_ratio=0.2,
        split_strategy="trial",
        training_mode="individual",
    )

    datasets = facade.study.datasets
    assert datasets is not None
    assert len(datasets) > 0
    assert all(dataset.get_epoch_data().get_data().shape[0] > 0 for dataset in datasets)


@pytest.mark.parametrize("stem", CHECKED_IN_GDF_STEMS)
def test_checked_in_label_attached_training_smoke(stem):
    """Each checked-in GDF+MAT pair should support a one-epoch training smoke."""
    facade = _build_label_attached_facade(stem)

    facade.apply_filter(4, 38)
    facade.normalize_data("z score")
    facade.epoch_data(0, 4, event_ids=["1", "2", "3", "4"])
    facade.generate_dataset(
        test_ratio=0.2,
        val_ratio=0.2,
        split_strategy="trial",
        training_mode="individual",
    )

    facade.study.set_model_holder(ModelHolder(EEGNet, {}, None))
    facade.study.set_training_option(
        TrainingOption(
            output_dir="test_real_output",
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch=1,
            bs=16,
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
