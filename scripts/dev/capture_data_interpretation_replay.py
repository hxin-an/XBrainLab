#!/usr/bin/env python3
"""Capture UI-observable Data Interpretation replay artifacts.

Expected usage in WSL/headless environments:

    xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import mne
import numpy as np
from PIL import Image
from PyQt6.QtCore import QPoint, QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.study import Study
from XBrainLab.ui.dialogs.dataset import DataInterpretationPreviewDialog
from XBrainLab.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT / "artifacts" / "ui"
SOURCE_DIR = Path(tempfile.gettempdir()) / "xbrainlab_data_interpretation_replay"
SOURCE_PATH = SOURCE_DIR / "sub-01_task-mi_run-1_raw.fif"
SECOND_SOURCE_PATH = SOURCE_DIR / "sub-01_task-mi_run-2_raw.fif"
LABEL_PATH = SOURCE_DIR / "events.tsv"
PREVIEW_SCREENSHOT = ARTIFACTS_DIR / "data-interpretation-preview.png"
REMAP_SCREENSHOT = ARTIFACTS_DIR / "data-interpretation-remap.png"
APPLIED_SCREENSHOT = ARTIFACTS_DIR / "data-interpretation-applied.png"
REPLAY_JSON = ARTIFACTS_DIR / "data-interpretation-replay.json"
WINDOW_SIZE = QSize(1280, 800)


def write_synthetic_raw_fif() -> Path:
    """Write a deterministic synthetic EEG source for the replay."""
    if SOURCE_DIR.exists():
        shutil.rmtree(SOURCE_DIR)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    _write_raw_file(SOURCE_PATH, seed=17)
    _write_raw_file(SECOND_SOURCE_PATH, seed=23)
    LABEL_PATH.write_text(
        "onset\tduration\ttrial_type\n"
        "1.0\t0.5\tleft\n"
        "2.0\t0.5\tright\n"
        "3.0\t0.5\tleft\n"
        "4.0\t0.5\tright\n",
        encoding="utf-8",
    )
    return SOURCE_PATH


def _write_raw_file(path: Path, *, seed: int) -> None:
    """Write one deterministic synthetic EEG file."""
    sfreq = 128
    ch_names = ["C3", "C4", "Cz", "Pz"]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    data = np.random.default_rng(seed).normal(size=(len(ch_names), sfreq * 6))
    raw = mne.io.RawArray(data, info)
    events = np.array(
        [
            [128, 0, 1],
            [256, 0, 2],
            [384, 0, 1],
            [512, 0, 2],
            [640, 0, 1],
            [704, 0, 2],
        ],
    )
    raw.set_annotations(
        mne.annotations_from_events(
            events,
            sfreq=sfreq,
            event_desc={1: "left", 2: "right"},
        )
    )
    raw.save(path, overwrite=True)


def set_capture_geometry(window: QWidget) -> None:
    """Force a deterministic capture geometry."""
    window.setWindowState(Qt.WindowState.WindowNoState)
    screen = window.screen() or QApplication.primaryScreen()
    if screen is not None:
        window.move(screen.availableGeometry().topLeft())
    else:
        window.move(QPoint(0, 0))
    window.resize(WINDOW_SIZE)


def capture_widget(widget: QWidget, output_path: Path) -> None:
    """Capture a widget pixmap and fail if the image is unusable."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Could not grab widget for {output_path.name}.")
    if not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save {output_path}.")
    if is_nearly_black(output_path):
        raise RuntimeError(f"Screenshot is nearly black: {output_path}.")


def is_nearly_black(path: Path) -> bool:
    """Return True when a screenshot contains almost no visible content."""
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


def visible_texts(widget: QWidget) -> list[str]:
    """Collect visible labels for replay evidence."""
    return [
        child.text()
        for child in widget.findChildren(QLabel)
        if child.isVisible() and child.text()
    ]


def button_state(button: Any) -> dict[str, Any]:
    """Return the user-visible state for one button-like widget."""
    return {
        "text": " ".join(str(button.text() or "").split()),
        "enabled": bool(button.isEnabled()),
        "tooltip": " ".join(str(button.toolTip() or "").split()),
    }


