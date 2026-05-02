"""Tests for startup splash placement."""

from run import _create_centered_splash


def test_splash_is_centered_before_show(qapp, qtbot):
    splash = _create_centered_splash(qapp, saved_geometry=None)
    qtbot.addWidget(splash)

    screen = qapp.primaryScreen()
    available = screen.availableGeometry()
    center = splash.geometry().center()

    assert not splash.isVisible()
    assert abs(center.x() - available.center().x()) <= 1
    assert abs(center.y() - available.center().y()) <= 1
