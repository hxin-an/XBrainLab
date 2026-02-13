from unittest.mock import MagicMock, patch

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

        mock_callback = MagicMock()
        controller.subscribe("training_started", mock_callback)

        with patch("threading.Thread") as MockThread:
            thread_instance = MockThread.return_value
            controller.start_training()

            mock_study.generate_plan.assert_called_once_with(
                force_update=True, append=True
            )
            mock_study.train.assert_called_once_with(interact=True)
            mock_callback.assert_called_once()

            # Verify monitoring started
            MockThread.assert_called_once()
            thread_instance.start.assert_called_once()

    def test_start_training_already_running(self, controller, mock_study):
        mock_study.is_training.return_value = True
        mock_callback = MagicMock()
        controller.subscribe("training_started", mock_callback)

        controller.start_training()

        mock_study.generate_plan.assert_not_called()
        mock_callback.assert_not_called()

    def test_stop_training(self, controller, mock_study):
        mock_study.is_training.return_value = True
        mock_callback = MagicMock()
        controller.subscribe("training_stopped", mock_callback)

        controller.stop_training()

        mock_study.stop_training.assert_called_once()
        mock_callback.assert_called_once()

    def test_clear_history_running(self, controller, mock_study):
        mock_study.is_training.return_value = True
        with pytest.raises(RuntimeError):
            controller.clear_history()

    def test_clear_history_success(self, controller, mock_study):
        mock_study.is_training.return_value = False
        mock_trainer = MagicMock()
        mock_study.trainer = mock_trainer

        # Setup observer
        mock_callback = MagicMock()
        controller.subscribe("history_cleared", mock_callback)

        controller.clear_history()

        mock_trainer.clear_history.assert_called_once()
        mock_callback.assert_called_once()

    def test_get_formatted_history(self, controller, mock_study):
        mock_trainer = MagicMock()
        mock_study.trainer = mock_trainer

        # Mock Plan and Record
        plan_holder = MagicMock()
        plan_holder.model_holder.target_model.__name__ = "ModelA"
        plan_holder.get_training_repeat.return_value = 1

        record = MagicMock()
        record.repeat = 1

        plan_holder.get_plans.return_value = [record]
        mock_trainer.get_training_plan_holders.return_value = [plan_holder]
        mock_trainer.is_running.return_value = True
        mock_trainer.current_idx = 0

        history = controller.get_formatted_history()

        assert len(history) == 1
        assert history[0]["model_name"] == "ModelA"
        assert history[0]["group_name"] == "Group 1"
        assert history[0]["run_name"] == "1"
        assert history[0]["is_active"] is True
        assert history[0]["is_current_run"] is True

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
