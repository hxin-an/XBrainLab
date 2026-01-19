import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox

from XBrainLab.ui.dashboard_panel.preprocess import PreprocessPanel

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def mock_main_window(qapp):
    window = MagicMock(spec=QMainWindow)
    window.study = MagicMock()
    # Add custom methods not in QMainWindow spec
    window.refresh_panels = MagicMock()
    return window


@pytest.fixture
def mock_controller(mock_main_window):
    controller = MagicMock()
    controller.is_epoched.return_value = False
    controller.has_data.return_value = True
    controller.get_preprocessed_data_list.return_value = []

    mock_main_window.study.get_controller.return_value = controller
    return controller


def test_preprocess_panel_init_controller(mock_main_window, mock_controller, qtbot):
    """Test initialization creates controller."""
    # Use real objects for inheritance check
    real_window = QMainWindow()
    real_window.study = mock_main_window.study

    panel = PreprocessPanel(real_window)
    qtbot.addWidget(panel)
    assert hasattr(panel, "controller")
    assert panel.controller == mock_controller

    panel.close()
    real_window.close()


def test_preprocess_panel_filtering(mock_main_window, mock_controller, qtbot):
    """Test filtering delegates to controller."""
    mock_controller.has_data.return_value = True

    # Use real window
    real_window = QMainWindow()
    real_window.study = mock_main_window.study
    real_window.refresh_panels = MagicMock()

    panel = PreprocessPanel(real_window)
    qtbot.addWidget(panel)

    with (
        patch.object(panel, "plot_sample_data"),  # Mock plotting
        patch("XBrainLab.ui.dashboard_panel.preprocess.FilteringDialog") as MockDialog,
    ):
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_params.return_value = (
            1.0,
            40.0,
            50.0,
        )  # l_freq, h_freq, notch

        with patch(
            "XBrainLab.ui.dashboard_panel.preprocess.QMessageBox.information"
        ) as mock_info:
            panel.open_filtering()

            mock_controller.apply_filter.assert_called_with(1.0, 40.0, 50.0)
            mock_info.assert_called_once()

    real_window.close()


def test_preprocess_panel_resample(mock_main_window, mock_controller, qtbot):
    """Test resampling delegates to controller."""
    mock_controller.has_data.return_value = True
    # Use real window
    real_window = QMainWindow()
    real_window.study = mock_main_window.study
    real_window.refresh_panels = MagicMock()

    panel = PreprocessPanel(real_window)
    qtbot.addWidget(panel)

    with (
        patch.object(panel, "plot_sample_data"),
        patch("XBrainLab.ui.dashboard_panel.preprocess.ResampleDialog") as MockDialog,
    ):
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_params.return_value = 256.0

        with patch(
            "XBrainLab.ui.dashboard_panel.preprocess.QMessageBox.information"
        ) as mock_info:
            panel.open_resample()

            mock_controller.apply_resample.assert_called_with(256.0)
            mock_info.assert_called_once()

    real_window.close()


def test_preprocess_panel_epoching(mock_main_window, mock_controller, qtbot):
    """Test epoching delegates to controller."""
    mock_controller.has_data.return_value = True
    # Use real window
    real_window = QMainWindow()
    real_window.study = mock_main_window.study
    real_window.refresh_panels = MagicMock()

    panel = PreprocessPanel(real_window)
    qtbot.addWidget(panel)

    with (
        patch.object(panel, "plot_sample_data"),
        patch("XBrainLab.ui.dashboard_panel.preprocess.EpochingDialog") as MockDialog,
    ):
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_params.return_value = ((0.0, 0.1), ["Event1"], -0.2, 0.5)

        mock_controller.apply_epoching.return_value = True

        with patch(
            "XBrainLab.ui.dashboard_panel.preprocess.QMessageBox.information"
        ) as mock_info:
            panel.open_epoching()

            mock_controller.apply_epoching.assert_called_with(
                (0.0, 0.1), ["Event1"], -0.2, 0.5
            )
            # Should show success message
            mock_info.assert_called_once()

    real_window.close()


def test_preprocess_panel_reset(mock_main_window, mock_controller, qtbot):
    """Test reset delegates to controller."""
    mock_controller.has_data.return_value = True
    real_window = QMainWindow()
    real_window.study = mock_main_window.study

    panel = PreprocessPanel(real_window)
    qtbot.addWidget(panel)

    with (
        patch.object(panel, "plot_sample_data"),
        patch(
            "XBrainLab.ui.dashboard_panel.preprocess.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch(
            "XBrainLab.ui.dashboard_panel.preprocess.QMessageBox.information"
        ) as mock_info,
        patch.object(panel, "info_panel") as mock_info_panel,
    ):
        panel.reset_preprocess()
        mock_controller.reset_preprocess.assert_called_once()
        mock_info.assert_called_once()
        mock_info_panel.update_info.assert_called_once()

    real_window.close()


if __name__ == "__main__":
    pytest.main([__file__])
