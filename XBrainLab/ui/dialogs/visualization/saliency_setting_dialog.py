import contextlib
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QGroupBox,
    QHeaderView,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


class SaliencySettingDialog(BaseDialog):
    def __init__(self, parent, saliency_params=None):
        self.saliency_params = saliency_params
        self.algo_map: dict[str, list[str] | None] = {}
        self.params_tables: dict[str, QTableWidget] = {}

        super().__init__(parent, title="Saliency Setting")
        self.resize(500, 600)

        self.check_init_data()
        if self.algo_map:
            self.display_data()

    def check_init_data(self):
        support_saliency_methods = ["SmoothGrad", "SmoothGrad_Squared", "VarGrad"]
        for method in support_saliency_methods:
            if method.startswith("Gradient"):
                self.algo_map[method] = None
            elif method in ["SmoothGrad", "SmoothGrad_Squared", "VarGrad"]:
                self.algo_map[method] = [
                    "nt_samples",
                    "nt_samples_batch_size",
                    "stdevs",
                ]

    def init_ui(self):
        layout = QVBoxLayout(self)

        if not self.algo_map:
            self.check_init_data()

        for method in self.algo_map:
            group = QGroupBox(f"{method} Parameters")
            group_layout = QVBoxLayout(group)

            table = QTableWidget()
            table.setColumnCount(2)
            table.setHorizontalHeaderLabels(["Parameter", "Value"])
            header = table.horizontalHeader()
            if header is not None:
                header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

            self.params_tables[method] = table
            group_layout.addWidget(table)

            layout.addWidget(group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def display_data(self):
        for algo, params_list in self.algo_map.items():
            table = self.params_tables.get(algo)
            if not table:
                continue

            table.setRowCount(0)

            if not params_list:
                continue

            table.setRowCount(len(params_list))

            for row, param in enumerate(params_list):
                # Default values
                value = ""
                if self.saliency_params and algo in self.saliency_params:
                    value = str(self.saliency_params[algo].get(param, ""))
                elif param == "nt_samples":
                    value = "5"
                elif param == "nt_samples_batch_size":
                    value = "None"
                elif param == "stdevs":
                    value = "1.0"

                # Parameter Name (Read-only)
                item_param = QTableWidgetItem(param)
                item_param.setFlags(item_param.flags() ^ Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, 0, item_param)

                # Value (Editable)
                item_val = QTableWidgetItem(str(value))
                table.setItem(row, 1, item_val)

    def accept(self):
        new_params: dict[str, dict] = {}
        try:
            for algo, table in self.params_tables.items():
                new_params[algo] = {}
                for row in range(table.rowCount()):
                    item0 = table.item(row, 0)
                    item1 = table.item(row, 1)
                    if not item0 or not item1:
                        continue
                    param = item0.text()
                    value_text = item1.text()

                    # Validation and Conversion
                    value: Any = value_text
                    if param.startswith("nt_samples"):
                        if value_text == "None":
                            value = None
                        elif value_text.isdigit():
                            value = int(value_text)
                        else:
                            raise ValueError(  # noqa: TRY301
                                f"Invalid value for {param}: {value_text}"
                            )
                    elif value_text == "None":
                        value = None
                    elif value_text == "True":
                        value = True
                    elif value_text == "False":
                        value = False
                    elif value_text:
                        with contextlib.suppress(ValueError):
                            value = float(value_text)

                    new_params[algo][param] = value

            self.saliency_params = new_params
            super().accept()

        except Exception as e:
            QMessageBox.warning(self, "Validation Error", str(e))

    def get_result(self):
        return self.saliency_params
