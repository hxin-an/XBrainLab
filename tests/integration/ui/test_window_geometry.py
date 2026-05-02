"""Window geometry product-shell regression tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
        patch("XBrainLab.ui.main_window.QSettings", return_value=settings),
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(MagicMock())
    qtbot.addWidget(window)
    return window


def _healthy_user_geometry(window: MainWindow) -> QRect:
    available = window._available_screen_geometry()
    width = min(
        max(window.MIN_WINDOW_SIZE.width(), available.width() // 2),
        available.width() - (window.WINDOW_EDGE_MARGIN * 2),
    )
    height = min(
        max(window.MIN_WINDOW_SIZE.height(), available.height() // 2),
        available.height()
        - window.WINDOW_TOP_DRAG_MARGIN
        - window.WINDOW_BOTTOM_MARGIN,
    )
    width = max(min(width, available.width()), 1)
    height = max(min(height, available.height()), 1)
    x, y = window._bounded_window_position(
        available,
        width,
        height,
        available.left() + max((available.width() - width) // 3, 0),
        available.top() + window.WINDOW_TOP_DRAG_MARGIN + 32,
    )
    return QRect(x, y, width, height)


def _default_centered_geometry(window: MainWindow) -> QRect:
    available = window._available_screen_geometry()
    size = window._default_window_size_for_screen()
    width = min(size.width(), available.width())
    height = min(size.height(), available.height())
    x = available.left() + max((available.width() - width) // 2, 0)
    y = available.top() + max((available.height() - height) // 2, 0)
    x, y = window._bounded_window_position(available, width, height, x, y)
    return QRect(x, y, width, height)


def test_first_launch_window_is_on_available_screen(qtbot):
    window = _make_lightweight_window(qtbot, _FakeSettings())

    available = window._available_screen_geometry()
    geometry = window.geometry()

    assert available.contains(geometry.topLeft())
    assert available.contains(geometry.bottomRight())
    assert window._is_current_window_geometry_usable()
    assert not window.windowFlags() & Qt.WindowType.FramelessWindowHint


def test_saved_top_left_window_geometry_is_reset_and_recentered(qtbot):
    seed = _make_lightweight_window(qtbot, _FakeSettings())
    seed.setGeometry(
        QRect(
            seed._available_screen_geometry().left(),
            seed._available_screen_geometry().top(),
            seed.MIN_WINDOW_SIZE.width(),
            seed.MIN_WINDOW_SIZE.height(),
        )
    )
    saved_geometry = seed.saveGeometry()
    seed.close()

    settings = _FakeSettings(saved_geometry)
    window = _make_lightweight_window(qtbot, settings)

    assert window.geometry() == _default_centered_geometry(window)
    assert window._is_current_window_geometry_usable()
    assert settings.removed_keys == ["main_window/geometry"]


def test_saved_offscreen_window_geometry_is_reset_and_recentered(qtbot):
    seed = _make_lightweight_window(qtbot, _FakeSettings())
    seed.setGeometry(QRect(-8000, -8000, 1800, 1200))
    saved_geometry = seed.saveGeometry()
    seed.close()

    settings = _FakeSettings(saved_geometry)
    window = _make_lightweight_window(qtbot, settings)

    available = window._available_screen_geometry()
    geometry = window.geometry()

    assert geometry == _default_centered_geometry(window)
    assert available.contains(geometry.topLeft())
    assert available.contains(geometry.bottomRight())
    assert geometry.width() <= available.width()
    assert geometry.height() <= available.height()
    assert window._is_current_window_geometry_usable()
    assert settings.removed_keys == ["main_window/geometry"]


def test_healthy_saved_window_geometry_is_preserved(qtbot):
    seed = _make_lightweight_window(qtbot, _FakeSettings())
    seed.setGeometry(_healthy_user_geometry(seed))
    expected_geometry = seed.geometry()
    saved_geometry = seed.saveGeometry()
    seed.close()

    settings = _FakeSettings(saved_geometry)
    window = _make_lightweight_window(qtbot, settings)

    assert window.geometry() == expected_geometry
    assert window._is_current_window_geometry_usable()
    assert settings.removed_keys == []


def test_close_event_discards_unusable_window_geometry(qtbot):
    settings = _FakeSettings()
    window = _make_lightweight_window(qtbot, settings)
    available = window._available_screen_geometry()
    window.setGeometry(
        QRect(
            available.left(),
            available.top(),
            window.MIN_WINDOW_SIZE.width(),
            window.MIN_WINDOW_SIZE.height(),
        )
    )

    with patch.object(MainWindow, "_window_settings", return_value=settings):
        window.close()

    assert "main_window/geometry" not in settings.values
    assert settings.removed_keys == ["main_window/geometry"]


def test_main_window_can_resize_maximize_and_restore(qtbot):
    window = _make_lightweight_window(qtbot, _FakeSettings())
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(20)

    available = window._available_screen_geometry()
    target_width = min(
        960,
        available.width() - (window.WINDOW_EDGE_MARGIN * 2),
    )
    target_height = min(
        620,
        available.height()
        - window.WINDOW_TOP_DRAG_MARGIN
        - window.WINDOW_BOTTOM_MARGIN,
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
