"""Resampling dialog for downsampling EEG data to a target frequency.

Provides a simple input for specifying the desired sampling rate,
useful for reducing data size and computation time.
"""

from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import normalize_dialog_button_box
from XBrainLab.ui.dialogs.preprocess.common import (
    configure_preprocess_dialog_layout,
    create_preprocess_section,
    fit_preprocess_dialog_to_content,
)


class ResampleDialog(BaseDialog):
    """Dialog for downsampling/resampling EEG data to a target frequency.

    Provides a single spin box for specifying the desired sampling rate.

    Attributes:
        sfreq: Target sampling frequency in Hz after acceptance.
        sfreq_spin: QDoubleSpinBox for entering the sampling rate.

    """

    def __init__(self, parent):
        self.sfreq: float | None = None
        self.sfreq_spin = None
        self.section_title = None
        super().__init__(parent, title="Resample", width=400, height=220)
        fit_preprocess_dialog_to_content(self, minimum_width=400)

    def init_ui(self):
        """Initialize the dialog UI with sampling rate input and buttons."""
        layout = QVBoxLayout(self)
        configure_preprocess_dialog_layout(layout)
        section, self.section_title, section_layout = create_preprocess_section(
            "Target sampling rate",
            parent=self,
        )
        self.sfreq_spin = QDoubleSpinBox()
        self.sfreq_spin.setRange(1, 10000)
        self.sfreq_spin.setValue(250.0)
        self.sfreq_spin.setFixedWidth(150)
        self.sfreq_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        field_row = QHBoxLayout()
        field_row.setContentsMargins(0, 0, 0, 0)
        field_row.setSpacing(8)
        field_label = QLabel("Sampling rate")
        field_label.setObjectName("PreprocessFieldLabel")
        field_row.addWidget(field_label)
        field_row.addWidget(self.sfreq_spin)
        field_row.addWidget(QLabel("Hz"))
        field_row.addStretch()
        section_layout.addLayout(field_row)
        layout.addWidget(section)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        normalize_dialog_button_box(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        """Store the selected sampling rate and accept the dialog."""
        if self.sfreq_spin:
            self.sfreq = self.sfreq_spin.value()
        super().accept()

    def get_params(self):
        """Return the selected sampling frequency.

        Returns:
            Target sampling frequency in Hz as a float, or None.

        """
        return self.sfreq

    def get_result(self):
        """Return the selected sampling frequency.

        Returns:
            Target sampling frequency in Hz as a float, or None.

        """
        return self.get_params()
