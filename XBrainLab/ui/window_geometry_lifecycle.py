"""Own the restore, post-show recovery, and persistence of window geometry."""

from __future__ import annotations

import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QObject, QRect, QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QScreen
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.window_placement import (
    bounded_window_position,
    choose_screen_for_rect,
    default_window_size_for_available,
    frame_extents_for,
    is_window_geometry_usable,
    screen_geometry_for,
    startup_geometry_diagnostics_enabled,
    startup_screen_hint,
    usable_window_position_bounds,
    widget_geometry_diagnostic_line,
)


@dataclass(frozen=True)
class WindowGeometryPolicy:
    """Immutable geometry and persistence policy for the product shell."""

    default_size: QSize = field(default_factory=lambda: QSize(1280, 800))
    minimum_size: QSize = field(default_factory=lambda: QSize(760, 520))
    edge_margin: int = 24
    top_drag_margin: int = 72
    bottom_margin: int = 48
    settings_key: str = "main_window/geometry"
    immediate_recovery_ms: int = 0
    delayed_recovery_ms: int = 250


def _default_settings() -> QSettings:
    return QSettings("XBrainLab", "XBrainLab")


class WindowGeometryLifecycle(QObject):
    """Coordinate geometry side effects for one top-level window."""

    def __init__(
        self,
        window: QMainWindow,
        *,
        policy: WindowGeometryPolicy | None = None,
        settings_factory: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__(window)
        self._window_ref = weakref.ref(window)
        self._policy = policy or WindowGeometryPolicy()
        self._settings = (settings_factory or _default_settings)()
        self._post_show_recovery_scheduled = False
        self._startup_fallback_applied = False

        self._immediate_recovery_timer = QTimer(self)
        self._immediate_recovery_timer.setSingleShot(True)
        self._immediate_recovery_timer.timeout.connect(self._recover_immediately)

        self._delayed_recovery_timer = QTimer(self)
        self._delayed_recovery_timer.setSingleShot(True)
        self._delayed_recovery_timer.timeout.connect(self._recover_after_delay)

    @property
    def policy(self) -> WindowGeometryPolicy:
        """Return the immutable geometry policy."""
        return self._policy

    def restore_initial_geometry(self) -> bool:
        """Restore healthy geometry or place a maximized draggable fallback.

        Returns:
            ``True`` only when saved geometry was restored and accepted.
        """
        window = self._window_if_alive()
        if window is None:
            return False
        window.setMinimumSize(self._policy.minimum_size)

        settings = self._settings
        saved_geometry = settings.value(self._policy.settings_key, None)
        self._log_message(
            "restore start saved_geometry=%s",
            "yes" if saved_geometry is not None else "no",
        )
        restored = False
        if saved_geometry is not None:
            try:
                restored = bool(window.restoreGeometry(saved_geometry))
            except TypeError:
                logger.debug("Ignoring invalid saved main-window geometry")
        self._log_message("restoreGeometry result=%s", restored)

        target_screen = self.target_screen()
        if restored and self.is_current_geometry_usable(target_screen):
            self._startup_fallback_applied = False
            self._log_geometry("main_window.after_restore_healthy")
            return True

        if saved_geometry is not None:
            logger.info("Resetting unusable saved main-window geometry")
            settings.remove(self._policy.settings_key)
            self._log_message("removed unusable saved geometry")

        self.place_maximized_fallback(target_screen)
        self._startup_fallback_applied = True
        self._log_geometry("main_window.after_maximized_fallback")
        return False

    def handle_window_shown(self) -> None:
        """Schedule frame-aware recovery once after the native window is shown."""
        window = self._window_if_alive()
        if self._post_show_recovery_scheduled or window is None:
            return
        self._post_show_recovery_scheduled = True
        if self._startup_fallback_applied and not window.isMaximized():
            self._log_message("pre-show normal geometry override accepted")
            return
        self._log_geometry("main_window.show_event")
        self._immediate_recovery_timer.start(
            self._policy.immediate_recovery_ms,
        )
        self._delayed_recovery_timer.start(
            self._policy.delayed_recovery_ms,
        )

    def persist_before_close(self) -> bool:
        """Persist usable normal geometry without touching a deleted Qt window."""
        window = self._window_if_alive()
        if window is None:
            return False
        try:
            maximized = window.isMaximized()
            full_screen = window.isFullScreen()
        except RuntimeError:
            if sip.isdeleted(window):
                logger.debug("Skipping geometry persistence for a deleted window")
                return False
            raise

        if maximized or full_screen:
            return True

        settings = self._settings
        if self.is_current_geometry_usable():
            settings.setValue(self._policy.settings_key, window.saveGeometry())
        else:
            logger.info("Discarding unusable main-window geometry on close")
            settings.remove(self._policy.settings_key)
        return True

    def recover_if_needed(self, recovery_label: str = "post_show") -> bool:
        """Recover unusable post-show geometry and report whether it changed."""
        if self._window_if_alive() is None:
            return False
        self._log_geometry(f"main_window.{recovery_label}.before")
        if self.is_current_geometry_usable():
            self._log_message("%s usable=True", recovery_label)
            return False
        logger.info(
            "Recovering unusable main-window geometry after show (%s)",
            recovery_label,
        )
        self.place_maximized_fallback()
        self._log_geometry(f"main_window.{recovery_label}.after")
        return True

    def place_maximized_fallback(self, screen: QScreen | None = None) -> bool:
        """Place a normal window safely, then start it maximized."""
        window = self._window_if_alive()
        if window is None:
            return False
        window.setWindowState(Qt.WindowState.WindowNoState)
        self._place_default_window(screen)
        window.setWindowState(Qt.WindowState.WindowMaximized)
        return True

    def default_window_size(self, screen: QScreen | None = None) -> QSize:
        """Return a screen-safe default client size."""
        return default_window_size_for_available(
            self._policy.default_size,
            self._policy.minimum_size,
            self.available_screen_geometry(screen),
            edge_margin=self._policy.edge_margin,
            top_drag_margin=self._policy.top_drag_margin,
            bottom_margin=self._policy.bottom_margin,
        )

    def available_screen_geometry(self, screen: QScreen | None = None) -> QRect:
        """Return available geometry for the selected or current screen."""
        target_screen = screen or self.target_screen()
        return screen_geometry_for(
            target_screen,
            self._policy.default_size,
        ).available

    def full_screen_geometry(self, screen: QScreen | None = None) -> QRect:
        """Return full geometry for frame-aware placement."""
        target_screen = screen or self.target_screen()
        return screen_geometry_for(
            target_screen,
            self._policy.default_size,
        ).full

    def target_screen(self) -> QScreen | None:
        """Choose a screen from current geometry, startup hint, cursor, or primary."""
        window = self._window_if_alive()
        if window is None:
            return None
        candidate = self._window_rect_for_screen_choice(window)
        if not window.isVisible() and self._is_unshown_default_rect(candidate):
            candidate = None
        return choose_screen_for_rect(
            candidate,
            preferred_screen=startup_screen_hint(),
        )

    def is_current_geometry_usable(self, screen: QScreen | None = None) -> bool:
        """Return whether current geometry is safe to restore or persist."""
        window = self._window_if_alive()
        if window is None or window.isFullScreen():
            return False
        if window.isMaximized():
            return True

        target_screen = screen or self.target_screen()
        return is_window_geometry_usable(
            window.geometry(),
            available_geometry=self.available_screen_geometry(target_screen),
            screen_geometry=self.full_screen_geometry(target_screen),
            frame_geometry=window.frameGeometry(),
            min_size=self._policy.minimum_size,
            edge_margin=self._policy.edge_margin,
            top_drag_margin=self._policy.top_drag_margin,
            bottom_margin=self._policy.bottom_margin,
        )

    def bounded_position(
        self,
        available: QRect,
        width: int,
        height: int,
        preferred_x: int,
        preferred_y: int,
        *,
        screen_geometry: QRect | None = None,
    ) -> tuple[int, int]:
        """Clamp a client position inside frame-aware draggable bounds."""
        window = self._window_if_alive()
        frame_extents = (
            frame_extents_for(window.geometry(), window.frameGeometry())
            if window is not None
            else None
        )
        return bounded_window_position(
            available,
            width,
            height,
            preferred_x,
            preferred_y,
            edge_margin=self._policy.edge_margin,
            top_drag_margin=self._policy.top_drag_margin,
            bottom_margin=self._policy.bottom_margin,
            screen_geometry=screen_geometry,
            frame_extents=frame_extents,
        )

    def position_bounds(
        self,
        available: QRect,
        width: int,
        height: int,
        *,
        screen_geometry: QRect | None = None,
    ) -> tuple[int, int, int, int]:
        """Return frame-aware client bounds that keep the title bar reachable."""
        window = self._window_if_alive()
        frame_extents = (
            frame_extents_for(window.geometry(), window.frameGeometry())
            if window is not None
            else None
        )
        return usable_window_position_bounds(
            available,
            width,
            height,
            edge_margin=self._policy.edge_margin,
            top_drag_margin=self._policy.top_drag_margin,
            bottom_margin=self._policy.bottom_margin,
            screen_geometry=screen_geometry,
            frame_extents=frame_extents,
        )

    def _place_default_window(self, screen: QScreen | None = None) -> None:
        window = self._window_if_alive()
        if window is None:
            return
        target_screen = screen or self.target_screen()
        window.resize(self.default_window_size(target_screen))
        self._center_window(target_screen)

    def _center_window(self, screen: QScreen | None = None) -> None:
        window = self._window_if_alive()
        if window is None:
            return
        target_screen = screen or self.target_screen()
        available = self.available_screen_geometry(target_screen)
        full = self.full_screen_geometry(target_screen)
        width = min(window.width(), available.width())
        height = min(window.height(), available.height())
        x = available.left() + max((available.width() - width) // 2, 0)
        y = available.top() + max((available.height() - height) // 2, 0)
        x, y = self.bounded_position(
            available,
            width,
            height,
            x,
            y,
            screen_geometry=full,
        )
        window.setGeometry(QRect(x, y, width, height))

    @staticmethod
    def _window_rect_for_screen_choice(window: QMainWindow) -> QRect | None:
        frame = window.frameGeometry()
        if frame.isValid():
            return frame
        current = window.geometry()
        if current.isValid():
            return current
        return None

    @staticmethod
    def _is_unshown_default_rect(candidate: QRect | None) -> bool:
        return bool(
            candidate is not None
            and candidate.isValid()
            and candidate.x() == 0
            and candidate.y() == 0
        )

    def _recover_immediately(self) -> None:
        self.recover_if_needed("post_show_0ms")

    def _recover_after_delay(self) -> None:
        self.recover_if_needed("post_show_250ms")

    def _window_if_alive(self) -> QMainWindow | None:
        if sip.isdeleted(self):
            return None
        window = self._window_ref()
        if window is None or sip.isdeleted(window):
            return None
        return window

    def _log_geometry(self, label: str) -> None:
        window = self._window_if_alive()
        if window is not None and startup_geometry_diagnostics_enabled():
            logger.info(widget_geometry_diagnostic_line(label, window))

    @staticmethod
    def _log_message(message: str, *args: object) -> None:
        if startup_geometry_diagnostics_enabled():
            logger.info("startup geometry: " + message, *args)
