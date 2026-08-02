#!/usr/bin/env python3
"""Capture a minimal UI baseline screenshot set for XBrainLab.

This helper launches the real application stack, waits for the main window to
settle, and captures the rendered main-window widget across the shell and the
five primary panels into transient ``artifacts/ui/`` PNGs. Approved references
live in ``tests/baselines/ui/``.

Expected usage in WSL/headless environments:

    xvfb-run -a /home/administrator/.local/bin/poetry run -- python \
        scripts/dev/capture_ui_baseline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from XBrainLab.ui.qt_runtime import configure_qt_platform_for_runtime

configure_qt_platform_for_runtime()

from PyQt6.QtCore import QPoint, QSettings, QSize, Qt, QTimer
from PyQt6.QtWidgets import QApplication

from scripts.dev.human_like_walkthrough.readiness import (
    assert_consecutive_complete_frames,
)
from scripts.dev.ui_navigation import open_workflow_panel

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT / "artifacts" / "ui"
OUTPUT_PATH = ARTIFACTS_DIR / "main-window-initial.png"
AI_DOCK_STEP = "ai-dock"
BASELINE_WINDOW_SIZE = QSize(1280, 800)
# Lazy panel materialization, dock resizing, and the final Qt polish/repaint each
# use queued event-loop work. Capturing earlier can record a partially repainted
# frame even though the live widget geometry is already correct.
PANEL_PAINT_SETTLE_MS = 300
CONSECUTIVE_FRAME_SETTLE_MS = 80
MAX_CONSECUTIVE_FRAME_CHANGED_RATIO = 0.02
CAPTURE_STEPS = [
    ("main-window-initial.png", None),
    ("panel-dataset.png", 0),
    ("panel-preprocess.png", 1),
    ("panel-training.png", 2),
    ("panel-evaluation.png", 3),
    ("panel-visualization.png", 4),
    ("ai-assistant-open.png", AI_DOCK_STEP),
]


def _clear_saved_main_window_geometry() -> None:
    """Remove user/session geometry so capture remains deterministic."""
    settings = QSettings("XBrainLab", "XBrainLab")
    settings.remove("main_window/geometry")
    settings.sync()


def _set_baseline_window_geometry(window) -> None:
    """Force the screenshot window to the approved capture dimensions."""
    window.setWindowState(Qt.WindowState.WindowNoState)
    screen = window.screen() or QApplication.primaryScreen()
    target = BASELINE_WINDOW_SIZE
    if screen is not None:
        available = screen.availableGeometry()
        window.move(available.topLeft())
    else:
        window.move(QPoint(0, 0))
    window.resize(target)


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


def _capture_window_frame(
    window,
    output_path: Path,
    *,
    announce: bool = False,
) -> int:
    """Grab one rendered frame and reject unusable output."""
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
    if announce:
        print(f"Saved baseline screenshot to {output_path}")
    return 0


def _validate_consecutive_frames(first_frame: Path, second_frame: Path) -> int:
    """Reject captures that still contain a visible repaint transition."""
    try:
        assert_consecutive_complete_frames(
            first_frame,
            second_frame,
            max_changed_pixel_ratio=MAX_CONSECUTIVE_FRAME_CHANGED_RATIO,
        )
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 5
    return 0


def _prepare_capture_step(window, step_target) -> None:
    """Move the UI into the state needed for the requested capture step."""
    if step_target is None:
        return

    if step_target == AI_DOCK_STEP:
        open_workflow_panel(window, 0)
        if window.agent_manager is None:
            window.init_agent()
        manager = window.agent_manager
        if manager is None:
            return
        if manager.chat_dock is not None:
            manager.chat_dock.show()
        if hasattr(manager, "update_ai_btn_state"):
            manager.update_ai_btn_state(True)
        elif hasattr(window, "ai_btn"):
            window.ai_btn.setChecked(True)
        return

    open_workflow_panel(window, step_target)


def capture_window(app: QApplication, output_path: Path) -> int:
    """Launch the main window and capture the shell plus all five panels."""
    from XBrainLab.backend.application.runtime import get_application_service
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    result: dict[str, int] = {"code": 3}

    _clear_saved_main_window_geometry()
    study = Study()
    get_application_service(study)
    window = MainWindow(study)
    _set_baseline_window_geometry(window)
    window.show()

    def _run_step(step_index: int) -> None:
        _filename, step_target = CAPTURE_STEPS[step_index]
        _prepare_capture_step(window, step_target)
        _set_baseline_window_geometry(window)

        app.processEvents()
        current_widget = window.stack.currentWidget()
        if current_widget is not None:
            current_widget.ensurePolished()
            layout = current_widget.layout()
            if layout is not None:
                layout.activate()
            current_widget.updateGeometry()
            current_widget.update()
        window.update()
        QTimer.singleShot(
            PANEL_PAINT_SETTLE_MS,
            lambda: _capture_prepared_step(step_index),
        )

    def _capture_prepared_step(step_index: int) -> None:
        filename, _step_target = CAPTURE_STEPS[step_index]
        app.processEvents()
        current_widget = window.stack.currentWidget()
        if current_widget is not None:
            current_widget.repaint()
        window.repaint()
        app.processEvents()

        step_output = output_path.parent / filename
        first_frame = step_output.with_name(f".{step_output.stem}-frame-1.png")
        result["code"] = _capture_window_frame(window, first_frame)
        if result["code"] != 0:
            first_frame.unlink(missing_ok=True)
            window.close()
            app.quit()
            return

        QTimer.singleShot(
            CONSECUTIVE_FRAME_SETTLE_MS,
            lambda: _capture_stable_step(step_index, first_frame, step_output),
        )

    def _capture_stable_step(
        step_index: int,
        first_frame: Path,
        step_output: Path,
    ) -> None:
        app.processEvents()
        current_widget = window.stack.currentWidget()
        if current_widget is not None:
            current_widget.repaint()
        window.repaint()
        app.processEvents()

        result["code"] = _capture_window_frame(
            window,
            step_output,
            announce=True,
        )
        if result["code"] == 0:
            result["code"] = _validate_consecutive_frames(first_frame, step_output)
        first_frame.unlink(missing_ok=True)
        if result["code"] != 0:
            window.close()
            app.quit()
            return

        if step_index + 1 >= len(CAPTURE_STEPS):
            window.close()
            app.quit()
            return

        QTimer.singleShot(
            max(0, 500 - PANEL_PAINT_SETTLE_MS),
            lambda: _run_step(step_index + 1),
        )

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
