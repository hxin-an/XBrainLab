from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialog,
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


class PickMontageWindow(QDialog):
    def __init__(self, parent, channel_names):
        super().__init__(parent)
        self.setWindowTitle("Set Montage")
        self.resize(700, 500)

        self.channel_names = channel_names
        self.check_data()

        self.chs = None
        self.positions = None
        self.montage_channels = []

        # Track which rows are explicitly set (Anchors)
        # Set of row indices
        self.anchors = set()

        # Settings for persistence
        self.settings = QSettings("XBrainLab", "MontagePicker")

        self.init_ui()

    def check_data(self):
        if not self.channel_names:
            QMessageBox.critical(self, "Error", "No valid channel name is provided")
            self.reject()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Top: Montage Selection
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Montage:"))

        self.montage_combo = QComboBox()
        self.montage_list = get_builtin_montages()
        self.montage_combo.addItems(self.montage_list)

        # Load last used montage
        last_montage = self.settings.value("last_montage", "")
        if last_montage and last_montage in self.montage_list:
            self.montage_combo.setCurrentText(last_montage)

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
            "Clear saved settings for this montage and re-run Smart Match"
        )
        self.btn_reset_saved.clicked.connect(self.reset_saved_settings)
        top_layout.addWidget(self.btn_reset_saved)

        layout.addLayout(top_layout)

        # Center: Mapping Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Dataset Channel", "Montage Channel"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        layout.addWidget(self.table)

        # Bottom: Dialog Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Initialize table with dataset channels
        self.init_table()

        # Trigger initial montage load
        if self.montage_combo.currentText():
            self.on_montage_select(self.montage_combo.currentText())
        elif self.montage_list:
            self.on_montage_select(self.montage_list[0])

    def init_table(self):
        self.table.setRowCount(len(self.channel_names))
        for i, ch_name in enumerate(self.channel_names):
            # Column 0: Dataset Channel (Read-only)
            item = QTableWidgetItem(ch_name)
            item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)  # Make read-only
            self.table.setItem(i, 0, item)

            # Column 1: Will be populated with ComboBoxes later

    def on_montage_select(self, montage_name):
        try:
            positions = get_montage_positions(montage_name)
            self.montage_channels = list(positions["ch_pos"].keys())

            # Reset anchors for new montage
            self.anchors.clear()

            # Load saved mapping for this montage
            saved_mapping = self.settings.value(f"mapping/{montage_name}", {})

            # 1. Create all widgets and run Smart Match / Load Settings
            for row in range(self.table.rowCount()):
                dataset_ch = self.table.item(row, 0).text()

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
                combo = self.table.cellWidget(row, 1)
                # Use lambda with captured row to identify source
                combo.currentIndexChanged.connect(
                    lambda idx, r=row: self.on_channel_changed(r, idx)
                )

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load montage: {e}")

    def initial_sequential_fill(self):
        """Run a one-pass sequential fill for initialization."""
        # Sort anchors by row index
        sorted_anchors = sorted(self.anchors)

        if not sorted_anchors:
            return

        for i in range(len(sorted_anchors)):
            curr_row = sorted_anchors[i]
            curr_combo = self.table.cellWidget(curr_row, 1)
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

                    # Only fill if not an anchor (though logic above ensures we are
                    # between anchors)
                    # And check if empty? No, initial fill should fill gaps.
                    if target_row not in self.anchors:
                        idx = combo.findText(target_ch)
                        if idx != -1:
                            combo.setCurrentIndex(idx)
                            # Do NOT add to anchors
                offset += 1

    def smart_match(self, combo, target_name):
        """
        Try to find best match for target_name in combo items.
        Returns True if matched, False otherwise.
        """
        target = target_name.lower().strip()

        # Clean target name
        clean_target = (
            target.replace("eeg", "").replace("ref", "").replace("-", "").strip()
        )

        best_match_idx = -1

        # 1. Exact Match (Case Insensitive)
        idx = combo.findText(
            target_name, Qt.MatchFlag.MatchFixedString | Qt.MatchFlag.MatchCaseSensitive
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
        """
        Live Cascading Fill:
        When a channel is selected in 'row', automatically fill subsequent rows
        with the next channels in the montage sequence.
        Stops at the next ANCHOR or end of list.
        """
        # If user manually changed this, it becomes an anchor
        # But we need to distinguish manual change vs cascade change
        # Since we block signals during cascade (or use a flag), we can assume this call
        # is manual/explicit
        # Wait, setCurrentIndex triggers this signal.
        # We need to block signals when cascading.

        if index <= 0:
            # If cleared, remove from anchors?
            if row in self.anchors:
                self.anchors.remove(row)
            return

        # Mark as anchor
        self.anchors.add(row)

        combo = self.table.cellWidget(row, 1)
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

            # Calculate next channel
            target_montage_idx = current_montage_idx + offset

            if target_montage_idx < len(self.montage_channels):
                target_ch = self.montage_channels[target_montage_idx]

                # Set the combo WITHOUT triggering signal (to avoid recursion and
                # marking as anchor)
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
        self.anchors.clear()
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 1)
            if combo:
                combo.blockSignals(True)
                combo.setCurrentIndex(0)
                combo.setCurrentIndex(0)
                combo.blockSignals(False)

    def reset_saved_settings(self):
        """Clear saved settings for current montage and re-run Smart Match."""
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

    def confirm(self):
        selected_map = {}
        montage_name = self.montage_combo.currentText()

        for row in range(self.table.rowCount()):
            dataset_ch = self.table.item(row, 0).text()
            combo = self.table.cellWidget(row, 1)
            if combo:
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
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error processing montage: {e}")

    def get_result(self):
        return self.chs, self.positions
