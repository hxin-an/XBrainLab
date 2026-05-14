#!/usr/bin/env python3
"""Capture canonical Data Import wizard screenshots for product review."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
from PIL import Image
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication, QWidget
from scipy.io import savemat

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.study import Study
from XBrainLab.ui.dialogs.dataset import DataInterpretationPreviewDialog

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "artifacts" / "ui" / "data-import-wizard-steps"
WINDOW_SIZE = QSize(1220, 920)


EEG_ROOT = "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data"
LABEL_ROOT = f"{EEG_ROOT}/label"


def main() -> int:
    existing_app = QApplication.instance()
    app = (
        existing_app
        if isinstance(existing_app, QApplication)
        else QApplication(sys.argv)
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    captures: list[tuple[str, str, DataInterpretationPreviewDialog, QSize]] = [
        (
            "01-choose-eeg-data.png",
            "Choose EEG Data",
            build_dialog(base_scan(), base_preview(), needs_confirmation()),
            WINDOW_SIZE,
        ),
        (
            "02-load-labels-empty.png",
            "Load Labels",
            build_dialog(empty_label_scan(), empty_label_preview(), safe()),
            WINDOW_SIZE,
        ),
        (
            "02-load-labels-auto-detected.png",
            "Load Labels",
            build_dialog(base_scan(), base_preview(), needs_confirmation()),
            WINDOW_SIZE,
        ),
        (
            "02-load-labels-user-added.png",
            "Load Labels",
            build_dialog(user_added_scan(), user_added_preview(), needs_confirmation()),
            WINDOW_SIZE,
        ),
        (
            "02-load-labels-duplicate-removal.png",
            "Load Labels",
            duplicate_removal_dialog(),
            WINDOW_SIZE,
        ),
        (
            "02-load-labels-many.png",
            "Load Labels",
            build_dialog(many_label_scan(), many_label_preview(), needs_confirmation()),
            WINDOW_SIZE,
        ),
        (
            "03-review-metadata-smart-parse.png",
            "Review Metadata",
            build_dialog(base_scan(), metadata_preview(), needs_confirmation()),
            WINDOW_SIZE,
        ),
        (
            "04-match-labels-internal-eeg-labels.png",
            "Match Labels",
            build_dialog(internal_scan(), internal_preview(), needs_confirmation()),
            WINDOW_SIZE,
        ),
        (
            "04-match-labels-bids-like-events.png",
            "Match Labels",
            build_dialog(bids_scan(), bids_preview(), needs_confirmation()),
            WINDOW_SIZE,
        ),
        (
            "04-match-labels-conversion-fallback.png",
            "Match Labels",
            build_dialog(conversion_scan(), conversion_preview(), blocked_conversion()),
            WINDOW_SIZE,
        ),
        (
            "05-review-and-import-normal.png",
            "Review and Import",
            build_dialog(base_scan(), review_preview("normal"), safe()),
            WINDOW_SIZE,
        ),
        (
            "05-review-and-import-needs-review.png",
            "Review and Import",
            build_dialog(
                base_scan(), review_preview("needs_review"), needs_confirmation()
            ),
            WINDOW_SIZE,
        ),
        (
            "05-review-and-import-blocked.png",
            "Review and Import",
            build_dialog(
                conversion_scan(), review_preview("blocked"), blocked_conversion()
            ),
            WINDOW_SIZE,
        ),
    ]

    for filename, step_title, dialog, size in captures:
        capture_dialog(dialog, step_title, OUTPUT_DIR / filename, app, size=size)

    capture_conversion_examples(app)
    write_epoch_handoff_artifact()
    return 0


def build_dialog(
    scan_result: dict[str, Any],
    preview: dict[str, Any],
    validation_decision: dict[str, Any],
) -> DataInterpretationPreviewDialog:
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result=scan_result,
        preview=preview,
        validation_decision=validation_decision,
    )


def capture_dialog(
    dialog: DataInterpretationPreviewDialog,
    step_title: str,
    output_path: Path,
    app: QApplication,
    *,
    size: QSize,
) -> None:
    dialog.resize(size)
    dialog.show()
    app.processEvents()
    dialog._go_to_step(dialog._step_titles.index(step_title))
    for _ in range(3):
        app.processEvents()
        dialog.repaint()
    capture_widget(dialog, output_path)
    dialog.close()


def capture_conversion_examples(app: QApplication) -> None:
    dialog = build_dialog(conversion_scan(), conversion_preview(), blocked_conversion())
    dialog.resize(WINDOW_SIZE)
    dialog.show()
    app.processEvents()
    examples = dialog._label_format_examples_dialog()
    examples.show()
    for _ in range(3):
        app.processEvents()
        examples.repaint()
    capture_widget(examples, OUTPUT_DIR / "04-match-labels-conversion-examples.png")
    examples.close()
    dialog.close()


def duplicate_removal_dialog() -> DataInterpretationPreviewDialog:
    dialog = build_dialog(user_added_scan(), user_added_preview(), needs_confirmation())
    dialog._remove_label_carrier(f"{LABEL_ROOT}/A02T.mat")
    return dialog


def base_scan() -> dict[str, Any]:
    eeg_files = [f"{EEG_ROOT}/A01T.gdf", f"{EEG_ROOT}/A02T.gdf", f"{EEG_ROOT}/A03T.gdf"]
    label_files = [
        f"{LABEL_ROOT}/A01T.mat",
        f"{LABEL_ROOT}/A02T.mat",
        f"{LABEL_ROOT}/A03T.mat",
    ]
    return {
        "source_path": EEG_ROOT,
        "source_kind": "folder",
        "eeg_files": eeg_files,
        "label_carriers": label_files,
        "label_carrier_sources": dict.fromkeys(label_files, "auto"),
        "bids": {"is_bids": False, "events_files": []},
    }


def empty_label_scan() -> dict[str, Any]:
    scan = base_scan()
    scan["eeg_files"] = [f"{EEG_ROOT}/A01T.gdf"]
    scan["label_carriers"] = []
    scan["label_carrier_sources"] = {}
    scan["source_kind"] = "file"
    return scan


def user_added_scan() -> dict[str, Any]:
    scan = base_scan()
    scan["label_sources"] = [LABEL_ROOT]
    scan["label_carrier_sources"] = {
        f"{LABEL_ROOT}/A01T.mat": "auto",
        f"{LABEL_ROOT}/A02T.mat": LABEL_ROOT,
        f"{LABEL_ROOT}/A03T.mat": LABEL_ROOT,
    }
    return scan


def many_label_scan() -> dict[str, Any]:
    scan = base_scan()
    carriers = [f"{LABEL_ROOT}/S{index:02d}_events.tsv" for index in range(1, 13)]
    scan["label_carriers"] = carriers
    scan["label_carrier_sources"] = dict.fromkeys(carriers, LABEL_ROOT)
    scan["label_sources"] = [LABEL_ROOT]
    return scan


def internal_scan() -> dict[str, Any]:
    scan = base_scan()
    scan["label_carriers"] = []
    scan["label_carrier_sources"] = {}
    return scan


def bids_scan() -> dict[str, Any]:
    events = f"{EEG_ROOT}/sub-01/eeg/sub-01_task-mi_run-01_events.tsv"
    return {
        "source_path": f"{EEG_ROOT}/bids_like",
        "source_kind": "bids",
        "eeg_files": [f"{EEG_ROOT}/sub-01/eeg/sub-01_task-mi_run-01_eeg.fif"],
        "label_carriers": [events],
        "label_carrier_sources": {events: "auto"},
        "bids": {
            "is_bids": True,
            "subjects": ["01"],
            "events_files": [events],
        },
    }


def conversion_scan() -> dict[str, Any]:
    label = f"{LABEL_ROOT}/custom_labels.mat"
    return {
        "source_path": EEG_ROOT,
        "source_kind": "file",
        "eeg_files": [f"{EEG_ROOT}/A01T.gdf"],
        "label_carriers": [label],
        "label_carrier_sources": {label: LABEL_ROOT},
        "bids": {"is_bids": False, "events_files": []},
    }


def base_preview() -> dict[str, Any]:
    return {
        "summary": "Found 3 EEG file(s) and 3 label/event carrier(s).",
        "source_selection": "3 selected file(s)",
        "selected_eeg_files": [
            f"{EEG_ROOT}/A01T.gdf",
            f"{EEG_ROOT}/A02T.gdf",
            f"{EEG_ROOT}/A03T.gdf",
        ],
        "file_count": 3,
        "label_carrier_count": 3,
        "metadata_preview": metadata_rows(),
        "label_carrier_preview": label_carriers("auto_discovered"),
        "internal_event_preview": internal_event_payload(),
        "recipe_trace": ["scan:scan-1", "candidate:candidate-1"],
    }


def empty_label_preview() -> dict[str, Any]:
    preview = base_preview()
    preview.update(
        {
            "summary": "Found 1 EEG file(s).",
            "source_selection": "Single file",
            "selected_eeg_files": [f"{EEG_ROOT}/A01T.gdf"],
            "file_count": 1,
            "label_carrier_count": 0,
            "label_carrier_preview": [],
        }
    )
    return preview


def user_added_preview() -> dict[str, Any]:
    preview = base_preview()
    preview["label_carrier_preview"] = [
        *label_carriers("auto_discovered", names=["A01T.mat"]),
        *label_carriers("user_added", names=["A02T.mat", "A03T.mat"]),
    ]
    return preview


def many_label_preview() -> dict[str, Any]:
    preview = base_preview()
    rows = []
    for index in range(1, 13):
        name = f"S{index:02d}_events.tsv"
        rows.append(
            label_carrier(
                name,
                f"{LABEL_ROOT}/{name}",
                target_file=f"A{((index - 1) % 3) + 1:02d}T.gdf",
                source_kind="user_added",
                source_location=LABEL_ROOT,
                fmt="TSV",
            )
        )
    preview["label_carrier_preview"] = rows
    preview["label_carrier_count"] = len(rows)
    preview["summary"] = "Found 3 EEG file(s) and 12 label/event carrier(s)."
    return preview


def metadata_preview() -> dict[str, Any]:
    preview = base_preview()
    preview["metadata_preview"] = [
        {
            "file": "A01T.gdf",
            "subject": field("01", "safe", "filename"),
            "session": field("T", "safe", "filename"),
            "task": field("motor-imagery", "safe", "manual"),
            "run": field("", "needs_confirmation", "missing"),
        },
        {
            "file": "A02T.gdf",
            "subject": field("02", "safe", "filename"),
            "session": field("T", "safe", "filename"),
            "task": field("motor-imagery", "safe", "manual"),
            "run": field("", "needs_confirmation", "missing"),
        },
        {
            "file": "A03T.gdf",
            "subject": field("03", "safe", "filename"),
            "session": field("T", "safe", "filename"),
            "task": field("motor-imagery", "safe", "manual"),
            "run": field("", "needs_confirmation", "missing"),
        },
    ]
    return preview


def internal_preview() -> dict[str, Any]:
    preview = empty_label_preview()
    preview.update(
        {
            "summary": "Found 3 EEG file(s).",
            "source_selection": "3 selected file(s)",
            "selected_eeg_files": [
                f"{EEG_ROOT}/A01T.gdf",
                f"{EEG_ROOT}/A02T.gdf",
                f"{EEG_ROOT}/A03T.gdf",
            ],
            "file_count": 3,
            "internal_event_preview": internal_event_payload(),
            "class_map_source": "",
            "class_map": {},
        }
    )
    return preview


def bids_preview() -> dict[str, Any]:
    events_path = f"{EEG_ROOT}/sub-01/eeg/sub-01_task-mi_run-01_events.tsv"
    return {
        "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
        "source_selection": "BIDS folder",
        "selected_eeg_files": [
            f"{EEG_ROOT}/sub-01/eeg/sub-01_task-mi_run-01_eeg.fif",
        ],
        "file_count": 1,
        "label_carrier_count": 1,
        "metadata_preview": [
            {
                "file": "sub-01_task-mi_run-01_eeg.fif",
                "subject": field("01", "safe", "bids"),
                "session": field("", "needs_confirmation", "bids"),
                "task": field("mi", "safe", "bids"),
                "run": field("01", "safe", "bids"),
            }
        ],
        "label_carrier_preview": [
            label_carrier(
                "sub-01_task-mi_run-01_events.tsv",
                events_path,
                target_file="sub-01_task-mi_run-01_eeg.fif",
                fmt="BIDS events",
                label_field="trial_type",
                anchor="onset",
                duration="duration",
                method="interval",
                time_model="seconds",
                granularity="event",
            )
        ],
        "event_roles": {
            "onset": "time anchor",
            "duration": "event duration",
            "trial_type": "class label candidate",
        },
        "warnings": [
            "BIDS-like events are supported; full BIDS validation is not claimed."
        ],
        "action_items": [
            action(
                "BIDS sidecar levels need review.",
                "Class names may remain generic if events.json levels are incomplete.",
                "Review trial_type values before import.",
                "Match Labels",
                "needs_confirmation",
            )
        ],
    }


def conversion_preview() -> dict[str, Any]:
    return {
        "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
        "source_selection": "Single file",
        "selected_eeg_files": [f"{EEG_ROOT}/A01T.gdf"],
        "file_count": 1,
        "label_carrier_count": 1,
        "metadata_preview": [metadata_rows()[0]],
        "label_carrier_preview": [
            {
                "path": f"{LABEL_ROOT}/custom_labels.mat",
                "name": "custom_labels.mat",
                "format": "MAT",
                "target_file": "A01T.gdf",
                "source_kind": "user_added",
                "source_location": LABEL_ROOT,
                "label_candidates": [],
                "anchor_candidates": [],
                "selected_label_field": "",
                "selected_anchor": "",
                "label_row_count": 0,
                "label_value_counts": {},
                "time_model": "unknown",
                "granularity": "unknown",
                "placement_method": "eeg_event",
                "role": "external labels",
                "reason": "No supported label rows were found.",
            }
        ],
        "internal_event_preview": internal_event_payload(),
        "blocked_reasons": [
            "Label file needs conversion before matching: custom_labels.mat."
        ],
        "action_items": [
            action(
                "Label file needs conversion before matching: custom_labels.mat.",
                "Import cannot use this label file until rows and label values are explicit.",
                "View the required table shape and load a converted MAT/CSV/TSV/TXT file.",
                "Match Labels",
                "blocked",
            )
        ],
    }


def review_preview(kind: str) -> dict[str, Any]:
    if kind == "normal":
        preview = base_preview()
        preview["action_items"] = []
        preview["warnings"] = []
        preview["confirmation_items"] = []
        preview["downstream_impacts"] = [
            "Epoch setup can prefill target events from the confirmed label recipe."
        ]
        return preview
    if kind == "blocked":
        return conversion_preview()
    preview = base_preview()
    preview["action_items"] = [
        action(
            "Confirm label placement for A01T.mat.",
            "Label rows and selected EEG events differ by 6 excluded artifact trials.",
            "Review the target EEG event and artifact handling.",
            "Match Labels",
            "needs_confirmation",
        ),
        action(
            "Run metadata is missing for A03T.gdf.",
            "Dataset splits may be ambiguous if run is needed later.",
            "Edit run metadata or confirm it is not required.",
            "Review Metadata",
            "warning",
        ),
    ]
    return preview


def label_carriers(
    source_kind: str, *, names: list[str] | None = None
) -> list[dict[str, Any]]:
    names = names or ["A01T.mat", "A02T.mat", "A03T.mat"]
    result = []
    for name in names:
        result.append(
            label_carrier(
                name,
                f"{LABEL_ROOT}/{name}",
                target_file=name.replace(".mat", ".gdf"),
                source_kind=source_kind,
                source_location=LABEL_ROOT if source_kind == "user_added" else "",
            )
        )
    return result


def label_carrier(
    name: str,
    path: str,
    *,
    target_file: str,
    source_kind: str = "auto_discovered",
    source_location: str = "",
    fmt: str = "MAT",
    label_field: str = "classlabel",
    anchor: str = "768",
    duration: str = "",
    method: str = "eeg_event",
    time_model: str = "trial_order",
    granularity: str = "trial",
) -> dict[str, Any]:
    return {
        "path": path,
        "name": name,
        "format": fmt,
        "target_file": target_file,
        "selected_target_file": target_file,
        "source_kind": source_kind,
        "source_location": source_location,
        "label_candidates": ["classlabel", "trial_type", "condition"],
        "anchor_candidates": ["trial order", "768", "onset", "event_code"],
        "time_field_candidates": ["onset", "sample"],
        "interval_start_candidates": ["onset", "sample"],
        "event_code_candidates": ["event_code", "value"],
        "duration_candidates": ["duration", "end"],
        "selected_label_field": label_field,
        "selected_anchor": anchor,
        "selected_duration_field": duration,
        "label_row_count": 282,
        "label_value_counts": {"1": 72, "2": 70, "3": 70, "4": 70},
        "selected_anchor_stats": {
            "row_count": 282,
            "value_counts": {"769": 72, "770": 70, "771": 70, "772": 70}
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
        "time_model": time_model,
        "granularity": granularity,
        "placement_method": method,
        "role": "external labels",
        "placement_reviews": placement_reviews(),
        "placement_review": placement_reviews()[method],
    }


def internal_event_payload() -> dict[str, Any]:
    return {
        "source": "mne_internal_events",
        "file_count": 3,
        "pattern_status": "Shared event pattern detected",
        "names_reliable": False,
        "candidate_label_events": [
            event_row(
                "769",
                "Class label",
                216,
                "3/3 files",
                "Stable repeated label event group",
            ),
            event_row(
                "770",
                "Class label",
                216,
                "3/3 files",
                "Stable repeated label event group",
            ),
            event_row(
                "771",
                "Class label",
                216,
                "3/3 files",
                "Stable repeated label event group",
            ),
            event_row("772", "Class label", 144, "2/3 files", "Missing in A03T.gdf"),
        ],
        "not_used_events": [
            event_row("768", "Trial timing", 864, "3/3 files", "Trial start marker"),
            event_row(
                "1023",
                "Exclude bad trials",
                18,
                "3/3 files",
                "Rejected / artifact trial",
            ),
            event_row("32766", "Ignore", 3, "3/3 files", "System / boundary marker"),
        ],
    }


def event_row(
    code: str, use_as: str, count: int, coverage: str, evidence: str
) -> dict[str, Any]:
    return {
        "event_code": code,
        "use_as": use_as,
        "event_count": count,
        "coverage": coverage,
        "evidence": evidence,
        "reason": evidence,
    }


def metadata_rows() -> list[dict[str, Any]]:
    return [
        {
            "file": "A01T.gdf",
            "subject": field("01", "safe", "filename"),
            "session": field("T", "safe", "filename"),
            "task": field("motor-imagery", "safe", "manual"),
            "run": field("01", "safe", "manual"),
        },
        {
            "file": "A02T.gdf",
            "subject": field("02", "safe", "filename"),
            "session": field("T", "safe", "filename"),
            "task": field("motor-imagery", "safe", "manual"),
            "run": field("02", "safe", "manual"),
        },
        {
            "file": "A03T.gdf",
            "subject": field("03", "safe", "filename"),
            "session": field("T", "safe", "filename"),
            "task": field("motor-imagery", "safe", "manual"),
            "run": field("", "needs_confirmation", "missing"),
        },
    ]


def field(value: str, decision: str, source: str) -> dict[str, str]:
    return {
        "value": value,
        "decision": decision,
        "source": source,
        "reason": f"{source} metadata",
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
            "summary": "282 rows match; 6 EEG events unlabeled; 0 label rows unmatched.",
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
            "summary": "All 4 label event codes match EEG events.",
        },
    }


def action(
    issue: str,
    impact: str,
    next_action: str,
    target_step: str,
    severity: str,
) -> dict[str, str]:
    return {
        "issue": issue,
        "impact": impact,
        "next_action": next_action,
        "target_step": target_step,
        "severity": severity,
    }


def safe() -> dict[str, Any]:
    return {"decision": "safe", "action_items": []}


def needs_confirmation() -> dict[str, Any]:
    return {
        "decision": "needs_confirmation",
        "required_confirmations": ["Confirm label placement before applying."],
    }


def blocked_conversion() -> dict[str, Any]:
    return {
        "decision": "blocked",
        "blocked_reasons": [
            "Label file needs conversion before matching: custom_labels.mat."
        ],
        "action_items": [
            action(
                "Label file needs conversion before matching: custom_labels.mat.",
                "Import cannot use this label file until rows and label values are explicit.",
                "View the required table shape and load a converted label file.",
                "Match Labels",
                "blocked",
            )
        ],
    }


def write_epoch_handoff_artifact() -> None:
    payload = backend_epoch_handoff_evidence()
    (OUTPUT_DIR / "epoch-handoff-evidence.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def backend_epoch_handoff_evidence() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="xbrainlab_data_import_") as tmp:
        source_dir = Path(tmp)
        eeg_path = source_dir / "A01T.gdf"
        label_path = source_dir / "A01T.mat"
        eeg_path.write_bytes(b"not loaded during scan")
        savemat(label_path, {"classlabel": np.array([1, 2])})

        service = ApplicationService(Study())
        raw = MagicMock()
        raw.get_filepath.return_value = str(eeg_path)
        raw.get_filename.return_value = eeg_path.name
        service.dataset.import_files = MagicMock(return_value=(1, []))
        service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
        service.dataset.apply_labels_legacy = MagicMock(return_value=1)

        service.execute(ScanSourceCommand(source_path=str(source_dir)))
        service.execute(
            PreviewInterpretationCommand(
                choices={
                    "label_carrier_choices": {
                        str(label_path): {
                            "target_file": eeg_path.name,
                            "label_field": "classlabel",
                            "anchor": "768",
                            "placement_method": "eeg_event",
                            "time_model": "trial_order",
                            "granularity": "trial",
                        }
                    },
                    "class_map": {"1": "left", "2": "right"},
                }
            )
        )
        service.execute(ValidateInterpretationCommand())
        result = service.execute(ApplyInterpretationCommand(confirmed=True))
        return {
            "source": "ApplicationService.apply_interpretation",
            "label_apply": result.diagnostics.get("label_apply", {}),
            "epoch_handoff": result.state.interpretation.epoch_handoff,
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
