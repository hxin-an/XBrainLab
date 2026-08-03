"""
E2E pipeline tests exercising the Study facade with TrainingManager delegation.

Covers: Study.generate_plan, train, stop_training, export_output_csv,
        clean cascade, append plan, saliency propagation, and error paths.
"""

from unittest.mock import MagicMock, patch

import mne
import numpy as np
import pytest
import torch

from XBrainLab.backend.dataset import Dataset, DataSplittingConfig, Epochs, TrainingType
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.model_base import EEGNet, SCCNet
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    ModelHolder,
    TrainingEvaluation,
    TrainingOption,
)
from XBrainLab.backend.training.record import TrainRecordKey
from XBrainLab.backend.training_manager import TrainingManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tiny_dataset(n_trials=12, n_channels=4, n_samples=168, n_classes=2):
    """Return a real tiny Dataset with disjoint train, validation, and test data."""
    if n_trials != 12:
        raise ValueError("The canonical tiny split requires exactly 12 trials")
    rng = np.random.default_rng(0)
    X = rng.standard_normal((n_trials, n_channels, n_samples)).astype(np.float32)
    y = np.arange(n_trials, dtype=int) % n_classes
    events = np.column_stack(
        (np.arange(n_trials), np.zeros(n_trials, dtype=int), y),
    )
    info = mne.create_info(
        [f"EEG-{index}" for index in range(n_channels)],
        sfreq=128,
        ch_types="eeg",
    )
    mne_epochs = mne.EpochsArray(
        X,
        info,
        events=events,
        event_id={f"class-{index}": index for index in range(n_classes)},
        verbose=False,
    )
    epoch_data = Epochs([Raw("tiny-study-epo.fif", mne_epochs)])
    config = DataSplittingConfig(TrainingType.FULL, False, [], [])
    dataset = Dataset(epoch_data, config)
    dataset.set_name("tiny-study")
    dataset.train_mask[:8] = True
    dataset.val_mask[8:10] = True
    dataset.test_mask[10:] = True
    dataset.remaining_mask[:] = False

    train = set(dataset.get_training_indices())
    validation = set(dataset.get_val_indices())
    test = set(dataset.get_test_indices())
    assert train.isdisjoint(validation)
    assert train.isdisjoint(test)
    assert validation.isdisjoint(test)
    assert train | validation | test == set(range(n_trials))
    assert np.all(
        np.count_nonzero(
            np.stack((dataset.train_mask, dataset.val_mask, dataset.test_mask)),
            axis=0,
        )
        == 1,
    )
    return dataset


def _make_option(tmp_path, epoch=1, repeat=1):
    return TrainingOption(
        output_dir=str(tmp_path / "training-output"),
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=epoch,
        bs=2,
        lr=0.001,
        checkpoint_epoch=1,
        evaluation_option=TrainingEvaluation.VAL_ACC,
        repeat_num=repeat,
    )


_FS_PATCHES = (
    patch("matplotlib.pyplot.savefig"),
    patch("torch.save"),
    patch("numpy.savetxt"),
    patch("os.makedirs"),
)


# ---------------------------------------------------------------------------
# Tests: Study → TrainingManager integration
# ---------------------------------------------------------------------------


class TestStudyTrainingManagerDelegation:
    """Verify Study correctly delegates to its TrainingManager."""

    def test_study_has_training_manager(self):
        study = Study()
        assert isinstance(study.training_manager, TrainingManager)

    def test_property_delegation(self):
        """Setting study.trainer = X actually writes to training_manager."""
        study = Study()
        sentinel = MagicMock()
        study.trainer = sentinel
        assert study.training_manager.trainer is sentinel
        assert study.trainer is sentinel

    def test_model_holder_property(self):
        study = Study()
        holder = ModelHolder(torch.nn.Identity, {})
        study.model_holder = holder
        published = study.training_manager.model_holder

        assert published is not None
        assert published is not holder
        assert published.target_model is holder.target_model
        assert published.model_params_map == holder.model_params_map
        assert published.pretrained_weight_path == holder.pretrained_weight_path

    def test_training_option_property(self, tmp_path):
        study = Study()
        opt = _make_option(tmp_path)
        study.training_option = opt
        published = study.training_manager.training_option

        assert published is not None
        assert published is not opt
        assert published.output_dir == opt.output_dir
        assert published.optim is opt.optim
        assert published.optim_params == opt.optim_params
        assert published.use_cpu is opt.use_cpu
        assert published.gpu_idx == opt.gpu_idx
        assert published.epoch == opt.epoch
        assert published.bs == opt.bs
        assert published.lr == opt.lr
        assert published.checkpoint_epoch == opt.checkpoint_epoch
        assert published.evaluation_option is opt.evaluation_option
        assert published.repeat_num == opt.repeat_num

    def test_saliency_params_property(self):
        study = Study()
        params = {"SmoothGrad": {}}
        study.saliency_params = params
        assert study.training_manager.saliency_params == params


