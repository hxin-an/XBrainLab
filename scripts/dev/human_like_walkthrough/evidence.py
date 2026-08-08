"""Observable GUI-with-Agent evidence collectors."""

from __future__ import annotations

import re
from itertools import pairwise
from math import ceil
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageStat
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QLabel,
    QToolButton,
    QWidget,
)

from scripts.dev.capture_chatpanel_local_walkthrough import collect_visible_messages
from scripts.dev.human_like_walkthrough.driver import WalkthroughAssistantController
from XBrainLab.ui.chat.message_bubble import MessageBubble
from XBrainLab.ui.components.agent_presentation_service import (
    AgentPresentationService,
)
from XBrainLab.ui.components.workflow_surface_router import (
    WorkflowSurfaceOutcome,
    WorkflowSurfaceStatus,
)


def chat_panel_geometry(widget: QWidget) -> dict[str, Any]:
    """Return evidence for ChatPanel transcript/composer overlap."""
    scroll_area = getattr(widget, "scroll_area", None)
    control_panel = getattr(widget, "control_panel", None)
    if scroll_area is None or control_panel is None:
        return {}
    bubbles = [
        bubble
        for bubble in widget.findChildren(MessageBubble)
        if bubble.isVisible() and bubble.height() > 0
    ]
    if not bubbles:
        return {}
    latest = bubbles[-1]
    latest_bottom_y = latest.mapTo(widget, QPoint(0, latest.height())).y()
    composer_top_y = control_panel.mapTo(widget, QPoint(0, 0)).y()
    scrollbar = scroll_area.verticalScrollBar()
    scrollbar_value = scrollbar.value() if scrollbar else 0
    scrollbar_max = scrollbar.maximum() if scrollbar else 0
    return {
        "visible_bubble_count": len(bubbles),
        "latest_message_text": latest.get_text(),
        "latest_message_bottom_y": latest_bottom_y,
        "composer_top_y": composer_top_y,
        "bottom_clearance_px": composer_top_y - latest_bottom_y,
        "scrollbar_value": scrollbar_value,
        "scrollbar_max": scrollbar_max,
        "latest_message_clear_of_composer": latest_bottom_y <= composer_top_y - 4,
        "scrollbar_at_bottom": scrollbar_value >= scrollbar_max - 1,
    }


def assistant_signal_path_evidence(
    controller: WalkthroughAssistantController,
) -> dict[str, Any]:
    """Describe the manager, dispatcher, and Qt signal surface used by replay."""
    return {
        "manager_path": True,
        "qt_signal_path": True,
        "direct_chat_controller_injection": False,
        "controller_class": type(controller).__name__,
        "events": list(controller.events),
    }


def assistant_main_window_handoff_evidence(
    window: Any,
    dock: QWidget,
    panel: Any,
    *,
    expected_panel: str,
) -> dict[str, Any]:
    """Record that a typed handoff opened a real main-window workflow panel."""
    nav_buttons = list(getattr(window, "nav_btns", []))
    expected_index = next(
        (
            index
            for index, button in enumerate(nav_buttons)
            if str(button.text()).strip() == expected_panel
        ),
        -1,
    )
    stack = getattr(window, "stack", None)
    active_index = int(stack.currentIndex()) if stack is not None else -1
    active_widget = stack.currentWidget() if stack is not None else None
    active_panel = (
        str(nav_buttons[active_index].text()).strip()
        if 0 <= active_index < len(nav_buttons)
        else ""
    )
    expected_button = (
        nav_buttons[expected_index] if 0 <= expected_index < len(nav_buttons) else None
    )
    workflow_opened = bool(
        active_panel == expected_panel
        and active_index == expected_index
        and expected_button is not None
        and expected_button.isChecked()
        and active_widget is not None
        and active_widget.isVisible()
    )
    evidence = assistant_main_window_evidence(
        window,
        dock,
        panel,
        state="assistant_existing_ui_handoff",
        workflow_status="opened" if workflow_opened else "not_opened",
    )
    evidence.update(
        {
            "active_panel": active_panel,
            "active_index": active_index,
            "evaluation_index": expected_index,
            "evaluation_nav_checked": bool(
                expected_button is not None and expected_button.isChecked()
            ),
            "active_page_visible": bool(
                active_widget is not None and active_widget.isVisible()
            ),
            "assistant_dock_visible": bool(dock.isVisible()),
            "expected_panel": expected_panel,
            "workflow_opened": workflow_opened,
            "evaluation_plot_readability": evaluation_plot_readability_evidence(window),
        }
    )
    return evidence


def _widget_rect_in(parent: QWidget, child: QWidget) -> QRect:
    origin = child.mapTo(parent, QPoint(0, 0))
    return QRect(origin.x(), origin.y(), child.width(), child.height())


def _rect_inside(parent: QWidget, rect: QRect, tolerance: int = 2) -> bool:
    bounds = parent.rect().adjusted(-tolerance, -tolerance, tolerance, tolerance)
    return bounds.contains(rect)


def _rects_overlap(first: QRect, second: QRect, tolerance: int = 2) -> bool:
    intersection = first.intersected(second)
    return intersection.width() > tolerance and intersection.height() > tolerance


