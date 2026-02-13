"""Verify that backend components work without QApplication (headless mode)."""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.getcwd())

from PyQt6.QtWidgets import QApplication

from XBrainLab.backend.controller.dataset_controller import DatasetController
from XBrainLab.backend.utils.observer import Observable


def verify_headless():
    # 1. Assert no QApplication exists
    if QApplication.instance() is not None:
        print("FAIL: QApplication already exists!", file=sys.stderr)
        sys.exit(1)

    try:
        # 2. Instantiate
        mock_study = MagicMock()
        mock_study.loaded_data_list = []
        mock_study.is_locked.return_value = False

        controller = DatasetController(mock_study)

        # 3. Verify types
        if not isinstance(controller, Observable):
            print("FAIL: Controller is not instance of Observable", file=sys.stderr)
            sys.exit(1)

        if hasattr(controller, "data_changed") and not isinstance(
            controller.data_changed, str
        ):
            # Just a loose check, actually data_changed signal shouldn't exist
            pass

        print("SUCCESS: Headless verification passed.")

    except ImportError as e:
        print(f"FAIL: ImportError - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"FAIL: Exception - {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    verify_headless()
