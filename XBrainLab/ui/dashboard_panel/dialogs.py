from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
)


class ResampleDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Resample")
        self.resize(300, 100)
        self.sfreq = None
        self.init_ui()

    def init_ui(self):
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
        self.sfreq = self.sfreq_spin.value()
        super().accept()

    def get_params(self):
        return self.sfreq


class EpochingDialog(QDialog):
    def __init__(self, parent, data_list):
        super().__init__(parent)
        self.setWindowTitle("Time Epoching")
        self.resize(400, 500)
        self.data_list = data_list
        self.params = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Event Selection
        event_group = QGroupBox("Select Events")
        event_layout = QVBoxLayout()
        self.event_list = QListWidget()
        self.event_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        # Collect all unique events
        events = set()
        for data in self.data_list:
            try:
                # Use get_event_list which prioritizes imported/resampled events
                _, ev_ids = data.get_event_list()
                if ev_ids:
                    events.update(ev_ids.keys())
            except Exception:  # noqa: PERF203
                pass

        for ev in sorted(events):
            self.event_list.addItem(ev)

        event_layout.addWidget(self.event_list)
        event_group.setLayout(event_layout)
        layout.addWidget(event_group)

        # 2. Parameters
        param_group = QGroupBox("Epoch Parameters")
        form = QFormLayout()

        self.tmin_spin = QDoubleSpinBox()
        self.tmin_spin.setRange(-10, 10)
        self.tmin_spin.setValue(-0.2)
        self.tmin_spin.setSingleStep(0.1)
        self.tmin_spin.valueChanged.connect(self.update_duration_info)

        self.tmax_spin = QDoubleSpinBox()
        self.tmax_spin.setRange(-10, 10)
        self.tmax_spin.setValue(1.0)
        self.tmax_spin.setSingleStep(0.1)
        self.tmax_spin.valueChanged.connect(self.update_duration_info)

        form.addRow("Start (s):", self.tmin_spin)
        form.addRow("End (s):", self.tmax_spin)

        # Duration info label
        self.duration_label = QLabel()
        self.duration_label.setStyleSheet("color: gray; font-style: italic;")
        form.addRow("Duration:", self.duration_label)

        # Warning label (must be created before update_duration_info is called)
        self.warning_label = QLabel()
        self.warning_label.setStyleSheet("color: orange; font-weight: bold;")
        self.warning_label.setWordWrap(True)
        form.addRow(self.warning_label)

        # Now update duration info (which uses warning_label)
        self.update_duration_info()

        # Baseline
        self.baseline_check = QCheckBox("Apply Baseline Correction")
        self.baseline_check.setChecked(True)
        self.baseline_check.toggled.connect(self.toggle_baseline)

        self.b_min_spin = QDoubleSpinBox()
        self.b_min_spin.setRange(-10, 10)
        self.b_min_spin.setValue(-0.2)

        self.b_max_spin = QDoubleSpinBox()
        self.b_max_spin.setRange(-10, 10)
        self.b_max_spin.setValue(0.0)

        form.addRow(self.baseline_check)
        form.addRow("Baseline Min (s):", self.b_min_spin)
        form.addRow("Baseline Max (s):", self.b_max_spin)

        param_group.setLayout(form)
        layout.addWidget(param_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def toggle_baseline(self, checked):
        self.b_min_spin.setEnabled(checked)
        self.b_max_spin.setEnabled(checked)

    def update_duration_info(self):
        """Update duration information and show warning if duration is too short."""
        tmin = self.tmin_spin.value()
        tmax = self.tmax_spin.value()
        duration = tmax - tmin

        self.duration_label.setText(f"{duration:.2f}s ({tmax} - ({tmin}))")

        # Check if duration might be too short for models
        # Most models need at least 1.0-1.2s at typical sampling rates
        if duration < 1.0:
            self.warning_label.setText(
                "Warning: Epoch duration < 1.0s may be too short for some models "
                "(EEGNet, SCCNet, ShallowConvNet). "
                "Consider using at least 1.2s to avoid errors during training plan "
                "generation."
            )
            self.warning_label.show()
        elif duration < 1.2:
            self.warning_label.setText(
                "Note: Epoch duration < 1.2s may cause issues with high sampling rates "
                "(>250Hz)."
            )
            self.warning_label.show()
        else:
            self.warning_label.hide()

    def accept(self):
        selected_items = self.event_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select at least one event.")
            return

        selected_events = [item.text() for item in selected_items]
        tmin = self.tmin_spin.value()
        tmax = self.tmax_spin.value()

        baseline = None
        if self.baseline_check.isChecked():
            baseline = (self.b_min_spin.value(), self.b_max_spin.value())

        self.params = (baseline, selected_events, tmin, tmax)
        super().accept()

    def get_params(self):
        return self.params


class FilteringDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Filtering")
        self.resize(300, 250)
        self.params = None
        self.init_ui()

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
        self.notch_spin.setEnabled(checked)

    def toggle_bandpass(self, checked):
        self.l_freq_spin.setEnabled(checked)
        self.h_freq_spin.setEnabled(checked)

    def accept(self):
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


class RereferenceDialog(QDialog):
    def __init__(self, parent, data_list):
        super().__init__(parent)
        self.setWindowTitle("Re-reference")
        self.resize(400, 300)
        self.data_list = data_list
        self.reref_params: str | list[str] | None = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.avg_check = QCheckBox("Use Average Reference")
        self.avg_check.setChecked(True)
        self.avg_check.toggled.connect(self.toggle_avg)
        layout.addWidget(self.avg_check)

        self.chan_group = QGroupBox("Select Reference Channels")
        self.chan_group.setEnabled(False)
        chan_layout = QVBoxLayout()
        self.chan_list = QListWidget()
        self.chan_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        if self.data_list:
            first_data = self.data_list[0]
            self.chan_list.addItems(first_data.get_mne().ch_names)

        chan_layout.addWidget(self.chan_list)
        self.chan_group.setLayout(chan_layout)
        layout.addWidget(self.chan_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def toggle_avg(self, checked):
        self.chan_group.setEnabled(not checked)

    def accept(self):
        ref: str | list[str]
        if self.avg_check.isChecked():
            ref = "average"
        else:
            selected = self.chan_list.selectedItems()
            if not selected:
                QMessageBox.warning(
                    self,
                    "Warning",
                    "Please select at least one channel or use average reference.",
                )
                return
            ref = [item.text() for item in selected]

        self.reref_params = ref
        super().accept()

    def get_params(self):
        return self.reref_params


class NormalizeDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Normalize")
        self.resize(300, 150)
        self.params = None
        self.init_ui()

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
        method = "z score" if self.zscore_radio.isChecked() else "minmax"
        self.params = method
        super().accept()

    def get_params(self):
        return self.params
