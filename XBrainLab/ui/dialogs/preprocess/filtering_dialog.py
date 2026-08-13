"""Frequency filtering settings for EEG preprocessing."""

from __future__ import annotations

import math

from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import normalize_dialog_button_box
from XBrainLab.ui.dialogs.preprocess.common import (
    configure_preprocess_dialog_layout,
    create_preprocess_section,
    fit_preprocess_dialog_to_content,
)


class FilteringDialog(BaseDialog):
    """Configure optional band-pass and notch filters without changing values."""

    def __init__(self, parent, *, sampling_rate_hz: float | None = None):
        self.params: tuple[float | None, float | None, float | None] | None = None
        self.sampling_rate_hz = self._valid_sampling_rate(sampling_rate_hz)
        self.bandpass_check: QPushButton
        self.notch_check: QPushButton
        self.bandpass_title: QLabel
        self.notch_title: QLabel
        self.frequency_range_label: QLabel
        self.l_freq_spin: QDoubleSpinBox
        self.h_freq_spin: QDoubleSpinBox
        self.notch_mode_combo: QComboBox
        self.notch_spin: QDoubleSpinBox
        self.validation_label: QLabel
        self.ok_button: QPushButton
        super().__init__(parent, title="Filtering", width=520, height=360)
        fit_preprocess_dialog_to_content(self, minimum_width=520)

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        configure_preprocess_dialog_layout(layout)

        bandpass_section, self.bandpass_title, bandpass_layout = (
            create_preprocess_section("Band-pass filter", parent=self)
        )
        bandpass_header = QHBoxLayout()
        bandpass_header.setContentsMargins(0, 0, 0, 0)
        bandpass_header.addWidget(self.bandpass_title)
        bandpass_header.addStretch()
        self.bandpass_check = self._toggle_button(checked=True)
        self.bandpass_check.setObjectName("FilteringBandpassToggle")
        bandpass_header.addWidget(self.bandpass_check)
        bandpass_layout.removeWidget(self.bandpass_title)
        bandpass_layout.insertLayout(0, bandpass_header)

        self.frequency_range_label = QLabel("Frequency range")
        self.frequency_range_label.setObjectName("PreprocessFieldLabel")
        bandpass_layout.addWidget(self.frequency_range_label)
        frequency_row = QHBoxLayout()
        frequency_row.setContentsMargins(0, 0, 0, 0)
        frequency_row.setSpacing(8)
        self.l_freq_spin = self._frequency_spin(1.0)
        self.l_freq_spin.setObjectName("FilteringLowFrequencyInput")
        self.h_freq_spin = self._frequency_spin(40.0)
        self.h_freq_spin.setObjectName("FilteringHighFrequencyInput")
        frequency_row.addWidget(self.l_freq_spin)
        frequency_row.addWidget(QLabel("-"))
        frequency_row.addWidget(self.h_freq_spin)
        frequency_row.addWidget(QLabel("Hz"))
        frequency_row.addStretch()
        bandpass_layout.addLayout(frequency_row)
        layout.addWidget(bandpass_section)

        notch_section, self.notch_title, notch_layout = create_preprocess_section(
            "Notch filter",
            parent=self,
        )
        notch_header = QHBoxLayout()
        notch_header.setContentsMargins(0, 0, 0, 0)
        notch_header.addWidget(self.notch_title)
        notch_header.addStretch()
        self.notch_check = self._toggle_button(checked=False)
        self.notch_check.setObjectName("FilteringNotchToggle")
        notch_header.addWidget(self.notch_check)
        notch_layout.removeWidget(self.notch_title)
        notch_layout.insertLayout(0, notch_header)

        notch_label = QLabel("Power-line frequency")
        notch_label.setObjectName("PreprocessFieldLabel")
        notch_layout.addWidget(notch_label)
        notch_row = QHBoxLayout()
        notch_row.setContentsMargins(0, 0, 0, 0)
        notch_row.setSpacing(8)
        self.notch_mode_combo = QComboBox()
        self.notch_mode_combo.setObjectName("FilteringNotchModeInput")
        self.notch_mode_combo.addItems(["50 Hz", "60 Hz", "Custom"])
        self.notch_mode_combo.setFixedWidth(140)
        self.notch_spin = self._frequency_spin(50.0)
        self.notch_spin.setObjectName("FilteringNotchFrequencyInput")
        self.notch_spin.setFixedWidth(120)
        self.notch_spin.setSuffix(" Hz")
        notch_row.addWidget(self.notch_mode_combo)
        notch_row.addWidget(self.notch_spin)
        notch_row.addStretch()
        notch_layout.addLayout(notch_row)
        layout.addWidget(notch_section)

        self.validation_label = QLabel()
        self.validation_label.setObjectName("PreprocessInlineError")
        self.validation_label.setWordWrap(True)
        self.validation_label.hide()
        layout.addWidget(self.validation_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        normalize_dialog_button_box(buttons)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if not isinstance(ok_button, QPushButton):
            raise RuntimeError("Filtering dialog OK button is unavailable")
        self.ok_button = ok_button
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.bandpass_check.toggled.connect(self.toggle_bandpass)
        self.notch_check.toggled.connect(self.toggle_notch)
        self.notch_mode_combo.currentTextChanged.connect(self._sync_notch_mode)
        for spin in (self.l_freq_spin, self.h_freq_spin, self.notch_spin):
            spin.valueChanged.connect(self._update_validation)
        self._sync_toggle_text(self.bandpass_check)
        self._sync_toggle_text(self.notch_check)
        self.toggle_bandpass(True)
        self.toggle_notch(False)
        self._sync_notch_mode()
        self._update_validation()

    @staticmethod
    def _valid_sampling_rate(value: float | None) -> float | None:
        if value is None:
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) and result > 0 else None

    @staticmethod
    def _toggle_button(*, checked: bool) -> QPushButton:
        button = QPushButton()
        button.setObjectName("PreprocessToggle")
        button.setCheckable(True)
        button.setChecked(checked)
        button.setAutoDefault(False)
        button.setDefault(False)
        button.toggled.connect(
            lambda _checked, owned=button: FilteringDialog._sync_toggle_text(owned)
        )
        return button

    @staticmethod
    def _sync_toggle_text(button: QPushButton) -> None:
        button.setText("On" if button.isChecked() else "Off")

    @staticmethod
    def _frequency_spin(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1000.0)
        spin.setDecimals(2)
        spin.setValue(value)
        spin.setFixedWidth(120)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        return spin

    def toggle_notch(self, checked: bool) -> None:
        self.notch_mode_combo.setEnabled(checked)
        self._sync_notch_mode()
        self._update_validation()

    def toggle_bandpass(self, checked: bool) -> None:
        self.frequency_range_label.setEnabled(checked)
        self.l_freq_spin.setEnabled(checked)
        self.h_freq_spin.setEnabled(checked)
        self._update_validation()

    def _sync_notch_mode(self, *_args) -> None:
        custom = self.notch_mode_combo.currentText() == "Custom"
        self.notch_spin.setVisible(custom)
        self.notch_spin.setEnabled(self.notch_check.isChecked() and custom)
        self._update_validation()

    def _selected_notch_frequency(self) -> float:
        mode = self.notch_mode_combo.currentText()
        if mode == "50 Hz":
            return 50.0
        if mode == "60 Hz":
            return 60.0
        return float(self.notch_spin.value())

    def _validation_error(self) -> str:
        if not self.bandpass_check.isChecked() and not self.notch_check.isChecked():
            return "Enable at least one filter."
        nyquist = (
            self.sampling_rate_hz / 2.0 if self.sampling_rate_hz is not None else None
        )
        if self.bandpass_check.isChecked():
            lower = float(self.l_freq_spin.value())
            upper = float(self.h_freq_spin.value())
            if lower < 0:
                return "Lower frequency must be zero or greater."
            if upper <= lower:
                return "Upper frequency must be greater than lower frequency."
            if nyquist is not None and upper >= nyquist:
                return f"Upper frequency must be below {nyquist:g} Hz."
        if self.notch_check.isChecked():
            notch = self._selected_notch_frequency()
            if notch <= 0:
                return "Notch frequency must be greater than zero."
            if nyquist is not None and notch >= nyquist:
                return f"Notch frequency must be below {nyquist:g} Hz."
        return ""

    def _update_validation(self, *_args) -> None:
        if not hasattr(self, "validation_label") or not hasattr(self, "ok_button"):
            return
        error = self._validation_error()
        self.validation_label.setText(error)
        self.validation_label.setVisible(bool(error))
        self.ok_button.setEnabled(not error)
        fit_preprocess_dialog_to_content(self, minimum_width=520)

    def accept(self) -> None:
        error = self._validation_error()
        if error:
            self._update_validation()
            return
        lower = self.l_freq_spin.value() if self.bandpass_check.isChecked() else None
        upper = self.h_freq_spin.value() if self.bandpass_check.isChecked() else None
        notch = (
            self._selected_notch_frequency() if self.notch_check.isChecked() else None
        )
        self.params = (lower, upper, notch)
        super().accept()

    def get_params(self):
        return self.params

    def get_result(self):
        return self.get_params()
