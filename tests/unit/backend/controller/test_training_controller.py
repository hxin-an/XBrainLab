from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.controller.training_controller import TrainingController
from XBrainLab.backend.study import Study


class TestTrainingController:
    @pytest.fixture
    def mock_study(self):
        return MagicMock(spec=Study)

    @pytest.fixture
    def controller(self, mock_study):
        return TrainingController(mock_study)

    def test_init(self, controller, mock_study):
        assert controller._study == mock_study

    def test_is_training(self, controller, mock_study):
        mock_study.is_training.return_value = True
        assert controller.is_training() is True
        mock_study.is_training.assert_called_once()

    def test_start_training_not_running(self, controller, mock_study):
        mock_study.is_training.return_value = False
        controller.start_training()
        mock_study.generate_plan.assert_called_once_with(force_update=True, append=True)
        mock_study.train.assert_called_once_with(interact=True)

    def test_start_training_already_running(self, controller, mock_study):
        mock_study.is_training.return_value = True
        controller.start_training()
        mock_study.generate_plan.assert_not_called()
        mock_study.train.assert_not_called()

    def test_stop_training(self, controller, mock_study):
        mock_study.is_training.return_value = True
        controller.stop_training()
        mock_study.stop_training.assert_called_once()

    def test_clear_history_running(self, controller, mock_study):
        mock_study.is_training.return_value = True
        with pytest.raises(RuntimeError):
            controller.clear_history()

    def test_clear_history_success(self, controller, mock_study):
        mock_study.is_training.return_value = False
        mock_trainer = MagicMock()
        mock_study.trainer = mock_trainer
        controller.clear_history()
        mock_trainer.clear_history.assert_called_once()

    def test_validate_ready_success(self, controller, mock_study):
        mock_study.datasets = [1, 2]
        mock_study.model_holder = "model"
        mock_study.training_option = "option"
        assert controller.validate_ready() is True

    def test_validate_ready_fail(self, controller, mock_study):
        mock_study.datasets = []
        mock_study.model_holder = "model"
        mock_study.training_option = "option"
        assert controller.validate_ready() is False
