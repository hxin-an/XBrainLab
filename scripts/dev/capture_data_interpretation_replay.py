#!/usr/bin/env python3
"""Capture UI-observable Data Interpretation replay artifacts.

Expected usage in WSL/headless environments:

    xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py
"""

from __future__ import annotations

import json
import re
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
LABEL_SIDECAR_PATH = SOURCE_DIR / "events.json"
PREVIEW_SCREENSHOT = ARTIFACTS_DIR / "data-interpretation-preview.png"
REMAP_SCREENSHOT = ARTIFACTS_DIR / "data-interpretation-remap.png"
APPLIED_SCREENSHOT = ARTIFACTS_DIR / "data-interpretation-applied.png"
REPLAY_JSON = ARTIFACTS_DIR / "data-interpretation-replay.json"
WINDOW_SIZE = QSize(1280, 800)
GEOMETRY_WIDTH_TOLERANCE_PX = 2
VISIBLE_INTERNAL_MARKERS = (
    "scan_source",
    "preview_interpretation",
    "validate_interpretation",
    "apply_interpretation",
    "save_interpretation_recipe",
    "reload_interpretation_recipe",
)
VISIBLE_TRACE_TOKEN_PATTERN = re.compile(
    r"\b(?:scan|candidate|metadata|metadata_override|choices|label_import|"
    r"label_carrier|class_map|recipe):[A-Za-z0-9_.<>/-]+",
)


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
    LABEL_SIDECAR_PATH.write_text(
        json.dumps(
            {
                "trial_type": {
                    "Levels": {
                        "left": "Left hand",
                        "right": "Right hand",
                    },
                },
            },
            indent=2,
        )
        + "\n",
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
        "import_bids": button_state(sidebar.import_bids_btn)
        if hasattr(sidebar, "import_bids_btn")
        else {"text": "", "enabled": False, "tooltip": ""},
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
    horizontal_scrollbar = table.horizontalScrollBar()
    vertical_scrollbar = table.verticalScrollBar()
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
        "horizontal_scrollbar_max": (
            horizontal_scrollbar.maximum() if horizontal_scrollbar is not None else 0
        ),
        "vertical_scrollbar_max": (
            vertical_scrollbar.maximum() if vertical_scrollbar is not None else 0
        ),
        "partial_visible_rows": partial_visible_table_rows(table),
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
    horizontal_scrollbar = tree.horizontalScrollBar()
    vertical_scrollbar = tree.verticalScrollBar()
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
        "horizontal_scrollbar_max": (
            horizontal_scrollbar.maximum() if horizontal_scrollbar is not None else 0
        ),
        "vertical_scrollbar_max": (
            vertical_scrollbar.maximum() if vertical_scrollbar is not None else 0
        ),
        "partial_visible_rows": partial_visible_tree_rows(tree),
        "text_elide_mode": tree.textElideMode().name,
        "alternating_row_colors": tree.alternatingRowColors(),
    }


