import sys
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import (
    QApplication,
    QGroupBox,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QWidget,
)

from XBrainLab.backend.application import (
    SaliencyCommand,
    SaliencyPlanIdentity,
    SaliencyRunIdentity,
)
from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import CommandReviewContext
from XBrainLab.ui.interaction_outcome import InteractionOutcome, InteractionStatus
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

    assert isinstance(sidebar.btn_saliency, QPushButton)
    assert sidebar.btn_saliency.text() == "Saliency Settings"
    assert isinstance(sidebar.btn_montage, QPushButton)
    assert sidebar.btn_montage.text() == "Electrode Layout"


def test_electrode_layout_button_delegates_to_dataset_route_without_command(
    mock_panel,
    qtbot,
):
    shared_route = MagicMock(return_value=InteractionOutcome.cancelled("Cancelled."))
    mock_panel.main_window.dataset_panel = SimpleNamespace(
        sidebar=SimpleNamespace(open_electrode_layout=shared_route),
    )
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)

    with patch(
        "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command"
    ) as execute:
        sidebar.btn_montage.click()

    shared_route.assert_called_once_with()
    execute.assert_not_called()


def test_3d_controls_are_grouped_and_hidden_until_the_ready_3d_tab(mock_panel, qtbot):
    tabs = QTabWidget()
    regular = QWidget()
    three_d = QWidget()
    tabs.addTab(regular, "Map")
    tabs.addTab(three_d, "3D Plot")
    three_d.scene_ready = False
    mock_panel.tabs = tabs
    mock_panel.tab_3d = three_d
    mock_panel.saliency_combo.currentData.return_value = None
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)
    sidebar.show()

    group = sidebar.findChild(QGroupBox, "Visualization3DControls")
    assert group is not None
    assert group.title() == "3D PLOT"
    assert group.isHidden()
    assert sidebar.btn_reset_view.parentWidget() is not group
    assert sidebar.btn_3d_electrodes.parentWidget() is group
    assert sidebar.btn_3d_head_surface.parentWidget() is group

    tabs.setCurrentWidget(three_d)
    three_d.scene_ready = True
    sidebar.refresh_view_controls()

    assert group.isVisible()
    assert sidebar.btn_3d_electrodes.isVisible()
    assert sidebar.btn_3d_head_surface.isVisible()


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
            "XBrainLab.ui.panels.visualization.control_sidebar.show_warning"
        ) as mock_warning,
    ):
        outcome = sidebar.set_saliency()

    assert outcome.status is InteractionStatus.BLOCKED
    mock_dialog.assert_not_called()
    mock_warning.assert_called_once_with(
        sidebar,
        "Saliency blocked",
        (
            "Create EEG epochs, build the training dataset, or select a model "
            "and training settings before querying saliency readiness."
        ),
    )


def test_sidebar_set_saliency_dialog_rejection_returns_cancelled(mock_panel, qtbot):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)
    query_result = MagicMock(
        failed=False,
        diagnostics={"payload_type": "saliency_summary", "params": {}},
    )

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "get_command_review_context",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.get_command_capability",
            return_value=MagicMock(enabled=True),
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "execute_application_command",
            return_value=query_result,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as dialog,
    ):
        dialog.return_value.exec.return_value = False
        outcome = sidebar.set_saliency()

    assert outcome.status is InteractionStatus.CANCELLED


def test_sidebar_set_saliency_nonrecoverable_query_failure_returns_failed(
    mock_panel,
    qtbot,
):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)
    query_result = MagicMock(
        failed=True,
        recoverable=False,
        message="saliency query failed",
    )

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.get_command_capability",
            return_value=MagicMock(enabled=True),
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "execute_application_command",
            return_value=query_result,
        ),
        patch("XBrainLab.ui.panels.visualization.control_sidebar.show_warning"),
    ):
        outcome = sidebar.set_saliency()

    assert outcome.status is InteractionStatus.FAILED


