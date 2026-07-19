"""Regression coverage for normalization statistics crossing split boundaries."""

from __future__ import annotations

import mne
import numpy as np
import pytest

from XBrainLab.backend.dataset import (
    Dataset,
    DataSplittingConfig,
    Epochs,
    TrainingType,
)
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.preprocessor import Normalize, TimeEpoch


def _supervised_dataset_with_test_only_offset(
    *,
    test_offset: float,
    normalization: str,
) -> Dataset:
    sfreq = 100.0
    samples = np.arange(900, dtype=np.float64) / sfreq
    signal = np.vstack(
        (
            np.sin(2 * np.pi * 8 * samples) + 0.05 * samples,
            np.cos(2 * np.pi * 12 * samples) - 0.03 * samples,
        )
    )
    signal[:, 500:] += test_offset
    mne_raw = mne.io.RawArray(
        signal,
        mne.create_info(["C3", "C4"], sfreq=sfreq, ch_types="eeg"),
        verbose=False,
    )
    raw = Raw(f"recordings/test-offset-{test_offset:g}.fif", mne_raw)
    raw.set_event(
        np.asarray(
            [
                [100, 0, 1],
                [300, 0, 2],
                [500, 0, 1],
                [700, 0, 2],
            ],
            dtype=int,
        ),
        {"left": 1, "right": 2},
    )

    normalized = Normalize([raw]).data_preprocess(normalization)
    epoched = TimeEpoch(normalized).data_preprocess(
        baseline=None,
        selected_event_names=["left", "right"],
        tmin=0.0,
        tmax=0.99,
    )
    dataset = Dataset(
        Epochs(epoched),
        DataSplittingConfig(TrainingType.FULL, False, [], []),
    )
    dataset.train_mask[:2] = True
    dataset.test_mask[2:] = True
    dataset.remaining_mask[:] = False
    return dataset


@pytest.mark.parametrize("normalization", ["z score", "minmax"])
def test_raw_normalization_cannot_leak_test_only_offset_into_training_input(
    normalization: str,
) -> None:
    baseline = _supervised_dataset_with_test_only_offset(
        test_offset=0.0,
        normalization=normalization,
    )
    shifted_test = _supervised_dataset_with_test_only_offset(
        test_offset=50.0,
        normalization=normalization,
    )

    baseline_training, baseline_labels = baseline.get_training_data()
    shifted_training, shifted_labels = shifted_test.get_training_data()

    np.testing.assert_array_equal(shifted_labels, baseline_labels)
    np.testing.assert_allclose(
        shifted_training,
        baseline_training,
        rtol=1e-12,
        atol=1e-12,
    )
