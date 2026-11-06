"""Observable per-subject allocation, capacity, and reproducibility regressions."""

import numpy as np
import pytest

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
)


def scoped_epochs(subject_count=5, session_count=4, trials_per_session=10):
    count = subject_count * session_count * trials_per_session
    result = Epochs([])
    result.data = np.zeros((count, 1, 8), dtype=np.float32)
    result.subject = np.repeat(
        np.arange(subject_count), session_count * trials_per_session
    )
    result.session = np.tile(
        np.repeat(np.arange(session_count), trials_per_session), subject_count
    )
    result.label = np.arange(count) % 2
    result.idx = np.arange(count)
    result.trial_group = np.arange(count)
    result.subject_map = {index: f"S{index + 1:02d}" for index in range(subject_count)}
    result.session_map = {index: f"session-{index}" for index in range(session_count)}
    result.label_map = {0: "A", 1: "B"}
    return result


def config(
    test_type=SplitByType.TRIAL,
    value="0.2",
    unit=SplitUnit.RATIO,
    validation=None,
    train_type=TrainingType.FULL,
    cv=False,
):
    return DataSplittingConfig(
        train_type,
        cv,
        [] if validation is None else [validation],
        [DataSplitter(test_type, value, unit)],
    )


@pytest.mark.parametrize("split_type", [SplitByType.TRIAL, SplitByType.SESSION])
@pytest.mark.parametrize(
    "unit,value", [(SplitUnit.NUMBER, "1"), (SplitUnit.RATIO, "0.25")]
)
def test_full_holdout_applies_requested_counts_to_every_subject(
    split_type, unit, value
):
    epochs = scoped_epochs()
    dataset = DatasetGenerator(epochs, config(split_type, value, unit)).generate()[0]
    values = epochs.trial_group if split_type is SplitByType.TRIAL else epochs.session
    expected = 10 if split_type is SplitByType.TRIAL and unit is SplitUnit.RATIO else 1
    for subject in range(5):
        scope = epochs.subject == subject
        assert len(np.unique(values[scope & dataset.test_mask])) == expected
        assert (scope & dataset.train_mask).any()
        assert set(epochs.label[scope & dataset.train_mask]) == {0, 1}


@pytest.mark.parametrize("cv", [False, True])
@pytest.mark.parametrize("split_type", [SplitByType.TRIAL, SplitByType.SESSION])
def test_full_masks_are_foldwise_union_of_individual_masks(cv, split_type):
    epochs = scoped_epochs()
    args = {
        "test_type": split_type,
        "value": "3" if cv else "0.2",
        "unit": SplitUnit.KFOLD if cv else SplitUnit.RATIO,
        "validation": DataSplitter(ValSplitByType.TRIAL, "0.2", SplitUnit.RATIO),
        "cv": cv,
    }
    full = DatasetGenerator(epochs, config(**args)).generate()
    individual = DatasetGenerator(
        epochs, config(**args, train_type=TrainingType.IND)
    ).generate()
    folds = 3 if cv else 1
    for fold in range(folds):
        for partition in ("train_mask", "val_mask", "test_mask"):
            union = np.logical_or.reduce(
                [
                    getattr(individual[subject * folds + fold], partition)
                    for subject in range(5)
                ]
            )
            assert np.array_equal(getattr(full[fold], partition), union)


def test_finer_validation_ratio_uses_remaining_scope_of_each_subject():
    epochs = scoped_epochs()
    specification = config(
        SplitByType.SESSION,
        "2",
        SplitUnit.NUMBER,
        DataSplitter(ValSplitByType.TRIAL, "0.25", SplitUnit.RATIO),
    )
    dataset = DatasetGenerator(epochs, specification).generate()[0]
    for subject in range(5):
        scope = epochs.subject == subject
        assert (scope & dataset.test_mask).sum() == 20
        assert (scope & dataset.val_mask).sum() == 5


def test_exact_number_can_leave_multilabel_group_for_train():
    epochs = scoped_epochs(1, 1, 4)
    epochs.trial_group = np.asarray([0, 0, 1, 2])
    dataset = DatasetGenerator(
        epochs, config(value="2", unit=SplitUnit.NUMBER)
    ).generate()[0]
    assert set(epochs.trial_group[dataset.test_mask]) == {1, 2}
    assert set(epochs.trial_group[dataset.train_mask]) == {0}


