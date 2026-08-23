"""Optimizer configuration dialog for selecting and parameterizing optimizers.

Dynamically loads available PyTorch optimizers and their parameters,
allowing users to configure training optimization settings.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.training.utils import (
    OptimizerParameterError,
    get_optimizer_classes,
    get_optimizer_params,
    instantiate_optimizer,
    parse_optimizer_param,
)
from XBrainLab.ui.components.modal_presentation import show_warning
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import normalize_dialog_button_box


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

    def __init__(
        self,
        parent,
        *,
        optimizer=None,
        optimizer_params: dict | None = None,
    ):
        self.optim = None
        self.optim_params = None
        self._initial_optimizer = optimizer
        self._initial_optimizer_params = dict(optimizer_params or {})

        self.algo_map = get_optimizer_classes()

        # UI
        self.algo_combo = None
        self.params_table = None

        super().__init__(parent, title="Optimizer Setting")
        self.resize(400, 500)

        # Restore the current training choice instead of silently selecting the
        # first algorithm whenever the nested dialog is opened.
        if self.algo_map and self.algo_combo:
            initial_name = str(getattr(optimizer, "__name__", optimizer) or "")
            if initial_name not in self.algo_map:
                initial_name = next(iter(self.algo_map.keys()))
            self.algo_combo.setCurrentText(initial_name)
            self.on_algo_select(initial_name)
            self._restore_initial_parameters(initial_name)

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
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        normalize_dialog_button_box(buttons)
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

    def _restore_initial_parameters(self, algo_name: str) -> None:
        if self.params_table is None or algo_name != str(
            getattr(self._initial_optimizer, "__name__", "") or ""
        ):
            return
        for row in range(self.params_table.rowCount()):
            name_item = self.params_table.item(row, 0)
            value_item = self.params_table.item(row, 1)
            if name_item is None or value_item is None:
                continue
            name = name_item.text()
            if name in self._initial_optimizer_params:
                value_item.setText(repr(self._initial_optimizer_params[name]))

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

                if value_text:
                    optim_params[param] = parse_optimizer_param(
                        target,
                        param,
                        value_text,
                    )

            # Test instantiation
            instantiate_optimizer(target, optim_params)

            self.optim_params = optim_params
            self.optim = target
            super().accept()

        except OptimizerParameterError as exc:
            show_warning(
                self,
                "Validation Error",
                str(exc),
            )
        except (TypeError, ValueError) as exc:
            show_warning(
                self,
                "Validation Error",
                f"Optimizer configuration: {exc}",
            )
        except Exception:
            present_unexpected_error(
                self,
                UnexpectedErrorContext.TRAINING_OPTIMIZER_SETTINGS,
            )

    def get_result(self):
        """Return the selected optimizer class and parameters.

        Returns:
            Tuple of (optimizer_class, optimizer_params_dict).

        """
        return self.optim, self.optim_params
