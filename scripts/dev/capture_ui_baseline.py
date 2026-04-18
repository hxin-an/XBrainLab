#!/usr/bin/env python3
"""Capture a minimal UI baseline screenshot for XBrainLab.

This helper launches the real application stack, waits for the main window to
settle, and captures the rendered main-window widget into
``artifacts/ui/main-window-initial.png``.

Expected usage in WSL/headless environments:

    xvfb-run -a /home/administrator/.local/bin/poetry run python \
        scripts/dev/capture_ui_baseline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT / "artifacts" / "ui"
OUTPUT_PATH = ARTIFACTS_DIR / "main-window-initial.png"


def is_nearly_black(path: Path) -> bool:
    """Return True when the captured image contains almost no visible content."""
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        histogram = rgb.histogram()

    bright_pixels = 0
    total_pixels = sum(histogram[:256])
    for value in range(16, 256):
        bright_pixels += histogram[value]
        bright_pixels += histogram[256 + value]
        bright_pixels += histogram[512 + value]

    return total_pixels == 0 or bright_pixels < total_pixels * 0.01


def capture_window(app: QApplication, output_path: Path) -> int:
    """Launch the main window, grab it after paint, and save a screenshot."""
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    result: dict[str, int] = {"code": 3}

    study = Study()
    window = MainWindow(study)
    window.show()

    def _save_capture() -> None:
        app.processEvents()
        window.repaint()
        app.processEvents()

        pixmap = window.grab()
        if pixmap.isNull():
            print("Failed to grab the main window pixmap.", file=sys.stderr)
            result["code"] = 3
        elif not pixmap.save(str(output_path)):
            print("Failed to save the grabbed main window pixmap.", file=sys.stderr)
            result["code"] = 4
        elif is_nearly_black(output_path):
            print(
                "Captured screenshot is nearly all black; visual baseline is not usable yet.",
                file=sys.stderr,
            )
            result["code"] = 2
        else:
            print(f"Saved baseline screenshot to {output_path}")
            result["code"] = 0

        window.close()
        app.quit()

    QTimer.singleShot(2500, _save_capture)
    app.exec()
    return result["code"]


def main() -> int:
    """Launch the app briefly and save a screenshot of the main window."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    return capture_window(app, OUTPUT_PATH)


if __name__ == "__main__":
    raise SystemExit(main())
