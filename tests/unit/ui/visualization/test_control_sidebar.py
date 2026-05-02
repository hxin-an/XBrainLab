import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton

from XBrainLab.backend.application import ApplyMontageCommand
from XBrainLab.ui.panels.visualization.control_sidebar import ControlSidebar

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def mock_controller():
    ctrl = MagicMock()
    ctrl.has_epoch_data.return_value = True
    ctrl.get_channel_names.return_value = ["Ch1", "Ch2"]
    return ctrl


@pytest.fixture
def mock_main_window():
    return QMainWindow()


@pytest.fixture
def mock_panel(mock_controller, mock_main_window):
    panel = MagicMock()
    panel.controller = mock_controller
    panel.main_window = mock_main_window
    return panel


def test_sidebar_init(mock_panel, qtbot):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)

    assert sidebar.findChild(QPushButton, "").text() == "Set Montage"
    assert isinstance(sidebar.btn_montage, QPushButton)
    assert isinstance(sidebar.btn_saliency, QPushButton)
    assert isinstance(sidebar.btn_export, QPushButton)


def test_sidebar_set_montage(mock_panel, qtbot):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.PickMontageDialog"
        ) as MockDialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.QMessageBox.information"
        ) as mock_info,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command"
        ) as mock_execute,
    ):
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_result.return_value = (["Ch1"], [[0, 0, 0]])
        mock_execute.return_value = MagicMock(failed=False)

        sidebar.set_montage()

        command = mock_execute.call_args.args[1]
        assert isinstance(command, ApplyMontageCommand)
        assert command.channels == ["Ch1"]
        assert command.positions == [(0.0, 0.0, 0.0)]
        mock_panel.controller.set_montage.assert_not_called()
        mock_info.assert_called_once()


def test_sidebar_set_montage_surfaces_command_failure(mock_panel, qtbot):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.PickMontageDialog"
        ) as MockDialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.QMessageBox.warning"
        ) as mock_warning,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.QMessageBox.information"
        ) as mock_info,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command"
        ) as mock_execute,
    ):
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_result.return_value = (["Ch1"], [[0, 0, 0]])
        mock_execute.return_value = MagicMock(
            failed=True,
            recoverable=True,
            message="Create epochs before applying a montage.",
        )

        sidebar.set_montage()

        mock_panel.controller.set_montage.assert_not_called()
        mock_info.assert_not_called()
        mock_warning.assert_called_once()
