"""Bounded real Qt routes: wrong model choices must remain measurable.

Only the model producer is absent. Navigation, fixture publication, rendering,
the product GPU notice, screenshots, and case-boundary observation are real.
These are engineering checks, not model accuracy or native desktop acceptance.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from scripts.dev.assistant_pilot_fixture import prepare_fixture
from scripts.dev.assistant_pilot_outcome import ui_measurement_issues
from scripts.dev.assistant_pilot_ui import PilotUiDriver
from tests.unit.ui.test_assistant_pilot_ui import Signals, _fixture, host
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
)
from XBrainLab.ui.components.modal_presentation import AlertSeverity, ModalAlertDialog
from XBrainLab.ui.qt_settings import application_settings

__all__ = ["host"]


@pytest.mark.parametrize(
    "target",
    [
        AssistantPanelTarget.DATASET,
        AssistantPanelTarget.PREPROCESS,
        AssistantPanelTarget.TRAINING,
        AssistantPanelTarget.EVALUATION,
    ],
)
def test_real_panel_routes_settle_without_requiring_model_correctness(
    host, qtbot, tmp_path, target
):
    window, manager = host
    prepare_fixture(window.study, _fixture("trained"), tmp_path / "fixture")
    driver = PilotUiDriver(window, manager, tmp_path / "screens")
    signals = Signals()
    driver.attach(signals)
    signals.panel_navigation_requested.connect(manager.handle_panel_navigation)
    try:
        signals.panel_navigation_requested.emit(AssistantPanelNavigationRequest(target))
        qtbot.waitUntil(
            lambda: bool(driver.snapshot()["events"])
            and driver.snapshot()["pending_count"] == 0,
            timeout=20000,
        )
        snapshot = driver.snapshot()
        ready = [e for e in snapshot["events"] if e["kind"] == "panel_ready"]
        assert len(ready) == 1, snapshot
        assert ready[0]["target"] == target.value
        assert ready[0]["projection_ready"] is True
        assert Path(ready[0]["screenshot"]).is_file()
        assert not snapshot["issues"], snapshot
    finally:
        driver.close()


@pytest.mark.parametrize("saliency", [False, True], ids=["no-saliency", "renderable"])
@pytest.mark.parametrize(
    "view_mode", ["saliency_map", "spectrogram", "topographic_map", "3d_plot"]
)
def test_real_visualization_routes_keep_success_or_failure_correlated(
    host, qtbot, tmp_path, allow_real_modals, saliency, view_mode
):
    window, manager = host
    prepare_fixture(
        window.study, _fixture("trained", saliency=saliency), tmp_path / "fixture"
    )
    # Supply the same local-runtime fact as the experiment, without loading an LLM.
    # The real checker, modal, host routing, and rendering remain unchanged.
    manager.vram_checker._get_runtime_snapshot = lambda: SimpleNamespace(
        initialized=True, backend_mode="local"
    )
    settings = application_settings()
    settings.setValue("warnings/suppress_local_assistant_3d", False)
    driver = PilotUiDriver(
        window, manager, tmp_path / "screens", readiness_timeout_seconds=5
    )
    signals = Signals()
    driver.attach(signals)
    signals.panel_navigation_requested.connect(manager.handle_panel_navigation)
    try:
        signals.panel_navigation_requested.emit(
            AssistantPanelNavigationRequest(
                AssistantPanelTarget.VISUALIZATION, view_mode
            )
        )
        qtbot.waitUntil(
            lambda: bool(driver.snapshot()["events"])
            and driver.snapshot()["pending_count"] == 0,
            timeout=20000,
        )
        snapshot = driver.snapshot()
        outcomes = [
            e
            for e in snapshot["events"]
            if e["kind"] in {"panel_ready", "readiness_timeout", "render_failed"}
        ]
        assert len(outcomes) == 1, snapshot
        outcome = outcomes[0]
        assert outcome["target"] == "visualization"
        assert outcome["view_mode"] == view_mode
        assert Path(outcome["screenshot"]).is_file()
        assert not ui_measurement_issues(snapshot), snapshot
        if saliency and view_mode != "3d_plot":
            assert outcome["kind"] == "panel_ready", snapshot
            assert outcome["render_ready"] is True
        if view_mode == "3d_plot":
            notices = [e for e in snapshot["events"] if e["kind"] == "product_notice"]
            assert len(notices) == 1, snapshot
            assert not settings.value("warnings/suppress_local_assistant_3d", type=bool)
        # A measured render failure may not leak an outstanding observation into
        # the next case. This exercises the real observer boundary after each route.
        driver.begin_case(tmp_path / "next")
        signals.panel_navigation_requested.emit(
            AssistantPanelNavigationRequest(AssistantPanelTarget.DATASET)
        )
        qtbot.waitUntil(
            lambda: any(
                e["kind"] == "panel_ready" for e in driver.snapshot()["events"]
            ),
            timeout=10000,
        )
        assert not driver.snapshot()["issues"]
        assert driver.snapshot()["pending_count"] == 0
    finally:
        driver.close()


@pytest.mark.parametrize(
    "guard", ["confirmation", "unrelated_target", "unrelated_title"]
)
def test_notice_exception_does_not_hide_other_owned_modals(
    host, qtbot, tmp_path, allow_real_modals, guard
):
    window, manager = host
    driver = PilotUiDriver(window, manager, tmp_path / "screens")
    signals = Signals()
    driver.attach(signals)
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Other warning" if guard == "unrelated_title" else "GPU Memory Usage",
        message="This is not an authorized 3D acknowledgement.",
        confirm_text="Proceed" if guard == "confirmation" else None,
        parent=window,
    )
    results = []
    signals.panel_navigation_requested.connect(lambda _: results.append(dialog.exec()))
    watchdog = QTimer(window)
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(dialog.reject)
    watchdog.start(3000)
    try:
        signals.panel_navigation_requested.emit(
            AssistantPanelNavigationRequest(
                AssistantPanelTarget.DATASET
                if guard == "unrelated_target"
                else AssistantPanelTarget.VISUALIZATION,
                None if guard == "unrelated_target" else "3d_plot",
            )
        )
        qtbot.waitUntil(lambda: bool(results), timeout=5000)
        snapshot = driver.snapshot()
        assert results == [QDialog.DialogCode.Rejected]
        assert "unexpected_dialog" in ui_measurement_issues(snapshot), snapshot
        assert not any(e["kind"] == "product_notice" for e in snapshot["events"])
        assert not any(e["kind"] == "panel_ready" for e in snapshot["events"])
    finally:
        watchdog.stop()
        driver.close()


def test_foreign_modal_is_never_dismissed_as_this_hosts_notice(host, qtbot, tmp_path):
    window, manager = host
    driver = PilotUiDriver(window, manager, tmp_path / "screens")
    signals = Signals()
    driver.attach(signals)
    other_window = QWidget()
    qtbot.addWidget(other_window)
    other_window.show()
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="GPU Memory Usage",
        message="A notice belonging to another host.",
        parent=other_window,
    )
    qtbot.addWidget(dialog)
    try:
        signals.panel_navigation_requested.emit(
            AssistantPanelNavigationRequest(
                AssistantPanelTarget.VISUALIZATION, "3d_plot"
            )
        )
        dialog.show()
        qtbot.waitUntil(lambda: QApplication.activeModalWidget() is dialog)
        qtbot.wait(100)  # Multiple actual observation timer ticks, no nested exec.
        snapshot = driver.snapshot()
        assert dialog.isVisible()
        assert snapshot["pending_count"] == 1
        assert not any(
            e["kind"] in {"product_notice", "driver_action", "panel_ready"}
            for e in snapshot["events"]
        ), snapshot
    finally:
        dialog.reject()
        driver.close()