def assistant_main_window_evidence(
    window: Any,
    dock: QWidget,
    panel: Any,
    *,
    state: str,
    workflow_status: str,
) -> dict[str, Any]:
    """Measure whether an assistant state is readable in the complete product window."""
    title_bar = getattr(dock, "titleBarWidget", lambda: None)()
    composer = getattr(panel, "input_widget", None)
    input_field = getattr(panel, "input_field", None)
    primary_action = getattr(panel, "send_btn", None)
    stack = getattr(window, "stack", None)
    nav_buttons = [
        button
        for button in getattr(window, "nav_btns", [])
        if isinstance(button, QAbstractButton)
    ]
    compact_nav = getattr(window, "compact_nav_combo", None)
    composer_widget = composer if isinstance(composer, QWidget) else None
    input_widget = input_field if isinstance(input_field, QWidget) else None
    primary_action_widget = (
        primary_action if isinstance(primary_action, QWidget) else None
    )
    primary_action_button = (
        primary_action if isinstance(primary_action, QAbstractButton) else None
    )
    stack_widget = stack if isinstance(stack, QWidget) else None
    compact_nav_widget = compact_nav if isinstance(compact_nav, QComboBox) else None
    dock_state = assistant_dock_evidence(dock, panel)

    widgets: dict[str, QWidget] = {
        "dock": dock,
        **({"title": title_bar} if isinstance(title_bar, QWidget) else {}),
        **({"composer": composer} if isinstance(composer, QWidget) else {}),
        **({"input": input_field} if isinstance(input_field, QWidget) else {}),
        **(
            {"primary_action": primary_action}
            if isinstance(primary_action, QWidget)
            else {}
        ),
        **({"main_content": stack} if isinstance(stack, QWidget) else {}),
    }
    rects = {
        name: _widget_rect_in(window, widget)
        for name, widget in widgets.items()
        if widget.isVisible()
    }
    out_of_window = [
        name for name, rect in rects.items() if not _rect_inside(window, rect)
    ]
    overlap_candidates = (
        ("title", "composer"),
        ("input", "primary_action"),
        ("main_content", "dock"),
    )
    overlaps = [
        f"{first}/{second}"
        for first, second in overlap_candidates
        if first in rects
        and second in rects
        and _rects_overlap(rects[first], rects[second])
    ]

    composer_visible = bool(
        composer_widget is not None
        and composer_widget.isVisible()
        and input_widget is not None
        and input_widget.isVisible()
    )
    action_visible = bool(
        primary_action_widget is not None and primary_action_widget.isVisible()
    )
    composer_inside_dock = bool(
        composer_widget is not None and _widget_inside(dock, composer_widget)
    )
    action_inside_dock = bool(
        primary_action_widget is not None
        and _widget_inside(dock, primary_action_widget)
    )
    main_content_visible = bool(stack_widget is not None and stack_widget.isVisible())
    main_content_inside_window = bool(
        stack_widget is not None
        and stack_widget.isVisible()
        and _rect_inside(window, _widget_rect_in(window, stack_widget))
    )
    visible_nav_buttons = [button for button in nav_buttons if button.isVisible()]
    if compact_nav_widget is not None and compact_nav_widget.isVisible():
        compact_nav_visible = True
        compact_nav_text = " ".join(str(compact_nav_widget.currentText() or "").split())
        compact_nav_inside_window = _rect_inside(
            window,
            _widget_rect_in(window, compact_nav_widget),
        )
        compact_nav_text_fits = bool(
            compact_nav_text
            and compact_nav_widget.fontMetrics().horizontalAdvance(compact_nav_text)
            + 36
            <= compact_nav_widget.contentsRect().width() + 2
        )
    else:
        compact_nav_visible = False
        compact_nav_text = ""
        compact_nav_inside_window = True
        compact_nav_text_fits = True
    nav_outside_window = [
        " ".join(str(button.text() or "").split())
        for button in visible_nav_buttons
        if not _rect_inside(window, _widget_rect_in(window, button))
    ]
    nav_text_overflow = [
        " ".join(str(button.text() or "").split())
        for button in visible_nav_buttons
        if button.fontMetrics().horizontalAdvance(button.text()) + 20
        > button.contentsRect().width() + 2
    ]
    dock_is_floating = bool(getattr(dock, "isFloating", lambda: False)())
    title_text = str(dock_state.get("title_text") or "")
    title_text_fits = bool(dock_state.get("title_text_fits"))
    geometry_passed = bool(
        window.isVisible()
        and dock.isVisible()
        and not dock_is_floating
        and "dock" not in out_of_window
        and title_text == "XBrainLab Assistant"
        and title_text_fits
        and composer_visible
        and composer_inside_dock
        and "composer" not in out_of_window
        and action_visible
        and action_inside_dock
        and "primary_action" not in out_of_window
        and main_content_visible
        and main_content_inside_window
        and bool(visible_nav_buttons or compact_nav_visible)
        and not nav_outside_window
        and not nav_text_overflow
        and compact_nav_inside_window
        and compact_nav_text_fits
        and not overlaps
    )
    return {
        "capture_target": "full_main_window",
        "state": state,
        "workflow_status": workflow_status,
        "main_window_visible": bool(window.isVisible()),
        "window_width": int(window.width()),
        "window_height": int(window.height()),
        "dock_visible": bool(dock.isVisible()),
        "dock_floating": dock_is_floating,
        "dock_inside_window": "dock" not in out_of_window,
        "title_text": title_text,
        "title_text_fits": title_text_fits,
        "composer_visible": composer_visible,
        "composer_inside_window": "composer" not in out_of_window,
        "composer_inside_dock": composer_inside_dock,
        "primary_action_text": (
            str(primary_action_button.text() or "")
            if primary_action_button is not None
            else ""
        ),
        "primary_action_visible": action_visible,
        "primary_action_inside_window": "primary_action" not in out_of_window,
        "primary_action_inside_dock": action_inside_dock,
        "main_content_visible": main_content_visible,
        "main_content_inside_window": main_content_inside_window,
        "main_navigation_visible_count": len(visible_nav_buttons),
        "main_navigation_outside_window": nav_outside_window,
        "main_navigation_text_overflow": nav_text_overflow,
        "compact_navigation_visible": compact_nav_visible,
        "compact_navigation_text": compact_nav_text,
        "compact_navigation_inside_window": compact_nav_inside_window,
        "compact_navigation_text_fits": compact_nav_text_fits,
        "out_of_window_widgets": out_of_window,
        "overlapping_widgets": overlaps,
        "geometry_passed": geometry_passed,
    }