def build_replay_geometry_review(ui_state: dict[str, Any]) -> dict[str, Any]:
    """Check replay table/tree geometry for overflow, underfill, and clipped rows."""
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for widget_name, state in iter_geometry_states(ui_state):
        header_length = geometry_int(state, "header_length")
        viewport_width = geometry_int(state, "viewport_width")
        if header_length <= 0 or viewport_width <= 0:
            continue
        horizontal_scrollbar_max = geometry_int(state, "horizontal_scrollbar_max")
        width_gap = viewport_width - header_length
        partial_visible_rows = geometry_int_list(state, "partial_visible_rows")
        has_right_boundary = "right_gap_to_boundary" in state
        right_gap_to_boundary = (
            geometry_int(state, "right_gap_to_boundary") if has_right_boundary else 0
        )
        fits_viewport = (
            header_length <= viewport_width + GEOMETRY_WIDTH_TOLERANCE_PX
            and horizontal_scrollbar_max == 0
        )
        fills_viewport = width_gap <= GEOMETRY_WIDTH_TOLERANCE_PX
        fills_content_boundary = (
            not has_right_boundary
            or abs(right_gap_to_boundary) <= GEOMETRY_WIDTH_TOLERANCE_PX
        )
        shows_only_complete_rows = not partial_visible_rows
        row = {
            "widget": widget_name,
            "headers": list(state.get("headers", [])),
            "row_count": len(state.get("rows", []))
            if isinstance(state.get("rows"), list)
            else 0,
            "header_length": header_length,
            "viewport_width": viewport_width,
            "width_gap": width_gap,
            "widget_width": geometry_int(state, "widget_width"),
            "panel_width": geometry_int(state, "panel_width"),
            "right_gap_to_boundary": right_gap_to_boundary,
            "horizontal_scrollbar_max": horizontal_scrollbar_max,
            "vertical_scrollbar_max": geometry_int(state, "vertical_scrollbar_max"),
            "partial_visible_rows": partial_visible_rows,
            "fits_viewport": fits_viewport,
            "fills_viewport": fills_viewport,
            "fills_content_boundary": fills_content_boundary,
            "shows_only_complete_rows": shows_only_complete_rows,
            "resize_modes": list(state.get("resize_modes", [])),
            "column_widths": list(state.get("column_widths", [])),
            "text_elide_mode": state.get("text_elide_mode"),
            "alternating_row_colors": state.get("alternating_row_colors"),
        }
        rows.append(row)
        if (
            not fits_viewport
            or not fills_viewport
            or not fills_content_boundary
            or not shows_only_complete_rows
        ):
            findings.append(row)
    return {
        "passed": bool(rows) and not findings,
        "checked_widgets": len(rows),
        "width_tolerance_px": GEOMETRY_WIDTH_TOLERANCE_PX,
        "findings": findings,
        "clipped_row_findings": [
            row for row in findings if not row.get("shows_only_complete_rows", True)
        ],
        "rows": rows,
        "boundary": (
            "Automated replay geometry checks table/tree header width, viewport "
            "fill, horizontal scrollbar state, optional content-boundary gap, "
            "and clipped visible rows. It is not a substitute for human UI review."
        ),
    }


def build_visible_text_review(ui_state: dict[str, Any]) -> dict[str, Any]:
    """Check UI-observable text for raw internal command or recipe trace tokens."""
    rows: list[dict[str, Any]] = []
    for location, text in iter_visible_text_values(ui_state):
        lowered = text.lower()
        markers = [marker for marker in VISIBLE_INTERNAL_MARKERS if marker in lowered]
        trace_tokens = VISIBLE_TRACE_TOKEN_PATTERN.findall(text)
        if markers or trace_tokens:
            rows.append(
                {
                    "location": location,
                    "text": text,
                    "markers": markers,
                    "trace_tokens": trace_tokens,
                }
            )
    return {
        "passed": not rows,
        "findings": rows,
        "boundary": (
            "Checks user-visible replay text for selected raw command names and "
            "recipe trace tokens. Backend command payloads and diagnostics may "
            "still preserve raw trace values."
        ),
    }


def ensure_visible_text_review_passed(visible_text_review: dict[str, Any]) -> None:
    """Raise when UI-observable replay text exposes internal tokens."""
    if visible_text_review["passed"]:
        return
    raise RuntimeError(
        "Data Interpretation replay visible-text review failed: "
        f"{visible_text_review['findings']}",
    )


def iter_visible_text_values(
    value: Any,
    prefix: str = "",
) -> list[tuple[str, str]]:
    """Flatten UI state visible-text fields and table/tree rows into text entries."""
    rows: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            location = f"{prefix}.{key}" if prefix else str(key)
            if key in {
                "visible_text",
                "visible_panel_text",
                "metadata_rows",
                "label_carrier_rows",
                "event_rows",
                "review_summary_rows",
                "rows",
            } or isinstance(item, dict):
                rows.extend(iter_visible_text_values(item, location))
        return rows
    if isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(iter_visible_text_values(item, f"{prefix}[{index}]"))
        return rows
    if isinstance(value, str) and value.strip():
        return [(prefix, " ".join(value.split()))]
    return rows


