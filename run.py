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

# Ensure the project root is importable when running the script directly.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from PyQt6.QtCore import QSettings, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from XBrainLab.ui.window_placement import (
    center_widget_on_screen,
    choose_screen_for_saved_geometry,
    remember_startup_screen,
    screen_geometry_diagnostic_lines,
    startup_geometry_diagnostics_enabled,
    startup_screen_hint,
    widget_geometry_diagnostic_line,
)


class _Splash(QSplashScreen):
    """Minimal branded splash screen shown during startup."""

    def drawContents(self, painter: QPainter) -> None:  # noqa: N802
        painter.setPen(QColor("#cccccc"))
        painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "XBrainLab")
        painter.setPen(QColor("#888888"))
        painter.setFont(QFont("Segoe UI", 11))
        painter.drawText(
            self.rect().adjusted(0, 50, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "Loading…",
        )


def _create_splash_pixmap() -> QPixmap:
    """Create the splash pixmap without importing the heavier UI stack."""
    pixmap = QPixmap(QSize(420, 200))
    pixmap.fill(QColor("#1e1e1e"))
    return pixmap


def _create_centered_splash(app: QApplication, saved_geometry=None) -> _Splash:
    """Create a splash centered on the same startup screen as MainWindow."""
    splash = _Splash(_create_splash_pixmap())
    target_screen = choose_screen_for_saved_geometry(saved_geometry)
    remember_startup_screen(target_screen)
    center_widget_on_screen(splash, target_screen)
    app.processEvents()
    return splash


def _show_centered_splash(app: QApplication, splash: _Splash) -> None:
    """Show the splash and recenter after the window manager assigns a frame."""
    splash.show()
    center_widget_on_screen(splash, startup_screen_hint() or app.primaryScreen())
    app.processEvents()


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
