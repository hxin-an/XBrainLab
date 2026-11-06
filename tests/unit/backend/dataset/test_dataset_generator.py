from unittest.mock import patch

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
)

from .test_epochs import (
    block_size,
    epochs,  # noqa: F401
    preprocessed_data_list,  # noqa: F401
    session_list,
    subject_list,
)


def test_dataset_generator(
    epochs,  # noqa: F811
):
    train_type = TrainingType.IND
    is_cross_validation = False
    test_splitter_list = []
    val_splitter_list = []
    config = DataSplittingConfig(
        train_type, is_cross_validation, val_splitter_list, test_splitter_list
    )
    with pytest.raises(ValueError):
        DatasetGenerator(epochs, config, ["test"])
    generator = DatasetGenerator(epochs, config)
    assert generator.datasets == []
    assert generator.interrupted is False
    assert generator.preview_failed is False
    assert generator.done is False
    assert generator.is_clean()


def test_dataset_generator_failed(
    epochs,  # noqa: F811
):
    train_type = TrainingType.FULL
    is_cross_validation = False
    val_splitter_list = []
    test_splitter_list = []
    config = DataSplittingConfig(
        train_type, is_cross_validation, val_splitter_list, test_splitter_list
    )
    generator = DatasetGenerator(epochs, config)
    generator.preview_failed = True
    assert not generator.is_clean()

    with pytest.raises(ValueError):
        generator.prepare_result()

    with pytest.raises(ValueError):
        generator.generate()


def test_dataset_generator_handle_individual(
    epochs,  # noqa: F811
):
    train_type = TrainingType.IND
    is_cross_validation = False
    split_value = 1
    split_unit = SplitUnit.NUMBER
    test_splitter_list = [DataSplitter(SplitByType.SESSION, split_value, split_unit)]
    split_value = 0.25
    split_unit = SplitUnit.RATIO
    val_splitter_list = [DataSplitter(ValSplitByType.TRIAL, split_value, split_unit)]
    config = DataSplittingConfig(
        train_type, is_cross_validation, val_splitter_list, test_splitter_list
    )
    generator = DatasetGenerator(epochs, config)
    result = generator.generate()
    assert len(result) == len(subject_list)
    for subject, dataset in enumerate(result):
        assert dataset.get_name() == f"Subject-{subject + 1}_0"
        assert set(epochs.subject[dataset.test_mask]) == {subject}
        test_sessions = set(epochs.session[dataset.test_mask])
        assert len(test_sessions) == 1
        assert not test_sessions & set(
            epochs.session[dataset.train_mask | dataset.val_mask]
        )
        assert dataset.get_test_len() == block_size
        assert dataset.get_val_len() == block_size // 4
        assert dataset.get_train_len() == block_size - block_size // 4


def test_dataset_generator_handle_individual_cross_validation(
    epochs,  # noqa: F811
):
    train_type = TrainingType.IND
    is_cross_validation = True
    split_value = 2
    split_unit = SplitUnit.KFOLD
    test_splitter_list = [DataSplitter(SplitByType.SESSION, split_value, split_unit)]
    split_value = 0.25
    split_unit = SplitUnit.RATIO
    val_splitter_list = [DataSplitter(ValSplitByType.TRIAL, split_value, split_unit)]
    config = DataSplittingConfig(
        train_type, is_cross_validation, val_splitter_list, test_splitter_list
    )
    generator = DatasetGenerator(epochs, config)
    result = generator.generate()
    assert len(result) == len(subject_list) * len(session_list)
    cohort_ids = [dataset.cross_validation_cohort_id for dataset in result]
    assert all(isinstance(cohort_id, str) and cohort_id for cohort_id in cohort_ids)
    assert len(set(cohort_ids)) == len(subject_list)
    for i in range(len(subject_list)):
        subject_cohort_ids = {
            cohort_ids[i * len(session_list) + j] for j in range(len(session_list))
        }
        assert len(subject_cohort_ids) == 1
        folds = result[i * len(session_list) : (i + 1) * len(session_list)]
        assert np.array_equal(
            np.logical_or.reduce([d.test_mask for d in folds]), epochs.subject == i
        )
        for j, dataset in enumerate(folds):
            assert dataset.get_name() == f"Subject-{i + 1}_{j}"
            assert set(epochs.subject[dataset.test_mask]) == {i}
            test_sessions = set(epochs.session[dataset.test_mask])
            assert len(test_sessions) == 1
            assert not test_sessions & set(
                epochs.session[dataset.train_mask | dataset.val_mask]
            )
            assert dataset.get_test_len() == block_size
            assert dataset.get_val_len() == block_size // 4


