"""Montage picker dialog for mapping dataset channels to standard montage positions.

Features reviewed name matching and saved settings persistence.  Mapping never
infers an electrode from adjacent table rows.
"""

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.utils.mne_helper import (
    get_builtin_montages,
    get_montage_channel_positions,
    get_montage_positions,
)
from XBrainLab.ui.components.modal_presentation import (
    show_error,
    show_warning,
)
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import (
    configure_dark_table,
    dark_dialog_stylesheet,
    fit_table_height_to_contents,
    normalize_dialog_button_box,
)
from XBrainLab.ui.styles.theme import Theme


def _mapping_table_stylesheet() -> str:
    return f"""
        QTableWidget#MontageMappingTable {{
            background-color: {Theme.METRICS_TABLE_BG};
            alternate-background-color: {Theme.METRICS_TABLE_ALT_BG};
            color: {Theme.TEXT_PRIMARY};
            gridline-color: {Theme.METRICS_TABLE_GRID};
            border: 1px solid {Theme.METRICS_TABLE_BORDER};
            selection-background-color: {Theme.TABLE_SELECTION};
            selection-color: {Theme.TEXT_PRIMARY};
        }}
        QTableWidget#MontageMappingTable::item {{
            padding: 4px 8px;
            color: {Theme.TEXT_PRIMARY};
        }}
        QHeaderView::section {{
            background-color: {Theme.BACKGROUND_MID};
            color: {Theme.TEXT_SECONDARY};
            border: none;
            border-bottom: 1px solid {Theme.METRICS_TABLE_GRID};
            padding: 5px 8px;
            font-weight: bold;
        }}
    """


def _mapping_combo_stylesheet(row_color: str) -> str:
    return f"""
        QComboBox#MontageChannelCombo {{
            background-color: {row_color};
            color: {Theme.TEXT_PRIMARY};
            border: none;
            padding: 2px 24px 2px 8px;
            min-height: 24px;
        }}
        QComboBox#MontageChannelCombo:hover {{
            background-color: {Theme.BACKGROUND_MID};
        }}
        QComboBox#MontageChannelCombo::drop-down {{
            border: none;
            width: 22px;
        }}
        QComboBox#MontageChannelCombo QAbstractItemView {{
            background-color: {Theme.METRICS_TABLE_BG};
            color: {Theme.TEXT_PRIMARY};
            border: 1px solid {Theme.METRICS_TABLE_BORDER};
            selection-background-color: {Theme.TABLE_SELECTION};
            selection-color: {Theme.TEXT_PRIMARY};
        }}
    """