def ensure_replay_geometry_passed(geometry_review: dict[str, Any]) -> None:
    """Raise when replay geometry evidence contains findings."""
    if geometry_review["passed"]:
        return
    raise RuntimeError(
        "Data Interpretation replay geometry review failed: "
        f"{geometry_review['findings']}",
    )


def iter_geometry_states(
    value: Any,
    prefix: str = "",
) -> list[tuple[str, dict[str, Any]]]:
    """Flatten nested replay state maps into named geometry states."""
    if not isinstance(value, dict):
        return []
    if "header_length" in value and "viewport_width" in value:
        return [(prefix or "widget", value)]
    rows: list[tuple[str, dict[str, Any]]] = []
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        rows.extend(iter_geometry_states(item, name))
    return rows


def geometry_int(state: dict[str, Any], key: str) -> int:
    """Read an integer geometry field from an artifact row."""
    try:
        return int(state.get(key, 0))
    except (TypeError, ValueError):
        return 0


def geometry_int_list(state: dict[str, Any], key: str) -> list[int]:
    """Read a list of integer geometry fields from an artifact row."""
    value = state.get(key, [])
    if not isinstance(value, list):
        return []
    rows: list[int] = []
    for item in value:
        try:
            rows.append(int(item))
        except (TypeError, ValueError):
            continue
    return rows


def partial_visible_tree_rows(tree: QTreeWidget) -> list[int]:
    """Return row indexes that are visibly clipped at the viewport bottom."""
    viewport = tree.viewport()
    if viewport is None:
        return []
    viewport_bottom = viewport.rect().bottom()
    partial: list[int] = []
    for row in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(row)
        if item is None:
            continue
        rect = tree.visualItemRect(item)
        if rect.isValid() and rect.top() < viewport_bottom < rect.bottom():
            partial.append(row)
    return partial