class TestStudyGeneratePlan:
    """Study.generate_plan passes datasets from DataManager to TrainingManager."""

    @pytest.fixture
    def ready_study(self, tmp_path):
        study = Study()
        study.datasets = [_make_tiny_dataset()]
        study.set_training_option(_make_option(tmp_path))
        study.set_model_holder(ModelHolder(EEGNet, {}))
        return study

    def test_generate_plan_creates_trainer(self, ready_study):
        with (
            _FS_PATCHES[0],
            _FS_PATCHES[1],
            _FS_PATCHES[2],
            _FS_PATCHES[3],
        ):
            ready_study.generate_plan(force_update=True)
            assert ready_study.trainer is not None
            assert ready_study.has_trainer()

    def test_generate_plan_no_datasets_raises(self, tmp_path):
        study = Study()
        study.set_training_option(_make_option(tmp_path))
        study.set_model_holder(ModelHolder(EEGNet, {}))
        with pytest.raises(ValueError, match="No valid dataset"):
            study.generate_plan()

    def test_generate_plan_no_option_raises(self):
        study = Study()
        study.datasets = [_make_tiny_dataset()]
        study.set_model_holder(ModelHolder(EEGNet, {}))
        with pytest.raises(ValueError, match="training option"):
            study.generate_plan()

    def test_generate_plan_no_model_raises(self, tmp_path):
        study = Study()
        study.datasets = [_make_tiny_dataset()]
        study.set_training_option(_make_option(tmp_path))
        with pytest.raises(ValueError, match="model holder"):
            study.generate_plan()


class TestStudyTrainCycle:
    """Full train → evaluate cycle through Study facade."""

    def _run_training(self, study):
        """Generate plan and run synchronously via trainer.job()."""
        with (
            _FS_PATCHES[0],
            _FS_PATCHES[1],
            _FS_PATCHES[2],
            _FS_PATCHES[3],
        ):
            study.generate_plan(force_update=True)
            study.trainer.job()

    def test_full_cycle_eegnet(self, tmp_path):
        study = Study()
        study.datasets = [_make_tiny_dataset()]
        study.set_training_option(_make_option(tmp_path, epoch=2))
        study.set_model_holder(ModelHolder(EEGNet, {}))

        self._run_training(study)

        plan = study.trainer.get_training_plan_holders()[0]
        assert len(plan.train_record_list) == 1
        record = plan.train_record_list[0]
        assert TrainRecordKey.LOSS in record.train
        assert len(record.train[TrainRecordKey.LOSS]) == 2  # 2 epochs
        assert set(record.evaluation_records) == {
            "training",
            "validation",
            "test",
        }
        assert all(
            evaluation.evaluation_split == split
            for split, evaluation in record.evaluation_records.items()
        )

    def test_full_cycle_sccnet(self, tmp_path):
        study = Study()
        study.datasets = [_make_tiny_dataset()]
        study.set_training_option(_make_option(tmp_path, epoch=1))
        study.set_model_holder(ModelHolder(SCCNet, {}))

        self._run_training(study)

        plan = study.trainer.get_training_plan_holders()[0]
        assert len(plan.train_record_list) == 1

    def test_multi_repeat(self, tmp_path):
        study = Study()
        study.datasets = [_make_tiny_dataset()]
        study.set_training_option(_make_option(tmp_path, epoch=1, repeat=2))
        study.set_model_holder(ModelHolder(EEGNet, {}))

        self._run_training(study)

        plan = study.trainer.get_training_plan_holders()[0]
        assert len(plan.train_record_list) == 2

    def test_multi_datasets(self, tmp_path):
        study = Study()
        study.datasets = [_make_tiny_dataset(), _make_tiny_dataset()]
        study.set_training_option(_make_option(tmp_path, epoch=1))
        study.set_model_holder(ModelHolder(EEGNet, {}))

        self._run_training(study)

        holders = study.trainer.get_training_plan_holders()
        assert len(holders) == 2
        for h in holders:
            assert len(h.train_record_list) == 1