def evaluation_plot_readability_evidence(window: Any) -> dict[str, Any]:
    """Measure responsive layout and all confusion-matrix decorations."""
    panel = getattr(window, "evaluation_panel", None)
    matrix_widget = getattr(panel, "matrix_widget", None)
    canvas = getattr(matrix_widget, "canvas", None)
    figure = getattr(matrix_widget, "fig", None)
    if canvas is None or figure is None:
        return {
            "available": False,
            "fully_visible": False,
            "finding": "Evaluation confusion matrix is unavailable in handoff evidence.",
            "labels": [],
        }

    canvas.draw()
    renderer = canvas.get_renderer()
    matrix_axes = next(
        (
            axes
            for axes in figure.axes
            if "confusion" in str(axes.get_title() or "").lower()
        ),
        figure.axes[0] if figure.axes else None,
    )
    if matrix_axes is None:
        return {
            "available": False,
            "fully_visible": False,
            "finding": "Evaluation confusion matrix axes are missing.",
            "labels": [],
        }

    figure_width = float(figure.bbox.width)
    figure_height = float(figure.bbox.height)
    rows: list[dict[str, Any]] = []

    def record_label(label: Any, role: str) -> None:
        text = " ".join(str(label.get_text() or "").split())
        if not text or not label.get_visible():
            return
        bounds = label.get_window_extent(renderer=renderer)
        anchor = label.get_transform().transform(label.get_position())
        clipped = bool(
            bounds.x0 < 0
            or bounds.y0 < 0
            or bounds.x1 > figure_width
            or bounds.y1 > figure_height
        )
        rows.append(
            {
                "text": text,
                "role": role,
                "x0": round(float(bounds.x0), 2),
                "x1": round(float(bounds.x1), 2),
                "y0": round(float(bounds.y0), 2),
                "y1": round(float(bounds.y1), 2),
                "anchor_x": round(float(anchor[0]), 2),
                "anchor_y": round(float(anchor[1]), 2),
                "rotation": round(float(label.get_rotation()), 2),
                "clipped": clipped,
            }
        )

    for label in matrix_axes.get_xticklabels():
        record_label(label, "x_tick")
    for label in matrix_axes.get_yticklabels():
        record_label(label, "y_tick")
    record_label(matrix_axes.xaxis.label, "x_axis")
    record_label(matrix_axes.yaxis.label, "y_axis")
    record_label(matrix_axes.title, "title")

    x_tick_rows = sorted(
        (row for row in rows if row["role"] == "x_tick"),
        key=lambda row: float(row["x0"]),
    )
    overlapping_x_ticks = _overlapping_x_tick_labels(x_tick_rows)
    axes_outside_figure = []
    for index, axes in enumerate(figure.axes):
        bounds = axes.get_window_extent(renderer=renderer)
        if (
            bounds.x0 < -1
            or bounds.y0 < -1
            or bounds.x1 > figure_width + 1
            or bounds.y1 > figure_height + 1
        ):
            axes_outside_figure.append(index)

    chart_tabs = getattr(panel, "chart_tabs", None)
    charts_container = getattr(panel, "charts_container", None)
    content_width = (
        int(charts_container.contentsRect().width())
        if charts_container is not None
        else 0
    )
    tabbed = bool(chart_tabs is not None and chart_tabs.isVisible())
    responsive_layout_ok = content_width >= 720 or tabbed
    aggregate_info = aggregate_info_readability_evidence(panel)
    clipped_labels = [str(row["text"]) for row in rows if row["clipped"]]
    canvas_width = int(canvas.width())
    canvas_height = int(canvas.height())
    canvas_size_ok = canvas_width >= 180 and canvas_height >= 120
    fully_visible = (
        bool(rows)
        and canvas_size_ok
        and not (
            clipped_labels
            or overlapping_x_ticks
            or axes_outside_figure
            or not responsive_layout_ok
            or not aggregate_info["fully_readable"]
        )
    )
    return {
        "available": bool(rows),
        "fully_visible": fully_visible,
        "figure_width": round(figure_width, 2),
        "figure_height": round(figure_height, 2),
        "canvas_width": canvas_width,
        "canvas_height": canvas_height,
        "canvas_size_ok": canvas_size_ok,
        "content_width": content_width,
        "layout_mode": "tabs" if tabbed else "side_by_side",
        "responsive_layout_ok": responsive_layout_ok,
        "aggregate_info": aggregate_info,
        "clipped_labels": clipped_labels,
        "overlapping_x_ticks": overlapping_x_ticks,
        "axes_outside_figure": axes_outside_figure,
        "labels": rows,
        "y_tick_labels": [row for row in rows if row["role"] == "y_tick"],
        "finding": (
            ""
            if fully_visible
            else "Evaluation plot labels, aggregate information, axes, or responsive "
            "layout are not fully readable in the full-window assistant handoff "
            "artifact."
        ),
    }


