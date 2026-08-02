"""Tests for startup splash placement and main-window presentation."""

import inspect

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMainWindow

from run import (
    _create_centered_splash,
    _create_splash_pixmap,
    _present_main_window,
    _show_centered_splash,
    main,
)


class _SplashStub:
    def __init__(self) -> None:
        self.finished_with = None

    def finish(self, window) -> None:
        self.finished_with = window


def test_splash_pixmap_contains_branded_loading_text(qapp):
    pixmap = _create_splash_pixmap()
    image = pixmap.toImage()
    background = image.pixelColor(20, 20)
    changed_pixels = 0

    for x in range(image.width()):
        for y in range(image.height()):
            if image.pixelColor(x, y) != background:
                changed_pixels += 1

    assert changed_pixels > 1000
    assert image.pixelColor(image.width() // 2, 3) == QColor("#0e7ac4")


def test_splash_is_centered_before_show(qapp, qtbot):
    splash = _create_centered_splash(qapp, saved_geometry=None)
    qtbot.addWidget(splash)

    screen = qapp.primaryScreen()
    available = screen.availableGeometry()
    center = splash.geometry().center()

    assert not splash.isVisible()
    assert abs(center.x() - available.center().x()) <= 1
    assert abs(center.y() - available.center().y()) <= 1


def test_splash_is_recentered_after_show(qapp, qtbot):
    splash = _create_centered_splash(qapp, saved_geometry=None)
    qtbot.addWidget(splash)

    screen = qapp.primaryScreen()
    available = screen.availableGeometry()
    splash.move(available.topLeft())

    _show_centered_splash(qapp, splash, paint_wait_ms=0)

    center = splash.geometry().center()
    assert splash.isVisible()
    assert abs(center.x() - available.center().x()) <= 1
    assert abs(center.y() - available.center().y()) <= 1


def test_splash_window_grab_contains_branding(qapp, qtbot):
    splash = _create_centered_splash(qapp, saved_geometry=None)
    qtbot.addWidget(splash)

    _show_centered_splash(qapp, splash, paint_wait_ms=0)

    image = splash.grab().toImage()
    background = image.pixelColor(20, 20)
    changed_pixels = 0
    for x in range(image.width()):
        for y in range(image.height()):
            if image.pixelColor(x, y) != background:
                changed_pixels += 1

    assert changed_pixels > 1000
    assert image.pixelColor(image.width() // 2, 3) == QColor("#0e7ac4")


def test_main_window_is_presented_after_splash_finishes(qapp, qtbot, monkeypatch):
    window = QMainWindow()
    qtbot.addWidget(window)
    splash = _SplashStub()
    calls: list[str] = []
    original_raise = window.raise_
    original_activate = window.activateWindow

    def record_raise() -> None:
        calls.append("raise")
        original_raise()

    def record_activate() -> None:
        calls.append("activate")
        original_activate()

    monkeypatch.setattr(window, "raise_", record_raise)
    monkeypatch.setattr(window, "activateWindow", record_activate)

    _present_main_window(qapp, splash, window)
    qtbot.waitUntil(lambda: calls.count("activate") >= 2, timeout=1_000)

    assert window.isVisible()
    assert qapp.activeWindow() is window
    assert splash.finished_with is window
    assert calls[:2] == ["raise", "activate"]


def test_main_drains_qt_runtime_after_event_loop_before_exiting():
    source = inspect.getsource(main)

    assert "raise SystemExit(run_qt_event_loop(app))" in source
    assert "sys.exit(app.exec())" not in source
