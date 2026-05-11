"""Shared top-level window placement helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QPoint, QRect, QSize
from PyQt6.QtGui import QCursor, QGuiApplication, QScreen
from PyQt6.QtWidgets import QWidget

STARTUP_SCREEN_PROPERTY = "xbrainlab_startup_screen_name"
STARTUP_GEOMETRY_DIAGNOSTICS_ENV = "XBRAINLAB_STARTUP_DIAGNOSTICS"
_TRUE_ENV_VALUES = {"1", "true", "yes", "on", "debug"}


@dataclass(frozen=True)
class ScreenGeometry:
    """Geometry pair used to rank real or simulated screens."""

    available: QRect
    full: QRect


@dataclass(frozen=True)
class FrameExtents:
    """Native frame border extents around a Qt client geometry."""

    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0


def startup_geometry_diagnostics_enabled(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether startup geometry diagnostics should be logged."""
    raw_value = (environ or os.environ).get(STARTUP_GEOMETRY_DIAGNOSTICS_ENV, "")
    return raw_value.strip().lower() in _TRUE_ENV_VALUES


def format_rect(rect: QRect | None) -> str:
    """Format a QRect for compact startup diagnostics."""
    if rect is None:
        return "<none>"
    return (
        f"x={rect.x()} y={rect.y()} w={rect.width()} h={rect.height()} "
        f"valid={rect.isValid()}"
    )


def format_screen(screen: QScreen | None) -> str:
    """Format a QScreen for compact startup diagnostics."""
    if screen is None:
        return "<none>"
    return (
        f"name={screen.name()!r} "
        f"available=({format_rect(screen.availableGeometry())}) "
        f"full=({format_rect(screen.geometry())})"
    )


def screen_geometry_diagnostic_lines() -> list[str]:
    """Return screen and cursor geometry diagnostics for startup logging."""
    app = QGuiApplication.instance()
    if app is None:
        return ["startup geometry: no QGuiApplication instance"]

    primary = QGuiApplication.primaryScreen()
    primary_name = primary.name() if primary is not None else "<none>"
    lines = [
        "startup geometry: "
        f"screen_count={len(QGuiApplication.screens())} "
        f"primary={primary_name!r} cursor=({format_point(QCursor.pos())})"
    ]
    for index, screen in enumerate(QGuiApplication.screens()):
        lines.append(f"startup geometry: screen[{index}] {format_screen(screen)}")
    return lines


def widget_geometry_diagnostic_line(label: str, widget: QWidget) -> str:
    """Return one geometry diagnostic line for a top-level widget."""
    screen = widget.screen()
    return (
        f"startup geometry: {label} "
        f"visible={widget.isVisible()} "
        f"geometry=({format_rect(widget.geometry())}) "
        f"frame=({format_rect(widget.frameGeometry())}) "
        f"screen={format_screen(screen)}"
    )


def format_point(point: QPoint | None) -> str:
    """Format a QPoint for compact startup diagnostics."""
    if point is None:
        return "<none>"
    return f"x={point.x()} y={point.y()}"


def screen_geometry_for(screen: QScreen | None, fallback_size: QSize) -> ScreenGeometry:
    """Return available/full geometry for a screen with a deterministic fallback."""
    if screen is not None:
        return ScreenGeometry(screen.availableGeometry(), screen.geometry())
    fallback = QRect(0, 0, fallback_size.width(), fallback_size.height())
    return ScreenGeometry(fallback, fallback)


def remember_startup_screen(screen: QScreen | None) -> None:
    """Store the startup screen chosen for splash/main-window consistency."""
    app = QGuiApplication.instance()
    if app is None or screen is None:
        return
    app.setProperty(STARTUP_SCREEN_PROPERTY, screen.name())


def startup_screen_hint() -> QScreen | None:
    """Return the screen selected at startup, if it still exists."""
    app = QGuiApplication.instance()
    if app is None:
        return None
    name = app.property(STARTUP_SCREEN_PROPERTY)
    if not isinstance(name, str) or not name:
        return None
    for screen in QGuiApplication.screens():
        if screen.name() == name:
            return screen
    return None


def restored_widget_geometry(saved_geometry: Any) -> QRect | None:
    """Extract a saved Qt geometry blob into a client QRect without showing it."""
    if saved_geometry is None or QGuiApplication.instance() is None:
        return None

    probe = QWidget()
    try:
        if not probe.restoreGeometry(saved_geometry):
            return None
        geometry = probe.geometry()
        return QRect(geometry)
    except (RuntimeError, TypeError, ValueError):
        return None
    finally:
        probe.deleteLater()


def choose_screen_for_saved_geometry(saved_geometry: Any) -> QScreen | None:
    """Choose a startup screen from saved main-window geometry, cursor, or primary."""
    return choose_screen_for_rect(restored_widget_geometry(saved_geometry))


