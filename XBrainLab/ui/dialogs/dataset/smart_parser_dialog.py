import contextlib
import os
import re

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.utils.filename_parser import FilenameParser
from XBrainLab.ui.core.base_dialog import BaseDialog


class SmartParserDialog(BaseDialog):
    """
    Dialog for configuring automated metadata extraction from filenames.
    Supports split, regex, folder structure, and fixed position strategies.
    """

    def __init__(self, filenames: list[str], parent=None):
        self.filenames = filenames
        self.parsed_data: dict[
            str, tuple[str, str]
        ] = {}  # filename -> (subject, session)

        # UI Elements
        # UI Elements
        self.mode_group: QButtonGroup | None = None
        self.radio_split: QRadioButton | None = None
        self.radio_regex: QRadioButton | None = None
        self.radio_folder: QRadioButton | None = None
        self.radio_fixed: QRadioButton | None = None
        self.settings_stack: QStackedWidget | None = None
        self.table: QTableWidget | None = None
        self.apply_btn: QPushButton | None = None
        self.cancel_btn: QPushButton | None = None

        # Settings Widgets
        self.split_sep_combo: QComboBox | None = None
        self.split_sub_idx: QSpinBox | None = None
        self.split_sess_idx: QSpinBox | None = None
        self.regex_preset_combo: QComboBox | None = None
        self.regex_input: QLineEdit | None = None
        self.regex_sub_idx: QSpinBox | None = None
        self.regex_sess_idx: QSpinBox | None = None
        self.fixed_sub_start: QSpinBox | None = None
        self.fixed_sub_len: QSpinBox | None = None
        self.fixed_sess_start: QSpinBox | None = None
        self.fixed_sess_len: QSpinBox | None = None

        super().__init__(parent, title="Smart Metadata Parser")
        self.resize(1000, 700)

        # Load previous settings after UI init
        self.load_settings()
        self.update_preview()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Configuration Area
        config_group = QGroupBox("Parsing Method")
        config_layout = QVBoxLayout()

        # Mode Selection
        mode_layout = QHBoxLayout()
        self.mode_group = QButtonGroup(self)

        self.radio_split = QRadioButton("Simple Split (Recommended)")
        self.radio_regex = QRadioButton("Advanced Regex")
        self.radio_folder = QRadioButton("Folder Structure")
        self.radio_fixed = QRadioButton("Fixed Position (No Separator)")

        self.mode_group.addButton(self.radio_split, 0)
        self.mode_group.addButton(self.radio_regex, 1)
        self.mode_group.addButton(self.radio_folder, 2)
        self.mode_group.addButton(self.radio_fixed, 3)

        self.radio_split.setChecked(True)
        self.radio_split.toggled.connect(self.toggle_mode)
        self.radio_regex.toggled.connect(self.toggle_mode)
        self.radio_folder.toggled.connect(self.toggle_mode)
        self.radio_fixed.toggled.connect(self.toggle_mode)

        mode_layout.addWidget(self.radio_split)
        mode_layout.addWidget(self.radio_fixed)
        mode_layout.addWidget(self.radio_regex)
        mode_layout.addWidget(self.radio_folder)
        mode_layout.addStretch()
        config_layout.addLayout(mode_layout)

        # Settings Stack
        self.settings_stack = QStackedWidget()

        # --- Page 0: Split Settings ---
        page_split = QWidget()
        layout_split = QFormLayout(page_split)

        self.split_sep_combo = QComboBox()
        self.split_sep_combo.addItems(
            ["Underscore (_)", "Hyphen (-)", "Space ( )", "Dot (.)"]
        )
        self.split_sep_combo.currentIndexChanged.connect(self.update_preview)

        self.split_sub_idx = QSpinBox()
        self.split_sub_idx.setRange(1, 10)
        self.split_sub_idx.setValue(1)
        self.split_sub_idx.setPrefix("Part ")
        self.split_sub_idx.valueChanged.connect(self.update_preview)

        self.split_sess_idx = QSpinBox()
        self.split_sess_idx.setRange(1, 10)
        self.split_sess_idx.setValue(2)
        self.split_sess_idx.setPrefix("Part ")
        self.split_sess_idx.valueChanged.connect(self.update_preview)

        layout_split.addRow("Separator:", self.split_sep_combo)
        layout_split.addRow("Subject is:", self.split_sub_idx)
        layout_split.addRow("Session is:", self.split_sess_idx)

        self.settings_stack.addWidget(page_split)

        # --- Page 1: Regex Settings ---
        page_regex = QWidget()
        layout_regex = QFormLayout(page_regex)

        self.regex_preset_combo = QComboBox()
        self.regex_preset_combo.addItems(
            ["Custom", "Subject_Session (e.g. Sub01_Ses01)", "BIDS (sub-01_ses-01)"]
        )
        self.regex_preset_combo.currentIndexChanged.connect(
            self.on_regex_preset_changed
        )

        self.regex_input = QLineEdit()
        self.regex_input.setPlaceholderText(r"(.*)_(.*)")
        self.regex_input.textChanged.connect(self.update_preview)

        self.regex_sub_idx = QSpinBox()
        self.regex_sub_idx.setRange(1, 10)
        self.regex_sub_idx.setPrefix("Group ")
        self.regex_sub_idx.valueChanged.connect(self.update_preview)

        self.regex_sess_idx = QSpinBox()
        self.regex_sess_idx.setRange(1, 10)
        self.regex_sess_idx.setValue(2)
        self.regex_sess_idx.setPrefix("Group ")
        self.regex_sess_idx.valueChanged.connect(self.update_preview)

        layout_regex.addRow("Preset:", self.regex_preset_combo)
        layout_regex.addRow("Regex Pattern:", self.regex_input)
        layout_regex.addRow("Subject Group:", self.regex_sub_idx)
        layout_regex.addRow("Session Group:", self.regex_sess_idx)

        self.settings_stack.addWidget(page_regex)

        # --- Page 2: Folder Settings ---
        page_folder = QWidget()
        layout_folder = QVBoxLayout(page_folder)
        layout_folder.addWidget(
            QLabel("Automatically extracts metadata from parent folder names.")
        )
        layout_folder.addWidget(
            QLabel("Structure assumed: .../Subject/Session/filename.gdf")
        )
        layout_folder.addStretch()

        self.settings_stack.addWidget(page_folder)

        # --- Page 3: Fixed Position Settings ---
        page_fixed = QWidget()
        layout_fixed = QFormLayout(page_fixed)

        self.fixed_sub_start = QSpinBox()
        self.fixed_sub_start.setRange(1, 50)
        self.fixed_sub_start.setValue(1)
        self.fixed_sub_start.valueChanged.connect(self.update_preview)

        self.fixed_sub_len = QSpinBox()
        self.fixed_sub_len.setRange(1, 50)
        self.fixed_sub_len.setValue(3)
        self.fixed_sub_len.valueChanged.connect(self.update_preview)

        self.fixed_sess_start = QSpinBox()
        self.fixed_sess_start.setRange(1, 50)
        self.fixed_sess_start.setValue(4)
        self.fixed_sess_start.valueChanged.connect(self.update_preview)

        self.fixed_sess_len = QSpinBox()
        self.fixed_sess_len.setRange(1, 50)
        self.fixed_sess_len.setValue(1)
        self.fixed_sess_len.valueChanged.connect(self.update_preview)

        sub_layout = QHBoxLayout()
        sub_layout.addWidget(QLabel("Start:"))
        sub_layout.addWidget(self.fixed_sub_start)
        sub_layout.addWidget(QLabel("Length:"))
        sub_layout.addWidget(self.fixed_sub_len)

        sess_layout = QHBoxLayout()
        sess_layout.addWidget(QLabel("Start:"))
        sess_layout.addWidget(self.fixed_sess_start)
        sess_layout.addWidget(QLabel("Length:"))
        sess_layout.addWidget(self.fixed_sess_len)

        layout_fixed.addRow("Subject (e.g. 'A01'):", sub_layout)
        layout_fixed.addRow("Session (e.g. 'T'):", sess_layout)

        self.settings_stack.addWidget(page_fixed)

        config_layout.addWidget(self.settings_stack)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # 2. Preview Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            ["Filename", "Extracted Subject", "Extracted Session"]
        )
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # 3. Buttons
        btn_layout = QHBoxLayout()
        self.apply_btn = QPushButton("Apply to Dataset")
        self.apply_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.apply_btn)
        layout.addLayout(btn_layout)

        self.toggle_mode()  # Init visibility

    def toggle_mode(self):
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
        if not self.regex_input:
            return

        if index == 1:  # Subject_Session
            self.regex_input.setText(r"([^_]+)_([^_]+)")
        elif index == 2:  # BIDS
            self.regex_input.setText(r"sub-([^_]+)_ses-([^_]+)")

    def update_preview(self):
        if not self.table or not self.split_sep_combo:
            return

        self.table.setRowCount(len(self.filenames))
        self.parsed_data = {}

        sep_map = {0: "_", 1: "-", 2: " ", 3: "."}
        sep = sep_map.get(self.split_sep_combo.currentIndex(), "_")

        if self.radio_regex and self.radio_regex.isChecked() and self.regex_input:
            with contextlib.suppress(Exception):
                re.compile(self.regex_input.text())

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
                sub_item.setBackground(Qt.GlobalColor.darkGreen)
                sub_item.setForeground(Qt.GlobalColor.white)
            if sess != "-":
                sess_item.setBackground(Qt.GlobalColor.darkBlue)
                sess_item.setForeground(Qt.GlobalColor.white)

            self.table.setItem(row, 1, sub_item)
            self.table.setItem(row, 2, sess_item)

            if sub != "-" or sess != "-":
                self.parsed_data[filepath] = (sub, sess)

    def get_result(self):
        return self.parsed_data

    def accept(self):
        self.save_settings()  # Save settings on apply
        super().accept()

    def save_settings(self):
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
                settings.value("split_sep", 0, type=int)
            )
        if self.split_sub_idx:
            self.split_sub_idx.setValue(settings.value("split_sub_idx", 1, type=int))
        if self.split_sess_idx:
            self.split_sess_idx.setValue(settings.value("split_sess_idx", 2, type=int))

        # Load Regex Settings
        if self.regex_preset_combo:
            self.regex_preset_combo.setCurrentIndex(
                settings.value("regex_preset", 0, type=int)
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
                settings.value("fixed_sub_start", 1, type=int)
            )
        if self.fixed_sub_len:
            self.fixed_sub_len.setValue(settings.value("fixed_sub_len", 3, type=int))
        if self.fixed_sess_start:
            self.fixed_sess_start.setValue(
                settings.value("fixed_sess_start", 4, type=int)
            )
        if self.fixed_sess_len:
            self.fixed_sess_len.setValue(settings.value("fixed_sess_len", 1, type=int))
