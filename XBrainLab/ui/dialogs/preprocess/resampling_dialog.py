"""Resampling dialog for downsampling EEG data to a target frequency.

Provides a simple input for specifying the desired sampling rate,
useful for reducing data size and computation time.
"""

from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


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
        super().__init__(parent, title="Resample")
        self.resize(300, 100)

    def init_ui(self):
        """Initialize the dialog UI with sampling rate input and buttons."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.sfreq_spin = QDoubleSpinBox()
        self.sfreq_spin.setRange(1, 10000)
        self.sfreq_spin.setValue(250.0)
        form.addRow("Sampling Rate (Hz):", self.sfreq_spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
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
