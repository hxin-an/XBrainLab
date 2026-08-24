"""Path-based dialog for reviewing and mapping external label files."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.application.commands import PreviewLabelImportCommand
from XBrainLab.backend.application.resource_preflight import (
    ResourcePreflightContractError,
    ResourcePreflightView,
)
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    execute_application_command_async,
    is_stale_publication_result,
)
from XBrainLab.ui.components.modal_presentation import (
    AlertSeverity,
    ask_confirmation,
    show_error,
    show_warning,
)
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import normalize_dialog_button_box
from XBrainLab.ui.interaction_outcome import InteractionOutcome


@dataclass(frozen=True, slots=True)
class LabelImportSelection:
    """Path/config/identity result accepted by the label import action."""

    preview_id: str
    label_paths: tuple[str, ...]
    label_configs: dict[str, dict[str, Any]]
    mode: str
    target_count: int | None


def _normalize_label_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value


def _label_sort_key(value: Any) -> tuple[int, Any]:
    value = _normalize_label_value(value)
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return (0, int(value))
    return (1, str(value))


def _parse_display_code(text: str) -> Any:
    try:
        return int(text)
    except ValueError:
        return text


class ImportLabelDialog(BaseDialog):
    """Review external labels through ApplicationService without owning payloads."""

    def __init__(
        self,
        parent=None,
        target_files: list[Any] | None = None,
        *,
        expected_publication_generation: int | None = None,
    ):
        self.label_paths: list[str] = []
        self.label_configs: dict[str, dict[str, Any]] = {}
        self.preview_summary: dict[str, Any] = {}
        self.unique_labels: list[Any] = []
        self.target_files = list(target_files or [])
        self._expected_publication_generation = expected_publication_generation
        self._preview_pending = False

        self.file_list: QListWidget | None = None
        self.map_table: QTableWidget | None = None
        self.info_label: QLabel | None = None
        self.target_summary_label: QLabel | None = None
        self.recipe_note_label: QLabel | None = None
        self.browse_button: QPushButton | None = None
        self.remove_button: QPushButton | None = None
        self.button_box: QDialogButtonBox | None = None

        super().__init__(parent, title="Add Labels to Loaded Data")
        self.resize(580, 460)

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)

        target_summary_label = QLabel(self._target_summary_text())
        self.target_summary_label = target_summary_label
        target_summary_label.setWordWrap(True)
        target_summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        layout.addWidget(target_summary_label)

        recipe_note_label = QLabel(
            "A successful import updates the current import recipe trace when a "
            "data interpretation is active."
        )
        self.recipe_note_label = recipe_note_label
        recipe_note_label.setWordWrap(True)
        layout.addWidget(recipe_note_label)

        file_group = QGroupBox("Select Label File")
        file_layout = QHBoxLayout()
        file_list = QListWidget()
        self.file_list = file_list
        file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        file_list.itemSelectionChanged.connect(self.on_file_selection_changed)

        button_layout = QVBoxLayout()
        browse_button = QPushButton("Add Files...")
        self.browse_button = browse_button
        browse_button.clicked.connect(self.browse_files)
        remove_button = QPushButton("Remove Selected")
        self.remove_button = remove_button
        remove_button.clicked.connect(self.remove_files)
        button_layout.addWidget(browse_button)
        button_layout.addWidget(remove_button)
        button_layout.addStretch()
        file_layout.addWidget(file_list, stretch=1)
        file_layout.addLayout(button_layout)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        map_group = QGroupBox("Map Codes to Event Names")
        map_layout = QVBoxLayout()
        map_table = QTableWidget()
        self.map_table = map_table
        map_table.setColumnCount(2)
        map_table.setHorizontalHeaderLabels(["Code", "Event Name"])
        header = map_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        map_layout.addWidget(map_table)
        map_group.setLayout(map_layout)
        layout.addWidget(map_group)

        info_label = QLabel("No labels selected.")
        self.info_label = info_label
        layout.addWidget(info_label)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        self.button_box = button_box
        normalize_dialog_button_box(button_box)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self._set_preview_busy(False)

    def _target_summary_text(self) -> str:
        if not self.target_files:
            return "Apply labels to the loaded EEG files selected in the dataset table."
        names = [self._target_file_name(item) for item in self.target_files]
        visible = ", ".join(names[:3])
        if len(names) > 3:
            visible += f", and {len(names) - 3} more"
        plural = "file" if len(names) == 1 else "files"
        return f"Apply labels to {len(names)} loaded EEG {plural}: {visible}."

    @staticmethod
    def _target_file_name(item: Any) -> str:
        for method_name in ("get_filename", "get_filepath"):
            method = getattr(item, method_name, None)
            if not callable(method):
                continue
            try:
                value = str(method())
            except Exception as exc:
                logger.debug(
                    "Could not read target filename via %s: %s", method_name, exc
                )
                continue
            if value:
                return os.path.basename(value)
        return str(item)

    def browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open Label Files",
            "",
            "Label Files (*.txt *.mat *.csv *.tsv *.npy)",
        )
        if not paths:
            return
        changed = False
        for path in paths:
            changed = self._add_label_path(path) or changed
        if changed:
            self._request_preview()

    def remove_files(self) -> None:
        if self.file_list is None:
            return
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            path = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
            self.label_paths = [
                existing for existing in self.label_paths if existing != path
            ]
            self.label_configs.pop(path, None)
            self.file_list.takeItem(self.file_list.row(item))
        if self.label_paths:
            self._request_preview()
        else:
            self._clear_preview("No labels selected.")

    def on_file_selection_changed(self) -> None:
        """File selection does not alter the current backend preview."""

    def load_file(self, path: str) -> None:
        """Register a path and asynchronously request its backend preview."""
        if self._add_label_path(path):
            self._request_preview()

    def _add_label_path(self, path: str) -> bool:
        normalized = os.path.abspath(os.path.expanduser(str(path)))
        if normalized in self.label_paths:
            return False
        self.label_paths.append(normalized)
        if self.file_list is not None:
            item = QListWidgetItem(os.path.basename(normalized))
            item.setData(Qt.ItemDataRole.UserRole, normalized)
            item.setToolTip(normalized)
            self.file_list.addItem(item)
        return True

    def _request_preview(
        self,
        *,
        confirmed: bool = False,
        token: str | None = None,
    ) -> None:
        paths = tuple(self.label_paths)
        if not paths:
            self._clear_preview("No labels selected.")
            return
        self.preview_summary = {}
        self._set_preview_busy(True)
        if self.info_label is not None:
            self.info_label.setText("Reviewing label files...")
        command = PreviewLabelImportCommand(
            label_paths=list(paths),
            label_configs={
                key: dict(value) for key, value in self.label_configs.items()
            },
            resource_preflight_confirmed=confirmed,
            resource_preflight_token=token,
        )

        def _handle_result(result: Any) -> InteractionOutcome | None:
            if tuple(self.label_paths) != paths:
                return InteractionOutcome.cancelled("The selected labels changed.")
            self._set_preview_busy(False)
            if getattr(result, "failed", False):
                return self._handle_preview_failure(result)
            raw_summary = getattr(result, "diagnostics", {}).get("label_preview")
            if not isinstance(raw_summary, Mapping):
                self._clear_preview("The backend returned an invalid label preview.")
                show_error(
                    self,
                    "Label Preview Failed",
                    "The backend returned an invalid label preview.",
                )
                return InteractionOutcome.failed("Invalid label preview response.")
            self._apply_preview_summary(dict(raw_summary))
            return InteractionOutcome.completed("Label preview is ready.")

        def _handle_error(error: tuple[Any, ...]) -> None:
            self._set_preview_busy(False)
            self._clear_preview("Label preview failed.")
            present_unexpected_error(
                self,
                UnexpectedErrorContext.LABEL_IMPORT_PREVIEW,
                error_info=error,
            )

        execute_kwargs: dict[str, Any] = {}
        if self._expected_publication_generation is not None:
            execute_kwargs["expected_publication_generation"] = (
                self._expected_publication_generation
            )
        started = execute_application_command_async(
            self,
            command,
            on_result=_handle_result,
            on_error=_handle_error,
            refresh=False,
            busy_target=self,
            **execute_kwargs,
        )
        if not started:
            self._set_preview_busy(False)
            self._clear_preview("Label preview is unavailable.")
            show_warning(
                self,
                "Label Preview Unavailable",
                "The application backend is unavailable for label review.",
            )

    def _handle_preview_failure(self, result: Any) -> InteractionOutcome:
        if is_stale_publication_result(result):
            self._clear_preview("The loaded data changed. Review label import again.")
            show_warning(
                self,
                "Review Label Import Again",
                str(result.message),
            )
            self.reject()
            return InteractionOutcome.blocked(str(result.message))
        try:
            preflight = ResourcePreflightView.from_diagnostics(
                getattr(result, "diagnostics", {})
            )
        except ResourcePreflightContractError:
            preflight = None
        error_type = getattr(
            getattr(result, "error_type", None),
            "value",
            getattr(result, "error_type", None),
        )
        if (
            preflight is not None
            and preflight.requires_confirmation
            and preflight.challenge is not None
            and error_type == ErrorType.CONFIRMATION_REQUIRED.value
        ):
            confirmed = ask_confirmation(
                self,
                severity=AlertSeverity.WARNING,
                title="Label Resource Check",
                message=(preflight.message or result.message)
                + "\n\nContinue reviewing these label files?",
                confirm_text="Continue",
            )
            if confirmed:
                self._request_preview(
                    confirmed=True,
                    token=preflight.challenge.challenge_id,
                )
                return InteractionOutcome.accepted(
                    "Confirmed label preview was scheduled."
                )
            self._clear_preview("Label review was cancelled.")
            return InteractionOutcome.cancelled("Label review was cancelled.")
        self._clear_preview("Label preview failed.")
        show_error(self, "Label Preview Failed", str(result.message))
        return InteractionOutcome.blocked(str(result.message))

    def _apply_preview_summary(self, summary: Mapping[str, Any]) -> None:
        preview_id = str(summary.get("preview_id") or "").strip()
        raw_paths = summary.get("label_paths")
        raw_unique = summary.get("unique_labels")
        raw_mapping_limit = summary.get("mapping_cardinality_limit")
        if (
            not preview_id
            or not isinstance(raw_paths, list)
            or not raw_paths
            or not isinstance(raw_unique, list)
            or isinstance(raw_mapping_limit, bool)
            or not isinstance(raw_mapping_limit, int)
            or raw_mapping_limit <= 0
            or len(raw_unique) > raw_mapping_limit
        ):
            raise ValueError("Label preview summary is incomplete.")
        normalized_paths = [str(path) for path in raw_paths if str(path)]
        if len(normalized_paths) != len(raw_paths):
            raise ValueError("Label preview paths are incomplete.")
        raw_configs = summary.get("label_configs")
        configs = (
            {
                str(path): dict(config)
                for path, config in raw_configs.items()
                if isinstance(config, Mapping)
            }
            if isinstance(raw_configs, Mapping)
            else {}
        )
        self.label_paths = normalized_paths
        self.label_configs = configs
        self.preview_summary = dict(summary)
        self.unique_labels = sorted(
            (_normalize_label_value(value) for value in raw_unique),
            key=_label_sort_key,
        )
        self.update_unique_labels()

    def _clear_preview(self, message: str) -> None:
        self.preview_summary = {}
        self.unique_labels = []
        if self.map_table is not None:
            self.map_table.setRowCount(0)
        if self.info_label is not None:
            self.info_label.setText(message)

    def _set_preview_busy(self, busy: bool) -> None:
        self._preview_pending = busy
        for widget in (self.file_list, self.browse_button, self.remove_button):
            if widget is not None:
                widget.setEnabled(not busy)
        if self.button_box is not None:
            ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
            if ok_button is not None:
                ok_button.setEnabled(not busy and bool(self.preview_summary))

    def update_unique_labels(self) -> None:
        if self.info_label is None or self.map_table is None:
            return
        if not self.preview_summary:
            self._clear_preview("No labels reviewed.")
            return
        current_mapping: dict[Any, str] = {}
        for row in range(self.map_table.rowCount()):
            code_item = self.map_table.item(row, 0)
            name_item = self.map_table.item(row, 1)
            if code_item is not None and name_item is not None:
                code = code_item.data(Qt.ItemDataRole.UserRole)
                current_mapping[
                    _parse_display_code(code_item.text()) if code is None else code
                ] = name_item.text()
        self.map_table.setRowCount(len(self.unique_labels))
        for row, code in enumerate(self.unique_labels):
            code_item = QTableWidgetItem(str(code))
            code_item.setFlags(code_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            code_item.setData(Qt.ItemDataRole.UserRole, code)
            self.map_table.setItem(row, 0, code_item)
            self.map_table.setItem(
                row,
                1,
                QTableWidgetItem(current_mapping.get(code, f"Event_{code}")),
            )
        total_count = int(self.preview_summary.get("total_label_count") or 0)
        file_count = len(self.label_paths)
        self.info_label.setText(
            f"Reviewed {total_count} labels from {file_count} files. "
            f"Found {len(self.unique_labels)} unique codes."
        )
        self._set_preview_busy(False)

    def get_results(
        self,
    ) -> tuple[LabelImportSelection | None, dict[Any, str] | None]:
        if not self.preview_summary or self.map_table is None:
            return None, None
        preview_id = str(self.preview_summary.get("preview_id") or "").strip()
        if not preview_id:
            return None, None
        mapping: dict[Any, str] = {}
        for row in range(self.map_table.rowCount()):
            code_item = self.map_table.item(row, 0)
            name_item = self.map_table.item(row, 1)
            if code_item is None or name_item is None:
                continue
            code = code_item.data(Qt.ItemDataRole.UserRole)
            if code is None:
                code = _parse_display_code(code_item.text())
            name = name_item.text().strip()
            if name:
                mapping[code] = name
        raw_target_count = self.preview_summary.get("target_count")
        target_count = raw_target_count if isinstance(raw_target_count, int) else None
        selection = LabelImportSelection(
            preview_id=preview_id,
            label_paths=tuple(self.label_paths),
            label_configs={
                key: dict(value) for key, value in self.label_configs.items()
            },
            mode=str(self.preview_summary.get("mode") or "").lower(),
            target_count=target_count,
        )
        return selection, mapping

    def get_result(
        self,
    ) -> tuple[LabelImportSelection | None, dict[Any, str] | None]:
        return self.get_results()

    def accept(self) -> None:
        if self._preview_pending:
            show_warning(self, "Warning", "Label review is still running.")
            return
        selection, mapping = self.get_results()
        if selection is None:
            show_warning(self, "Warning", "No labels have been reviewed.")
            return
        if selection.mode == "mixed":
            show_warning(
                self,
                "Warning",
                "Timestamp and sequence label files cannot be mixed in one import.",
            )
            return
        if not mapping or len(mapping) != len(self.unique_labels):
            show_warning(self, "Warning", "Please provide all event names.")
            return
        super().accept()
