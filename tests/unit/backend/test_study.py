from typing import Any, cast
from unittest.mock import patch

import mne
import pytest
import torch

from XBrainLab.backend.dataset import (
    Dataset,
    DatasetGenerator,
    DataSplittingConfig,
    TrainingType,
)
from XBrainLab.backend.load_data import Raw, RawDataLoader
from XBrainLab.backend.preprocessor import PreprocessBase
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
    TrainingPlanHolder,
)


def test_study_load_data():
    assert isinstance(Study().get_raw_data_loader(), RawDataLoader)


@pytest.fixture
def loaded_data_list():
    mne_data = mne.io.RawArray([[0]], mne.create_info(["test"], 100))
    return [Raw("test", mne_data)]


@pytest.fixture
def loaded_epoch_data_list():
    mne_data = mne.EpochsArray([[[0]]], mne.create_info(["test"], 100))
    return [Raw("test", mne_data)]


def _test_study_set_loaded_data_list_raise(study, loaded_data_list, force_update):
    if force_update:
        study.set_loaded_data_list(loaded_data_list, force_update)
    else:
        with pytest.raises(ValueError):
            study.set_loaded_data_list(loaded_data_list, force_update)
        study.clean_raw_data()
        study.set_loaded_data_list(loaded_data_list, force_update)


@pytest.mark.parametrize("force_update", [True, False])
def test_study_set_loaded_data_list(loaded_data_list, force_update):
    study = Study()
    study.set_loaded_data_list(loaded_data_list, force_update)
    _test_study_set_loaded_data_list_raise(study, loaded_data_list, force_update)


def _test_study_set_preprocessed_data_list_raise(study, loaded_data_list, force_update):
    if force_update or not study.datasets:
        study.set_preprocessed_data_list(loaded_data_list, force_update)
    else:
        with pytest.raises(ValueError):
            study.set_preprocessed_data_list(loaded_data_list, force_update)
        study.clean_datasets()
        study.set_preprocessed_data_list(loaded_data_list, force_update)


class FakePreprocessBase(PreprocessBase):
    def get_preprocess_desc(self):
        return "test"

    def _data_preprocess(self, preprocessed_data):
        preprocessed_data.filepath = "new"


@pytest.mark.parametrize("force_update", [True, False])
@pytest.mark.parametrize(
    "loaded_data_list_target, loaded_data_list_is_raw",
    [("loaded_data_list", True), ("loaded_epoch_data_list", False)],
)
@pytest.mark.parametrize("test_hook", [_test_study_set_loaded_data_list_raise])
def test_study_set_preprocessed_data_list(
    loaded_data_list_target, loaded_data_list_is_raw, force_update, test_hook, request
):
    loaded_data_list = request.getfixturevalue(loaded_data_list_target)
    study = Study()
    study.set_loaded_data_list(loaded_data_list, force_update)
    _test_study_set_preprocessed_data_list_raise(study, loaded_data_list, force_update)
    if loaded_data_list_is_raw:
        assert study.epoch_data is None
    else:
        assert study.epoch_data is not None
    study.preprocess(FakePreprocessBase)
    assert study.preprocessed_data_list[0].get_filepath() == "new"
    study.reset_preprocess()
    assert study.preprocessed_data_list[0].get_filepath() == "test"
    test_hook(study, loaded_data_list, force_update)


def test_study_get_datasets_generator(loaded_epoch_data_list):
    config = DataSplittingConfig(
        TrainingType.FULL,
        is_cross_validation=False,
        val_splitter_list=[],
        test_splitter_list=[],
    )
    study = Study()
    study.set_loaded_data_list(loaded_epoch_data_list)
    assert isinstance(study.get_datasets_generator(config), DatasetGenerator)


def _test_study_set_datasets_raise(study, dataset, force_update):
    if force_update:
        study.set_datasets([dataset], force_update)
    else:
        with pytest.raises(ValueError):
            study.set_datasets([dataset], force_update)
        study.clean_datasets()
        study.set_datasets([dataset], force_update)


@pytest.mark.parametrize("force_update", [True, False])
@pytest.mark.parametrize(
    "loaded_data_list_target", ["loaded_data_list", "loaded_epoch_data_list"]
)
@pytest.mark.parametrize(
    "test_hook",
    [
        _test_study_set_loaded_data_list_raise,
        _test_study_set_preprocessed_data_list_raise,
    ],
)
def test_study_set_datasets(
    loaded_data_list_target, force_update, loaded_epoch_data_list, test_hook, request
):
    loaded_data_list = request.getfixturevalue(loaded_data_list_target)
    config = DataSplittingConfig(
        TrainingType.FULL,
        is_cross_validation=False,
        val_splitter_list=[],
        test_splitter_list=[],
    )
    study = Study()
    study.set_loaded_data_list(loaded_epoch_data_list)
    assert study.epoch_data is not None
    dataset = Dataset(study.epoch_data, config)

    study.set_datasets([dataset], force_update)
    _test_study_set_datasets_raise(study, dataset, force_update)
    test_hook(study, loaded_data_list, force_update)


