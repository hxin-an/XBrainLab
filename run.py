"""Entry point for the XBrainLab desktop application.

Launches the PyQt6-based GUI, optionally accepting CLI arguments for
tool debugging and model selection.

Usage::

    python run.py
    python run.py --tool-debug path/to/script.json
    python run.py --model local
"""

import argparse
import os
import sys
from time import monotonic, sleep

# Ensure the project root is importable when running the script directly.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from PyQt6.QtCore import QSettings, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from XBrainLab.ui.window_placement import (
    center_widget_on_screen,
    choose_screen_for_saved_geometry,
    remember_startup_screen,
    screen_geometry_diagnostic_lines,
    startup_geometry_diagnostics_enabled,
    startup_screen_hint,
    widget_geometry_diagnostic_line,
)


class _Splash(QWidget):
    """Branded startup window shown while the heavier UI stack imports."""

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__(
            None,
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._pixmap = pixmap
        self.setObjectName("XBrainLabStartupSplash")
        self.setWindowTitle("XBrainLab")
        self.setFixedSize(pixmap.size())
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        _ = event
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()

    def finish(self, window: QWidget) -> None:
        """Match QSplashScreen.finish enough for the startup path."""
        _ = window
        self.hide()
        self.deleteLater()


def _create_splash_pixmap() -> QPixmap:
    """Create the splash pixmap without importing the heavier UI stack."""
    pixmap = QPixmap(QSize(420, 200))
    pixmap.fill(QColor("#22262b"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.fillRect(0, 0, pixmap.width(), 6, QColor("#0e7ac4"))
    painter.fillRect(0, pixmap.height() - 2, pixmap.width(), 2, QColor("#333942"))
    painter.setPen(QPen(QColor("#4a5664"), 1))
    painter.drawRect(pixmap.rect().adjusted(0, 0, -1, -1))

    painter.setPen(QColor("#f1f1f1"))
    painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
    painter.drawText(
        pixmap.rect().adjusted(0, -18, 0, -18),
        Qt.AlignmentFlag.AlignCenter,
        "XBrainLab",
    )
    painter.setPen(QColor("#a0a0a0"))
    painter.setFont(QFont("Segoe UI", 11))
    painter.drawText(
        pixmap.rect().adjusted(0, 118, 0, 0),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        "Loading...",
    )
    painter.end()
    return pixmap


def _flush_splash_paint(
    app: QApplication,
    splash: _Splash,
    *,
    paint_wait_ms: int = 220,
) -> None:
    """Force early splash painting before imports block the Qt event loop."""
    splash.raise_()
    splash.activateWindow()
    splash.repaint()
    app.processEvents()
    deadline = monotonic() + max(0, paint_wait_ms) / 1000
    while monotonic() < deadline:
        splash.repaint()
        app.processEvents()
        sleep(0.01)


def _create_centered_splash(app: QApplication, saved_geometry=None) -> _Splash:
    """Create a splash centered on the same startup screen as MainWindow."""
    splash = _Splash(_create_splash_pixmap())
    target_screen = choose_screen_for_saved_geometry(saved_geometry)
    remember_startup_screen(target_screen)
    center_widget_on_screen(splash, target_screen)
    app.processEvents()
    return splash


def _show_centered_splash(
    app: QApplication,
    splash: _Splash,
    *,
    paint_wait_ms: int = 220,
) -> None:
    """Show the splash and recenter after the window manager assigns a frame."""
    splash.show()
    center_widget_on_screen(splash, startup_screen_hint() or app.primaryScreen())
    _flush_splash_paint(app, splash, paint_wait_ms=paint_wait_ms)


def main() -> None:
    """Parse CLI arguments, create the application, and show the main window.

    The function initialises a :class:`~XBrainLab.backend.study.Study`,
    builds the :class:`~XBrainLab.ui.main_window.MainWindow`, and enters
    the Qt event loop.  It calls ``sys.exit`` when the window is closed.
    """
    parser = argparse.ArgumentParser(description="XBrainLab Application")
    parser.add_argument(
        "--tool-debug", type=str, help="Path to tool debug script (JSON)"
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["local"],
        help="Use the local-only assistant runtime for this session.",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)

    # --- Splash Screen (shown while heavy imports load) ---
    settings = QSettings("XBrainLab", "XBrainLab")
    splash = _create_centered_splash(app, settings.value("main_window/geometry", None))
    _show_centered_splash(app, splash)

    # --- Heavy imports deferred until after splash is visible ---
    from XBrainLab.backend.study import Study
    from XBrainLab.backend.utils.logger import logger
    from XBrainLab.ui.main_window import MainWindow

    logger.info("Starting XBrainLab (PyQt6)...")
    if startup_geometry_diagnostics_enabled():
        logger.info(
            "Startup geometry diagnostics enabled with XBRAINLAB_STARTUP_DIAGNOSTICS=1"
        )
        for line in screen_geometry_diagnostic_lines():
            logger.info(line)
        logger.info(widget_geometry_diagnostic_line("splash.after_show", splash))

    if args.tool_debug:
        logger.info("Tool Debug Mode enabled. Script: %s", args.tool_debug)
        app.setProperty("tool_debug_script", args.tool_debug)

    # Apply the local-only model override for this session only (not persisted)
    if args.model:
        app.setProperty("model_override", args.model)
        logger.info("CLI override: inference mode set to '%s'", args.model)

    app.setStyle("Fusion")

    study = Study()

    window = MainWindow(study)
    window.show()
    if startup_geometry_diagnostics_enabled():
        logger.info(widget_geometry_diagnostic_line("main_window.after_show", window))
    splash.finish(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