def partial_visible_table_rows(table: QTableWidget) -> list[int]:
    """Return row indexes that are visibly clipped at the viewport bottom."""
    viewport = table.viewport()
    if viewport is None:
        return []
    viewport_bottom = viewport.rect().bottom()
    partial: list[int] = []
    for row in range(table.rowCount()):
        top = table.rowViewportPosition(row)
        bottom = top + table.rowHeight(row)
        if top < viewport_bottom < bottom:
            partial.append(row)
    return partial


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
            target_index = target_selector.findData(SECOND_SOURCE_PATH.name)
            if target_index >= 0:
                target_selector.setCurrentIndex(target_index)
            else:
                target_selector.setCurrentText(SECOND_SOURCE_PATH.name)
        else:
            visible_selector = getattr(dialog, "_eeg_label_widgets", {}).get(
                SECOND_SOURCE_PATH.name
            )
            if isinstance(visible_selector, QComboBox):
                next_index = 1 if visible_selector.count() > 1 else 0
                visible_selector.setCurrentIndex(next_index)
            else:
                label_item.setText(1, SECOND_SOURCE_PATH.name)
        set_tree_cell(dialog.label_carrier_tree, label_item, 2, "trial_type")
        set_tree_cell(dialog.label_carrier_tree, label_item, 3, "onset")
        set_tree_cell(dialog.label_carrier_tree, label_item, 4, "Trial")
        set_tree_cell(
            dialog.label_carrier_tree,
            label_item,
            5,
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


def show_dialog_step(
    dialog: DataInterpretationPreviewDialog,
    step_title: str,
    app: QApplication,
) -> None:
    """Show one wizard step before screenshot or geometry capture."""
    step_titles = getattr(dialog, "_step_titles", [])
    if step_title in step_titles:
        dialog._go_to_step(step_titles.index(step_title))
    app.processEvents()


def tree_state_for_step(
    dialog: DataInterpretationPreviewDialog,
    step_title: str,
    tree: QTreeWidget,
    app: QApplication,
) -> dict[str, Any]:
    """Capture geometry for the tree while its wizard panel is visible."""
    show_dialog_step(dialog, step_title, app)
    dialog._fit_all_tree_columns_to_viewport()
    app.processEvents()
    return tree_state(tree)


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
            show_dialog_step(dialog, "Review and Import", app)
            dialog.repaint()
            app.processEvents()
            capture_widget(dialog, PREVIEW_SCREENSHOT)
            ok_button = dialog.apply_button

            dialog_state = {
                "title": dialog.windowTitle(),
                "decision": dialog.decision,
                "current_step": "Review and Import",
                "back_button": {
                    "text": dialog.back_button.text(),
                    "enabled": dialog.back_button.isEnabled(),
                },
                "next_button": {
                    "text": dialog.next_button.text(),
                    "visible": dialog.next_button.isVisible(),
                },
                "visible_text": visible_texts(dialog),
                "metadata_rows": tree_rows(dialog.file_tree),
                "label_carrier_rows": tree_rows(dialog.label_carrier_tree),
                "event_rows": tree_rows(dialog.event_tree),
                "review_summary_rows": sanitized(tree_rows(dialog.review_tree)),
                "tables": sanitized(
                    {
                        "metadata": tree_state_for_step(
                            dialog,
                            "Review Metadata",
                            dialog.file_tree,
                            app,
                        ),
                        "label_carriers": tree_state_for_step(
                            dialog,
                            "Match Labels",
                            dialog.label_carrier_tree,
                            app,
                        ),
                        "events": tree_state_for_step(
                            dialog,
                            "Match Labels",
                            dialog.event_tree,
                            app,
                        ),
                        "review_summary": tree_state_for_step(
                            dialog,
                            "Review and Import",
                            dialog.review_tree,
                            app,
                        ),
                    }
                ),
                "review_choices": sanitized(dialog_choices),
                "apply_button_enabled": (
                    ok_button.isEnabled() if ok_button is not None else False
                ),
                "apply_button_visible": (
                    ok_button.isVisible() if ok_button is not None else False
                ),
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
            show_dialog_step(remap_dialog, "Review and Import", app)
            remap_dialog.repaint()
            app.processEvents()
            capture_widget(remap_dialog, REMAP_SCREENSHOT)
            remap_ok_button = remap_dialog.apply_button
            remap_dialog_state = {
                "title": remap_dialog.windowTitle(),
                "decision": remap_dialog.decision,
                "current_step": "Review and Import",
                "visible_text": visible_texts(remap_dialog),
                "review_summary_rows": sanitized(tree_rows(remap_dialog.review_tree)),
                "tables": sanitized(
                    {
                        "metadata": tree_state_for_step(
                            remap_dialog,
                            "Review Metadata",
                            remap_dialog.file_tree,
                            app,
                        ),
                        "label_carriers": tree_state_for_step(
                            remap_dialog,
                            "Match Labels",
                            remap_dialog.label_carrier_tree,
                            app,
                        ),
                        "events": tree_state_for_step(
                            remap_dialog,
                            "Match Labels",
                            remap_dialog.event_tree,
                            app,
                        ),
                        "review_summary": tree_state_for_step(
                            remap_dialog,
                            "Review and Import",
                            remap_dialog.review_tree,
                            app,
                        ),
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
            geometry_review = build_replay_geometry_review(replay["ui_state"])
            visible_text_review = build_visible_text_review(replay["ui_state"])
            replay["ui_quality_review"] = {
                "geometry": geometry_review,
                "visible_text": visible_text_review,
                "human_design_review_boundary": (
                    "This automated replay catches obvious table/tree geometry "
                    "and visible internal-token regressions. Human desktop review "
                    "still decides polish, DPI, and Windows launcher acceptance."
                ),
            }
            ensure_replay_geometry_passed(geometry_review)
            ensure_visible_text_review_passed(visible_text_review)
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
