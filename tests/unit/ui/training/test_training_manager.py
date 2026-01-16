
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMessageBox

from XBrainLab.backend.training import Trainer
from XBrainLab.ui.training.training_manager import TrainingManagerWindow


class TestTrainingManager:
    @pytest.fixture
    def mock_trainer(self):
        trainer = MagicMock(spec=Trainer)
        trainer.get_training_plan_holders.return_value = []
        trainer.is_running.return_value = False
        trainer.get_progress_text.return_value = "IDLE"
        return trainer

    @pytest.fixture
    def window(self, qtbot, mock_trainer):
        # Mock Trainer check in __init__
        with patch('XBrainLab.ui.training.training_manager.isinstance', return_value=True):
            window = TrainingManagerWindow(None, mock_trainer)
            qtbot.addWidget(window)
            return window

    def test_init(self, window, mock_trainer):
        assert window.windowTitle() == "Training Manager"
        assert window.trainer == mock_trainer
        assert window.start_btn.isEnabled()

    def test_start_training(self, window, mock_trainer):
        mock_trainer.is_running.return_value = False

        window.start_training()

        mock_trainer.run.assert_called_once_with(interact=True)
        assert not window.start_btn.isEnabled()

    def test_stop_training(self, window, mock_trainer):
        # Case 1: Not running
        mock_trainer.is_running.return_value = False
        with patch.object(QMessageBox, 'warning') as mock_warn:
            window.stop_training()
            mock_warn.assert_called_once()
            mock_trainer.set_interrupt.assert_not_called()

        # Case 2: Running
        mock_trainer.is_running.return_value = True
        window.stop_training()
        mock_trainer.set_interrupt.assert_called_once()

    def test_update_loop_finish(self, window, mock_trainer):
        # Simulate training finished
        window.start_btn.setEnabled(False) # Simulate running state
        mock_trainer.is_running.return_value = False

        with patch.object(QMessageBox, 'information') as mock_info:
            window.show() # Must be visible for update_loop
            window.update_loop()

            assert window.start_btn.isEnabled()
            assert window.status_bar.text() == "IDLE"
            mock_info.assert_called_once()

    def test_update_table(self, window, mock_trainer):
        # Mock plan holder
        plan = MagicMock()
        plan.get_name.return_value = "Plan1"
        plan.get_training_status.return_value = "Running"
        plan.get_training_epoch.return_value = 10
        plan.get_training_evaluation.return_value = [0.01, 0.5, 99.0, 0.8, 0.02, 98.0, 0.7]

        window.training_plan_holders = [plan]

        window.update_table()

        assert window.plan_table.rowCount() == 1
        assert window.plan_table.item(0, 0).text() == "Plan1"
        assert window.plan_table.item(0, 1).text() == "Running"
