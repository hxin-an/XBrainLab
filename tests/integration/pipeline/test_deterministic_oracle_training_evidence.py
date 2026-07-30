"""Deterministic semantic oracle for the tiny train/evaluate pipeline.

This test proves event-to-class preservation, split integrity, held-out output
alignment, finite numerics, and real artifact persistence. Synthetic outcomes
are deliberately not evidence of scientific model accuracy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations
from pathlib import Path

import mne
import numpy as np
import torch

from XBrainLab.backend.dataset import (
    DatasetGenerator,
    DataSplitter,
    DataSplittingConfig,
    Epochs,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.model_base import EEGNet
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
    TrainingPlanHolder,
)
from XBrainLab.backend.training.record import RecordKey, TrainRecordKey

SOURCE_EVENT_CODES = {
    "left-hand imagery": 11,
    "right-hand imagery": 42,
}
EVENT_TO_CLASS = {
    "left-hand imagery": 0,
    "right-hand imagery": 1,
}
EXPECTED_CLASSES = np.asarray([0, 1] * 6, dtype=int)


def _build_oracle_epochs(tmp_path: Path) -> Epochs:
    """Build deterministic EEG where each source event has explicit semantics."""
    sfreq = 64.0
    sample_count = 96
    times = np.arange(sample_count, dtype=np.float32) / sfreq
    data = np.empty((len(EXPECTED_CLASSES), 4, sample_count), dtype=np.float32)

    for trial_index, class_index in enumerate(EXPECTED_CLASSES):
        frequency = 8.0 if class_index == 0 else 14.0
        semantic_wave = np.sin(2 * np.pi * frequency * times)
        opposite_wave = np.cos(2 * np.pi * frequency * times)
        dominant_channel = int(class_index)
        data[trial_index] = 1e-6 * np.stack(
            (
                semantic_wave if dominant_channel == 0 else 0.2 * opposite_wave,
                semantic_wave if dominant_channel == 1 else 0.2 * opposite_wave,
                0.1 * semantic_wave,
                0.1 * opposite_wave,
            ),
        )

    source_codes = np.asarray(
        [
            SOURCE_EVENT_CODES["left-hand imagery"]
            if class_index == 0
            else SOURCE_EVENT_CODES["right-hand imagery"]
            for class_index in EXPECTED_CLASSES
        ],
        dtype=int,
    )
    events = np.column_stack(
        (
            np.arange(len(EXPECTED_CLASSES)) * (sample_count + 16),
            np.zeros(len(EXPECTED_CLASSES), dtype=int),
            source_codes,
        ),
    )
    info = mne.create_info(
        ["C3", "C4", "Cz", "Pz"],
        sfreq=sfreq,
        ch_types="eeg",
    )
    mne_epochs = mne.EpochsArray(
        data,
        info,
        events=events,
        event_id=SOURCE_EVENT_CODES,
        tmin=0.0,
        verbose=False,
    )

    assert mne_epochs.event_id == SOURCE_EVENT_CODES
    np.testing.assert_array_equal(mne_epochs.events[:, 2], source_codes)

    wrapped = Raw(str(tmp_path / "deterministic-oracle-epo.fif"), mne_epochs)
    epochs = Epochs([wrapped])

    assert epochs.event_id == EVENT_TO_CLASS
    assert epochs.label_map == {0: "left-hand imagery", 1: "right-hand imagery"}
    np.testing.assert_array_equal(epochs.get_label_list(), EXPECTED_CLASSES)
    normalized_events, normalized_event_id = wrapped.get_event_list()
    assert normalized_event_id == EVENT_TO_CLASS
    np.testing.assert_array_equal(normalized_events[:, 2], EXPECTED_CLASSES)
    return epochs


def _generate_exact_split(epochs: Epochs):
    """Use the real generator to reserve two trials per held-out partition."""
    config = DataSplittingConfig(
        TrainingType.FULL,
        False,
        [
            DataSplitter(
                ValSplitByType.TRIAL,
                "8 9",
                SplitUnit.MANUAL,
            ),
        ],
        [
            DataSplitter(
                SplitByType.TRIAL,
                "10 11",
                SplitUnit.MANUAL,
            ),
        ],
    )
    datasets = DatasetGenerator(epochs, config).prepare_result()
    assert len(datasets) == 1
    return datasets[0]


def _assert_finite_history(
    history: Mapping[str, Sequence[float | None]],
    keys: Sequence[str],
) -> None:
    for key in keys:
        values = history[key]
        assert len(values) == 1
        assert all(value is not None for value in values)
        assert np.isfinite(np.asarray(values, dtype=float)).all()


def test_deterministic_oracle_preserves_semantics_and_held_out_outputs(
    tmp_path: Path,
) -> None:
    """A real tiny CPU run preserves semantic truth and finite held-out outputs."""
    epochs = _build_oracle_epochs(tmp_path)
    dataset = _generate_exact_split(epochs)

    split_indices = {
        "train": set(dataset.get_training_indices().tolist()),
        "validation": set(dataset.get_val_indices().tolist()),
        "test": set(dataset.get_test_indices().tolist()),
    }
    assert split_indices == {
        "train": set(range(8)),
        "validation": {8, 9},
        "test": {10, 11},
    }
    for left, right in combinations(split_indices.values(), 2):
        assert left.isdisjoint(right)
    assert set().union(*split_indices.values()) == set(range(len(EXPECTED_CLASSES)))
    assert not dataset.get_remaining_mask().any()

    output_root = tmp_path / "training-output"
    option = TrainingOption(
        output_dir=str(output_root),
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
    plan = TrainingPlanHolder(
        ModelHolder(EEGNet, {"f1": 2, "f2": 4, "d": 1}),
        dataset,
        option,
        {},
    )
    Trainer([plan]).job()

    assert plan.error is None
    assert len(plan.train_record_list) == 1
    record = plan.train_record_list[0]
    assert record.is_finished()
    _assert_finite_history(
        record.train,
        (
            RecordKey.LOSS,
            RecordKey.ACC,
            RecordKey.AUC,
            TrainRecordKey.LR,
            TrainRecordKey.TIME,
        ),
    )
    _assert_finite_history(
        record.val,
        (RecordKey.LOSS, RecordKey.ACC, RecordKey.AUC),
    )

    evaluation = record.eval_record
    assert evaluation is not None
    assert evaluation.evaluation_split == "test"
    targets = np.asarray(evaluation.label)
    logits = np.asarray(evaluation.output)
    predictions = logits.argmax(axis=1)
    test_indices = dataset.get_test_indices()

    assert targets.shape == predictions.shape == (len(test_indices),)
    assert logits.shape == (len(test_indices), len(EVENT_TO_CLASS))
    np.testing.assert_array_equal(targets, EXPECTED_CLASSES[test_indices])
    assert np.isfinite(logits).all()

    probabilities = torch.softmax(torch.from_numpy(logits), dim=1).numpy()
    assert probabilities.shape == logits.shape
    assert np.isfinite(probabilities).all()
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, rtol=1e-6, atol=1e-6)

    accuracy = float(evaluation.get_acc())
    auc = evaluation.get_auc()
    kappa = float(evaluation.get_kappa())
    assert auc is not None
    assert np.isfinite(np.asarray([accuracy, auc, kappa], dtype=float)).all()
    per_class_metrics = evaluation.get_per_class_metrics()
    assert all(
        np.isfinite(float(value))
        for metrics in per_class_metrics.values()
        for value in metrics.values()
    )

    # Valid ranges are sanity checks only; no minimum score is a scientific claim.
    assert 0.0 <= accuracy <= 1.0
    assert 0.0 <= auc <= 1.0
    assert -1.0 <= kappa <= 1.0

    assert record.target_path is not None
    artifact_dir = Path(record.target_path).resolve()
    assert artifact_dir.is_relative_to(output_root.resolve())
    persisted_names = {path.name for path in artifact_dir.iterdir() if path.is_file()}
    assert {"eval", "eval.npz", "record", "record.npz"} <= persisted_names
    assert any(name.startswith("Epoch-1-model") for name in persisted_names)
