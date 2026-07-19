#!/usr/bin/env python3
"""Capture focused evidence for the current UI product-review fixes."""

from __future__ import annotations

import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import cast
from unittest.mock import patch

from PIL import Image
from PyQt6.QtCore import QBuffer, QIODevice, QPoint, QSize
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QLabel,
    QWidget,
)

from scripts.dev.human_like_walkthrough.readiness import (
    assert_consecutive_complete_frames,
    assert_region_has_no_unpainted_block,
    assert_region_matches_reference,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)
from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog
from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget
from XBrainLab.ui.styles.stylesheets import Stylesheets

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "artifacts" / "ui" / "ui-review-fixes"


def main() -> int:
    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    app.setStyle("Fusion")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    preview = PreviewWidget()
    preview.setStyleSheet(Stylesheets.MAIN_WINDOW)
    preview.resize(QSize(920, 620))
    preview.show_locked_message("Data is Epoched - Preprocessing Locked")
    _capture(app, preview, "preprocess-locked.png")

    with tempfile.TemporaryDirectory(prefix="xbrainlab-ui-review-model-") as temp_dir:
        config = _installed_local_config(Path(temp_dir))
        with (
            patch.object(LLMConfig, "load_from_file", return_value=config),
            patch.object(config, "missing_local_runtime_packages", return_value=[]),
            patch("XBrainLab.ui.dialogs.model_settings_dialog.ModelDownloader"),
        ):
            settings = ModelSettingsDialog(config=config)
        settings.setStyleSheet(Stylesheets.MAIN_WINDOW)
        settings.resize(QSize(520, 440))
        _capture(app, settings, "assistant-settings.png")

    review = _ready_import_dialog()
    review.resize(QSize(1100, 800))
    review._go_to_step(review._step_titles.index("Review and Import"))
    review.import_report_toggle.click()
    _capture(app, review, "import-report-ready.png")
    return 0


def _installed_local_config(root: Path) -> LLMConfig:
    config = LLMConfig()
    config.model_name = LLMConfig.default_local_model_id()
    config.cache_dir = str(root / "model-cache")
    config.device = "cpu"
    config.load_in_4bit = False
    config.local_model_enabled = True
    cache = Path(config.local_cache_candidates(config.model_name)[0])
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "config.json").write_text("{}", encoding="utf-8")
    (cache / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    with (cache / "model.safetensors").open("wb") as model_file:
        model_file.truncate(256 * 1024 * 1024)
    return config


def _ready_import_dialog() -> DataInterpretationPreviewDialog:
    source_path = ROOT / "tests" / "fixtures" / "data"
    eeg_path = str(source_path / "sub-01_task-mi_raw.fif")
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": str(source_path), "eeg_files": [eeg_path]},
        preview={
            "summary": "Found 1 EEG file(s).",
            "selected_eeg_files": [eeg_path],
            "source_selection": "Single file",
            "metadata_preview": [
                {
                    "file": "sub-01_task-mi_raw.fif",
                    "subject": {"value": "01", "decision": "safe"},
                    "session": {"value": None, "decision": "safe"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": None, "decision": "safe"},
                }
            ],
            "class_map": {"left": "Left", "right": "Right"},
            "resource_preflight": {
                "risk_level": "safe",
                "required_memory_bytes": 512 * 1024**2,
                "available_memory_bytes": 8 * 1024**3,
            },
        },
        validation_decision={"decision": "safe"},
    )


def _capture(app: QApplication, widget: QWidget, filename: str) -> None:
    widget.show()
    for _ in range(4):
        app.processEvents()
        widget.repaint()
        time.sleep(0.01)
    output = OUTPUT_DIR / filename
    first = output.with_name(f".{output.stem}-frame-1.png")
    try:
        _save_capture(widget, first)
        _assert_reviewer_surface_pixels(widget, first)
        app.processEvents()
        widget.repaint()
        time.sleep(0.04)
        app.processEvents()
        _save_capture(widget, output)
        _assert_reviewer_surface_pixels(widget, output)
        assert_consecutive_complete_frames(first, output)
    finally:
        first.unlink(missing_ok=True)
    widget.close()
    widget.deleteLater()
    app.processEvents()


def _save_capture(widget: QWidget, output: Path) -> None:
    pixmap = widget.grab()
    if pixmap.isNull() or not pixmap.save(str(output)):
        raise RuntimeError(f"Could not capture {output}.")
    with Image.open(output) as captured:
        normalized = captured.convert("RGB")
        extrema = cast(tuple[float, float], normalized.convert("L").getextrema())
        if extrema[1] - extrema[0] < 12:
            raise RuntimeError(f"Capture is visually blank: {output}.")
        normalized.save(output, format="PNG", optimize=True)


def _assert_reviewer_surface_pixels(widget: QWidget, screenshot: Path) -> None:
    required: dict[str, QWidget] = {
        f"{type(widget).__name__} complete surface": widget,
    }
    controls: list[QWidget] = [
        *widget.findChildren(QLabel),
        *widget.findChildren(QAbstractButton),
        *widget.findChildren(QComboBox),
        *widget.findChildren(QAbstractItemView),
    ]
    for index, control in enumerate(controls):
        if not control.isVisibleTo(widget):
            continue
        text = _control_text(control)
        if isinstance(control, QAbstractItemView) or text:
            name = control.objectName() or type(control).__name__
            required[f"{name} {index}: {text[:48]}"] = control

    with Image.open(screenshot) as captured:
        scale_x = captured.width / max(widget.width(), 1)
        scale_y = captured.height / max(widget.height(), 1)
    for surface_name, control in required.items():
        top_left = control.mapTo(widget, QPoint(0, 0))
        bounds = (
            round(top_left.x() * scale_x),
            round(top_left.y() * scale_y),
            round((top_left.x() + control.width()) * scale_x),
            round((top_left.y() + control.height()) * scale_y),
        )
        assert_region_has_no_unpainted_block(
            screenshot,
            bounds,
            surface_name=surface_name,
            max_black_ratio=0.20,
        )
        is_text = isinstance(control, (QLabel, QAbstractButton, QComboBox))
        assert_region_matches_reference(
            screenshot,
            bounds,
            _pixmap_image(control.grab()),
            surface_name=surface_name,
            minimum_edge_recall=0.70 if is_text else 0.42,
            maximum_changed_pixel_ratio=1.0 if is_text else 0.55,
        )


def _control_text(control: QWidget) -> str:
    text_getter = getattr(control, "text", None)
    if callable(text_getter):
        return " ".join(str(text_getter()).split())
    if isinstance(control, QComboBox):
        return " ".join(control.currentText().split())
    return ""


def _pixmap_image(pixmap) -> Image.Image:
    if pixmap.isNull():
        raise RuntimeError("Could not create a settled live widget reference.")
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Could not open the live widget reference buffer.")
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError("Could not encode the live widget reference.")
    data = bytes(buffer.data())
    buffer.close()
    with Image.open(BytesIO(data)) as source:
        image = source.convert("RGB")
        image.load()
    return image


if __name__ == "__main__":
    raise SystemExit(main())