def test_sidebar_set_saliency_uses_query_configuration_readiness(qtbot):
    controller = MagicMock()
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    panel = MagicMock()
    panel.controller = controller
    panel.main_window = main_window
    sidebar = ControlSidebar(panel)
    qtbot.addWidget(sidebar)
    query_result = MagicMock(
        failed=False,
        diagnostics={
            "payload_type": "saliency_summary",
            "params": {},
            "configure_available": False,
            "configure_reasons": [
                "Select a model and training settings before configuring saliency."
            ],
        },
    )
    capability = CommandCapability(command_name="saliency", enabled=True)

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "get_command_review_context",
            return_value=CommandReviewContext(
                capability=capability,
                publication_generation=29,
            ),
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command",
            return_value=query_result,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.show_warning"
        ) as mock_warning,
    ):
        sidebar.set_saliency()

    mock_dialog.assert_not_called()
    mock_warning.assert_called_once_with(
        sidebar,
        "Saliency blocked",
        "Select a model and training settings before configuring saliency.",
    )
    controller.get_saliency_params.assert_not_called()


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
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "get_command_review_context",
            return_value=None,
        ),
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
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.show_warning"
        ) as mock_warning,
    ):
        mock_dialog.return_value.exec.return_value = True
        mock_dialog.return_value.get_result.return_value = {
            "SmoothGrad": {"nt_samples": 1}
        }
        sidebar.set_saliency()

    mock_dialog.assert_not_called()
    mock_warning.assert_called_once()
    assert "could not safely complete" in mock_warning.call_args.args[2]
    controller.set_saliency_params.assert_not_called()


def test_sidebar_set_saliency_stages_for_real_study_without_controller_fallback(qtbot):
    controller = MagicMock()
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    panel = MagicMock()
    panel.controller = controller
    panel.main_window = main_window
    sidebar = ControlSidebar(panel)
    qtbot.addWidget(sidebar)
    query_result = MagicMock(
        failed=False,
        diagnostics={
            "payload_type": "saliency_summary",
            "params": {"SmoothGrad": {"nt_samples": 4}},
        },
    )
    capability = CommandCapability(command_name="saliency", enabled=True)
    review_context = CommandReviewContext(
        capability=capability,
        publication_generation=29,
    )
    run_identity = SaliencyRunIdentity(
        plan=SaliencyPlanIdentity(plan_index=0),
        run_index=0,
    )
    panel.saliency_settings_target.return_value = (
        29,
        run_identity,
        "EEGNet",
    )
    panel.stage_saliency_params.return_value = True

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.get_command_capability",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "get_command_review_context",
            return_value=review_context,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command",
            return_value=query_result,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.show_warning"
        ) as mock_warning,
    ):
        mock_dialog.return_value.exec.return_value = True
        mock_dialog.return_value.get_result.return_value = {
            "SmoothGrad": {"nt_samples": 5},
        }
        outcome = sidebar.set_saliency()

    assert outcome.status is InteractionStatus.ACCEPTED
    controller.set_saliency_params.assert_not_called()
    panel.stage_saliency_params.assert_called_once_with(
        {"SmoothGrad": {"nt_samples": 5}},
        publication_generation=29,
        run_identity=run_identity,
        model_name="EEGNet",
    )
    mock_warning.assert_not_called()


def test_sidebar_set_saliency_stages_params_without_starting_compute(
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
            return_value=MagicMock(
                failed=False,
                diagnostics={"payload_type": "saliency_summary", "params": None},
            ),
        ) as mock_execute,
    ):
        mock_dialog.return_value.exec.return_value = True
        mock_dialog.return_value.get_result.return_value = {"method": "gradient"}
        outcome = sidebar.set_saliency()

    assert outcome.status is InteractionStatus.ACCEPTED
    command = mock_execute.call_args.args[1]
    assert isinstance(command, SaliencyCommand)
    assert command.params is None
    assert mock_execute.call_count == 1
    mock_panel.stage_saliency_params.assert_called_once_with({"method": "gradient"})
    mock_panel.controller.set_saliency_params.assert_not_called()
    mock_panel.on_update.assert_not_called()
    mock_panel.mark_refresh_dirty.assert_not_called()
    mock_panel.update_info.assert_not_called()


def test_sidebar_set_saliency_uses_query_defaults_before_stale_controller(
    mock_panel,
    qtbot,
):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)
    mock_panel.controller.get_saliency_params.return_value = {
        "stale": {"nt_samples": 99},
    }
    query_result = MagicMock(
        failed=False,
        diagnostics={
            "payload_type": "saliency_summary",
            "params": {"SmoothGrad": {"nt_samples": 4}},
        },
    )
    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command",
            return_value=query_result,
        ) as mock_execute,
    ):
        mock_dialog.return_value.exec.return_value = True
        mock_dialog.return_value.get_result.return_value = {
            "SmoothGrad": {"nt_samples": 5},
        }

        sidebar.set_saliency()

    mock_panel.controller.get_saliency_params.assert_not_called()
    mock_dialog.assert_called_once_with(
        sidebar,
        {"SmoothGrad": {"nt_samples": 4}},
    )
    first_command = mock_execute.call_args.args[1]
    assert isinstance(first_command, SaliencyCommand)
    assert first_command.params is None
    assert mock_execute.call_count == 1
    mock_panel.stage_saliency_params.assert_called_once_with(
        {"SmoothGrad": {"nt_samples": 5}}
    )
    mock_panel.controller.set_saliency_params.assert_not_called()