def dataset_sidebar_state(sidebar: Any) -> dict[str, dict[str, Any]]:
    """Capture Dataset sidebar button states used by import workflows."""
    return {
        "import_source": button_state(sidebar.import_btn),
        "import_folder": button_state(sidebar.import_folder_btn),
        "reload_recipe": button_state(sidebar.reload_recipe_btn),
        "import_labels": button_state(sidebar.import_label_btn),
        "smart_parse": button_state(sidebar.smart_parse_btn),
        "channel_selection": button_state(sidebar.chan_select_btn),
        "clear_dataset": button_state(sidebar.clear_btn),
    }


def table_state(
    table: QTableWidget,
    *,
    panel: QWidget | None = None,
    right_boundary: QWidget | None = None,
) -> dict[str, Any]:
    """Return visible table text and resize policy for replay evidence."""
    header = table.horizontalHeader()
    headers: list[str] = []
    for column in range(table.columnCount()):
        header_item = table.horizontalHeaderItem(column)
        headers.append(header_item.text() if header_item is not None else "")
    rows: list[list[str]] = []
    for row in range(table.rowCount()):
        row_values: list[str] = []
        for column in range(table.columnCount()):
            item = table.item(row, column)
            row_values.append(item.text() if item is not None else "")
        rows.append(row_values)
    resize_modes = (
        [
            _resize_mode_name(header.sectionResizeMode(column))
            for column in range(table.columnCount())
        ]
        if header is not None
        else []
    )
    header_length = header.length() if header is not None else 0
    stretch_last_section = (
        bool(header.stretchLastSection()) if header is not None else False
    )
    viewport = table.viewport()
    scrollbar = table.horizontalScrollBar()
    state: dict[str, Any] = {
        "headers": headers,
        "rows": rows,
        "resize_modes": resize_modes,
        "stretch_last_section": stretch_last_section,
        "header_length": header_length,
        "viewport_width": viewport.width() if viewport is not None else 0,
        "widget_width": table.width(),
        "widget_x": table.x(),
        "column_widths": [
            table.columnWidth(column) for column in range(table.columnCount())
        ],
        "horizontal_scrollbar_max": scrollbar.maximum() if scrollbar is not None else 0,
        "text_elide_mode": table.textElideMode().name,
    }
    if panel is not None:
        state["panel_width"] = panel.width()
        table_right = table.mapTo(panel, QPoint(table.width(), 0)).x()
        state["table_right_x"] = table_right
        if right_boundary is not None:
            boundary_left = right_boundary.mapTo(panel, QPoint(0, 0)).x()
            state["right_boundary_x"] = boundary_left
            state["right_gap_to_boundary"] = boundary_left - table_right
    return state


def _resize_mode_name(mode: QHeaderView.ResizeMode) -> str:
    return mode.name


def tree_rows(tree: QTreeWidget) -> list[list[str]]:
    """Return visible rows from a QTreeWidget."""
    rows: list[list[str]] = []
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        if item is None:
            continue
        row: list[str] = []
        for column in range(tree.columnCount()):
            widget = tree.itemWidget(item, column)
            if isinstance(widget, QComboBox):
                row.append(widget.currentText())
            else:
                row.append(item.text(column))
        rows.append(row)
    return rows


def tree_state(tree: QTreeWidget) -> dict[str, Any]:
    """Return visible tree text and geometry evidence for replay artifacts."""
    header = tree.header()
    headers: list[str] = []
    for column in range(tree.columnCount()):
        header_item = tree.headerItem()
        headers.append(header_item.text(column) if header_item is not None else "")
    resize_modes = (
        [
            _resize_mode_name(header.sectionResizeMode(column))
            for column in range(tree.columnCount())
        ]
        if header is not None
        else []
    )
    viewport = tree.viewport()
    scrollbar = tree.horizontalScrollBar()
    return {
        "headers": headers,
        "rows": tree_rows(tree),
        "resize_modes": resize_modes,
        "stretch_last_section": (
            bool(header.stretchLastSection()) if header is not None else False
        ),
        "header_length": header.length() if header is not None else 0,
        "viewport_width": viewport.width() if viewport is not None else 0,
        "column_widths": [
            tree.columnWidth(column) for column in range(tree.columnCount())
        ],
        "horizontal_scrollbar_max": scrollbar.maximum() if scrollbar is not None else 0,
        "text_elide_mode": tree.textElideMode().name,
        "alternating_row_colors": tree.alternatingRowColors(),
    }


