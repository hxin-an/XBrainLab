"""Normalization dialog for selecting EEG data normalization method.

Provides a choice between Z-Score (standardization) and Min-Max scaling.
"""

from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QGroupBox,
    QRadioButton,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


class NormalizeDialog(BaseDialog):
    """Dialog for selecting data normalization method.

    Provides radio button selection between Z-Score (standardization)
    and Min-Max scaling methods.

    Attributes:
        params: Selected normalization method string after acceptance.
        method_group: QGroupBox containing the method radio buttons.
        zscore_radio: QRadioButton for Z-Score normalization.
        minmax_radio: QRadioButton for Min-Max normalization.

    """

    def __init__(self, parent):
        self.params: str | None = None
        self.method_group = None
        self.zscore_radio = None
        self.minmax_radio = None
        super().__init__(parent, title="Normalize")
        self.resize(300, 150)

    def init_ui(self):
        """Initialize the dialog UI with normalization method selection."""
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
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        """Store the selected normalization method and accept the dialog."""
        if not self.zscore_radio:
            return
        method = "z score" if self.zscore_radio.isChecked() else "minmax"
        self.params = method
        super().accept()

    def get_params(self):
        """Return the selected normalization method.

        Returns:
            String ``'z score'`` or ``'minmax'``, or None if not set.

        """
        return self.params

    def get_result(self):
        """Return the selected normalization method.

        Returns:
            String ``'z score'`` or ``'minmax'``, or None if not set.

        """
        return self.get_params()
