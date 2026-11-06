from __future__ import annotations

import time

import mne
import numpy as np
import pytest

import XBrainLab.backend.dataset.epochs as epochs_module
from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitSpecification,
)
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


def test_trial_kfold_rejects_one_fold_before_any_split_is_materialized():
    epoch_data = _atomic_epochs()
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [],
        [DataSplitter(SplitByType.TRIAL, "1", SplitUnit.KFOLD)],
    )

    with pytest.raises(ValueError, match="Preview failed"):
        DatasetGenerator(epoch_data, config).generate()


def _multi_subject_kfold_epochs(subject_count: int = 2) -> Epochs:
    """A real Epochs container with seven atomic groups per subject."""
    epoch_data = Epochs([])
    group_sizes = [2, 1, 1, 1, 1, 1, 1]
    subjects: list[int] = []
    groups: list[int] = []
    labels: list[int] = []
    group_id = 0
    for subject in range(subject_count):
        for size in group_sizes:
            subjects.extend([subject] * size)
            groups.extend([group_id] * size)
            labels.extend([group_id % 2] * size)
            group_id += 1
    count = len(subjects)
    epoch_data.data = np.zeros((count, 1, 8), dtype=np.float32)
    epoch_data.subject = np.asarray(subjects)
    epoch_data.session = np.zeros(count, dtype=int)
    epoch_data.label = np.asarray(labels)
    epoch_data.idx = np.arange(count)
    epoch_data.trial_group = np.asarray(groups)
    epoch_data.subject_map = {
        subject: f"S{subject + 1:02d}" for subject in range(subject_count)
    }
    epoch_data.session_map = {0: "ses-1"}
    epoch_data.label_map = {0: "class-a", 1: "class-b"}
    return epoch_data


@pytest.mark.parametrize("training_type", [TrainingType.FULL, TrainingType.IND])
@pytest.mark.parametrize("fold_count", [2, 3, 5, 7])
def test_trial_kfold_generates_exact_disjoint_union_for_every_scope(
    training_type: TrainingType,
    fold_count: int,
) -> None:
    epoch_data = _multi_subject_kfold_epochs()
    config = DataSplittingConfig(
        training_type,
        True,
        [],
        [DataSplitter(SplitByType.TRIAL, str(fold_count), SplitUnit.KFOLD)],
    )

    datasets = DatasetGenerator(epoch_data, config).generate()

    expected_scopes = 1 if training_type is TrainingType.FULL else 2
    assert len(datasets) == expected_scopes * fold_count
    for subject in range(expected_scopes):
        scope_datasets = (
            datasets
            if training_type is TrainingType.FULL
            else datasets[subject * fold_count : (subject + 1) * fold_count]
        )
        tests = [dataset.test_mask for dataset in scope_datasets]
        assert all(mask.any() for mask in tests)
        assert not np.any(np.sum(np.asarray(tests, dtype=int), axis=0) > 1)
        expected = np.ones(epoch_data.get_data_length(), dtype=bool)
        if training_type is TrainingType.IND:
            expected = epoch_data.subject == subject
        assert np.array_equal(np.any(tests, axis=0), expected)


def test_trial_kfold_blocks_when_one_individual_scope_has_too_few_groups():
    epoch_data = _multi_subject_kfold_epochs()
    epoch_data.trial_group[epoch_data.subject == 1] = 99
    config = DataSplittingConfig(
        TrainingType.IND,
        True,
        [],
        [DataSplitter(SplitByType.TRIAL, "2", SplitUnit.KFOLD)],
    )

    with pytest.raises(ValueError, match="requires at least 2 atomic groups"):
        DatasetGenerator(epoch_data, config).generate()


