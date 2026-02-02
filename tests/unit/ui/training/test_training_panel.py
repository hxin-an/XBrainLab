import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow

from XBrainLab.ui.panels.training.panel import MetricTab, TrainingPanel

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def mock_main_window(qtbot):
    window = QMainWindow()
    window.study = MagicMock()
    window.subscribe = MagicMock()
    qtbot.addWidget(window)
    return window


@pytest.fixture
def mock_controller(mock_main_window):
    """
    Create a mock controller and ensure Study returns it.
    """
    controller = MagicMock()
    controller.is_training.return_value = False
    controller.has_datasets.return_value = True
    controller.get_trainer.return_value = None
    controller.validate_ready.return_value = True

    # Configure study logic
    # When panel calls get_controller, return this mock
    mock_main_window.study.get_controller.return_value = controller
    return controller


def test_training_panel_init_controller(mock_main_window, mock_controller, qtbot):
    """Test initialization creates controller."""
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)
    assert hasattr(panel, "controller")
    assert panel.controller == mock_controller
    panel.close()


def test_training_panel_start_training_success(
    mock_main_window, mock_controller, qtbot
):
    """
    Test that 'Start Training' works correctly using controller.
    """
    # Setup
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)

    # Verify Start Button is enabled (Mock returns Ready)
    panel.sidebar.check_ready_to_train()
    assert panel.sidebar.btn_start.isEnabled()

    # Trigger Start Training
    # Simulate state change: Not training -> Start called -> Training
    # Providing plenty of True values to avoid StopIteration during
    # subsequent UI updates
    mock_controller.is_training.side_effect = [False] + [True] * 50

    with (
        patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
        patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
    ):
        panel.sidebar.start_training_ui_action()

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
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)

    with (
        patch("XBrainLab.ui.panels.training.sidebar.DataSplittingDialog") as MockDialog,
        patch("XBrainLab.ui.panels.training.sidebar.QMessageBox.information"),
    ):
        # Setup Dialog Mock
        instance = MockDialog.return_value
        instance.exec.return_value = True
        mock_generator = MagicMock()
        instance.get_result.return_value = mock_generator

        panel.sidebar.split_data()

        # Verify Dialog checked with Controller
        MockDialog.assert_called_with(panel.sidebar, mock_controller)

        # Verify Controller applied splitting
        mock_controller.apply_data_splitting.assert_called_once_with(mock_generator)


def test_training_panel_stop_training(mock_main_window, mock_controller, qtbot):
    """
    Test that 'Stop Training' delegates to controller.
    """
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)

    # Simulate Training
    mock_controller.is_training.return_value = True

    panel.sidebar.stop_training()

    mock_controller.stop_training.assert_called_once()


def test_training_panel_check_ready(mock_main_window, mock_controller, qtbot):
    """Test check_ready_to_train logic."""
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)

    # 1. Not Ready
    mock_controller.validate_ready.return_value = False
    mock_controller.has_datasets.return_value = False
    mock_controller.has_model.return_value = True
    mock_controller.has_training_option.return_value = True

    panel.sidebar.check_ready_to_train()
    assert not panel.sidebar.btn_start.isEnabled()
    assert "Data Splitting" in panel.sidebar.btn_start.toolTip()

    # 2. Ready
    mock_controller.validate_ready.return_value = True
    panel.sidebar.check_ready_to_train()
    assert panel.sidebar.btn_start.isEnabled()