class FakeRecord:
    def export_csv(self, filepath):
        self.filepath = filepath


class FakePlan:
    def __init__(self, name, real_name, record=None):
        self.name = name
        self.real_name = real_name
        self.record = record

    def get_eval_record(self):
        return self.record


class FakeTrainer:
    def __init__(self, record=None):
        self.running = False
        self.interact = None
        self.interrupt = False
        self.return_plan = False
        self.record = record

    def run(self, interact=False):
        self.running = True
        self.interact = interact

    def set_interrupt(self):
        self.interrupt = True

    def stop(self, wait_timeout=None):
        del wait_timeout
        self.set_interrupt()
        self.running = False
        return True

    def is_running(self):
        return self.running

    def clean(self, force_update):
        pass

    def get_real_training_plan(self, name, real_name):
        if self.return_plan:
            return FakePlan(name, real_name, self.record)
        else:
            raise ValueError


@pytest.fixture
def trainer_study():
    study = Study()
    cast(Any, study).trainer = FakeTrainer()
    return study


@pytest.mark.parametrize("force_update", [True, False])
def test_study_set_training_option(trainer_study, force_update):
    option = TrainingOption(
        "test",
        torch.optim.Adam,
        {},
        True,
        None,
        1,
        1,
        1,
        1,
        TrainingEvaluation.VAL_ACC,
        1,
    )

    trainer_study.set_training_option(option, force_update)

    published = trainer_study.training_option
    assert published is not None
    assert published is not option
    assert published.epoch == option.epoch


def test_study_set_training_option_rejects_mutated_invalid_option():
    study = Study()
    existing = TrainingOption(
        "test",
        torch.optim.Adam,
        {},
        True,
        None,
        1,
        1,
        0.001,
        0,
        TrainingEvaluation.VAL_ACC,
        1,
    )
    invalid = TrainingOption(
        "test",
        torch.optim.Adam,
        {},
        True,
        None,
        1,
        1,
        0.001,
        0,
        TrainingEvaluation.VAL_ACC,
        1,
    )
    cast(Any, invalid).repeat_num = 1.5
    study.set_training_option(existing)

    with pytest.raises(ValueError):
        study.set_training_option(invalid)

    published = study.training_option
    assert published is not None
    assert published.epoch == existing.epoch


def test_study_compatibility_property_rejects_invalid_training_option():
    study = Study()
    existing = TrainingOption(
        "test",
        torch.optim.Adam,
        {},
        True,
        None,
        1,
        1,
        0.001,
        0,
        TrainingEvaluation.VAL_ACC,
        1,
    )
    study.set_training_option(existing)

    with pytest.raises(TypeError):
        cast(Any, study).training_option = object()

    published = study.training_option
    assert published is not None
    assert published.epoch == 1


def test_study_compatibility_property_rejects_invalid_model_holder():
    study = Study()
    holder = ModelHolder(int, {})
    study.set_model_holder(holder)

    with pytest.raises(TypeError):
        cast(Any, study).model_holder = object()

    published = study.model_holder
    assert published is not None
    assert published is not holder
    assert published.target_model is holder.target_model


@pytest.mark.parametrize("force_update", [True, False])
def test_study_set_model_holder(trainer_study, force_update):
    holder = ModelHolder(int, {})

    trainer_study.set_model_holder(holder, force_update)

    published = trainer_study.model_holder
    assert published is not None
    assert published is not holder
    assert published.target_model is holder.target_model


@pytest.mark.parametrize("force_update", [True, False])
def test_study_generate_plan(trainer_study, force_update):
    with (
        patch(
            "XBrainLab.backend.training.TrainingPlanHolder.__init__", return_value=None
        ) as holder_mock,
        patch(
            "XBrainLab.backend.training.Trainer.__init__", return_value=None
        ) as trainer_mock,
    ):
        cast(Any, trainer_study).datasets = [1, 2, 3]
        option = TrainingOption(
            "test",
            torch.optim.Adam,
            {},
            True,
            None,
            1,
            1,
            0.001,
            0,
            TrainingEvaluation.VAL_ACC,
            1,
        )
        holder = ModelHolder(int, {})
        trainer_study.set_training_option(option)
        trainer_study.set_model_holder(holder)
        if force_update:
            trainer_study.generate_plan(force_update=force_update)
        else:
            with pytest.raises(ValueError):
                trainer_study.generate_plan(force_update=force_update)
            trainer_study.clean_trainer()
            trainer_study.generate_plan(force_update=force_update)

        called_args_list = holder_mock.call_args_list
        assert len(called_args_list) == 3
        for i in range(3):
            called_args = called_args_list[i][0]
            assert called_args[0] is not holder
            assert called_args[0].target_model is holder.target_model
            assert called_args[1] == (i + 1)
            assert called_args[2].epoch == option.epoch
            assert called_args[3] is None  # saliency_params

        trainer_mock.assert_called_once()


