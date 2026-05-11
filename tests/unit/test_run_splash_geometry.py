"""Tests for startup splash placement."""

from PyQt6.QtGui import QColor

from run import _create_centered_splash, _create_splash_pixmap, _show_centered_splash


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
