import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton

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
    assert hasattr(sidebar, "btn_montage")
    assert hasattr(sidebar, "btn_saliency")
    assert hasattr(sidebar, "btn_export")


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
    ):
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_result.return_value = (["Ch1"], {"Ch1": [0, 0, 0]})

        sidebar.set_montage()

        mock_panel.controller.set_montage.assert_called()
        mock_info.assert_called_once()
