"""Window geometry product-shell regression tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QRect, Qt

from XBrainLab.ui.main_window import MainWindow


class _FakeSettings:
    def __init__(self, saved_geometry=None):
        self.values: dict[str, object] = {}
        if saved_geometry is not None:
            self.values["main_window/geometry"] = saved_geometry
        self.removed_keys: list[str] = []

    def value(self, key: str, default=None):
        return self.values.get(key, default)

    def setValue(self, key: str, value) -> None:
        self.values[key] = value

    def remove(self, key: str) -> None:
        self.removed_keys.append(key)
        self.values.pop(key, None)


def _make_lightweight_window(qtbot, settings):
    with (
        patch(
            "XBrainLab.ui.window_geometry_lifecycle.QSettings",
            return_value=settings,
        ),
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(MagicMock())
    qtbot.addWidget(window)
    return window


def _make_normal_lightweight_window(qtbot, settings):
    window = _make_lightweight_window(qtbot, settings)
    window.setWindowState(Qt.WindowState.WindowNoState)
    return window


def _healthy_user_geometry(window: MainWindow) -> QRect:
    geometry = window.window_geometry
    policy = geometry.policy
    available = geometry.available_screen_geometry()
    width = min(
        max(policy.minimum_size.width(), available.width() // 2),
        available.width() - (policy.edge_margin * 2),
    )
    height = min(
        max(policy.minimum_size.height(), available.height() // 2),
        available.height() - policy.top_drag_margin - policy.bottom_margin,
    )
    width = max(min(width, available.width()), 1)
    height = max(min(height, available.height()), 1)
    x, y = geometry.bounded_position(
        available,
        width,
        height,
        available.left() + max((available.width() - width) // 3, 0),
        available.top() + policy.top_drag_margin + 32,
    )
    return QRect(x, y, width, height)


def _default_centered_geometry(window: MainWindow) -> QRect:
    geometry = window.window_geometry
    available = geometry.available_screen_geometry()
    size = geometry.default_window_size()
    width = min(size.width(), available.width())
    height = min(size.height(), available.height())
    x = available.left() + max((available.width() - width) // 2, 0)
    y = available.top() + max((available.height() - height) // 2, 0)
    x, y = geometry.bounded_position(available, width, height, x, y)
    return QRect(x, y, width, height)


def test_top_navigation_uses_readable_selector_when_width_is_constrained(qtbot):
    window = _make_lightweight_window(qtbot, _FakeSettings())

    window.top_bar.resize(window.COMPACT_NAV_BREAKPOINT - 1, 50)
    window._update_navigation_layout()

    assert window.compact_nav_combo.isVisibleTo(window.top_bar)
    assert [button.isVisibleTo(window.top_bar) for button in window.nav_btns] == [
        False,
    ] * 5
    assert [
        window.compact_nav_combo.itemText(index)
        for index in range(window.compact_nav_combo.count())
    ] == ["Dataset", "Preprocess", "Training", "Evaluation", "Visualization"]

    window.top_bar.resize(window.COMPACT_NAV_BREAKPOINT + 1, 50)
    window._update_navigation_layout()

    assert not window.compact_nav_combo.isVisible()
    assert all(button.isVisibleTo(window.top_bar) for button in window.nav_btns)


def test_top_navigation_reacts_when_a_dock_reduces_central_width(qtbot):
    window = _make_lightweight_window(qtbot, _FakeSettings())

    window.top_bar.resize(window.COMPACT_NAV_BREAKPOINT + 1, 50)
    qtbot.waitUntil(lambda: not window.compact_nav_combo.isVisible())

    window.top_bar.resize(window.COMPACT_NAV_BREAKPOINT - 1, 50)
    qtbot.waitUntil(lambda: window.compact_nav_combo.isVisibleTo(window.top_bar))

    assert not any(button.isVisibleTo(window.top_bar) for button in window.nav_btns)


def test_first_launch_window_is_on_available_screen(qtbot):
    window = _make_lightweight_window(qtbot, _FakeSettings())

    owner = window.window_geometry
    available = owner.available_screen_geometry()
    geometry = window.geometry()
    _min_x, _max_x, min_y, _max_y = owner.position_bounds(
        available,
        geometry.width(),
        geometry.height(),
        screen_geometry=owner.full_screen_geometry(),
    )

    assert available.contains(geometry.topLeft())
    assert available.contains(geometry.bottomRight())
    assert geometry.y() >= min_y
    assert geometry.center().y() > available.center().y() - 2
    assert owner.is_current_geometry_usable()
    assert window.isMaximized()
    assert not window.isFullScreen()
    assert not window.windowFlags() & Qt.WindowType.FramelessWindowHint


@pytest.mark.parametrize("anchor", ["left", "center", "right"])
def test_saved_top_edge_window_geometry_is_reset_and_recentered(qtbot, anchor):
    seed = _make_normal_lightweight_window(qtbot, _FakeSettings())
    policy = seed.window_geometry.policy
    available = seed.window_geometry.available_screen_geometry()
    width = policy.minimum_size.width()
    if anchor == "left":
        x = available.left()
    elif anchor == "center":
        x = available.left() + max((available.width() - width) // 2, 0)
    else:
        x = available.right() - width + 1
    seed.setGeometry(
        QRect(
            x,
            available.top(),
            width,
            policy.minimum_size.height(),
        )
    )
    saved_geometry = seed.saveGeometry()
    seed.close()

    settings = _FakeSettings(saved_geometry)
    window = _make_lightweight_window(qtbot, settings)

    assert window.isMaximized()
    assert not window.isFullScreen()
    assert window.window_geometry.is_current_geometry_usable()
    assert settings.removed_keys == ["main_window/geometry"]


def test_frame_geometry_above_available_top_is_unusable(qtbot):
    window = _make_normal_lightweight_window(qtbot, _FakeSettings())
    window.setGeometry(_healthy_user_geometry(window))

    available = window.window_geometry.available_screen_geometry()
    current = window.geometry()
    bad_frame = QRect(
        current.left(),
        available.top() - 8,
        current.width(),
        current.height() + 8,
    )

    with patch.object(window, "frameGeometry", return_value=bad_frame):
        assert not window.window_geometry.is_current_geometry_usable()


def test_saved_offscreen_window_geometry_is_reset_and_recentered(qtbot):
    seed = _make_normal_lightweight_window(qtbot, _FakeSettings())
    seed.setGeometry(QRect(-8000, -8000, 1800, 1200))
    saved_geometry = seed.saveGeometry()
    seed.close()

    settings = _FakeSettings(saved_geometry)
    window = _make_lightweight_window(qtbot, settings)

    available = window.window_geometry.available_screen_geometry()
    geometry = window.geometry()

    assert geometry == _default_centered_geometry(window)
    assert available.contains(geometry.topLeft())
    assert available.contains(geometry.bottomRight())
    assert geometry.width() <= available.width()
    assert geometry.height() <= available.height()
    assert window.isMaximized()
    assert not window.isFullScreen()
    assert window.window_geometry.is_current_geometry_usable()
    assert settings.removed_keys == ["main_window/geometry"]


def test_healthy_saved_window_geometry_is_preserved(qtbot):
    seed = _make_normal_lightweight_window(qtbot, _FakeSettings())
    seed.setGeometry(_healthy_user_geometry(seed))
    expected_geometry = seed.geometry()
    saved_geometry = seed.saveGeometry()
    seed.close()

    settings = _FakeSettings(saved_geometry)
    window = _make_lightweight_window(qtbot, settings)

    assert window.geometry() == expected_geometry
    assert not window.isMaximized()
    assert not window.isFullScreen()
    assert window.window_geometry.is_current_geometry_usable()
    assert settings.removed_keys == []


def test_close_event_discards_unusable_window_geometry(qtbot):
    settings = _FakeSettings()
    window = _make_normal_lightweight_window(qtbot, settings)
    policy = window.window_geometry.policy
    available = window.window_geometry.available_screen_geometry()
    window.setGeometry(
        QRect(
            available.left(),
            available.top(),
            policy.minimum_size.width(),
            policy.minimum_size.height(),
        )
    )

    window.close()

    assert "main_window/geometry" not in settings.values
    assert settings.removed_keys == ["main_window/geometry"]


def test_main_window_can_resize_maximize_and_restore(qtbot):
    window = _make_lightweight_window(qtbot, _FakeSettings())
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(20)
    assert window.isMaximized()

    window.showNormal()
    qtbot.wait(50)
    policy = window.window_geometry.policy
    available = window.window_geometry.available_screen_geometry()
    target_width = max(
        window.minimumWidth(),
        min(960, available.width() - (policy.edge_margin * 2)),
    )
    target_height = max(
        window.minimumHeight(),
        min(
            620,
            available.height() - policy.top_drag_margin - policy.bottom_margin,
        ),
    )
    window.resize(target_width, target_height)
    qtbot.wait(20)
    assert window.width() == target_width
    assert window.height() == target_height

    window.showMaximized()
    qtbot.wait(50)
    assert window.isMaximized()

    window.showNormal()
    qtbot.wait(50)
    assert not window.isMaximized()
    assert window.width() >= window.minimumWidth()
    assert window.height() >= window.minimumHeight()


def test_show_event_schedules_immediate_and_delayed_geometry_recovery(qtbot):
    window = _make_lightweight_window(qtbot, _FakeSettings())
    with patch.object(
        window.window_geometry,
        "recover_if_needed",
    ) as recover_if_needed:
        window.show()
        qtbot.waitUntil(lambda: recover_if_needed.call_count == 2, timeout=1_000)

    assert [call.args[0] for call in recover_if_needed.call_args_list] == [
        "post_show_0ms",
        "post_show_250ms",
    ]


def test_delayed_recovery_recenters_late_top_edge_geometry(qtbot):
    window = _make_lightweight_window(qtbot, _FakeSettings())
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(20)
    window.showNormal()
    qtbot.wait(50)

    policy = window.window_geometry.policy
    available = window.window_geometry.available_screen_geometry()
    window.setGeometry(
        QRect(
            available.left(),
            available.top(),
            policy.minimum_size.width(),
            policy.minimum_size.height(),
        )
    )

    assert not window.window_geometry.is_current_geometry_usable()

    window.window_geometry.recover_if_needed("post_show_250ms")

    assert window.isMaximized()
    assert not window.isFullScreen()
    assert window.window_geometry.is_current_geometry_usable()
