"""Epoching dialog for configuring time-locked EEG epoch extraction.

Provides controls for selecting events, specifying the time window
(tmin/tmax), and optionally applying baseline correction.
"""

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
)

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.styles.stylesheets import Stylesheets


class EpochingDialog(BaseDialog):
    """Dialog for configuring epoching parameters (time-lock).

    Allows selection of events, time window (tmin, tmax), and baseline
    correction. Displays duration info and warnings for short epochs.

    Attributes:
        data_list: List of loaded EEG data objects.
        params: Tuple of (baseline, selected_events, tmin, tmax) after acceptance.
        event_list: QListWidget displaying available event types.
        tmin_spin: QDoubleSpinBox for epoch start time.
        tmax_spin: QDoubleSpinBox for epoch end time.
        duration_label: QLabel showing computed epoch duration.
        warning_label: QLabel showing duration warnings.
        baseline_check: QCheckBox to enable/disable baseline correction.
        b_min_spin: QDoubleSpinBox for baseline start time.
        b_max_spin: QDoubleSpinBox for baseline end time.

    """

    def __init__(self, parent, data_list: list):
        self.data_list = data_list
        self.params: tuple | None = None

        # UI Elements
        self.event_list: QListWidget | None = None
        self.tmin_spin: QDoubleSpinBox | None = None
        self.tmax_spin: QDoubleSpinBox | None = None
        self.duration_label: QLabel | None = None
        self.warning_label: QLabel | None = None
        self.baseline_check: QCheckBox | None = None
        self.b_min_spin: QDoubleSpinBox | None = None
        self.b_max_spin: QDoubleSpinBox | None = None

        super().__init__(parent, title="Time Epoching")
        self.resize(400, 500)

    def init_ui(self):
        """Initialize the dialog UI with event list, parameter controls, and buttons."""
        layout = QVBoxLayout(self)

        # 1. Event Selection
        event_group = QGroupBox("Select Events")
        event_layout = QVBoxLayout()
        self.event_list = QListWidget()
        self.event_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        # Collect all unique events
        events: set[str] = set()
        for data in self.data_list:
            self._extract_events_safely(data, events)

        for ev in sorted(events):
            self.event_list.addItem(str(ev))

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

        self.duration_label.setStyleSheet(Stylesheets.DIALOG_INFO_LABEL)
        form.addRow("Duration:", self.duration_label)

        # Warning label (must be created before update_duration_info is called)
        self.warning_label = QLabel()
        self.warning_label.setStyleSheet(Stylesheets.DIALOG_WARNING_LABEL)
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
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def toggle_baseline(self, checked):
        """Enable or disable baseline correction spin boxes.

        Args:
            checked: Whether baseline correction is enabled.

        """
        if self.b_min_spin:
            self.b_min_spin.setEnabled(checked)
        if self.b_max_spin:
            self.b_max_spin.setEnabled(checked)

    def update_duration_info(self):
        """Update duration information and show warning if duration is too short."""
        if (
            not self.tmin_spin
            or not self.tmax_spin
            or not self.duration_label
            or not self.warning_label
        ):
            return

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
                "generation.",
            )
            self.warning_label.show()
        elif duration < 1.2:
            self.warning_label.setText(
                "Note: Epoch duration < 1.2s may cause issues with high sampling rates "
                "(>250Hz).",
            )
            self.warning_label.show()
        else:
            self.warning_label.hide()

    def accept(self):
        """Validate parameters and accept the dialog.

        Raises:
            QMessageBox: Warning if no events are selected or time range
                is invalid.

        """
        if (
            not self.event_list
            or not self.tmin_spin
            or not self.tmax_spin
            or not self.baseline_check
            or not self.b_min_spin
            or not self.b_max_spin
        ):
            return

        selected_items = self.event_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select at least one event.")
            return

        selected_events = [item.text() for item in selected_items]
        tmin = self.tmin_spin.value()
        tmax = self.tmax_spin.value()

        if tmin >= tmax:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Start time must be less than End time.",
            )
            return

        if (tmax - tmin) < 0.1:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Epoch duration is too short (< 0.1s).",
            )
            return

        baseline = None
        if self.baseline_check.isChecked():
            baseline = (self.b_min_spin.value(), self.b_max_spin.value())

        self.params = (baseline, selected_events, tmin, tmax)
        super().accept()

    def get_params(self):
        """Return the configured epoching parameters.

        Returns:
            Tuple of (baseline, selected_events, tmin, tmax) or None.

        """
        return self.params

    def get_result(self):
        """Return the configured epoching parameters.

        Returns:
            Tuple of (baseline, selected_events, tmin, tmax) or None.

        """
        return self.get_params()

    def _extract_events_safely(self, data, events):
        """Safely extract event names from a data object.

        Args:
            data: EEG data object to extract events from.
            events: Set to add event name strings to.

        """
        try:
            # Use get_event_list which prioritizes imported/resampled events
            _, ev_ids = data.get_event_list()
            if ev_ids:
                events.update(ev_ids.keys())
        except Exception:
            logger.exception("Failed to get event list for data")
