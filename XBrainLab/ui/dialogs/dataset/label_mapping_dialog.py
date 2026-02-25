"""Label-to-data file mapping dialog for aligning label files with data files.

Provides a dual-list interface where data files are fixed and label files
can be reordered via drag-and-drop to establish correct alignment.
"""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.styles.stylesheets import Stylesheets


class LabelMappingDialog(BaseDialog):
    """Dialog for mapping label files to their corresponding data files.

    Displays data files in a fixed list on the left and label files in a
    reorderable (drag-and-drop) list on the right. Supports automatic
    name-based sorting and synchronized scrolling.

    Attributes:
        data_files: List of data file paths.
        label_files: List of label file paths.
        mapping: Dictionary mapping data file paths to label file paths.
        data_list: QListWidget displaying data files (fixed order).
        label_list: QListWidget displaying label files (reorderable).

    """

    def __init__(self, parent, data_files, label_files):
        self.data_files = data_files  # List of data file paths/names
        self.label_files = label_files  # List of label file paths/names
        self.mapping = {}  # {data_filename: label_filename}

        # UI
        self.data_list = None
        self.label_list = None

        super().__init__(parent, title="Map Labels to Data Files")
        self.resize(600, 400)

    def init_ui(self):
        """Initialize the dialog UI with data and label file lists."""
        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel(
                "Drag and drop Label files (Right) to align with Data files (Left):"
            ),
        )

        # Main layout for lists
        lists_layout = QHBoxLayout()

        # Left: Data Files (Fixed)
        data_layout = QVBoxLayout()
        data_layout.addWidget(QLabel("Data Files (Fixed)"))
        self.data_list = QListWidget()
        self.data_list.setSelectionMode(
            QListWidget.SelectionMode.SingleSelection,
        )  # Allow selection for highlighting
        self.data_list.setUniformItemSizes(True)
        self.data_list.setAlternatingRowColors(True)

        self.data_list.setStyleSheet(Stylesheets.LIST_ITEM_HEIGHT)  # Enforce height
        # self.data_list.setEnabled(False) # Don't disable, just make non-selectable?
        # Or just visual.
        # Better to keep enabled for scrolling, but disallow drag/drop
        for f in self.data_files:
            self.data_list.addItem(os.path.basename(f))
        data_layout.addWidget(self.data_list)
        lists_layout.addLayout(data_layout)

        # Right: Label Files (Reorderable)
        label_layout = QVBoxLayout()
        label_layout.addWidget(QLabel("Label Files (Drag to Reorder)"))
        self.label_list = QListWidget()
        self.label_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.label_list.setUniformItemSizes(True)
        self.label_list.setAlternatingRowColors(True)
        self.label_list.setStyleSheet(Stylesheets.LIST_ITEM_HEIGHT)  # Enforce height

        # Auto-sort label files to match data files
        sorted_labels = self.auto_sort_labels()

        for f in sorted_labels:
            item = QListWidgetItem(os.path.basename(f) if f else "-- No Label --")
            item.setData(Qt.ItemDataRole.UserRole, f)  # Store full path/key
            if not f:
                item.setForeground(Qt.GlobalColor.gray)
            self.label_list.addItem(item)

        label_layout.addWidget(self.label_list)
        lists_layout.addLayout(label_layout)

        layout.addLayout(lists_layout)

        # Sync scrolling
        data_scroll = self.data_list.verticalScrollBar()
        label_scroll = self.label_list.verticalScrollBar()
        if data_scroll and label_scroll:
            data_scroll.valueChanged.connect(label_scroll.setValue)
            label_scroll.valueChanged.connect(data_scroll.setValue)

        # Sync selection for visual alignment
        self.data_list.currentRowChanged.connect(self.label_list.setCurrentRow)
        self.label_list.currentRowChanged.connect(self.data_list.setCurrentRow)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def auto_sort_labels(self):
        """Automatically align label files with data files by name matching.

        Attempts to match label files to data files using filename
        containment heuristics, then fills remaining slots sequentially.

        Returns:
            List of label file paths aligned to the data file order,
            with None for any unmatched slots.

        """
        aligned_labels = [None] * len(self.data_files)
        used_indices = set()

        # 1. Try strict matching
        for i, data_file in enumerate(self.data_files):
            data_name = os.path.basename(data_file)
            data_stem = os.path.splitext(data_name)[0]

            best_match = None
            best_match_idx = -1

            for j, label_file in enumerate(self.label_files):
                if j in used_indices:
                    continue

                label_name = os.path.basename(label_file)
                label_stem = os.path.splitext(label_name)[0]

                # Check for containment
                if data_stem in label_name or label_stem in data_name:
                    best_match = label_file
                    best_match_idx = j
                    break

            if best_match:
                aligned_labels[i] = best_match
                used_indices.add(best_match_idx)

        # 2. Fill gaps with remaining labels
        remaining_labels = [
            f for j, f in enumerate(self.label_files) if j not in used_indices
        ]

        # If we have more data files than labels, some will be None (handled by None
        # init)
        # Fill empty slots in data file mapping with remaining labels first
        rem_idx = 0
        for i in range(len(aligned_labels)):
            if aligned_labels[i] is None and rem_idx < len(remaining_labels):
                aligned_labels[i] = remaining_labels[rem_idx]
                rem_idx += 1

        # Append remaining unmapped labels to the end of the list.
        # This allows the user to manually rearrange them if needed.
        while rem_idx < len(remaining_labels):
            aligned_labels.append(remaining_labels[rem_idx])
            rem_idx += 1

        return aligned_labels

    def accept(self):
        """Build the data-to-label mapping from current list order and accept."""
        self.mapping = {}
        # Map based on index
        if self.data_list and self.label_list:
            count = min(self.data_list.count(), self.label_list.count())
            for i in range(count):
                data_file = self.data_files[i]  # data list is fixed order
                label_item = self.label_list.item(i)
                if label_item:
                    label_file = label_item.data(Qt.ItemDataRole.UserRole)

                    if label_file:
                        self.mapping[data_file] = label_file

        super().accept()

    def get_mapping(self):
        """Return the data-to-label file mapping.

        Returns:
            Dictionary mapping data file paths to label file paths.

        """
        return self.mapping

    def get_result(self):
        """Return the data-to-label file mapping.

        Returns:
            Dictionary mapping data file paths to label file paths.

        """
        return self.get_mapping()