def test_oversized_ratio_pair_is_rejected_without_silent_shrink():
    epochs = scoped_epochs()
    specification = config(
        value="0.8",
        validation=DataSplitter(ValSplitByType.TRIAL, "0.8", SplitUnit.RATIO),
    )
    generator = DatasetGenerator(epochs, specification)
    sequence = Dataset.SEQ
    with pytest.raises(ValueError):
        generator.generate()
    assert generator.datasets == []
    assert sequence == Dataset.SEQ


@pytest.mark.parametrize(
    "test_type,val_type",
    [
        (SplitByType.TRIAL, ValSplitByType.SESSION),
        (SplitByType.TRIAL, ValSplitByType.SUBJECT),
        (SplitByType.SESSION, ValSplitByType.SUBJECT),
    ],
)
def test_direct_generator_rejects_validation_coarser_than_test(test_type, val_type):
    epochs = scoped_epochs()
    specification = config(
        test_type, validation=DataSplitter(val_type, "0.2", SplitUnit.RATIO)
    )
    with pytest.raises(ValueError, match=r"Validation.*Test"):
        DatasetGenerator(epochs, specification).generate()


def test_full_failure_names_infeasible_subject_and_rolls_back():
    epochs = scoped_epochs()
    epochs.trial_group[epochs.subject == 4] = 999
    generator = DatasetGenerator(epochs, config())
    sequence = Dataset.SEQ
    with pytest.raises(ValueError, match="S05"):
        generator.generate()
    assert generator.datasets == []
    assert sequence == Dataset.SEQ


@pytest.mark.parametrize("cv", [False, True])
def test_class_allocation_preserves_source_proportions(cv):
    epochs = scoped_epochs(1, 1, 100)
    epochs.label = np.asarray([0] * 80 + [1] * 20)
    specification = config(
        value="5" if cv else "0.2",
        unit=SplitUnit.KFOLD if cv else SplitUnit.RATIO,
        cv=cv,
    )
    for dataset in DatasetGenerator(epochs, specification).generate():
        assert np.bincount(epochs.label[dataset.test_mask]).tolist() == [16, 4]
        assert set(epochs.label[dataset.train_mask]) == {0, 1}


def test_recorded_seed_changes_ties_and_reproduces_masks():
    epochs = scoped_epochs()
    first_config = config()
    second_config = config()
    second_config.seed = 7
    first = DatasetGenerator(epochs, first_config).generate()[0]
    repeat = DatasetGenerator(epochs, first_config).generate()[0]
    second = DatasetGenerator(epochs, second_config).generate()[0]
    assert first_config.seed == 42
    assert np.array_equal(first.test_mask, repeat.test_mask)
    assert not np.array_equal(first.test_mask, second.test_mask)


def test_full_rejects_subject_with_train_only_class_even_if_others_supply_it():
    epochs = scoped_epochs()
    epochs.label[epochs.subject == 4] = np.arange(40)
    with pytest.raises(ValueError, match=r"S05.*training classes"):
        DatasetGenerator(epochs, config()).generate()


@pytest.mark.parametrize("seed", [-1, 2**32, 1.5, True])
def test_config_rejects_invalid_seed(seed):
    with pytest.raises(ValueError, match="seed"):
        DataSplittingConfig(TrainingType.FULL, False, [], [], seed=seed)


def test_number_retry_diversifies_group_support_before_repeating_equivalent_starts():
    # For seed 42, singleton groups 13 and 8 come after 32 multilabel groups.
    # Trying only the first 32 seeded starts misses the feasible allocation:
    # hold out both singletons and 31 AB groups, retain one AB group for Train.
    labels = []
    groups = []
    for group in range(34):
        group_labels = [0] if group == 13 else [1] if group == 8 else [0, 1]
        labels.extend(group_labels)
        groups.extend([group] * len(group_labels))
    epochs = scoped_epochs(1, 1, len(labels))
    epochs.label = np.asarray(labels)
    epochs.trial_group = np.asarray(groups)
    dataset = DatasetGenerator(
        epochs, config(value="33", unit=SplitUnit.NUMBER)
    ).generate()[0]
    assert len(np.unique(epochs.trial_group[dataset.test_mask])) == 33
    assert len(np.unique(epochs.trial_group[dataset.train_mask])) == 1
    assert set(epochs.label[dataset.train_mask]) == {0, 1}


