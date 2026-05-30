#!/usr/bin/env python3
"""Capture focused UI surfaces that are not covered by the wizard screenshots."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication, QWidget

from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DataSplittingDialog
from XBrainLab.ui.dialogs.training.model_selection_dialog import ModelSelectionDialog
from XBrainLab.ui.panels.evaluation.metrics_table import MetricsTableWidget

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "artifacts" / "ui" / "app-polish"


def main() -> int:
    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    captures = [
        ("model-selection-dialog.png", _model_selection_dialog()),
        ("data-splitting-dialog.png", _data_splitting_dialog()),
        ("evaluation-metrics-table.png", _metrics_table()),
    ]
    for filename, widget in captures:
        widget.show()
        app.processEvents()
        widget.repaint()
        app.processEvents()
        _capture(widget, OUTPUT_DIR / filename)
        widget.close()
    _write_readme()
    return 0


def _model_selection_dialog() -> QWidget:
    dialog = ModelSelectionDialog(None, MagicMock())
    dialog.resize(QSize(680, 560))
    if dialog.model_combo is not None:
        index = dialog.model_combo.findText("EEGNet")
        if index >= 0:
            dialog.model_combo.setCurrentIndex(index)
    return dialog


def _data_splitting_dialog() -> QWidget:
    controller = MagicMock()
    controller.get_epoch_data.return_value = object()
    controller.get_dataset_generator.return_value = None
    dialog = DataSplittingDialog(None, controller)
    dialog.resize(QSize(820, 600))
    return dialog


def _metrics_table() -> QWidget:
    table = MetricsTableWidget()
    table.resize(QSize(780, 210))
    table.update_data(
        {
            0: {
                "precision": 0.4762,
                "recall": 0.2326,
                "f1-score": 0.3125,
                "support": 43,
            },
            1: {
                "precision": 0.3788,
                "recall": 0.5814,
                "f1-score": 0.4587,
                "support": 43,
            },
            2: {
                "precision": 0.5429,
                "recall": 0.4419,
                "f1-score": 0.4872,
                "support": 43,
            },
            3: {
                "precision": 0.6600,
                "recall": 0.7674,
                "f1-score": 0.7097,
                "support": 43,
            },
            "macro_avg": {
                "precision": 0.5145,
                "recall": 0.5058,
                "f1-score": 0.4920,
                "support": 172,
            },
        }
    )
    return table


def _capture(widget: QWidget, output_path: Path) -> None:
    pixmap = widget.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Could not grab {output_path}.")
    if not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save {output_path}.")
    if _is_nearly_black(output_path):
        raise RuntimeError(f"Screenshot is nearly black: {output_path}.")


def _write_readme() -> None:
    (OUTPUT_DIR / "README.md").write_text(
        "# App Polish Screenshots\n\n"
        "status: current release-candidate review evidence\n"
        "generator: `scripts/dev/capture_ui_polish_surfaces.py`\n"
        "environment: PyQt offscreen capture\n"
        "supports: current visual state for model selection, data splitting, "
        "and evaluation metrics table polish\n"
        "does_not_support: end-to-end training quality, human desktop "
        "acceptance, or long-running runtime behavior\n"
        "next_human_or_runtime_gate: open the same dialogs in the Windows "
        "desktop app during manual acceptance\n\n"
        "Focused current screenshots for manual review of surfaces that are not "
        "fully represented by the Data Import wizard artifacts.\n\n"
        "- `model-selection-dialog.png`\n"
        "- `data-splitting-dialog.png`\n"
        "- `evaluation-metrics-table.png`\n",
        encoding="utf-8",
    )


def _is_nearly_black(path: Path) -> bool:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        histogram = rgb.histogram()
    total_pixels = sum(histogram[:256])
    bright_pixels = 0
    for value in range(16, 256):
        bright_pixels += histogram[value]
        bright_pixels += histogram[256 + value]
        bright_pixels += histogram[512 + value]
    return total_pixels == 0 or bright_pixels < total_pixels * 0.01


if __name__ == "__main__":
    raise SystemExit(main())
