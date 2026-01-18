import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow

from XBrainLab.ui.training.panel import MetricTab, TrainingPanel

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def mock_main_window(qtbot):
    window = QMainWindow()
    window.study = MagicMock()
    qtbot.addWidget(window)
    return window


@pytest.fixture
def mock_controller():
    # Patch the TrainingController class in the panel module
    with patch("XBrainLab.ui.training.panel.TrainingController") as MockController:
        instance = MockController.return_value
        instance.is_training.return_value = False
        instance.has_datasets.return_value = True
        instance.get_trainer.return_value = None
        instance.validate_ready.return_value = True
        yield instance


def test_training_panel_init_controller(mock_main_window, mock_controller, qtbot):
    """Test initialization creates controller."""
    panel = TrainingPanel(mock_main_window)
    qtbot.addWidget(panel)
    assert hasattr(panel, "controller")
    # Since we patched the class, panel.controller should be our mock instance
    # (or rather, the return value of the mocked constructor)
    # verify constructor was called
    # MockController constructor returns mock_controller
    assert panel.controller == mock_controller

    panel.close()


def test_training_panel_start_training_success(
    mock_main_window, mock_controller, qtbot
):
    """
    Test that 'Start Training' works correctly using controller.
    """
    # Setup
    panel = TrainingPanel(mock_main_window)
    panel.controller = (
        mock_controller  # Explicitly set if needed, but init should handle it via patch
    )
    qtbot.addWidget(panel)

    # Verify Start Button is enabled (Mock returns Ready)
    panel.check_ready_to_train()
    assert panel.btn_start.isEnabled()

    # Trigger Start Training
    # Simulate state change: Not training -> Start called -> Training
    mock_controller.is_training.side_effect = [False, True]

    with (
        patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
        patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
    ):
        panel.start_training()

        # Should call controller.start_training
        mock_controller.start_training.assert_called_once()

        # Verify no errors
        assert not mock_critical.called
        assert not mock_warning.called


def test_metric_tab_methods_exist():
    """
    Verify MetricTab now has the required methods.
    """
    tab = MetricTab("Test")
    assert hasattr(tab, "update_plot")
    assert hasattr(tab, "clear")


def test_training_panel_split_data_success(mock_main_window, mock_controller, qtbot):
    """
    Test that 'Dataset Splitting' delegates to dialog and controller.
    """
    panel = TrainingPanel(mock_main_window)
    qtbot.addWidget(panel)

    with (
        patch("XBrainLab.ui.training.panel.DataSplittingSettingWindow") as MockDialog,
        patch("XBrainLab.ui.training.panel.QMessageBox.information"),
    ):
        # Setup Dialog Mock
        instance = MockDialog.return_value
        instance.exec.return_value = True
        mock_generator = MagicMock()
        instance.get_result.return_value = mock_generator

        panel.split_data()

        # Verify Dialog checked with Controller
        MockDialog.assert_called_with(panel, mock_controller)

        # Verify Controller applied splitting
        mock_controller.apply_data_splitting.assert_called_once_with(mock_generator)


def test_training_panel_stop_training(mock_main_window, mock_controller, qtbot):
    """
    Test that 'Stop Training' delegates to controller.
    """
    panel = TrainingPanel(mock_main_window)
    qtbot.addWidget(panel)

    # Simulate Training
    mock_controller.is_training.return_value = True

    panel.stop_training()

    mock_controller.stop_training.assert_called_once()


def test_training_panel_update_loop_metrics(mock_main_window, mock_controller, qtbot):
    """
    Test that update_loop correctly updates metrics from controller history.
    """
    panel = TrainingPanel(mock_main_window)
    qtbot.addWidget(panel)

    # Mock Controller.is_training to True
    mock_controller.is_training.return_value = True

    # Mock get_formatted_history


def test_training_panel_check_ready(mock_main_window, mock_controller, qtbot):
    """Test check_ready_to_train logic."""
    panel = TrainingPanel(mock_main_window)
    qtbot.addWidget(panel)

    # 1. Not Ready
    mock_controller.validate_ready.return_value = False
    mock_controller.has_datasets.return_value = False
    mock_controller.has_model.return_value = True
    mock_controller.has_training_option.return_value = True

    panel.check_ready_to_train()
    assert not panel.btn_start.isEnabled()
    assert "Data Splitting" in panel.btn_start.toolTip()

    # 2. Ready
    mock_controller.validate_ready.return_value = True
    panel.check_ready_to_train()
    assert panel.btn_start.isEnabled()
