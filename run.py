"""Entry point for the XBrainLab desktop application.

Launches the PyQt6-based GUI, optionally accepting a ``--tool-debug``
argument that feeds a JSON script into the tool-debug subsystem.

Usage::

    python run.py
    python run.py --tool-debug path/to/script.json
"""

import argparse
import os
import sys

# Ensure the project root is importable when running the script directly.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QApplication, QSplashScreen


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
    args = parser.parse_args()

    app = QApplication(sys.argv)

    # --- Splash Screen (shown while heavy imports load) ---
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QPixmap

    pixmap = QPixmap(QSize(420, 200))
    pixmap.fill(QColor("#1e1e1e"))
    splash = _Splash(pixmap)
    splash.show()
    app.processEvents()

    # --- Heavy imports deferred until after splash is visible ---
    from XBrainLab.backend.study import Study
    from XBrainLab.backend.utils.logger import logger
    from XBrainLab.ui.main_window import MainWindow

    logger.info("Starting XBrainLab (PyQt6)...")

    if args.tool_debug:
        logger.info(f"Tool Debug Mode enabled. Script: {args.tool_debug}")
        app.setProperty("tool_debug_script", args.tool_debug)

    app.setStyle("Fusion")

    study = Study()

    window = MainWindow(study)
    window.show()
    splash.finish(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
