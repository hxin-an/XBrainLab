"""Label import dialog for loading and mapping external label files.

Provides file selection, automatic label code detection, and a mapping
table for assigning human-readable event names to numeric label codes.
"""

import os
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
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.load_data.label_loader import load_label_file
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.base_dialog import BaseDialog


def _normalize_label_value(value: Any) -> Any:
    """Convert NumPy scalars to native Python scalars for UI/state storage."""
    if isinstance(value, np.generic):
        return value.item()
    return value


def _label_sort_key(value: Any) -> tuple[int, Any]:
    """Sort numeric codes numerically and other labels lexically."""
    value = _normalize_label_value(value)

    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return (0, int(value))

    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return (0, int(value))

    return (1, str(value))


def _parse_display_code(text: str) -> Any:
    """Best-effort parser for legacy table rows that only stored text."""
    try:
        return int(text)
    except ValueError:
        return text


class ImportLabelDialog(BaseDialog):
    """Dialog for importing label files and mapping codes to event names.

    Supports loading label files in various formats (txt, mat, csv, tsv),
    detecting unique label values, and allowing the user to assign
    descriptive event names to each value.

    Attributes:
        label_data_map: Mapping of label file path to loaded label data arrays.
        unique_labels: Sorted list of unique label values across all files.
        file_list: QListWidget displaying loaded label files.
        map_table: QTableWidget for code-to-event-name mapping.
        info_label: QLabel showing summary statistics.

    """

    def __init__(self, parent=None, target_files: list[Any] | None = None):
        self.label_data_map: dict[str, Any] = {}  # {label_path: label_array}
        self.unique_labels: list[Any] = []
        self.target_files = list(target_files or [])

        # UI Elements
        self.file_list: QListWidget | None = None
        self.map_table: QTableWidget | None = None
        self.info_label: QLabel | None = None
        self.target_summary_label: QLabel | None = None
        self.recipe_note_label: QLabel | None = None

        super().__init__(parent, title="Add Labels to Loaded Data")
        self.resize(580, 460)

    def init_ui(self):
        """Initialize the dialog UI with file list, mapping table, and buttons."""
        layout = QVBoxLayout(self)

        self.target_summary_label = QLabel(self._target_summary_text())
        self.target_summary_label.setWordWrap(True)
        self.target_summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        layout.addWidget(self.target_summary_label)

        self.recipe_note_label = QLabel(
            "A successful import updates the current import recipe trace when a "
            "data interpretation is active."
        )
        self.recipe_note_label.setWordWrap(True)
        layout.addWidget(self.recipe_note_label)

        # 1. File Selection
        file_group = QGroupBox("Select Label File")
        file_layout = QHBoxLayout()

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.itemSelectionChanged.connect(self.on_file_selection_changed)

        btn_layout = QVBoxLayout()
        browse_btn = QPushButton("Add Files...")
        browse_btn.clicked.connect(self.browse_files)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_files)
        btn_layout.addWidget(browse_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()

        file_layout.addWidget(self.file_list, stretch=1)
        file_layout.addLayout(btn_layout)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # 3. Label Mapping
        map_group = QGroupBox("Map Codes to Event Names")
        map_layout = QVBoxLayout()

        self.map_table = QTableWidget()
        self.map_table.setColumnCount(2)
        self.map_table.setHorizontalHeaderLabels(["Code", "Event Name"])
        header = self.map_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        map_layout.addWidget(self.map_table)

        map_group.setLayout(map_layout)
        layout.addWidget(map_group)

        # 4. Info Label
        self.info_label = QLabel("")
        layout.addWidget(self.info_label)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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

    def browse_files(self):
        """Open a file picker and load selected label files."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open Label Files",
            "",
            "Label Files (*.txt *.mat *.csv *.tsv)",
        )
        if not paths:
            return

        for path in paths:
            filename = os.path.basename(path)
            # Check duplicates
            if path in self.label_data_map:
                continue

            try:
                self.load_file(path)
                if self.file_list is not None:
                    item = QListWidgetItem(filename)
                    item.setData(Qt.ItemDataRole.UserRole, path)
                    item.setToolTip(path)
                    self.file_list.addItem(item)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load {filename}: {e}")

        self.update_unique_labels()

    def remove_files(self):
        """Remove selected files from the loaded list."""
        if self.file_list is None:
            return

        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return

        for item in selected_items:
            label_path = item.data(Qt.ItemDataRole.UserRole) or item.text()
            if label_path in self.label_data_map:
                del self.label_data_map[label_path]
            self.file_list.takeItem(self.file_list.row(item))

        self.update_unique_labels()

    def on_file_selection_changed(self):
        """Handle file list selection changes (reserved for future use)."""
        # Maybe show info for selected file?

    def load_file(self, path):
        """Load a label file and store its data.

        Args:
            path: Absolute path to the label file.

        """
        labels = load_label_file(path)
        if labels is not None:
            self.label_data_map[path] = labels

    def update_unique_labels(self):
        """Aggregates labels from all loaded files, finds unique values,
        and updates the mapping table.
        """
        if self.info_label is None or self.map_table is None:
            return

        all_labels: list[Any] = []
        for labels in self.label_data_map.values():
            if (
                isinstance(labels, list)
                and len(labels) > 0
                and isinstance(labels[0], dict)
            ):
                # Timestamp Mode: Extract 'label' from dicts
                all_labels.extend(
                    _normalize_label_value(item["label"]) for item in labels
                )
            else:
                # Sequence Mode: labels is ndarray
                all_labels.extend(_normalize_label_value(label) for label in labels)

        if not all_labels:
            self.unique_labels = []
            self.info_label.setText("No labels loaded.")
            self.map_table.setRowCount(0)
            return

        unique_labels = {_normalize_label_value(label): None for label in all_labels}
        self.unique_labels = sorted(unique_labels.keys(), key=_label_sort_key)
        self.info_label.setText(
            f"Loaded {len(all_labels)} labels from {len(self.label_data_map)} files. "
            f"Found {len(self.unique_labels)} unique codes.",
        )

        # Preserve existing mapping if possible
        current_mapping = {}
        for i in range(self.map_table.rowCount()):
            code_item = self.map_table.item(i, 0)
            name_item = self.map_table.item(i, 1)
            if code_item and name_item:
                try:
                    code = code_item.data(Qt.ItemDataRole.UserRole)
                    if code is None:
                        code = _parse_display_code(code_item.text())
                    name = name_item.text()
                    current_mapping[code] = name
                except Exception:
                    logger.exception("Failed to parse mapping code")

        # Populate Table
        self.map_table.setRowCount(len(self.unique_labels))
        for i, code in enumerate(self.unique_labels):
            # Code (Read-only)
            item_code = QTableWidgetItem(str(code))
            item_code.setFlags(item_code.flags() ^ Qt.ItemFlag.ItemIsEditable)
            item_code.setData(Qt.ItemDataRole.UserRole, code)
            self.map_table.setItem(i, 0, item_code)

            # Name (Editable)
            # Use existing name if available, else default
            name = current_mapping.get(code, f"Event_{code}")
            item_name = QTableWidgetItem(name)
            self.map_table.setItem(i, 1, item_name)

    def get_results(self):
        """Return the loaded label data and code-to-name mapping.

        Returns:
            Tuple of (label_data_map, mapping_dict) where label_data_map maps
            filenames to label arrays and mapping_dict maps raw label values
            to event name strings. Returns (None, None) if no data loaded.

        """
        if not self.label_data_map or not self.map_table:
            return None, None

        mapping = {}
        for i in range(self.map_table.rowCount()):
            code_item = self.map_table.item(i, 0)
            name_item = self.map_table.item(i, 1)
            if code_item and name_item:
                code = code_item.data(Qt.ItemDataRole.UserRole)
                if code is None:
                    code = _parse_display_code(code_item.text())
                name = name_item.text().strip()
                if code is not None and name:
                    mapping[code] = name

        return self.label_data_map, mapping

    def get_result(self):
        """Return the import results.

        Returns:
            Tuple of (label_data_map, mapping_dict).

        """
        return self.get_results()

    def accept(self):
        """Validate loaded data and mapping before accepting the dialog."""
        if not self.label_data_map:
            QMessageBox.warning(self, "Warning", "No labels loaded.")
            return

        # Validate mapping
        _, mapping = self.get_results()
        if not mapping:
            QMessageBox.warning(self, "Warning", "Please provide event names.")
            return

        super().accept()
