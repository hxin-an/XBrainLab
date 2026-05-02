"""Window geometry product-shell regression tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QRect

from XBrainLab.ui.main_window import MainWindow


class _FakeSettings:
    def __init__(self, saved_geometry=None):
        self.saved_geometry = saved_geometry
        self.values: dict[str, object] = {}

    def value(self, key: str, default=None):
        if key == "main_window/geometry":
            return self.saved_geometry
        return self.values.get(key, default)

    def setValue(self, key: str, value) -> None:
        self.values[key] = value


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


def test_first_launch_window_is_on_available_screen(qtbot):
    window = _make_lightweight_window(qtbot, _FakeSettings())

    available = window._available_screen_geometry()
    geometry = window.geometry()

    assert available.contains(geometry.topLeft())
    assert available.contains(geometry.bottomRight())


def test_restored_offscreen_window_is_clamped_to_available_screen(qtbot):
    seed = _make_lightweight_window(qtbot, _FakeSettings())
    seed.setGeometry(QRect(-8000, -8000, 1800, 1200))
    saved_geometry = seed.saveGeometry()
    seed.close()

    window = _make_lightweight_window(qtbot, _FakeSettings(saved_geometry))

    available = window._available_screen_geometry()
    geometry = window.geometry()

    assert available.contains(geometry.topLeft())
    assert available.contains(geometry.bottomRight())
    assert geometry.width() <= available.width()
    assert geometry.height() <= available.height()


def test_main_window_can_resize_maximize_and_restore(qtbot):
    window = _make_lightweight_window(qtbot, _FakeSettings())
    window.show()
    qtbot.waitExposed(window)

    available = window._available_screen_geometry()
    target_width = min(960, available.width())
    target_height = min(620, available.height())
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
