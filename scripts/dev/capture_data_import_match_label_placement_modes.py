#!/usr/bin/env python3
"""Capture Match Labels placement-mode screenshots for review."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PIL import Image
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication, QWidget

from XBrainLab.ui.dialogs.dataset import DataInterpretationPreviewDialog

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = (
    ROOT
    / "artifacts"
    / "ui"
    / "data-import-wizard-steps"
    / "match-label-placement-modes"
)
WINDOW_SIZE = QSize(1220, 1320)


MODE_OUTPUTS = {
    "eeg_event": "eeg-event-order-full.png",
    "time_field": "label-time-full.png",
    "interval": "label-interval-full.png",
    "event_code": "label-event-code-full.png",
}


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for method, filename in MODE_OUTPUTS.items():
        path = OUTPUT_DIR / filename
        dialog = build_dialog(method)
        dialog.resize(WINDOW_SIZE)
        dialog.show()
        app.processEvents()
        dialog._go_to_step(dialog._step_titles.index("Match Labels"))
        app.processEvents()
        dialog.repaint()
        app.processEvents()
        capture_widget(dialog, path)
        dialog.close()
    return 0


def build_dialog(method: str) -> DataInterpretationPreviewDialog:
    preview = preview_payload(method)
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data",
            "source_kind": "file",
            "eeg_files": [
                "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A01T.gdf",
            ],
            "label_carriers": [
                "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A01T.mat",
            ],
        },
        preview=preview,
        validation_decision={"decision": "needs_confirmation"},
    )


def preview_payload(method: str) -> dict[str, Any]:
    selected_anchor = {
        "eeg_event": "trial order",
        "time_field": "onset",
        "interval": "onset",
        "event_code": "event_code",
    }[method]
    return {
        "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
        "source_selection": "1 selected file",
        "selected_eeg_files": [
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A01T.gdf",
        ],
        "label_carrier_preview": [
            {
                "path": (
                    "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/"
                    "label/A01T.mat"
                ),
                "name": "A01T.mat",
                "format": "MAT",
                "target_file": "A01T.gdf",
                "label_candidates": ["classlabel", "trial_type", "value"],
                "anchor_candidates": ["trial order", "onset", "sample", "event_code"],
                "time_field_candidates": ["onset", "sample"],
                "interval_start_candidates": ["onset", "sample"],
                "event_code_candidates": ["event_code", "value"],
                "duration_candidates": ["duration", "end"],
                "selected_label_field": "classlabel",
                "selected_anchor": selected_anchor,
                "selected_duration_field": "duration" if method == "interval" else "",
                "label_row_count": 282,
                "label_value_counts": {"1": 72, "2": 70, "3": 70, "4": 70},
                "time_label_preview": [
                    {"time": "0", "label": "1"},
                    {"time": "2.5", "label": "2"},
                    {"time": "5", "label": "1"},
                ],
                "selected_anchor_stats": {
                    "row_count": 282,
                    "value_counts": {
                        "769": 72,
                        "770": 70,
                        "771": 70,
                        "772": 70,
                    }
                    if method == "event_code"
                    else {},
                    "numeric_count": 282,
                    "min": 0.0,
                    "max": 719.5,
                },
                "selected_duration_stats": {
                    "row_count": 282,
                    "value_counts": {},
                    "numeric_count": 282,
                    "min": 0.5,
                    "max": 0.5,
                },
                "time_model": "trial_order" if method == "eeg_event" else "seconds",
                "granularity": "trial",
                "placement_method": method,
                "role": "external labels",
                "placement_reviews": placement_reviews(),
                "placement_review": placement_reviews()[method],
            }
        ],
        "internal_event_preview": {
            "pattern_status": "Event pattern ready for review",
            "candidate_label_events": [
                {
                    "event_code": "769",
                    "use_as": "Class label",
                    "event_count": 72,
                    "evidence": "Repeated count + timing",
                },
                {
                    "event_code": "770",
                    "use_as": "Class label",
                    "event_count": 70,
                    "evidence": "Repeated count + timing",
                },
                {
                    "event_code": "771",
                    "use_as": "Class label",
                    "event_count": 70,
                    "evidence": "Repeated count + timing",
                },
                {
                    "event_code": "772",
                    "use_as": "Class label",
                    "event_count": 70,
                    "evidence": "Repeated count + timing",
                },
            ],
            "not_used_events": [
                {
                    "event_code": "768",
                    "use_as": "Trial timing",
                    "event_count": 288,
                    "evidence": "Matches class total",
                },
                {
                    "event_code": "1023",
                    "use_as": "Artifact",
                    "event_count": 6,
                    "evidence": "Artifact text",
                },
            ],
        },
    }


def placement_reviews() -> dict[str, dict[str, Any]]:
    return {
        "eeg_event": {
            "method": "eeg_event",
            "status": "needs_review",
            "label_field": "classlabel",
            "target_event": "768",
            "label_rows": 282,
            "selected_eeg_events": 288,
            "matched": 282,
            "unlabeled_eeg_events": 6,
            "unmatched_label_rows": 0,
            "excluded_eeg_events": 6,
            "summary": (
                "6 selected EEG events have no label "
                "(282 label rows, 288 selected events)."
            ),
            "next_action": (
                "Uncheck extra target events or choose a label field with more rows."
            ),
        },
        "time_field": {
            "method": "time_field",
            "status": "ready",
            "label_field": "classlabel",
            "time_field": "onset",
            "label_rows": 282,
            "numeric_rows": 282,
            "time_min": 0.0,
            "time_max": 719.5,
            "time_model": "seconds",
            "summary": "onset: 282/282 numeric rows, range 0 to 719.5.",
        },
        "interval": {
            "method": "interval",
            "status": "ready",
            "label_field": "classlabel",
            "time_field": "onset",
            "duration_field": "duration",
            "label_rows": 282,
            "numeric_rows": 282,
            "duration_numeric_rows": 282,
            "summary": "282 interval rows using onset and duration.",
        },
        "event_code": {
            "method": "event_code",
            "status": "ready",
            "label_field": "classlabel",
            "event_code_field": "event_code",
            "label_rows": 282,
            "label_code_count": 4,
            "matched_code_count": 4,
            "matched_codes": ["769", "770", "771", "772"],
            "missing_codes": [],
            "code_mappings": [
                {
                    "event_code": "769",
                    "label_values": ["Left hand"],
                    "label_rows": 72,
                    "eeg_event_count": 72,
                    "status": "ready",
                    "review": "Ready.",
                },
                {
                    "event_code": "770",
                    "label_values": ["Right hand"],
                    "label_rows": 70,
                    "eeg_event_count": 70,
                    "status": "ready",
                    "review": "Ready.",
                },
                {
                    "event_code": "771",
                    "label_values": ["Feet"],
                    "label_rows": 70,
                    "eeg_event_count": 70,
                    "status": "ready",
                    "review": "Ready.",
                },
                {
                    "event_code": "772",
                    "label_values": ["Tongue"],
                    "label_rows": 70,
                    "eeg_event_count": 70,
                    "status": "ready",
                    "review": "Ready.",
                },
            ],
            "unlabeled_eeg_events": [
                {
                    "event_code": "768",
                    "use_as": "Trial timing",
                    "event_count": 288,
                },
                {
                    "event_code": "1023",
                    "use_as": "Artifact",
                    "event_count": 6,
                },
            ],
            "summary": "All 4 label event codes match EEG events.",
        },
    }


def capture_widget(widget: QWidget, output_path: Path) -> None:
    pixmap = widget.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Could not grab {output_path}.")
    if not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save {output_path}.")
    if is_nearly_black(output_path):
        raise RuntimeError(f"Screenshot is nearly black: {output_path}.")


def is_nearly_black(path: Path) -> bool:
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