def test_dataset_generator_handle_full(
    epochs,  # noqa: F811
):
    train_type = TrainingType.FULL
    is_cross_validation = False
    split_value = 1
    split_unit = SplitUnit.NUMBER
    test_splitter_list = [DataSplitter(SplitByType.SUBJECT, split_value, split_unit)]
    split_value = 1
    split_unit = SplitUnit.NUMBER
    val_splitter_list = [DataSplitter(ValSplitByType.SESSION, split_value, split_unit)]
    config = DataSplittingConfig(
        train_type, is_cross_validation, val_splitter_list, test_splitter_list
    )
    generator = DatasetGenerator(epochs, config)
    result = generator.generate()
    assert len(result) == 1
    result = result[0]
    assert result.get_name() == "Fold_0"
    test_subjects = set(epochs.subject[result.test_mask])
    assert len(test_subjects) == 1
    assert not test_subjects & set(epochs.subject[result.train_mask | result.val_mask])
    assert result.get_test_len() == block_size * len(session_list)
    assert result.get_val_len() == block_size * (len(subject_list) - 1)
    assert result.get_train_len() == block_size * (len(subject_list) - 1)
    for subject in set(epochs.subject) - test_subjects:
        assert (
            len(set(epochs.session[result.val_mask & (epochs.subject == subject)])) == 1
        )


def test_dataset_generator_handle_full_cross_validation(
    epochs,  # noqa: F811
):
    train_type = TrainingType.FULL
    is_cross_validation = True
    split_value = 3
    split_unit = SplitUnit.KFOLD
    test_splitter_list = [DataSplitter(SplitByType.SUBJECT, split_value, split_unit)]
    split_value = 1
    split_unit = SplitUnit.NUMBER
    val_splitter_list = [DataSplitter(ValSplitByType.SESSION, split_value, split_unit)]
    config = DataSplittingConfig(
        train_type, is_cross_validation, val_splitter_list, test_splitter_list
    )
    generator = DatasetGenerator(epochs, config)
    result = generator.generate()
    assert len(result) == len(subject_list)
    assert np.all(np.sum([dataset.test_mask for dataset in result], axis=0) == 1)
    for i, dataset in enumerate(result):
        assert dataset.get_name() == f"Fold_{i}"
        test_subjects = set(epochs.subject[dataset.test_mask])
        assert len(test_subjects) == 1
        assert not test_subjects & set(
            epochs.subject[dataset.train_mask | dataset.val_mask]
        )
        assert dataset.get_test_len() == block_size * len(session_list)
        assert dataset.get_val_len() == block_size * (len(subject_list) - 1)
        assert dataset.get_train_len() == block_size * (len(subject_list) - 1)


def test_dataset_generator_trial_kfold_cross_validation_is_non_leaking(
    preprocessed_data_list,  # noqa: F811
):
    for preprocessed_data in preprocessed_data_list:
        # Trusted provenance must describe disjoint windows: this fixture
        # originally puts all six events inside one overlapping atomic group.
        source = preprocessed_data.get_mne()
        source.events[:, 0] = np.arange(len(source.events)) * len(source.times)
        epochs_module.mark_xbrainlab_raw_event_source_epochs(preprocessed_data)
    trusted_epochs = Epochs(preprocessed_data_list)
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [DataSplitter(ValSplitByType.TRIAL, "0.2", SplitUnit.RATIO)],
        [DataSplitter(SplitByType.TRIAL, "5", SplitUnit.KFOLD)],
    )

    datasets = DatasetGenerator(trusted_epochs, config).generate()
    audit = audit_dataset_splits(datasets, protocol="trial-wise")

    assert len(datasets) == 5
    assert audit.ok
    assert [dataset.get_name() for dataset in datasets] == [
        "Fold_0",
        "Fold_1",
        "Fold_2",
        "Fold_3",
        "Fold_4",
    ]
    for dataset in datasets:
        train = set(dataset.get_training_indices())
        val = set(dataset.get_val_indices())
        test = set(dataset.get_test_indices())
        assert train
        assert val
        assert test
        assert not (train & val)
        assert not (train & test)
        assert not (val & test)