class TestAppendPlan:
    """Study.generate_plan(append=True) adds to existing trainer."""

    def test_append_doubles_plans(self, tmp_path):
        study = Study()
        study.datasets = [_make_tiny_dataset()]
        study.set_training_option(_make_option(tmp_path))
        study.set_model_holder(ModelHolder(EEGNet, {}))

        with (
            _FS_PATCHES[0],
            _FS_PATCHES[1],
            _FS_PATCHES[2],
            _FS_PATCHES[3],
        ):
            study.generate_plan(force_update=True)
            assert len(study.trainer.get_training_plan_holders()) == 1
            study.generate_plan(append=True)
            assert len(study.trainer.get_training_plan_holders()) == 2


class TestCleanCascade:
    """Study.clean_* methods cascade correctly to TrainingManager."""

    def test_clean_trainer_clears(self):
        study = Study()
        study.trainer = MagicMock()
        study.clean_trainer(force_update=True)
        assert study.trainer is None

    def test_clean_trainer_force_false_raises(self):
        study = Study()
        study.trainer = MagicMock()
        with pytest.raises(ValueError, match="already been done"):
            study.clean_trainer(force_update=False)

    def test_clean_datasets_cascades_to_trainer(self):
        study = Study()
        study.trainer = MagicMock()
        study.clean_datasets(force_update=True)
        assert study.trainer is None

    def test_clean_raw_data_cascades_to_trainer(self):
        study = Study()
        study.trainer = MagicMock()
        study.clean_raw_data(force_update=True)
        assert study.trainer is None

    def test_set_loaded_data_cleans_trainer(self):
        study = Study()
        study.trainer = MagicMock()
        study.set_loaded_data_list([], force_update=True)
        assert study.trainer is None


class TestStopTraining:
    """Study.stop_training delegates to TrainingManager."""

    def test_stop_delegates_to_trainer(self):
        study = Study()
        trainer = MagicMock()
        trainer.stop.return_value = True
        study.trainer = trainer

        assert study.stop_training() is True
        trainer.stop.assert_called_once_with(wait_timeout=None)

    def test_stop_no_trainer_raises(self):
        study = Study()
        with pytest.raises(ValueError, match="No valid trainer"):
            study.stop_training()


class TestIsTraining:
    def test_false_when_no_trainer(self):
        study = Study()
        assert study.is_training() is False

    def test_delegates_to_trainer(self):
        study = Study()
        study.trainer = MagicMock()
        study.trainer.is_running.return_value = True
        assert study.is_training() is True


class TestSaliencyPropagation:
    """Setting saliency params propagates to existing plan holders."""

    def test_propagation_through_study(self, tmp_path):
        study = Study()
        study.datasets = [_make_tiny_dataset()]
        study.set_training_option(_make_option(tmp_path))
        study.set_model_holder(ModelHolder(EEGNet, {}))

        with (
            _FS_PATCHES[0],
            _FS_PATCHES[1],
            _FS_PATCHES[2],
            _FS_PATCHES[3],
        ):
            study.generate_plan(force_update=True)
            params = {
                "SmoothGrad": {"nt_samples": 5},
                "SmoothGrad_Squared": {"nt_samples": 5},
                "VarGrad": {"nt_samples": 5},
            }
            study.set_saliency_params(params)

            # Saliency params should be stored
            assert study.get_saliency_params() == params
            # And propagated to plan holders
            for plan in study.trainer.get_training_plan_holders():
                assert plan.saliency_params == params


class TestExportOutputCsv:
    """Study.export_output_csv delegates to TrainingManager."""

    def test_no_trainer_raises(self):
        study = Study()
        with pytest.raises(ValueError, match="No valid training plan"):
            study.export_output_csv("out.csv", "p", "rp")

    def test_no_eval_record_raises(self):
        study = Study()
        study.trainer = MagicMock()
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        study.trainer.get_real_training_plan.return_value = plan
        with pytest.raises(ValueError, match="No evaluation record"):
            study.export_output_csv("out.csv", "p", "rp")
