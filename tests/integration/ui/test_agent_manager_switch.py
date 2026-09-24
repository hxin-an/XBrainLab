"""Typed Assistant navigation against the real desktop host."""

import pytest
from PyQt6.QtCore import QThread, pyqtSlot

from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
)
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycleState,
)


@pytest.mark.parametrize("cancel_before_completion", [True, False])
def test_navigation_completion_ignores_cancelled_turn_but_reports_live_rejection(
    qtbot, test_app, monkeypatch, cancel_before_completion
):
    test_app.init_agent()
    manager = test_app.agent_manager
    assert manager is not None
    runtime = manager.assistant_runtime
    callbacks = []
    notices = []
    terminals = []
    monkeypatch.setattr(
        manager,
        "_open_assistant_panel_target",
        lambda _target, *, view_mode, on_terminal: callbacks.append(on_terminal),
    )
    monkeypatch.setattr(manager, "_show_low_priority_notice", notices.append)
    try:
        assert runtime.start_diagnostics()
        controller = manager.agent_controller
        assert controller is not None
        controller.turn_finished.connect(terminals.append)
        manager._handle_debug_tool_requested(
            "switch_panel",
            {"panel_name": "visualization", "view_mode": "3d_plot"},
            False,
            "",
        )
        qtbot.waitUntil(lambda: len(callbacks) == 1)
        if cancel_before_completion:
            manager.stop_generation()
            qtbot.waitUntil(lambda: len(terminals) == 1 and not runtime.turn_in_flight)
            assert terminals[0].outcome == "cancelled"
            assert not manager.chat_controller.is_processing
        else:
            # Fail only the external transport: the current turn still owns its result.
            monkeypatch.setattr(
                runtime.dispatcher, "resolve_panel_navigation", lambda *_a, **_k: False
            )

        callbacks[0](True)

        if cancel_before_completion:
            assert notices == []
            assert len(terminals) == 1
        else:
            assert notices == [runtime._DELIVERY_FAILURE_MESSAGE]
            assert runtime.turn_in_flight
    finally:
        manager.close()
        qtbot.waitUntil(
            lambda: runtime.state is AssistantRuntimeLifecycleState.CLOSED,
            timeout=10_000,
        )


def test_typed_panel_navigation_with_view_mode_logic(qtbot, test_app):
    test_app.init_agent()
    manager = test_app.agent_manager
    assert manager is not None

    manager.handle_panel_navigation(
        AssistantPanelNavigationRequest(
            AssistantPanelTarget.VISUALIZATION,
            view_mode="3d_plot",
        )
    )

    qtbot.waitUntil(
        lambda: 4 in test_app._loaded_panel_indices
        and test_app.visualization_panel.tabs.currentIndex() == 3,
        timeout=5_000,
    )
    assert test_app.stack.currentWidget() is test_app.visualization_panel
    assert test_app.visualization_panel.tabs.tabText(3) == "3D Plot"


def test_diagnostic_panel_navigation_finishes_real_controller_metrics(
    qtbot, test_app, monkeypatch
):
    resolution_threads = []
    resolved_requests = []

    class ObservedController(LLMController):
        @pyqtSlot(object, bool)
        def on_panel_navigation_resolved(self, request, success):
            resolution_threads.append(QThread.currentThread())
            resolved_requests.append(request)
            super().on_panel_navigation_resolved(request, success=success)

    monkeypatch.setattr(
        "XBrainLab.ui.components.agent_manager.LLMController", ObservedController
    )
    test_app.init_agent()
    manager = test_app.agent_manager
    assert manager is not None
    runtime = manager.assistant_runtime
    controller = None
    try:
        assert runtime.start_diagnostics()
        controller = manager.agent_controller
        assert controller is not None
        terminals = []
        controller.turn_finished.connect(terminals.append)
        turn = controller.metrics.start_turn()

        manager._handle_debug_tool_requested(
            "switch_panel",
            {"panel_name": "visualization", "view_mode": "3d_plot"},
            False,
            "",
        )

        qtbot.waitUntil(lambda: controller.metrics.current_turn is None, timeout=5_000)
        assert controller.metrics.last_completed_turn is turn
        qtbot.waitUntil(lambda: bool(terminals), timeout=5_000)
        assert len(terminals) == 1
        assert terminals[0].outcome == "completed"
        assert resolution_threads == [runtime.dispatcher.command_thread]
        assert resolution_threads[0] is not test_app.thread()
        qtbot.waitUntil(lambda: not runtime.turn_in_flight, timeout=5_000)
        assert not runtime.resolve_panel_navigation(
            resolved_requests[0], success=True
        ).accepted
        qtbot.wait(20)
        assert len(terminals) == 1
        assert len(resolution_threads) == 1
    finally:
        manager.close()
        qtbot.waitUntil(
            lambda: runtime.state is AssistantRuntimeLifecycleState.CLOSED,
            timeout=10_000,
        )
        if controller is not None:
            qtbot.waitUntil(
                lambda: not controller.worker_thread.isRunning(),
                timeout=10_000,
            )
