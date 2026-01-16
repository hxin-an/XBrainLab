from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.ui.training.panel import TrainingPanel


class TestTrainingPanel:
    @pytest.fixture
    def panel(self, qtbot):
        # Mock MainWindow
        main_window = QMainWindow()
        main_window.study = MagicMock()
        main_window.study.is_training.return_value = False

        # Patch Controller used in TrainingPanel.__init__
        with patch("XBrainLab.ui.training.panel.TrainingController") as MockController:
            # Setup mock instance
            mock_controller = MockController.return_value
            mock_controller.is_training.return_value = False
            mock_controller.get_epoch_data.return_value = MagicMock()
            mock_controller.get_trainer.return_value = None
            mock_controller.has_datasets.return_value = False
            mock_controller.get_formatted_history.return_value = []

            panel = TrainingPanel(main_window)
            qtbot.addWidget(panel)

            # Attach mock for use in tests
            panel._mock_controller = mock_controller
            yield panel

            # Clean up (but yield hands control, so after test finishes)
            # Actually since we used yield inside patch default, scope is tricky.
            # But here I'm creating panel inside context.
            # The patch exits when fixture exits? using yield. Yes.

    def test_select_model_success(self, panel):
        mock_holder = MagicMock()
        mock_holder.target_model.__name__ = "DummyModel"

        with patch("XBrainLab.ui.training.panel.ModelSelectionWindow") as MockWindow:
            instance = MockWindow.return_value
            instance.exec.return_value = True
            instance.get_result.return_value = mock_holder

            # Mock the state update that would happen in a real study
            panel.study.model_holder = mock_holder

            # Use patch specific to the module to capture calls
            with patch(
                "XBrainLab.ui.training.panel.QMessageBox.information"
            ) as mock_info:
                panel.select_model()

                # Verify study called
                panel.study.set_model_holder.assert_called_once_with(mock_holder)
                mock_info.assert_called_once()

    def test_training_setting_success(self, panel):
        mock_option = MagicMock()

        with patch("XBrainLab.ui.training.panel.TrainingSettingWindow") as MockWindow:
            instance = MockWindow.return_value
            instance.exec.return_value = True
            instance.get_result.return_value = mock_option

            with patch("XBrainLab.ui.training.panel.QMessageBox.information"):
                panel.training_setting()

            panel.study.set_training_option.assert_called_once_with(mock_option)

    def test_start_training_success(self, panel):
        # Mock controller methods
        panel.controller.get_training_plan_holders.return_value = [MagicMock()]
        # State transitions
        # 1. First check: False (not running) -> Start
        # 2. Second check: True (started successfully) -> Timer Start
        panel.controller.is_training.side_effect = [False, True]

        panel.timer = MagicMock()

        with patch("XBrainLab.ui.training.panel.QMessageBox.critical") as mock_crit:
            panel.start_training()
            if mock_crit.called:
                print(f"Critical error: {mock_crit.call_args}")

        panel.controller.start_training.assert_called_once()
        panel.timer.start.assert_called_once()

    def test_split_data(self, panel):
        mock_generator = MagicMock()

        # Ensure imports work for patching
        with patch(
            "XBrainLab.ui.training.panel.DataSplittingSettingWindow"
        ) as MockWindow:
            instance = MockWindow.return_value
            instance.exec.return_value = True
            instance.get_result.return_value = mock_generator

            with patch(
                "XBrainLab.ui.training.panel.QMessageBox.information"
            ) as mock_info:
                panel.split_data()

                mock_generator.apply.assert_called_once_with(panel.study)
                mock_info.assert_called_once()

    def test_stop_training(self, panel):
        panel.controller.is_training.return_value = True
        panel.stop_training()
        panel.controller.stop_training.assert_called_once()

    def test_clear_history(self, panel):
        panel.controller.is_training.return_value = False
        panel.clear_history()
        panel.controller.clear_history.assert_called_once()
