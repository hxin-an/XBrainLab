"""Tests for frame-aware multi-screen window placement helpers."""

from PyQt6.QtCore import QPoint, QRect, QSize

from XBrainLab.ui.window_placement import (
    FrameExtents,
    ScreenGeometry,
    bounded_window_position,
    choose_screen_index_for_rect,
    default_window_size_for_available,
    is_window_geometry_usable,
)


def _dual_screens() -> list[ScreenGeometry]:
    return [
        ScreenGeometry(
            available=QRect(0, 0, 1920, 1040),
            full=QRect(0, 0, 1920, 1080),
        ),
        ScreenGeometry(
            available=QRect(1920, 0, 1280, 984),
            full=QRect(1920, 0, 1280, 1024),
        ),
    ]


def test_choose_screen_prefers_restored_window_center_on_second_monitor():
    restored_top_edge = QRect(2200, 0, 760, 520)

    assert (
        choose_screen_index_for_rect(
            restored_top_edge,
            _dual_screens(),
            cursor_pos=QPoint(200, 200),
            primary_index=0,
        )
        == 1
    )


def test_choose_screen_falls_back_to_cursor_then_primary():
    offscreen = QRect(-8000, -8000, 760, 520)

    assert (
        choose_screen_index_for_rect(
            offscreen,
            _dual_screens(),
            cursor_pos=QPoint(2300, 400),
            primary_index=0,
        )
        == 1
    )
    assert (
        choose_screen_index_for_rect(
            offscreen,
            _dual_screens(),
            cursor_pos=QPoint(-1000, -1000),
            primary_index=0,
        )
        == 0
    )


def test_geometry_health_rejects_top_edge_and_frame_outside_screen():
    available = QRect(1920, 0, 1280, 984)
    full = QRect(1920, 0, 1280, 1024)
    min_size = QSize(760, 520)
    top_center = QRect(2180, 0, 760, 520)
    top_right = QRect(2440, 0, 760, 520)
    healthy = QRect(2180, 96, 760, 520)
    bad_frame = QRect(2172, -4, 776, 552)

    for client in (top_center, top_right):
        assert not is_window_geometry_usable(
            client,
            available_geometry=available,
            screen_geometry=full,
            min_size=min_size,
            edge_margin=16,
            top_drag_margin=48,
            bottom_margin=24,
        )
    assert not is_window_geometry_usable(
        healthy,
        available_geometry=available,
        screen_geometry=full,
        frame_geometry=bad_frame,
        min_size=min_size,
        edge_margin=16,
        top_drag_margin=48,
        bottom_margin=24,
    )


def test_bounded_position_preserves_native_titlebar_space():
    available = QRect(0, 0, 1280, 720)
    full = QRect(0, 0, 1280, 760)

    _x, y = bounded_window_position(
        available,
        760,
        520,
        0,
        0,
        edge_margin=16,
        top_drag_margin=48,
        bottom_margin=24,
        screen_geometry=full,
        frame_extents=FrameExtents(top=32),
    )

    assert y >= 48


def test_default_window_size_leaves_visual_centering_room_on_short_screen():
    size = default_window_size_for_available(
        QSize(1280, 800),
        QSize(760, 520),
        QRect(0, 0, 1366, 720),
        edge_margin=24,
        top_drag_margin=72,
        bottom_margin=48,
    )

    centered_y = (720 - size.height()) // 2

    assert size.height() < 720 - 72 - 48
    assert centered_y >= 72