@pytest.mark.parametrize(
    "validation_type,number,expected_counts",
    [
        (ValSplitByType.SESSION, "1", [6, 4]),
        (ValSplitByType.TRIAL, "10", [4, 6]),
    ],
)
def test_validation_class_proportions_follow_the_configured_scope(
    validation_type, number, expected_counts
):
    # Original scope is 60:40; holding session 0 out leaves 24:36 (40:60).
    # Same-unit validation retains the original target; finer Trial validation
    # targets the remainder, matching the ratio/count scope contract.
    session_counts = [(36, 4), (6, 4), (4, 6), (14, 26)]
    epochs = scoped_epochs(1, 4, 25)
    epochs.session = np.repeat(np.arange(4), [40, 10, 10, 40])
    epochs.label = np.asarray(
        [
            label
            for count_a, count_b in session_counts
            for label in [0] * count_a + [1] * count_b
        ]
    )
    specification = config(
        SplitByType.SESSION,
        "4",
        SplitUnit.KFOLD,
        DataSplitter(validation_type, number, SplitUnit.NUMBER),
        cv=True,
    )
    datasets = DatasetGenerator(epochs, specification).generate()
    held_first_session = next(
        dataset for dataset in datasets if set(epochs.session[dataset.test_mask]) == {0}
    )
    assert (
        np.bincount(epochs.label[held_first_session.val_mask]).tolist()
        == expected_counts
    )
    if validation_type is ValSplitByType.SESSION:
        assert set(epochs.session[held_first_session.val_mask]) == {1}
    assert set(epochs.label[held_first_session.train_mask]) == {0, 1}


@pytest.mark.parametrize("split_type", [SplitByType.TRIAL, SplitByType.SESSION])
def test_unequal_subject_group_counts_keep_exact_cv_coverage_and_fold_unions(
    split_type,
):
    group_counts = [7, 8, 10]
    epochs = scoped_epochs(1, 1, sum(group_counts) * 2)
    epochs.subject = np.repeat(np.arange(3), np.asarray(group_counts) * 2)
    epochs.subject_map = {index: f"S{index + 1:02d}" for index in range(3)}
    epochs.trial_group = np.repeat(np.arange(sum(group_counts)), 2)
    epochs.session = np.concatenate(
        [np.repeat(np.arange(count), 2) for count in group_counts]
    )
    epochs.session_map = {index: f"session-{index}" for index in range(10)}
    args = {
        "test_type": split_type,
        "value": "3",
        "unit": SplitUnit.KFOLD,
        "validation": DataSplitter(
            ValSplitByType(split_type.value), "1", SplitUnit.NUMBER
        ),
        "cv": True,
    }
    full = DatasetGenerator(epochs, config(**args)).generate()
    individual = DatasetGenerator(
        epochs, config(**args, train_type=TrainingType.IND)
    ).generate()
    assert len(full) == 3
    assert len(individual) == 9
    assert np.all(np.sum([dataset.test_mask for dataset in full], axis=0) == 1)
    values = epochs.trial_group if split_type is SplitByType.TRIAL else epochs.session
    for subject, count in enumerate(group_counts):
        scope = epochs.subject == subject
        subject_folds = individual[subject * 3 : (subject + 1) * 3]
        assert np.array_equal(
            np.sum([dataset.test_mask for dataset in subject_folds], axis=0),
            scope.astype(int),
        )
        base, remainder = divmod(count, 3)
        assert sorted(
            len(np.unique(values[dataset.test_mask & scope])) for dataset in full
        ) == sorted([base + int(fold < remainder) for fold in range(3)])
        for dataset in subject_folds:
            assert len(np.unique(values[dataset.val_mask])) == 1
            assert set(epochs.label[dataset.train_mask]) == {0, 1}
    for fold in range(3):
        assert np.all(
            full[fold].train_mask.astype(int)
            + full[fold].val_mask
            + full[fold].test_mask
            == 1
        )
        for partition in ("train_mask", "val_mask", "test_mask"):
            assert np.array_equal(
                getattr(full[fold], partition),
                np.logical_or.reduce(
                    [
                        getattr(individual[subject * 3 + fold], partition)
                        for subject in range(3)
                    ]
                ),
            )
