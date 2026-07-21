#!/usr/bin/env python3
"""Capture focused evidence for current import and preprocessing UI fixes."""

from __future__ import annotations

import sys
import time
from io import BytesIO
from pathlib import Path
from typing import cast

import numpy as np
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
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)
from XBrainLab.ui.dialogs.dataset.smart_parser_dialog import SmartParserDialog
from XBrainLab.ui.dialogs.preprocess.filtering_dialog import FilteringDialog
from XBrainLab.ui.dialogs.preprocess.normalize_dialog import NormalizeDialog
from XBrainLab.ui.dialogs.preprocess.rereference_dialog import RereferenceDialog
from XBrainLab.ui.dialogs.preprocess.resampling_dialog import ResampleDialog
from XBrainLab.ui.panels.preprocess.history_widget import HistoryWidget
from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget
from XBrainLab.ui.styles.stylesheets import Stylesheets

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "artifacts" / "ui" / "ui-review-fixes"


def main() -> int:
    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(Stylesheets.MAIN_WINDOW)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    _capture_preprocess_states(app)
    _capture_preprocess_dialogs(app)
    _capture_smart_parser_modes(app)

    review = _ready_import_dialog()
    review.resize(QSize(1100, 800))
    review._go_to_step(review._step_titles.index("Review and Import"))
    review.import_report_toggle.click()
    _capture(app, review, "import-report-ready.png")
    return 0


def _capture_preprocess_states(app: QApplication) -> None:
    preview = PreviewWidget()
    preview.resize(QSize(920, 620))
    preview.reset_view()
    _capture(app, preview, "preprocess-no-data.png")

    preview = PreviewWidget()
    preview.resize(QSize(920, 620))
    preview.chan_combo.addItems(["C3", "Cz", "C4"])
    time_axis = np.linspace(0.0, 4.0, 800)
    original = 18.0 * np.sin(2 * np.pi * 10 * time_axis)
    current = 14.0 * np.sin(2 * np.pi * 10 * time_axis + 0.15)
    preview.time_original_curve.setData(time_axis, original)
    preview.time_current_curve.setData(time_axis, current)
    frequency_axis = np.linspace(1.0, 50.0, 100)
    preview.freq_original_curve.setData(
        frequency_axis,
        -20.0 * np.log10(frequency_axis + 1.0),
    )
    preview.freq_current_curve.setData(
        frequency_axis,
        -18.0 * np.log10(frequency_axis + 1.0),
    )
    preview._set_preview_interactive(True, state="loaded")
    _capture(app, preview, "preprocess-loaded.png")

    preview = PreviewWidget()
    preview.resize(QSize(920, 620))
    preview.show_locked_message("Preprocessing locked")
    _capture(app, preview, "preprocess-locked.png")

    history = HistoryWidget()
    history.resize(QSize(920, history.HISTORY_HEIGHT))
    history.show_no_data()
    _capture(app, history, "preprocessing-history-no-data.png")

    history = HistoryWidget()
    history.resize(QSize(920, history.HISTORY_HEIGHT))
    history.update_history(
        [
            "Band-pass filter: 1-40 Hz",
            "Re-reference: average",
            "Normalize: Z-Score",
        ],
        is_epoched=True,
    )
    _capture(app, history, "preprocessing-history-locked.png")


def _capture_preprocess_dialogs(app: QApplication) -> None:
    filtering = FilteringDialog(None, sampling_rate_hz=250.0)
    _capture(app, filtering, "preprocess-filtering-dialog.png")

    data = type("CaptureData", (), {})()
    data.get_mne = lambda: type(
        "CaptureMne",
        (),
        {"ch_names": ["Fz", "C3", "Cz", "C4", "Pz"]},
    )()
    rereference = RereferenceDialog(None, [data])
    _capture(app, rereference, "preprocess-rereference-average.png")

    rereference = RereferenceDialog(None, [data])
    rereference.selected_channels_radio.setChecked(True)
    rereference.chan_list.item(1).setSelected(True)
    rereference.chan_list.item(3).setSelected(True)
    _capture(app, rereference, "preprocess-rereference-selected.png")

    _capture(app, NormalizeDialog(None), "preprocess-normalize-dialog.png")
    _capture(app, ResampleDialog(None), "preprocess-resample-dialog.png")


def _capture_smart_parser_modes(app: QApplication) -> None:
    modes = (
        (
            "simple",
            "radio_split",
            ["Sub01_Ses01.gdf", "Sub02_Ses01.gdf", "Sub03_Ses02.gdf"],
        ),
        (
            "regex",
            "radio_regex",
            [
                "sub-01_ses-01_task-mi_run-01_eeg.gdf",
                "sub-02_ses-01_task-mi_run-02_eeg.gdf",
                "sub-03_ses-02_task-mi_run-01_eeg.gdf",
            ],
        ),
        (
            "folder",
            "radio_folder",
            [
                "/capture/Subject01/ses-01/eeg01.gdf",
                "/capture/Subject02/ses-01/eeg02.gdf",
                "/capture/Subject03/ses-02/eeg03.gdf",
            ],
        ),
        ("fixed", "radio_fixed", ["A01T.gdf", "A02E.gdf", "A03T.gdf"]),
    )
    for suffix, radio_name, filenames in modes:
        dialog = SmartParserDialog(filenames)
        getattr(dialog, radio_name).setChecked(True)
        if suffix == "simple":
            dialog.split_sep_combo.setCurrentIndex(0)
            dialog.split_sub_idx.setValue(1)
            dialog.split_sess_idx.setValue(2)
        dialog.update_preview()
        _capture(app, dialog, f"smart-parser-{suffix}.png")


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
        has_readable_text = bool(
            text and any(character.isalnum() for character in text)
        )
        if isinstance(control, QAbstractItemView) or has_readable_text:
            name = control.objectName() or type(control).__name__
            required[f"{name} {index}: {text[:48]}"] = control

    with Image.open(screenshot) as captured:
        scale_x = captured.width / max(widget.width(), 1)
        scale_y = captured.height / max(widget.height(), 1)
    for surface_name, control in required.items():
        top_left = control.mapTo(widget, QPoint(0, 0))
        bottom_right = control.mapTo(widget, control.rect().bottomRight())
        if not widget.rect().contains(top_left) or not widget.rect().contains(
            bottom_right
        ):
            raise RuntimeError(
                f"{surface_name} is clipped outside the captured widget."
            )
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
