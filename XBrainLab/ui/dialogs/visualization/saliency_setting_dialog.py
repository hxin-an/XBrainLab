"""Saliency method parameter configuration dialog.

Dynamically generates editable parameter tables for each supported
saliency method (e.g., SmoothGrad, VarGrad) based on backend definitions.
"""

import contextlib
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialogButtonBox,
    QGroupBox,
    QHeaderView,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.application.saliency_policy import (
    ADVANCED_SALIENCY_METHODS,
    DEFAULT_ADVANCED_SALIENCY_PARAMS,
    selected_saliency_methods_from_params,
)
from XBrainLab.backend.visualization import supported_saliency_methods
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import (
    configure_dark_table,
    dark_dialog_stylesheet,
    normalize_dialog_button_box,
)


def _raise_no_saliency_method_selected() -> None:
    raise ValueError("Select at least one saliency method.")


class SaliencySettingDialog(BaseDialog):
    """Dialog for configuring saliency method parameters.

    Dynamically generates a parameter table for each supported saliency
    method based on backend definitions, with validation on acceptance.

    Attributes:
        saliency_params: Dictionary mapping method names to parameter
            dictionaries.
        algo_map: Dictionary mapping method names to their parameter
            name lists (or None for no-parameter methods).
        params_tables: Dictionary mapping method names to QTableWidget
            instances.

    """

    def __init__(self, parent, saliency_params=None):
        self.saliency_params = saliency_params
        self.algo_map: dict[str, list[str] | None] = {}
        self.params_tables: dict[str, QTableWidget] = {}
        self.method_checks: dict[str, QCheckBox] = {}

        super().__init__(parent, title="Saliency Setting")
        self.resize(560, 520)
        self.setMinimumWidth(560)
        self.setStyleSheet(dark_dialog_stylesheet())

        self.check_init_data()
        if self.algo_map:
            self.display_data()

    def check_init_data(self):
        """Populate the algorithm map from backend saliency method definitions."""
        for method in supported_saliency_methods:
            self.algo_map[method] = list(DEFAULT_ADVANCED_SALIENCY_PARAMS)

    def init_ui(self):
        """Initialize the dialog UI with parameter tables for each method."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        if not self.algo_map:
            self.check_init_data()

        methods_group = QGroupBox("Compute methods")
        methods_layout = QVBoxLayout(methods_group)
        methods_layout.setContentsMargins(12, 10, 12, 10)
        methods_layout.setSpacing(6)
        selected_methods = selected_saliency_methods_from_params(
            self.saliency_params or {"methods": list(ADVANCED_SALIENCY_METHODS)}
        )
        if not selected_methods:
            selected_methods = set(ADVANCED_SALIENCY_METHODS)
        for method in self.algo_map:
            check = QCheckBox(method)
            check.setObjectName(f"SaliencyMethodCheck_{method}")
            check.setChecked(method in selected_methods)
            self.method_checks[method] = check
            methods_layout.addWidget(check)
        layout.addWidget(methods_group)

        for method in self.algo_map:
            group = QGroupBox(f"{method} Parameters")
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(12, 10, 12, 10)
            group_layout.setSpacing(8)

            table = QTableWidget()
            table.setColumnCount(2)
            table.setHorizontalHeaderLabels(["Parameter", "Value"])
            configure_dark_table(
                table,
                object_name=f"SaliencyParamsTable_{method}",
                no_selection=True,
            )
            header = table.horizontalHeader()
            if header is not None:
                header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setFixedHeight(126)

            self.params_tables[method] = table
            group_layout.addWidget(table)

            layout.addWidget(group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        normalize_dialog_button_box(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def display_data(self):
        """Populate parameter tables with default or previously saved values."""
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
            table.resizeRowsToContents()

    def accept(self):
        """Parse and validate all parameter values, then accept the dialog.

        Raises:
            QMessageBox: Warning if any parameter value is invalid.

        """
        new_params: dict[str, Any] = {}
        try:
            selected_methods = [
                method
                for method, check in self.method_checks.items()
                if check.isChecked()
            ]
            if not selected_methods:
                _raise_no_saliency_method_selected()

            new_params["methods"] = selected_methods
            new_params["profile"] = "advanced"
            for algo, table in self.params_tables.items():
                if algo not in selected_methods:
                    continue
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
                                f"Invalid value for {param}: {value_text}",
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
        """Return the configured saliency parameters.

        Returns:
            Dictionary mapping method names to parameter dictionaries.

        """
        return self.saliency_params
