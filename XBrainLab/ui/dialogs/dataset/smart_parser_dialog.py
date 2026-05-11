"""Smart metadata parser dialog for extracting subject/session info from filenames.

Provides multiple parsing strategies (split, regex, folder structure, fixed
position) with a live preview table showing extracted metadata for each file.
"""

import os
import re
from typing import cast, override

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QColor, QShowEvent
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.utils.filename_parser import FilenameParser
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.styles.theme import Theme

_PARSER_MODE_WIDTH = 116
_PARSER_SETTINGS_LABEL_WIDTH = 64


class SmartParserDialog(BaseDialog):
    """Dialog for configuring automated metadata extraction from filenames.

    Supports simple split, advanced regex, folder structure, and fixed
    position parsing strategies with a live preview table. Settings are
    persisted via QSettings.

    Attributes:
        filenames: List of file paths to parse.
        parsed_data: Dictionary mapping filepath to ``(subject, session)`` tuples.
        mode_group: QButtonGroup for selecting the parsing mode.
        settings_stack: QStackedWidget holding mode-specific settings pages.
        table: QTableWidget displaying the live parsing preview.

    """

    def __init__(self, filenames: list[str], parent=None):
        self.filenames = filenames
        self.parsed_data: dict[
            str,
            tuple[str, str],
        ] = {}  # filename -> (subject, session)

        # UI Elements
        # UI Elements
        self.mode_group: QButtonGroup = cast(QButtonGroup, None)
        self.radio_split: QRadioButton = cast(QRadioButton, None)
        self.radio_regex: QRadioButton = cast(QRadioButton, None)
        self.radio_folder: QRadioButton = cast(QRadioButton, None)
        self.radio_fixed: QRadioButton = cast(QRadioButton, None)
        self.settings_stack: QStackedWidget = cast(QStackedWidget, None)
        self.table: QTableWidget = cast(QTableWidget, None)
        self.apply_btn: QPushButton = cast(QPushButton, None)
        self.cancel_btn: QPushButton = cast(QPushButton, None)
        self._centered_on_show = False

        # Settings Widgets
        self.split_sep_combo: QComboBox = cast(QComboBox, None)
        self.split_sub_idx: QSpinBox = cast(QSpinBox, None)
        self.split_sess_idx: QSpinBox = cast(QSpinBox, None)
        self.regex_preset_combo: QComboBox = cast(QComboBox, None)
        self.regex_input: QLineEdit = cast(QLineEdit, None)
        self.regex_sub_idx: QSpinBox = cast(QSpinBox, None)
        self.regex_sess_idx: QSpinBox = cast(QSpinBox, None)
        self.fixed_sub_start: QSpinBox = cast(QSpinBox, None)
        self.fixed_sub_len: QSpinBox = cast(QSpinBox, None)
        self.fixed_sess_start: QSpinBox = cast(QSpinBox, None)
        self.fixed_sess_len: QSpinBox = cast(QSpinBox, None)

        super().__init__(parent, title="Smart Metadata Parser")
        self.resize(1000, 700)

        # Load previous settings after UI init
        self.load_settings()
        self.update_preview()

    @override
    def showEvent(self, event: QShowEvent) -> None:
        """Center the parser over the import dialog when it is shown."""
        super().showEvent(event)
        if self._centered_on_show:
            return
        self._center_on_parent_or_screen()
        self._centered_on_show = True

    def _center_on_parent_or_screen(self) -> None:
        frame = self.frameGeometry()
        parent = self.parentWidget()
        if parent is not None:
            frame.moveCenter(parent.frameGeometry().center())
            self.move(frame.topLeft())
            return

        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            frame.moveCenter(screen.availableGeometry().center())
            self.move(frame.topLeft())

    def init_ui(self):
        """Initialize dialog UI with parsing mode controls and preview table."""
        self.setObjectName("SmartParserDialog")
        self.setStyleSheet(self._style_sheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 22, 18, 14)
        layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("SmartParserHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        title_label = QLabel("Smart Parse Metadata")
        title_label.setObjectName("SmartParserTitle")
        subtitle_label = QLabel("Extract subject and session from file names.")
        subtitle_label.setObjectName("SmartParserSubtitle")
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        layout.addWidget(header)

        # 1. Configuration Area
        config_group = QGroupBox("Parsing method")
        config_group.setObjectName("SmartParserMethodGroup")
        config_group.setMaximumWidth(640)
        config_layout = QVBoxLayout()
        config_layout.setContentsMargins(10, 12, 10, 8)
        config_layout.setSpacing(6)

        # Mode Selection
        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(4)
        self.mode_group = QButtonGroup(self)

        self.radio_split = QRadioButton("Simple Split")
        self.radio_regex = QRadioButton("BIDS / Regex")
        self.radio_folder = QRadioButton("Folder Names")
        self.radio_fixed = QRadioButton("Fixed Position")

        self.mode_group.addButton(self.radio_split, 0)
        self.mode_group.addButton(self.radio_regex, 1)
        self.mode_group.addButton(self.radio_folder, 2)
        self.mode_group.addButton(self.radio_fixed, 3)

        self.radio_split.setChecked(True)
        self.radio_split.toggled.connect(self.toggle_mode)
        self.radio_regex.toggled.connect(self.toggle_mode)
        self.radio_folder.toggled.connect(self.toggle_mode)
        self.radio_fixed.toggled.connect(self.toggle_mode)

        for radio in (
            self.radio_split,
            self.radio_regex,
            self.radio_fixed,
            self.radio_folder,
        ):
            self._configure_mode_radio(radio)
            mode_layout.addWidget(radio)
        mode_layout.addStretch()
        config_layout.addLayout(mode_layout)

        # Settings Stack
        self.settings_stack = QStackedWidget()
        self.settings_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self.settings_stack.setMaximumHeight(108)

        # --- Page 0: Split Settings ---
        page_split = QWidget()
        layout_split = self._parser_grid_layout(page_split)

        self.split_sep_combo = QComboBox()
        self.split_sep_combo.addItems(
            ["Underscore (_)", "Hyphen (-)", "Space ( )", "Dot (.)"],
        )
        self.split_sep_combo.setFixedWidth(150)
        self.split_sep_combo.currentIndexChanged.connect(self.update_preview)

        self.split_sub_idx = QSpinBox()
        self.split_sub_idx.setRange(1, 10)
        self.split_sub_idx.setValue(1)
        self.split_sub_idx.setPrefix("Part ")
        self.split_sub_idx.setFixedWidth(82)
        self.split_sub_idx.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.split_sub_idx.valueChanged.connect(self.update_preview)

        self.split_sess_idx = QSpinBox()
        self.split_sess_idx.setRange(1, 10)
        self.split_sess_idx.setValue(2)
        self.split_sess_idx.setPrefix("Part ")
        self.split_sess_idx.setFixedWidth(82)
        self.split_sess_idx.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.split_sess_idx.valueChanged.connect(self.update_preview)

        self._add_settings_row(layout_split, 0, "Separator", self.split_sep_combo)
        self._add_settings_row(layout_split, 1, "Subject is", self.split_sub_idx)
        self._add_settings_row(layout_split, 2, "Session is", self.split_sess_idx)

        self.settings_stack.addWidget(page_split)

        # --- Page 1: Regex Settings ---
        page_regex = QWidget()
        layout_regex = self._parser_grid_layout(page_regex)

        self.regex_preset_combo = QComboBox()
        self.regex_preset_combo.addItems(
            ["Custom", "Subject_Session (e.g. Sub01_Ses01)", "BIDS (sub-01_ses-01)"],
        )
        self.regex_preset_combo.setMaximumWidth(340)
        self.regex_preset_combo.currentIndexChanged.connect(
            self.on_regex_preset_changed,
        )

        self.regex_input = QLineEdit()
        self.regex_input.setPlaceholderText(r"(.*)_(.*)")
        self.regex_input.setMinimumWidth(320)
        self.regex_input.setMaximumWidth(460)
        self.regex_input.textChanged.connect(self.update_preview)

        self.regex_sub_idx = QSpinBox()
        self.regex_sub_idx.setRange(1, 10)
        self.regex_sub_idx.setPrefix("Group ")
        self.regex_sub_idx.setFixedWidth(82)
        self.regex_sub_idx.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.regex_sub_idx.valueChanged.connect(self.update_preview)

        self.regex_sess_idx = QSpinBox()
        self.regex_sess_idx.setRange(1, 10)
        self.regex_sess_idx.setValue(2)
        self.regex_sess_idx.setPrefix("Group ")
        self.regex_sess_idx.setFixedWidth(82)
        self.regex_sess_idx.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.regex_sess_idx.valueChanged.connect(self.update_preview)

        group_widget = QWidget()
        group_row = QHBoxLayout()
        group_widget.setLayout(group_row)
        group_row.setContentsMargins(0, 0, 0, 0)
        group_row.setSpacing(6)
        group_row.addWidget(self._inline_field_label("Subject"))
        group_row.addWidget(self.regex_sub_idx)
        group_row.addSpacing(8)
        group_row.addWidget(self._inline_field_label("Session"))
        group_row.addWidget(self.regex_sess_idx)
        group_row.addStretch()

        self._add_settings_row(layout_regex, 0, "Preset", self.regex_preset_combo)
        self._add_settings_row(layout_regex, 1, "Pattern", self.regex_input)
        self._add_settings_row(layout_regex, 2, "Groups", group_widget)

        self.settings_stack.addWidget(page_regex)

        # --- Page 2: Folder Settings ---
        page_folder = QWidget()
        layout_folder = self._parser_grid_layout(page_folder)
        folder_hint = QLabel("Subject folder / session folder / EEG file")
        folder_hint.setObjectName("SmartParserFolderHint")
        folder_hint.setWordWrap(False)
        folder_hint.setMaximumWidth(520)
        self._add_settings_row(layout_folder, 0, "Pattern", folder_hint)
        self._add_settings_row(
            layout_folder,
            1,
            "Example",
            self._folder_example_widget(),
        )

        self.settings_stack.addWidget(page_folder)

        # --- Page 3: Fixed Position Settings ---
        page_fixed = QWidget()
        layout_fixed = self._parser_grid_layout(page_fixed)

        self.fixed_sub_start = QSpinBox()
        self.fixed_sub_start.setRange(1, 50)
        self.fixed_sub_start.setValue(1)
        self.fixed_sub_start.setMaximumWidth(90)
        self.fixed_sub_start.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.fixed_sub_start.valueChanged.connect(self.update_preview)

        self.fixed_sub_len = QSpinBox()
        self.fixed_sub_len.setRange(1, 50)
        self.fixed_sub_len.setValue(3)
        self.fixed_sub_len.setMaximumWidth(90)
        self.fixed_sub_len.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.fixed_sub_len.valueChanged.connect(self.update_preview)

        self.fixed_sess_start = QSpinBox()
        self.fixed_sess_start.setRange(1, 50)
        self.fixed_sess_start.setValue(4)
        self.fixed_sess_start.setMaximumWidth(90)
        self.fixed_sess_start.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.fixed_sess_start.valueChanged.connect(self.update_preview)

        self.fixed_sess_len = QSpinBox()
        self.fixed_sess_len.setRange(1, 50)
        self.fixed_sess_len.setValue(1)
        self.fixed_sess_len.setMaximumWidth(90)
        self.fixed_sess_len.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.fixed_sess_len.valueChanged.connect(self.update_preview)

        fixed_grid = self._fixed_position_widget()
        layout_fixed.addWidget(
            fixed_grid,
            0,
            0,
            1,
            3,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )

        self.settings_stack.addWidget(page_fixed)

        config_layout.addWidget(self.settings_stack)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group, 0, Qt.AlignmentFlag.AlignLeft)

        # 2. Preview Table
        preview_label = QLabel("Preview")
        preview_label.setObjectName("SmartParserSectionTitle")
        layout.addWidget(preview_label)
        self.table = QTableWidget()
        self.table.setObjectName("SmartParserPreviewTable")
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            ["File", "Subject", "Session"],
        )
        self.table.setMinimumHeight(260)
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        vertical_header = self.table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        layout.addWidget(self.table, stretch=1)

        # 3. Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        self.apply_btn = QPushButton("Apply metadata")
        self.apply_btn.setObjectName("SmartParserApplyButton")
        self.apply_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SmartParserSecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.apply_btn)
        layout.addLayout(btn_layout)

        self.toggle_mode()  # Init visibility

    @staticmethod
    def _parser_grid_layout(parent: QWidget) -> QGridLayout:
        layout = QGridLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(5)
        layout.setVerticalSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, _PARSER_SETTINGS_LABEL_WIDTH)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)
        return layout

    @staticmethod
    def _inline_field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SmartParserInlineFieldLabel")
        return label

    @staticmethod
    def _configure_mode_radio(radio: QRadioButton) -> None:
        radio.setObjectName("SmartParserModeRadio")
        radio.setFixedWidth(_PARSER_MODE_WIDTH)

    @staticmethod
    def _add_settings_row(
        layout: QGridLayout,
        row: int,
        label_text: str,
        field: QWidget,
    ) -> None:
        label = QLabel(label_text)
        label.setObjectName("SmartParserSettingsLabel")
        label.setFixedWidth(_PARSER_SETTINGS_LABEL_WIDTH)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(label, row, 0)
        layout.addWidget(field, row, 1, 1, 2, Qt.AlignmentFlag.AlignLeft)

    @staticmethod
    def _folder_example_widget() -> QFrame:
        frame = QFrame()
        frame.setObjectName("SmartParserFolderExample")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for text, object_name in (
            (".../", "SmartParserFolderMuted"),
            ("Subject01", "SmartParserFolderChip"),
            ("/", "SmartParserFolderMuted"),
            ("Session02", "SmartParserFolderChip"),
            ("/file.gdf", "SmartParserFolderMuted"),
        ):
            label = QLabel(text)
            label.setObjectName(object_name)
            layout.addWidget(label)
        layout.addStretch()
        return frame

    def _fixed_position_widget(self) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(7)
        layout.setColumnMinimumWidth(0, 86)
        layout.setColumnMinimumWidth(1, 72)
        layout.setColumnMinimumWidth(2, 72)

        for column, text in enumerate(("Field", "Start", "Length")):
            label = QLabel(text)
            label.setObjectName("SmartParserFixedHeader")
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            layout.addWidget(label, 0, column)

        rows = (
            ("Subject", self.fixed_sub_start, self.fixed_sub_len),
            ("Session", self.fixed_sess_start, self.fixed_sess_len),
        )
        for row, (name, start_widget, length_widget) in enumerate(
            rows,
            start=1,
        ):
            field_label = QLabel(name)
            field_label.setObjectName("SmartParserFixedField")
            field_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            start_widget.setFixedWidth(72)
            length_widget.setFixedWidth(72)
            layout.addWidget(field_label, row, 0)
            layout.addWidget(start_widget, row, 1)
            layout.addWidget(length_widget, row, 2)

        layout.setColumnStretch(3, 1)
        return widget

    def toggle_mode(self):
        """Switch the settings stack page based on the selected parsing mode."""
        if not self.mode_group or not self.settings_stack:
            return

        if self.radio_split and self.radio_split.isChecked():
            self.settings_stack.setCurrentIndex(0)
        elif self.radio_regex and self.radio_regex.isChecked():
            self.settings_stack.setCurrentIndex(1)
        elif self.radio_folder and self.radio_folder.isChecked():
            self.settings_stack.setCurrentIndex(2)
        elif self.radio_fixed and self.radio_fixed.isChecked():
            self.settings_stack.setCurrentIndex(3)

        self.update_preview()

    def on_regex_preset_changed(self, index):
        """Populate the regex input with a preset pattern.

        Args:
            index: Index of the selected preset in the combo box.

        """
        if not self.regex_input:
            return

        if index == 1:  # Subject_Session
            self.regex_input.setText(r"([^_]+)_([^_]+)")
        elif index == 2:  # BIDS
            self.regex_input.setText(r"sub-([^_]+)_ses-([^_]+)")

    def update_preview(self):
        """Re-parse all filenames and refresh the preview table."""
        if not self.table or not self.split_sep_combo:
            return

        self.table.setRowCount(len(self.filenames))
        self.parsed_data = {}

        sep_map = {0: "_", 1: "-", 2: " ", 3: "."}
        sep = sep_map.get(self.split_sep_combo.currentIndex(), "_")

        if self.radio_regex and self.radio_regex.isChecked() and self.regex_input:
            try:
                re.compile(self.regex_input.text())
            except re.error:
                logger.debug("Invalid regex pattern: %s", self.regex_input.text())

        for row, filepath in enumerate(self.filenames):
            filename = os.path.basename(filepath)

            self.table.setItem(row, 0, QTableWidgetItem(filename))

            sub = "-"
            sess = "-"

            # Ensure widgets are valid before accessing .value() / .text()
            if self.radio_split and self.radio_split.isChecked():
                if self.split_sub_idx and self.split_sess_idx:
                    sub, sess = FilenameParser.parse_by_split(
                        filename,
                        sep,
                        self.split_sub_idx.value(),
                        self.split_sess_idx.value(),
                    )

            elif self.radio_regex and self.radio_regex.isChecked():
                if self.regex_input and self.regex_sub_idx and self.regex_sess_idx:
                    sub, sess = FilenameParser.parse_by_regex(
                        filename,
                        self.regex_input.text(),
                        self.regex_sub_idx.value(),
                        self.regex_sess_idx.value(),
                    )

            elif self.radio_folder and self.radio_folder.isChecked():
                sub, sess = FilenameParser.parse_by_folder(filepath)

            elif (
                self.radio_fixed
                and self.radio_fixed.isChecked()
                and self.fixed_sub_start
                and self.fixed_sub_len
                and self.fixed_sess_start
                and self.fixed_sess_len
            ):
                sub, sess = FilenameParser.parse_by_fixed_position(
                    filename,
                    self.fixed_sub_start.value(),
                    self.fixed_sub_len.value(),
                    self.fixed_sess_start.value(),
                    self.fixed_sess_len.value(),
                )

            # Update Table
            sub_item = QTableWidgetItem(sub)
            sess_item = QTableWidgetItem(sess)

            # Highlight if found
            if sub != "-":
                sub_item.setBackground(QColor("#1f5e3a"))
                sub_item.setForeground(QColor("#ffffff"))
            if sess != "-":
                sess_item.setBackground(QColor("#214c7a"))
                sess_item.setForeground(QColor("#ffffff"))

            self.table.setItem(row, 1, sub_item)
            self.table.setItem(row, 2, sess_item)

            if sub != "-" or sess != "-":
                self.parsed_data[filepath] = (sub, sess)

    def get_result(self):
        """Return the parsed metadata mapping.

        Returns:
            Dictionary mapping file paths to ``(subject, session)`` tuples.

        """
        return self.parsed_data

    @staticmethod
    def _style_sheet() -> str:
        return f"""
            QDialog#SmartParserDialog {{
                background-color: {Theme.BACKGROUND_DARK};
                color: #e8e8e8;
                font-family: 'Segoe UI', sans-serif;
            }}
            QFrame#SmartParserHeader {{
                background-color: transparent;
                border: none;
            }}
            QLabel#SmartParserTitle {{
                color: #ffffff;
                font-size: 18px;
                font-weight: 700;
            }}
            QLabel#SmartParserSubtitle {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 12px;
            }}
            QLabel#SmartParserSectionTitle {{
                color: #e8e8e8;
                font-size: 14px;
                font-weight: 700;
            }}
            QGroupBox#SmartParserMethodGroup {{
                background-color: transparent;
                border: 1px solid #323232;
                border-radius: 4px;
                margin-top: 10px;
                color: #e8e8e8;
                font-weight: 600;
            }}
            QGroupBox#SmartParserMethodGroup::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                left: 7px;
                color: #e8e8e8;
                background-color: {Theme.BACKGROUND_DARK};
            }}
            QRadioButton {{
                color: #e8e8e8;
                background-color: transparent;
                border: none;
                spacing: 7px;
            }}
            QRadioButton:checked {{
                color: #ffffff;
                font-weight: 600;
            }}
            QRadioButton::indicator {{
                width: 13px;
                height: 13px;
                border-radius: 7px;
                border: 1px solid #8a8a8a;
                background-color: {Theme.BACKGROUND_DARK};
            }}
            QRadioButton::indicator:hover {{
                border-color: {Theme.BLUE_FOCUS_BORDER};
            }}
            QRadioButton::indicator:checked {{
                background-color: {Theme.BLUE_PRIMARY};
                border: 2px solid #9bd8ff;
            }}
            QLabel {{
                color: #e8e8e8;
                background-color: transparent;
                border: none;
            }}
            QLabel#SmartParserSettingsLabel,
            QLabel#SmartParserInlineFieldLabel,
            QLabel#SmartParserFixedHeader,
            QLabel#SmartParserFixedField,
            QLabel#SmartParserFolderHint,
            QLabel#SmartParserFolderMuted {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 12px;
            }}
            QLabel#SmartParserFixedHeader {{
                color: #9f9f9f;
                font-weight: 600;
            }}
            QLabel#SmartParserFixedField {{
                color: #e0e0e0;
            }}
            QLabel#SmartParserSettingsLabel {{
                color: #e0e0e0;
            }}
            QFrame#SmartParserFolderExample {{
                background-color: transparent;
                border: none;
            }}
            QLabel#SmartParserFolderChip {{
                color: #eeeeee;
                background-color: transparent;
                border: none;
                padding: 0;
                font-size: 12px;
                font-weight: 600;
            }}
            QComboBox,
            QLineEdit,
            QSpinBox {{
                background-color: {Theme.BACKGROUND_MID};
                color: #e8e8e8;
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                padding: 4px 6px;
                min-height: 20px;
            }}
            QComboBox:hover,
            QLineEdit:hover,
            QSpinBox:hover {{
                border-color: {Theme.ACCENT_PRIMARY};
            }}
            QTableWidget#SmartParserPreviewTable {{
                background-color: {Theme.BACKGROUND_DARK};
                alternate-background-color: #252526;
                color: #e8e8e8;
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                gridline-color: #303030;
                selection-background-color: {Theme.BLUE_PRESSED};
            }}
            QTableWidget#SmartParserPreviewTable::item {{
                padding: 3px 6px;
            }}
            QHeaderView::section {{
                background-color: #2a2a2a;
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                padding: 5px 6px;
                font-weight: 500;
            }}
            QTableCornerButton::section {{
                background-color: #2a2a2a;
                border: 1px solid {Theme.BACKGROUND_LIGHT};
            }}
            QPushButton#SmartParserApplyButton {{
                background-color: {Theme.BLUE_PRIMARY};
                color: #e8e8e8;
                border: 1px solid {Theme.BLUE_HOVER};
                border-radius: 4px;
                padding: 6px 14px;
                min-height: 20px;
                font-weight: 600;
            }}
            QPushButton#SmartParserApplyButton:hover {{
                background-color: {Theme.BLUE_HOVER};
            }}
            QPushButton#SmartParserApplyButton:pressed {{
                background-color: {Theme.BLUE_PRESSED};
            }}
            QPushButton#SmartParserSecondaryButton {{
                background-color: {Theme.BACKGROUND_MID};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                padding: 6px 12px;
                min-height: 20px;
            }}
            QPushButton#SmartParserSecondaryButton:hover {{
                color: #e8e8e8;
                border-color: {Theme.ACCENT_PRIMARY};
                background-color: {Theme.BACKGROUND_LIGHT};
            }}
        """

    def accept(self):
        """Save current settings and accept the dialog."""
        self.save_settings()  # Save settings on apply
        super().accept()

    def save_settings(self):
        """Persist current parsing settings to QSettings."""
        settings = QSettings("XBrainLab", "SmartParser")

        # Save Mode
        if self.mode_group:
            settings.setValue("mode", self.mode_group.checkedId())

        # Save Split Settings
        if self.split_sep_combo:
            settings.setValue("split_sep", self.split_sep_combo.currentIndex())
        if self.split_sub_idx:
            settings.setValue("split_sub_idx", self.split_sub_idx.value())
        if self.split_sess_idx:
            settings.setValue("split_sess_idx", self.split_sess_idx.value())

        # Save Regex Settings
        if self.regex_preset_combo:
            settings.setValue("regex_preset", self.regex_preset_combo.currentIndex())
        if self.regex_input:
            settings.setValue("regex_pattern", self.regex_input.text())
        if self.regex_sub_idx:
            settings.setValue("regex_sub_idx", self.regex_sub_idx.value())
        if self.regex_sess_idx:
            settings.setValue("regex_sess_idx", self.regex_sess_idx.value())

        # Save Fixed Settings
        if self.fixed_sub_start:
            settings.setValue("fixed_sub_start", self.fixed_sub_start.value())
        if self.fixed_sub_len:
            settings.setValue("fixed_sub_len", self.fixed_sub_len.value())
        if self.fixed_sess_start:
            settings.setValue("fixed_sess_start", self.fixed_sess_start.value())
        if self.fixed_sess_len:
            settings.setValue("fixed_sess_len", self.fixed_sess_len.value())

    def load_settings(self):
        """Restore parsing settings from QSettings."""
        settings = QSettings("XBrainLab", "SmartParser")

        # Load Mode
        mode_id = settings.value("mode", 0, type=int)
        if self.mode_group:
            button = self.mode_group.button(mode_id)
            if button:
                button.setChecked(True)

        # Load Split Settings
        if self.split_sep_combo:
            self.split_sep_combo.setCurrentIndex(
                settings.value("split_sep", 0, type=int),
            )
        if self.split_sub_idx:
            self.split_sub_idx.setValue(settings.value("split_sub_idx", 1, type=int))
        if self.split_sess_idx:
            self.split_sess_idx.setValue(settings.value("split_sess_idx", 2, type=int))

        # Load Regex Settings
        if self.regex_preset_combo:
            self.regex_preset_combo.setCurrentIndex(
                settings.value("regex_preset", 0, type=int),
            )
        if self.regex_input:
            self.regex_input.setText(settings.value("regex_pattern", "", type=str))
        if self.regex_sub_idx:
            self.regex_sub_idx.setValue(settings.value("regex_sub_idx", 1, type=int))
        if self.regex_sess_idx:
            self.regex_sess_idx.setValue(settings.value("regex_sess_idx", 2, type=int))

        # Load Fixed Settings
        if self.fixed_sub_start:
            self.fixed_sub_start.setValue(
                settings.value("fixed_sub_start", 1, type=int),
            )
        if self.fixed_sub_len:
            self.fixed_sub_len.setValue(settings.value("fixed_sub_len", 3, type=int))
        if self.fixed_sess_start:
            self.fixed_sess_start.setValue(
                settings.value("fixed_sess_start", 4, type=int),
            )
        if self.fixed_sess_len:
            self.fixed_sess_len.setValue(settings.value("fixed_sess_len", 1, type=int))
