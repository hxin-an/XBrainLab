#!/usr/bin/env python3
"""Capture canonical Data Import wizard screenshots."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PIL import Image
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication, QWidget

from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
    _ConvertedLabelTableDialog,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "artifacts" / "ui" / "data-import-wizard-steps"
REVIEW_STATES_DIR = OUTPUT_DIR / "review-import-states"
BIDS_PRESET_DIR = OUTPUT_DIR / "bids-preset"
WINDOW_SIZE = QSize(1220, 1320)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_STATES_DIR.mkdir(parents=True, exist_ok=True)
    BIDS_PRESET_DIR.mkdir(parents=True, exist_ok=True)
    captures = [
        ("01-choose-eeg-data.png", _main_dialog(), "Choose EEG Data"),
        ("02-load-labels-many.png", _many_labels_dialog(), "Load Labels"),
        ("03-review-metadata.png", _main_dialog(), "Review Metadata"),
        (
            "04-match-labels-internal-suggested-events-full.png",
            _internal_events_dialog(),
            "Match Labels",
        ),
        (
            "04-match-labels-final-loaded-label-files.png",
            _loaded_label_files_dialog(),
            "Match Labels",
        ),
        ("04-match-labels-bids-events.png", _bids_events_dialog(), "Match Labels"),
        (
            "04-match-labels-conversion-fallback.png",
            _conversion_fallback_dialog(),
            "Match Labels",
        ),
        ("05-review-and-import.png", _review_import_dialog(), "Review and Import"),
    ]
    for filename, dialog, step_title in captures:
        path = OUTPUT_DIR / filename
        _show_step(dialog, step_title, app)
        _capture(dialog, path)
        dialog.close()

    bids_preset_captures = [
        ("01-choose-eeg-data.png", _bids_events_dialog(), "Choose EEG Data"),
        ("02-load-labels.png", _bids_events_dialog(), "Load Labels"),
        ("03-review-metadata.png", _bids_events_dialog(), "Review Metadata"),
        ("04-match-labels.png", _bids_events_dialog(), "Match Labels"),
        ("05-review-and-import.png", _bids_events_dialog(), "Review and Import"),
    ]
    for filename, dialog, step_title in bids_preset_captures:
        path = BIDS_PRESET_DIR / filename
        _show_step(dialog, step_title, app)
        _capture(dialog, path)
        dialog.close()

    review_state_captures = [
        ("no-confirm.png", _review_import_state_dialog("safe"), "Review and Import"),
        (
            "needs-confirm.png",
            _review_import_state_dialog("confirm"),
            "Review and Import",
        ),
        (
            "needs-review.png",
            _review_import_state_dialog("review"),
            "Review and Import",
        ),
        (
            "confirm-and-review.png",
            _review_import_state_dialog("both"),
            "Review and Import",
        ),
    ]
    for filename, dialog, step_title in review_state_captures:
        path = REVIEW_STATES_DIR / filename
        _show_step(dialog, step_title, app)
        _capture(dialog, path)
        dialog.close()

    style_source = _main_dialog()
    format_dialog = _ConvertedLabelTableDialog()
    format_dialog.setStyleSheet(style_source.styleSheet())
    format_dialog.resize(QSize(900, 720))
    format_dialog.show()
    app.processEvents()
    _capture(
        format_dialog,
        OUTPUT_DIR / "04-match-labels-conversion-table-format-dialog.png",
    )
    format_dialog.close()
    style_source.close()
    return 0


def _show_step(
    dialog: DataInterpretationPreviewDialog,
    step_title: str,
    app: QApplication,
) -> None:
    dialog.resize(WINDOW_SIZE)
    dialog.show()
    app.processEvents()
    dialog._go_to_step(dialog._step_titles.index(step_title))
    app.processEvents()
    dialog.repaint()
    app.processEvents()


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


def _base_scan() -> dict[str, Any]:
    return {
        "source_path": "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data",
        "source_kind": "file",
        "eeg_files": [
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A01T.gdf",
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A02T.gdf",
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A03T.gdf",
        ],
        "label_carriers": [
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A01T.mat",
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A02T.mat",
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A03T.mat",
        ],
        "label_carrier_sources": {
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A01T.mat": (
                "auto"
            ),
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A02T.mat": (
                "auto"
            ),
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A03T.mat": (
                "auto"
            ),
        },
        "bids": {"is_bids": False, "events_files": []},
    }


def _main_dialog() -> DataInterpretationPreviewDialog:
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result=_base_scan(),
        preview={
            "summary": "Found 3 EEG file(s) and 3 label/event carrier(s).",
            "source_selection": "3 selected file(s)",
            "metadata_preview": _metadata_rows(),
            "label_carrier_preview": _label_carriers(),
            "confirmation_items": [
                "Confirm session metadata for A01T.gdf.",
                "Confirm label placement for A01T.mat: 6 selected EEG events have no label.",
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )


def _many_labels_dialog() -> DataInterpretationPreviewDialog:
    scan = _base_scan()
    carriers = []
    paths = []
    for index in range(1, 13):
        path = f"/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A{index:02d}T.mat"
        paths.append(path)
        carriers.append(
            {
                "path": path,
                "name": Path(path).name,
                "format": "MAT",
                "source_kind": "auto_discovered" if index <= 6 else "user_added",
                "source_location": (
                    ""
                    if index <= 6
                    else "/mnt/d/workspace_v2/projects/lab/XBrainLab/external-labels"
                ),
                "selected_label_field": "classlabel",
                "selected_anchor": "trial order",
                "time_model": "trial_order",
                "granularity": "trial",
                "placement_method": "eeg_event",
            }
        )
    scan["label_carriers"] = paths
    scan["label_carrier_sources"] = {
        path: "auto" if index <= 6 else "/external-labels"
        for index, path in enumerate(paths, start=1)
    }
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result=scan,
        preview={
            "summary": "Found 3 EEG file(s) and 12 label/event carrier(s).",
            "source_selection": "3 selected file(s)",
            "metadata_preview": _metadata_rows(),
            "label_carrier_preview": carriers,
        },
        validation_decision={"decision": "needs_confirmation"},
    )


def _internal_events_dialog() -> DataInterpretationPreviewDialog:
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result={**_base_scan(), "label_carriers": []},
        preview={
            "summary": "Found 3 EEG file(s).",
            "source_selection": "3 selected file(s)",
            "metadata_preview": _metadata_rows(),
            "internal_event_preview": {
                "pattern_status": "Shared event pattern detected",
                "candidate_label_events": [
                    _event("769", "Class label", 216, "Repeats once per trial"),
                    _event("770", "Class label", 216, "Repeats once per trial"),
                    _event("771", "Class label", 216, "Repeats once per trial"),
                    _event("772", "Class label", 144, "Missing in A03T.gdf"),
                ],
                "not_used_events": [
                    _event("768", "Trial timing", 864, "Trial start marker"),
                    _event("1023", "Exclude bad trials", 18, "Rejected trial marker"),
                    _event("32766", "Ignore", 3, "System / boundary marker"),
                ],
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )


def _loaded_label_files_dialog() -> DataInterpretationPreviewDialog:
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            **_base_scan(),
            "eeg_files": [
                "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A01T.gdf",
            ],
            "label_carriers": [
                "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A01T.mat",
            ],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "source_selection": "1 selected file",
            "metadata_preview": [_metadata_rows()[0]],
            "label_carrier_preview": [_label_carriers()[0]],
            "internal_event_preview": _external_target_event_preview(),
        },
        validation_decision={"decision": "needs_confirmation"},
    )


def _bids_events_dialog() -> DataInterpretationPreviewDialog:
    events_path = (
        "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/bids/"
        "sub-01_task-mi_run-01_events.tsv"
    )
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/bids",
            "source_kind": "bids",
            "eeg_files": [
                "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/bids/"
                "sub-01_task-mi_run-01_raw.fif",
            ],
            "label_carriers": [events_path],
            "bids": {
                "is_bids": True,
                "subjects": ["01"],
                "sessions": [],
                "tasks": ["mi"],
                "runs": ["01"],
                "events_files": [events_path],
                "has_participants_tsv": False,
            },
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "source_selection": "BIDS-like folder",
            "metadata_preview": [_metadata_rows()[0]],
            "label_carrier_preview": [
                {
                    "path": events_path,
                    "name": "sub-01_task-mi_run-01_events.tsv",
                    "format": "BIDS events",
                    "bids_event_columns": ["onset", "duration", "trial_type"],
                    "label_candidates": ["trial_type"],
                    "anchor_candidates": ["onset"],
                    "time_field_candidates": ["onset"],
                    "duration_candidates": ["duration"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "time_model": "seconds",
                    "placement_method": "interval",
                    "granularity": "trial",
                    "label_value_counts": {
                        "left_hand": 72,
                        "right_hand": 72,
                        "feet": 72,
                        "tongue": 72,
                    },
                    "placement_review": {
                        "method": "interval",
                        "status": "ready",
                        "label_field": "trial_type",
                        "time_field": "onset",
                        "duration_field": "duration",
                        "label_rows": 288,
                        "numeric_rows": 288,
                        "duration_numeric_rows": 288,
                        "summary": (
                            "288 labels have onset and duration fields from events.tsv."
                        ),
                    },
                    "warnings": [
                        "events.json sidecar is missing; class names need review."
                    ],
                },
            ],
            "action_items": [
                {
                    "target_step": "Match Labels",
                    "issue": "Confirm BIDS class names.",
                    "impact": (
                        "events.json was not found, so class descriptions come "
                        "from raw trial_type values."
                    ),
                    "next_action": "Confirm class names in Match Labels.",
                }
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )


def _conversion_fallback_dialog() -> DataInterpretationPreviewDialog:
    label_path = (
        "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/custom_labels.mat"
    )
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            **_base_scan(),
            "eeg_files": [
                "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A01T.gdf",
            ],
            "label_carriers": [label_path],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "source_selection": "1 selected file",
            "metadata_preview": [_metadata_rows()[0]],
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "custom_labels.mat",
                    "format": "MAT",
                    "label_candidates": [],
                    "anchor_candidates": [],
                    "selected_label_field": "",
                    "selected_anchor": "",
                    "time_model": "",
                    "granularity": "",
                    "placement_method": "eeg_event",
                    "role": "external labels",
                }
            ],
        },
        validation_decision={"decision": "blocked"},
    )


def _review_import_dialog() -> DataInterpretationPreviewDialog:
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result=_base_scan(),
        preview={
            "summary": "Found 3 EEG file(s) and 3 label/event carrier(s).",
            "source_selection": "3 selected file(s)",
            "metadata_preview": _metadata_rows(),
            "label_carrier_preview": _label_carriers(),
            "review_action_items": [
                {
                    "target_step": "Choose EEG Data",
                    "issue": (
                        "Multiple EEG files were discovered; subject/session/run "
                        "mapping should be reviewed."
                    ),
                    "impact": (
                        "Import may still be usable, but downstream labels or "
                        "metadata may need review."
                    ),
                    "next_action": "Open the target step and confirm the selected files.",
                },
                {
                    "target_step": "Review Metadata",
                    "issue": "Confirm session metadata for A01T.gdf.",
                    "impact": (
                        "This choice affects imported metadata, labels, and "
                        "downstream training readiness."
                    ),
                    "next_action": "Review the target step and confirm the choice.",
                },
                {
                    "target_step": "Match Labels",
                    "issue": "Confirm label placement for A01T.mat.",
                    "impact": "Labels will be applied before supervised training.",
                    "next_action": "Check the target EEG events and class names.",
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )


def _review_import_state_dialog(state: str) -> DataInterpretationPreviewDialog:
    preview: dict[str, Any] = {
        "summary": "Found 3 EEG file(s) and 3 label/event carrier(s).",
        "source_selection": "3 selected file(s)",
        "metadata_preview": _metadata_rows(),
        "label_carrier_preview": _label_carriers(),
    }
    validation_decision: dict[str, Any] = {"decision": "safe"}
    if state == "confirm":
        preview["action_items"] = [
            {
                "target_step": "Review Metadata",
                "issue": "Confirm session metadata.",
                "impact": "Session was inferred from filenames for 3 files.",
                "next_action": "Go to Review Metadata if the session is wrong.",
            }
        ]
        validation_decision = {"decision": "needs_confirmation"}
    elif state == "review":
        preview["action_items"] = [
            {
                "target_step": "Match Labels",
                "issue": "Label count needs review.",
                "impact": "A03T.mat has 282 labels and 288 selected EEG events.",
                "next_action": "Open Match Labels and check target EEG events.",
            }
        ]
    elif state == "both":
        preview["action_items"] = [
            {
                "target_step": "Review Metadata",
                "issue": "Confirm session metadata.",
                "impact": "Session was inferred from filenames for 3 files.",
                "next_action": "Go to Review Metadata if the session is wrong.",
            },
            {
                "target_step": "Match Labels",
                "issue": "Label count needs review.",
                "impact": "A03T.mat has 282 labels and 288 selected EEG events.",
                "next_action": "Open Match Labels and check target EEG events.",
            },
        ]
        validation_decision = {"decision": "needs_confirmation"}

    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result=_base_scan(),
        preview=preview,
        validation_decision=validation_decision,
    )


def _metadata_rows() -> list[dict[str, Any]]:
    return [
        {
            "file": "A01T.gdf",
            "subject": {"value": "A01", "decision": "safe"},
            "session": {"value": "T", "decision": "needs_confirmation"},
            "task": {"value": "motor-imagery", "decision": "safe"},
            "run": {"value": "01", "decision": "safe"},
        },
        {
            "file": "A02T.gdf",
            "subject": {"value": "A02", "decision": "safe"},
            "session": {"value": "T", "decision": "needs_confirmation"},
            "task": {"value": "motor-imagery", "decision": "safe"},
            "run": {"value": "01", "decision": "safe"},
        },
        {
            "file": "A03T.gdf",
            "subject": {"value": "A03", "decision": "safe"},
            "session": {"value": "T", "decision": "needs_confirmation"},
            "task": {"value": "motor-imagery", "decision": "safe"},
            "run": {"value": "01", "decision": "safe"},
        },
    ]


def _label_carriers() -> list[dict[str, Any]]:
    carriers = []
    for name, target in (
        ("A01T.mat", "A01T.gdf"),
        ("A02T.mat", "A02T.gdf"),
        ("A03T.mat", "A03T.gdf"),
    ):
        carriers.append(
            {
                "path": (
                    "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/"
                    f"{name}"
                ),
                "name": name,
                "format": "MAT",
                "target_file": target,
                "label_candidates": ["classlabel"],
                "anchor_candidates": ["trial order"],
                "event_code_candidates": ["event_code"],
                "selected_label_field": "classlabel",
                "selected_anchor": "trial order",
                "selected_target_event_codes": ["769", "770", "771", "772"],
                "label_row_count": 282,
                "label_value_counts": {"1": 72, "2": 70, "3": 70, "4": 70},
                "time_model": "trial_order",
                "granularity": "trial",
                "placement_method": "eeg_event",
                "role": "external labels",
                "placement_review": {
                    "method": "eeg_event",
                    "status": "ready",
                    "label_field": "classlabel",
                    "label_rows": 282,
                    "selected_eeg_events": 282,
                    "matched": 282,
                    "summary": "282 label rows match 282 selected EEG events.",
                },
            }
        )
    return carriers


def _external_target_event_preview() -> dict[str, Any]:
    return {
        "pattern_status": "Event pattern ready for review",
        "candidate_label_events": [
            _event("769", "Class label", 72, "Repeated count + timing"),
            _event("770", "Class label", 70, "Repeated count + timing"),
            _event("771", "Class label", 70, "Repeated count + timing"),
            _event("772", "Class label", 70, "Repeated count + timing"),
        ],
        "not_used_events": [
            _event("768", "Trial timing", 288, "Matches class total"),
            _event("1023", "Artifact", 6, "Artifact text"),
        ],
    }


def _event(
    event_code: str,
    use_as: str,
    event_count: int,
    evidence: str,
) -> dict[str, Any]:
    return {
        "event_code": event_code,
        "use_as": use_as,
        "event_count": event_count,
        "coverage": "3/3 files",
        "evidence": evidence,
    }


if __name__ == "__main__":
    raise SystemExit(main())