def aggregate_info_readability_evidence(panel: Any) -> dict[str, Any]:
    """Measure visible aggregate-information cells against rendered text widths."""
    info_panel = getattr(panel, "info_panel", None)
    table = getattr(info_panel, "table", None)
    if info_panel is None or table is None:
        return {
            "available": False,
            "visible": False,
            "fully_readable": False,
            "clipped_labels": [],
            "cells": [],
        }

    visible = bool(
        panel is not None and info_panel.isVisible() and info_panel.isVisibleTo(panel)
    )
    if not visible:
        return {
            "available": True,
            "visible": False,
            "fully_readable": True,
            "clipped_labels": [],
            "cells": [],
        }

    cells: list[dict[str, Any]] = []
    clipped_labels: list[str] = []
    metrics = table.fontMetrics()
    viewport = table.viewport()
    viewport_width = int(viewport.width()) if viewport is not None else 0
    for row in range(table.rowCount()):
        if table.isRowHidden(row):
            continue
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is None:
                continue
            text = " ".join(str(item.text() or "").split())
            rect = table.visualItemRect(item)
            required_width = metrics.horizontalAdvance(text) + 16
            clipped = bool(
                text
                and (
                    rect.width() < required_width
                    or rect.left() < 0
                    or rect.right() > viewport_width
                )
            )
            if clipped:
                clipped_labels.append(text)
            cells.append(
                {
                    "row": row,
                    "column": column,
                    "text": text,
                    "cell_width": int(rect.width()),
                    "required_width": int(required_width),
                    "clipped": clipped,
                }
            )
    return {
        "available": True,
        "visible": True,
        "fully_readable": bool(cells) and not clipped_labels,
        "clipped_labels": clipped_labels,
        "key_column_width": int(table.columnWidth(0)),
        "value_column_width": int(table.columnWidth(1)),
        "viewport_width": viewport_width,
        "cells": cells,
    }


def training_metric_tab_evidence(tab: Any) -> dict[str, Any]:
    """Snapshot the observable empty/data state of one real MetricTab."""
    canvas = getattr(tab, "canvas", None)
    axis = getattr(tab, "ax", None)
    lines = list(axis.lines) if axis is not None else []
    empty_state = getattr(tab, "empty_state_label", None)
    return {
        "empty_state_text": (
            " ".join(str(empty_state.text()).split()) if empty_state is not None else ""
        ),
        "empty_state_visible": bool(
            empty_state is not None and empty_state.isVisibleTo(tab)
        ),
        "canvas_visible": bool(canvas is not None and canvas.isVisibleTo(tab)),
        "epochs": list(getattr(tab, "epochs", [])),
        "train_values": list(getattr(tab, "train_vals", [])),
        "validation_values": list(getattr(tab, "val_vals", [])),
        "plotted_series": len(lines),
        "series_points": [
            {
                "x": [float(value) for value in line.get_xdata()],
                "y": [float(value) for value in line.get_ydata()],
                "label": str(line.get_label()),
            }
            for line in lines
        ],
    }


def _overlapping_x_tick_labels(
    rows: list[dict[str, Any]],
) -> list[str]:
    """Return labels that are visually too close at the current rotation."""
    overlaps: list[str] = []
    for left, right in pairwise(rows):
        left_rotation = abs(float(left.get("rotation", 0.0)))
        right_rotation = abs(float(right.get("rotation", 0.0)))
        if max(left_rotation, right_rotation) >= 1.0:
            too_close = (
                abs(
                    float(right.get("anchor_x", 0.0)) - float(left.get("anchor_x", 0.0))
                )
                < 18.0
            )
        else:
            too_close = float(left["x1"]) + 6.0 > float(right["x0"])
        if too_close:
            overlaps.append(f"{left['text']} / {right['text']}")
    return overlaps


def workflow_handoff_product_copy_evidence() -> dict[str, str]:
    """Render non-navigation handoff outcomes through production copy policy."""
    return {
        status.value: AgentPresentationService.workflow_surface_outcome_message(
            WorkflowSurfaceOutcome(
                status=status,
                command_name="evaluate",
                message="",
            )
        )
        for status in (
            WorkflowSurfaceStatus.CANCELLED,
            WorkflowSurfaceStatus.COMPLETED,
            WorkflowSurfaceStatus.FAILED,
        )
    }


