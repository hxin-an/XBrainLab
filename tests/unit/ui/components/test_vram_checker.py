"""Tests for VRAMConflictChecker."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QTabWidget,
    QWidget,
)

from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.ui.components.modal_presentation import AlertSeverity
from XBrainLab.ui.components.vram_checker import VRAMConflictChecker


@pytest.fixture()
def widget_main_window(qtbot):
    main_window = QMainWindow()
    stack = QStackedWidget(main_window)
    # The visible workspace order is intentionally fixed here rather than
    # derived from the implementation constants being consolidated.
    for _ in range(4):
        stack.addWidget(QWidget(stack))

    visualization_panel = QWidget(stack)
    tabs = QTabWidget(visualization_panel)
    for label in (
        "Saliency Map",
        "Spectrogram",
        "Topographic Map",
        "3D Plot",
    ):
        tabs.addTab(QWidget(tabs), label)
    stack.addWidget(visualization_panel)
    stack.setCurrentIndex(4)

    main_window.setCentralWidget(stack)
    main_window.stack = stack
    main_window.visualization_panel = visualization_panel
    visualization_panel.tabs = tabs
    qtbot.addWidget(main_window)
    main_window.show()
    return main_window


@pytest.fixture()
def local_runtime_snapshot():
    return AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY,
        initialized=True,
        backend_mode="local",
    )


@pytest.fixture()
def widget_checker(widget_main_window, local_runtime_snapshot):
    return VRAMConflictChecker(widget_main_window, lambda: local_runtime_snapshot)


def test_real_widgets_warn_for_initialized_local_mode_with_active_3d(
    widget_main_window,
    widget_checker,
):
    widget_main_window.visualization_panel.tabs.setCurrentIndex(3)
    assert not widget_main_window.visualization_panel.isHidden()
    assert widget_main_window.stack.currentIndex() == 4

    with patch("XBrainLab.ui.components.vram_checker.show_alert") as show_alert:
        widget_checker.check()

    show_alert.assert_called_once_with(
        widget_main_window,
        severity=AlertSeverity.WARNING,
        title="VRAM Warning",
        message=(
            "This requires significant VRAM (Video Memory). "
            "If you experience crashes or lag, please close the 3D view "
            "before using the assistant."
        ),
    )


@pytest.mark.parametrize(
    ("tab_index", "panel_hidden", "stack_index", "initialized", "backend_mode"),
    [
        (0, False, 4, True, "local"),
        (3, True, 4, True, "local"),
        (3, False, 0, True, "local"),
        (3, False, 4, True, "remote"),
        (3, False, 4, False, "local"),
    ],
    ids=("other-tab", "hidden", "other-workspace", "nonlocal", "not-initialized"),
)
def test_real_widgets_skip_warning_outside_active_local_3d_conditions(
    widget_main_window,
    tab_index,
    panel_hidden,
    stack_index,
    initialized,
    backend_mode,
):
    widget_main_window.visualization_panel.tabs.setCurrentIndex(tab_index)
    widget_main_window.stack.setCurrentIndex(stack_index)
    if panel_hidden:
        widget_main_window.visualization_panel.hide()
    snapshot = AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY
        if initialized
        else AssistantRuntimePhase.IDLE,
        initialized=initialized,
        backend_mode=backend_mode,
    )
    checker = VRAMConflictChecker(widget_main_window, lambda: snapshot)

    with patch("XBrainLab.ui.components.vram_checker.show_alert") as show_alert:
        checker.check()

    assert widget_main_window.visualization_panel.isHidden() is (
        panel_hidden or stack_index != 4
    )
    assert widget_main_window.stack.currentIndex() == stack_index
    show_alert.assert_not_called()


def test_real_widgets_warn_when_switching_to_local_with_3d_visible(
    widget_main_window,
):
    widget_main_window.visualization_panel.tabs.setCurrentIndex(3)
    remote_snapshot = AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY,
        initialized=True,
        backend_mode="remote",
    )
    checker = VRAMConflictChecker(widget_main_window, lambda: remote_snapshot)

    with patch("XBrainLab.ui.components.vram_checker.show_alert") as show_alert:
        checker.check(switching_to_local=True)

    show_alert.assert_called_once()


def test_real_widgets_warn_when_switching_to_3d_with_local_mode(
    widget_main_window,
    widget_checker,
):
    widget_main_window.visualization_panel.tabs.setCurrentIndex(0)

    with patch("XBrainLab.ui.components.vram_checker.show_alert") as show_alert:
        widget_checker.on_viz_tab_changed(0)
        show_alert.assert_not_called()
        widget_checker.on_viz_tab_changed(3)

    show_alert.assert_called_once()


def test_real_widgets_skip_warning_when_runtime_snapshot_is_unavailable(
    widget_main_window,
):
    widget_main_window.visualization_panel.tabs.setCurrentIndex(3)

    def unavailable_snapshot():
        raise RuntimeError("runtime not ready")

    checker = VRAMConflictChecker(widget_main_window, unavailable_snapshot)
    with patch("XBrainLab.ui.components.vram_checker.show_alert") as show_alert:
        checker.check()

    show_alert.assert_not_called()


def test_real_widgets_skip_warning_for_lazy_visualization_placeholder(
    widget_main_window,
    local_runtime_snapshot,
):
    lazy_placeholder = QWidget(widget_main_window)
    widget_main_window.visualization_panel = lazy_placeholder
    checker = VRAMConflictChecker(widget_main_window, lambda: local_runtime_snapshot)

    with patch("XBrainLab.ui.components.vram_checker.show_alert") as show_alert:
        checker.check()

    show_alert.assert_not_called()
