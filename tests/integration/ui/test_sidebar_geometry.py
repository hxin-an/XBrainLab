"""Responsive geometry checks for the five workflow sidebars."""

from __future__ import annotations

from itertools import pairwise
from typing import Any, cast

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


def _assert_evaluation_info_is_reachable(panel, qtbot) -> None:
    panel._update_responsive_layout()
    if panel._info_in_bottom_tabs:
        tabs = panel.chart_tabs if panel._details_in_chart_tabs else panel.bottom_tabs
        info_index = tabs.indexOf(panel.info_tab)
        assert info_index >= 0
        tabs.setCurrentIndex(info_index)
        qtbot.wait(0)

        scroll_area = panel.info_tab_scroll
        assert panel.info_panel.parentWidget() is scroll_area.content
        if not scroll_area.isVisibleTo(panel):
            assert panel.plot_stack.currentWidget() is panel.no_data_label
            return
        scroll_area.ensureWidgetVisible(panel.info_panel, 0, 8)
        qtbot.wait(0)
        info_rect = _widget_rect_in(panel.info_panel, scroll_area.viewport())
        assert info_rect.intersects(scroll_area.viewport().rect())
        return

    sidebar_rect = _widget_rect_in(panel.right_panel, panel)
    assert panel.rect().contains(sidebar_rect)
    info_rect = _widget_rect_in(panel.info_panel, panel.right_panel)
    assert panel.right_panel.rect().contains(info_rect)


@pytest.mark.parametrize(("width", "height"), TARGET_WINDOW_SIZES)
def test_five_panel_sidebars_are_responsive_and_actions_remain_reachable(
    qtbot,
    width: int,
    height: int,
):
    window = MainWindow(Study())
    qtbot.addWidget(window)
    cast(Any, window)._recover_unusable_window_geometry_if_alive = lambda _label: None
    window.showNormal()
    window.resize(width, height)
    window.show()
    qtbot.waitUntil(
        lambda: window.size().width() == width and window.size().height() == height,
        timeout=2000,
    )

    for index in range(5):
        ready_panels = []
        window.switch_page(index, on_ready=ready_panels.append)
        qtbot.waitUntil(
            lambda panels=ready_panels: len(panels) == 1,
            timeout=5_000,
        )
        qtbot.wait(0)

        panel = ready_panels[0]
        assert panel is not None
        if index == 3:
            _assert_evaluation_info_is_reachable(panel, qtbot)
            continue

        sidebar = panel.sidebar
        sidebar_rect = _widget_rect_in(sidebar, panel)
        assert panel.rect().contains(sidebar_rect)

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
        groups = [group for group in groups if group.isVisibleTo(scroll_area.content)]
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

        # A compact sidebar may fit without scrolling. The product contract is
        # that every visible action remains reachable; requiring overflow at a
        # particular shell height would reject a better compact layout.
