"""Model selection dialog for choosing deep learning architectures.

Dynamically generates parameter inputs based on the selected model class
signature and supports loading pretrained weights.
"""

import inspect
import os
from typing import Any

from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend import model_base
from XBrainLab.backend.training import ModelHolder
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

ARG_DICT_SKIP_SET = {"self", "n_classes", "channels", "samples", "sfreq"}


class ModelSelectionDialog(BaseDialog):
    """Dialog for selecting a deep learning model architecture.

    Dynamically generates parameter inputs based on the model class
    constructor signature, with support for loading pretrained weights.

    Attributes:
        controller: Application controller for data access.
        pretrained_weight_path: Path to pretrained weight file, or None.
        model_holder: Configured ModelHolder after acceptance.
        model_combo: QComboBox for selecting the model architecture.
        params_table: QTableWidget displaying model-specific parameters.
        model_map: Dictionary mapping model names to model classes.
        model_list: List of available model class names.

    """

    def __init__(self, parent, controller):
        self.controller = controller

        self.pretrained_weight_path = None
        self.model_holder = None

        # UI Elements
        self.model_combo = None
        self.params_table = None
        self.params_group = None
        self.weight_label = None
        self.weight_btn = None

        # Fetch model list
        self.model_map = {
            m[0]: m[1] for m in inspect.getmembers(model_base, inspect.isclass)
        }
        self.model_list = list(self.model_map.keys())

        super().__init__(parent, title="Model Selection")
        self.resize(640, 520)

        # Init with first model
        if self.model_list:
            self.on_model_select(self.model_list[0])

    def init_ui(self):
        """Initialize the dialog UI with model combo, parameter table, and buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)

        # Model Selection
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(self.model_list)
        self.model_combo.currentTextChanged.connect(self.on_model_select)
        top_layout.addWidget(self.model_combo)
        layout.addLayout(top_layout)

        # Parameters Table
        self.params_group = QGroupBox("Model Parameters")
        group_layout = QVBoxLayout(self.params_group)
        self.params_table = QTableWidget()
        self.params_table.setColumnCount(2)
        self.params_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.params_table.setAlternatingRowColors(True)
        self.params_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.params_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.params_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.params_table.setMinimumHeight(180)
        self.params_table.setStyleSheet(Stylesheets.METRICS_TABLE)
        palette = self.params_table.palette()
        for group in (
            QPalette.ColorGroup.Active,
            QPalette.ColorGroup.Inactive,
            QPalette.ColorGroup.Disabled,
        ):
            palette.setColor(
                group,
                QPalette.ColorRole.Base,
                QColor(Theme.METRICS_TABLE_BG),
            )
            palette.setColor(
                group,
                QPalette.ColorRole.AlternateBase,
                QColor(Theme.METRICS_TABLE_ALT_BG),
            )
            palette.setColor(
                group,
                QPalette.ColorRole.Text,
                QColor(Theme.TEXT_PRIMARY),
            )
            palette.setColor(
                group,
                QPalette.ColorRole.Highlight,
                QColor(Theme.BLUE_PRESSED),
            )
            palette.setColor(
                group,
                QPalette.ColorRole.HighlightedText,
                QColor(Theme.TEXT_PRIMARY),
            )
        self.params_table.setPalette(palette)
        header = self.params_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        vertical_header = self.params_table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        group_layout.addWidget(self.params_table)
        layout.addWidget(self.params_group)

        # Pretrained Weight
        weight_layout = QHBoxLayout()
        weight_layout.addWidget(QLabel("Pretrained weight:"))
        self.weight_label = QLabel("")
        weight_layout.addWidget(self.weight_label)
        self.weight_btn = QPushButton("load")
        self.weight_btn.clicked.connect(self.load_pretrained_weight)
        weight_layout.addWidget(self.weight_btn)
        layout.addLayout(weight_layout)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def on_model_select(self, model_name):
        """Populate the parameter table based on the selected model.

        Args:
            model_name: Name of the selected model class.

        """
        if not self.params_table or not self.params_group:
            return

        target = self.model_map[model_name]
        self.params_table.setRowCount(0)

        if target:
            sigs = inspect.signature(target.__init__)
            params = sigs.parameters

            rows = []
            for param in params:
                if param in ARG_DICT_SKIP_SET:
                    continue

                default_val = ""
                if params[param].default != inspect._empty:
                    default_val = str(params[param].default)

                rows.append((param, default_val))

            self.params_table.setRowCount(len(rows))
            for i, (param, val) in enumerate(rows):
                item_param = QTableWidgetItem(param)
                item_param.setFlags(item_param.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.params_table.setItem(i, 0, item_param)
                self.params_table.setItem(i, 1, QTableWidgetItem(val))

            if not rows:
                self._show_no_editable_params()
            self._clear_params_table_selection()
            self.params_group.setVisible(True)

    def _show_no_editable_params(self) -> None:
        """Render an explicit empty state instead of hiding the parameter table."""
        if not self.params_table:
            return
        self.params_table.setRowCount(1)
        name_item = QTableWidgetItem("No editable parameters")
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        value_item = QTableWidgetItem("This model only uses data-derived settings.")
        value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.params_table.setItem(0, 0, name_item)
        self.params_table.setItem(0, 1, value_item)
        self._clear_params_table_selection()

    def _clear_params_table_selection(self) -> None:
        """Avoid a misleading initial selected row in the parameter table."""
        if not self.params_table:
            return
        self.params_table.clearSelection()
        self.params_table.setCurrentIndex(QModelIndex())
        selection_model = self.params_table.selectionModel()
        if selection_model is not None:
            selection_model.clear()

    def load_pretrained_weight(self):
        """Open a file dialog to load or clear pretrained model weights."""
        if not self.weight_label or not self.weight_btn:
            return

        if self.pretrained_weight_path:
            self.pretrained_weight_path = None
            self.weight_label.setText("")
            self.weight_btn.setText("load")
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Pretrained Weight",
            filter="Model Weights (*)",
        )
        if filepath:
            self.pretrained_weight_path = filepath
            self.weight_label.setText(os.path.basename(filepath))
            self.weight_btn.setText("clear")

    def accept(self):
        """Build the ModelHolder from current selections and accept.

        Raises:
            QMessageBox: Warning if parameter parsing fails.

        """
        if not self.model_combo or not self.params_table:
            return

        target_model = self.model_map[self.model_combo.currentText()]
        model_params_map = {}

        try:
            for row in range(self.params_table.rowCount()):
                item0 = self.params_table.item(row, 0)
                param = item0.text() if item0 else ""

                item1 = self.params_table.item(row, 1)
                value_text = item1.text() if item1 else ""

                value: Any = None

                # Simple type inference (could be improved)
                if value_text:
                    if value_text.isdigit():
                        value = int(value_text)
                    elif value_text.replace(".", "", 1).isdigit():
                        value = float(value_text)
                    elif value_text == "True":
                        value = True
                    elif value_text == "False":
                        value = False
                    else:
                        value = value_text
                    model_params_map[param] = value

            self.model_holder = ModelHolder(
                target_model,
                model_params_map,
                self.pretrained_weight_path,
            )
            super().accept()

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def get_result(self):
        """Return the configured ModelHolder.

        Returns:
            ModelHolder instance with selected model and parameters, or None.

        """
        return self.model_holder
