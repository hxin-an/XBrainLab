"""
E2E pipeline tests exercising the Study facade with TrainingManager delegation.

Covers: Study.generate_plan, train, stop_training, export_output_csv,
        clean cascade, append plan, saliency propagation, and error paths.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

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


def _make_mock_dataset(n_trials=4, n_channels=4, n_samples=168, n_classes=2):
    """Return a mock dataset usable by TrainingPlanHolder."""
    X = np.random.randn(n_trials, n_channels, n_samples).astype(np.float32)
    y = np.array([i % n_classes for i in range(n_trials)])

    ds = MagicMock()
    ds.get_training_data.return_value = (X, y)
    ds.get_val_data.return_value = (X, y)
    ds.get_test_data.return_value = (X, y)
    ds.get_training_indices.return_value = np.arange(n_trials)
    ds.get_val_indices.return_value = np.arange(n_trials)
    ds.get_test_indices.return_value = np.arange(n_trials)
    ds.train_mask = np.ones(n_trials, dtype=bool)
    ds.val_mask = np.ones(n_trials, dtype=bool)
    ds.test_mask = np.ones(n_trials, dtype=bool)

    epoch_data = MagicMock()
    epoch_data.get_model_args.return_value = {
        "n_classes": n_classes,
        "channels": n_channels,
        "samples": n_samples,
        "sfreq": 128,
    }
    epoch_data.get_data.return_value = X
    epoch_data.get_label_list.return_value = y
    ds.get_epoch_data.return_value = epoch_data
    return ds


def _make_option(epoch=1, repeat=1):
    return TrainingOption(
        output_dir="test_output",
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=epoch,
        bs=2,
        lr=0.001,
        checkpoint_epoch=1,
        evaluation_option=TrainingEvaluation.TEST_ACC,
        repeat_num=repeat,
    )


_FS_PATCHES = (
    patch("matplotlib.pyplot.savefig"),
    patch("torch.save"),
    patch("numpy.savetxt"),
    patch("os.makedirs"),
    patch("XBrainLab.backend.training.training_plan.validate_type"),
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
        holder = ModelHolder(int, 0)
        study.model_holder = holder
        assert study.training_manager.model_holder is holder

    def test_training_option_property(self):
        study = Study()
        opt = MagicMock()
        study.training_option = opt
        assert study.training_manager.training_option is opt

    def test_saliency_params_property(self):
        study = Study()
        params = {"SmoothGrad": {}}
        study.saliency_params = params
        assert study.training_manager.saliency_params == params


class TestStudyGeneratePlan:
    """Study.generate_plan passes datasets from DataManager to TrainingManager."""

    @pytest.fixture
    def ready_study(self):
        study = Study()
        study.datasets = [_make_mock_dataset()]
        study.set_training_option(_make_option())
        study.set_model_holder(ModelHolder(EEGNet, {}))
        return study

    def test_generate_plan_creates_trainer(self, ready_study):
        with (
            _FS_PATCHES[0],
            _FS_PATCHES[1],
            _FS_PATCHES[2],
            _FS_PATCHES[3],
            _FS_PATCHES[4],
        ):
            ready_study.generate_plan(force_update=True)
            assert ready_study.trainer is not None
            assert ready_study.has_trainer()

    def test_generate_plan_no_datasets_raises(self):
        study = Study()
        study.set_training_option(_make_option())
        study.set_model_holder(ModelHolder(EEGNet, {}))
        with pytest.raises(ValueError, match="No valid dataset"):
            study.generate_plan()

    def test_generate_plan_no_option_raises(self):
        study = Study()
        study.datasets = [_make_mock_dataset()]
        study.set_model_holder(ModelHolder(EEGNet, {}))
        with pytest.raises(ValueError, match="training option"):
            study.generate_plan()

    def test_generate_plan_no_model_raises(self):
        study = Study()
        study.datasets = [_make_mock_dataset()]
        study.set_training_option(_make_option())
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
            _FS_PATCHES[4],
        ):
            study.generate_plan(force_update=True)
            study.trainer.job()

    def test_full_cycle_eegnet(self):
        study = Study()
        study.datasets = [_make_mock_dataset()]
        study.set_training_option(_make_option(epoch=2))
        study.set_model_holder(ModelHolder(EEGNet, {}))

        self._run_training(study)

        plan = study.trainer.get_training_plan_holders()[0]
        assert len(plan.train_record_list) == 1
        record = plan.train_record_list[0]
        assert TrainRecordKey.LOSS in record.train
        assert len(record.train[TrainRecordKey.LOSS]) == 2  # 2 epochs

    def test_full_cycle_sccnet(self):
        study = Study()
        study.datasets = [_make_mock_dataset()]
        study.set_training_option(_make_option(epoch=1))
        study.set_model_holder(ModelHolder(SCCNet, {}))

        self._run_training(study)

        plan = study.trainer.get_training_plan_holders()[0]
        assert len(plan.train_record_list) == 1

    def test_multi_repeat(self):
        study = Study()
        study.datasets = [_make_mock_dataset()]
        study.set_training_option(_make_option(epoch=1, repeat=2))
        study.set_model_holder(ModelHolder(EEGNet, {}))

        self._run_training(study)

        plan = study.trainer.get_training_plan_holders()[0]
        assert len(plan.train_record_list) == 2

    def test_multi_datasets(self):
        study = Study()
        study.datasets = [_make_mock_dataset(), _make_mock_dataset()]
        study.set_training_option(_make_option(epoch=1))
        study.set_model_holder(ModelHolder(EEGNet, {}))

        self._run_training(study)

        holders = study.trainer.get_training_plan_holders()
        assert len(holders) == 2
        for h in holders:
            assert len(h.train_record_list) == 1


class TestAppendPlan:
    """Study.generate_plan(append=True) adds to existing trainer."""

    def test_append_doubles_plans(self):
        study = Study()
        study.datasets = [_make_mock_dataset()]
        study.set_training_option(_make_option())
        study.set_model_holder(ModelHolder(EEGNet, {}))

        with (
            _FS_PATCHES[0],
            _FS_PATCHES[1],
            _FS_PATCHES[2],
            _FS_PATCHES[3],
            _FS_PATCHES[4],
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

    def test_stop_sets_interrupt(self):
        study = Study()
        study.trainer = MagicMock()
        study.stop_training()
        study.trainer.set_interrupt.assert_called_once()

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

    def test_propagation_through_study(self):
        study = Study()
        study.datasets = [_make_mock_dataset()]
        study.set_training_option(_make_option())
        study.set_model_holder(ModelHolder(EEGNet, {}))

        with (
            _FS_PATCHES[0],
            _FS_PATCHES[1],
            _FS_PATCHES[2],
            _FS_PATCHES[3],
            _FS_PATCHES[4],
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
