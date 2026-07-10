"""Saliency method parameter configuration dialog."""

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.saliency_policy import (
    ADVANCED_SALIENCY_METHODS,
    DEFAULT_ADVANCED_SALIENCY_PARAMS,
    selected_saliency_methods_from_params,
)
from XBrainLab.backend.visualization import supported_saliency_methods
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import (
    dark_dialog_stylesheet,
    normalize_dialog_button_box,
)
from XBrainLab.ui.styles.theme import Theme


def _raise_no_saliency_method_selected() -> None:
    raise ValueError("Select at least one saliency method.")


class SaliencySettingDialog(BaseDialog):
    """Dialog for configuring advanced saliency methods and parameters."""

    def __init__(self, parent, saliency_params=None):
        self.saliency_params = saliency_params
        self.algo_map: dict[str, list[str] | None] = {}
        self.params_tables: dict[str, QWidget] = {}
        self.method_checks: dict[str, QCheckBox] = {}
        self.method_param_pages: dict[str, QWidget] = {}
        self.param_editors: dict[str, dict[str, QSpinBox | QDoubleSpinBox]] = {}

        super().__init__(parent, title="Saliency Setting")
        self.setMinimumWidth(440)
        self.setStyleSheet(dark_dialog_stylesheet() + self._dialog_style())

        self.check_init_data()
        if self.algo_map:
            self.display_data()

    def check_init_data(self):
        """Populate the algorithm map from backend saliency method definitions."""
        for method in supported_saliency_methods:
            self.algo_map[method] = list(DEFAULT_ADVANCED_SALIENCY_PARAMS)

    def init_ui(self):
        """Initialize method checkboxes and dynamic parameter tabs."""
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        if not self.algo_map:
            self.check_init_data()

        methods_title = QLabel("Compute methods")
        methods_title.setObjectName("SaliencySectionTitle")
        layout.addWidget(methods_title)

        methods_group = QWidget()
        methods_group.setObjectName("SaliencyComputeMethodsRow")
        methods_group.setMaximumWidth(420)
        methods_group.setMinimumWidth(410)
        methods_group.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Preferred,
        )
        methods_layout = QHBoxLayout(methods_group)
        methods_layout.setContentsMargins(4, 2, 4, 2)
        methods_layout.setSpacing(22)

        selected_methods = selected_saliency_methods_from_params(
            self.saliency_params or {"methods": list(ADVANCED_SALIENCY_METHODS)}
        )
        if not selected_methods:
            selected_methods = set(ADVANCED_SALIENCY_METHODS)
        for method in self.algo_map:
            check = QCheckBox(self._display_method_name(method))
            check.setObjectName(f"SaliencyMethodCheck_{method}")
            check.setChecked(method in selected_methods)
            check.toggled.connect(
                lambda checked, method=method: self._sync_method_tabs(
                    activated_method=method if checked else None,
                ),
            )
            self.method_checks[method] = check
            methods_layout.addWidget(check)
        methods_layout.addStretch(1)
        layout.addWidget(methods_group)

        self.params_title = QLabel("Method parameters")
        self.params_title.setObjectName("SaliencySectionTitle")
        layout.addWidget(self.params_title)

        params_group = QWidget()
        params_group.setObjectName("SaliencyMethodParametersPanel")
        self.params_group = params_group
        params_group.setMaximumWidth(390)
        params_group.setMinimumWidth(380)
        params_group.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Preferred,
        )
        params_layout = QVBoxLayout(params_group)
        params_layout.setContentsMargins(4, 0, 0, 0)
        params_layout.setSpacing(8)

        self.single_method_host = QWidget()
        self.single_method_host.setObjectName("SaliencySingleMethodHost")
        self.single_method_layout = QVBoxLayout(self.single_method_host)
        self.single_method_layout.setContentsMargins(0, 0, 0, 0)
        self.single_method_layout.setSpacing(0)
        params_layout.addWidget(
            self.single_method_host,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )

        self.method_tabs = QTabWidget()
        self.method_tabs.setObjectName("SaliencyMethodTabs")
        self.method_tabs.setDocumentMode(True)
        self.method_tabs.setMovable(False)
        self.method_tabs.setMaximumWidth(380)
        self.method_tabs.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Preferred,
        )
        tab_bar = self.method_tabs.tabBar()
        if tab_bar is not None:
            tab_bar.setDrawBase(False)
        params_layout.addWidget(
            self.method_tabs,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )

        self.empty_state_label = QLabel(
            "Select at least one saliency method to configure parameters."
        )
        self.empty_state_label.setObjectName("SaliencyEmptyState")
        self.empty_state_label.setWordWrap(True)
        self.empty_state_label.setMaximumWidth(372)
        self.empty_state_label.setMinimumWidth(360)
        self.empty_state_label.setMinimumHeight(42)
        self.empty_state_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.MinimumExpanding,
        )
        self.empty_state_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        params_layout.addWidget(
            self.empty_state_label,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )

        for method in self.algo_map:
            page = self._build_method_param_page(method)
            self.method_param_pages[method] = page
            self.params_tables[method] = page

        layout.addWidget(params_group)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        normalize_dialog_button_box(self.button_box)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self._sync_method_tabs()

    def display_data(self):
        """Populate parameter widgets with default or previously saved values."""
        for algo, params_list in self.algo_map.items():
            editors = self.param_editors.get(algo)
            if not editors:
                continue
            for param in params_list or []:
                editor = editors.get(param)
                if editor is None:
                    continue
                self._set_editor_value(editor, self._initial_param_value(algo, param))

    def accept(self):
        """Parse and validate all parameter values, then accept the dialog."""
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
            for algo, editors in self.param_editors.items():
                if algo not in selected_methods:
                    continue
                new_params[algo] = {
                    param: self._editor_value(param, editor)
                    for param, editor in editors.items()
                }

            self.saliency_params = new_params
            super().accept()

        except Exception as e:
            QMessageBox.warning(self, "Validation Error", str(e))

    def get_result(self):
        """Return the configured saliency parameters."""
        return self.saliency_params

    def _build_method_param_page(self, method: str) -> QWidget:
        page = QWidget()
        page.setObjectName("SaliencyMethodParamPage")
        layout = QGridLayout(page)
        page.setMaximumWidth(360)
        page.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout.setContentsMargins(6, 8, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.param_editors[method] = {}
        for row, param in enumerate(self.algo_map.get(method) or []):
            label = QLabel(param)
            label.setObjectName("SaliencyParamLabel")
            label.setFixedWidth(180)
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            editor = self._build_param_editor(param)
            self._set_editor_value(editor, self._initial_param_value(method, param))
            self.param_editors[method][param] = editor
            layout.addWidget(label, row, 0, alignment=Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(editor, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.setColumnMinimumWidth(0, 180)
        layout.setColumnMinimumWidth(1, 150)
        return page

    def _build_param_editor(self, param: str) -> QSpinBox | QDoubleSpinBox:
        if param == "stdevs":
            editor = QDoubleSpinBox()
            editor.setRange(0.0, 100.0)
            editor.setDecimals(4)
            editor.setSingleStep(0.1)
        else:
            editor = QSpinBox()
            if param == "nt_samples_batch_size":
                editor.setRange(0, 100_000)
                editor.setSpecialValueText("None")
            else:
                editor.setRange(1, 100_000)
        editor.setObjectName("SaliencyParamEditor")
        editor.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        editor.setFixedWidth(150)
        editor.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return editor

    def _initial_param_value(self, method: str, param: str) -> Any:
        if self.saliency_params and isinstance(self.saliency_params.get(method), dict):
            return self.saliency_params[method].get(
                param,
                DEFAULT_ADVANCED_SALIENCY_PARAMS.get(param),
            )
        return DEFAULT_ADVANCED_SALIENCY_PARAMS.get(param)

    @staticmethod
    def _set_editor_value(editor: QSpinBox | QDoubleSpinBox, value: Any) -> None:
        if isinstance(editor, QDoubleSpinBox):
            editor.setValue(float(value if value is not None else 0.0))
            return
        if value is None:
            editor.setValue(0)
        else:
            editor.setValue(int(value))

    @staticmethod
    def _editor_value(
        param: str,
        editor: QSpinBox | QDoubleSpinBox,
    ) -> int | float | None:
        if param == "nt_samples_batch_size" and isinstance(editor, QSpinBox):
            value = editor.value()
            return None if value == 0 else value
        if isinstance(editor, QDoubleSpinBox):
            return editor.value()
        return editor.value()

    def _sync_method_tabs(self, activated_method: str | None = None) -> None:
        selected_methods = [
            method for method, check in self.method_checks.items() if check.isChecked()
        ]
        self.method_tabs.clear()
        self._clear_single_method_host()

        has_methods = bool(selected_methods)
        is_single_method = len(selected_methods) == 1
        is_multi_method = len(selected_methods) > 1

        if not has_methods:
            self.params_title.setText("Method parameters")
            self.single_method_host.setVisible(False)
            self.method_tabs.setVisible(False)
            self.method_tabs.setMinimumHeight(0)
            self.method_tabs.setMaximumHeight(0)
            self.empty_state_label.setVisible(True)
            self.empty_state_label.adjustSize()
            empty_height = max(42, self.empty_state_label.sizeHint().height())
            self.empty_state_label.setMinimumHeight(empty_height)
            self.params_group.setMaximumHeight(empty_height + 4)
        elif is_single_method:
            method = selected_methods[0]
            self.params_title.setText(f"{self._display_method_name(method)} parameters")
            self.single_method_host.setVisible(True)
            self.method_param_pages[method].setVisible(True)
            self.single_method_layout.addWidget(
                self.method_param_pages[method],
                alignment=Qt.AlignmentFlag.AlignLeft,
            )
            self.method_tabs.setVisible(False)
            self.method_tabs.setMinimumHeight(0)
            self.method_tabs.setMaximumHeight(0)
            self.empty_state_label.setVisible(False)
            self.params_group.setMaximumHeight(16_777_215)
        elif is_multi_method:
            self.params_title.setText("Method parameters")
            self.single_method_host.setVisible(False)
            self.method_tabs.setMinimumHeight(0)
            self.method_tabs.setMaximumHeight(16_777_215)
            self.params_group.setMaximumHeight(16_777_215)
            for method in selected_methods:
                self.method_tabs.addTab(
                    self.method_param_pages[method],
                    self._display_method_name(method),
                )
            self.method_tabs.setVisible(True)
            self.empty_state_label.setVisible(False)
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(has_methods)
        if activated_method in selected_methods and is_multi_method:
            self.method_tabs.setCurrentWidget(self.method_param_pages[activated_method])
        dialog_layout = self.layout()
        if dialog_layout is not None:
            dialog_layout.activate()
        self.adjustSize()

    def _clear_single_method_host(self) -> None:
        while self.single_method_layout.count():
            item = self.single_method_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    @staticmethod
    def _display_method_name(method: str) -> str:
        return method.replace("_", " ")

    @staticmethod
    def _dialog_style() -> str:
        return f"""
            QLabel#SaliencySectionTitle {{
                color: {Theme.TEXT_PRIMARY};
                font-weight: bold;
                background: transparent;
            }}
            QCheckBox {{
                color: {Theme.TEXT_PRIMARY};
                spacing: 8px;
                padding: 2px 0;
                background: transparent;
            }}
            QWidget#SaliencyComputeMethodsRow,
            QWidget#SaliencyMethodParametersPanel,
            QWidget#SaliencySingleMethodHost {{
                background-color: transparent;
                border: none;
            }}
            QWidget#SaliencyMethodParamPage {{
                background-color: transparent;
                border: none;
            }}
            QLabel#SaliencyParamLabel {{
                color: {Theme.TEXT_SECONDARY};
                min-width: 180px;
                background: transparent;
            }}
            QLabel#SaliencyEmptyState {{
                color: {Theme.TEXT_SECONDARY};
                padding: 8px 0;
                border: none;
                border-radius: 4px;
                background-color: transparent;
            }}
            QTabWidget::pane {{
                border: none;
                background-color: transparent;
                top: 0;
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {Theme.TEXT_SECONDARY};
                border: none;
                border-bottom: 2px solid transparent;
                padding: 6px 9px;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: transparent;
                color: {Theme.TEXT_PRIMARY};
                border-bottom: 2px solid {Theme.BLUE_HOVER};
            }}
            QTabBar::tab:!selected:hover {{
                color: {Theme.TEXT_PRIMARY};
                border-bottom-color: {Theme.BLUE_PRESSED};
            }}
            QTabBar::base {{
                border: none;
                background: transparent;
            }}
            QSpinBox#SaliencyParamEditor,
            QDoubleSpinBox#SaliencyParamEditor {{
                min-width: 140px;
                max-width: 150px;
                background-color: {Theme.METRICS_TABLE_BG};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.METRICS_TABLE_BORDER};
                border-radius: 4px;
                padding: 5px 8px;
            }}
            QSpinBox#SaliencyParamEditor:focus,
            QDoubleSpinBox#SaliencyParamEditor:focus {{
                border-color: {Theme.BLUE_FOCUS_BORDER};
            }}
        """