class PickMontageDialog(BaseDialog):
    """Dialog for mapping dataset channels to standard montage channels.

    Features name-based suggestions and persistent settings for remembering
    prior reviewed mappings.

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

    def __init__(
        self,
        parent,
        channel_names,
        default_montage=None,
        *,
        current_layout=None,
        is_bids_source=False,
        layout_changes_allowed=True,
    ):
        self.channel_names = channel_names
        self.default_montage = default_montage  # Pre-selected montage from Agent
        self.current_layout = current_layout or {}
        self.is_bids_source = is_bids_source
        self.layout_changes_allowed = layout_changes_allowed
        self._restore_bids_requested = False

        self.chs = None
        self.positions = None
        self.electrode_names = None
        self.montage_channels = []
        self.montage_list: list = []
        self._ignored_saved_montages: set[str] = set()

        # Settings for persistence
        self.settings = QSettings("XBrainLab", "MontagePicker")

        # UI Elements
        self.montage_combo = None
        self.table = None
        self.summary_page = None
        self.mapping_page = None
        self.button_box = None

        super().__init__(parent, title="Electrode Layout")
        self.setMinimumWidth(700)
        self.setStyleSheet(dark_dialog_stylesheet())

        # Trigger initial montage load even when the compact BIDS summary is shown.
        if self.montage_combo and self.montage_combo.currentText():
            self.on_montage_select(self.montage_combo.currentText())
        elif self.montage_list and self.montage_combo:
            self.on_montage_select(self.montage_list[0])

        self._resize_dialog_to_content()

    def init_ui(self):
        """Initialize the dialog UI with montage selector and mapping table."""
        if not self.channel_names:
            show_error(self, "Error", "No valid channel name is provided")
            self.reject()
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        self.summary_page = QWidget(self)
        summary_layout = QVBoxLayout(self.summary_page)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(10)
        summary_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        summary_heading = QLabel("Current electrode layout")
        summary_heading.setProperty("role", "section-title")
        summary_layout.addWidget(summary_heading)
        source = str(self.current_layout.get("source") or "not configured")
        name = str(self.current_layout.get("name") or source.upper())
        positioned = int(self.current_layout.get("positioned_channel_count") or 0)
        count = int(self.current_layout.get("channel_count") or len(self.channel_names))
        frame = str(self.current_layout.get("coordinate_summary") or "not specified")
        status = str(self.current_layout.get("status") or "not configured")
        summary_details = QLabel(
            f"Layout: {name}\nSource: {source.upper()} · {status}\n"
            f"Coverage: {positioned}/{count} channels positioned\n"
            f"Coordinate frame: {frame}"
        )
        summary_details.setWordWrap(True)
        summary_details.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        summary_layout.addWidget(summary_details)
        if not self.layout_changes_allowed:
            blocked = QLabel("Clear training before replacing this layout.")
            blocked.setWordWrap(True)
            summary_layout.addWidget(blocked)
        summary_actions = QHBoxLayout()
        self.btn_change_layout = QPushButton("Change Layout")
        self.btn_change_layout.setEnabled(self.layout_changes_allowed)
        self.btn_change_layout.clicked.connect(self.show_mapping_page)
        summary_actions.addWidget(self.btn_change_layout)
        self.btn_use_bids = QPushButton("Use BIDS Layout")
        can_restore = bool(self.current_layout.get("bids_restore_available"))
        self.btn_use_bids.setVisible(can_restore)
        self.btn_use_bids.setEnabled(can_restore and self.layout_changes_allowed)
        self.btn_use_bids.clicked.connect(self.restore_bids)
        summary_actions.addWidget(self.btn_use_bids)
        summary_actions.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        summary_actions.addWidget(close_button)
        summary_layout.addLayout(summary_actions)
        layout.addWidget(self.summary_page)

        self.mapping_page = QWidget(self)
        mapping_layout = QVBoxLayout(self.mapping_page)
        mapping_layout.setContentsMargins(0, 0, 0, 0)
        mapping_layout.setSpacing(12)

        # Top: Montage Selection
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Standard layout:"))

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
        self.btn_clear = QPushButton("Clear Mapping")
        self.btn_clear.clicked.connect(self.clear_selections)
        top_layout.addWidget(self.btn_clear)

        # Reset Saved Button (for demoing Smart Match)
        self.btn_reset_saved = QPushButton("Auto Match")
        self.btn_reset_saved.setToolTip(
            "Clear saved settings for this montage and re-run Smart Match",
        )
        self.btn_reset_saved.clicked.connect(self.reset_saved_settings)
        top_layout.addWidget(self.btn_reset_saved)

        mapping_layout.addLayout(top_layout)

        # Center: Mapping Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Dataset Channel", "Electrode"])
        configure_dark_table(self.table, object_name="MontageMappingTable")
        header = self.table.horizontalHeader()
        if header is not None:
            header.setMinimumSectionSize(160)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.table.setColumnWidth(0, 240)
        v_header = self.table.verticalHeader()
        if v_header is not None:
            v_header.setVisible(False)
            v_header.setDefaultSectionSize(34)
            v_header.setMinimumSectionSize(32)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setStyleSheet(_mapping_table_stylesheet())
        palette = self.table.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(Theme.METRICS_TABLE_BG))
        palette.setColor(
            QPalette.ColorRole.AlternateBase,
            QColor(Theme.METRICS_TABLE_ALT_BG),
        )
        palette.setColor(QPalette.ColorRole.Text, QColor(Theme.TEXT_PRIMARY))
        self.table.setPalette(palette)

        mapping_layout.addWidget(self.table)

        # Bottom: Dialog Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        normalize_dialog_button_box(buttons)
        self.button_box = buttons
        if self.is_bids_source:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Replace Layout")
            back_button = buttons.addButton(
                "Back", QDialogButtonBox.ButtonRole.ActionRole
            )
            back_button.clicked.connect(self.show_summary_page)
        if not self.layout_changes_allowed:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        mapping_layout.addWidget(buttons)
        layout.addWidget(self.mapping_page)

        show_summary = self.is_bids_source and bool(self.current_layout)
        self.summary_page.setVisible(show_summary)
        self.mapping_page.setVisible(not show_summary)

        # Initialize table with dataset channels
        self.init_table()

    def show_mapping_page(self):
        """Expand the existing picker in-place after the BIDS summary."""
        if self.summary_page is not None:
            self.summary_page.setVisible(False)
        if self.mapping_page is not None:
            self.mapping_page.setVisible(True)
        self._resize_dialog_to_content()

    def show_summary_page(self):
        """Return to the compact current-layout view without changing data."""
        if self.mapping_page is not None:
            self.mapping_page.setVisible(False)
        if self.summary_page is not None:
            self.summary_page.setVisible(True)
        self._resize_dialog_to_content()

    def restore_bids(self):
        """Return an explicit request for the retained BIDS snapshot."""
        self._restore_bids_requested = True
        super().accept()

    def restore_bids_requested(self) -> bool:
        """Whether acceptance selected the retained BIDS layout."""
        return self._restore_bids_requested

    def init_table(self):
        """Populate the table with dataset channel names as read-only rows."""
        if not self.table:
            return
        self.table.setRowCount(len(self.channel_names))
        for i, ch_name in enumerate(self.channel_names):
            # Column 0: Dataset Channel (Read-only)
            item = QTableWidgetItem(ch_name)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setForeground(QColor(Theme.TEXT_PRIMARY))
            item.setBackground(QColor(self._row_color(i)))
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

            # Load saved mapping for this montage
            saved_mapping = (
                {}
                if montage_name in self._ignored_saved_montages
                else self.settings.value(f"mapping/{montage_name}", {})
            )

            # 1. Create all widgets and run Smart Match / Load Settings
            for row in range(self.table.rowCount()):
                dataset_item = self.table.item(row, 0)
                if dataset_item is None:
                    continue
                dataset_ch = dataset_item.text()

                # Create Searchable ComboBox
                combo = QComboBox()
                combo.setObjectName("MontageChannelCombo")
                combo.setEditable(True)
                combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
                combo.setStyleSheet(_mapping_combo_stylesheet(self._row_color(row)))

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
                        continue

                # If no saved setting, use Smart Match
                self.smart_match(combo, dataset_ch)

            self._resize_mapping_table_to_content()

        except Exception:
            present_unexpected_error(
                self,
                UnexpectedErrorContext.MONTAGE_MAPPING_PREPARE,
            )

    def _resize_mapping_table_to_content(self) -> None:
        """Show short mappings without an empty viewport and bound long lists."""
        if self.table is None:
            return
        fit_table_height_to_contents(
            self.table,
            max_visible_rows=10,
            minimum_rows=1,
            padding=8,
        )

    def _resize_dialog_to_content(self) -> None:
        """Fit the dialog around the mapping rows without exceeding a useful size."""
        showing_summary = (
            self.summary_page is not None and not self.summary_page.isHidden()
        )
        minimum_height = 200 if showing_summary else 320
        self.setMinimumHeight(minimum_height)
        self.fit_to_content(
            minimum_width=700,
            minimum_height=minimum_height,
            maximum_height=640,
        )

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

    def clear_selections(self):
        """Clear all channel mappings and anchors."""
        if not self.table:
            return
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

        # Recompute this dialog's rows without changing persisted preferences
        # until the user explicitly replaces the layout.
        self._ignored_saved_montages.add(montage_name)
        self.on_montage_select(montage_name)

    @staticmethod
    def _row_color(row: int) -> str:
        return Theme.METRICS_TABLE_ALT_BG if row % 2 else Theme.METRICS_TABLE_BG

    def accept(self):
        """Build the channel mapping, save settings, and accept the dialog.

        Displays a warning if no channels are mapped. Unexpected montage
        processing failures use the central error presentation.

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
            show_warning(self, "Warning", "No channels mapped.")
            return

        # Save settings
        self.settings.setValue("last_montage", montage_name)
        self.settings.setValue(f"mapping/{montage_name}", selected_map)
        self._ignored_saved_montages.discard(montage_name)

        # Prepare result
        mapped_dataset_chs = list(selected_map.keys())
        mapped_montage_chs = list(selected_map.values())

        try:
            positions = get_montage_channel_positions(montage_name, mapped_montage_chs)

            self.chs = mapped_dataset_chs
            self.positions = positions
            self.electrode_names = mapped_montage_chs
            super().accept()

        except Exception:
            present_unexpected_error(
                self,
                UnexpectedErrorContext.MONTAGE_MAPPING_APPLY,
            )

    def get_result(self):
        """Return the channel mapping and position data.

        Returns:
            Tuple of (mapped_channel_names, channel_positions).

        """
        return self.chs, self.positions

    def get_electrode_names(self):
        """Return the reviewed electrode identity aligned with ``get_result``."""
        return self.electrode_names