def choose_screen_for_rect(
    candidate_rect: QRect | None = None,
    *,
    preferred_screen: QScreen | None = None,
) -> QScreen | None:
    """Choose the most reasonable screen for a window rectangle."""
    screens = list(QGuiApplication.screens())
    if not screens:
        return QGuiApplication.primaryScreen()

    primary = QGuiApplication.primaryScreen()
    primary_index = screens.index(primary) if primary in screens else 0
    preferred_index = (
        screens.index(preferred_screen) if preferred_screen in screens else None
    )
    screen_geometries = [
        ScreenGeometry(screen.availableGeometry(), screen.geometry())
        for screen in screens
    ]
    index = choose_screen_index_for_rect(
        candidate_rect,
        screen_geometries,
        cursor_pos=QCursor.pos(),
        primary_index=primary_index,
        preferred_index=preferred_index,
    )
    if index is None:
        return None
    return screens[index]


def choose_screen_index_for_rect(
    candidate_rect: QRect | None,
    screens: Sequence[ScreenGeometry],
    *,
    cursor_pos: QPoint | None = None,
    primary_index: int = 0,
    preferred_index: int | None = None,
) -> int | None:
    """Rank simulated screens using window center, intersection, cursor, primary."""
    if not screens:
        return None

    if candidate_rect is not None and candidate_rect.isValid():
        center = candidate_rect.center()
        for index, screen in enumerate(screens):
            if screen.available.contains(center):
                return index
        for index, screen in enumerate(screens):
            if screen.full.contains(center):
                return index

        available_intersection = _largest_intersection_index(
            candidate_rect,
            [screen.available for screen in screens],
        )
        if available_intersection is not None:
            return available_intersection

        full_intersection = _largest_intersection_index(
            candidate_rect,
            [screen.full for screen in screens],
        )
        if full_intersection is not None:
            return full_intersection

    if preferred_index is not None and 0 <= preferred_index < len(screens):
        return preferred_index

    if cursor_pos is not None:
        for index, screen in enumerate(screens):
            if screen.available.contains(cursor_pos):
                return index
        for index, screen in enumerate(screens):
            if screen.full.contains(cursor_pos):
                return index

    if 0 <= primary_index < len(screens):
        return primary_index
    return 0


