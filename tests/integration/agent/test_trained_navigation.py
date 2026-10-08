"""Real trained-state Assistant routes, independent of research observers.

Only inference/RAG are isolated by the runtime harness. CPU training, Commands,
turn correlation, panel materialization and 2D saliency rendering remain real.
Native 3D frames remain covered by test_saliency_compute_entrypoints.py.
"""

import json

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication

from tests.integration.agent.runtime_workflow_support import start_cpu_training
from tests.integration.assistant_runtime.test_lifecycle import (
    _release_initial_load,
    _runtime_harness,
    _send_request,
)
from XBrainLab.backend.application import SaliencyCommand, get_application_service
from XBrainLab.backend.training_state_contract import TrainingOutcomeState
from XBrainLab.ui.components.modal_presentation import ModalAlertDialog
from XBrainLab.ui.qt_settings import application_settings

_TIMEOUT_MS = 20_000


@pytest.fixture
def trained_runtime(qtbot, monkeypatch, tmp_path):
    with _runtime_harness(
        qtbot, monkeypatch, use_real_workflow_router=True, use_real_main_window=True
    ) as harness:
        _release_initial_load(qtbot, harness)
        service = get_application_service(harness.study)
        operation_id = start_cpu_training(harness.study, tmp_path)
        try:
            qtbot.waitUntil(
                lambda: service.get_owned_operation(operation_id).phase.terminal
                and service.training.wait_until_restart_safe(timeout=0),
                timeout=_TIMEOUT_MS,
            )
            assert service.training_runtime.terminal_outcome().state is (
                TrainingOutcomeState.COMPLETED
            )
            assert service.get_state().training.finished_run_count == 1
            harness.engine.generation_release.set()
            yield harness, service
        finally:
            if not service.get_owned_operation(operation_id).phase.terminal:
                service.cancel_owned_operation(operation_id)
            qtbot.waitUntil(
                lambda: service.wait_for_background_tasks(timeout=0),
                timeout=_TIMEOUT_MS,
            )


def _navigate(qtbot, harness, target, panel_index, view_mode=None):
    parameters = {"panel_name": target}
    if view_mode:
        parameters["view_mode"] = view_mode
    harness.engine.generation_output = json.dumps(
        {"tool_name": "switch_panel", "parameters": parameters}
    )
    terminals = QSignalSpy(harness.runtime.turn_finished)
    submissions = QSignalSpy(harness.runtime.dispatcher.input_requested)
    routes = QSignalSpy(harness.controller.panel_navigation_requested)
    commands = QSignalSpy(harness.controller.application_command_completed)
    _send_request(harness, f"Open {view_mode or target}.")
    qtbot.waitUntil(lambda: len(terminals) == 1, timeout=_TIMEOUT_MS)
    assert len(submissions) == len(routes) == 1
    assert terminals[0][0].outcome == "completed"
    assert terminals[0][0].correlation == submissions[0][0].correlation
    assert routes[0][0].correlation == submissions[0][0].correlation
    assert routes[0][0].target.value == target
    assert not commands  # Navigation does not mutate the workflow.
    assert harness.main_window.stack.currentIndex() == panel_index
    panel = harness.main_window.stack.currentWidget()
    assert panel.isVisibleTo(harness.main_window)
    publication = harness.manager.application_service.get_view_publication()
    qtbot.waitUntil(
        lambda: harness.main_window._panel_rendered_application_revision(
            panel_index, publication.revision
        ),
        timeout=_TIMEOUT_MS,
    )
    return panel


def test_trained_panel_routes_materialize_and_complete_the_requested_turn(
    qtbot, trained_runtime
):
    harness, service = trained_runtime
    for index, target in enumerate(("dataset", "preprocess", "training", "evaluation")):
        _navigate(qtbot, harness, target, index)
    assert harness.engine.generation_calls == 4
    assert service.get_state().training.finished_run_count == 1


@pytest.mark.parametrize("computed", [False, True])
def test_visualization_navigation_distinguishes_missing_and_rendered_saliency(
    qtbot, trained_runtime, computed, allow_real_modals
):
    harness, service = trained_runtime
    if computed:
        command = SaliencyCommand(method="Gradient", params={})
        operation = service.begin_owned_operation(command)
        result = service.execute(command, operation_id=operation.operation_id)
        assert result.ok, result.message
        qtbot.waitUntil(
            lambda: service.get_owned_operation(operation.operation_id).phase.terminal,
            timeout=_TIMEOUT_MS,
        )
        assert service.get_owned_operation(operation.operation_id).phase.value == (
            "completed"
        )
    assert service.get_state().visualization.saliency_available is computed
    views = ["saliency_map", "spectrogram", "topographic_map"]
    if not computed:
        views.append("3d_plot")
    settings = application_settings()
    settings.setValue("warnings/suppress_local_assistant_3d", False)
    notices = []

    def acknowledge_gpu_notice():
        modal = QApplication.activeModalWidget()
        if (
            isinstance(modal, ModalAlertDialog)
            and modal.windowTitle() == "GPU Memory Usage"
        ):
            notices.append(modal.windowTitle())
            modal.acknowledge_button.click()

    timer = QTimer(harness.main_window)
    timer.timeout.connect(acknowledge_gpu_notice)
    timer.start(20)
    try:
        for index, view in enumerate(views):
            panel = _navigate(qtbot, harness, "visualization", 4, view)
            assert panel.tabs.currentIndex() == index
            widget = panel.tabs.currentWidget()
            assert widget.isVisibleTo(panel)
            if computed:
                qtbot.waitUntil(
                    lambda view=widget: view.property("renderStatus") == "completed",
                    timeout=_TIMEOUT_MS,
                )
                summary = widget.property("saliencyNumericSummary")
                assert summary["finite_count"] > 0
                assert summary["nonfinite_count"] == 0
            else:
                assert widget.property("renderStatus") != "completed"
                assert panel.saliency_action_bar.isVisible()
                assert panel.compute_saliency_btn.isEnabled()
            # A missing plot or a completed render must not strand the next turn.
            _navigate(qtbot, harness, "dataset", 0)
        assert notices == ([] if computed else ["GPU Memory Usage"])
        assert not settings.value("warnings/suppress_local_assistant_3d", type=bool)
        assert harness.engine.generation_calls == 2 * len(views)
    finally:
        timer.stop()
