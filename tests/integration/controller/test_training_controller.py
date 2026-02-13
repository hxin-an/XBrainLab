"""
Integration tests for TrainingController.
"""

from unittest.mock import MagicMock, patch

import pytest
import torch

from XBrainLab.backend.controller.training_controller import TrainingController
from XBrainLab.backend.model_base import EEGNet
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import TrainingEvaluation, TrainingOption
from XBrainLab.backend.training.model_holder import ModelHolder


@pytest.fixture
def study():
    return Study()


@pytest.fixture
def training_controller(study):
    ctrl = TrainingController(study)
    yield ctrl
    ctrl.shutdown()


@pytest.fixture
def valid_training_option():
    return TrainingOption(
        output_dir="./test_output",
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,  # Short epoch for testing
        bs=4,
        lr=0.001,
        checkpoint_epoch=1,
        evaluation_option=TrainingEvaluation.TEST_ACC,
        repeat_num=1,
    )


class TestTrainingControllerLifecycle:
    """Test the full training lifecycle managed by the controller."""

    def test_validate_ready_requirements(
        self, training_controller, valid_training_option
    ):
        """Test strict validation checks before training can start."""
        # Initially nothing is set
        assert not training_controller.validate_ready()
        missing = training_controller.get_missing_requirements()
        assert "Data Splitting" in missing
        assert "Model Selection" in missing
        assert "Training Settings" in missing

        # 1. Set Training Option
        training_controller.set_training_option(valid_training_option)
        missing = training_controller.get_missing_requirements()
        assert "Training Settings" not in missing

        # 2. Set Model
        training_controller.set_model_holder(ModelHolder(EEGNet, {}))
        missing = training_controller.get_missing_requirements()
        assert "Model Selection" not in missing

        # 3. Set Mock Data (Simulate having datasets)
        # We Mock the internal study datasets check for this specific test
        # purely to verify the controller logic, not the study logic (which is tested elsewhere)
        with patch.object(training_controller, "has_datasets", return_value=True):
            assert training_controller.validate_ready()
            assert not training_controller.get_missing_requirements()

    def test_start_stop_training_lifecycle(
        self, training_controller, study, valid_training_option
    ):
        """Test starting, monitoring, and stopping training."""

        # Setup requirements
        training_controller.set_training_option(valid_training_option)
        training_controller.set_model_holder(ModelHolder(EEGNet, {}))

        # Mock backend methods to simulate training running
        study.generate_plan = MagicMock()
        study.train = MagicMock()
        study.stop_training = MagicMock()

        # Simulate is_training state
        with patch.object(study, "is_training", side_effect=[False, True, True, False]):
            # 1. Start Training
            training_controller.start_training()

            assert study.generate_plan.called
            assert study.train.called

            # 2. Stop Training
            training_controller.stop_training()
            assert study.stop_training.called

            # Allow thread to exit
            training_controller.shutdown()

    def test_training_events_emitted(self, training_controller, study):
        """Verify observant events are emitted correctly."""

        # Mock the notify method to track events
        training_controller.notify = MagicMock()

        # Setup mocks
        study.is_training = MagicMock(return_value=False)
        study.generate_plan = MagicMock()
        study.train = MagicMock()
        study.stop_training = MagicMock()

        # Start
        training_controller.start_training()
        # Should notify started
        training_controller.notify.assert_any_call("training_started")

        # Stop
        with patch.object(training_controller, "is_training", return_value=True):
            training_controller.stop_training()
            training_controller.notify.assert_any_call("training_stopped")


class TestTrainingHistory:
    """Test history management via controller."""

    def test_get_formatted_history_structure(self, training_controller, study):
        """Test that history is formatted correctly for UI (flat list of dicts)."""

        # Mock Trainer structure
        mock_trainer = MagicMock()
        study.trainer = mock_trainer

        # Mock Plans and Records
        mock_plan = MagicMock()
        mock_plan.model_holder.target_model.__name__ = "TestModel"
        mock_plan.get_training_repeat.return_value = 1

        mock_record = MagicMock()
        mock_record.repeat = 1

        mock_plan.get_plans.return_value = [mock_record]
        mock_trainer.get_training_plan_holders.return_value = [mock_plan]
        mock_trainer.is_running.return_value = False

        # Get history
        history = training_controller.get_formatted_history()

        assert len(history) == 1
        item = history[0]

        assert item["model_name"] == "TestModel"
        assert item["group_name"] == "Group 1"
        assert item["run_name"] == "1"
        assert item["plan"] == mock_plan
        assert item["record"] == mock_record
        assert item["is_active"] is False

    def test_clear_history_safety(self, training_controller, study):
        """Test validation when clearing history."""

        mock_trainer = MagicMock()
        study.trainer = mock_trainer

        # Case 1: Training is running -> Should raise error
        with (
            patch.object(training_controller, "is_training", return_value=True),
            pytest.raises(RuntimeError),
        ):
            training_controller.clear_history()

        # Case 2: Idle -> Should clear
        with patch.object(training_controller, "is_training", return_value=False):
            training_controller.clear_history()
            mock_trainer.clear_history.assert_called_once()
