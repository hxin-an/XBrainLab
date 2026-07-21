"""Normalization dialog for selecting EEG data normalization method.

Provides a choice between Z-Score (standardization) and Min-Max scaling.
"""

from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QRadioButton,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import normalize_dialog_button_box
from XBrainLab.ui.dialogs.preprocess.common import create_preprocess_section


class NormalizeDialog(BaseDialog):
    """Dialog for selecting data normalization method.

    Provides radio button selection between Z-Score (standardization)
    and Min-Max scaling methods.

    Attributes:
        params: Selected normalization method string after acceptance.
        section_container: Unframed section containing the method radio buttons.
        zscore_radio: QRadioButton for Z-Score normalization.
        minmax_radio: QRadioButton for Min-Max normalization.

    """

    def __init__(self, parent):
        self.params: str | None = None
        self.section_container = None
        self.section_title = None
        self.zscore_radio = None
        self.minmax_radio = None
        super().__init__(parent, title="Normalize", width=380, height=220)

    def init_ui(self):
        """Initialize the dialog UI with normalization method selection."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(16)

        self.section_container, self.section_title, method_layout = (
            create_preprocess_section("Normalization method", parent=self)
        )

        self.zscore_radio = QRadioButton("Z-Score (Standardization)")
        self.zscore_radio.setChecked(True)
        self.minmax_radio = QRadioButton("Min-Max Scaling")

        method_layout.addWidget(self.zscore_radio)
        method_layout.addWidget(self.minmax_radio)
        layout.addWidget(self.section_container)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        normalize_dialog_button_box(buttons)
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
