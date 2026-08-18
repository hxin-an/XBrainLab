"""Capture the Dataset panel beside a 320 px Assistant dock."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QPoint, QRect, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.pipeline_stage import (
    PipelineStage,
    pipeline_stage_status_label,
)
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ApplicationStateSnapshot,
    PreprocessedStateSnapshot,
    RawStateSnapshot,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.ui.chat.panel import ChatPanel
from XBrainLab.ui.panels.dataset.panel import DatasetPanel
from XBrainLab.ui.styles.stylesheets import Stylesheets

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "build" / "dev-artifacts" / "dataset-narrow"
SHELL_HEIGHTS = (520, 800)
ASSISTANT_DOCK_WIDTH = 320
FIXED_SUMMARY_SIDEBAR_WIDTH = 260
MINIMUM_FIXED_SIDEBAR_SHELL_WIDTH = 840
SHELL_WIDTHS = (MINIMUM_FIXED_SIDEBAR_SHELL_WIDTH, 960, 1280)
LOGICAL_SCALES = (1.0, 1.25, 1.5)
SOURCE_PATHS = (
    "XBrainLab/ui/components/info_panel.py",
    "XBrainLab/ui/panels/dataset/panel.py",
    "XBrainLab/ui/panels/dataset/sidebar.py",
    "scripts/dev/capture_dataset_narrow_walkthrough.py",
)


def _fixture_publication(
    *, has_data: bool, revision: int
) -> ApplicationViewPublication:
    state = ApplicationStateSnapshot.empty()
    if has_data:
        state = replace(
            state,
            pipeline_stage=PipelineStage.DATA_LOADED.value,
            raw=RawStateSnapshot(
                loaded=True,
                count=1,
                files=["sub-01_task-mi_run-01_eeg.fif"],
                formats=["fif"],
            ),
            preprocessed=PreprocessedStateSnapshot(
                available=True,
                count=1,
                files=["sub-01_task-mi_run-01_eeg.fif"],
                is_epoched=False,
                operations=[],
            ),
            active_dataset=ActiveDatasetSnapshot(
                has_raw_data=True,
                has_preprocessed_data=False,
            ),
        )
    return ApplicationViewPublication(
        generation=revision,
        revision=revision,
        state=state,
        capabilities=build_capability_policy(state),
    )


class _DatasetControllerFixture:
    """Controller and publication fixture with one consistent capture state."""

    def __init__(self) -> None:
        self.study = SimpleNamespace()
        self._subscribers: dict[str, list[Callable[..., Any]]] = defaultdict(list)
        self._loaded_data: list[Any] = []
        self._publication = _fixture_publication(has_data=False, revision=1)

    def subscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        subscribers = self._subscribers.get(event_name, [])
        if callback in subscribers:
            subscribers.remove(callback)

    @staticmethod
    def is_locked() -> bool:
        return False

    def has_data(self) -> bool:
        return bool(self._loaded_data)

    def get_loaded_data_list(self) -> list[Any]:
        return list(self._loaded_data)

    def get_view_publication(self) -> ApplicationViewPublication:
        return self._publication

    def set_loaded_data(self, data: Any) -> ApplicationViewPublication:
        self._loaded_data = [data]
        self._publication = _fixture_publication(has_data=True, revision=2)
        return self._publication


class _LoadedEpochFixture:
    """Stable loaded summary values that exercise the longest visible labels."""

    @staticmethod
    def get_filepath() -> str:
        return "/fixture/sub-01_task-mi_run-01_eeg.fif"

    @staticmethod
    def get_filename() -> str:
        return "sub-01_task-mi_run-01_eeg.fif"

    @staticmethod
    def get_subject_name() -> str:
        return "S01"

    @staticmethod
    def get_session_name() -> str:
        return "session-01"

    @staticmethod
    def get_nchan() -> int:
        return 64

    @staticmethod
    def get_sfreq() -> int:
        return 250

    @staticmethod
    def get_epochs_length() -> int:
        return 120

    @staticmethod
    def is_raw() -> bool:
        return False

    @staticmethod
    def get_tmin() -> float:
        return -0.2

    @staticmethod
    def get_epoch_duration() -> int:
        return 250

    @staticmethod
    def get_filter_range() -> tuple[float, float]:
        return (0.5, 40.0)

    @staticmethod
    def get_event_summary(*, allow_scan: bool = False) -> dict[str, Any]:
        del allow_scan
        return {
            "available": True,
            "count": 120,
            "labels": ["left", "right"],
        }


def _detached_summary_row(data: _LoadedEpochFixture) -> dict[str, Any]:
    """Build the detached publication row consumed by AggregateInfoPanel."""
    highpass, lowpass = data.get_filter_range()
    return {
        "subject": data.get_subject_name(),
        "session": data.get_session_name(),
        "epochs_length": data.get_epochs_length(),
        "is_raw": data.is_raw(),
        "event": data.get_event_summary(),
        "n_channels": data.get_nchan(),
        "sampling_frequency": data.get_sfreq(),
        "epoch_duration_samples": data.get_epoch_duration(),
        "tmin": data.get_tmin(),
        "highpass": highpass,
        "lowpass": lowpass,
    }


def _settle(app: QApplication, turns: int = 12) -> None:
    for _ in range(turns):
        app.processEvents()


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(  # noqa: S603
            ("git", *args),
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rect(rect: QRect) -> dict[str, int]:
    return {
        "x": int(rect.x()),
        "y": int(rect.y()),
        "width": int(rect.width()),
        "height": int(rect.height()),
    }


def _mapped_rect(widget: QWidget, ancestor: QWidget) -> QRect:
    top_left = widget.mapTo(ancestor, QPoint(0, 0))
    return QRect(top_left, widget.size())


def _fits_ancestor(widget: QWidget, ancestor: QWidget) -> bool:
    return ancestor.contentsRect().contains(_mapped_rect(widget, ancestor))


def _fits_scroll_viewport(widget: QWidget, scroll_area: Any) -> bool:
    viewport = scroll_area.viewport()
    return viewport.contentsRect().contains(_mapped_rect(widget, viewport))


def _fits_scroll_content(widget: QWidget, scroll_area: Any) -> bool:
    content = scroll_area.widget()
    if not isinstance(content, QWidget):
        return False
    return content.contentsRect().contains(_mapped_rect(widget, content))


def _scroll_maximum(scroll_area: Any, orientation: Qt.Orientation) -> int:
    scrollbar = (
        scroll_area.horizontalScrollBar()
        if orientation is Qt.Orientation.Horizontal
        else scroll_area.verticalScrollBar()
    )
    if scrollbar is None:
        raise RuntimeError("Expected the Qt scroll area to own a scrollbar.")
    return int(scrollbar.maximum())


def _button_evidence(
    button: QPushButton,
    panel: DatasetPanel,
    *,
    scroll_area: Any | None = None,
    horizontal_padding: int = 30,
) -> dict[str, Any]:
    text_width = button.fontMetrics().horizontalAdvance(button.text())
    evidence = {
        "text": button.text(),
        "visible": bool(button.isVisibleTo(panel)),
        "enabled": bool(button.isEnabled()),
        "geometry_in_panel": _rect(_mapped_rect(button, panel)),
        "inside_panel": _fits_ancestor(button, panel),
        "text_width": int(text_width),
        "available_width": int(button.contentsRect().width()),
        "text_fits": text_width + horizontal_padding <= button.contentsRect().width(),
    }
    if scroll_area is not None:
        evidence["inside_scroll_viewport"] = _fits_scroll_viewport(
            button,
            scroll_area,
        )
        evidence["inside_scroll_content"] = _fits_scroll_content(
            button,
            scroll_area,
        )
    return evidence


def _info_evidence(
    info_panel: Any,
    panel: DatasetPanel,
    *,
    scroll_area: Any,
) -> dict[str, Any]:
    table = info_panel.table
    viewport = table.viewport()
    cells: list[dict[str, Any]] = []
    clipped: list[str] = []
    for row in range(table.rowCount()):
        if table.isRowHidden(row):
            continue
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is None:
                continue
            text = " ".join(item.text().split())
            cell_rect = table.visualItemRect(item)
            available_width = max(1, cell_rect.width() - 8)
            text_rect = table.fontMetrics().boundingRect(
                QRect(0, 0, available_width, 10_000),
                int(Qt.AlignmentFlag.AlignLeft)
                | int(Qt.AlignmentFlag.AlignTop)
                | int(Qt.TextFlag.TextWordWrap),
                text,
            )
            fits = bool(
                text_rect.width() <= available_width
                and text_rect.height() + 2 <= cell_rect.height()
                and cell_rect.left() >= 0
                and cell_rect.right() <= viewport.width()
            )
            if text and not fits:
                clipped.append(text)
            cells.append(
                {
                    "row": row,
                    "column": column,
                    "text": text,
                    "cell_width": int(cell_rect.width()),
                    "cell_height": int(cell_rect.height()),
                    "required_width": int(text_rect.width() + 8),
                    "required_height": int(text_rect.height() + 2),
                    "fits": fits,
                }
            )
    inside_panel = _fits_ancestor(info_panel, panel)
    inside_scroll_content = _fits_scroll_content(info_panel, scroll_area)
    return {
        "visible": bool(info_panel.isVisibleTo(panel)),
        "inside_panel": inside_panel,
        "inside_scroll_content": inside_scroll_content,
        "geometry_in_panel": _rect(_mapped_rect(info_panel, panel)),
        "viewport": _rect(viewport.rect()),
        "column_widths": [
            int(table.columnWidth(column)) for column in range(table.columnCount())
        ],
        "horizontal_scroll_maximum": int(table.horizontalScrollBar().maximum()),
        "clipped_text": clipped,
        "cells": cells,
        "vertical_scroll_maximum": _scroll_maximum(
            scroll_area,
            Qt.Orientation.Vertical,
        ),
        "passed": bool(cells)
        and not clipped
        and (inside_panel or inside_scroll_content),
    }


def _dataset_table_evidence(panel: DatasetPanel) -> dict[str, Any]:
    table = panel.table
    viewport = table.viewport()
    header = table.horizontalHeader()
    if viewport is None or header is None:
        raise RuntimeError("Dataset table did not create its viewport and header.")
    visible_columns = [
        column
        for column in range(table.columnCount())
        if not table.isColumnHidden(column)
    ]
    cells: list[dict[str, Any]] = []
    for row in range(table.rowCount()):
        for column in visible_columns:
            item = table.item(row, column)
            if item is None:
                continue
            cell_rect = table.visualItemRect(item)
            text_width = table.fontMetrics().horizontalAdvance(item.text())
            inside_viewport = bool(
                cell_rect.left() >= 0
                and cell_rect.right() <= viewport.width()
                and cell_rect.top() >= 0
                and cell_rect.bottom() <= viewport.height()
            )
            cells.append(
                {
                    "row": row,
                    "column": column,
                    "text": item.text(),
                    "cell_rect": _rect(cell_rect),
                    "text_width": int(text_width),
                    "text_fits": text_width + 12 <= cell_rect.width(),
                    "intentional_elide": bool(
                        text_width + 12 > cell_rect.width()
                        and table.textElideMode() is Qt.TextElideMode.ElideRight
                    ),
                    "inside_viewport": inside_viewport,
                }
            )
    horizontal_scroll_maximum = _scroll_maximum(
        table,
        Qt.Orientation.Horizontal,
    )
    return {
        "visible": bool(table.isVisibleTo(panel)),
        "inside_panel": _fits_ancestor(table, panel),
        "row_count": int(table.rowCount()),
        "visible_columns": visible_columns,
        "header_length": int(header.length()),
        "viewport_width": int(viewport.width()),
        "horizontal_scroll_maximum": horizontal_scroll_maximum,
        "cells": cells,
        "passed": bool(
            table.isVisibleTo(panel)
            and table.rowCount() > 0
            and 0 in visible_columns
            and cells
            and all(
                cell["inside_viewport"]
                and (cell["text_fits"] or cell["intentional_elide"])
                for cell in cells
            )
            and horizontal_scroll_maximum == 0
            and abs(header.length() - viewport.width()) <= 2
        ),
    }


def _build_shell(
    app: QApplication,
    *,
    shell_width: int,
    shell_height: int,
    logical_scale: float,
) -> tuple[QMainWindow, DatasetPanel, QDockWidget, ChatPanel]:
    window = QMainWindow()
    window.setWindowTitle("XBrainLab")
    scaled_point_size = 10 * logical_scale
    window.setStyleSheet(
        Stylesheets.MAIN_WINDOW.replace(
            "font-size: 10pt;",
            f"font-size: {scaled_point_size:g}pt;",
        )
    )
    window.study = SimpleNamespace()  # type: ignore[attr-defined]

    central_widget = QWidget(window)
    central_layout = QVBoxLayout(central_widget)
    central_layout.setContentsMargins(0, 0, 0, 0)
    central_layout.setSpacing(0)

    top_bar = QFrame(central_widget)
    top_bar.setObjectName("TopBar")
    top_bar.setFixedHeight(50)
    top_layout = QHBoxLayout(top_bar)
    top_layout.setContentsMargins(10, 0, 10, 0)
    navigation = QComboBox(top_bar)
    navigation.setObjectName("CompactNavigation")
    navigation.addItems(
        ["Dataset", "Preprocess", "Training", "Evaluation", "Visualization"]
    )
    navigation.setCurrentText("Dataset")
    navigation.setMinimumWidth(150)
    navigation.setMaximumWidth(220)
    navigation.setStyleSheet(Stylesheets.COMBO_BOX)
    top_layout.addWidget(navigation)
    top_layout.addStretch()
    assistant_button = QPushButton("AI Assistant", top_bar)
    assistant_button.setObjectName("ActionBtn")
    assistant_button.setCheckable(True)
    assistant_button.setChecked(True)
    top_layout.addWidget(assistant_button)
    central_layout.addWidget(top_bar)

    controller = _DatasetControllerFixture()
    panel = DatasetPanel(
        controller=controller,
        parent=window,
        publication_port=controller,
    )
    central_layout.addWidget(panel)
    window.setCentralWidget(central_widget)
    status_bar = window.statusBar()
    if status_bar is None:
        raise RuntimeError("Dataset capture shell did not create a status bar.")
    status_bar.showMessage(
        pipeline_stage_status_label(
            controller.get_view_publication().state.pipeline_stage,
        )
    )

    chat_panel = ChatPanel()
    chat_panel.set_runtime_state("ready")
    assistant_dock = QDockWidget("XBrainLab Assistant", window)
    assistant_dock.setObjectName("DatasetNarrowAssistantDock")
    assistant_dock.setWidget(chat_panel)
    assistant_dock.setFixedWidth(ASSISTANT_DOCK_WIDTH)
    window.addDockWidget(
        Qt.DockWidgetArea.RightDockWidgetArea,
        assistant_dock,
    )
    window.setFixedSize(shell_width, shell_height)
    window.show()
    assistant_dock.show()
    window.resizeDocks(
        [assistant_dock],
        [ASSISTANT_DOCK_WIDTH],
        Qt.Orientation.Horizontal,
    )
    _settle(app)
    return window, panel, assistant_dock, chat_panel


def _apply_loaded_state(panel: DatasetPanel) -> None:
    data = _LoadedEpochFixture()
    controller = panel.controller
    if not isinstance(controller, _DatasetControllerFixture):
        raise RuntimeError("Dataset capture lost its application fixture.")
    publication = controller.set_loaded_data(data)
    panel.sidebar.info_panel.update_info(
        preprocessed_data_list=[_detached_summary_row(data)]
    )
    panel.table.blockSignals(True)
    panel.table.setRowCount(1)
    for column, text in enumerate(
        (
            data.get_filename(),
            data.get_subject_name(),
            data.get_session_name(),
            str(data.get_nchan()),
            str(data.get_sfreq()),
            str(data.get_epochs_length()),
            "120",
        )
    ):
        panel.table.setItem(0, column, QTableWidgetItem(text))
    panel.table.blockSignals(False)
    panel.data_surface.setCurrentWidget(panel.table)
    window = panel.window()
    if not isinstance(window, QMainWindow):
        raise RuntimeError("Dataset capture shell lost its status bar.")
    status_bar = window.statusBar()
    if status_bar is None:
        raise RuntimeError("Dataset capture shell lost its status bar.")
    status_bar.showMessage(
        pipeline_stage_status_label(publication.state.pipeline_stage)
    )


def _state_truth_evidence(
    window: QMainWindow,
    panel: DatasetPanel,
    *,
    state: str,
) -> dict[str, Any]:
    controller = panel.controller
    publication = panel._read_application_publication()
    status_bar = window.statusBar()
    status_text = status_bar.currentMessage() if status_bar is not None else ""
    fixture_has_data = bool(
        isinstance(controller, _DatasetControllerFixture) and controller.has_data()
    )
    publication_has_data = bool(
        publication is not None
        and publication.usable
        and (
            publication.state.active_dataset.has_raw_data
            or publication.state.active_dataset.has_preprocessed_data
            or publication.state.active_dataset.has_epoch_data
            or publication.state.active_dataset.has_datasets
        )
    )
    expected_has_data = state == "loaded-summary"
    expected_surface = panel.table if expected_has_data else panel.empty_state
    expected_status = (
        pipeline_stage_status_label(publication.state.pipeline_stage)
        if publication is not None
        else ""
    )
    contradictory_empty_copy = bool(
        panel.data_surface.currentWidget() is panel.empty_state
        and panel.empty_state_title.text() == "No EEG data loaded"
        and status_text.strip().casefold() in {"dataset is ready.", "dataset ready"}
    )
    checks = {
        "publication_available": publication is not None and publication.usable,
        "fixture_matches_scenario": fixture_has_data == expected_has_data,
        "publication_matches_scenario": publication_has_data == expected_has_data,
        "surface_matches_scenario": panel.data_surface.currentWidget()
        is expected_surface,
        "status_matches_publication": bool(expected_status)
        and status_text == expected_status,
        "no_empty_ready_contradiction": not contradictory_empty_copy,
    }
    return {
        "fixture_has_data": fixture_has_data,
        "publication_has_data": publication_has_data,
        "publication_pipeline_stage": (
            publication.state.pipeline_stage if publication is not None else None
        ),
        "visible_surface": (
            "empty"
            if panel.data_surface.currentWidget() is panel.empty_state
            else "table"
        ),
        "empty_state_title": panel.empty_state_title.text(),
        "status_text": status_text,
        "expected_status_text": expected_status,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _active_info_panel(panel: DatasetPanel) -> Any:
    if panel.sidebar.info_panel.isVisibleTo(panel):
        return panel.sidebar.info_panel
    raise RuntimeError("Loaded Dataset summary is not visible in the sidebar.")


def _scenario_evidence(
    window: QMainWindow,
    panel: DatasetPanel,
    assistant_dock: QDockWidget,
    chat_panel: ChatPanel,
    *,
    state: str,
    shell_width: int,
    shell_height: int,
    logical_scale: float,
    active_info_panel: Any | None,
) -> dict[str, Any]:
    sidebar = panel.sidebar
    action_buttons = [
        _button_evidence(
            button,
            panel,
            scroll_area=sidebar.scroll_area,
        )
        for button in (
            sidebar.import_btn,
            sidebar.reload_recipe_btn,
            sidebar.chan_select_btn,
        )
    ]
    info = (
        _info_evidence(
            active_info_panel,
            panel,
            scroll_area=sidebar.scroll_area,
        )
        if active_info_panel is not None
        else None
    )
    state_truth = _state_truth_evidence(window, panel, state=state)
    empty_title_rect = panel.empty_state_title.fontMetrics().boundingRect(
        QRect(
            0,
            0,
            max(1, panel.empty_state_title.contentsRect().width()),
            10_000,
        ),
        int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap),
        panel.empty_state_title.text(),
    )
    horizontal_scroll = {
        "dataset_table": _scroll_maximum(
            panel.table,
            Qt.Orientation.Horizontal,
        ),
        "dataset_sidebar": _scroll_maximum(
            sidebar.scroll_area,
            Qt.Orientation.Horizontal,
        ),
        "sidebar_summary": _scroll_maximum(
            sidebar.info_panel.table,
            Qt.Orientation.Horizontal,
        ),
        "assistant": _scroll_maximum(
            chat_panel.scroll_area,
            Qt.Orientation.Horizontal,
        ),
    }
    visible_horizontal_scroll = {
        "dataset_sidebar": horizontal_scroll["dataset_sidebar"],
        "assistant": horizontal_scroll["assistant"],
    }
    if panel.table.isVisibleTo(panel):
        visible_horizontal_scroll["dataset_table"] = horizontal_scroll["dataset_table"]
    if sidebar.info_panel.table.isVisibleTo(panel):
        visible_horizontal_scroll["sidebar_summary"] = horizontal_scroll[
            "sidebar_summary"
        ]
    non_overlapping = (
        panel.content_column.geometry().right() < sidebar.geometry().left()
    )
    checks = {
        "shell_size_exact": window.size().width() == shell_width
        and window.size().height() == shell_height,
        "assistant_visible_at_320": assistant_dock.isVisible()
        and assistant_dock.width() == ASSISTANT_DOCK_WIDTH,
        "sidebar_fixed_at_260": sidebar.width() == FIXED_SUMMARY_SIDEBAR_WIDTH,
        "content_inside_panel": _fits_ancestor(panel.content_column, panel),
        "sidebar_inside_panel": _fits_ancestor(sidebar, panel),
        "primary_surfaces_do_not_overlap": non_overlapping,
        "empty_title_fits": state != "empty"
        or empty_title_rect.height()
        <= panel.empty_state_title.contentsRect().height() + 1,
        "all_actions_visible": all(
            item["visible"] and item["inside_scroll_content"] and item["text_fits"]
            for item in action_buttons
        ),
        "loaded_summary_readable": info is None or bool(info["passed"]),
        "summary_stays_in_sidebar": state != "loaded-summary"
        or active_info_panel is sidebar.info_panel,
        "loaded_table_readable": state != "loaded-summary",
        "state_truth_consistent": bool(state_truth["passed"]),
        "no_horizontal_scroll": all(
            maximum == 0 for maximum in visible_horizontal_scroll.values()
        ),
    }
    return {
        "state": state,
        "shell_logical_size": [shell_width, shell_height],
        "logical_text_scale": logical_scale,
        "font_point_size": round(panel.font().pointSizeF(), 2),
        "device_pixel_ratio": float(window.devicePixelRatioF()),
        "dock_width": int(assistant_dock.width()),
        "dataset_panel_size": [int(panel.width()), int(panel.height())],
        "layout_mode": "side-by-side",
        "summary_host": "none" if info is None else "sidebar",
        "content_geometry": _rect(panel.content_column.geometry()),
        "sidebar_geometry": _rect(sidebar.geometry()),
        "sidebar_vertical_scroll_maximum": _scroll_maximum(
            sidebar.scroll_area,
            Qt.Orientation.Vertical,
        ),
        "horizontal_scroll_maximum": horizontal_scroll,
        "visible_horizontal_scroll_maximum": visible_horizontal_scroll,
        "actions": action_buttons,
        "summary": info,
        "state_truth": state_truth,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _capture_scenario(
    app: QApplication,
    output_dir: Path,
    base_font: QFont,
    *,
    state: str,
    shell_width: int,
    shell_height: int,
    logical_scale: float,
) -> dict[str, Any]:
    scaled_font = QFont(base_font)
    scaled_font.setPointSizeF(base_font.pointSizeF() * logical_scale)
    app.setFont(scaled_font)
    window: QMainWindow | None = None
    try:
        window, panel, assistant_dock, chat_panel = _build_shell(
            app,
            shell_width=shell_width,
            shell_height=shell_height,
            logical_scale=logical_scale,
        )
        if state == "loaded-summary":
            _apply_loaded_state(panel)
        _settle(app)
        active_info_panel = (
            _active_info_panel(panel) if state == "loaded-summary" else None
        )
        evidence = _scenario_evidence(
            window,
            panel,
            assistant_dock,
            chat_panel,
            state=state,
            shell_width=shell_width,
            shell_height=shell_height,
            logical_scale=logical_scale,
            active_info_panel=active_info_panel,
        )
        scale_label = round(logical_scale * 100)
        filename = f"dataset-{state}-w{shell_width}-h{shell_height}-s{scale_label}.png"
        output_path = output_dir / filename
        pixmap = window.grab()
        if not pixmap.save(str(output_path), "PNG"):
            raise RuntimeError(f"Could not save {output_path}")
        evidence.update(
            {
                "screenshot": filename,
                "rendered_pixel_size": [pixmap.width(), pixmap.height()],
                "sha256": _sha256(output_path),
            }
        )
        if state == "loaded-summary":
            _settle(app)
            table_evidence = _dataset_table_evidence(panel)
            evidence["table"] = table_evidence
            evidence["checks"]["loaded_table_readable"] = bool(table_evidence["passed"])
            evidence["passed"] = all(evidence["checks"].values())
            table_filename = (
                f"dataset-loaded-table-w{shell_width}-h{shell_height}-"
                f"s{scale_label}.png"
            )
            table_output_path = output_dir / table_filename
            table_pixmap = window.grab()
            if not table_pixmap.save(str(table_output_path), "PNG"):
                raise RuntimeError(f"Could not save {table_output_path}")
            evidence["table_screenshot"] = table_filename
            evidence["table_screenshot_sha256"] = _sha256(table_output_path)
        return evidence
    finally:
        if window is not None:
            panel = window.findChild(DatasetPanel)
            if panel is not None:
                panel.cleanup()
            window.close()
            window.deleteLater()
        app.setFont(base_font)
        _settle(app, turns=4)


def _render_readme(payload: dict[str, Any]) -> str:
    rows = []
    for scenario in payload["scenarios"]:
        shell = scenario["shell_logical_size"]
        table_file = scenario.get("table_screenshot")
        table_link = f"[table]({table_file})" if table_file else "-"
        rows.append(
            "| {state} | {width}x{height} | {scale:.0%} | {panel} | {layout} | "
            "{summary} | [{file}]({file}) | {table} | {status} |".format(
                state=scenario["state"],
                width=shell[0],
                height=shell[1],
                scale=scenario["logical_text_scale"],
                panel="x".join(str(value) for value in scenario["dataset_panel_size"]),
                layout=scenario["layout_mode"],
                summary=scenario["summary_host"],
                file=scenario["screenshot"],
                table=table_link,
                status="PASS" if scenario["passed"] else "FAIL",
            )
        )
    return "\n".join(
        [
            "# Dataset Narrow Presentation Evidence",
            "",
            f"- status: `{'passed' if payload['passed'] else 'failed'}`",
            f"- generated: `{payload['generated_at']}`",
            f"- Git revision: `{payload['git']['revision']}`",
            f"- branch: `{payload['git']['branch']}`",
            f"- Qt platform: `{payload['qt']['platform']}`",
            "- Assistant dock: real `QDockWidget` with real `ChatPanel`, fixed at "
            "`320` logical px",
            "- logical scaling: application font multiplier; this is not native "
            "Windows DPI evidence",
            "- workflow scope: synthetic controller and in-memory presentation "
            "state; this capture does not execute the real import command path",
            "",
            "## Matrix",
            "",
            "| State | Shell | Scale | Dataset panel | Layout | Summary | Screenshot | EEG table | Result |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            *rows,
            "",
            "## Root Cause",
            "",
            "A 760 px synthetic shell with a forced 320 px Assistant leaves only "
            "434-435 px for Dataset. That fixture came from the superseded variable-"
            "width sidebar design and cannot contain the accepted fixed 260 px "
            "sidebar plus readable Dataset content at every text scale.",
            "",
            "The current matrix starts at the supported 840 px synthetic shell, keeps "
            "Data Summary at the top of the right sidebar, and requires that sidebar "
            "to remain exactly 260 px. Short windows use one sidebar-owned vertical "
            "scroll area. No duplicate summary or responsive summary tab remains.",
            "",
            "## Claim Boundary",
            "",
            payload["claim_boundary"],
            "",
            "Machine-readable geometry, source hashes, viewport metadata, and "
            "per-widget checks are in "
            "[dataset-narrow-evidence.json](dataset-narrow-evidence.json).",
            "",
        ]
    )


def capture(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_path in output_dir.glob("dataset-*.png"):
        old_path.unlink()

    existing_app = QApplication.instance()
    app = existing_app if isinstance(existing_app, QApplication) else QApplication([])
    app.setStyle("Fusion")
    base_font = QFont(app.font())
    scenarios = [
        _capture_scenario(
            app,
            output_dir,
            base_font,
            state=state,
            shell_width=width,
            shell_height=height,
            logical_scale=scale,
        )
        for scale in LOGICAL_SCALES
        for width in SHELL_WIDTHS
        for height in SHELL_HEIGHTS
        for state in ("empty", "loaded-summary")
    ]
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": all(scenario["passed"] for scenario in scenarios),
        "scenario_count": len(scenarios),
        "git": {
            "revision": _git_value("rev-parse", "HEAD"),
            "branch": _git_value("branch", "--show-current"),
            "working_tree_dirty": bool(_git_value("status", "--porcelain")),
        },
        "qt": {
            "platform": app.platformName(),
            "qt_version": QT_VERSION_STR,
            "pyqt_version": PYQT_VERSION_STR,
            "native_display_scaling_observed": False,
            "logical_scaling_method": "QApplication font point-size multiplier",
        },
        "source": {
            relative: {
                "sha256": _sha256(REPO_ROOT / relative),
                "path": relative,
            }
            for relative in SOURCE_PATHS
        },
        "viewports": {
            "shell_widths": list(SHELL_WIDTHS),
            "shell_heights": list(SHELL_HEIGHTS),
            "assistant_dock_width": ASSISTANT_DOCK_WIDTH,
            "fixed_summary_sidebar_width": FIXED_SUMMARY_SIDEBAR_WIDTH,
            "logical_text_scales": list(LOGICAL_SCALES),
        },
        "claim_boundary": (
            "Linux Qt offscreen geometry and raster evidence using a synthetic "
            "controller, in-memory loaded-state fixture, and logical font scaling. "
            "It proves presentation behavior only: it does not execute real import, "
            "and it does not prove Windows native DPI, per-monitor DPI transitions, "
            "compositor behavior, or physical-pixel rendering."
        ),
        "scenarios": scenarios,
    }
    report_path = output_dir / "dataset-narrow-evidence.json"
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        _render_readme(payload),
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    args = parser.parse_args()
    payload = capture(args.output_dir.resolve())
    print(
        json.dumps(
            {
                "passed": payload["passed"],
                "scenario_count": payload["scenario_count"],
                "output_dir": str(args.output_dir.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
