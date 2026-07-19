from __future__ import annotations

import mne
import numpy as np
import pytest

import XBrainLab.backend.dataset.epochs as epochs_module
from XBrainLab.backend.dataset import (
    Dataset,
    DatasetGenerator,
    DataSplitter,
    DataSplittingConfig,
    Epochs,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
    audit_dataset_splits,
    build_split_artifact,
)
from XBrainLab.backend.load_data import Raw


def _recording_epochs(
    filepath: str,
    event_samples: list[int],
    *,
    labels: list[int] | None = None,
) -> Raw:
    sfreq = 100.0
    labels = labels or [index % 2 + 1 for index in range(len(event_samples))]
    info = mne.create_info(["Cz"], sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(
        np.zeros((1, max(event_samples) + 300)),
        info,
        verbose=False,
    )
    events = np.column_stack(
        (
            np.asarray(event_samples),
            np.zeros(len(event_samples), dtype=int),
            np.asarray(labels),
        ),
    )
    event_id = {f"class-{label}": label for label in sorted(set(labels))}
    mne_epochs = mne.Epochs(
        raw,
        events,
        event_id=event_id,
        tmin=0.0,
        tmax=0.99,
        baseline=None,
        preload=True,
        verbose=False,
    )
    wrapped = Raw(filepath, mne_epochs)
    epochs_module.mark_xbrainlab_raw_event_source_epochs(wrapped)
    return wrapped


def _atomic_epochs() -> Epochs:
    return Epochs(
        [
            _recording_epochs(
                "recordings/source-a.fif",
                [100, 150, 220, 320, 500, 700, 900, 1100, 1300],
            ),
            _recording_epochs("recordings/source-b.fif", [100, 500]),
        ],
    )


def _assert_groups_are_atomic(
    epoch_data: Epochs, split_masks: list[np.ndarray]
) -> None:
    group_ids = epoch_data.get_trial_group_list()
    for group_id in np.unique(group_ids):
        group_mask = group_ids == group_id
        memberships = [bool(np.any(mask & group_mask)) for mask in split_masks]
        assert sum(memberships) == 1
        selected_mask = split_masks[memberships.index(True)]
        assert np.all(selected_mask[group_mask])


def test_atomic_groups_include_transitive_overlap_but_not_adjacency_or_other_source():
    epoch_data = _atomic_epochs()

    groups = epoch_data.get_trial_group_list()

    assert groups[0] == groups[1] == groups[2]
    assert groups[3] != groups[2]  # [320, 420) touches [220, 320)
    assert groups[9] != groups[0]  # same samples, different source recording


def test_trial_ratio_selection_never_splits_atomic_groups():
    epoch_data = _atomic_epochs()
    mask = np.ones(epoch_data.get_data_length(), dtype=bool)
    target = int(0.4 * mask.sum())

    selected, remaining = epoch_data.pick_trial(
        mask,
        None,
        0.4,
        SplitUnit.RATIO,
        0,
    )

    _assert_groups_are_atomic(epoch_data, [selected, remaining])
    largest_group = max(
        int(np.sum(epoch_data.get_trial_group_list() == group_id))
        for group_id in np.unique(epoch_data.get_trial_group_list())
    )
    assert target <= int(selected.sum()) < target + largest_group


def test_trial_number_selection_never_splits_atomic_groups():
    epoch_data = _atomic_epochs()
    mask = np.ones(epoch_data.get_data_length(), dtype=bool)

    selected, remaining = epoch_data.pick_trial(
        mask,
        None,
        2,
        SplitUnit.NUMBER,
        0,
    )

    _assert_groups_are_atomic(epoch_data, [selected, remaining])
    assert 2 <= int(selected.sum()) < 5


def test_trial_kfold_assigns_each_atomic_group_to_exactly_one_fold():
    epoch_data = _atomic_epochs()
    clean_mask = np.ones(epoch_data.get_data_length(), dtype=bool)
    remaining = clean_mask.copy()
    folds: list[np.ndarray] = []

    for fold_index in range(3):
        selected, remaining = epoch_data.pick_trial(
            remaining,
            clean_mask,
            3,
            SplitUnit.KFOLD,
            fold_index,
        )
        folds.append(selected)

    assert not remaining.any()
    assert all(fold.any() for fold in folds)
    _assert_groups_are_atomic(epoch_data, folds)


def test_trial_kfold_blocks_when_there_are_fewer_atomic_groups_than_folds():
    epoch_data = Epochs(
        [_recording_epochs("recordings/one-component.fif", [100, 150, 220])],
    )
    mask = np.ones(epoch_data.get_data_length(), dtype=bool)

    with pytest.raises(ValueError, match="requires at least 2 atomic groups"):
        epoch_data.pick_trial(mask, mask.copy(), 2, SplitUnit.KFOLD, 0)


def test_manual_trial_selection_expands_to_the_whole_atomic_group_with_evidence():
    epoch_data = _atomic_epochs()
    mask = np.ones(epoch_data.get_data_length(), dtype=bool)

    selected, remaining = epoch_data.pick_trial(
        mask,
        None,
        [1],
        SplitUnit.MANUAL,
        0,
    )

    assert np.flatnonzero(selected).tolist() == [0, 1, 2]
    assert not remaining[:3].any()
    evidence = epoch_data.get_trial_selection_evidence()[-1]
    assert evidence["selection_unit"] == "manual"
    assert evidence["requested_indices"] == [1]
    assert evidence["expanded_indices"] == [0, 2]
    assert evidence["selected_epoch_count"] == 3
    dataset = Dataset(
        epoch_data,
        DataSplittingConfig(TrainingType.FULL, False, [], []),
    )
    dataset.set_name("manual-expansion")
    dataset.test_mask = selected
    dataset.train_mask = remaining
    dataset.remaining_mask[:] = False
    artifact_evidence = build_split_artifact([dataset])["datasets"][0][
        "trial_selection_evidence"
    ]
    assert artifact_evidence["records"][-1]["expanded_indices"] == [0, 2]


def test_manual_trial_selection_blocks_when_whole_group_is_not_available():
    epoch_data = _atomic_epochs()
    mask = np.ones(epoch_data.get_data_length(), dtype=bool)
    mask[0] = False

    with pytest.raises(ValueError, match="would split atomic overlap group"):
        epoch_data.pick_trial(mask, None, [1], SplitUnit.MANUAL, 0)


def test_dataset_generator_keeps_atomic_groups_across_kfold_test_val_and_train():
    epoch_data = _atomic_epochs()
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [DataSplitter(ValSplitByType.TRIAL, "0.2", SplitUnit.RATIO)],
        [DataSplitter(SplitByType.TRIAL, "3", SplitUnit.KFOLD)],
    )

    datasets = DatasetGenerator(epoch_data, config).generate()

    assert len(datasets) == 3
    assert audit_dataset_splits(datasets, protocol="trial-wise").ok is True
    for dataset in datasets:
        _assert_groups_are_atomic(
            epoch_data,
            [dataset.train_mask, dataset.val_mask, dataset.test_mask],
        )


def test_class_coverage_audit_does_not_break_atomic_group_to_repair_train_split():
    epoch_data = Epochs(
        [
            _recording_epochs(
                "recordings/class-boundary.fif",
                [100, 150, 400, 600],
                labels=[2, 2, 1, 1],
            ),
        ],
    )
    available = np.ones(epoch_data.get_data_length(), dtype=bool)
    test_mask, available = epoch_data.pick_trial(
        available,
        None,
        [0],
        SplitUnit.MANUAL,
        0,
    )
    val_mask, available = epoch_data.pick_trial(
        available,
        None,
        [2],
        SplitUnit.MANUAL,
        0,
    )
    dataset = Dataset(
        epoch_data,
        DataSplittingConfig(TrainingType.FULL, False, [], []),
    )
    dataset.set_name("class-boundary")
    dataset.test_mask = test_mask
    dataset.val_mask = val_mask
    dataset.train_mask = available
    dataset.remaining_mask[:] = False

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    assert np.flatnonzero(test_mask).tolist() == [0, 1]
    assert result.ok is False
    assert any(
        issue.severity == "error" and "train split is missing class" in issue.message
        for issue in result.issues
    )