@pytest.mark.parametrize(
    "missing_part, complain",
    [
        ["datasets", "dataset"],
        ["training_option", "training option"],
        ["model_holder", "model holder"],
    ],
)
def test_study_generate_plan_missing_options(missing_part, complain):
    study = Study()
    cast(Any, study).datasets = [1, 2, 3]
    study.set_training_option(
        TrainingOption(
            "test",
            torch.optim.Adam,
            {},
            True,
            None,
            1,
            1,
            0.001,
            0,
            TrainingEvaluation.VAL_ACC,
            1,
        )
    )
    study.set_model_holder(ModelHolder(int, {}))
    setattr(study, missing_part, None)

    with pytest.raises(ValueError, match=rf".*{complain}.*"):
        study.generate_plan()


def test_study_training(trainer_study):
    assert not trainer_study.is_training()
    trainer_study.train(interact=True)
    assert trainer_study.is_training()
    assert trainer_study.trainer.interact is True
    trainer_study.stop_training()
    assert trainer_study.trainer.interrupt


def test_study_training_not_set():
    study = Study()
    assert not study.is_training()
    with pytest.raises(ValueError):
        study.train()
    assert not study.is_training()
    with pytest.raises(ValueError):
        study.stop_training()


@pytest.mark.parametrize("has_record", [True, False])
@pytest.mark.parametrize("has_eval", [True, False])
def test_study_export_output_csv(trainer_study, has_record, has_eval):
    record = FakeRecord()
    if has_eval:
        trainer_study.trainer.record = record
    else:
        trainer_study.trainer.record = None

    trainer_study.trainer.return_plan = has_record

    if not has_record:
        with pytest.raises(ValueError):
            trainer_study.export_output_csv("test", "1", "2")
        return
    if not has_eval:
        with pytest.raises(ValueError):
            trainer_study.export_output_csv("test", "1", "2")
        return
    trainer_study.export_output_csv("test", "1", "2")
    assert record.filepath == "test"


def test_study_export_output_csv_not_set():
    study = Study()
    with pytest.raises(ValueError):
        study.export_output_csv("test", "test", "test")


def test_study_set_channels():
    class FakeEpochData:
        def __init__(self):
            self.channels = ["Cz"]

        def get_channel_names(self):
            return list(self.channels)

        def set_channels(self, channels, channel_types):
            self.channels = channels
            self.channel_types = channel_types

    study = Study()
    fake_epoch_data = FakeEpochData()
    cast(Any, study).epoch_data = fake_epoch_data
    study.set_channels(["Cz"], [(0.0, 0.0, 1.0)])
    assert fake_epoch_data.channels == ["Cz"]
    assert fake_epoch_data.channel_types == [(0.0, 0.0, 1.0)]


def test_study_set_channels_not_set():
    study = Study()
    with pytest.raises(ValueError):
        study.set_channels([], [])


def test_study_blocks_channel_identity_change_after_dataset_generation():
    class FakeEpochData:
        def __init__(self):
            self.channels = ["C3", "C4"]

        def get_channel_names(self):
            return list(self.channels)

        def set_channels(self, channels, _positions):
            self.channels = list(channels)

    study = Study()
    fake_epoch_data = FakeEpochData()
    cast(Any, study).epoch_data = fake_epoch_data
    cast(Any, study).datasets = [object()]

    with pytest.raises(ValueError, match="before generating datasets"):
        study.set_channels(["C3"], [(0.0, 0.0, 1.0)])

    assert fake_epoch_data.channels == ["C3", "C4"]


def test_study_allows_position_update_for_same_channels_after_training():
    class FakeEpochData:
        def __init__(self):
            self.channels = ["C3", "C4"]
            self.positions = None

        def get_channel_names(self):
            return list(self.channels)

        def set_channels(self, channels, positions):
            self.channels = list(channels)
            self.positions = list(positions)

    study = Study()
    fake_epoch_data = FakeEpochData()
    cast(Any, study).epoch_data = fake_epoch_data
    cast(Any, study).datasets = [object()]
    positions = [(0.0, 0.0, 1.0), (0.1, 0.0, 0.9)]

    study.set_channels(["C3", "C4"], positions)

    assert fake_epoch_data.positions == positions


def test_study_saliency_params():
    study = Study()
    params = {"method": {"param": 1}}
    study.set_saliency_params(params)
    assert study.get_saliency_params() == params

    holder = object.__new__(TrainingPlanHolder)
    holder.train_record_list = []
    holder._state_tracker = None
    holder.saliency_params = {}
    study.trainer = Trainer([holder])

    study.set_saliency_params(params)

    assert holder.saliency_params == params