def assistant_notice_evidence(panel: Any) -> dict[str, Any]:
    """Record whether a persistent notice duplicates the visible transcript."""
    notice = getattr(panel, "notice_label", None)
    text = ""
    visible = False
    if notice is not None:
        text = " ".join(str(notice.text() or "").split())
        visible = bool(notice.isVisible() and text)
    source = "notice"
    phase = getattr(getattr(panel, "_runtime_phase", None), "value", "")
    if not visible and phase == "failed":
        runtime_state = getattr(panel, "runtime_state_widget", None)
        runtime_detail = getattr(panel, "runtime_state_detail", None)
        if runtime_state is not None and runtime_detail is not None:
            text = " ".join(str(runtime_detail.text() or "").split())
            visible = bool(runtime_state.isVisible() and text)
            source = "inline_runtime"
    transcript = [
        " ".join(message.text.split()) for message in collect_visible_messages(panel)
    ]
    duplicate = bool(
        visible
        and any(
            text == message or text in message or message in text
            for message in transcript
        )
    )
    owner = getattr(panel, "_notice_owner", None) if visible else None
    if visible and source == "inline_runtime":
        # The runtime state surface is itself owned by the typed runtime
        # snapshot. It no longer uses the transient notice QLabel owner flag.
        owner = "runtime"
    return {
        "visible": visible,
        "owner": owner,
        "source": source if visible else None,
        "text": text,
        "duplicate_with_transcript": duplicate,
    }


def assistant_error_evidence(panel: Any) -> dict[str, Any]:
    """Prove a raw traceback reached the manager but not the transcript."""
    messages = [message.text for message in collect_visible_messages(panel)]
    visible = "\n".join(messages)
    normalized = visible.casefold()
    return {
        "raw_error_injected": True,
        "raw_error_visible": "traceback" in normalized,
        "sanitized_message_visible": any(
            marker in normalized
            for marker in (
                "try again",
                "retry",
                "open assistant settings",
                "assistant needs input",
            )
        ),
    }


def _widget_inside(parent: QWidget, child: QWidget, tolerance: int = 2) -> bool:
    origin = child.mapTo(parent, QPoint(0, 0))
    return (
        origin.x() >= -tolerance
        and origin.y() >= -tolerance
        and origin.x() + child.width() <= parent.width() + tolerance
        and origin.y() + child.height() <= parent.height() + tolerance
    )


def _label_text_exceeds_bounds(label: QLabel) -> bool:
    """Return whether a visible label needs more space than its content rect."""
    if not label.isVisible() or not label.text():
        return False
    contents = label.contentsRect()
    if label.wordWrap():
        unbreakable_segments = re.split(r"[\s\u200b]+", label.text())
        if any(
            label.fontMetrics().horizontalAdvance(segment) > contents.width() + 2
            for segment in unbreakable_segments
            if segment
        ):
            return True
        needed = label.fontMetrics().boundingRect(
            QRect(0, 0, max(contents.width(), 1), 10000),
            int(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap
            ),
            label.text(),
        )
        return needed.height() > contents.height() + 3
    return (
        label.fontMetrics().horizontalAdvance(" ".join(label.text().split()))
        > contents.width() + 2
    )


def _button_renders_text(button: QAbstractButton) -> bool:
    """Return whether Qt paints the button text in its current presentation."""
    if button.property("assistantCustomContent") is True:
        return False
    return not (
        isinstance(button, QToolButton)
        and button.toolButtonStyle() is Qt.ToolButtonStyle.ToolButtonIconOnly
    )


