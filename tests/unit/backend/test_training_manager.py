"""Tests for TrainingManager extracted from Study."""

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.training import ModelHolder, TrainingOption
from XBrainLab.backend.training_manager import TrainingManager


class TestTrainingManagerInit:
    def test_defaults(self):
        tm = TrainingManager()
        assert tm.model_holder is None
        assert tm.training_option is None
        assert tm.trainer is None
        assert tm.saliency_params is None


class TestSetTrainingOption:
    def test_sets_valid_option(self):
        tm = TrainingManager()
        option = MagicMock(spec=TrainingOption)
        tm.set_training_option(option)
        assert tm.training_option == option

    def test_rejects_invalid_type(self):
        tm = TrainingManager()
        with pytest.raises(TypeError):
            tm.set_training_option("not_an_option")


class TestSetModelHolder:
    def test_sets_valid_holder(self):
        tm = TrainingManager()
        holder = ModelHolder(int, 0)
        tm.set_model_holder(holder)
        assert tm.model_holder == holder

    def test_rejects_invalid_type(self):
        tm = TrainingManager()
        with pytest.raises(TypeError):
            tm.set_model_holder("not_a_holder")


class TestGeneratePlan:
    def test_no_datasets_raises(self):
        tm = TrainingManager()
        tm.training_option = MagicMock()
        tm.model_holder = MagicMock()
        with pytest.raises(ValueError, match="No valid dataset"):
            tm.generate_plan(datasets=[])

    def test_no_training_option_raises(self):
        tm = TrainingManager()
        tm.model_holder = MagicMock()
        with pytest.raises(ValueError, match="training option"):
            tm.generate_plan(datasets=[MagicMock()])

    def test_no_model_holder_raises(self):
        tm = TrainingManager()
        tm.training_option = MagicMock()
        with pytest.raises(ValueError, match="model holder"):
            tm.generate_plan(datasets=[MagicMock()])

    @patch("XBrainLab.backend.training_manager.Trainer")
    @patch("XBrainLab.backend.training_manager.TrainingPlanHolder")
    def test_creates_trainer(self, mock_tph, mock_trainer):
        tm = TrainingManager()
        tm.training_option = MagicMock()
        tm.model_holder = MagicMock()
        datasets = [MagicMock(), MagicMock()]

        tm.generate_plan(datasets=datasets)

        assert mock_tph.call_count == 2
        mock_trainer.assert_called_once()
        assert tm.trainer == mock_trainer.return_value

    @patch("XBrainLab.backend.training_manager.TrainingPlanHolder")
    def test_append_to_existing(self, mock_tph):
        tm = TrainingManager()
        tm.training_option = MagicMock()
        tm.model_holder = MagicMock()
        tm.trainer = MagicMock()
        datasets = [MagicMock()]

        tm.generate_plan(datasets=datasets, append=True)

        tm.trainer.add_training_plan_holders.assert_called_once()


class TestTrain:
    def test_no_trainer_raises(self):
        tm = TrainingManager()
        with pytest.raises(ValueError, match="No valid trainer"):
            tm.train()

    def test_calls_run(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        tm.train(interact=True)
        tm.trainer.run.assert_called_once_with(interact=True)


class TestStopTraining:
    def test_no_trainer_raises(self):
        tm = TrainingManager()
        with pytest.raises(ValueError, match="No valid trainer"):
            tm.stop_training()

    def test_sets_interrupt(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        tm.stop_training()
        tm.trainer.set_interrupt.assert_called_once()


class TestIsTraining:
    def test_no_trainer_returns_false(self):
        tm = TrainingManager()
        assert tm.is_training() is False

    def test_delegates_to_trainer(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        tm.trainer.is_running.return_value = True
        assert tm.is_training() is True


class TestExportOutputCsv:
    def test_no_trainer_raises(self):
        tm = TrainingManager()
        with pytest.raises(ValueError, match="No valid training plan"):
            tm.export_output_csv("out.csv", "p", "rp")

    def test_no_record_raises(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        tm.trainer.get_real_training_plan.return_value = plan
        with pytest.raises(ValueError, match="No evaluation record"):
            tm.export_output_csv("out.csv", "p", "rp")

    def test_exports(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        record = MagicMock()
        plan = MagicMock()
        plan.get_eval_record.return_value = record
        tm.trainer.get_real_training_plan.return_value = plan
        tm.export_output_csv("out.csv", "p", "rp")
        record.export_csv.assert_called_once_with("out.csv")


class TestSaliencyParams:
    def test_get_none_default(self):
        tm = TrainingManager()
        assert tm.get_saliency_params() is None

    def test_set_and_get(self):
        tm = TrainingManager()
        params = {"SmoothGrad": {"n_samples": 50}}
        tm.set_saliency_params(params)
        assert tm.get_saliency_params() == params

    def test_propagates_to_existing_plans(self):
        tm = TrainingManager()
        plan_holder = MagicMock()
        tm.trainer = MagicMock()
        tm.trainer.get_training_plan_holders.return_value = [plan_holder]
        params = {"SmoothGrad": {"n_samples": 50}}
        tm.set_saliency_params(params)
        plan_holder.set_saliency_params.assert_called_once_with(params)


class TestCleanTrainer:
    def test_force_update_true(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        tm.clean_trainer(force_update=True)
        assert tm.trainer is None

    def test_force_update_false_with_trainer_raises(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        with pytest.raises(ValueError, match="already been done"):
            tm.clean_trainer(force_update=False)

    def test_force_update_false_no_trainer_ok(self):
        tm = TrainingManager()
        tm.clean_trainer(force_update=False)
        assert tm.trainer is None


class TestHasTrainer:
    def test_false_when_none(self):
        tm = TrainingManager()
        assert tm.has_trainer() is False

    def test_true_when_set(self):
        tm = TrainingManager()
        tm.trainer = MagicMock()
        assert tm.has_trainer() is True
