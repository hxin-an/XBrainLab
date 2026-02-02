import inspect
import os
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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

ARG_DICT_SKIP_SET = {"self", "n_classes", "channels", "samples", "sfreq"}


class ModelSelectionDialog(BaseDialog):
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
        self.resize(500, 600)

        # Init with first model
        if self.model_list:
            self.on_model_select(self.model_list[0])

    def init_ui(self):
        layout = QVBoxLayout(self)

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
        header = self.params_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
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
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def on_model_select(self, model_name):
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
                item_param.setFlags(item_param.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.params_table.setItem(i, 0, item_param)
                self.params_table.setItem(i, 1, QTableWidgetItem(val))

            self.params_group.setVisible(len(rows) > 0)

    def load_pretrained_weight(self):
        if not self.weight_label or not self.weight_btn:
            return

        if self.pretrained_weight_path:
            self.pretrained_weight_path = None
            self.weight_label.setText("")
            self.weight_btn.setText("load")
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Pretrained Weight", filter="Model Weights (*)"
        )
        if filepath:
            self.pretrained_weight_path = filepath
            self.weight_label.setText(os.path.basename(filepath))
            self.weight_btn.setText("clear")

    def accept(self):
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
                target_model, model_params_map, self.pretrained_weight_path
            )
            super().accept()

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def get_result(self):
        return self.model_holder
