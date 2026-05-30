#!/usr/bin/env python3
"""Capture canonical Create Epochs dialog screenshots."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PIL import Image
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication, QWidget

from XBrainLab.backend.application.epoch_context import EPOCH_HINT_KEY
from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "artifacts" / "ui" / "epoching-dialog"


class _EpochData:
    def __init__(self, event_id: dict[str, int], hint: dict[str, Any]) -> None:
        self._event_id = event_id
        self._hint = hint

    def get_event_list(self):
        return None, self._event_id

    def get_runtime_detail(self, key: str) -> Any:
        return self._hint if key == EPOCH_HINT_KEY else None


def main() -> int:
    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    captures = [
        (
            "epoching-interval-import.png",
            EpochingDialog(None, [_interval_epoch_data()]),
        ),
        (
            "epoching-internal-events.png",
            EpochingDialog(None, [_internal_event_epoch_data()]),
        ),
    ]
    for filename, dialog in captures:
        dialog.resize(QSize(640, 720))
        dialog.show()
        app.processEvents()
        dialog.repaint()
        app.processEvents()
        _capture(dialog, OUTPUT_DIR / filename)
        dialog.close()
    return 0


def _interval_epoch_data() -> _EpochData:
    return _EpochData(
        {"Left hand": 1, "Right hand": 2, "Artifact": 99},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 288, "min": 0.5, "max": 1.25},
            "class_map": {"left": "Left hand", "right": "Right hand"},
        },
    )


def _internal_event_epoch_data() -> _EpochData:
    return _EpochData(
        {"769": 769, "770": 770, "771": 771, "772": 772, "1023": 1023},
        {
            "source": "Labels inside EEG files",
            "placement_method": "internal_events",
            "class_map": {
                "769": "769",
                "770": "770",
                "771": "771",
                "772": "772",
            },
        },
    )


def _capture(widget: QWidget, output_path: Path) -> None:
    pixmap = widget.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Could not grab {output_path}.")
    if not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save {output_path}.")
    if _is_nearly_black(output_path):
        raise RuntimeError(f"Screenshot is nearly black: {output_path}.")


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
