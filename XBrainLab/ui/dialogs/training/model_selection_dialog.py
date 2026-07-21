"""Model selection dialog for choosing deep learning architectures.

Dynamically generates parameter inputs based on the selected model class
signature and supports loading pretrained weights.
"""

import inspect
import os
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend import model_base
from XBrainLab.backend.training import ModelHolder
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import (
    configure_dark_table,
    fit_table_height_to_contents,
)
from XBrainLab.ui.styles.theme import Theme

ARG_DICT_SKIP_SET = {"self", "n_classes", "channels", "samples", "sfreq"}
_MODEL_PARAMETER_PRESENTATION = {
    "f1": (
        "Temporal filters",
        "f1: number of temporal filters in the first EEGNet convolution.",
    ),
    "f2": (
        "Pointwise filters",
        "f2: number of pointwise filters in the EEGNet separable convolution.",
    ),
    "d": (
        "Depth multiplier",
        "d: number of spatial filters learned for each temporal filter.",
    ),
    "pool_1": (
        "First pooling size",
        "pool_1: first average-pooling window, measured in samples.",
    ),
    "pool_2": (
        "Second pooling size",
        "pool_2: second average-pooling window, measured in samples.",
    ),
    "ns": (
        "Spatial filters",
        "ns: number of spatial filters used by SCCNet.",
    ),
    "pool_len": (
        "Pooling window",
        "pool_len: average-pooling window, measured in samples.",
    ),
    "pool_stride": (
        "Pooling stride",
        "pool_stride: distance between pooling windows, measured in samples.",
    ),
}
_CHEVRON_DOWN_ICON = (
    Path(__file__).resolve().parents[3] / "resources" / "icons" / "chevron-down.svg"
).as_posix()


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

    def __init__(
        self,
        parent,
        controller,
        initial_model_name: str | None = None,
    ):
        self.controller = controller

        self.pretrained_weight_path = None
        self.model_holder = None

        # UI Elements
        self.model_combo = None
        self.params_table = None
        self.params_group = None
        self.confirm_btn = None
        self.weight_label = None
        self.weight_btn = None
        self.content_scroll = None

        # Fetch model list
        self.model_map = {
            m[0]: m[1] for m in inspect.getmembers(model_base, inspect.isclass)
        }
        self.model_list = list(self.model_map.keys())
        self.initial_model_name = self._canonical_model_name(initial_model_name)

        super().__init__(parent, title="Model Selection")
        self.setMinimumSize(600, 360)

        # Init with first model
        if self.model_list:
            selected_model_name = (
                self.model_combo.currentText()
                if self.model_combo is not None
                else self.model_list[0]
            )
            self.on_model_select(selected_model_name)
        self.fit_to_content(
            minimum_width=640,
            minimum_height=440,
            maximum_height=620,
        )

    def _canonical_model_name(self, model_name: str | None) -> str | None:
        if not isinstance(model_name, str):
            return None
        requested_name = model_name.casefold()
        return next(
            (
                available_name
                for available_name in self.model_list
                if available_name.casefold() == requested_name
            ),
            None,
        )

    def init_ui(self):
        """Initialize the dialog UI with model combo, parameter table, and buttons."""
        self.setObjectName("ModelSelectionDialog")
        self.setStyleSheet(self._dialog_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)

        content = QWidget()
        content.setObjectName("ModelSelectionContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.content_scroll = QScrollArea()
        self.content_scroll.setObjectName("ModelSelectionContentScroll")
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.content_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setWidget(content)

        # Model setup
        setup_frame = QFrame()
        setup_frame.setObjectName("ModelSection")
        setup_frame.setFrameShape(QFrame.Shape.NoFrame)
        setup_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        setup_layout = QGridLayout(setup_frame)
        setup_layout.setContentsMargins(12, 12, 12, 12)
        setup_layout.setHorizontalSpacing(12)
        setup_layout.setVerticalSpacing(10)
        setup_title = QLabel("Model setup")
        setup_title.setObjectName("SectionTitle")
        setup_layout.addWidget(setup_title, 0, 0, 1, 3)

        setup_layout.addWidget(QLabel("Model"), 1, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems(self.model_list)
        if self.initial_model_name is not None:
            self.model_combo.setCurrentText(self.initial_model_name)
        self.model_combo.currentTextChanged.connect(self.on_model_select)
        setup_layout.addWidget(self.model_combo, 1, 1)

        setup_layout.addWidget(QLabel("Pretrained weight"), 2, 0)
        self.weight_label = QLabel("None")
        self.weight_label.setObjectName("PretrainedWeightLabel")
        self.weight_label.setMinimumHeight(28)
        self.weight_label.setWordWrap(False)
        setup_layout.addWidget(self.weight_label, 2, 1)
        self.weight_btn = QPushButton("Load")
        self.weight_btn.setFixedWidth(76)
        self.weight_btn.clicked.connect(self.load_pretrained_weight)
        setup_layout.addWidget(self.weight_btn, 2, 2)
        setup_layout.setColumnStretch(1, 1)
        content_layout.addWidget(setup_frame)

        # Parameters Table
        self.params_group = QFrame()
        self.params_group.setObjectName("ModelSection")
        self.params_group.setFrameShape(QFrame.Shape.NoFrame)
        self.params_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        group_layout = QVBoxLayout(self.params_group)
        group_layout.setContentsMargins(12, 12, 12, 12)
        group_layout.setSpacing(10)
        params_title = QLabel("Model parameters")
        params_title.setObjectName("SectionTitle")
        group_layout.addWidget(params_title)
        self.params_table = QTableWidget()
        self.params_table.setColumnCount(2)
        self.params_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.params_table.setAlternatingRowColors(True)
        self.params_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.params_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.params_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.params_table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.params_table.setMaximumHeight(240)
        configure_dark_table(
            self.params_table,
            object_name="ModelParamsTable",
            no_selection=True,
        )
        header = self.params_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        vertical_header = self.params_table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        group_layout.addWidget(self.params_table)
        content_layout.addWidget(self.params_group, stretch=0)
        layout.addWidget(self.content_scroll, stretch=0)

        # Buttons
        action_layout = QHBoxLayout()
        action_layout.addStretch(1)
        self.confirm_btn = QPushButton("Confirm")
        self.confirm_btn.setObjectName("PrimaryConfirmButton")
        self.confirm_btn.clicked.connect(self.accept)
        action_layout.addWidget(self.confirm_btn)
        layout.addLayout(action_layout)

    @staticmethod
    def _dialog_style() -> str:
        return f"""
        QDialog#ModelSelectionDialog {{
            background: {Theme.BACKGROUND_DARK};
            color: {Theme.TEXT_PRIMARY};
        }}
        QDialog#ModelSelectionDialog QLabel {{
            color: {Theme.TEXT_PRIMARY};
            background: transparent;
        }}
        QDialog#ModelSelectionDialog QFrame#ModelSection {{
            color: {Theme.TEXT_PRIMARY};
            border: none;
            border-radius: 6px;
            background: {Theme.BACKGROUND_MID};
        }}
        QDialog#ModelSelectionDialog QLabel#SectionTitle {{
            color: {Theme.TEXT_SECONDARY};
            background: transparent;
            font-weight: 700;
        }}
        QDialog#ModelSelectionDialog QComboBox {{
            background: {Theme.METRICS_TABLE_BG};
            color: {Theme.TEXT_PRIMARY};
            border: 1px solid {Theme.METRICS_TABLE_BORDER};
            border-radius: 4px;
            padding: 4px 28px 4px 8px;
            min-height: 22px;
        }}
        QDialog#ModelSelectionDialog QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            border: none;
            width: 24px;
        }}
        QDialog#ModelSelectionDialog QComboBox::down-arrow {{
            image: url("{_CHEVRON_DOWN_ICON}");
            width: 10px;
            height: 10px;
        }}
        QDialog#ModelSelectionDialog QLabel#PretrainedWeightLabel {{
            background: {Theme.METRICS_TABLE_BG};
            color: {Theme.TEXT_SECONDARY};
            border: 1px solid {Theme.METRICS_TABLE_BORDER};
            border-radius: 4px;
            padding: 5px 8px;
        }}
        QDialog#ModelSelectionDialog QScrollArea#ModelSelectionContentScroll {{
            border: none;
            background: {Theme.BACKGROUND_DARK};
        }}
        QDialog#ModelSelectionDialog QScrollArea#ModelSelectionContentScroll > QWidget,
        QDialog#ModelSelectionDialog QWidget#ModelSelectionContent {{
            background: {Theme.BACKGROUND_DARK};
        }}
        QDialog#ModelSelectionDialog QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 0;
            border: none;
        }}
        QDialog#ModelSelectionDialog QScrollBar::handle:vertical {{
            background: {Theme.BACKGROUND_LIGHT};
            border-radius: 5px;
            min-height: 28px;
        }}
        QDialog#ModelSelectionDialog QScrollBar::handle:vertical:hover {{
            background: {Theme.TEXT_MUTED};
        }}
        QDialog#ModelSelectionDialog QScrollBar::add-line:vertical,
        QDialog#ModelSelectionDialog QScrollBar::sub-line:vertical {{
            height: 0;
            background: transparent;
        }}
        QDialog#ModelSelectionDialog QScrollBar::add-page:vertical,
        QDialog#ModelSelectionDialog QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
        QDialog#ModelSelectionDialog QPushButton {{
            background: {Theme.BACKGROUND_MID};
            color: {Theme.TEXT_PRIMARY};
            border: 1px solid {Theme.BACKGROUND_LIGHT};
            border-radius: 4px;
            padding: 6px 12px;
        }}
        QDialog#ModelSelectionDialog QPushButton:hover {{
            background: #32363b;
        }}
        QDialog#ModelSelectionDialog QPushButton:default {{
            background: {Theme.BLUE_PRIMARY};
            border-color: {Theme.BLUE_HOVER};
            font-weight: 700;
        }}
        QDialog#ModelSelectionDialog QPushButton#PrimaryConfirmButton {{
            min-width: 128px;
            padding: 7px 12px;
            border-radius: 4px;
            border: 1px solid #0a7fc7;
            background: #0069a8;
            color: {Theme.TEXT_PRIMARY};
            font-weight: 700;
        }}
        QDialog#ModelSelectionDialog QPushButton#PrimaryConfirmButton:hover {{
            background: #0a7fc7;
        }}
        """

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
                label, tooltip = _MODEL_PARAMETER_PRESENTATION.get(
                    param,
                    (param, f"Model constructor parameter: {param}"),
                )
                item_param = QTableWidgetItem(label)
                item_param.setData(Qt.ItemDataRole.UserRole, param)
                item_param.setToolTip(tooltip)
                item_param.setFlags(item_param.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.params_table.setItem(i, 0, item_param)
                value_item = QTableWidgetItem(val)
                value_item.setToolTip(tooltip)
                self.params_table.setItem(i, 1, value_item)

            if not rows:
                self._show_no_editable_params()
        self._resize_params_table_to_content()
        self._clear_params_table_selection()
        self.params_group.setVisible(True)
        self._resize_dialog_to_content()

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
        self._resize_params_table_to_content()
        self._clear_params_table_selection()

    def _resize_params_table_to_content(self) -> None:
        """Keep the parameter table compact instead of filling the dialog."""
        if not self.params_table:
            return

        target_height = fit_table_height_to_contents(
            self.params_table,
            max_visible_rows=7,
            minimum_rows=1,
            padding=8,
        )
        if self.params_group:
            self.params_group.setMaximumHeight(target_height + 58)

    def _resize_dialog_to_content(self) -> None:
        """Resize normal content high enough so the scroll area is not a gutter."""
        self.fit_to_content(
            minimum_width=640,
            minimum_height=440,
            maximum_height=620,
        )

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
            self.weight_label.setText("None")
            self.weight_btn.setText("Load")
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Pretrained Weight",
            filter="Model Weights (*)",
        )
        if filepath:
            self.pretrained_weight_path = filepath
            self.weight_label.setText(os.path.basename(filepath))
            self.weight_btn.setText("Clear")

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
                param = (
                    item0.data(Qt.ItemDataRole.UserRole) if item0 is not None else None
                )
                if not isinstance(param, str) or not param:
                    continue

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
