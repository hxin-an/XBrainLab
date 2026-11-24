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


def _uneven_group_epochs(class_counts, split_type, *, extra_training_class=False):
    from XBrainLab.backend.dataset.epochs import EpochWindowProvenance

    counts = list(class_counts)
    if extra_training_class:
        # This group is mandatory Train support for a new class. A repair that
        # only handles a single all-class Train group cannot solve this case.
        counts.append((0, 0, 0, 0, 3))
    labels = [
        label
        for group in counts
        for label, count in enumerate(group)
        for _ in range(count)
    ]
    epochs = scoped_epochs(1, 1, len(labels))
    epochs.label = np.asarray(labels)
    epochs.label_map = {label: f"class-{label}" for label in set(labels)}
    groups = np.repeat(np.arange(len(counts)), [sum(group) for group in counts])
    epochs.trial_group = groups.copy()
    if split_type is SplitByType.SESSION:
        epochs.session = groups.copy()
        epochs.session_map = {index: f"session-{index}" for index in range(len(counts))}
    elif split_type is SplitByType.SUBJECT:
        epochs.subject = groups.copy()
        epochs.subject_map = {index: f"subject-{index}" for index in range(len(counts))}
    epochs.epoch_window_provenance = tuple(
        EpochWindowProvenance(
            "content-sha256:" + "a" * 64,
            int(group * 100),
            int(group * 100),
            int(group * 100 + 8),
            100.0,
            100.0,
            0.0,
            0.07,
            True,
        )
        for group in groups
    )
    return epochs


@pytest.mark.parametrize("split_type", list(SplitByType))
@pytest.mark.parametrize("extra_training_class", [False, True])
@pytest.mark.parametrize(
    "class_counts,test_count,validation_unit,validation_value,train_group",
    [
        (
            [
                (0, 4, 6, 7),
                (0, 7, 6, 7),
                (0, 3, 6, 1),
                (7, 3, 4, 0),
                (7, 4, 0, 7),
                (2, 2, 6, 2),
            ],
            4,
            SplitUnit.RATIO,
            "0.25",
            5,
        ),
        (
            [
                (2, 0, 0, 6),
                (4, 4, 0, 0),
                (7, 4, 1, 0),
                (0, 7, 4, 5),
                (1, 6, 3, 2),
                (1, 6, 6, 0),
                (5, 0, 7, 3),
            ],
            5,
            SplitUnit.NUMBER,
            "1",
            4,
        ),
    ],
    ids=["six-groups-number-ratio", "seven-groups-number-number"],
)
def test_paired_holdout_retains_feasible_training_groups(
    split_type,
    extra_training_class,
    class_counts,
    test_count,
    validation_unit,
    validation_value,
    train_group,
):
    """A proportional Test choice must not hide a feasible Validation/Train pair."""
    from XBrainLab.backend.application.dataset_split_preview import (
        DatasetSplitSpecification,
    )
    from XBrainLab.backend.dataset.split_audit import (
        audit_dataset_splits,
        split_protocols_for_config,
    )

    epochs = _uneven_group_epochs(
        class_counts, split_type, extra_training_class=extra_training_class
    )
    groups = epochs.trial_group
    group_count = len(np.unique(groups))
    specification = config(
        split_type,
        str(test_count),
        SplitUnit.NUMBER,
        DataSplitter(
            ValSplitByType(split_type.value), validation_value, validation_unit
        ),
    )
    specification.seed = 173
    specification = DatasetSplitSpecification.from_config(specification).to_config()
    protocols = split_protocols_for_config(specification)
    expected_train = {train_group}
    if extra_training_class:
        expected_train.add(group_count - 1)
    # Establish a valid independent witness before asking the allocator to find
    # one. Counts, atomic membership, temporal leakage and classes all matter.
    available = [index for index in range(group_count) if index not in expected_train]
    witness = Dataset(epochs, specification)
    witness.set_test(np.isin(groups, available[:test_count]))
    witness.set_val(np.isin(groups, available[test_count:]))
    witness.set_remaining_to_train()
    assert audit_dataset_splits([witness], protocols=protocols).ok
    assert len(set(groups[witness.test_mask])) == test_count
    assert len(set(groups[witness.val_mask])) == 1

    generated = DatasetGenerator(epochs, specification).generate()[0]
    repeated = DatasetGenerator(epochs, specification).generate()[0]
    assert len(set(groups[generated.test_mask])) == test_count
    assert len(set(groups[generated.val_mask])) == 1
    assert set(groups[generated.train_mask]) == expected_train
    assert audit_dataset_splits([generated], protocols=protocols).ok
    for partition in ("train_mask", "val_mask", "test_mask"):
        mask = getattr(generated, partition)
        assert np.array_equal(mask, getattr(repeated, partition))
        assert all(
            np.unique(mask[groups == group]).size == 1 for group in range(group_count)
        )
    assert np.all(
        generated.train_mask.astype(int) + generated.val_mask + generated.test_mask == 1
    )


