"""Real Qt surfaces; synthetic signals isolate only the expensive LLM producer."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from scripts.dev.assistant_pilot_fixture import prepare_fixture
from scripts.dev.assistant_pilot_ui import PilotUiDriver
from XBrainLab.backend.application import CommandName
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationRisk,
)
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
)
from XBrainLab.llm.agent.ui_handoff import WorkflowUiHandoffRequest
from XBrainLab.ui.chat.action_card import AssistantConfirmationCard
from XBrainLab.ui.components.agent_manager import AgentManager
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycle,
)
from XBrainLab.ui.components.modal_presentation import (
    AlertSeverity,
    ModalAlertDialog,
)
from XBrainLab.ui.main_window import MainWindow


class Signals(QObject):
    workflow_ui_handoff_requested = pyqtSignal(object)
    confirmation_requested = pyqtSignal(object)
    panel_navigation_requested = pyqtSignal(object)


@pytest.fixture
def host(qtbot):
    def factory(window, study, *, application_service):
        runtime = AssistantRuntimeLifecycle(
            study, controller_factory=lambda _: None, parent=window
        )
        return AgentManager(
            window,
            study,
            application_service=application_service,
            runtime_lifecycle=runtime,
        )

    window = MainWindow(Study(), agent_manager_factory=factory)
    qtbot.addWidget(window)
    window.show()
    window.init_agent()
    yield window, window.agent_manager
    window.close()


def test_real_import_modal_ready_capture_then_cancel(
    host, qtbot, tmp_path, allow_real_modals
):
    window, manager = host
    driver = PilotUiDriver(window, manager, tmp_path / "screens")
    signals = Signals()
    driver.attach(signals)  # Before the product modal slot is connected.
    resolutions = []
    signals.workflow_ui_handoff_requested.connect(
        lambda request: resolutions.append(
            manager._workflow_ui_handoff_host.open(request)
        )
    )
    request = WorkflowUiHandoffRequest.for_decision(CommandName.SCAN_SOURCE)

    def watchdog():
        modal = QApplication.activeModalWidget()
        if isinstance(modal, QDialog):
            modal.reject()

    timer = QTimer(window)
    timer.setSingleShot(True)
    timer.timeout.connect(watchdog)
    timer.start(3000)
    QTimer.singleShot(0, lambda: signals.workflow_ui_handoff_requested.emit(request))
    qtbot.waitUntil(lambda: bool(resolutions), timeout=10000)
    snapshot = driver.snapshot()
    timer.stop()
    ready = [event for event in snapshot["events"] if event["kind"] == "dialog_ready"]
    assert len(ready) == 1 and ready[0]["request_id"] == request.request_id
    assert ready[0]["route"] == "data_import_dialog"
    assert Path(ready[0]["screenshot"]).is_file()
    assert resolutions[0].status.value == "cancelled"
    assert not window.study.loaded_data_list
    assert not snapshot["issues"]
    assert snapshot["events"][-1]["action"] == "reject_dialog"
    driver.close()


def test_unexpected_message_is_recorded_and_rejected_never_accepted(
    host, qtbot, tmp_path, allow_real_modals
):
    window, manager = host
    driver = PilotUiDriver(window, manager, tmp_path / "screens")
    signals = Signals()
    driver.attach(signals)
    box = QMessageBox(
        QMessageBox.Icon.Warning, "Unexpected", "Do not approve", parent=window
    )
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    done = []
    signals.workflow_ui_handoff_requested.connect(lambda _: done.append(box.exec()))
    QTimer.singleShot(
        0,
        lambda: signals.workflow_ui_handoff_requested.emit(
            WorkflowUiHandoffRequest.for_decision(CommandName.SCAN_SOURCE)
        ),
    )
    qtbot.waitUntil(lambda: bool(done), timeout=10000)
    assert done[0] != QMessageBox.StandardButton.Yes
    assert "unexpected_dialog" in driver.snapshot()["issues"]
    assert any(
        event["kind"] == "unexpected_dialog" for event in driver.snapshot()["events"]
    )
    assert not any(
        event["kind"] == "dialog_ready" for event in driver.snapshot()["events"]
    )
    driver.close()


def test_known_vram_notice_from_3d_navigation_is_observed_not_measurement_error(
    host, qtbot, tmp_path, allow_real_modals
):
    window, manager = host
    driver = PilotUiDriver(window, manager, tmp_path / "screens")
    signals = Signals()
    driver.attach(signals)
    done = []

    def present_notice(_request):
        dialog = ModalAlertDialog(
            severity=AlertSeverity.WARNING,
            title="VRAM Warning",
            message="Known product acknowledgement after opening the 3D view.",
            parent=window,
        )
        done.append(dialog.exec())

    signals.panel_navigation_requested.connect(present_notice)
    signals.panel_navigation_requested.emit(
        AssistantPanelNavigationRequest(AssistantPanelTarget.VISUALIZATION, "3d_plot")
    )
    qtbot.waitUntil(lambda: bool(done), timeout=10000)
    snapshot = driver.snapshot()
    notices = [
        event for event in snapshot["events"] if event["kind"] == "product_notice"
    ]
    assert len(notices) == 1
    assert notices[0]["target"] == "visualization"
    assert notices[0]["view_mode"] == "3d_plot"
    assert notices[0]["widget_class"] == "ModalAlertDialog"
    assert Path(notices[0]["screenshot"]).is_file()
    assert "unexpected_dialog" not in snapshot["issues"]
    assert any(
        event.get("kind") == "driver_action"
        and event.get("action") == "dismiss_product_notice"
        for event in snapshot["events"]
    )
    driver.close()


@pytest.mark.parametrize("allowed", [False, True])
def test_confirmation_click_uses_real_matching_card_only(
    host, qtbot, tmp_path, allowed
):
    window, manager = host
    driver = PilotUiDriver(
        window, manager, tmp_path / "screens", allow_confirmation=allowed
    )
    signals = Signals()
    driver.attach(signals)
    request = AgentConfirmationRequest(
        "normalize_data",
        "fingerprint",
        "Normalize",
        "Synthetic case",
        AgentConfirmationRisk(),
        1,
    )
    card = AssistantConfirmationCard(window)
    card.resize(500, 400)
    decisions = []
    card.decision_requested.connect(
        lambda actual, approved: decisions.append((actual, approved))
    )

    def present(actual):
        card.present(actual)
        card.show()

    signals.confirmation_requested.connect(present)
    signals.confirmation_requested.emit(request)
    qtbot.waitUntil(lambda: bool(driver.snapshot()["events"]), timeout=5000)
    qtbot.waitUntil(
        lambda: any(
            e["kind"] == "confirmation_ready" for e in driver.snapshot()["events"]
        ),
        timeout=5000,
    )
    assert decisions == ([(request, True)] if allowed else [])
    if not allowed:
        assert "confirmation_not_authorized" in driver.snapshot()["issues"]
    driver.close()
    card.close()


def test_navigation_observes_actual_panel_without_mutating_it(host, qtbot, tmp_path):
    window, manager = host
    driver = PilotUiDriver(window, manager, tmp_path / "screens")
    signals = Signals()
    driver.attach(signals)
    signals.panel_navigation_requested.connect(manager.handle_panel_navigation)
    signals.panel_navigation_requested.emit(
        AssistantPanelNavigationRequest(AssistantPanelTarget.DATASET)
    )
    qtbot.waitUntil(
        lambda: any(e["kind"] == "panel_ready" for e in driver.snapshot()["events"]),
        timeout=10000,
    )
    assert window.stack.currentIndex() == 0
    assert not driver.snapshot()["issues"]
    driver.close()


def test_attached_driver_starts_a_fresh_case_without_reconnecting_signals(
    host, qtbot, tmp_path
):
    window, manager = host
    driver = PilotUiDriver(window, manager, tmp_path / "first")
    signals = Signals()
    driver.attach(signals)
    signals.panel_navigation_requested.connect(manager.handle_panel_navigation)
    request = AssistantPanelNavigationRequest(AssistantPanelTarget.DATASET)
    signals.panel_navigation_requested.emit(request)
    qtbot.waitUntil(
        lambda: any(e["kind"] == "panel_ready" for e in driver.snapshot()["events"]),
        timeout=10000,
    )

    driver.begin_case(tmp_path / "second")
    assert driver.snapshot() == {
        "schema": "xbrainlab.assistant_pilot_ui.v1",
        "events": [],
        "issues": [],
        "pending_count": 0,
        "screenshot_kind": "qt_widget_capture",
    }
    signals.panel_navigation_requested.emit(request)
    qtbot.waitUntil(
        lambda: any(e["kind"] == "panel_ready" for e in driver.snapshot()["events"]),
        timeout=10000,
    )
    screenshot = next(
        e["screenshot"]
        for e in driver.snapshot()["events"]
        if e["kind"] == "panel_ready"
    )
    assert Path(screenshot).parent == tmp_path / "second"
    driver.close()


def test_missing_surface_times_out_without_fabricated_readiness(host, qtbot, tmp_path):
    window, manager = host
    driver = PilotUiDriver(
        window, manager, tmp_path / "screens", readiness_timeout_seconds=0.05
    )
    signals = Signals()
    driver.attach(signals)
    signals.workflow_ui_handoff_requested.emit(
        WorkflowUiHandoffRequest.for_decision(CommandName.SCAN_SOURCE)
    )
    qtbot.waitUntil(
        lambda: "readiness_timeout" in driver.snapshot()["issues"], timeout=5000
    )
    assert not any(
        event["kind"] == "dialog_ready" for event in driver.snapshot()["events"]
    )
    driver.close()


def _fixture(stage, saliency=False):
    conditions = {"stage": stage, "session_history": "fresh_single_turn"}
    if saliency:
        conditions["saliency_results"] = (
            "already computed and renderable for current selected run"
        )
    return {
        "conditions": conditions,
        "metadata": {"fixture_id": "ui-synthetic", "workflow_stage": stage},
    }


@pytest.mark.parametrize(
    "stage,command,fields,dialog_class",
    [
        ("data_loaded", CommandName.PREPROCESS, (), "ChannelSelectionDialog"),
        ("data_loaded", CommandName.APPLY_MONTAGE, (), "PickMontageDialog"),
        ("data_loaded", CommandName.CREATE_EPOCH, (), "EpochingDialog"),
        ("epoch_ready", CommandName.CONFIGURE_DATASET_SPLIT, (), "DataSplittingDialog"),
        (
            "dataset_ready",
            CommandName.CONFIGURE_TRAINING,
            ("model",),
            "ModelSelectionDialog",
        ),
        (
            "dataset_ready",
            CommandName.CONFIGURE_TRAINING,
            ("training_options",),
            "TrainingSettingDialog",
        ),
    ],
)
def test_real_route_specific_dialogs_are_observed_and_cancelled(
    host, qtbot, tmp_path, allow_real_modals, stage, command, fields, dialog_class
):
    window, manager = host
    prepare_fixture(window.study, _fixture(stage), tmp_path / "fixture")
    driver = PilotUiDriver(
        window, manager, tmp_path / "screens", readiness_timeout_seconds=5
    )
    signals = Signals()
    driver.attach(signals)
    resolved = []
    signals.workflow_ui_handoff_requested.connect(
        lambda request: resolved.append(manager._workflow_ui_handoff_host.open(request))
    )
    request = WorkflowUiHandoffRequest.for_decision(command, decision_fields=fields)
    signals.workflow_ui_handoff_requested.emit(request)
    qtbot.waitUntil(
        lambda: any(
            e["kind"] in {"dialog_ready", "readiness_timeout", "unexpected_dialog"}
            for e in driver.snapshot()["events"]
        ),
        timeout=10000,
    )
    snapshot = driver.snapshot()
    ready = [event for event in snapshot["events"] if event["kind"] == "dialog_ready"]
    assert len(ready) == 1, snapshot
    assert ready[0]["widget_class"] == dialog_class
    assert not snapshot["issues"]
    driver.close()


def test_real_trained_visualization_requires_completed_render(host, qtbot, tmp_path):
    window, manager = host
    prepare_fixture(
        window.study, _fixture("trained", saliency=True), tmp_path / "fixture"
    )
    driver = PilotUiDriver(window, manager, tmp_path / "screens")
    signals = Signals()
    driver.attach(signals)
    signals.panel_navigation_requested.connect(manager.handle_panel_navigation)
    signals.panel_navigation_requested.emit(
        AssistantPanelNavigationRequest(
            AssistantPanelTarget.VISUALIZATION, "saliency_map"
        )
    )
    qtbot.waitUntil(
        lambda: any(
            e["kind"] in {"panel_ready", "readiness_timeout", "render_failed"}
            for e in driver.snapshot()["events"]
        ),
        timeout=20000,
    )
    snapshot = driver.snapshot()
    ready = [event for event in snapshot["events"] if event["kind"] == "panel_ready"]
    panel = window.stack.currentWidget()
    view = panel.tabs.currentWidget()
    details = {
        "snapshot": snapshot,
        "index": window.stack.currentIndex(),
        "view_properties": {
            bytes(name).decode(): view.property(bytes(name).decode())
            for name in view.dynamicPropertyNames()
        },
        "panel_rendered": window._panel_rendered_application_revision(
            4, manager.application_service.get_view_publication().revision
        ),
        "publication_generation": manager.application_service.get_view_publication().generation,
        "method": panel.method_combo.currentText(),
        "plan": panel.plan_combo.currentText(),
        "run": panel.run_combo.currentText(),
    }
    assert len(ready) == 1, details
    assert ready[0]["projection_ready"] is True
    assert ready[0]["render_ready"] is True
    assert ready[0]["render_status"] == "completed"
    assert ready[0]["operation_id"]
    assert ready[0]["ready_observed_ns"] <= ready[0]["monotonic_ns"]
    assert not snapshot["issues"]
    driver.close()


@pytest.mark.parametrize(
    "condition", ["wrong_identity", "outside_viewport", "disabled"]
)
def test_confirmation_does_not_click_wrong_or_unreachable_card(
    host, qtbot, tmp_path, condition
):
    window, manager = host
    driver = PilotUiDriver(
        window,
        manager,
        tmp_path / "screens",
        allow_confirmation=True,
        readiness_timeout_seconds=0.1,
    )
    signals = Signals()
    driver.attach(signals)
    request = AgentConfirmationRequest(
        "normalize_data",
        "fingerprint",
        "Normalize",
        "Synthetic case",
        AgentConfirmationRisk(),
        1,
    )
    card = AssistantConfirmationCard(window)
    card.resize(500, 400)
    decisions = []
    card.decision_requested.connect(
        lambda actual, approved: decisions.append((actual, approved))
    )
    shown = (
        AgentConfirmationRequest(
            "normalize_data",
            "fingerprint",
            "Normalize",
            "Synthetic case",
            AgentConfirmationRisk(),
            1,
        )
        if condition == "wrong_identity"
        else request
    )
    card.present(shown)
    card.show()
    if condition == "outside_viewport":
        card.move(100000, 100000)
    if condition == "disabled":
        card.primary_button.setEnabled(False)
    signals.confirmation_requested.emit(request)
    qtbot.waitUntil(
        lambda: "readiness_timeout" in driver.snapshot()["issues"], timeout=5000
    )
    assert not decisions
    assert not any(
        e["kind"] == "confirmation_ready" for e in driver.snapshot()["events"]
    )
    driver.close()
    card.close()
