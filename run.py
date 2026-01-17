import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from PyQt6.QtWidgets import QApplication

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.main_window import MainWindow


def main():
    logger.info("Starting XBrainLab (PyQt6)...")
    app = QApplication(sys.argv)

    # Apply global style (optional)
    app.setStyle("Fusion")

    # Initialize Study
    # from XBrainLab.backend.study import Study

    study = Study()

    window = MainWindow(study)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
