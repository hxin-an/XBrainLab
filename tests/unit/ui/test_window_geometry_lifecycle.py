"""Focused tests for the main-window geometry lifecycle owner."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.ui.window_geometry_lifecycle import (
    WindowGeometryLifecycle,
    WindowGeometryPolicy,
)


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


def _make_owner(qtbot, settings: _FakeSettings):
    window = QMainWindow()
    qtbot.addWidget(window)
    owner = WindowGeometryLifecycle(
        window,
        settings_factory=lambda: settings,
    )
    window.setMinimumSize(owner.policy.minimum_size)
    return window, owner


def _healthy_geometry(owner: WindowGeometryLifecycle) -> QRect:
    available = owner.available_screen_geometry()
    policy = owner.policy
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
    x, y = owner.bounded_position(
        available,
        width,
        height,
        available.left() + max((available.width() - width) // 3, 0),
        available.top() + policy.top_drag_margin + 32,
    )
    return QRect(x, y, width, height)


def test_policy_is_immutable():
    policy = WindowGeometryPolicy()

    with pytest.raises(FrozenInstanceError):
        policy.edge_margin = 12  # type: ignore[misc]


def test_restore_initial_geometry_preserves_healthy_saved_window(qtbot):
    seed_settings = _FakeSettings()
    seed, seed_owner = _make_owner(qtbot, seed_settings)
    seed.setGeometry(_healthy_geometry(seed_owner))
    expected = seed.geometry()
    saved_geometry = seed.saveGeometry()
    seed.close()

    settings = _FakeSettings(saved_geometry)
    window, owner = _make_owner(qtbot, settings)

    assert owner.restore_initial_geometry() is True
    assert window.geometry() == expected
    assert not window.isMaximized()
    assert settings.removed_keys == []


def test_restore_initial_geometry_discards_unusable_saved_window(qtbot):
    seed_settings = _FakeSettings()
    seed, _seed_owner = _make_owner(qtbot, seed_settings)
    seed.setGeometry(QRect(-8000, -8000, 1800, 1200))
    saved_geometry = seed.saveGeometry()
    seed.close()

    settings = _FakeSettings(saved_geometry)
    window, owner = _make_owner(qtbot, settings)

    assert owner.restore_initial_geometry() is False
    assert window.isMaximized()
    assert owner.is_current_geometry_usable()
    assert settings.removed_keys == ["main_window/geometry"]


def test_handle_window_shown_runs_each_recovery_once(qtbot):
    window, owner = _make_owner(qtbot, _FakeSettings())
    recovery_labels: list[str] = []
    owner.recover_if_needed = recovery_labels.append  # type: ignore[method-assign]

    window.show()
    owner.handle_window_shown()
    owner.handle_window_shown()

    qtbot.waitUntil(lambda: len(recovery_labels) == 2, timeout=1_000)
    assert recovery_labels == ["post_show_0ms", "post_show_250ms"]


def test_pre_show_normal_override_is_not_replaced_by_startup_fallback(qtbot):
    window, owner = _make_owner(qtbot, _FakeSettings())
    assert owner.restore_initial_geometry() is False
    assert window.isMaximized()
    window.setWindowState(Qt.WindowState.WindowNoState)
    recovery_labels: list[str] = []
    owner.recover_if_needed = recovery_labels.append  # type: ignore[method-assign]

    owner.handle_window_shown()
    qtbot.wait(300)

    assert recovery_labels == []


def test_show_recovery_timer_does_not_touch_deleted_window(qtbot):
    window, owner = _make_owner(qtbot, _FakeSettings())
    recovery_labels: list[str] = []
    owner.recover_if_needed = recovery_labels.append  # type: ignore[method-assign]

    owner.handle_window_shown()
    sip.delete(window)
    qtbot.wait(300)

    assert recovery_labels == []


def test_persist_before_close_saves_usable_normal_geometry(qtbot):
    settings = _FakeSettings()
    window, owner = _make_owner(qtbot, settings)
    window.setGeometry(_healthy_geometry(owner))

    assert owner.persist_before_close() is True
    assert settings.values["main_window/geometry"] == window.saveGeometry()
    assert settings.removed_keys == []


def test_persist_before_close_ignores_deleted_qt_window(qtbot):
    window, owner = _make_owner(qtbot, _FakeSettings())

    with (
        patch.object(
            window,
            "isMaximized",
            side_effect=RuntimeError(
                "wrapped C/C++ object of type QMainWindow has been deleted"
            ),
        ),
        patch(
            "XBrainLab.ui.window_geometry_lifecycle.sip.isdeleted",
            side_effect=[False, False, True],
        ),
    ):
        assert owner.persist_before_close() is False


def test_maximized_window_is_not_persisted(qtbot):
    settings = _FakeSettings()
    window, owner = _make_owner(qtbot, settings)
    window.setWindowState(Qt.WindowState.WindowMaximized)

    assert owner.persist_before_close() is True
    assert settings.values == {}
