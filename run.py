import argparse
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from PyQt6.QtWidgets import QApplication

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.main_window import MainWindow


def main():
    # Parse CLI Arguments
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

    # Apply global style (optional)
    app.setStyle("Fusion")

    # Initialize Study
    # from XBrainLab.backend.study import Study

    study = Study()

    window = MainWindow(study)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
