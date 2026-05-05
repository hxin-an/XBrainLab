import sys
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton

from XBrainLab.backend.application import ApplyMontageCommand, SaliencyCommand
from XBrainLab.backend.study import Study
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
        mock_panel.on_update.assert_not_called()
        mock_info.assert_called_once()


def test_sidebar_set_montage_blocked_by_backend_capability(qtbot):
    controller = MagicMock()
    controller.has_epoch_data.return_value = True
    controller.get_channel_names.return_value = ["Ch1", "Ch2"]
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    panel = MagicMock()
    panel.controller = controller
    panel.main_window = main_window
    sidebar = ControlSidebar(panel)
    qtbot.addWidget(sidebar)

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.PickMontageDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.QMessageBox.warning"
        ) as mock_warning,
    ):
        sidebar.set_montage()

    mock_dialog.assert_not_called()
    mock_warning.assert_called_once_with(
        sidebar,
        "Montage blocked",
        "Create epochs before applying a montage.",
    )


def test_sidebar_set_montage_real_study_uses_application_service(qtbot):
    controller = MagicMock()
    controller.has_epoch_data.return_value = False
    controller.get_channel_names.return_value = ["Ch1", "Ch2"]
    main_window = QMainWindow()
    study = Study()
    cast(Any, main_window).study = study
    epoch_data = MagicMock()
    epoch_data.get_mne.return_value.info = {"ch_names": ["Ch1", "Ch2"]}
    study.epoch_data = epoch_data
    panel = MagicMock()
    panel.controller = controller
    panel.main_window = main_window
    sidebar = ControlSidebar(panel)
    qtbot.addWidget(sidebar)

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.PickMontageDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.QMessageBox.information"
        ) as mock_info,
    ):
        mock_dialog.return_value.exec.return_value = True
        mock_dialog.return_value.get_result.return_value = (
            ["Ch1", "Ch2"],
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        )

        sidebar.set_montage()

    epoch_data.set_channels.assert_called_once_with(
        ["Ch1", "Ch2"],
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
    )
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


def test_sidebar_set_montage_legacy_result_uses_controller_fallback(
    mock_panel,
    qtbot,
):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)
    mock_panel.controller.set_montage.return_value = None

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.PickMontageDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.QMessageBox.information"
        ) as mock_info,
    ):
        mock_dialog.return_value.exec.return_value = True
        mock_dialog.return_value.get_result.return_value = (["Ch1"], [[0, 0, 0]])

        sidebar.set_montage()

    mock_panel.controller.set_montage.assert_called_once_with(
        ["Ch1"],
        [(0.0, 0.0, 0.0)],
    )
    mock_panel.on_update.assert_called_once()
    mock_info.assert_called_once_with(sidebar, "Success", "Montage set")


def test_sidebar_set_montage_refuses_real_study_controller_fallback(qtbot):
    controller = MagicMock()
    controller.has_epoch_data.return_value = True
    controller.get_channel_names.return_value = ["Ch1", "Ch2"]
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    panel = MagicMock()
    panel.controller = controller
    panel.main_window = main_window
    sidebar = ControlSidebar(panel)
    qtbot.addWidget(sidebar)

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.get_command_capability",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.PickMontageDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command",
            return_value=None,
        ),
        pytest.raises(RuntimeError, match="could not safely complete"),
    ):
        mock_dialog.return_value.exec.return_value = True
        mock_dialog.return_value.get_result.return_value = (["Ch1"], [[0, 0, 0]])
        sidebar.set_montage()

    controller.set_montage.assert_not_called()


def test_sidebar_set_saliency_blocked_by_backend_capability(qtbot):
    controller = MagicMock()
    controller.get_saliency_params.return_value = None
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    panel = MagicMock()
    panel.controller = controller
    panel.main_window = main_window
    sidebar = ControlSidebar(panel)
    qtbot.addWidget(sidebar)

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.QMessageBox.warning"
        ) as mock_warning,
    ):
        sidebar.set_saliency()

    mock_dialog.assert_not_called()
    mock_warning.assert_called_once_with(
        sidebar,
        "Saliency blocked",
        (
            "Create epochs, generate datasets, or select a model and training "
            "settings before querying saliency readiness."
        ),
    )


def test_sidebar_set_saliency_refuses_real_study_controller_fallback(qtbot):
    controller = MagicMock()
    controller.get_saliency_params.return_value = None
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    panel = MagicMock()
    panel.controller = controller
    panel.main_window = main_window
    sidebar = ControlSidebar(panel)
    qtbot.addWidget(sidebar)

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.get_command_capability",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command",
            return_value=None,
        ),
        pytest.raises(RuntimeError, match="could not safely complete"),
    ):
        mock_dialog.return_value.exec.return_value = True
        mock_dialog.return_value.get_result.return_value = {
            "SmoothGrad": {"nt_samples": 1}
        }
        sidebar.set_saliency()

    controller.set_saliency_params.assert_not_called()


def test_sidebar_set_saliency_service_success_uses_coordinator_refresh(
    mock_panel,
    qtbot,
):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)
    mock_panel.controller.get_saliency_params.return_value = None

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command",
            return_value=MagicMock(failed=False),
        ) as mock_execute,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.QMessageBox.information"
        ),
    ):
        mock_dialog.return_value.exec.return_value = True
        mock_dialog.return_value.get_result.return_value = {"method": "gradient"}
        sidebar.set_saliency()

    command = mock_execute.call_args.args[1]
    assert isinstance(command, SaliencyCommand)
    mock_panel.controller.set_saliency_params.assert_not_called()
    mock_panel.on_update.assert_not_called()


def test_sidebar_export_saliency_uses_query_before_stale_trainers(qtbot):
    controller = MagicMock()
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    panel = MagicMock()
    panel.controller = controller
    panel.main_window = main_window
    panel.get_trainers.return_value = [MagicMock()]
    sidebar = ControlSidebar(panel)
    qtbot.addWidget(sidebar)

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.ExportSaliencyDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.QMessageBox.warning"
        ) as mock_warning,
    ):
        sidebar.export_saliency()

    panel.get_trainers.assert_not_called()
    controller.get_trainers.assert_not_called()
    mock_dialog.assert_not_called()
    mock_warning.assert_called_once()
    assert "saliency" in mock_warning.call_args.args[2].lower()
