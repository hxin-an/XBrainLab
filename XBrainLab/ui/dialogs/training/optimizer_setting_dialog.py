"""Optimizer configuration dialog for selecting and parameterizing optimizers.

Dynamically loads available PyTorch optimizers and their parameters,
allowing users to configure training optimization settings.
"""

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.training.utils import (
    get_optimizer_classes,
    get_optimizer_params,
    instantiate_optimizer,
)
from XBrainLab.ui.core.base_dialog import BaseDialog


class OptimizerSettingDialog(BaseDialog):
    """Dialog for configuring the training optimizer (e.g., Adam, SGD).

    Dynamically loads optimizer classes and generates parameter tables
    with validation on acceptance.

    Attributes:
        optim: Selected optimizer class after acceptance.
        optim_params: Dictionary of optimizer parameters.
        algo_map: Dictionary mapping optimizer names to classes.
        algo_combo: QComboBox for selecting the optimizer algorithm.
        params_table: QTableWidget displaying configurable parameters.
    """

    def __init__(self, parent):
        self.optim = None
        self.optim_params = None

        self.algo_map = get_optimizer_classes()

        # UI
        self.algo_combo = None
        self.params_table = None

        super().__init__(parent, title="Optimizer Setting")
        self.resize(400, 500)

        # Init with first algo
        if self.algo_map and self.algo_combo:
            self.on_algo_select(next(iter(self.algo_map.keys())))

    def init_ui(self):
        """Initialize dialog UI: algorithm combo, parameter table, buttons."""
        layout = QVBoxLayout(self)

        # Algorithm Selection
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Algorithm"))
        self.algo_combo = QComboBox()
        self.algo_combo.addItems(list(self.algo_map.keys()))
        self.algo_combo.currentTextChanged.connect(self.on_algo_select)
        top_layout.addWidget(self.algo_combo)
        layout.addLayout(top_layout)

        # Parameters Table
        group = QGroupBox("Parameters")
        group_layout = QVBoxLayout(group)
        self.params_table = QTableWidget()
        self.params_table.setColumnCount(2)
        self.params_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        header = self.params_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        group_layout.addWidget(self.params_table)
        layout.addWidget(group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def on_algo_select(self, algo_name):
        """Populate the parameter table for the selected optimizer.

        Args:
            algo_name: Name of the selected optimizer algorithm.
        """
        if not self.params_table:
            return
        target = self.algo_map[algo_name]
        self.params_table.setRowCount(0)

        if target:
            rows = get_optimizer_params(target)

            self.params_table.setRowCount(len(rows))
            for i, (param, val) in enumerate(rows):
                item_param = QTableWidgetItem(param)
                item_param.setFlags(item_param.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.params_table.setItem(i, 0, item_param)
                self.params_table.setItem(i, 1, QTableWidgetItem(val))

    def accept(self):
        """Parse and validate optimizer parameters, then accept the dialog.

        Raises:
            QMessageBox: Warning if parameter validation or test
                instantiation fails.
        """
        if not self.algo_combo or not self.params_table:
            return
        optim_params = {}
        target = self.algo_map[self.algo_combo.currentText()]

        try:
            for row in range(self.params_table.rowCount()):
                item0 = self.params_table.item(row, 0)
                param = item0.text() if item0 else ""

                item1 = self.params_table.item(row, 1)
                value_text = item1.text() if item1 else ""

                value: Any = None
                if value_text:
                    if len(value_text.split()) > 1:
                        value = [float(v) for v in value_text.split()]
                    elif value_text == "True":
                        value = True
                    elif value_text == "False":
                        value = False
                    else:
                        value = float(value_text)
                    optim_params[param] = value

            # Test instantiation
            instantiate_optimizer(target, optim_params)

            self.optim_params = optim_params
            self.optim = target
            super().accept()

        except Exception as e:
            QMessageBox.warning(self, "Validation Error", f"Invalid parameter: {e}")

    def get_result(self):
        """Return the selected optimizer class and parameters.

        Returns:
            Tuple of (optimizer_class, optimizer_params_dict).
        """
        return self.optim, self.optim_params
