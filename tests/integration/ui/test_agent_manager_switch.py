"""Typed Assistant navigation against the real desktop host."""

from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
)
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycleState,
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


def test_diagnostic_panel_navigation_finishes_real_controller_metrics(qtbot, test_app):
    test_app.init_agent()
    manager = test_app.agent_manager
    assert manager is not None
    runtime = manager.assistant_runtime
    controller = None
    try:
        assert runtime.start_diagnostics()
        controller = manager.agent_controller
        assert controller is not None
        turn = controller.metrics.start_turn()

        manager._handle_debug_tool_requested(
            "switch_panel",
            {"panel_name": "visualization", "view_mode": "3d_plot"},
            False,
            "",
        )

        qtbot.waitUntil(lambda: controller.metrics.current_turn is None, timeout=5_000)
        assert controller.metrics.last_completed_turn is turn
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