def test_sidebar_set_saliency_binds_reviewed_generation_and_selected_run(
    mock_panel,
    qtbot,
):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)
    capability = CommandCapability(command_name="saliency", enabled=True)
    run_identity = SaliencyRunIdentity(
        plan=SaliencyPlanIdentity(plan_index=1),
        run_index=2,
    )
    query_result = MagicMock(
        failed=False,
        diagnostics={
            "payload_type": "saliency_summary",
            "params": {"SmoothGrad": {"nt_samples": 4}},
        },
    )
    reviewed_context = CommandReviewContext(
        capability=capability,
        publication_generation=41,
    )
    mock_panel.saliency_settings_target.return_value = (
        41,
        run_identity,
        "EEGNet",
    )
    mock_panel.stage_saliency_params.return_value = True

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "get_command_review_context",
            return_value=reviewed_context,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "execute_application_command",
            return_value=query_result,
        ) as mock_execute,
    ):
        mock_dialog.return_value.exec.return_value = True
        mock_dialog.return_value.get_result.return_value = {
            "SmoothGrad": {"nt_samples": 5},
        }

        outcome = sidebar.set_saliency()

    assert outcome.status is InteractionStatus.ACCEPTED
    assert mock_execute.call_args.kwargs["expected_publication_generation"] == 41
    mock_panel.stage_saliency_params.assert_called_once_with(
        {"SmoothGrad": {"nt_samples": 5}},
        publication_generation=41,
        run_identity=run_identity,
        model_name="EEGNet",
    )


def test_sidebar_set_saliency_surfaces_selection_change_while_dialog_is_open(
    mock_panel,
    qtbot,
):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)
    capability = CommandCapability(command_name="saliency", enabled=True)
    run_identity = SaliencyRunIdentity(
        plan=SaliencyPlanIdentity(plan_index=0),
        run_index=0,
    )
    review_context = CommandReviewContext(
        capability=capability,
        publication_generation=17,
    )
    mock_panel.saliency_settings_target.return_value = (
        17,
        run_identity,
        "EEGNet",
    )
    mock_panel.stage_saliency_params.return_value = False
    query_result = MagicMock(
        failed=False,
        diagnostics={"payload_type": "saliency_summary", "params": {}},
    )

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "get_command_review_context",
            return_value=review_context,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "execute_application_command",
            return_value=query_result,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.show_warning"
        ) as mock_warning,
    ):
        mock_dialog.return_value.exec.return_value = True
        mock_dialog.return_value.get_result.return_value = {
            "SmoothGrad": {"nt_samples": 5},
        }

        outcome = sidebar.set_saliency()

    assert outcome.status is InteractionStatus.BLOCKED
    assert mock_warning.call_args.args[1] == "Review Saliency Settings Again"
    assert "selected run changed" in mock_warning.call_args.args[2]


@pytest.mark.parametrize(
    "review_context",
    [
        pytest.param(None, id="saliency-missing-review"),
        pytest.param(
            SimpleNamespace(capability=None, publication_generation=52),
            id="saliency-missing-capability",
        ),
    ],
)
def test_visualization_actions_fail_before_command_or_dialog_without_product_review(
    qtbot,
    review_context,
):
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    qtbot.addWidget(main_window)
    panel = MagicMock()
    panel.controller = MagicMock()
    panel.main_window = main_window
    sidebar = ControlSidebar(panel)
    qtbot.addWidget(sidebar)
    enabled = CommandCapability(command_name="saliency", enabled=True)

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "get_command_review_context",
            return_value=review_context,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.get_command_capability",
            return_value=enabled,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar."
            "execute_application_command",
        ) as execute,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog",
        ) as saliency_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.show_warning",
        ) as warning,
    ):
        outcome = sidebar.set_saliency()

    assert outcome.status is InteractionStatus.BLOCKED
    execute.assert_not_called()
    saliency_dialog.assert_not_called()
    warning.assert_called_once()
