#!/usr/bin/env python3
"""Capture UI-observable Data Interpretation replay artifacts.

Expected usage in WSL/headless environments:

    xvfb-run -a poetry run -- python scripts/dev/capture_data_interpretation_replay.py \
        --output-dir /tmp/xbrainlab-data-interpretation-replay

The current tree keeps Data Import wizard screenshots under
``build/dev-artifacts/data-import-wizard-steps/``. This replay helper is kept for
targeted debugging and must not repopulate the tracked ``artifacts/`` namespace
screenshots as canonical evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

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

from scripts.dev.ui_navigation import open_workflow_panel
from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
from XBrainLab.ui.dialogs.dataset import DataInterpretationPreviewDialog
from XBrainLab.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = "scripts/dev/capture_data_interpretation_replay.py"
SCHEMA_VERSION = 1
FINGERPRINT_PATTERNS = (
    GENERATOR,
    "pyproject.toml",
    "poetry.lock",
    "XBrainLab/backend/application/data_interpretation_*.py",
    "XBrainLab/backend/application/resource_guard.py",
    "XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py",
    "XBrainLab/ui/dialogs/dataset/event_value_decision_editor.py",
    "XBrainLab/ui/dialogs/dataset/internal_event_step.py",
    "XBrainLab/ui/dialogs/dataset/label_placement_step.py",
    "XBrainLab/ui/dialogs/dataset/load_labels_step.py",
    "XBrainLab/ui/dialogs/dataset/review_import_presenter.py",
    "XBrainLab/ui/dialogs/dataset/review_import_step.py",
    "XBrainLab/ui/dialogs/dataset/review_presenter.py",
    "XBrainLab/ui/dialogs/dataset/wizard_host_protocol.py",
    "XBrainLab/ui/dialogs/dataset/wizard_state.py",
    "XBrainLab/ui/components/info_panel.py",
    "XBrainLab/ui/components/info_panel_service.py",
    "XBrainLab/ui/panels/dataset/actions.py",
    "XBrainLab/ui/panels/dataset/panel.py",
    "XBrainLab/ui/panels/dataset/sidebar.py",
    "XBrainLab/ui/styles/stylesheets.py",
    "XBrainLab/ui/styles/theme.py",
)
DEFAULT_ARTIFACTS_DIR = (
    Path(tempfile.gettempdir()) / "xbrainlab_data_interpretation_replay_artifacts"
)
SOURCE_DIR = Path(tempfile.gettempdir()) / "xbrainlab_data_interpretation_replay"
SOURCE_PATH = SOURCE_DIR / "sub-01_task-mi_run-1_raw.fif"
SECOND_SOURCE_PATH = SOURCE_DIR / "sub-01_task-mi_run-2_raw.fif"
LABEL_PATH = SOURCE_DIR / "events.tsv"
LABEL_SIDECAR_PATH = SOURCE_DIR / "events.json"
WINDOW_SIZE = QSize(1280, 800)
GEOMETRY_WIDTH_TOLERANCE_PX = 2
WINDOW_CLOSE_TIMEOUT_MS = 8_000
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


@dataclass
class ReplayArtifactPaths:
    """Mutable replay artifact target paths for CLI and tests."""

    directory: Path

    @property
    def preview_screenshot(self) -> Path:
        return self.directory / "data-interpretation-preview.png"

    @property
    def remap_screenshot(self) -> Path:
        return self.directory / "data-interpretation-remap.png"

    @property
    def applied_screenshot(self) -> Path:
        return self.directory / "data-interpretation-applied.png"

    @property
    def replay_json(self) -> Path:
        return self.directory / "data-interpretation-replay.json"


ARTIFACT_PATHS = ReplayArtifactPaths(DEFAULT_ARTIFACTS_DIR)


def source_file_manifest() -> list[dict[str, str]]:
    """Return the exact product source represented by this replay."""
    paths: set[Path] = set()
    for pattern in FINGERPRINT_PATTERNS:
        matches = [path for path in ROOT.glob(pattern) if path.is_file()]
        if not matches:
            raise FileNotFoundError(f"Replay fingerprint source is missing: {pattern}")
        paths.update(matches)
    return [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix())
    ]


def source_fingerprint(
    source_files: Iterable[Mapping[str, str]] | None = None,
) -> str:
    """Hash the ordered source manifest used by the replay."""
    digest = hashlib.sha256()
    records = source_file_manifest() if source_files is None else source_files
    for record in records:
        digest.update(record["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def ensure_source_manifest_stable(
    source_files_at_start: list[dict[str, str]],
) -> None:
    """Reject replay evidence when represented source changes mid-capture."""
    if source_file_manifest() != source_files_at_start:
        raise RuntimeError(
            "Data Import source changed while replay evidence was captured."
        )


def artifact_file_manifest(
    artifact_paths: Mapping[str, Path],
    *,
    artifact_root: Path,
) -> dict[str, dict[str, object]]:
    """Return fail-closed identities for replay screenshots."""
    root = artifact_root.resolve()
    manifest: dict[str, dict[str, object]] = {}
    for name, path in sorted(artifact_paths.items()):
        resolved = path.resolve(strict=True)
        relative_path = resolved.relative_to(root).as_posix()
        content = resolved.read_bytes()
        manifest[name] = {
            "relative_path": relative_path,
            "sha256": hashlib.sha256(content).hexdigest(),
            "byte_size": len(content),
        }
    return manifest


def set_artifact_dir(output_dir: Path) -> None:
    """Set replay output paths; tests should use tmp paths by default."""
    ARTIFACT_PATHS.directory = output_dir


def write_synthetic_raw_fif() -> Path:
    """Write a deterministic synthetic EEG source for the replay."""
    if SOURCE_DIR.exists():
        shutil.rmtree(SOURCE_DIR)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    _write_raw_file(SOURCE_PATH, seed=17)
    _write_raw_file(SECOND_SOURCE_PATH, seed=23)
    LABEL_PATH.write_text(
        "onset\tduration\ttrial_type\n"
        "0.5\t0.5\tleft\n"
        "1.2\t0.5\tright\n"
        "1.9\t0.5\tleft\n"
        "2.6\t0.5\tright\n"
        "3.3\t0.5\tleft\n"
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
    settle_widget_for_capture(widget)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Could not grab widget for {output_path.name}.")
    if not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save {output_path}.")
    if is_nearly_black(output_path):
        raise RuntimeError(f"Screenshot is nearly black: {output_path}.")


def settle_widget_for_capture(widget: QWidget, *, wait_ms: int = 500) -> None:
    """Flush deferred layouts and child paints before recording evidence."""
    app = QApplication.instance()
    if app is None:
        return
    widget.updateGeometry()
    widget.repaint()
    for child in widget.findChildren(QWidget):
        if child.isVisible():
            child.update()
    app.processEvents()
    deadline = time.monotonic() + max(wait_ms, 0) / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


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


def pairing_rows(dialog: DataInterpretationPreviewDialog) -> list[list[str]]:
    """Return the EEG-to-label rows that are actually visible to the user."""
    rows: list[list[str]] = []
    selectors = getattr(dialog, "_eeg_label_widgets", {})
    badges = getattr(dialog, "_eeg_label_status_widgets", {})
    for eeg_file, selector in selectors.items():
        if not isinstance(selector, QComboBox):
            continue
        badge = badges.get(eeg_file)
        status = badge.text() if isinstance(badge, QLabel) else ""
        rows.append([eeg_file, selector.currentText(), status])
    return rows


def pairing_rows_state(dialog: DataInterpretationPreviewDialog) -> dict[str, Any]:
    """Capture geometry and values from the visible file-pairing controls."""
    widget = dialog.label_pairing_rows_widget
    selectors = getattr(dialog, "_eeg_label_widgets", {})
    badges = getattr(dialog, "_eeg_label_status_widgets", {})
    overflowing_controls: list[str] = []
    for eeg_file, control in [*selectors.items(), *badges.items()]:
        if not isinstance(control, QWidget):
            continue
        top_left = control.mapTo(widget, QPoint(0, 0))
        if top_left.x() < 0 or top_left.x() + control.width() > widget.width():
            overflowing_controls.append(str(eeg_file))
    width = max(widget.width(), 0)
    return {
        "headers": ["EEG file", "Label file", "Status"],
        "rows": pairing_rows(dialog),
        "visible": widget.isVisibleTo(dialog),
        "header_length": width,
        "viewport_width": width,
        "widget_width": width,
        "horizontal_scrollbar_max": 0,
        "vertical_scrollbar_max": 0,
        "partial_visible_rows": [],
        "overflowing_controls": sorted(set(overflowing_controls)),
        "text_elide_mode": "visible controls",
        "alternating_row_colors": False,
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
        visible = bool(state.get("visible", True))
        overflowing_controls = [
            str(value) for value in state.get("overflowing_controls", [])
        ]
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
            "visible": visible,
            "overflowing_controls": overflowing_controls,
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
            or not visible
            or bool(overflowing_controls)
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
                "file_pairing_rows",
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

    app = QApplication.instance()
    if app is not None:
        show_dialog_step(dialog, "Match Labels", app)
    pairing_selector = getattr(dialog, "_eeg_label_widgets", {}).get(
        SECOND_SOURCE_PATH.name
    )
    if not isinstance(pairing_selector, QComboBox):
        selectors = list(getattr(dialog, "_eeg_label_widgets", {}).values())
        pairing_selector = selectors[-1] if selectors else None
    if isinstance(pairing_selector, QComboBox):
        desired_index = pairing_selector.findData(str(LABEL_PATH))
        if desired_index < 0:
            desired_index = 1 if pairing_selector.count() > 1 else 0
        pairing_selector.setCurrentIndex(desired_index)

    for selector_name, value in (
        ("rule_label_field_combo", "trial_type"),
        ("rule_use_as_combo", "class cue labels"),
    ):
        selector = getattr(dialog, selector_name, None)
        if isinstance(selector, QComboBox):
            index = selector.findData(value)
            if index >= 0:
                selector.setCurrentIndex(index)

    value_editor = getattr(dialog, "event_value_editor", None)
    if value_editor is not None and value_editor.has_rows():
        class_names = {"left": "Left hand", "right": "Right hand"}
        for raw_value in value_editor.unresolved_values():
            value_editor.set_value_decision(
                raw_value,
                role="stimulus",
                use="class",
                class_name=class_names.get(raw_value, raw_value),
            )

    for index in range(dialog.event_tree.topLevelItemCount()):
        event_item = dialog.event_tree.topLevelItem(index)
        if (
            event_item is not None
            and dialog.event_tree.isVisibleTo(dialog)
            and source_event_field_matches(
                event_item,
                "trial_type",
            )
        ):
            set_tree_cell(dialog.event_tree, event_item, 2, "Class cue")

    dialog_result = dialog.get_result()
    choices = dialog_result.get("choices", {})
    if not isinstance(choices, dict):
        return {}
    selected_eeg_files = dialog.preview.get("selected_eeg_files")
    if isinstance(selected_eeg_files, list) and selected_eeg_files:
        choices["selected_eeg_files"] = [
            str(path) for path in selected_eeg_files if str(path).strip()
        ]
    return choices


def ensure_confirmed_apply_succeeded(command_result: Any) -> None:
    """Fail replay evidence unless the confirmed product command succeeded."""
    typed_ok = getattr(command_result, "ok", None)
    if typed_ok is True:
        return
    to_dict = getattr(command_result, "to_dict", None)
    payload = to_dict() if callable(to_dict) else command_result
    if not isinstance(payload, dict):
        raise RuntimeError("Confirmed apply failed: command result is unavailable.")
    status = str(payload.get("status") or "").strip().casefold()
    if payload.get("ok") is True or status in {"ok", "success"}:
        return
    message = str(payload.get("message") or "Unknown apply failure.").strip()
    raise RuntimeError(f"Confirmed apply failed: {message}")


def source_event_field_matches(item: QTreeWidgetItem, source_field: str) -> bool:
    """Match a source event field after the UI has humanized its visible label."""
    tooltip_match = item.toolTip(0) == f"Source event field: {source_field}"
    legacy_visible_match = item.text(0) == source_field
    return tooltip_match or legacy_visible_match


def show_dialog_step(
    dialog: DataInterpretationPreviewDialog,
    step_title: str,
    app: Any,
) -> None:
    """Show one wizard step before screenshot or geometry capture."""
    step_titles = getattr(dialog, "_step_titles", [])
    if step_title in step_titles:
        dialog._go_to_step(step_titles.index(step_title))
    process_events = getattr(app, "processEvents", None)
    if callable(process_events):
        process_events()
        return
    qt_app = QApplication.instance()
    if qt_app is not None:
        qt_app.processEvents()


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


def pairing_rows_state_for_step(
    dialog: DataInterpretationPreviewDialog,
    step_title: str,
    app: Any,
) -> dict[str, Any]:
    """Capture the user-facing pairing grid while its wizard step is visible."""
    show_dialog_step(dialog, step_title, app)
    process_events = getattr(app, "processEvents", None)
    if callable(process_events):
        process_events()
    else:
        qt_app = QApplication.instance()
        if qt_app is not None:
            qt_app.processEvents()
    return pairing_rows_state(dialog)


def capture_replay(app: QApplication) -> int:
    """Run the replay and write JSON / screenshot artifacts."""
    result: dict[str, int] = {"code": 1}
    source_files_at_start = source_file_manifest()
    source_fingerprint_at_start = source_fingerprint(source_files_at_start)
    ARTIFACT_PATHS.directory.mkdir(parents=True, exist_ok=True)
    source_path = write_synthetic_raw_fif()
    study = Study()
    service = get_application_service(study)
    window = MainWindow(study)
    dataset_panel = cast(Any, window).dataset_panel
    set_capture_geometry(window)
    window.show()

    def run_steps() -> None:
        try:
            dataset_panel.sidebar.update_sidebar()
            empty_sidebar_buttons = dataset_sidebar_state(dataset_panel.sidebar)
            empty_sidebar_state = {
                "buttons": empty_sidebar_buttons,
                "import_label_button_text": (
                    dataset_panel.sidebar.import_label_btn.text()
                ),
                "import_label_button_enabled": (
                    dataset_panel.sidebar.import_label_btn.isEnabled()
                ),
                "import_label_button_tooltip": (
                    dataset_panel.sidebar.import_label_btn.toolTip()
                ),
            }
            scan = service.execute(
                ScanSourceCommand(source_path=str(source_path.parent))
            )
            preview = service.execute(
                PreviewInterpretationCommand(
                    choices={"selected_eeg_files": [str(SECOND_SOURCE_PATH)]},
                )
            )
            validation = service.execute(ValidateInterpretationCommand())
            dialog = DataInterpretationPreviewDialog(
                dataset_panel,
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
            capture_widget(dialog, ARTIFACT_PATHS.preview_screenshot)
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
                "file_pairing_rows": pairing_rows(dialog),
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
                        "file_pairing": pairing_rows_state_for_step(
                            dialog,
                            "Match Labels",
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
                "screenshot": ARTIFACT_PATHS.preview_screenshot.name,
            }
            dialog.close()

            remap_dialog = DataInterpretationPreviewDialog(
                dataset_panel,
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
            capture_widget(remap_dialog, ARTIFACT_PATHS.remap_screenshot)
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
                        "file_pairing": pairing_rows_state_for_step(
                            remap_dialog,
                            "Match Labels",
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
                "screenshot": ARTIFACT_PATHS.remap_screenshot.name,
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
            ensure_confirmed_apply_succeeded(apply_confirmed)
            dataset_panel.update_panel()
            open_workflow_panel(window, 0)
            set_capture_geometry(window)
            app.processEvents()
            window.repaint()
            app.processEvents()
            capture_widget(window, ARTIFACT_PATHS.applied_screenshot)

            replay = {
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(UTC).isoformat(),
                "generator": GENERATOR,
                "source_files": source_files_at_start,
                "source_fingerprint": source_fingerprint_at_start,
                "artifacts": artifact_file_manifest(
                    {
                        "preview": ARTIFACT_PATHS.preview_screenshot,
                        "remap": ARTIFACT_PATHS.remap_screenshot,
                        "applied": ARTIFACT_PATHS.applied_screenshot,
                    },
                    artifact_root=ARTIFACT_PATHS.directory,
                ),
                "workflow": "data_interpretation_ui_replay",
                "source": SOURCE_DIR.name,
                "transcript": [
                    "Selected folder source for interpretation.",
                    "Scanned source and previewed metadata plus label carrier "
                    "interpretation.",
                    "Selected one EEG file from the scanned folder scope.",
                    "Mapped generic events.tsv to the selected EEG file in the wizard.",
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
                            dataset_panel.sidebar,
                        ),
                        "import_button_text": (dataset_panel.sidebar.import_btn.text()),
                        "import_button_enabled": (
                            dataset_panel.sidebar.import_btn.isEnabled()
                        ),
                        "import_label_button_text": (
                            dataset_panel.sidebar.import_label_btn.text()
                        ),
                        "import_label_button_enabled": (
                            dataset_panel.sidebar.import_label_btn.isEnabled()
                        ),
                        "import_label_button_tooltip": (
                            dataset_panel.sidebar.import_label_btn.toolTip()
                        ),
                        "table_rows": dataset_panel.table.rowCount(),
                        "table": table_state(
                            dataset_panel.table,
                            panel=dataset_panel,
                            right_boundary=dataset_panel.sidebar,
                        ),
                        "visible_panel_text": visible_texts(dataset_panel),
                        "screenshot": ARTIFACT_PATHS.applied_screenshot.name,
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
            ensure_source_manifest_stable(source_files_at_start)
            ARTIFACT_PATHS.replay_json.write_text(
                json.dumps(replay, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            result["code"] = 0
        except Exception as exc:
            print(f"Replay capture failed: {exc}", file=sys.stderr)
            result["code"] = 1
        finally:
            request_window_close(
                window,
                on_closed=app.quit,
                on_timeout=lambda: _handle_capture_close_timeout(app, result),
            )

    QTimer.singleShot(1500, run_steps)
    app.exec()
    return result["code"]


def request_window_close(
    window: QWidget,
    *,
    on_closed: Callable[[], None],
    on_timeout: Callable[[], None],
    timeout_ms: int = WINDOW_CLOSE_TIMEOUT_MS,
) -> None:
    """Wait for the product's asynchronous close protocol before finishing."""
    started_at = time.monotonic()

    def poll() -> None:
        if not window.isVisible():
            on_closed()
            return
        elapsed_ms = (time.monotonic() - started_at) * 1000
        if elapsed_ms >= max(timeout_ms, 0):
            on_timeout()
            return
        QTimer.singleShot(25, poll)

    window.close()
    QTimer.singleShot(0, poll)


def _handle_capture_close_timeout(
    app: QApplication,
    result: dict[str, int],
) -> None:
    """Fail a replay that cannot complete the real MainWindow shutdown path."""
    print(
        "Replay capture failed: MainWindow did not finish shutdown within "
        f"{WINDOW_CLOSE_TIMEOUT_MS} ms.",
        file=sys.stderr,
    )
    result["code"] = 1
    app.exit(1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture Data Interpretation replay screenshots and JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR,
        help=(
            "Directory for replay artifacts. Defaults to a tmp directory so "
            "validation does not dirty tracked artifacts."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    set_artifact_dir(output_dir)
    app = QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    return capture_replay(app)


if __name__ == "__main__":
    raise SystemExit(main())