def test_generator_interrupts_between_individual_subject_scopes_and_restores_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real generator must cooperate with cancellation at a bounded scope edge."""
    epoch_data = _multi_subject_kfold_epochs()
    initial_sequence = Dataset.SEQ
    generator = DatasetGenerator(
        epoch_data,
        DataSplittingConfig(
            TrainingType.IND,
            False,
            [],
            [DataSplitter(SplitByType.TRIAL, "1", SplitUnit.NUMBER)],
        ),
    )
    original_handle = generator.handle
    completed_scopes = 0

    def interrupt_after_first_scope(*args, **kwargs) -> None:
        nonlocal completed_scopes
        original_handle(*args, **kwargs)
        completed_scopes += 1
        generator.set_interrupt()

    monkeypatch.setattr(generator, "handle", interrupt_after_first_scope)

    with pytest.raises(KeyboardInterrupt):
        generator.generate()

    assert completed_scopes == 1
    assert generator.datasets == []
    assert initial_sequence == Dataset.SEQ


@pytest.mark.parametrize("split_type", [SplitByType.TRIAL, SplitByType.SESSION])
def test_five_subject_individual_kfold_is_exact_and_scope_isolated(split_type):
    epoch_data = _multi_subject_kfold_epochs(subject_count=5)
    if split_type is SplitByType.SESSION:
        epoch_data.session = np.tile(np.repeat(np.arange(7), [2, 1, 1, 1, 1, 1, 1]), 5)
        epoch_data.session_map = {index: f"ses-{index}" for index in range(7)}
    config = DataSplittingConfig(
        TrainingType.IND,
        True,
        [],
        [DataSplitter(split_type, "3", SplitUnit.KFOLD)],
    )

    datasets = DatasetGenerator(epoch_data, config).generate()

    assert len(datasets) == 15
    target_values = (
        epoch_data.trial_group
        if split_type is SplitByType.TRIAL
        else epoch_data.session
    )
    for subject in range(5):
        subject_datasets = datasets[subject * 3 : (subject + 1) * 3]
        test_masks = np.asarray(
            [dataset.test_mask for dataset in subject_datasets], dtype=int
        )
        subject_scope = epoch_data.subject == subject
        assert all(
            np.all(epoch_data.subject[dataset.test_mask] == subject)
            for dataset in subject_datasets
        )
        assert not np.any(test_masks.sum(axis=0) > 1)
        assert np.array_equal(test_masks.any(axis=0), subject_scope)
        assert sorted(
            len(set(target_values[dataset.test_mask])) for dataset in subject_datasets
        ) == [2, 2, 3]
        assert all(
            set(epoch_data.label[dataset.train_mask].tolist()) == {0, 1}
            for dataset in subject_datasets
        )


@pytest.mark.parametrize("training_type", [TrainingType.FULL, TrainingType.IND])
@pytest.mark.parametrize("fold_count", [2, 3, 5, 7])
def test_session_kfold_generates_exact_folds_for_full_and_individual_scopes(
    training_type: TrainingType,
    fold_count: int,
) -> None:
    epoch_data = _multi_subject_kfold_epochs()
    session_values = np.tile(np.repeat(np.arange(7), [2, 1, 1, 1, 1, 1, 1]), 2)
    epoch_data.session = session_values
    epoch_data.session_map = {index: f"ses-{index}" for index in range(7)}
    config = DataSplittingConfig(
        training_type,
        True,
        [],
        [DataSplitter(SplitByType.SESSION, str(fold_count), SplitUnit.KFOLD)],
    )

    datasets = DatasetGenerator(epoch_data, config).generate()

    scope_count = 1 if training_type is TrainingType.FULL else 2
    assert len(datasets) == scope_count * fold_count
    for subject in range(2):
        subject_datasets = (
            datasets
            if training_type is TrainingType.FULL
            else datasets[subject * fold_count : (subject + 1) * fold_count]
        )
        selected_sessions = [
            set(epoch_data.session[dataset.test_mask & (epoch_data.subject == subject)])
            for dataset in subject_datasets
        ]
        assert all(selected_sessions)
        assert not any(
            left & right
            for index, left in enumerate(selected_sessions)
            for right in selected_sessions[index + 1 :]
        )
        assert set().union(*selected_sessions) == set(range(7))


def test_individual_subject_kfold_is_rejected_by_the_public_config_contract() -> None:
    with pytest.raises(ValueError, match=r"Individual.*Subject"):
        DatasetSplitSpecification.from_payload(
            {
                "train_type": "Individual",
                "is_cross_validation": True,
                "val_splitters": [],
                "test_splitters": [
                    {
                        "split_type": "By Subject",
                        "split_unit": "K Fold",
                        "value": "2",
                        "is_option": True,
                    }
                ],
            }
        ).to_config()


@pytest.mark.parametrize("fold_count", [2, 3, 5, 7])
def test_subject_kfold_generates_exact_folds_for_full_scope(fold_count: int) -> None:
    epoch_data = Epochs([])
    epoch_data.data = np.zeros((7, 1, 8), dtype=np.float32)
    epoch_data.subject = np.arange(7, dtype=int)
    epoch_data.session = np.zeros(7, dtype=int)
    epoch_data.label = np.asarray([0, 1, 0, 1, 0, 1, 0])
    epoch_data.idx = np.arange(7)
    epoch_data.trial_group = np.arange(7)
    epoch_data.subject_map = {index: f"S{index:02d}" for index in range(7)}
    epoch_data.session_map = {0: "ses-0"}
    epoch_data.label_map = {0: "class-a", 1: "class-b"}
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [],
        [DataSplitter(SplitByType.SUBJECT, str(fold_count), SplitUnit.KFOLD)],
    )

    datasets = DatasetGenerator(epoch_data, config).generate()

    assert len(datasets) == fold_count
    tests = [dataset.test_mask for dataset in datasets]
    assert all(mask.any() for mask in tests)
    assert not np.any(np.sum(np.asarray(tests, dtype=int), axis=0) > 1)
    assert np.array_equal(np.any(tests, axis=0), np.ones(7, dtype=bool))


def test_generator_joint_high_trial_ratios_reject_oversized_targets():
    epoch_data = _multi_subject_kfold_epochs()
    config = DataSplittingConfig(
        TrainingType.FULL,
        False,
        [DataSplitter(ValSplitByType.TRIAL, "0.8", SplitUnit.RATIO)],
        [DataSplitter(SplitByType.TRIAL, "0.8", SplitUnit.RATIO)],
    )

    with pytest.raises(ValueError):
        DatasetGenerator(epoch_data, config).generate()


def test_joint_ratio_allocation_rejects_oversized_targets_even_with_multilabel_train():
    epoch_data = _four_atomic_group_epochs([0, 1, 0, 1, 0, 1])
    epoch_data.trial_group = np.repeat(np.arange(3), 2)
    config = DataSplittingConfig(
        TrainingType.FULL,
        False,
        [DataSplitter(ValSplitByType.TRIAL, "0.8", SplitUnit.RATIO)],
        [DataSplitter(SplitByType.TRIAL, "0.8", SplitUnit.RATIO)],
    )

    with pytest.raises(ValueError):
        DatasetGenerator(epoch_data, config).generate()


def test_generator_joint_high_ratios_reject_infeasible_fixed_targets():
    epoch_data = Epochs(
        [
            _recording_epochs(
                "recordings/five-groups-high-ratio.fif",
                [100, 150, 300, 350, 500, 550, 700, 750, 900, 950],
                labels=[1, 2] * 5,
            )
        ]
    )
    config = DataSplittingConfig(
        TrainingType.FULL,
        False,
        [DataSplitter(ValSplitByType.TRIAL, "0.8", SplitUnit.RATIO)],
        [DataSplitter(SplitByType.TRIAL, "0.8", SplitUnit.RATIO)],
    )
    with pytest.raises(ValueError):
        DatasetGenerator(epoch_data, config).generate()


def test_generator_split_masks_and_materialization_digest_are_deterministic():
    epoch_data = _multi_subject_kfold_epochs()
    config = DataSplittingConfig(
        TrainingType.FULL,
        False,
        [DataSplitter(ValSplitByType.TRIAL, "0.2", SplitUnit.RATIO)],
        [DataSplitter(SplitByType.TRIAL, "0.2", SplitUnit.RATIO)],
    )
    from XBrainLab.backend.dataset.split_audit import materialization_digest

    first = DatasetGenerator(epoch_data, config).generate()
    second = DatasetGenerator(epoch_data, config).generate()
    assert materialization_digest(first) == materialization_digest(second)
    for left, right in zip(first, second, strict=True):
        assert np.array_equal(left.train_mask, right.train_mask)
        assert np.array_equal(left.val_mask, right.val_mask)
        assert np.array_equal(left.test_mask, right.test_mask)


def _many_balanced_atomic_trial_epochs(group_count: int = 1719) -> Epochs:
    """Build the Zhou2020-scale trial scope without loading EEG payloads."""
    epoch_data = Epochs([])
    epoch_data.data = np.zeros((group_count, 1, 8), dtype=np.float32)
    epoch_data.subject = np.zeros(group_count, dtype=int)
    epoch_data.session = np.arange(group_count, dtype=int) % 7
    epoch_data.label = np.arange(group_count, dtype=int) % 4
    epoch_data.idx = np.arange(group_count)
    epoch_data.trial_group = np.arange(group_count)
    epoch_data.subject_map = {0: "S01"}
    epoch_data.session_map = {session: f"ses-{session}" for session in range(7)}
    epoch_data.label_map = {label: f"class-{label}" for label in range(4)}
    return epoch_data


@pytest.mark.parametrize(
    (
        "test_ratio",
        "validation_ratio",
        "expected_train_groups",
        "expected_validation_groups",
        "expected_test_groups",
    ),
    [
        ("0.2", "0.2", 1033, 343, 343),
        ("0.2", "0.3", 861, 515, 343),
        ("0.3", "0.2", 861, 343, 515),
    ],
)
def test_large_non_cv_trial_ratio_preview_is_fast_and_uses_original_scope_targets(
    test_ratio: str,
    validation_ratio: str,
    expected_train_groups: int,
    expected_validation_groups: int,
    expected_test_groups: int,
) -> None:
    """Changing ratio must promptly recompute the original 1,719-group scope."""
    epoch_data = _many_balanced_atomic_trial_epochs()
    config = DataSplittingConfig(
        TrainingType.FULL,
        False,
        [DataSplitter(ValSplitByType.TRIAL, validation_ratio, SplitUnit.RATIO)],
        [DataSplitter(SplitByType.TRIAL, test_ratio, SplitUnit.RATIO)],
    )

    started = time.monotonic()
    dataset = DatasetGenerator(epoch_data, config).generate()[0]
    elapsed = time.monotonic() - started

    assert elapsed < 8.0
    assert (
        len(np.unique(epoch_data.trial_group[dataset.test_mask]))
        == expected_test_groups
    )
    assert (
        len(np.unique(epoch_data.trial_group[dataset.val_mask]))
        == expected_validation_groups
    )
    assert (
        len(np.unique(epoch_data.trial_group[dataset.train_mask]))
        == expected_train_groups
    )
    assert set(epoch_data.label[dataset.train_mask].tolist()) == {0, 1, 2, 3}
    assert not np.any(dataset.train_mask & dataset.val_mask)
    assert not np.any(dataset.train_mask & dataset.test_mask)
    assert not np.any(dataset.val_mask & dataset.test_mask)
    assert np.array_equal(
        dataset.train_mask | dataset.val_mask | dataset.test_mask,
        np.ones(epoch_data.get_data_length(), dtype=bool),
    )


@pytest.mark.parametrize(
    "test_type,val_type",
    [
        (SplitByType.SESSION, ValSplitByType.TRIAL),
        (SplitByType.TRIAL, ValSplitByType.SESSION),
    ],
)
def test_generator_mixed_units_keep_required_partitions_nonempty(test_type, val_type):
    epoch_data = _multi_subject_kfold_epochs()
    epoch_data.session = np.tile(np.repeat(np.arange(7), [2, 1, 1, 1, 1, 1, 1]), 2)
    config = DataSplittingConfig(
        TrainingType.FULL,
        False,
        [DataSplitter(val_type, "0.2", SplitUnit.RATIO)],
        [DataSplitter(test_type, "0.2", SplitUnit.RATIO)],
    )
    if test_type is SplitByType.TRIAL:
        with pytest.raises(ValueError, match=r"Validation.*Test"):
            DatasetGenerator(epoch_data, config).generate()
        return
    dataset = DatasetGenerator(epoch_data, config).generate()[0]
    for subject in np.unique(epoch_data.subject):
        scope = epoch_data.subject == subject
        test_sessions = set(epoch_data.session[dataset.test_mask & scope])
        assert test_sessions
        assert not test_sessions & set(epoch_data.session[dataset.train_mask & scope])
        assert not test_sessions & set(epoch_data.session[dataset.val_mask & scope])
        assert (dataset.val_mask & scope).any()
        assert (dataset.train_mask & scope).any()
    _assert_groups_are_atomic(
        epoch_data, [dataset.train_mask, dataset.val_mask, dataset.test_mask]
    )


def _four_atomic_group_epochs(labels: list[int]) -> Epochs:
    epoch_data = Epochs([])
    count = len(labels)
    epoch_data.data = np.zeros((count, 1, 8), dtype=np.float32)
    epoch_data.subject = np.zeros(count, dtype=int)
    epoch_data.session = np.zeros(count, dtype=int)
    epoch_data.label = np.asarray(labels)
    epoch_data.idx = np.arange(count)
    epoch_data.trial_group = np.arange(count)
    epoch_data.subject_map = {0: "S01"}
    epoch_data.session_map = {0: "ses-0"}
    epoch_data.label_map = {0: "class-a", 1: "class-b"}
    return epoch_data


def _grouped_epochs(
    labels: list[int], trial_groups: list[int], sessions: list[int]
) -> Epochs:
    """Build a minimal real Epochs carrier for allocation counterexamples."""
    epoch_data = Epochs([])
    count = len(labels)
    epoch_data.data = np.zeros((count, 1, 8), dtype=np.float32)
    epoch_data.subject = np.zeros(count, dtype=int)
    epoch_data.session = np.asarray(sessions)
    epoch_data.label = np.asarray(labels)
    epoch_data.idx = np.arange(count)
    epoch_data.trial_group = np.asarray(trial_groups)
    epoch_data.subject_map = {0: "S01"}
    epoch_data.session_map = {
        session: f"ses-{session}" for session in sorted(set(sessions))
    }
    epoch_data.label_map = {0: "class-a", 1: "class-b"}
    return epoch_data


@pytest.mark.parametrize(
    "test_value,test_unit",
    [("1", SplitUnit.NUMBER), ("0.34", SplitUnit.RATIO)],
)
def test_mixed_non_cv_trial_test_and_session_validation_is_rejected(
    test_value, test_unit
):
    # Greedy test group 0 leaves only session 1 for validation and no train.
    # Group 1 test + session 0 validation leaves atomic group 2 (both classes).
    epoch_data = _grouped_epochs(
        labels=[0, 0, 0, 1],
        trial_groups=[0, 1, 2, 2],
        sessions=[0, 1, 1, 1],
    )
    config = DataSplittingConfig(
        TrainingType.FULL,
        False,
        [DataSplitter(ValSplitByType.SESSION, "1", SplitUnit.NUMBER)],
        [DataSplitter(SplitByType.TRIAL, test_value, test_unit)],
    )

    with pytest.raises(ValueError):
        DatasetGenerator(epoch_data, config).generate()


def test_class_aware_kfold_rebalances_a_layout_that_round_robin_would_break():
    epoch_data = _four_atomic_group_epochs([1, 0, 1, 0])
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [],
        [DataSplitter(SplitByType.TRIAL, "2", SplitUnit.KFOLD)],
    )

    datasets = DatasetGenerator(epoch_data, config).generate()

    assert len(datasets) == 2
    assert all(
        set(epoch_data.label[item.train_mask].tolist()) == {0, 1} for item in datasets
    )


def test_class_aware_kfold_repairs_a_greedy_three_group_counterexample():
    epoch_data = _four_atomic_group_epochs([0, 1, 0, 1])
    epoch_data.trial_group = np.asarray([0, 1, 2, 2])
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [],
        [DataSplitter(SplitByType.TRIAL, "2", SplitUnit.KFOLD)],
    )

    datasets = DatasetGenerator(epoch_data, config).generate()

    assert len(datasets) == 2
    assert all(
        set(epoch_data.label[item.train_mask].tolist()) == {0, 1} for item in datasets
    )


def test_class_aware_kfold_blocks_when_no_atomic_assignment_can_keep_train_classes():
    epoch_data = _four_atomic_group_epochs([0, 0, 0, 1])
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [],
        [DataSplitter(SplitByType.TRIAL, "2", SplitUnit.KFOLD)],
    )

    with pytest.raises(ValueError, match="Training split is missing"):
        DatasetGenerator(epoch_data, config).generate()


def test_cv_ratio_validation_rejects_infeasible_original_scope_target():
    epoch_data = _four_atomic_group_epochs([0, 1] * 4)
    epoch_data.trial_group = np.repeat(np.arange(4), 2)
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [DataSplitter(ValSplitByType.TRIAL, "0.8", SplitUnit.RATIO)],
        [DataSplitter(SplitByType.TRIAL, "2", SplitUnit.KFOLD)],
    )

    with pytest.raises(ValueError):
        DatasetGenerator(epoch_data, config).generate()


def test_cv_kfold_swaps_fixed_capacity_test_groups_for_validation_feasibility():
    # The greedy fixed-capacity layout [0, 2] / [1, 3] keeps test complements
    # class-complete but leaves no one-group validation that preserves train in
    # its second fold.  [0, 1] / [2, 3] is an equally sized feasible layout.
    epoch_data = _grouped_epochs(
        labels=[0, 0, 1, 1, 0, 1],
        trial_groups=[0, 1, 1, 2, 3, 3],
        sessions=[0, 0, 0, 0, 0, 0],
    )
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [DataSplitter(ValSplitByType.TRIAL, "0.25", SplitUnit.RATIO)],
        [DataSplitter(SplitByType.TRIAL, "2", SplitUnit.KFOLD)],
    )

    datasets = DatasetGenerator(epoch_data, config).generate()

    assert len(datasets) == 2
    assert all(
        len(set(epoch_data.trial_group[item.test_mask])) == 2 for item in datasets
    )
    assert set().union(
        *(set(epoch_data.trial_group[item.test_mask]) for item in datasets)
    ) == {0, 1, 2, 3}
    assert all(
        set(epoch_data.label[item.train_mask].tolist()) == {0, 1} for item in datasets
    )


def test_large_kfold_materializes_exact_disjoint_coverage_with_train_classes():
    epoch_data = Epochs([])
    count = 200
    epoch_data.data = np.zeros((count, 1, 8), dtype=np.float32)
    epoch_data.subject = np.zeros(count, dtype=int)
    epoch_data.session = np.zeros(count, dtype=int)
    epoch_data.label = np.arange(count, dtype=int) % 2
    epoch_data.idx = np.arange(count)
    epoch_data.trial_group = np.arange(count)
    epoch_data.subject_map = {0: "S01"}
    epoch_data.session_map = {0: "ses-0"}
    epoch_data.label_map = {0: "class-a", 1: "class-b"}
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [],
        [DataSplitter(SplitByType.TRIAL, "100", SplitUnit.KFOLD)],
    )

    datasets = DatasetGenerator(epoch_data, config).generate()

    assert len(datasets) == 100
    test_masks = np.asarray([item.test_mask for item in datasets], dtype=int)
    assert all(item.test_mask.any() for item in datasets)
    assert not np.any(test_masks.sum(axis=0) > 1)
    assert np.array_equal(test_masks.any(axis=0), np.ones(count, dtype=bool))
    assert all(
        np.array_equal(item.train_mask, ~item.test_mask)
        and set(epoch_data.label[item.train_mask].tolist()) == {0, 1}
        for item in datasets
    )


def test_generator_blocks_when_any_required_test_split_removes_a_train_only_class():
    epoch_data = _multi_subject_kfold_epochs()
    epoch_data.subject[:] = 0
    epoch_data.subject_map = {0: "S01"}
    epoch_data.label = epoch_data.trial_group.copy()
    epoch_data.label_map = {
        int(group): f"class-{group}" for group in np.unique(epoch_data.trial_group)
    }
    config = DataSplittingConfig(
        TrainingType.FULL,
        False,
        [],
        [DataSplitter(SplitByType.TRIAL, "1", SplitUnit.NUMBER)],
    )
    with pytest.raises(ValueError):
        DatasetGenerator(epoch_data, config).generate()


def test_trial_test_and_validation_ratios_use_the_same_original_group_scope():
    epoch_data = Epochs(
        [
            _recording_epochs(
                "recordings/five-atomic-groups.fif",
                [100, 300, 500, 700, 900],
                labels=[1, 2, 1, 2, 1],
            )
        ]
    )
    config = DataSplittingConfig(
        TrainingType.FULL,
        False,
        [DataSplitter(ValSplitByType.TRIAL, "0.2", SplitUnit.RATIO)],
        [DataSplitter(SplitByType.TRIAL, "0.4", SplitUnit.RATIO)],
    )

    dataset = DatasetGenerator(epoch_data, config).generate()[0]

    assert dataset.get_test_len() == 2
    assert dataset.get_val_len() == 1
    assert dataset.get_train_len() == 2
    _assert_groups_are_atomic(
        epoch_data,
        [dataset.train_mask, dataset.val_mask, dataset.test_mask],
    )


def test_non_cv_ratio_without_validation_rejects_target_that_removes_train_classes():
    epoch_data = Epochs(
        [
            _recording_epochs(
                "recordings/four-atomic-groups.fif",
                [100, 300, 500, 700],
                labels=[1, 2, 1, 2],
            )
        ]
    )
    config = DataSplittingConfig(
        TrainingType.FULL,
        False,
        [],
        [DataSplitter(SplitByType.TRIAL, "0.75", SplitUnit.RATIO)],
    )

    with pytest.raises(ValueError):
        DatasetGenerator(epoch_data, config).generate()


@pytest.mark.parametrize("fold_count", [2, 3])
@pytest.mark.parametrize(
    "validation_type", [ValSplitByType.TRIAL, ValSplitByType.SESSION]
)
def test_cv_validation_number_selects_exactly_one_unit_group_per_fold(
    fold_count: int, validation_type: ValSplitByType
) -> None:
    epoch_data = _multi_subject_kfold_epochs(subject_count=1)
    epoch_data.session = epoch_data.trial_group.copy()
    epoch_data.session_map = {
        session: f"ses-{session}" for session in np.unique(epoch_data.session)
    }
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [DataSplitter(validation_type, "1", SplitUnit.NUMBER)],
        [
            DataSplitter(
                SplitByType(validation_type.value), str(fold_count), SplitUnit.KFOLD
            )
        ],
    )

    datasets = DatasetGenerator(epoch_data, config).generate()

    assert len(datasets) == fold_count
    test_masks = np.asarray([dataset.test_mask for dataset in datasets], dtype=int)
    assert not np.any(test_masks.sum(axis=0) > 1)
    assert np.array_equal(
        test_masks.any(axis=0),
        np.ones(epoch_data.get_data_length(), dtype=bool),
    )
    validation_values = (
        epoch_data.trial_group
        if validation_type is ValSplitByType.TRIAL
        else epoch_data.session
    )
    assert all(
        len(set(validation_values[dataset.val_mask].tolist())) == 1
        and set(epoch_data.label[dataset.train_mask].tolist()) == {0, 1}
        for dataset in datasets
    )


def _cv_subject_validation_epochs(session_count: int) -> Epochs:
    """Return real epoch metadata with every subject represented in each session."""
    epoch_data = Epochs([])
    subjects: list[int] = []
    sessions: list[int] = []
    labels: list[int] = []
    for subject in range(4):
        for session in range(session_count):
            subjects.append(subject)
            sessions.append(session)
            labels.append((subject + session) % 2)
    count = len(subjects)
    epoch_data.data = np.zeros((count, 1, 8), dtype=np.float32)
    epoch_data.subject = np.asarray(subjects)
    epoch_data.session = np.asarray(sessions)
    epoch_data.label = np.asarray(labels)
    epoch_data.idx = np.arange(count)
    epoch_data.trial_group = np.arange(count)
    epoch_data.subject_map = {subject: f"S{subject + 1:02d}" for subject in range(4)}
    epoch_data.session_map = {
        session: f"ses-{session}" for session in range(session_count)
    }
    epoch_data.label_map = {0: "class-a", 1: "class-b"}
    return epoch_data


@pytest.mark.parametrize("fold_count", [2, 3])
def test_cv_trial_kfold_with_number_subject_validation_is_rejected(
    fold_count: int,
) -> None:
    epoch_data = _cv_subject_validation_epochs(session_count=3)
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [DataSplitter(ValSplitByType.SUBJECT, "1", SplitUnit.NUMBER)],
        [DataSplitter(SplitByType.TRIAL, str(fold_count), SplitUnit.KFOLD)],
    )

    with pytest.raises(ValueError):
        DatasetGenerator(epoch_data, config).generate()


@pytest.mark.parametrize("fold_count", [2, 3])
def test_cv_session_kfold_with_number_subject_validation_is_rejected(
    fold_count: int,
) -> None:
    epoch_data = _cv_subject_validation_epochs(session_count=3)
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [DataSplitter(ValSplitByType.SUBJECT, "1", SplitUnit.NUMBER)],
        [DataSplitter(SplitByType.SESSION, str(fold_count), SplitUnit.KFOLD)],
    )

    with pytest.raises(ValueError):
        DatasetGenerator(epoch_data, config).generate()


def test_dataset_generator_keeps_atomic_groups_across_kfold_test_val_and_train():
    epoch_data = _atomic_epochs()
    epoch_data.subject[:] = 0
    epoch_data.subject_map = {0: "S01"}
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
    dataset = Dataset(
        epoch_data,
        DataSplittingConfig(TrainingType.FULL, False, [], []),
    )
    dataset.set_name("class-boundary")
    dataset.test_mask = np.asarray([True, True, False, False])
    dataset.val_mask = np.asarray([False, False, True, False])
    dataset.train_mask = np.asarray([False, False, False, True])
    dataset.remaining_mask[:] = False

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    assert np.flatnonzero(dataset.test_mask).tolist() == [0, 1]
    assert result.ok is False
    assert any(
        issue.severity == "error" and "train split is missing class" in issue.message
        for issue in result.issues
    )