def set_tree_cell(tree: QTreeWidget, item: Any, column: int, text: str) -> None:
    """Set a tree cell through its widget when the column has an editor."""
    widget = tree.itemWidget(item, column)
    if isinstance(widget, QComboBox):
        widget.setCurrentText(text)
    else:
        item.setText(column, text)


def sanitized(value: Any) -> Any:
    """Replace machine-local paths with stable replay tokens."""
    if isinstance(value, dict):
        return {
            str(sanitized(str(key))): sanitized(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    if isinstance(value, str):
        return value.replace(str(SOURCE_DIR), "<replay_source>")
    return value


def apply_replay_review_choices(
    dialog: DataInterpretationPreviewDialog,
) -> dict[str, Any]:
    """Apply the review choices used by the Data Interpretation replay."""
    metadata_item = dialog.file_tree.topLevelItem(0)
    if metadata_item is not None:
        metadata_item.setText(1, "S01")
        metadata_item.setText(2, "session-01")
        metadata_item.setText(3, "motor-imagery")

    label_item = dialog.label_carrier_tree.topLevelItem(0)
    if label_item is not None:
        target_selector = dialog.label_carrier_tree.itemWidget(label_item, 1)
        if isinstance(target_selector, QComboBox):
            target_selector.setCurrentText(SECOND_SOURCE_PATH.name)
        else:
            label_item.setText(1, SECOND_SOURCE_PATH.name)
        set_tree_cell(dialog.label_carrier_tree, label_item, 3, "trial_type")
        set_tree_cell(dialog.label_carrier_tree, label_item, 4, "onset")
        set_tree_cell(dialog.label_carrier_tree, label_item, 5, "Seconds")
        set_tree_cell(dialog.label_carrier_tree, label_item, 6, "Trial")
        set_tree_cell(
            dialog.label_carrier_tree,
            label_item,
            7,
            "Class cue labels",
        )

    for index in range(dialog.event_tree.topLevelItemCount()):
        event_item = dialog.event_tree.topLevelItem(index)
        if event_item is not None and source_event_field_matches(
            event_item,
            "trial_type",
        ):
            set_tree_cell(dialog.event_tree, event_item, 2, "Class cue")

    dialog_result = dialog.get_result()
    choices = dialog_result.get("choices", {})
    return choices if isinstance(choices, dict) else {}


def source_event_field_matches(item: QTreeWidgetItem, source_field: str) -> bool:
    """Match a source event field after the UI has humanized its visible label."""
    tooltip_match = item.toolTip(0) == f"Source event field: {source_field}"
    legacy_visible_match = item.text(0) == source_field
    return tooltip_match or legacy_visible_match


def capture_replay(app: QApplication) -> int:
    """Run the replay and write JSON / screenshot artifacts."""
    result: dict[str, int] = {"code": 1}
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    source_path = write_synthetic_raw_fif()
    study = Study()
    service = ApplicationService(study)
    window = MainWindow(study)
    set_capture_geometry(window)
    window.show()

    def run_steps() -> None:
        try:
            window.dataset_panel.sidebar.update_sidebar()
            empty_sidebar_buttons = dataset_sidebar_state(window.dataset_panel.sidebar)
            empty_sidebar_state = {
                "buttons": empty_sidebar_buttons,
                "import_label_button_text": (
                    window.dataset_panel.sidebar.import_label_btn.text()
                ),
                "import_label_button_enabled": (
                    window.dataset_panel.sidebar.import_label_btn.isEnabled()
                ),
                "import_label_button_tooltip": (
                    window.dataset_panel.sidebar.import_label_btn.toolTip()
                ),
            }
            scan = service.execute(
                ScanSourceCommand(source_path=str(source_path.parent))
            )
            preview = service.execute(PreviewInterpretationCommand())
            validation = service.execute(ValidateInterpretationCommand())
            dialog = DataInterpretationPreviewDialog(
                window.dataset_panel,
                scan_result=scan.diagnostics["scan_result"],
                preview=preview.diagnostics["preview"],
                validation_decision=validation.diagnostics["validation_decision"],
            )
            dialog.show()
            app.processEvents()
            dialog_choices = apply_replay_review_choices(dialog)
            dialog.repaint()
            app.processEvents()
            capture_widget(dialog, PREVIEW_SCREENSHOT)

            dialog_state = {
                "title": dialog.windowTitle(),
                "decision": dialog.decision,
                "visible_text": visible_texts(dialog),
                "metadata_rows": tree_rows(dialog.file_tree),
                "label_carrier_rows": tree_rows(dialog.label_carrier_tree),
                "event_rows": tree_rows(dialog.event_tree),
                "review_summary_rows": sanitized(tree_rows(dialog.review_tree)),
                "tables": sanitized(
                    {
                        "metadata": tree_state(dialog.file_tree),
                        "label_carriers": tree_state(dialog.label_carrier_tree),
                        "events": tree_state(dialog.event_tree),
                        "review_summary": tree_state(dialog.review_tree),
                    }
                ),
                "review_choices": sanitized(dialog_choices),
                "apply_button_enabled": dialog.decision != "blocked",
                "save_recipe_checked": dialog.save_recipe_check.isChecked(),
                "screenshot": PREVIEW_SCREENSHOT.name,
            }
            dialog.close()

            remap_dialog = DataInterpretationPreviewDialog(
                window.dataset_panel,
                scan_result={
                    "source_path": str(source_path.parent),
                    "source_kind": "folder",
                    "eeg_files": [str(SOURCE_PATH), str(SECOND_SOURCE_PATH)],
                    "label_carriers": [str(LABEL_PATH)],
                },
                preview={
                    "summary": "Reloaded recipe needs file and label carrier remap.",
                    "recipe_reload_summary": {
                        "message": (
                            "Saved recipe choices were reapplied before validation."
                        ),
                        "eeg_file_remap_options": [
                            {
                                "saved": str(SOURCE_DIR / "old_raw.fif"),
                                "saved_name": "old_raw.fif",
                                "candidates": [
                                    {
                                        "path": str(SOURCE_PATH),
                                        "name": SOURCE_PATH.name,
                                    },
                                    {
                                        "path": str(SECOND_SOURCE_PATH),
                                        "name": SECOND_SOURCE_PATH.name,
                                    },
                                ],
                            }
                        ],
                        "label_carrier_remap_options": [
                            {
                                "saved": str(SOURCE_DIR / "old_events.tsv"),
                                "saved_name": "old_events.tsv",
                                "candidates": [
                                    {
                                        "path": str(LABEL_PATH),
                                        "name": LABEL_PATH.name,
                                    }
                                ],
                            }
                        ],
                    },
                },
                validation_decision={
                    "decision": "blocked",
                    "blocked_reasons": [
                        "Selected EEG file(s) were not found in the current scan: old_raw.fif.",
                        "Saved label/event carrier(s) were not found in the current scan: old_events.tsv.",
                    ],
                },
            )
            remap_dialog.show()
            app.processEvents()
            for selector in [
                *getattr(remap_dialog, "_eeg_file_remap_widgets", {}).values(),
                *getattr(remap_dialog, "_label_carrier_remap_widgets", {}).values(),
            ]:
                if isinstance(selector, QComboBox) and not selector.currentData():
                    next_index = 1 if selector.count() > 1 else 0
                    selector.setCurrentIndex(next_index)
            app.processEvents()
            remap_dialog.repaint()
            app.processEvents()
            capture_widget(remap_dialog, REMAP_SCREENSHOT)
            remap_ok_button = remap_dialog.button_box.button(
                QDialogButtonBox.StandardButton.Ok,
            )
            remap_dialog_state = {
                "title": remap_dialog.windowTitle(),
                "decision": remap_dialog.decision,
                "visible_text": visible_texts(remap_dialog),
                "review_summary_rows": sanitized(tree_rows(remap_dialog.review_tree)),
                "tables": sanitized(
                    {
                        "metadata": tree_state(remap_dialog.file_tree),
                        "label_carriers": tree_state(remap_dialog.label_carrier_tree),
                        "events": tree_state(remap_dialog.event_tree),
                        "review_summary": tree_state(remap_dialog.review_tree),
                    }
                ),
                "remap_choices": sanitized(
                    remap_dialog.get_result().get("choices", {})
                ),
                "apply_button_enabled": (
                    remap_ok_button.isEnabled()
                    if remap_ok_button is not None
                    else False
                ),
                "screenshot": REMAP_SCREENSHOT.name,
            }
            remap_dialog.close()

            reviewed_preview = service.execute(
                PreviewInterpretationCommand(
                    scan_id=scan.diagnostics["scan_result"]["scan_id"],
                    choices=dialog_choices,
                )
            )
            reviewed_validation = service.execute(ValidateInterpretationCommand())
            apply_without_confirmation = service.execute(ApplyInterpretationCommand())
            apply_confirmed = service.execute(
                ApplyInterpretationCommand(confirmed=True),
            )
            window.dataset_panel.update_panel()
            window.switch_page(0)
            set_capture_geometry(window)
            app.processEvents()
            window.repaint()
            app.processEvents()
            capture_widget(window, APPLIED_SCREENSHOT)

            replay = {
                "workflow": "data_interpretation_ui_replay",
                "source": SOURCE_DIR.name,
                "transcript": [
                    "Selected folder source for interpretation.",
                    "Scanned source and previewed metadata plus label carrier "
                    "interpretation.",
                    "Mapped generic events.tsv to the second EEG file in the wizard.",
                    "Reviewed label column, anchor, time model, granularity, and role.",
                    "Confirmed trial_type as the class cue event role.",
                    "Validation required confirmation for missing metadata.",
                    "Unconfirmed apply was blocked.",
                    "Confirmed apply loaded the interpreted source.",
                ],
                "commands": {
                    "scan_source": sanitized(scan.to_dict()),
                    "preview_interpretation": sanitized(preview.to_dict()),
                    "validate_interpretation": sanitized(validation.to_dict()),
                    "reviewed_preview": sanitized(reviewed_preview.to_dict()),
                    "reviewed_validation": sanitized(reviewed_validation.to_dict()),
                    "apply_without_confirmation": sanitized(
                        apply_without_confirmation.to_dict(),
                    ),
                    "apply_confirmed": sanitized(apply_confirmed.to_dict()),
                },
                "ui_state": {
                    "dialog": dialog_state,
                    "remap_dialog": remap_dialog_state,
                    "dataset_panel": {
                        "sidebar_buttons": dataset_sidebar_state(
                            window.dataset_panel.sidebar,
                        ),
                        "import_button_text": (
                            window.dataset_panel.sidebar.import_btn.text()
                        ),
                        "import_button_enabled": (
                            window.dataset_panel.sidebar.import_btn.isEnabled()
                        ),
                        "import_label_button_text": (
                            window.dataset_panel.sidebar.import_label_btn.text()
                        ),
                        "import_label_button_enabled": (
                            window.dataset_panel.sidebar.import_label_btn.isEnabled()
                        ),
                        "import_label_button_tooltip": (
                            window.dataset_panel.sidebar.import_label_btn.toolTip()
                        ),
                        "table_rows": window.dataset_panel.table.rowCount(),
                        "table": table_state(
                            window.dataset_panel.table,
                            panel=window.dataset_panel,
                            right_boundary=window.dataset_panel.sidebar,
                        ),
                        "visible_panel_text": visible_texts(window.dataset_panel),
                        "screenshot": APPLIED_SCREENSHOT.name,
                    },
                    "empty_dataset_sidebar": empty_sidebar_state,
                },
            }
            REPLAY_JSON.write_text(
                json.dumps(replay, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            result["code"] = 0
        except Exception as exc:
            print(f"Replay capture failed: {exc}", file=sys.stderr)
            result["code"] = 1
        finally:
            window.close()
            app.quit()

    QTimer.singleShot(1500, run_steps)
    app.exec()
    return result["code"]


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    return capture_replay(app)


if __name__ == "__main__":
    raise SystemExit(main())