def centered_rect_on_available(size: QSize, available: QRect) -> QRect:
    """Return a rectangle centered within available screen geometry."""
    width = min(max(size.width(), 1), available.width())
    height = min(max(size.height(), 1), available.height())
    x = available.left() + max((available.width() - width) // 2, 0)
    y = available.top() + max((available.height() - height) // 2, 0)
    return QRect(x, y, width, height)


def center_widget_on_screen(widget: QWidget, screen: QScreen | None) -> QRect:
    """Move a widget to the center of a target screen before it is shown."""
    fallback_size = widget.size()
    if not fallback_size.isValid():
        fallback_size = widget.sizeHint()
    geometry = screen_geometry_for(screen, fallback_size)
    target_rect = centered_rect_on_available(fallback_size, geometry.available)
    widget.move(target_rect.topLeft())
    return QRect(widget.geometry())


def default_window_size_for_available(
    default_size: QSize,
    min_size: QSize,
    available: QRect,
    *,
    edge_margin: int,
    top_drag_margin: int,
    bottom_margin: int,
) -> QSize:
    """Scale an initial size so startup looks centered, not glued to the top."""
    max_width = max(available.width() - (edge_margin * 2), 1)
    vertical_margin = max(top_drag_margin, bottom_margin) + 8
    max_height = max(available.height() - (vertical_margin * 2), 1)
    width = min(default_size.width(), max_width)
    height = min(default_size.height(), max_height)
    width = min(max(width, min(min_size.width(), available.width())), available.width())
    height = min(
        max(height, min(min_size.height(), available.height())),
        available.height(),
    )
    return QSize(width, height)


def frame_extents_for(
    client_geometry: QRect,
    frame_geometry: QRect | None,
) -> FrameExtents:
    """Return frame extents around a client rectangle."""
    if (
        frame_geometry is None
        or not frame_geometry.isValid()
        or not client_geometry.isValid()
    ):
        return FrameExtents()
    return FrameExtents(
        left=max(client_geometry.left() - frame_geometry.left(), 0),
        top=max(client_geometry.top() - frame_geometry.top(), 0),
        right=max(frame_geometry.right() - client_geometry.right(), 0),
        bottom=max(frame_geometry.bottom() - client_geometry.bottom(), 0),
    )


def usable_window_position_bounds(
    available: QRect,
    width: int,
    height: int,
    *,
    edge_margin: int,
    top_drag_margin: int,
    bottom_margin: int,
    screen_geometry: QRect | None = None,
    frame_extents: FrameExtents | None = None,
) -> tuple[int, int, int, int]:
    """Return client-position bounds that keep the native frame reachable."""
    remaining_x = max(available.width() - width, 0)
    left_margin = min(edge_margin, remaining_x)
    right_margin = min(edge_margin, max(remaining_x - left_margin, 0))

    remaining_y = max(available.height() - height, 0)
    top_margin = min(top_drag_margin, remaining_y)
    bottom_margin = min(bottom_margin, max(remaining_y - top_margin, 0))

    min_x = available.left() + left_margin
    max_x = available.right() - width + 1 - right_margin
    min_y = available.top() + top_margin
    max_y = available.bottom() - height + 1 - bottom_margin

    extents = frame_extents or FrameExtents()
    if screen_geometry is not None and screen_geometry.isValid():
        min_x = max(min_x, screen_geometry.left() + extents.left)
        max_x = min(max_x, screen_geometry.right() - width + 1 - extents.right)
        min_y = max(min_y, available.top() + extents.top + 1)
        max_y = min(max_y, screen_geometry.bottom() - height + 1 - extents.bottom)

    if min_x > max_x:
        centered_x = available.left() + max((available.width() - width) // 2, 0)
        min_x = max_x = centered_x
    if min_y > max_y:
        centered_y = available.top() + max((available.height() - height) // 2, 0)
        min_y = max_y = centered_y
    return min_x, max_x, min_y, max_y


def bounded_window_position(
    available: QRect,
    width: int,
    height: int,
    preferred_x: int,
    preferred_y: int,
    *,
    edge_margin: int,
    top_drag_margin: int,
    bottom_margin: int,
    screen_geometry: QRect | None = None,
    frame_extents: FrameExtents | None = None,
) -> tuple[int, int]:
    """Clamp a client position inside usable frame-aware screen bounds."""
    min_x, max_x, min_y, max_y = usable_window_position_bounds(
        available,
        width,
        height,
        edge_margin=edge_margin,
        top_drag_margin=top_drag_margin,
        bottom_margin=bottom_margin,
        screen_geometry=screen_geometry,
        frame_extents=frame_extents,
    )
    return min(max(preferred_x, min_x), max_x), min(max(preferred_y, min_y), max_y)


def is_window_geometry_usable(
    client_geometry: QRect,
    *,
    available_geometry: QRect,
    min_size: QSize,
    edge_margin: int,
    top_drag_margin: int,
    bottom_margin: int,
    screen_geometry: QRect | None = None,
    frame_geometry: QRect | None = None,
) -> bool:
    """Return whether a top-level window geometry is safe to restore or save."""
    if not client_geometry.isValid():
        return False

    min_width = min(min_size.width(), available_geometry.width())
    min_height = min(min_size.height(), available_geometry.height())
    if client_geometry.width() < min_width or client_geometry.height() < min_height:
        return False
    if (
        client_geometry.width() > available_geometry.width()
        or client_geometry.height() > available_geometry.height()
    ):
        return False
    if not _contains_rect(available_geometry, client_geometry):
        return False

    effective_screen_geometry = screen_geometry or available_geometry
    effective_frame_geometry = frame_geometry
    if effective_frame_geometry is not None and effective_frame_geometry.isValid():
        if not _contains_rect(effective_screen_geometry, effective_frame_geometry):
            return False
        if effective_frame_geometry.top() <= available_geometry.top():
            return False
    else:
        effective_frame_geometry = None

    extents = frame_extents_for(client_geometry, effective_frame_geometry)
    min_x, max_x, min_y, max_y = usable_window_position_bounds(
        available_geometry,
        client_geometry.width(),
        client_geometry.height(),
        edge_margin=edge_margin,
        top_drag_margin=top_drag_margin,
        bottom_margin=bottom_margin,
        screen_geometry=effective_screen_geometry,
        frame_extents=extents,
    )
    return (
        min_x <= client_geometry.x() <= max_x and min_y <= client_geometry.y() <= max_y
    )


def _largest_intersection_index(rect: QRect, containers: Sequence[QRect]) -> int | None:
    best_index: int | None = None
    best_area = 0
    for index, container in enumerate(containers):
        area = _intersection_area(rect, container)
        if area > best_area:
            best_area = area
            best_index = index
    return best_index


def _intersection_area(left: QRect, right: QRect) -> int:
    intersection = left.intersected(right)
    if intersection.isEmpty():
        return 0
    return intersection.width() * intersection.height()


def _contains_rect(container: QRect, rect: QRect) -> bool:
    return container.contains(rect.topLeft()) and container.contains(rect.bottomRight())
