"""Montage picker dialog for mapping dataset channels to standard montage positions.

Features smart matching, saved settings persistence, and live cascading
fill to streamline the channel-to-montage mapping workflow.
"""

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.utils.mne_helper import (
    get_builtin_montages,
    get_montage_channel_positions,
    get_montage_positions,
)
from XBrainLab.ui.core.base_dialog import BaseDialog


class PickMontageDialog(BaseDialog):
    """Dialog for mapping dataset channels to standard montage channels.

    Features Smart Match for automatic channel name matching, Live
    Cascading Fill for sequential channel propagation, and persistent
    settings for remembering previous mappings.

    Attributes:
        channel_names: List of dataset channel names to map.
        default_montage: Pre-selected montage name, or None.
        chs: List of mapped dataset channel names after acceptance.
        positions: Channel position data from the selected montage.
        montage_channels: List of channel names from the current montage.
        anchors: Set of row indices explicitly set by the user.
        settings: QSettings for persisting montage selections.
        montage_combo: QComboBox for selecting the montage standard.
        table: QTableWidget with mapping from dataset to montage channels.

    """

    def __init__(self, parent, channel_names, default_montage=None):
        self.channel_names = channel_names
        self.default_montage = default_montage  # Pre-selected montage from Agent

        self.chs = None
        self.positions = None
        self.montage_channels = []
        self.montage_list = []

        # Track which rows are explicitly set (Anchors)
        # Set of row indices
        self.anchors = set()

        # Settings for persistence
        self.settings = QSettings("XBrainLab", "MontagePicker")

        # UI Elements
        self.montage_combo = None
        self.table = None

        super().__init__(parent, title="Set Montage")
        self.resize(700, 500)

        # Trigger initial montage load
        if self.montage_combo and self.montage_combo.currentText():
            self.on_montage_select(self.montage_combo.currentText())
        elif self.montage_list and self.montage_combo:
            self.on_montage_select(self.montage_list[0])

    def init_ui(self):
        """Initialize the dialog UI with montage selector and mapping table."""
        if not self.channel_names:
            QMessageBox.critical(self, "Error", "No valid channel name is provided")
            self.reject()
            return

        layout = QVBoxLayout(self)

        # Top: Montage Selection
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Montage:"))

        self.montage_combo = QComboBox()
        self.montage_list = get_builtin_montages()
        self.montage_combo.addItems(self.montage_list)

        # Use Agent-provided montage first, then last used, then first in list
        target_montage = None
        if self.default_montage and self.default_montage in self.montage_list:
            target_montage = self.default_montage
        else:
            last_montage = self.settings.value("last_montage", "")
            if last_montage and last_montage in self.montage_list:
                target_montage = last_montage

        if target_montage:
            self.montage_combo.setCurrentText(target_montage)

        self.montage_combo.currentTextChanged.connect(self.on_montage_select)
        top_layout.addWidget(self.montage_combo)

        top_layout.addStretch()

        # Clear Button
        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.clicked.connect(self.clear_selections)
        top_layout.addWidget(self.btn_clear)

        # Reset Saved Button (for demoing Smart Match)
        self.btn_reset_saved = QPushButton("Reset Saved")
        self.btn_reset_saved.setToolTip(
            "Clear saved settings for this montage and re-run Smart Match",
        )
        self.btn_reset_saved.clicked.connect(self.reset_saved_settings)
        top_layout.addWidget(self.btn_reset_saved)

        layout.addLayout(top_layout)

        # Center: Mapping Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Dataset Channel", "Montage Channel"])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        layout.addWidget(self.table)

        # Bottom: Dialog Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Initialize table with dataset channels
        self.init_table()

    def init_table(self):
        """Populate the table with dataset channel names as read-only rows."""
        if not self.table:
            return
        self.table.setRowCount(len(self.channel_names))
        for i, ch_name in enumerate(self.channel_names):
            # Column 0: Dataset Channel (Read-only)
            item = QTableWidgetItem(ch_name)
            item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)  # Make read-only
            self.table.setItem(i, 0, item)

    def on_montage_select(self, montage_name):
        """Load montage channels and apply smart match / saved settings.

        Args:
            montage_name: Name of the selected montage standard.

        """
        if not self.table or not self.settings:
            return

        try:
            positions = get_montage_positions(montage_name)
            self.montage_channels = list(positions["ch_pos"].keys())

            # Reset anchors for new montage
            self.anchors.clear()

            # Load saved mapping for this montage
            saved_mapping = self.settings.value(f"mapping/{montage_name}", {})

            # 1. Create all widgets and run Smart Match / Load Settings
            for row in range(self.table.rowCount()):
                dataset_item = self.table.item(row, 0)
                if dataset_item is None:
                    continue
                dataset_ch = dataset_item.text()

                # Create Searchable ComboBox
                combo = QComboBox()
                combo.setEditable(True)
                combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

                # Add empty option at top
                combo.addItem("")
                combo.addItems(self.montage_channels)

                # Setup Completer for searching
                completer = QCompleter(self.montage_channels)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                combo.setCompleter(completer)

                self.table.setCellWidget(row, 1, combo)

                # Logic:
                # Try to load from saved settings
                if dataset_ch in saved_mapping:
                    idx = combo.findText(saved_mapping[dataset_ch])
                    if idx != -1:
                        combo.setCurrentIndex(idx)
                        self.anchors.add(row)  # Mark as anchor
                        continue

                # If no saved setting, use Smart Match
                if self.smart_match(combo, dataset_ch):
                    self.anchors.add(row)  # Mark as anchor

            # 2. Run initial batch Sequential Fill to fill gaps
            self.initial_sequential_fill()

            # 3. Connect signals for Live Cascading Fill
            for row in range(self.table.rowCount()):
                widget = self.table.cellWidget(row, 1)
                if isinstance(widget, QComboBox):
                    # Use lambda with captured row to identify source
                    widget.currentIndexChanged.connect(
                        lambda idx, r=row: self.on_channel_changed(r, idx),
                    )

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load montage: {e}")

    def initial_sequential_fill(self):
        """Run a one-pass sequential fill for initialization."""
        if not self.table:
            return

        # Sort anchors by row index
        sorted_anchors = sorted(self.anchors)

        if not sorted_anchors:
            return

        for i in range(len(sorted_anchors)):
            curr_row = sorted_anchors[i]
            curr_combo = self.table.cellWidget(curr_row, 1)
            if not isinstance(curr_combo, QComboBox):
                continue
            curr_ch = curr_combo.currentText()

            if i < len(sorted_anchors) - 1:
                next_row = sorted_anchors[i + 1]
                fill_range = range(curr_row + 1, next_row)
            else:
                fill_range = range(curr_row + 1, self.table.rowCount())

            try:
                curr_montage_idx = self.montage_channels.index(curr_ch)
            except ValueError:
                continue

            offset = 1
            for target_row in fill_range:
                target_montage_idx = curr_montage_idx + offset
                if target_montage_idx < len(self.montage_channels):
                    target_ch = self.montage_channels[target_montage_idx]
                    combo = self.table.cellWidget(target_row, 1)

                    if isinstance(combo, QComboBox) and target_row not in self.anchors:
                        idx = combo.findText(target_ch)
                        if idx != -1:
                            combo.setCurrentIndex(idx)
                            # Do NOT add to anchors
                offset += 1

    def smart_match(self, combo, target_name):
        """Try to find the best montage channel match for a dataset channel.

        Performs exact match, case-insensitive match, then cleaned fuzzy
        match to find the closest montage channel.

        Args:
            combo: QComboBox containing montage channel options.
            target_name: Dataset channel name to match.

        Returns:
            True if a match was found and set, False otherwise.

        """
        target = target_name.lower().strip()

        # Clean target name
        clean_target = (
            target.replace("eeg", "").replace("ref", "").replace("-", "").strip()
        )

        best_match_idx = -1

        # 1. Exact Match (Case Insensitive)
        idx = combo.findText(
            target_name,
            Qt.MatchFlag.MatchFixedString | Qt.MatchFlag.MatchCaseSensitive,
        )
        if idx != -1:
            best_match_idx = idx
        else:
            # 2. Case Insensitive Match
            idx = combo.findText(target_name, Qt.MatchFlag.MatchFixedString)
            if idx != -1:
                best_match_idx = idx
            else:
                # 3. Fuzzy / Cleaned Match
                for i in range(1, combo.count()):  # Skip empty first item
                    item_text = combo.itemText(i).lower()
                    if item_text == clean_target:
                        best_match_idx = i
                        break

        if best_match_idx != -1:
            combo.setCurrentIndex(best_match_idx)
            return True
        return False

    def on_channel_changed(self, row, index):
        """Handle channel selection changes with live cascading fill.

        When a channel is selected, automatically fills subsequent rows
        with sequential montage channels until the next anchor or end.

        Args:
            row: Row index where the change occurred.
            index: New combo box index.

        """
        if not self.table:
            return

        if index <= 0:
            # If cleared, remove from anchors?
            if row in self.anchors:
                self.anchors.remove(row)
            return

        # Mark as anchor
        self.anchors.add(row)

        combo = self.table.cellWidget(row, 1)
        if not isinstance(combo, QComboBox):
            return
        current_ch = combo.currentText()

        try:
            current_montage_idx = self.montage_channels.index(current_ch)
        except ValueError:
            return

        # Find next anchor to determine limit
        next_anchor_row = self.table.rowCount()
        for r in range(row + 1, self.table.rowCount()):
            if r in self.anchors:
                next_anchor_row = r
                break

        # Cascade fill subsequent rows
        offset = 1
        for target_row in range(row + 1, next_anchor_row):
            target_combo = self.table.cellWidget(target_row, 1)
            if not isinstance(target_combo, QComboBox):
                continue

            # Calculate next channel
            target_montage_idx = current_montage_idx + offset

            if target_montage_idx < len(self.montage_channels):
                target_ch = self.montage_channels[target_montage_idx]

                # Set the combo WITHOUT triggering signal
                idx = target_combo.findText(target_ch)
                if idx != -1:
                    target_combo.blockSignals(True)
                    target_combo.setCurrentIndex(idx)
                    target_combo.blockSignals(False)
                    # Do NOT add to anchors
            else:
                break

            offset += 1

    def clear_selections(self):
        """Clear all channel mappings and anchors."""
        if not self.table:
            return
        self.anchors.clear()
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 1)
            if isinstance(combo, QComboBox):
                combo.blockSignals(True)
                combo.setCurrentIndex(0)
                combo.setCurrentIndex(0)
                combo.blockSignals(False)

    def reset_saved_settings(self):
        """Clear saved settings for current montage and re-run Smart Match."""
        if not self.montage_combo:
            return
        montage_name = self.montage_combo.currentText()
        if not montage_name:
            return

        # Remove from settings
        self.settings.remove(f"mapping/{montage_name}")

        # Reload montage (triggers Smart Match since settings are gone)
        self.on_montage_select(montage_name)

        QMessageBox.information(
            self,
            "Reset",
            f"Saved settings for '{montage_name}' have been cleared.\n"
            f"Smart Match has been re-applied.",
        )

    def accept(self):
        """Build the channel mapping, save settings, and accept the dialog.

        Raises:
            QMessageBox: Warning if no channels are mapped or montage
                processing fails.

        """
        if not self.table or not self.montage_combo:
            return

        selected_map = {}
        montage_name = self.montage_combo.currentText()

        for row in range(self.table.rowCount()):
            dataset_item = self.table.item(row, 0)
            if dataset_item is None:
                continue
            dataset_ch = dataset_item.text()
            combo = self.table.cellWidget(row, 1)
            if isinstance(combo, QComboBox):
                selected_montage_ch = combo.currentText()
                if selected_montage_ch:
                    selected_map[dataset_ch] = selected_montage_ch

        if not selected_map:
            QMessageBox.warning(self, "Warning", "No channels mapped.")
            return

        # Save settings
        self.settings.setValue("last_montage", montage_name)
        self.settings.setValue(f"mapping/{montage_name}", selected_map)

        # Prepare result
        mapped_dataset_chs = list(selected_map.keys())
        mapped_montage_chs = list(selected_map.values())

        try:
            positions = get_montage_channel_positions(montage_name, mapped_montage_chs)

            self.chs = mapped_dataset_chs
            self.positions = positions
            super().accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error processing montage: {e}")

    def get_result(self):
        """Return the channel mapping and position data.

        Returns:
            Tuple of (mapped_channel_names, channel_positions).

        """
        return self.chs, self.positions
