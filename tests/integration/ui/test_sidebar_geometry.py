"""Responsive geometry checks for the five workflow sidebars."""

from __future__ import annotations

from itertools import pairwise

import pytest
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QGroupBox,
    QPushButton,
    QWidget,
)

from XBrainLab.backend.study import Study
from XBrainLab.ui.main_window import MainWindow

TARGET_WINDOW_SIZES = ((760, 520), (960, 620), (1280, 800))


def _widget_rect_in(widget: QWidget, ancestor: QWidget) -> QRect:
    return QRect(widget.mapTo(ancestor, QPoint(0, 0)), widget.size())


def _assert_no_overlap(widgets: list[QWidget], ancestor: QWidget) -> None:
    rects = sorted(
        (_widget_rect_in(widget, ancestor) for widget in widgets),
        key=lambda rect: rect.top(),
    )
    for previous, current in pairwise(rects):
        assert previous.bottom() < current.top()


@pytest.mark.parametrize(("width", "height"), TARGET_WINDOW_SIZES)
def test_five_panel_sidebars_are_responsive_and_actions_remain_reachable(
    qtbot,
    width: int,
    height: int,
):
    window = MainWindow(Study())
    qtbot.addWidget(window)
    window._recover_unusable_window_geometry_if_alive = lambda _label: None
    window.showNormal()
    window.resize(width, height)
    window.show()
    qtbot.waitUntil(
        lambda: window.size().width() == width and window.size().height() == height,
        timeout=2000,
    )

    for index in range(5):
        window.switch_page(index)
        qtbot.wait(0)

        panel = window.stack.currentWidget()
        assert panel is not None
        is_action_sidebar = index != 3
        sidebar = (
            panel.sidebar
            if is_action_sidebar
            else window.evaluation_panel.info_panel.parentWidget()
        )
        sidebar_rect = _widget_rect_in(sidebar, panel)
        assert panel.rect().contains(sidebar_rect)

        if not is_action_sidebar:
            info_rect = _widget_rect_in(window.evaluation_panel.info_panel, sidebar)
            assert sidebar.rect().contains(info_rect)
            continue

        scroll_area = sidebar.scroll_area
        vertical_owners = [
            area
            for area in sidebar.findChildren(QAbstractScrollArea)
            if area.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        ]
        assert vertical_owners == [scroll_area]

        groups = scroll_area.content.findChildren(
            QGroupBox,
            options=Qt.FindChildOption.FindDirectChildrenOnly,
        )
        _assert_no_overlap(groups, scroll_area.content)

        buttons = [
            button
            for button in scroll_area.content.findChildren(QPushButton)
            if button.isVisibleTo(sidebar)
        ]
        assert buttons
        _assert_no_overlap(buttons, scroll_area.content)

        for button in buttons:
            scroll_area.ensureWidgetVisible(button, 0, 8)
            qtbot.wait(0)
            center = button.mapTo(scroll_area.viewport(), button.rect().center())
            assert scroll_area.viewport().rect().contains(center)

        if height <= 620:
            assert scroll_area.verticalScrollBar().maximum() > 0