@pytest.mark.parametrize(
    "train_type, handle_func_name",
    [(TrainingType.IND, "handle_ind"), (TrainingType.FULL, "handle_full")],
)
@pytest.mark.parametrize(
    "datasets, has_error", [([], True), ([1], False), ([1, 2, 3], False)]
)
def test_dataset_generator_generate(
    epochs,  # noqa: F811
    train_type,
    handle_func_name,
    datasets,
    has_error,
):
    is_cross_validation = False
    test_splitter_list = val_splitter_list = []
    config = DataSplittingConfig(
        train_type, is_cross_validation, val_splitter_list, test_splitter_list
    )
    generator = DatasetGenerator(epochs, config)

    def handle():
        generator.datasets.extend(datasets)

    with patch.object(generator, handle_func_name, side_effect=handle) as handle_mock:
        if has_error:
            with pytest.raises(ValueError):
                generator.generate()
            assert not generator.is_clean()
        else:
            generator.generate()
        handle_mock.assert_called_once()


@pytest.mark.parametrize("train_type", ["error", None])
def test_dataset_generator_generate_not_implemented(
    epochs,  # noqa: F811
    train_type,
):
    is_cross_validation = False
    test_splitter_list = val_splitter_list = []
    config = DataSplittingConfig(
        TrainingType.IND, is_cross_validation, val_splitter_list, test_splitter_list
    )
    config.train_type = train_type
    generator = DatasetGenerator(epochs, config)
    with pytest.raises(NotImplementedError):
        generator.generate()


@pytest.mark.parametrize("train_type", [(TrainingType.IND), (TrainingType.FULL)])
def test_dataset_generator_generate_exists(
    epochs,  # noqa: F811
    train_type,
):
    is_cross_validation = False
    test_splitter_list = val_splitter_list = []
    config = DataSplittingConfig(
        train_type, is_cross_validation, val_splitter_list, test_splitter_list
    )
    generator = DatasetGenerator(epochs, config)
    datasets = [1, 2, 3]
    generator.datasets = datasets
    result = generator.generate()
    assert result == datasets


def _dataset_generator(selected):
    def func(epoch):
        train_type = TrainingType.IND
        is_cross_validation = False
        test_splitter_list = val_splitter_list = []
        config = DataSplittingConfig(
            train_type, is_cross_validation, val_splitter_list, test_splitter_list
        )
        dataset = Dataset(epoch, config)
        dataset.set_selection(selected)
        return dataset

    return func


@pytest.mark.parametrize(
    "datasets, has_error",
    [
        ([], True),
        ([_dataset_generator(False)], True),
        ([_dataset_generator(True)], False),
        ([_dataset_generator(False), _dataset_generator(True)], False),
        ([_dataset_generator(False), _dataset_generator(False)], True),
    ],
)
@pytest.mark.parametrize("train_type", [(TrainingType.IND), (TrainingType.FULL)])
def test_dataset_generator_prepare_result(
    epochs,  # noqa: F811
    train_type,
    datasets,
    has_error,
):
    is_cross_validation = False
    test_splitter_list = val_splitter_list = []
    config = DataSplittingConfig(
        train_type, is_cross_validation, val_splitter_list, test_splitter_list
    )
    generator = DatasetGenerator(epochs, config)
    for i in range(len(datasets)):
        if not isinstance(datasets[i], Dataset):
            datasets[i] = datasets[i](epochs)
    generator.datasets = datasets

    with patch.object(generator, "generate"):
        if has_error:
            with pytest.raises(ValueError):
                generator.prepare_result()
        else:
            generator.prepare_result()
            assert generator.is_clean()
