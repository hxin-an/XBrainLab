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

TARGET_WINDOW_SIZES = ((840, 520), (960, 620), (1280, 800))
EXPECTED_SUMMARY_LABELS = (
    "Type",
    "EEG files",
    "Subjects",
    "Sessions",
    "Epochs",
    "Events",
    "Channels",
    "Sample rate",
    "Epoch start",
    "Epoch length",
    "High pass",
    "Low pass",
    "Classes",
)


def _widget_rect_in(widget: QWidget, ancestor: QWidget) -> QRect:
    return QRect(widget.mapTo(ancestor, QPoint(0, 0)), widget.size())


def _assert_no_overlap(widgets: list[QWidget], ancestor: QWidget) -> None:
    rects = sorted(
        (_widget_rect_in(widget, ancestor) for widget in widgets),
        key=lambda rect: rect.top(),
    )
    for previous, current in pairwise(rects):
        assert previous.bottom() < current.top()


def _assert_old_summary_table_is_readable(info_panel) -> None:
    """Protect the accepted fixed two-column Data Summary presentation."""
    table = info_panel.table
    assert info_panel.title() == "Data Summary"
    assert table.isVisibleTo(info_panel)
    assert table.rowCount() == len(EXPECTED_SUMMARY_LABELS)
    assert (
        tuple(table.item(row, 0).text() for row in range(table.rowCount()))
        == EXPECTED_SUMMARY_LABELS
    )
    assert all(not table.isRowHidden(row) for row in range(table.rowCount()))
    assert table.horizontalScrollBar().maximum() == 0
    assert table.verticalScrollBar().maximum() == 0
    assert table.minimumHeight() == table.maximumHeight()
    assert info_panel.minimumHeight() == info_panel.maximumHeight()

    viewport = table.viewport()
    assert viewport is not None
    key_width = table.columnWidth(0)
    required_key_width = (
        max(
            table.fontMetrics().horizontalAdvance(label)
            for label in EXPECTED_SUMMARY_LABELS
        )
        + 8
    )
    assert key_width >= required_key_width

    first_item = table.item(0, 0)
    last_item = table.item(table.rowCount() - 1, 0)
    assert first_item is not None
    assert last_item is not None
    assert viewport.rect().contains(table.visualItemRect(first_item))
    assert viewport.rect().contains(table.visualItemRect(last_item))

    # Geometry-only checks missed an earlier regression where QTableWidget had
    # thirteen model rows but only the first row reached the rendered surface.
    # Inspect the actual viewport pixels so the handoff gate protects what a
    # user sees, not just the item model.
    pixmap = viewport.grab()
    assert not pixmap.isNull()
    image = pixmap.toImage()
    scale = pixmap.devicePixelRatio()
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        assert item is not None
        rect = table.visualItemRect(item)
        left = max(0, round((rect.left() + 2) * scale))
        right = min(image.width(), round((rect.right() - 2) * scale))
        top = max(0, round((rect.top() + 2) * scale))
        bottom = min(image.height(), round((rect.bottom() - 2) * scale))
        bright_pixels = 0
        for y in range(top, bottom):
            for x in range(left, right):
                color = image.pixelColor(x, y)
                if max(color.red(), color.green(), color.blue()) >= 110:
                    bright_pixels += 1
        assert bright_pixels >= len(item.text()) * 3, (
            f"summary row {row} was not fully painted: {item.text()!r}"
        )


def _assert_evaluation_info_is_reachable(panel, qtbot) -> None:
    panel._update_responsive_layout()
    sidebar_rect = _widget_rect_in(panel.right_panel, panel)
    assert panel.rect().contains(sidebar_rect)
    info_rect = _widget_rect_in(panel.info_panel, panel.right_panel)
    assert panel.right_panel.rect().contains(info_rect)
    assert panel.right_layout.indexOf(panel.info_panel) == 0


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

    sidebar_widths: list[int] = []
    sidebar_left_edges: list[int] = []
    summary_top_edges: list[int] = []
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
        qtbot.waitUntil(
            lambda active_panel=panel: active_panel.width() == window.stack.width(),
            timeout=2_000,
        )
        if index == 3:
            _assert_evaluation_info_is_reachable(panel, qtbot)
            _assert_old_summary_table_is_readable(panel.info_panel)
            sidebar_widths.append(panel.right_panel.width())
            sidebar_left_edges.append(panel.right_panel.x())
            summary_top_edges.append(panel.info_panel.mapTo(panel, QPoint()).y())
            continue

        sidebar = panel.sidebar
        sidebar_rect = _widget_rect_in(sidebar, panel)
        assert panel.rect().contains(sidebar_rect)
        sidebar_widths.append(sidebar.width())
        sidebar_left_edges.append(sidebar.x())

        scroll_area = sidebar.scroll_area
        assert scroll_area.content_layout.indexOf(sidebar.info_panel) == 0
        assert scroll_area.verticalScrollBar().value() == 0
        _assert_old_summary_table_is_readable(sidebar.info_panel)
        summary_top_edges.append(sidebar.info_panel.mapTo(panel, QPoint()).y())
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

    assert sidebar_widths == [260] * 5
    assert len(set(sidebar_left_edges)) == 1
    assert max(summary_top_edges) - min(summary_top_edges) <= 2

    # A compact sidebar may fit without scrolling. The product contract is
    # that every visible action remains reachable; requiring overflow at a
    # particular shell height would reject a better compact layout.
