from PyQt6.QtWidgets import (
    QCheckBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QMessageBox,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


class FilteringDialog(BaseDialog):
    """
    Dialog for configuring frequency filters.
    Supports Bandpass (Low/High cut) and Notch filters.
    """

    def __init__(self, parent):
        self.params: tuple | None = None
        self.bandpass_check = None
        self.l_freq_spin = None
        self.h_freq_spin = None
        self.notch_check = None
        self.notch_spin = None

        super().__init__(parent, title="Filtering")
        self.resize(300, 250)

    def init_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Bandpass Filter
        self.bandpass_check = QCheckBox("Apply Bandpass Filter")
        self.bandpass_check.setChecked(True)
        self.bandpass_check.toggled.connect(self.toggle_bandpass)
        form_layout.addRow(self.bandpass_check)

        self.l_freq_spin = QDoubleSpinBox()
        self.l_freq_spin.setRange(0, 1000)
        self.l_freq_spin.setDecimals(2)
        self.l_freq_spin.setValue(1.0)  # Default

        self.h_freq_spin = QDoubleSpinBox()
        self.h_freq_spin.setRange(0, 1000)
        self.h_freq_spin.setDecimals(2)
        self.h_freq_spin.setValue(40.0)  # Default

        form_layout.addRow("Lower pass-band (Hz):", self.l_freq_spin)
        form_layout.addRow("Upper pass-band (Hz):", self.h_freq_spin)

        # Notch Filter
        self.notch_check = QCheckBox("Apply Notch Filter")
        self.notch_check.toggled.connect(self.toggle_notch)
        form_layout.addRow(self.notch_check)

        self.notch_spin = QDoubleSpinBox()
        self.notch_spin.setRange(0, 1000)
        self.notch_spin.setValue(50.0)  # Default 50Hz
        self.notch_spin.setEnabled(False)
        form_layout.addRow("Notch Frequency (Hz):", self.notch_spin)

        layout.addLayout(form_layout)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def toggle_notch(self, checked):
        if self.notch_spin:
            self.notch_spin.setEnabled(checked)

    def toggle_bandpass(self, checked):
        if self.l_freq_spin:
            self.l_freq_spin.setEnabled(checked)
        if self.h_freq_spin:
            self.h_freq_spin.setEnabled(checked)

    def accept(self):
        if (
            not self.bandpass_check
            or not self.l_freq_spin
            or not self.h_freq_spin
            or not self.notch_check
            or not self.notch_spin
        ):
            return

        l_freq = None
        h_freq = None

        if self.bandpass_check.isChecked():
            l_freq = self.l_freq_spin.value()
            h_freq = self.h_freq_spin.value()

            # Validate
            if l_freq >= h_freq > 0:
                QMessageBox.warning(
                    self, "Invalid Input", "Lower freq must be less than Upper freq."
                )
                return

        notch_freqs = None
        if self.notch_check.isChecked():
            notch_freqs = self.notch_spin.value()

        if l_freq is None and h_freq is None and notch_freqs is None:
            QMessageBox.warning(
                self,
                "Warning",
                "Please select at least one filter (Bandpass or Notch).",
            )
            return

        self.params = (l_freq, h_freq, notch_freqs)
        super().accept()

    def get_params(self):
        return self.params

    def get_result(self):
        return self.get_params()