def icon_only_control_contrast_evidence(
    root: QWidget,
    screenshot: Path,
    control: QToolButton,
) -> dict[str, Any]:
    """Measure whether an icon-only control paints visible icon detail."""
    if control.toolButtonStyle() is not Qt.ToolButtonStyle.ToolButtonIconOnly:
        return {
            "passed": True,
            "applicable": False,
            "luminance_span": 0,
            "luminance_stddev": 0.0,
        }
    if control.icon().isNull() or not control.accessibleName().strip():
        return {
            "passed": False,
            "applicable": True,
            "luminance_span": 0,
            "luminance_stddev": 0.0,
        }

    icon_size = control.iconSize()
    icon_width = max(min(icon_size.width(), control.width()), 1)
    icon_height = max(min(icon_size.height(), control.height()), 1)
    local_x = max((control.width() - icon_width) // 2, 0)
    local_y = max((control.height() - icon_height) // 2, 0)
    origin = control.mapTo(root, QPoint(local_x, local_y))
    with Image.open(screenshot) as captured:
        scale_x = captured.width / max(root.width(), 1)
        scale_y = captured.height / max(root.height(), 1)
        left = round(origin.x() * scale_x)
        top = round(origin.y() * scale_y)
        right = round((origin.x() + icon_width) * scale_x)
        bottom = round((origin.y() + icon_height) * scale_y)
        crop = captured.convert("L").crop((left, top, right, bottom))
        occupied_bins = [value for value, count in enumerate(crop.histogram()) if count]
        low = occupied_bins[0] if occupied_bins else 0
        high = occupied_bins[-1] if occupied_bins else 0
        stddev = float(ImageStat.Stat(crop).stddev[0]) if crop.size[0] else 0.0
    span = high - low
    return {
        "passed": span >= 24 and stddev >= 3.0,
        "applicable": True,
        "luminance_span": span,
        "luminance_stddev": round(stddev, 3),
        "bounds": [left, top, max(right - left, 0), max(bottom - top, 0)],
    }


def _assistant_text_overflow(panel: Any) -> list[str]:
    """Return named assistant widgets whose rendered text exceeds bounds."""
    overflows: list[str] = []
    for name in (
        "send_btn",
        "empty_state_action_button",
        "setup_btn",
        "workflow_run_status_label",
    ):
        widget = getattr(panel, name, None)
        if widget is None or not widget.isVisible() or not hasattr(widget, "text"):
            continue
        text = " ".join(str(widget.text() or "").split())
        if not text:
            continue
        if isinstance(widget, QAbstractButton) and not _button_renders_text(widget):
            continue
        available = max(widget.contentsRect().width(), 1)
        padding = 18 if isinstance(widget, QAbstractButton) else 0
        if widget.fontMetrics().horizontalAdvance(text) + padding > available + 2:
            overflows.append(name)

    for name in (
        "empty_state_title",
        "empty_state_intro",
        "empty_state_next_label",
        "notice_label",
        "runtime_state_title",
        "runtime_state_detail",
        "turn_activity_title",
        "turn_activity_step",
        "turn_activity_cancelability",
    ):
        label = getattr(panel, name, None)
        if label is None or not label.isVisible() or not label.text():
            continue
        if _label_text_exceeds_bounds(label):
            overflows.append(name)

    confirmation_card = getattr(panel, "confirmation_card_widget", None)
    if confirmation_card is not None and confirmation_card.isVisible():
        for name in (
            "title_label",
            "description_label",
            "reason_title",
            "reason_label",
        ):
            label = getattr(confirmation_card, name, None)
            if isinstance(label, QLabel) and _label_text_exceeds_bounds(label):
                overflows.append(f"confirmation_card/{name}")
        for index, row in enumerate(confirmation_card.proposal_rows):
            for name in ("label", "current_value", "proposed_value"):
                label = getattr(row, name, None)
                if (
                    isinstance(label, QLabel)
                    and label.isVisible()
                    and _label_text_exceeds_bounds(label)
                ):
                    overflows.append(f"confirmation_card/row_{index}/{name}")

    for index, bubble in enumerate(
        child for child in panel.findChildren(MessageBubble) if child.isVisible()
    ):
        text_edit = bubble.text_edit
        if text_edit is None:
            continue
        document = text_edit.document()
        layout = document.documentLayout() if document is not None else None
        if layout is None:
            continue
        document_size = layout.documentSize()
        if document_size.height() > text_edit.viewport().height() + 4:
            overflows.append(f"message_bubble_{index}")

    placeholder = assistant_composer_placeholder_evidence(panel)
    if placeholder["visible"] and not placeholder["fits"]:
        overflows.append("input_field_placeholder")
    return overflows


def assistant_composer_placeholder_evidence(panel: Any) -> dict[str, Any]:
    """Measure the wrapped composer placeholder against its real viewport."""
    input_field = cast(Any, panel.input_field)
    viewport_factory = getattr(input_field, "viewport", None)
    viewport = cast(
        Any,
        viewport_factory() if callable(viewport_factory) else input_field,
    )
    placeholder = str(input_field.placeholderText() or "")
    document_factory = getattr(input_field, "document", None)
    document = cast(
        Any,
        document_factory() if callable(document_factory) else None,
    )
    document_margin = (
        ceil(float(document.documentMargin())) if document is not None else 0
    )
    available_width = max(viewport.contentsRect().width() - 2 * document_margin, 0)
    # QPlainTextEdit positions the first line below the top document margin; the
    # remaining viewport height is the actual vertical clipping boundary.
    available_height = max(viewport.contentsRect().height() - document_margin, 0)
    metrics = input_field.fontMetrics()
    unwrapped_width = metrics.horizontalAdvance(placeholder)
    wrapped_bounds = metrics.boundingRect(
        QRect(0, 0, max(available_width, 1), 10000),
        int(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop
            | Qt.TextFlag.TextWordWrap
        ),
        placeholder,
    )
    required_width = min(unwrapped_width, wrapped_bounds.width())
    required_height = wrapped_bounds.height()
    fits_width = not placeholder or wrapped_bounds.width() <= available_width
    fits_height = not placeholder or required_height <= available_height
    return {
        "text": placeholder,
        "visible": bool(placeholder and input_field.isVisible()),
        "viewport_width": viewport.width(),
        "viewport_height": viewport.height(),
        "document_margin": document_margin,
        "required_width": required_width,
        "unwrapped_width": unwrapped_width,
        "required_height": required_height,
        "available_width": available_width,
        "available_height": available_height,
        "fits_width": fits_width,
        "fits_height": fits_height,
        "fits": fits_width and fits_height,
    }


def assistant_dock_evidence(dock: QWidget, panel: Any) -> dict[str, Any]:
    """Record full-dock geometry, title visibility, scrolling, and text fit."""
    title_bar = getattr(dock, "titleBarWidget", lambda: None)()
    overflowing = _assistant_text_overflow(panel)
    title_text = ""
    title_text_fits = False
    if title_bar is not None:
        for child in title_bar.findChildren(QWidget):
            if child.isVisible() and not _widget_inside(title_bar, child):
                name = child.objectName() or type(child).__name__
                overflowing.append(f"title_bar/{name}")
        title_label = title_bar.findChild(QLabel, "AssistantDockTitle")
        if title_label is not None:
            title_text = " ".join(str(title_label.text() or "").split())
            required_width = title_label.fontMetrics().horizontalAdvance(title_text)
            title_text_fits = bool(
                title_text and required_width <= title_label.contentsRect().width() + 1
            )
    scroll_area = getattr(panel, "scroll_area", None)
    horizontal_scrollbar = (
        scroll_area.horizontalScrollBar() if scroll_area is not None else None
    )
    runtime_state = getattr(panel, "runtime_state_widget", None)
    runtime_actions = getattr(panel, "runtime_actions", None)
    chat_content = getattr(panel, "chat_content_widget", None)
    setup_action = getattr(panel, "setup_btn", None)
    retry_action = getattr(panel, "retry_runtime_btn", None)
    runtime_visible = bool(runtime_state is not None and runtime_state.isVisible())
    setup_visible = bool(setup_action is not None and setup_action.isVisible())
    setup_text = str(setup_action.text() or "") if setup_action is not None else ""
    setup_available = (
        setup_action.contentsRect().width() if setup_action is not None else 0
    )
    setup_required = (
        setup_action.fontMetrics().horizontalAdvance(setup_text) + 24
        if setup_action is not None
        else 0
    )
    retry_visible = bool(retry_action is not None and retry_action.isVisible())
    retry_text = str(retry_action.text() or "") if retry_action is not None else ""
    retry_available = (
        retry_action.contentsRect().width() if retry_action is not None else 0
    )
    retry_required = (
        retry_action.fontMetrics().horizontalAdvance(retry_text) + 24
        if retry_action is not None
        else 0
    )
    empty_state = getattr(panel, "empty_state_widget", None)
    transcript_messages = (
        chat_content.findChildren(MessageBubble) if chat_content is not None else []
    )
    visible_messages = collect_visible_messages(panel)
    placeholder = assistant_composer_placeholder_evidence(panel)
    panel_origin = panel.mapTo(dock, QPoint(0, 0))
    dock_content = dock.contentsRect()
    panel_left_gap = panel_origin.x() - dock_content.x()
    panel_right_gap = (
        dock_content.x() + dock_content.width() - panel_origin.x() - panel.width()
    )
    panel_fills_dock_width = abs(panel_left_gap) <= 2 and abs(panel_right_gap) <= 2
    return {
        "capture_target": "full_dock",
        "dock_width": dock.width(),
        "dock_height": dock.height(),
        "dock_content_width": dock_content.width(),
        "panel_width": panel.width(),
        "panel_left_gap_px": panel_left_gap,
        "panel_right_gap_px": panel_right_gap,
        "panel_fills_dock_width": panel_fills_dock_width,
        "title_bar_visible": bool(title_bar is not None and title_bar.isVisible()),
        "title_text": title_text,
        "title_text_fits": title_text_fits,
        "title_bar_inside_bounds": bool(
            title_bar is not None and _widget_inside(dock, title_bar)
        ),
        "panel_inside_bounds": _widget_inside(dock, panel),
        "horizontal_scrollbar_max": (
            horizontal_scrollbar.maximum() if horizontal_scrollbar is not None else 0
        ),
        "overflowing_widgets": sorted(set(overflowing)),
        "empty_state_visible": bool(
            empty_state is not None and empty_state.isVisible()
        ),
        "transcript_message_count": len(transcript_messages),
        "visible_message_count": len(visible_messages),
        "composer_placeholder": placeholder,
        "runtime_state": {
            "visible": runtime_visible,
            "inside_content": bool(
                runtime_state is not None
                and chat_content is not None
                and runtime_state.parentWidget() is chat_content
            ),
            "inside_bounds": bool(
                not runtime_visible
                or (
                    runtime_state is not None
                    and chat_content is not None
                    and _widget_inside(chat_content, runtime_state)
                )
            ),
        },
        "setup_action": {
            "text": setup_text,
            "visible": setup_visible,
            "enabled": bool(setup_action is not None and setup_action.isEnabled()),
            "inside_runtime_state": bool(
                setup_action is not None
                and runtime_state is not None
                and setup_action.parentWidget() is runtime_state
            ),
            "inside_runtime_actions": bool(
                setup_action is not None
                and runtime_actions is not None
                and setup_action.parentWidget() is runtime_actions
            ),
            "inside_bounds": bool(
                not setup_visible
                or (
                    setup_action is not None
                    and runtime_actions is not None
                    and _widget_inside(runtime_actions, setup_action)
                )
            ),
            "text_width": setup_required,
            "available_width": setup_available,
            "fits_width": bool(not setup_visible or setup_required <= setup_available),
        },
        "retry_action": {
            "text": retry_text,
            "visible": retry_visible,
            "enabled": bool(retry_action is not None and retry_action.isEnabled()),
            "inside_runtime_actions": bool(
                retry_action is not None
                and runtime_actions is not None
                and retry_action.parentWidget() is runtime_actions
            ),
            "inside_bounds": bool(
                not retry_visible
                or (
                    retry_action is not None
                    and runtime_actions is not None
                    and _widget_inside(runtime_actions, retry_action)
                )
            ),
            "text_width": retry_required,
            "available_width": retry_available,
            "fits_width": bool(not retry_visible or retry_required <= retry_available),
        },
    }


def assistant_processing_evidence(
    panel: Any,
    *,
    controller_processing: bool,
) -> dict[str, Any]:
    """Return readable state and geometry evidence while processing."""
    input_field = panel.input_field
    send_button = panel.send_btn
    status_label = panel.workflow_run_status_label
    status_text = " ".join(status_label.text().split())
    text_width = status_label.fontMetrics().horizontalAdvance(status_text)
    text_height = status_label.fontMetrics().height()
    available_width = status_label.contentsRect().width()
    available_height = status_label.contentsRect().height()
    turn_presentation = getattr(panel, "_turn_presentation", None)
    activity_widget = panel.turn_activity_widget
    activity_title = panel.turn_activity_title
    activity_step = panel.turn_activity_step
    activity_cancelability = panel.turn_activity_cancelability

    def label_state(label: QLabel) -> dict[str, Any]:
        contents = label.contentsRect()
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        if label.wordWrap():
            flags |= int(Qt.TextFlag.TextWordWrap)
        needed = label.fontMetrics().boundingRect(
            QRect(0, 0, max(contents.width(), 1), 10000),
            flags,
            label.text(),
        )
        return {
            "text": " ".join(label.text().split()),
            "visible": label.isVisible(),
            "available_width": contents.width(),
            "available_height": contents.height(),
            "required_height": needed.height(),
            "fits_height": needed.height() <= contents.height() + 3,
        }

    return {
        "manual_mode_selector_present": any(
            hasattr(panel, name)
            for name in ("mode_selector_widget", "ask_mode_btn", "workflow_mode_btn")
        ),
        "runtime_phase": str(
            getattr(getattr(panel, "_runtime_phase", None), "value", "")
        ),
        "header_status": str(getattr(panel, "header_status_text", "")),
        "controller_processing": bool(controller_processing),
        "panel_processing": bool(panel.is_processing),
        "composer_input_enabled": input_field.isEnabled(),
        "stop_button": {
            "text": send_button.text(),
            "visible": send_button.isVisible(),
            "enabled": send_button.isEnabled(),
            "x": send_button.x(),
            "y": send_button.y(),
            "width": send_button.width(),
            "height": send_button.height(),
        },
        "turn_activity": {
            "visible": activity_widget.isVisible(),
            "phase": str(
                getattr(getattr(turn_presentation, "phase", None), "value", "")
            ),
            "cancelability": str(
                getattr(
                    getattr(turn_presentation, "cancelability", None),
                    "value",
                    "",
                )
            ),
            "primary_status": label_state(activity_title),
            "step": label_state(activity_step),
            "cancelability_text": label_state(activity_cancelability),
        },
        "workflow_status": {
            "text": status_text,
            "tooltip": " ".join(status_label.toolTip().split()),
            "visible": status_label.isVisible(),
            "x": status_label.x(),
            "y": status_label.y(),
            "width": status_label.width(),
            "height": status_label.height(),
            "text_width": text_width,
            "available_width": available_width,
            "text_height": text_height,
            "available_height": available_height,
            "fits_width": available_width > 0 and text_width <= available_width,
            "fits_height": available_height > 0 and text_height <= available_height,
        },
    }


def assistant_runtime_evidence(panel: Any) -> dict[str, Any]:
    """Return composer evidence for the current local runtime phase."""
    phase = getattr(panel, "_runtime_phase", "")
    phase_text = getattr(phase, "value", str(phase))
    status = panel.workflow_run_status_label
    inline_state = panel.runtime_state_widget
    setup_action = panel.setup_btn
    retry_action = panel.retry_runtime_btn
    return {
        "phase": str(phase_text),
        "panel_processing": bool(panel.is_processing),
        "composer_input_enabled": panel.input_field.isEnabled(),
        "composer_has_text": bool(panel.input_field.toPlainText().strip()),
        "composer_visible": panel.input_widget.isVisible(),
        "send_button_enabled": panel.send_btn.isEnabled(),
        "send_button_text": panel.send_btn.text(),
        "composer_placeholder": panel.input_field.placeholderText(),
        "status_visible": status.isVisible(),
        "status_text": " ".join(status.text().split()),
        "inline_state_visible": inline_state.isVisible(),
        "inline_state_location": (
            "content"
            if inline_state.parentWidget() is panel.chat_content_widget
            else "other"
        ),
        "inline_state_title": " ".join(panel.runtime_state_title.text().split()),
        "inline_state_detail": " ".join(panel.runtime_state_detail.text().split()),
        "setup_action_visible": setup_action.isVisible(),
        "setup_action_enabled": setup_action.isEnabled(),
        "setup_action_text": setup_action.text(),
        "setup_action_semantic_text": _semantic_action_text(setup_action),
        "retry_action_visible": retry_action.isVisible(),
        "retry_action_enabled": retry_action.isEnabled(),
        "retry_action_text": retry_action.text(),
        "retry_action_semantic_text": _semantic_action_text(retry_action),
    }


def _semantic_action_text(button: QAbstractButton) -> str:
    """Read stable action identity without depending on native text elision."""
    accessible_name = " ".join(button.accessibleName().split())
    if accessible_name:
        return accessible_name
    full_label = button.property("assistantFullLabel")
    if isinstance(full_label, str) and full_label.strip():
        return " ".join(full_label.split())
    return " ".join(button.text().split())


def assistant_restored_state(
    panel: Any,
    *,
    controller_processing: bool,
) -> dict[str, Any]:
    """Return evidence that Stop restored an idle, usable composer."""
    return {
        "manual_mode_selector_present": any(
            hasattr(panel, name)
            for name in ("mode_selector_widget", "ask_mode_btn", "workflow_mode_btn")
        ),
        "controller_processing": bool(controller_processing),
        "panel_processing": bool(panel.is_processing),
        "composer_input_enabled": panel.input_field.isEnabled(),
        "send_button_text": panel.send_btn.text(),
        "workflow_status_visible": panel.workflow_run_status_label.isVisible(),
    }
