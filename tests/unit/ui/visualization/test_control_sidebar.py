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
    ChangedState,
    CommandResult,
    ErrorType,
    SaliencyCommand,
    SaliencyPlanIdentity,
    SaliencyRunIdentity,
)
from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import CommandReviewContext
from XBrainLab.ui.interaction_outcome import InteractionStatus
from XBrainLab.ui.panels.visualization.control_sidebar import ControlSidebar

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def mock_main_window():
    return QMainWindow()


@pytest.fixture
def mock_panel(mock_main_window):
    panel = MagicMock()
    panel.main_window = mock_main_window
    return panel


def test_sidebar_init(mock_panel, qtbot):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)

    assert isinstance(sidebar.btn_saliency, QPushButton)
    assert sidebar.btn_saliency.text() == "Saliency Settings"
    assert "Electrode Layout" not in {
        button.text() for button in sidebar.findChildren(QPushButton)
    }


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
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    panel = MagicMock()
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
    query_result = CommandResult.success_result(
        command_name="saliency",
        message="Ready",
        state={},
        changed_state=ChangedState(),
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
    query_result = CommandResult.failure_result(
        command_name="saliency",
        message="saliency query failed",
        state={},
        changed_state=ChangedState(),
        error_type=ErrorType.VISUALIZATION,
        recoverable=False,
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
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    panel = MagicMock()
    panel.main_window = main_window
    sidebar = ControlSidebar(panel)
    qtbot.addWidget(sidebar)
    query_result = CommandResult.success_result(
        command_name="saliency",
        message="Ready",
        state={},
        changed_state=ChangedState(),
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


def test_sidebar_set_saliency_refuses_missing_product_review(qtbot):
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    panel = MagicMock()
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


def test_sidebar_set_saliency_stages_for_real_study(qtbot):
    main_window = QMainWindow()
    cast(Any, main_window).study = Study()
    panel = MagicMock()
    panel.main_window = main_window
    sidebar = ControlSidebar(panel)
    qtbot.addWidget(sidebar)
    query_result = CommandResult.success_result(
        command_name="saliency",
        message="Ready",
        state={},
        changed_state=ChangedState(),
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

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as mock_dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command",
            return_value=CommandResult.success_result(
                command_name="saliency",
                message="Ready",
                state={},
                changed_state=ChangedState(),
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
    mock_panel.on_update.assert_not_called()
    mock_panel.mark_refresh_dirty.assert_not_called()
    mock_panel.update_info.assert_not_called()


def test_sidebar_set_saliency_uses_query_defaults(
    mock_panel,
    qtbot,
):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)
    query_result = CommandResult.success_result(
        command_name="saliency",
        message="Ready",
        state={},
        changed_state=ChangedState(),
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


@pytest.mark.parametrize("query_available", [True, False])
def test_sidebar_preserves_pending_settings_before_query_defaults(
    mock_panel, qtbot, query_available
):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)
    pending = {"SmoothGrad": {"nt_samples": 8}}
    mock_panel.pending_saliency_params = pending
    query = CommandResult.success_result(
        command_name="saliency",
        message="Ready",
        state={},
        changed_state=ChangedState(),
        diagnostics={"payload_type": "saliency_summary", "params": {}},
    )
    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command",
            return_value=query if query_available else None,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as dialog,
    ):
        dialog.return_value.exec.return_value = False
        outcome = sidebar.set_saliency()
    dialog.assert_called_once_with(sidebar, pending)
    assert outcome.status is InteractionStatus.CANCELLED
    mock_panel.stage_saliency_params.assert_not_called()


def test_sidebar_missing_query_and_pending_settings_fails_closed(mock_panel, qtbot):
    sidebar = ControlSidebar(mock_panel)
    qtbot.addWidget(sidebar)
    mock_panel.pending_saliency_params = None
    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.execute_application_command",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
        ) as dialog,
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.show_warning"
        ) as warning,
    ):
        outcome = sidebar.set_saliency()
    assert outcome.status is InteractionStatus.BLOCKED
    dialog.assert_not_called()
    mock_panel.stage_saliency_params.assert_not_called()
    warning.assert_called_once_with(sidebar, "Saliency blocked", outcome.message)


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
    query_result = CommandResult.success_result(
        command_name="saliency",
        message="Ready",
        state={},
        changed_state=ChangedState(),
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
    query_result = CommandResult.success_result(
        command_name="saliency",
        message="Ready",
        state={},
        changed_state=ChangedState(),
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