def _six_group_paired_config(*, finer_validation=False):
    epochs = _uneven_group_epochs(
        [
            (0, 4, 6, 7),
            (0, 7, 6, 7),
            (0, 3, 6, 1),
            (7, 3, 4, 0),
            (7, 4, 0, 7),
            (2, 2, 6, 2),
        ],
        SplitByType.SESSION if finer_validation else SplitByType.TRIAL,
    )
    specification = config(
        SplitByType.SESSION if finer_validation else SplitByType.TRIAL,
        "4",
        SplitUnit.NUMBER,
        DataSplitter(
            ValSplitByType.TRIAL,
            "0.5" if finer_validation else "0.25",
            SplitUnit.RATIO,
        ),
    )
    specification.seed = 173
    return epochs, specification


def test_paired_repair_uses_remaining_scope_for_finer_validation():
    from XBrainLab.backend.dataset.split_audit import (
        audit_dataset_splits,
        split_protocols_for_config,
    )

    epochs, specification = _six_group_paired_config(finer_validation=True)
    dataset = DatasetGenerator(epochs, specification).generate()[0]
    groups = epochs.trial_group
    assert len(set(epochs.session[dataset.test_mask])) == 4
    # Half of the two remaining atomic groups, not half of the six originals.
    assert len(set(groups[dataset.val_mask])) == 1
    assert set(groups[dataset.train_mask]) == {5}
    assert audit_dataset_splits(
        [dataset], protocols=split_protocols_for_config(specification)
    ).ok


def test_cancellation_during_paired_repair_rolls_back(monkeypatch):
    epochs, specification = _six_group_paired_config()
    generator = DatasetGenerator(epochs, specification)
    original_validation = generator._validation_mask
    repair_reached = False

    def cancel_before_repaired_validation(scope, test_mask):
        nonlocal repair_reached
        # Every failed greedy attempt consumes group 5. Returning it to the
        # remainder is the first observable repair that can support Train.
        if 5 not in set(epochs.trial_group[test_mask]):
            repair_reached = True
            generator.set_interrupt()
        return original_validation(scope, test_mask)

    monkeypatch.setattr(
        generator, "_validation_mask", cancel_before_repaired_validation
    )
    sequence = Dataset.SEQ
    with pytest.raises(KeyboardInterrupt):
        generator.generate()
    assert repair_reached
    assert generator.datasets == []
    assert sequence == Dataset.SEQ
    assert generator.interrupted
    assert generator.preview_failed


def test_paired_repair_rejects_impossible_train_without_partial_publication():
    epochs, specification = _six_group_paired_config()
    # Remove G5's only A support. No group now contains all four classes, so
    # retaining one Train group cannot meet the exact requested counts.
    epochs.label[(epochs.trial_group == 5) & (epochs.label == 0)] = 1
    generator = DatasetGenerator(epochs, specification)
    sequence = Dataset.SEQ
    with pytest.raises(ValueError, match="requested group counts"):
        generator.generate()
    assert generator.datasets == []
    assert sequence == Dataset.SEQ
    assert generator.preview_failed


@pytest.mark.parametrize("class_count,train_capacity", [(2, 1), (3, 2), (4, 2)])
def test_impossible_train_class_capacity_does_not_repeat_validation_search(
    monkeypatch, class_count, train_capacity
):
    epochs = scoped_epochs(1, 1, 100)
    epochs.label = np.arange(100) % class_count
    epochs.label_map = {label: f"class-{label}" for label in range(class_count)}
    specification = config(
        value="20",
        unit=SplitUnit.NUMBER,
        validation=DataSplitter(
            ValSplitByType.TRIAL, str(80 - train_capacity), SplitUnit.NUMBER
        ),
    )
    generator = DatasetGenerator(epochs, specification)
    original_validation = generator._validation_mask
    validation_attempts = 0
    # Existing ordinary allocation retries have a bounded number of starts.
    # A provably impossible class capacity must not multiply that work again.
    ordinary_attempts = len(
        generator._selection_offsets(
            specification.test_splitter_list[0],
            np.ones(epochs.get_data_length(), dtype=bool),
        )
    )

    def count_validation_attempts(scope, test_mask):
        nonlocal validation_attempts
        validation_attempts += 1
        assert validation_attempts <= ordinary_attempts, (
            "Provably insufficient Train class capacity repeated Validation search"
        )
        return original_validation(scope, test_mask)

    monkeypatch.setattr(generator, "_validation_mask", count_validation_attempts)
    sequence = Dataset.SEQ
    with pytest.raises(ValueError, match="requested group counts"):
        generator.generate()
    assert validation_attempts == ordinary_attempts
    assert generator.datasets == []
    assert sequence == Dataset.SEQ
    assert generator.preview_failed
