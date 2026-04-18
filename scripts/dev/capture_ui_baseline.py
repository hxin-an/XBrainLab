#!/usr/bin/env python3
"""Capture a minimal UI baseline screenshot set for XBrainLab.

This helper launches the real application stack, waits for the main window to
settle, and captures the rendered main-window widget across the shell and the
five primary panels into ``artifacts/ui/``.

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
CAPTURE_STEPS = [
    ("main-window-initial.png", None),
    ("panel-dataset.png", 0),
    ("panel-preprocess.png", 1),
    ("panel-training.png", 2),
    ("panel-evaluation.png", 3),
    ("panel-visualization.png", 4),
]


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


def _capture_current_window(window, output_path: Path) -> int:
    """Grab the current rendered window and write it to ``output_path``."""
    pixmap = window.grab()
    if pixmap.isNull():
        print("Failed to grab the main window pixmap.", file=sys.stderr)
        return 3
    if not pixmap.save(str(output_path)):
        print("Failed to save the grabbed main window pixmap.", file=sys.stderr)
        return 4
    if is_nearly_black(output_path):
        print(
            f"Captured screenshot is nearly all black and unusable: {output_path.name}",
            file=sys.stderr,
        )
        return 2
    print(f"Saved baseline screenshot to {output_path}")
    return 0


def capture_window(app: QApplication, output_path: Path) -> int:
    """Launch the main window and capture the shell plus all five panels."""
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    result: dict[str, int] = {"code": 3}

    study = Study()
    window = MainWindow(study)
    window.show()

    def _run_step(step_index: int) -> None:
        filename, panel_index = CAPTURE_STEPS[step_index]
        if panel_index is not None:
            window.switch_page(panel_index)

        app.processEvents()
        current_widget = window.stack.currentWidget()
        if current_widget is not None:
            current_widget.repaint()
        window.repaint()
        app.processEvents()

        step_output = output_path.parent / filename
        result["code"] = _capture_current_window(window, step_output)
        if result["code"] != 0:
            window.close()
            app.quit()
            return

        if step_index + 1 >= len(CAPTURE_STEPS):
            window.close()
            app.quit()
            return

        QTimer.singleShot(500, lambda: _run_step(step_index + 1))

    QTimer.singleShot(2500, lambda: _run_step(0))
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
