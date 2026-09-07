"""Typed Assistant navigation against the real desktop host."""

from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
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
