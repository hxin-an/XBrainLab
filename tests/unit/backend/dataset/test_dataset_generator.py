from unittest.mock import patch

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
from XBrainLab.backend.study import Study

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
    DatasetGenerator(epochs, config)


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

    generator.reset()
    assert generator.is_clean()


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
    for i in range(len(result)):
        assert result[i].get_name() == "Subject-" + str(i + 1) + "_0"
        X, _ = result[i].get_training_data()
        assert (((i + 1) * 100000 + 2 * 1000) == (X // 1000 * 1000)).all()
        X, _ = result[i].get_val_data()
        assert (((i + 1) * 100000 + 2 * 1000) == (X // 1000 * 1000)).all()
        X, _ = result[i].get_test_data()
        assert (((i + 1) * 100000 + 1 * 1000) == (X // 1000 * 1000)).all()


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
        for j in range(len(session_list)):
            idx = i * len(session_list) + j
            assert result[idx].get_name() == "Subject-" + str(i + 1) + "_" + str(j)
            X, _ = result[idx].get_training_data()
            assert (
                ((i + 1) * 100000 + ((j + 1) % len(session_list) + 1) * 1000)
                == (X // 1000 * 1000)
            ).all()
            X, _ = result[idx].get_val_data()
            assert (
                ((i + 1) * 100000 + ((j + 1) % len(session_list) + 1) * 1000)
                == (X // 1000 * 1000)
            ).all()
            X, _ = result[idx].get_test_data()
            assert (
                ((i + 1) * 100000 + ((j) % len(session_list) + 1) * 1000)
                == (X // 1000 * 1000)
            ).all()


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
    X, _ = result.get_training_data()
    assert ((X // 100000 * 100000) != (1 * 100000)).all()
    assert len(X) == block_size * ((len(subject_list) - 1) * (len(session_list) - 1))
    X, _ = result.get_val_data()
    assert ((X // 100000 * 100000) != (1 * 100000)).all()
    assert len(X) == block_size * ((len(subject_list) - 1) * 1)
    X, _ = result.get_test_data()
    assert ((X // 100000 * 100000) == (1 * 100000)).all()
    assert len(X) == block_size * len(session_list)


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
    for i in range(len(subject_list)):
        assert result[i].get_name() == "Fold_" + str(i)
        X, _ = result[i].get_training_data()
        assert (((i + 1) * 100000) != (X // 100000 * 100000)).all()
        assert len(X) == block_size * (
            (len(subject_list) - 1) * (len(session_list) - 1)
        )
        X, _ = result[i].get_val_data()
        assert (((i + 1) * 100000) != (X // 100000 * 100000)).all()
        assert len(X) == block_size * ((len(subject_list) - 1) * 1)
        X, _ = result[i].get_test_data()
        assert (((i + 1) * 100000) == (X // 100000 * 100000)).all()
        assert len(X) == block_size * len(session_list)


def test_dataset_generator_trial_kfold_cross_validation_is_non_leaking(
    preprocessed_data_list,  # noqa: F811
):
    for preprocessed_data in preprocessed_data_list:
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


def test_dataset_generator_apply(epochs):  # noqa: F811
    study = Study()
    is_cross_validation = False
    test_splitter_list = val_splitter_list = []
    config = DataSplittingConfig(
        TrainingType.IND, is_cross_validation, val_splitter_list, test_splitter_list
    )
    generator = DatasetGenerator(epochs, config)
    generator.datasets = [Dataset(epochs, config)]
    generator.apply(study)
    assert study.datasets == generator.datasets
