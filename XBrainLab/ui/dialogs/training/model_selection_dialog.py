"""Model selection dialog for choosing deep learning architectures.

Dynamically generates parameter inputs based on the selected model class
signature and supports loading pretrained weights.
"""

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
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend import model_base
from XBrainLab.backend.model_base.model_catalog import (
    ModelSpec,
    default_model_id,
    discover_model_specs,
)
from XBrainLab.backend.training import ModelHolder
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import (
    configure_dark_table,
    fit_table_height_to_contents,
)
from XBrainLab.ui.styles.theme import Theme

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

        self.pretrained_weight_path: str | None = None
        self.model_holder: ModelHolder | None = None

        # UI Elements
        self.model_combo: QComboBox | None = None
        self.params_table: QTableWidget | None = None
        self.params_group: QFrame | None = None
        self.confirm_btn: QPushButton | None = None
        self.weight_label: QLabel | None = None
        self.weight_btn: QPushButton | None = None
        self.content_scroll: QScrollArea | None = None

        # Fetch model list
        self.model_specs = discover_model_specs(model_base)
        self.model_map = {spec.display_name: spec.factory for spec in self.model_specs}
        self._spec_by_name = {spec.display_name: spec for spec in self.model_specs}
        self.model_list = [spec.display_name for spec in self.model_specs]
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
            minimum_height=452,
            maximum_height=620,
        )

    def _canonical_model_name(self, model_name: str | None) -> str | None:
        if not isinstance(model_name, str):
            default_id = default_model_id()
            return next(
                (
                    spec.display_name
                    for spec in self.model_specs
                    if spec.model_id == default_id
                ),
                self.model_list[0] if self.model_list else None,
            )
        requested_name = model_name.casefold()
        for spec in self.model_specs:
            factory_name = getattr(spec.factory, "__name__", "").casefold()
            if requested_name in {
                spec.model_id.casefold(),
                spec.display_name.casefold(),
                factory_name,
            }:
                return spec.display_name
        return None

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

        content_scroll = QScrollArea()
        self.content_scroll = content_scroll
        content_scroll.setObjectName("ModelSelectionContentScroll")
        content_scroll.setWidgetResizable(True)
        content_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        content_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setWidget(content)

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
        model_combo = QComboBox()
        self.model_combo = model_combo
        model_combo.setObjectName("ModelSelectionCombo")
        model_combo.addItems(self.model_list)
        if self.initial_model_name is not None:
            model_combo.setCurrentText(self.initial_model_name)
        model_combo.currentTextChanged.connect(self.on_model_select)
        setup_layout.addWidget(model_combo, 1, 1)

        setup_layout.addWidget(QLabel("Pretrained weight"), 2, 0)
        weight_label = QLabel("None")
        self.weight_label = weight_label
        weight_label.setObjectName("PretrainedWeightLabel")
        weight_label.setMinimumHeight(28)
        weight_label.setWordWrap(False)
        setup_layout.addWidget(weight_label, 2, 1)
        weight_btn = QPushButton("Load")
        self.weight_btn = weight_btn
        weight_btn.setFixedWidth(76)
        weight_btn.clicked.connect(self.load_pretrained_weight)
        setup_layout.addWidget(weight_btn, 2, 2)
        setup_layout.setColumnStretch(1, 1)
        content_layout.addWidget(setup_frame)

        # Parameters Table
        params_group = QFrame()
        self.params_group = params_group
        params_group.setObjectName("ModelSection")
        params_group.setFrameShape(QFrame.Shape.NoFrame)
        params_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        group_layout = QVBoxLayout(params_group)
        group_layout.setContentsMargins(12, 12, 12, 12)
        group_layout.setSpacing(10)
        params_title = QLabel("Model parameters")
        params_title.setObjectName("SectionTitle")
        group_layout.addWidget(params_title)
        params_table = QTableWidget()
        self.params_table = params_table
        params_table.setColumnCount(2)
        params_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        params_table.setAlternatingRowColors(True)
        params_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        params_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        params_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        params_table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        params_table.setMaximumHeight(240)
        configure_dark_table(
            params_table,
            object_name="ModelParamsTable",
            no_selection=True,
        )
        header = params_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        vertical_header = params_table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        group_layout.addWidget(params_table)
        content_layout.addWidget(params_group, stretch=0)
        layout.addWidget(content_scroll, stretch=0)

        # Buttons
        action_layout = QHBoxLayout()
        action_layout.addStretch(1)
        confirm_btn = QPushButton("Confirm")
        self.confirm_btn = confirm_btn
        confirm_btn.setObjectName("PrimaryConfirmButton")
        confirm_btn.clicked.connect(self.accept)
        action_layout.addWidget(confirm_btn)
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

        spec = self._spec_by_name[model_name]
        self.params_table.setRowCount(0)

        if spec:
            rows = list(spec.parameters)
            self.params_table.setRowCount(len(rows))
            for i, parameter in enumerate(rows):
                item_param = QTableWidgetItem(parameter.label)
                item_param.setData(Qt.ItemDataRole.UserRole, parameter.key)
                item_param.setToolTip(parameter.tooltip)
                item_param.setFlags(item_param.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.params_table.setItem(i, 0, item_param)
                value = "" if parameter.default is None else str(parameter.default)
                value_item = QTableWidgetItem(value)
                value_item.setToolTip(parameter.tooltip)
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
            minimum_height=452,
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

        spec: ModelSpec = self._spec_by_name[self.model_combo.currentText()]
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
                spec.factory,
                model_params_map,
                self.pretrained_weight_path,
                model_id=spec.model_id,
                display_name=spec.display_name,
            )
            super().accept()

        except Exception:
            present_unexpected_error(
                self,
                UnexpectedErrorContext.TRAINING_MODEL_SETTINGS,
            )

    def get_result(self):
        """Return the configured ModelHolder.

        Returns:
            ModelHolder instance with selected model and parameters, or None.

        """
        return self.model_holder
