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

from PyQt6.QtWidgets import QApplication

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.main_window import MainWindow


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

    logger.info("Starting XBrainLab (PyQt6)...")
    app = QApplication(sys.argv)

    if args.tool_debug:
        logger.info(f"Tool Debug Mode enabled. Script: {args.tool_debug}")
        app.setProperty("tool_debug_script", args.tool_debug)

    app.setStyle("Fusion")

    study = Study()

    window = MainWindow(study)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
