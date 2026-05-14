"""Epoching dialog for configuring time-locked EEG epoch extraction.

Provides controls for selecting events, specifying the time window
(tmin/tmax), and optionally applying baseline correction.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from XBrainLab.backend.application.epoch_context import build_epoching_context
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.styles.stylesheets import Stylesheets


def _label_source_display(value: object) -> str:
    text = str(value or "").strip()
    return {
        "bids_events": "BIDS events",
        "loaded_label_files": "loaded label files",
        "external_files": "loaded label files",
        "embedded_events": "labels inside EEG files",
    }.get(text, text.replace("_", " ") if text else "import")


def _placement_mode_display(values: list[str]) -> str:
    labels = {
        "internal_events": "Events inside EEG files",
        "eeg_event": "EEG event order",
        "time_field": "Label time",
        "interval": "Label interval",
        "event_code": "Label event code",
    }
    displayed = [labels.get(value, value.replace("_", " ")) for value in values]
    return ", ".join(displayed) if displayed else "Manual event selection"


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

    def __init__(
        self,
        parent,
        data_list: list,
        epoch_context: dict | None = None,
        *,
        epoch_handoff: dict | None = None,
    ):
        self.data_list = data_list
        self.epoch_context = self._normalized_epoch_context(
            data_list,
            epoch_context,
            epoch_handoff,
        )
        self.params: tuple | None = None

        # UI Elements
        self.event_list: QListWidget | None = None
        self.handoff_label: QLabel | None = None
        self.tmin_spin: QDoubleSpinBox | None = None
        self.tmax_spin: QDoubleSpinBox | None = None
        self.duration_label: QLabel | None = None
        self.warning_label: QLabel | None = None
        self.baseline_check: QCheckBox | None = None
        self.b_min_spin: QDoubleSpinBox | None = None
        self.b_max_spin: QDoubleSpinBox | None = None

        super().__init__(parent, title="Time Epoching")
        self.resize(620, 680)
        self.setStyleSheet(self._dialog_style())

    def init_ui(self):
        """Initialize the dialog UI with event list, parameter controls, and buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        header = QLabel("Create Epochs")
        header.setObjectName("EpochDialogTitle")
        header.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(header)

        subtitle = QLabel(
            "Choose which events become epochs, then set the time window used "
            "for training."
        )
        subtitle.setObjectName("EpochDialogSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        if self.epoch_context.get("has_import_hint"):
            layout.addWidget(self._build_import_hint_card())

        # 1. Event Selection
        event_group, event_layout = self._build_section_card("Events")
        event_layout.setSpacing(8)
        event_hint = QLabel(self._event_hint_text())
        event_hint.setWordWrap(True)
        event_layout.addWidget(event_hint)
        self.event_list = QListWidget()
        self.event_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        available_events = self.epoch_context.get("available_events") or []
        if not available_events:
            events: set[str] = set()
            for data in self.data_list:
                self._extract_events_safely(data, events)
            available_events = [{"name": str(ev), "count": None} for ev in events]

        recommended_events = set(self.epoch_context.get("recommended_events") or [])
        for event in sorted(available_events, key=self._event_item_sort_key):
            event_name = str(event.get("name") or "").strip()
            if not event_name:
                continue
            self.event_list.addItem(event_name)
            item = self.event_list.item(self.event_list.count() - 1)
            if item is None:
                continue
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            count = event.get("count")
            if count is not None:
                item.setToolTip(f"{event_name}: {count} event(s)")
            if event_name in recommended_events:
                item.setCheckState(Qt.CheckState.Checked)
                item.setSelected(True)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)

        self.event_list.setMinimumHeight(
            min(260, max(130, self.event_list.count() * 31 + 28)),
        )
        self.event_list.setMaximumHeight(260)
        event_layout.addWidget(self.event_list)
        layout.addWidget(event_group)

        # 2. Parameters
        param_group, param_layout = self._build_section_card("Time Window")

        self.tmin_spin = QDoubleSpinBox()
        self.tmin_spin.setRange(-10, 10)
        self.tmin_spin.setValue(float(self.epoch_context.get("suggested_t_min", -0.2)))
        self.tmin_spin.setSingleStep(0.1)
        self._configure_compact_spinbox(self.tmin_spin)
        self.tmin_spin.valueChanged.connect(self.update_duration_info)

        self.tmax_spin = QDoubleSpinBox()
        self.tmax_spin.setRange(-10, 10)
        self.tmax_spin.setValue(float(self.epoch_context.get("suggested_t_max", 1.0)))
        self.tmax_spin.setSingleStep(0.1)
        self._configure_compact_spinbox(self.tmax_spin)
        self.tmax_spin.valueChanged.connect(self.update_duration_info)

        window_grid = QGridLayout()
        window_grid.setContentsMargins(0, 2, 0, 0)
        window_grid.setHorizontalSpacing(12)
        window_grid.setVerticalSpacing(8)
        window_grid.addWidget(self._field_label("Start (s)"), 0, 0)
        window_grid.addWidget(self.tmin_spin, 0, 1)
        window_grid.addWidget(self._field_label("End (s)"), 0, 2)
        window_grid.addWidget(self.tmax_spin, 0, 3)

        # Duration info label
        self.duration_label = QLabel()
        self.duration_label.setObjectName("EpochDialogValue")
        self.duration_label.setStyleSheet(Stylesheets.DIALOG_INFO_LABEL)
        window_grid.addWidget(self._field_label("Duration"), 1, 0)
        window_grid.addWidget(self.duration_label, 1, 1, 1, 3)

        window_evidence = str(self.epoch_context.get("window_evidence") or "").strip()
        if window_evidence:
            evidence_label = QLabel(window_evidence)
            evidence_label.setObjectName("EpochDialogEvidence")
            evidence_label.setWordWrap(True)
            window_grid.addWidget(self._field_label("Suggested by"), 2, 0)
            window_grid.addWidget(evidence_label, 2, 1, 1, 3)

        # Warning label (must be created before update_duration_info is called)
        self.warning_label = QLabel()
        self.warning_label.setStyleSheet(Stylesheets.DIALOG_WARNING_LABEL)
        self.warning_label.setWordWrap(True)
        window_grid.addWidget(self.warning_label, 3, 0, 1, 4)
        window_grid.setColumnStretch(4, 1)
        param_layout.addLayout(window_grid)

        # Now update duration info (which uses warning_label)
        self.update_duration_info()

        # Baseline
        suggested_baseline = self.epoch_context.get("suggested_baseline")
        self.baseline_check = QCheckBox("Apply baseline correction")
        self.baseline_check.setChecked(suggested_baseline is not None)
        self.baseline_check.toggled.connect(self.toggle_baseline)
        param_layout.addWidget(self.baseline_check)

        self.b_min_spin = QDoubleSpinBox()
        self.b_min_spin.setRange(-10, 10)
        baseline_min = (
            suggested_baseline[0]
            if isinstance(suggested_baseline, (list, tuple))
            and suggested_baseline
            and suggested_baseline[0] is not None
            else -0.2
        )
        self.b_min_spin.setValue(float(baseline_min))
        self._configure_compact_spinbox(self.b_min_spin)

        self.b_max_spin = QDoubleSpinBox()
        self.b_max_spin.setRange(-10, 10)
        baseline_max = (
            suggested_baseline[1]
            if isinstance(suggested_baseline, (list, tuple))
            and len(suggested_baseline) > 1
            and suggested_baseline[1] is not None
            else 0.0
        )
        self.b_max_spin.setValue(float(baseline_max))
        self._configure_compact_spinbox(self.b_max_spin)

        baseline_grid = QGridLayout()
        baseline_grid.setContentsMargins(0, 0, 0, 0)
        baseline_grid.setHorizontalSpacing(12)
        baseline_grid.setVerticalSpacing(8)
        baseline_grid.addWidget(self._field_label("Baseline Min (s)"), 0, 0)
        baseline_grid.addWidget(self.b_min_spin, 0, 1)
        baseline_grid.addWidget(self._field_label("Baseline Max (s)"), 0, 2)
        baseline_grid.addWidget(self.b_max_spin, 0, 3)
        baseline_grid.setColumnStretch(4, 1)
        param_layout.addLayout(baseline_grid)
        self.toggle_baseline(self.baseline_check.isChecked())

        layout.addWidget(param_group)

        footer_rule = QFrame()
        footer_rule.setObjectName("EpochFooterRule")
        footer_rule.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(footer_rule)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("EpochSecondaryButton")
        cancel_button.clicked.connect(self.reject)
        footer.addWidget(cancel_button)
        footer.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("Create Epochs")
            ok_button.setObjectName("EpochPrimaryButton")
        buttons.accepted.connect(self.accept)
        footer.addWidget(buttons)
        layout.addLayout(footer)

    def _build_section_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("EpochSectionCard")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 13, 16, 14)
        card_layout.setSpacing(9)
        title_label = QLabel(title)
        title_label.setObjectName("EpochSectionTitle")
        card_layout.addWidget(title_label)
        return card, card_layout

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("EpochFieldLabel")
        return label

    @staticmethod
    def _configure_compact_spinbox(spinbox: QDoubleSpinBox) -> None:
        spinbox.setMinimumWidth(116)
        spinbox.setMaximumWidth(150)
        spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

    def _build_import_hint_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("EpochImportHintCard")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        card.setStyleSheet(
            """
            QFrame#EpochImportHintCard {
                border: 1px solid rgba(120, 130, 145, 0.45);
                border-radius: 6px;
                padding: 8px;
            }
            QLabel#EpochImportHintTitle {
                font-weight: 700;
            }
            QLabel#EpochImportHintKey {
                color: #aeb6c2;
                font-weight: 600;
            }
            QLabel#EpochImportHintValue {
                font-weight: 600;
            }
            """
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        title_row = QHBoxLayout()
        title = QLabel("Suggested from import")
        title.setObjectName("EpochImportHintTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        handoff_summary = self._handoff_summary_text()
        if handoff_summary:
            summary = QLabel(handoff_summary)
            summary.setObjectName("EpochImportHintSummary")
            summary.setWordWrap(True)
            self.handoff_label = summary
            layout.addWidget(summary)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        rows = [
            ("Source", self.epoch_context.get("source")),
            ("Placement", self.epoch_context.get("placement_label")),
            ("Timing", self._timing_summary_text()),
        ]
        label_field = str(self.epoch_context.get("label_field") or "").strip()
        if label_field:
            rows.insert(2, ("Label field", label_field))
        for row, (label, value) in enumerate(rows):
            key = QLabel(label)
            key.setObjectName("EpochImportHintKey")
            val = QLabel(str(value or "Review manually"))
            val.setObjectName("EpochImportHintValue")
            val.setWordWrap(True)
            grid.addWidget(key, row // 2, (row % 2) * 2)
            grid.addWidget(val, row // 2, (row % 2) * 2 + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        layout.addLayout(grid)
        return card

    def _event_hint_text(self) -> str:
        recommended = self.epoch_context.get("recommended_events") or []
        if recommended:
            return (
                "Suggested class events are checked. Adjust this list if the import "
                "matched the wrong labels."
            )
        return "Select the event types that should become training epochs."

    def _timing_summary_text(self) -> str:
        time_field = str(self.epoch_context.get("time_field") or "").strip()
        duration_field = str(self.epoch_context.get("duration_field") or "").strip()
        if time_field and duration_field:
            return f"{time_field} + {duration_field}"
        if time_field:
            return time_field
        return "Event onset"

    @staticmethod
    def _normalized_epoch_context(
        data_list: list,
        epoch_context: dict | None,
        epoch_handoff: dict | None,
    ) -> dict:
        if epoch_context is not None:
            return dict(epoch_context)
        context = build_epoching_context(data_list)
        if not epoch_handoff:
            return dict(context)
        handoff = dict(epoch_handoff)
        blockers = [str(item) for item in handoff.get("supervised_blockers", [])]
        ready = bool(handoff.get("ready")) and not blockers
        placement_modes = [
            str(item).strip()
            for item in handoff.get("placement_modes", []) or []
            if str(item).strip()
        ]
        default_events = [
            str(item).strip()
            for item in handoff.get("default_epoch_events", []) or []
            if str(item).strip()
        ]
        context.update(
            {
                "source": _label_source_display(handoff.get("label_source")),
                "placement_method": placement_modes[0] if placement_modes else "manual",
                "placement_label": _placement_mode_display(placement_modes),
                "recommended_events": default_events if ready else [],
                "has_import_hint": True,
                "epoch_handoff": handoff,
                "handoff_ready": ready,
                "handoff_blockers": blockers,
            }
        )
        return context

    def _handoff_summary_text(self) -> str:
        handoff = self.epoch_context.get("epoch_handoff")
        if isinstance(handoff, dict):
            blockers = self.epoch_context.get("handoff_blockers") or []
            source = str(self.epoch_context.get("source") or "import").strip()
            if blockers:
                blocker_text = "; ".join(str(item) for item in blockers)
                return f"{source} needs review: {blocker_text}"
            return f"Suggested from {source}."
        if self.epoch_context.get("has_import_hint"):
            return "Import choices are available for this epoch setup."
        return ""

    @staticmethod
    def _event_item_sort_key(item: dict) -> tuple[int, int | str]:
        text = str(item.get("name") or "").strip()
        if text.isdigit():
            return (0, int(text))
        return (1, text.casefold())

    @staticmethod
    def _dialog_style() -> str:
        return """
        QDialog {
            background: #1b1b1d;
            color: #f2f5f8;
        }
        QLabel {
            color: #f2f5f8;
        }
        QLabel#EpochDialogSubtitle,
        QLabel#EpochDialogEvidence {
            color: #bac2cc;
        }
        QFrame#EpochSectionCard {
            background: #222426;
            border: 1px solid #3b3f45;
            border-radius: 6px;
        }
        QLabel#EpochSectionTitle {
            color: #f2f5f8;
            font-size: 15px;
            font-weight: 700;
        }
        QLabel#EpochFieldLabel {
            color: #d8dde4;
            font-weight: 600;
        }
        QFrame#EpochImportHintCard {
            background: #222426;
            border: 1px solid #3d454d;
            border-radius: 6px;
        }
        QLabel#EpochImportHintKey {
            color: #aeb6c2;
            font-weight: 600;
        }
        QLabel#EpochImportHintValue {
            color: #f2f5f8;
            font-weight: 700;
        }
        QListWidget {
            background: #18191b;
            color: #f2f5f8;
            border: 1px solid #3d454d;
            border-radius: 4px;
            padding: 5px;
            outline: 0;
        }
        QListWidget::item {
            color: #f2f5f8;
            min-height: 24px;
            padding: 3px 6px;
            border-radius: 3px;
        }
        QListWidget::item:selected {
            background: #263444;
        }
        QDoubleSpinBox {
            background: #25272a;
            color: #f2f5f8;
            border: 1px solid #3d454d;
            border-radius: 4px;
            padding: 4px 6px;
        }
        QDoubleSpinBox:disabled {
            color: #7f8791;
            background: #202124;
        }
        QCheckBox {
            color: #f2f5f8;
            spacing: 8px;
        }
        QFrame#EpochFooterRule {
            color: #343941;
            background: #343941;
            max-height: 1px;
        }
        QPushButton {
            min-width: 128px;
            padding: 6px 12px;
            border-radius: 4px;
            border: 1px solid #454b52;
            background: #2a2c30;
            color: #f2f5f8;
        }
        QPushButton:hover {
            background: #32363b;
        }
        QPushButton#EpochPrimaryButton,
        QPushButton:default {
            background: #0069a8;
            border-color: #0a7fc7;
            font-weight: 700;
        }
        QPushButton#EpochSecondaryButton {
            min-width: 84px;
        }
        """

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

        checked_items: list[QListWidgetItem] = []
        for index in range(self.event_list.count()):
            item = self.event_list.item(index)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                checked_items.append(item)
        selected_items = checked_items or self.event_list.selectedItems()
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
