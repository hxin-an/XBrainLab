from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QGroupBox,
    QRadioButton,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


class NormalizeDialog(BaseDialog):
    def __init__(self, parent):
        self.params = None
        self.method_group = None
        self.zscore_radio = None
        self.minmax_radio = None
        super().__init__(parent, title="Normalize")
        self.resize(300, 150)

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.method_group = QGroupBox("Normalization Method")
        method_layout = QVBoxLayout()

        self.zscore_radio = QRadioButton("Z-Score (Standardization)")
        self.zscore_radio.setChecked(True)
        self.minmax_radio = QRadioButton("Min-Max Scaling")

        method_layout.addWidget(self.zscore_radio)
        method_layout.addWidget(self.minmax_radio)
        self.method_group.setLayout(method_layout)
        layout.addWidget(self.method_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        if not self.zscore_radio:
            return
        method = "z score" if self.zscore_radio.isChecked() else "minmax"
        self.params = method
        super().accept()

    def get_params(self):
        return self.params

    def get_result(self):
        return self.get_params()
