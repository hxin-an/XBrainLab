"""Epoching dialog for configuring time-locked EEG epoch extraction.

Provides controls for selecting events, specifying the time window
(tmin/tmax), and optionally applying baseline correction.
"""

from contextlib import suppress
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QEvent, QSize, Qt
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QCheckBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.epoch_context import (
    EpochContextAvailability,
    EpochContextAvailabilityCode,
    EpochWindowMode,
    build_epoch_confirmation_requirement,
    epoch_handoff_matches_context,
    validated_epoch_context_availability,
    validated_epoch_window_mode,
)
from XBrainLab.ui.components.presentation import fit_table_to_all_rows
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import (
    checkbox_stylesheet,
    configure_dark_table,
    normalize_dialog_button_box,
    preprocess_toggle_stylesheet,
)
from XBrainLab.ui.styles.stylesheets import Stylesheets


def _label_source_display(value: object) -> str:
    text = str(value or "").strip()
    return {
        "bids_events": "BIDS events",
        "loaded_label_files": "loaded label files",
        "external_files": "loaded label files",
        "embedded_events": "labels inside EEG files",
        "internal_events": "labels inside EEG files",
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


_BASELINE_ORDER_ERROR = "Baseline start must be less than or equal to baseline end."
_BASELINE_WINDOW_ERROR = "Baseline must stay inside the EEG epoch time window."
_WINDOW_MODE_REVIEW_TITLE = "Review epoch window"
_WINDOW_MODE_REVIEW_MESSAGE = (
    "The epoch window mode needs review before EEG epochs can be created. "
    "Return to Data Import and review the event timing, then reopen this dialog."
)
_EPOCH_DIALOG_MINIMUM_SIZE = QSize(700, 740)


def validate_epoch_baseline(
    *,
    enabled: bool,
    baseline_min: float,
    baseline_max: float,
    t_min: float,
    t_max: float,
) -> str | None:
    """Return the baseline validation error shared by live and submit paths."""
    if not enabled:
        return None
    if baseline_min > baseline_max:
        return _BASELINE_ORDER_ERROR
    if baseline_min < t_min or baseline_max > t_max:
        return _BASELINE_WINDOW_ERROR
    return None


class EpochSubmissionIssue(str, Enum):
    """One user-actionable reason the current epoch proposal cannot submit."""

    NONE = "none"
    CONTEXT_UNAVAILABLE = "context_unavailable"
    EVENTS_REQUIRED = "events_required"
    TIME_ORDER = "time_order"
    MINIMUM_DURATION = "minimum_duration"
    BASELINE = "baseline"
    CONFIRMATION_REQUIRED = "confirmation_required"


@dataclass(frozen=True)
class EpochSubmissionValidation:
    """Pure validation result shared by live enablement and acceptance."""

    issue: EpochSubmissionIssue
    title: str
    message: str

    @property
    def allowed(self) -> bool:
        return self.issue is EpochSubmissionIssue.NONE


def validate_epoch_submission(
    *,
    context_available: bool,
    context_unavailable_reason: str,
    window_mode: object,
    selected_events: list[str],
    t_min: float,
    t_max: float,
    baseline_enabled: bool,
    baseline_min: float,
    baseline_max: float,
    confirmation_required: bool,
    confirmation_accepted: bool,
    confirmation_title: str,
    confirmation_message: str,
) -> EpochSubmissionValidation:
    """Validate every condition controlling the Create EEG Epochs action."""
    try:
        validated_epoch_window_mode(window_mode)
    except ValueError:
        context_available = False
    if not context_available:
        return EpochSubmissionValidation(
            EpochSubmissionIssue.CONTEXT_UNAVAILABLE,
            _WINDOW_MODE_REVIEW_TITLE,
            str(context_unavailable_reason).strip() or _WINDOW_MODE_REVIEW_MESSAGE,
        )
    if not selected_events:
        return EpochSubmissionValidation(
            EpochSubmissionIssue.EVENTS_REQUIRED,
            "Warning",
            "Please select at least one event.",
        )
    if t_min >= t_max:
        return EpochSubmissionValidation(
            EpochSubmissionIssue.TIME_ORDER,
            "Invalid Input",
            "Start time must be less than End time.",
        )
    if (t_max - t_min) < 0.1:
        return EpochSubmissionValidation(
            EpochSubmissionIssue.MINIMUM_DURATION,
            "Invalid Input",
            "EEG epoch duration is too short (< 0.1s).",
        )
    baseline_error = validate_epoch_baseline(
        enabled=baseline_enabled,
        baseline_min=baseline_min,
        baseline_max=baseline_max,
        t_min=t_min,
        t_max=t_max,
    )
    if baseline_error is not None:
        return EpochSubmissionValidation(
            EpochSubmissionIssue.BASELINE,
            "Invalid Input",
            baseline_error,
        )
    if confirmation_required and not confirmation_accepted:
        return EpochSubmissionValidation(
            EpochSubmissionIssue.CONFIRMATION_REQUIRED,
            confirmation_title,
            confirmation_message,
        )
    return EpochSubmissionValidation(EpochSubmissionIssue.NONE, "", "")


class EpochingDialog(BaseDialog):
    """Dialog for configuring epoching parameters (time-lock).

    Allows selection of events, time window (tmin, tmax), and baseline
    correction. Displays duration info and warnings for short epochs.

    Attributes:
        params: Tuple of (baseline, selected_events, tmin, tmax) after acceptance.
        event_list: QTableWidget displaying available event types.
        tmin_spin: QDoubleSpinBox for epoch start time.
        tmax_spin: QDoubleSpinBox for epoch end time.
        duration_label: QLabel showing computed epoch duration.
        warning_label: QLabel showing duration warnings.
        baseline_check: QPushButton to enable/disable baseline correction.
        b_min_spin: QDoubleSpinBox for baseline start time.
        b_max_spin: QDoubleSpinBox for baseline end time.

    """

    def __init__(
        self,
        parent,
        *,
        epoch_context: dict,
        epoch_handoff: dict | None = None,
        assistant_suggestions: dict[str, str] | None = None,
    ):
        if not isinstance(epoch_context, dict):
            raise TypeError("epoch_context must be a detached dictionary")
        self.epoch_context = self._normalized_epoch_context(
            epoch_context,
            epoch_handoff,
            assistant_suggestions,
        )
        try:
            self.context_availability = validated_epoch_context_availability(
                self.epoch_context
            )
        except ValueError:
            self.context_availability = EpochContextAvailability.unavailable(
                EpochContextAvailabilityCode.INVALID_CONTEXT,
                _WINDOW_MODE_REVIEW_MESSAGE,
            )
        self.window_mode = self.context_availability.window_mode
        self.params: tuple | None = None
        self.confirmation_requirement: dict | None = None
        self.confirmation_receipt: str | None = None

        # UI Elements
        self.event_list: QTableWidget | None = None
        self.handoff_label: QLabel | None = None
        self.tmin_spin: QDoubleSpinBox | None = None
        self.tmax_spin: QDoubleSpinBox | None = None
        self.duration_label: QLabel | None = None
        self.warning_label: QLabel | None = None
        self.confirmation_check: QCheckBox | None = None
        self.baseline_check: QPushButton | None = None
        self.baseline_group: QFrame | None = None
        self.baseline_content: QWidget | None = None
        self.baseline_title_label: QLabel | None = None
        self.baseline_help_label: QLabel | None = None
        self.baseline_min_label: QLabel | None = None
        self.baseline_max_label: QLabel | None = None
        self.b_min_spin: QDoubleSpinBox | None = None
        self.b_max_spin: QDoubleSpinBox | None = None
        self.baseline_error_label: QLabel | None = None
        self.create_button: QPushButton | None = None
        self.content_scroll: QScrollArea | None = None
        self._content_fit_ready = False

        super().__init__(parent, title="Time Epoching")
        self.resize(_EPOCH_DIALOG_MINIMUM_SIZE)
        self.setStyleSheet(self._dialog_style())
        self._content_fit_ready = True
        self._grow_to_visible_content()

    def showEvent(self, event: QShowEvent | None) -> None:  # noqa: N802
        """Finish native content fitting before the first visible paint."""
        self._grow_to_visible_content()
        super().showEvent(event)

    def changeEvent(self, event: QEvent | None) -> None:  # noqa: N802
        """Grow again when native font or style metrics change."""
        super().changeEvent(event)
        if event is not None and event.type() in {
            QEvent.Type.ApplicationFontChange,
            QEvent.Type.DevicePixelRatioChange,
            QEvent.Type.FontChange,
            QEvent.Type.StyleChange,
        }:
            self._grow_to_visible_content()

    def init_ui(self):
        """Initialize the dialog UI with event list, parameter controls, and buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setSpacing(8)

        content = QWidget()
        content.setObjectName("EpochDialogContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setObjectName("EpochDialogContentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(content)
        self.content_scroll = scroll

        header = QLabel("Create EEG Epochs")
        header.setObjectName("EpochDialogTitle")
        header.setStyleSheet(
            "background-color: transparent; font-size: 18px; font-weight: 700;"
        )
        content_layout.addWidget(header)

        subtitle = QLabel(
            "Choose which events become EEG epochs, then set the analysis time window."
        )
        subtitle.setObjectName("EpochDialogSubtitle")
        subtitle.setWordWrap(True)
        content_layout.addWidget(subtitle)

        if self.epoch_context.get("has_import_hint"):
            content_layout.addWidget(self._build_import_hint_card())

        # 1. Event Selection
        event_group, _, event_layout = self._build_section_card("Events")
        event_layout.setSpacing(6)
        event_hint = QLabel(self._event_hint_text())
        event_hint.setWordWrap(True)
        event_layout.addWidget(event_hint)
        event_list = QTableWidget()
        self.event_list = event_list
        event_list.setColumnCount(4)
        event_list.setHorizontalHeaderLabels(["Use", "Event", "Type", "Count"])
        configure_dark_table(event_list, object_name="EpochEventTable")
        event_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        event_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        event_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        event_list.setShowGrid(False)
        # This public, visible table is the downstream projection of the
        # backend-owned applied handoff.  It deliberately includes kept
        # non-class events: the checked rows below are only the supervised
        # epoch selection, not the import's complete event catalog.
        event_list.setProperty(
            "appliedEventCatalog",
            self._applied_event_catalog_evidence(),
        )
        event_vertical_header = event_list.verticalHeader()
        if event_vertical_header is not None:
            event_vertical_header.setDefaultSectionSize(25)
            event_vertical_header.setMinimumSectionSize(24)

        available_events = self.epoch_context.get("available_events") or []

        recommended_events = set(self.epoch_context.get("recommended_events") or [])
        rows = []
        for event in sorted(available_events, key=self._event_item_sort_key):
            event_name = str(event.get("name") or "").strip()
            if not event_name:
                continue
            rows.append((event_name, event))

        event_list.setRowCount(len(rows))
        for row, (event_name, event) in enumerate(rows):
            use_item = QTableWidgetItem("")
            use_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            use_item.setCheckState(
                Qt.CheckState.Checked
                if event_name in recommended_events
                else Qt.CheckState.Unchecked
            )
            event_list.setItem(row, 0, use_item)

            event_item = QTableWidgetItem(event_name)
            event_item.setFlags(event_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            event_list.setItem(row, 1, event_item)

            event_type = (
                "Training label"
                if event_name in recommended_events
                else "Available event"
            )
            type_item = QTableWidgetItem(event_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            event_list.setItem(row, 2, type_item)

            count = event.get("count")
            count_text = f"{count} events" if count is not None else "-"
            count_item = QTableWidgetItem(count_text)
            count_item.setFlags(count_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            event_list.setItem(row, 3, count_item)
            if count is not None:
                for col in range(4):
                    item = event_list.item(row, col)
                    if item is not None:
                        item.setToolTip(f"{event_name}: {count} event(s)")

        event_header = event_list.horizontalHeader()
        if event_header is not None:
            event_header.setSectionResizeMode(
                0,
                QHeaderView.ResizeMode.ResizeToContents,
            )
            event_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            event_header.setSectionResizeMode(
                2,
                QHeaderView.ResizeMode.ResizeToContents,
            )
            event_header.setSectionResizeMode(
                3,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        fit_table_to_all_rows(event_list)
        event_list.itemChanged.connect(self._confirmation_scope_changed)
        event_layout.addWidget(event_list)
        content_layout.addWidget(event_group)

        # 2. Parameters
        param_group, _, param_layout = self._build_section_card("Time Window")
        window_mode_text = self._window_mode_text()
        if window_mode_text:
            mode_label = QLabel(window_mode_text)
            mode_label.setObjectName("EpochWindowModeLabel")
            mode_label.setWordWrap(True)
            param_layout.addWidget(mode_label)

        tmin_spin = QDoubleSpinBox()
        self.tmin_spin = tmin_spin
        tmin_spin.setObjectName("EpochStartInput")
        tmin_spin.setRange(-300, 300)
        tmin_spin.setValue(float(self.epoch_context.get("suggested_t_min", -0.2)))
        tmin_spin.setSingleStep(0.1)
        self._configure_compact_spinbox(tmin_spin)
        tmin_spin.valueChanged.connect(self.update_duration_info)
        tmin_spin.valueChanged.connect(self._confirmation_scope_changed)

        tmax_spin = QDoubleSpinBox()
        self.tmax_spin = tmax_spin
        tmax_spin.setObjectName("EpochEndInput")
        tmax_spin.setRange(-300, 300)
        tmax_spin.setDecimals(
            max(
                2,
                min(
                    int(self.epoch_context.get("suggested_t_max_decimals", 2)),
                    9,
                ),
            )
        )
        tmax_spin.setValue(float(self.epoch_context.get("suggested_t_max", 1.0)))
        tmax_spin.setSingleStep(0.1)
        self._configure_compact_spinbox(tmax_spin)
        tmax_spin.valueChanged.connect(self.update_duration_info)
        tmax_spin.valueChanged.connect(self._confirmation_scope_changed)

        window_grid = QGridLayout()
        window_grid.setContentsMargins(0, 2, 0, 0)
        window_grid.setHorizontalSpacing(12)
        window_grid.setVerticalSpacing(8)
        window_grid.addWidget(self._field_label("Start (s)"), 0, 0)
        window_grid.addWidget(tmin_spin, 0, 1)
        window_grid.addWidget(self._field_label("End (s)"), 0, 2)
        window_grid.addWidget(tmax_spin, 0, 3)

        # Duration info label
        duration_label = QLabel()
        self.duration_label = duration_label
        duration_label.setObjectName("EpochDialogValue")
        duration_label.setStyleSheet(Stylesheets.DIALOG_INFO_LABEL)
        window_grid.addWidget(self._field_label("Duration"), 1, 0)
        window_grid.addWidget(duration_label, 1, 1, 1, 3)

        window_evidence = str(self.epoch_context.get("window_evidence") or "").strip()
        if window_evidence:
            evidence_label = QLabel(window_evidence)
            evidence_label.setObjectName("EpochDialogEvidence")
            evidence_label.setWordWrap(True)
            window_grid.addWidget(self._field_label("Suggested by"), 2, 0)
            window_grid.addWidget(evidence_label, 2, 1, 1, 3)

        # Warning label (must be created before update_duration_info is called)
        warning_label = QLabel()
        self.warning_label = warning_label
        warning_label.setStyleSheet(Stylesheets.DIALOG_WARNING_LABEL)
        warning_label.setWordWrap(True)
        window_grid.addWidget(warning_label, 3, 0, 1, 4)

        confirmation_check = QCheckBox()
        self.confirmation_check = confirmation_check
        confirmation_check.setObjectName("EpochConfirmationCheck")
        confirmation_check.toggled.connect(self._refresh_submit_validity)
        confirmation_check.hide()
        window_grid.addWidget(confirmation_check, 4, 0, 1, 4)
        window_grid.setColumnStretch(4, 1)
        param_layout.addLayout(window_grid)

        # Now update duration info (which uses warning_label)
        self.update_duration_info()
        self._refresh_confirmation_requirement()

        content_layout.addWidget(param_group)

        # Baseline
        suggested_baseline = self.epoch_context.get("suggested_baseline")
        baseline_check = self._toggle_button(
            checked=self._baseline_is_inside_window(suggested_baseline)
        )
        self.baseline_check = baseline_check
        baseline_check.setAccessibleName("Baseline correction")
        baseline_check.setToolTip("Enable or disable baseline correction.")
        (
            baseline_group,
            self.baseline_title_label,
            baseline_layout,
        ) = self._build_section_card(
            "Baseline Correction",
            header_action=baseline_check,
        )
        baseline_group.setObjectName("EpochBaselineSection")
        self.baseline_group = baseline_group

        baseline_content = QWidget()
        self.baseline_content = baseline_content
        baseline_content.setObjectName("EpochBaselineContent")
        baseline_content.setAutoFillBackground(False)
        baseline_content_layout = QVBoxLayout(baseline_content)
        baseline_content_layout.setContentsMargins(0, 0, 0, 0)
        baseline_content_layout.setSpacing(6)

        baseline_help_label = QLabel(
            "When enabled, the average signal in this interval will be removed "
            "from each epoch."
        )
        self.baseline_help_label = baseline_help_label
        baseline_help_label.setObjectName("EpochDialogEvidence")
        baseline_help_label.setWordWrap(True)
        baseline_content_layout.addWidget(baseline_help_label)
        baseline_check.toggled.connect(self.toggle_baseline)

        b_min_spin = QDoubleSpinBox()
        self.b_min_spin = b_min_spin
        b_min_spin.setObjectName("EpochBaselineStartInput")
        b_min_spin.setRange(-300, 300)
        baseline_min = (
            suggested_baseline[0]
            if isinstance(suggested_baseline, (list, tuple))
            and suggested_baseline
            and suggested_baseline[0] is not None
            else -0.2
        )
        b_min_spin.setValue(float(baseline_min))
        self._configure_compact_spinbox(b_min_spin)

        b_max_spin = QDoubleSpinBox()
        self.b_max_spin = b_max_spin
        b_max_spin.setObjectName("EpochBaselineEndInput")
        b_max_spin.setRange(-300, 300)
        baseline_max = (
            suggested_baseline[1]
            if isinstance(suggested_baseline, (list, tuple))
            and len(suggested_baseline) > 1
            and suggested_baseline[1] is not None
            else 0.0
        )
        b_max_spin.setValue(float(baseline_max))
        self._configure_compact_spinbox(b_max_spin)
        b_min_spin.valueChanged.connect(self._refresh_submit_validity)
        b_max_spin.valueChanged.connect(self._refresh_submit_validity)

        baseline_grid = QGridLayout()
        baseline_grid.setContentsMargins(0, 0, 0, 0)
        baseline_grid.setHorizontalSpacing(12)
        baseline_grid.setVerticalSpacing(8)
        self.baseline_min_label = self._field_label("Baseline Min (s)")
        baseline_grid.addWidget(self.baseline_min_label, 0, 0)
        baseline_grid.addWidget(b_min_spin, 0, 1)
        self.baseline_max_label = self._field_label("Baseline Max (s)")
        baseline_grid.addWidget(self.baseline_max_label, 0, 2)
        baseline_grid.addWidget(b_max_spin, 0, 3)
        baseline_grid.setColumnStretch(4, 1)
        baseline_content_layout.addLayout(baseline_grid)
        baseline_error_label = QLabel()
        self.baseline_error_label = baseline_error_label
        baseline_error_label.setObjectName("EpochBaselineError")
        baseline_error_label.setStyleSheet(Stylesheets.DIALOG_WARNING_LABEL)
        baseline_error_label.setWordWrap(True)
        baseline_error_label.hide()
        baseline_content_layout.addWidget(baseline_error_label)
        baseline_layout.addWidget(baseline_content)
        self.toggle_baseline(baseline_check.isChecked())

        content_layout.addWidget(baseline_group)
        layout.addWidget(scroll, stretch=1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("EpochSecondaryButton")
        cancel_button.clicked.connect(self.reject)
        footer.addWidget(cancel_button)
        footer.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        normalize_dialog_button_box(buttons, ok_text="Confirm")
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setObjectName("EpochPrimaryButton")
            self.create_button = ok_button
        buttons.accepted.connect(self.accept)
        footer.addWidget(buttons)
        layout.addLayout(footer)
        self._refresh_submit_validity()

    def _grow_to_visible_content(self) -> None:
        """Use spare screen height before asking users to scroll the content."""
        scroll = self.content_scroll
        if not self._content_fit_ready or scroll is None:
            return
        content = scroll.widget()
        if content is None:
            return

        self.ensurePolished()
        content.ensurePolished()
        content_layout = content.layout()
        if content_layout is not None:
            content_layout.activate()
        content.updateGeometry()
        scroll.updateGeometry()
        root_layout = self.layout()
        if root_layout is not None:
            root_layout.activate()

        content_height = max(
            content.sizeHint().height(),
            content.minimumSizeHint().height(),
        )
        chrome_height = 0
        if root_layout is not None:
            margins = root_layout.contentsMargins()
            chrome_height = margins.top() + margins.bottom()
            for index in range(root_layout.count()):
                item = root_layout.itemAt(index)
                if item is None or item.widget() is scroll:
                    continue
                chrome_height += max(
                    item.sizeHint().height(),
                    item.minimumSize().height(),
                )
            chrome_height += max(root_layout.count() - 1, 0) * max(
                root_layout.spacing(),
                0,
            )
        target_size = QSize(
            max(self.width(), _EPOCH_DIALOG_MINIMUM_SIZE.width()),
            max(
                self.height(),
                _EPOCH_DIALOG_MINIMUM_SIZE.height(),
                content_height + chrome_height,
            ),
        )
        if target_size != self.size():
            self.resize_preserving_center(target_size)

    def _build_section_card(
        self,
        title: str,
        *,
        header_action: QWidget | None = None,
    ) -> tuple[QFrame, QLabel, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("EpochSectionCard")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 9, 12, 10)
        card_layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("EpochSectionTitle")
        if header_action is None:
            card_layout.addWidget(title_label)
        else:
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.addWidget(title_label)
            header.addStretch()
            header.addWidget(header_action)
            card_layout.addLayout(header)
        return card, title_label, card_layout

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

    @staticmethod
    def _toggle_button(*, checked: bool) -> QPushButton:
        button = QPushButton()
        button.setObjectName("PreprocessToggle")
        button.setCheckable(True)
        button.setChecked(checked)
        button.setAutoDefault(False)
        button.setDefault(False)
        button.toggled.connect(
            lambda _checked, owned=button: EpochingDialog._sync_toggle_text(owned)
        )
        EpochingDialog._sync_toggle_text(button)
        return button

    @staticmethod
    def _sync_toggle_text(button: QPushButton) -> None:
        button.setText("On" if button.isChecked() else "Off")

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
                background-color: transparent;
                font-weight: 700;
            }
            QLabel#EpochImportHintSummary {
                background-color: transparent;
            }
            QLabel#EpochImportHintKey {
                background-color: transparent;
                color: #aeb6c2;
                font-weight: 600;
            }
            QLabel#EpochImportHintValue {
                background-color: transparent;
                font-weight: 600;
            }
            """
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(11, 8, 11, 8)
        layout.setSpacing(6)
        title_row = QHBoxLayout()
        title = QLabel(
            "BIDS events from import"
            if self._is_bids_epoch_context()
            else "Suggested from import"
        )
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
        label_field = str(self.epoch_context.get("label_field") or "").strip()
        if self._is_bids_epoch_context():
            rows = []
            if label_field:
                rows.append(("Label field", label_field))
            rows.extend(
                [
                    ("Epoch anchor", "Event onset"),
                    ("Window mode", self._effective_window_mode_text()),
                ]
            )
        else:
            rows = [
                ("Source", self.epoch_context.get("source")),
                ("Timing", self._timing_summary_text()),
                ("Placement", self.epoch_context.get("placement_label")),
            ]
            if label_field:
                rows.insert(2, ("Label field", label_field))
        pairs_per_row = 2
        for row, (label, value) in enumerate(rows):
            key = QLabel(label)
            key.setObjectName("EpochImportHintKey")
            val = QLabel(str(value or "Review manually"))
            val.setObjectName("EpochImportHintValue")
            val.setWordWrap(True)
            grid_row = row // pairs_per_row
            grid_column = (row % pairs_per_row) * 2
            grid.addWidget(key, grid_row, grid_column)
            grid.addWidget(val, grid_row, grid_column + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        layout.addLayout(grid)
        return card

    def _event_hint_text(self) -> str:
        recommended = self.epoch_context.get("recommended_events") or []
        if self._is_bids_epoch_context() and recommended:
            return (
                "These labels were confirmed in Match Labels. Uncheck a class only "
                "if this EEG epoch setup should use a subset."
            )
        if recommended:
            return (
                "Suggested class events are checked. Adjust this list if the import "
                "matched the wrong labels."
            )
        return "Select the event types that should become EEG epochs."

    def _timing_summary_text(self) -> str:
        time_field = str(self.epoch_context.get("time_field") or "").strip()
        duration_field = str(self.epoch_context.get("duration_field") or "").strip()
        if time_field and duration_field:
            return f"{time_field} + {duration_field}"
        if time_field:
            return time_field
        return "Event onset"

    def _effective_window_mode_text(self) -> str:
        if self.window_mode is EpochWindowMode.DURATION:
            return "Fixed to largest duration"
        if self.window_mode is EpochWindowMode.EVENT_LOCKED:
            return "Event-locked"
        return "Needs review"

    def _is_bids_epoch_context(self) -> bool:
        source = str(self.epoch_context.get("source") or "").casefold()
        return "bids" in source and "event" in source

    def _window_mode_text(self) -> str:
        if not self.context_availability.available:
            return self.context_availability.reason
        if not self._is_bids_epoch_context():
            return ""
        return self.context_availability.window_explanation

    @staticmethod
    def _normalized_epoch_context(
        epoch_context: dict,
        epoch_handoff: dict | None,
        assistant_suggestions: dict[str, str] | None,
    ) -> dict:
        context = dict(epoch_context)
        handoff = dict(epoch_handoff or {})
        if handoff:
            if not epoch_handoff_matches_context(context, handoff):
                reason = (
                    "The import handoff does not match this EEG epoch setup. "
                    "Reopen Time Epoching from the current dataset."
                )
                context["context_availability"] = EpochContextAvailability.unavailable(
                    EpochContextAvailabilityCode.INVALID_CONTEXT,
                    reason,
                ).to_payload()
                context.update(
                    {
                        "recommended_events": [],
                        "epoch_handoff": handoff,
                        "handoff_ready": False,
                        "handoff_blockers": [reason],
                    }
                )
                return context
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
                    "placement_method": (
                        placement_modes[0] if placement_modes else "manual"
                    ),
                    "placement_label": _placement_mode_display(placement_modes),
                    "recommended_events": default_events if ready else [],
                    "has_import_hint": True,
                    "epoch_handoff": handoff,
                    "handoff_ready": ready,
                    "handoff_blockers": blockers,
                }
            )

        suggestions = dict(assistant_suggestions or {})
        target_event = str(suggestions.get("target_event") or "").strip()
        if target_event:
            context["recommended_events"] = [target_event]
        with suppress(KeyError, TypeError, ValueError):
            context["suggested_t_min"] = float(suggestions["t_min"])
        with suppress(KeyError, TypeError, ValueError):
            context["suggested_t_max"] = float(suggestions["t_max"])
        if suggestions:
            context["assistant_suggestions"] = suggestions
        return context

    def _applied_event_catalog_evidence(self) -> list[dict[str, object]]:
        """Project the applied backend catalog for visible downstream evidence.

        ``epoch_handoff`` is detached from the ApplicationService publication;
        the table only exposes an immutable semantic projection, never mutable
        application state.  Per-recording duplicates are merged by event value
        so a reviewed BIDS value remains one auditable choice with all source
        recordings retained.
        """
        handoff = self.epoch_context.get("epoch_handoff")
        if not isinstance(handoff, dict):
            return []
        catalog = handoff.get("event_catalog")
        if not isinstance(catalog, list):
            return []
        grouped: dict[str, dict[str, object]] = {}
        for row in catalog:
            if not isinstance(row, dict):
                return []
            event_value = str(row.get("raw_value") or "").strip()
            event_role = str(row.get("role") or "").strip()
            keep_event = row.get("keep_event")
            use_as_class = row.get("use_as_class")
            class_name = str(row.get("class_name") or "").strip()
            source = str(row.get("target_file") or row.get("carrier") or "").strip()
            if (
                not event_value
                or not event_role
                or not isinstance(keep_event, bool)
                or not isinstance(use_as_class, bool)
                or (use_as_class and not class_name)
                or not source
            ):
                return []
            current = {
                "event_value": event_value,
                "event_role": event_role,
                "keep_event": keep_event,
                "use_as_class": use_as_class,
                "class_name": class_name,
                "sources": [source],
            }
            prior = grouped.get(event_value)
            if prior is None:
                grouped[event_value] = current
                continue
            if any(
                prior[field] != current[field]
                for field in (
                    "event_role",
                    "keep_event",
                    "use_as_class",
                    "class_name",
                )
            ):
                # A single value with inconsistent applied semantics cannot
                # honestly be collapsed into one visible decision row.
                return []
            sources = prior["sources"]
            if isinstance(sources, list) and source not in sources:
                sources.append(source)
        return [grouped[key] for key in sorted(grouped, key=str.casefold)]

    def _confirmation_scope_changed(self, *_args: object) -> None:
        self._refresh_confirmation_requirement()

    def _refresh_confirmation_requirement(self) -> None:
        if self.tmin_spin is None or self.tmax_spin is None or self.event_list is None:
            return
        requirement = (
            build_epoch_confirmation_requirement(
                self.epoch_context,
                t_min=self.tmin_spin.value(),
                t_max=self.tmax_spin.value(),
                event_ids=self._selected_event_names(),
            )
            if self.context_availability.available
            else None
        )
        previous_receipt = (
            str(self.confirmation_requirement.get("receipt") or "")
            if isinstance(self.confirmation_requirement, dict)
            else ""
        )
        current_receipt = (
            str(requirement.get("receipt") or "")
            if isinstance(requirement, dict)
            else ""
        )
        self.confirmation_requirement = requirement
        self.confirmation_receipt = None
        if self.confirmation_check is None:
            return
        if requirement is None:
            self.confirmation_check.setChecked(False)
            self.confirmation_check.hide()
            self._refresh_submit_validity()
            return
        if current_receipt != previous_receipt:
            self.confirmation_check.setChecked(False)
        self.confirmation_check.setText(str(requirement["confirmation_label"]))
        self.confirmation_check.show()
        self._refresh_submit_validity()

    def _handoff_summary_text(self) -> str:
        handoff = self.epoch_context.get("epoch_handoff")
        if isinstance(handoff, dict):
            blockers = self.epoch_context.get("handoff_blockers") or []
            source = str(self.epoch_context.get("source") or "import").strip()
            if blockers:
                blocker_text = "; ".join(str(item) for item in blockers)
                return f"{source} needs review: {blocker_text}"
            if self._is_bids_epoch_context():
                return ""
            return f"Suggested from {source}."
        if self.epoch_context.get("has_import_hint"):
            if self._is_bids_epoch_context():
                return ""
            return "Import choices are available for this EEG epoch setup."
        return ""

    @staticmethod
    def _event_item_sort_key(item: dict) -> tuple[int, int | str]:
        text = str(item.get("name") or "").strip()
        if text.isdigit():
            return (0, int(text))
        return (1, text.casefold())

    @staticmethod
    def _dialog_style() -> str:
        return (
            """
        QDialog {
            background: #1b1b1d;
            color: #f2f5f8;
        }
        QScrollArea#EpochDialogContentScroll,
        QScrollArea#EpochDialogContentScroll > QWidget,
        QWidget#EpochDialogContent {
            background: transparent;
            border: none;
        }
        QLabel {
            background-color: transparent;
            color: #f2f5f8;
        }
        QLabel#EpochDialogSubtitle,
        QLabel#EpochDialogEvidence {
            background-color: transparent;
            color: #bac2cc;
        }
        QLabel#EpochDialogEvidence:disabled,
        QLabel#EpochFieldLabel:disabled {
            color: #7f8791;
        }
        QFrame#EpochSectionCard,
        QFrame#EpochBaselineSection {
            background: #222426;
            border: 1px solid #3b3f45;
            border-radius: 6px;
        }
        QFrame#EpochBaselineSection[baselineEnabled="false"] {
            background: #202124;
            border-color: #363a40;
        }
        QWidget#EpochBaselineContent,
        QWidget#EpochBaselineContent:disabled {
            background-color: transparent;
            border: none;
        }
        QLabel#EpochSectionTitle {
            background-color: transparent;
            color: #f2f5f8;
            font-size: 15px;
            font-weight: 700;
        }
        QLabel#EpochFieldLabel {
            background-color: transparent;
            color: #d8dde4;
            font-weight: 600;
        }
        QFrame#EpochImportHintCard {
            background: #222426;
            border: 1px solid #3d454d;
            border-radius: 6px;
        }
        QLabel#EpochImportHintKey {
            background-color: transparent;
            color: #aeb6c2;
            font-weight: 600;
        }
        QLabel#EpochImportHintValue {
            background-color: transparent;
            color: #f2f5f8;
            font-weight: 700;
        }
        QTableWidget#EpochEventTable {
            background: #18191b;
            color: #f2f5f8;
            border: 1px solid #3d454d;
            border-radius: 4px;
            outline: 0;
        }
        QTableWidget#EpochEventTable::item {
            color: #f2f5f8;
            padding: 2px 8px;
            border: none;
        }
        QHeaderView::section {
            background: #2d2d2d;
            color: #bac2cc;
            border: none;
            border-bottom: 1px solid #3d454d;
            padding: 5px 8px;
            font-weight: 700;
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
        """
            + checkbox_stylesheet()
            + """
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
        QPushButton#EpochPrimaryButton:disabled {
            background: #4b4e53;
            border-color: #62666c;
            color: #a9adb3;
        }
        QPushButton#EpochSecondaryButton {
            min-width: 84px;
        }
        """
            + preprocess_toggle_stylesheet()
        )

    def toggle_baseline(self, checked):
        """Enable or disable baseline correction spin boxes.

        Args:
            checked: Whether baseline correction is enabled.

        """
        if self.baseline_check is not None:
            self._sync_toggle_text(self.baseline_check)
        if self.baseline_content is not None:
            self.baseline_content.setEnabled(checked)
        if self.baseline_group is not None:
            self.baseline_group.setProperty(
                "baselineEnabled",
                "true" if checked else "false",
            )
            style = self.baseline_group.style()
            if style is not None:
                style.unpolish(self.baseline_group)
                style.polish(self.baseline_group)
            self.baseline_group.update()
        self._refresh_submit_validity()

    def _baseline_is_inside_window(self, value: object) -> bool:
        if (
            not isinstance(value, (list, tuple))
            or len(value) < 2
            or value[0] is None
            or value[1] is None
            or self.tmin_spin is None
            or self.tmax_spin is None
        ):
            return False
        try:
            baseline_min = float(value[0])
            baseline_max = float(value[1])
        except (TypeError, ValueError):
            return False
        return (
            validate_epoch_baseline(
                enabled=True,
                baseline_min=baseline_min,
                baseline_max=baseline_max,
                t_min=self.tmin_spin.value(),
                t_max=self.tmax_spin.value(),
            )
            is None
        )

    def _current_submission_validation(self) -> EpochSubmissionValidation | None:
        if (
            self.event_list is None
            or self.baseline_check is None
            or self.b_min_spin is None
            or self.b_max_spin is None
            or self.tmin_spin is None
            or self.tmax_spin is None
        ):
            return None
        requirement = self.confirmation_requirement
        return validate_epoch_submission(
            context_available=self.context_availability.available,
            context_unavailable_reason=self.context_availability.reason,
            window_mode=self.window_mode,
            selected_events=self._selected_event_names(),
            t_min=self.tmin_spin.value(),
            t_max=self.tmax_spin.value(),
            baseline_enabled=self.baseline_check.isChecked(),
            baseline_min=self.b_min_spin.value(),
            baseline_max=self.b_max_spin.value(),
            confirmation_required=requirement is not None,
            confirmation_accepted=(
                self.confirmation_check is not None
                and self.confirmation_check.isChecked()
            ),
            confirmation_title=(
                str(requirement.get("title") or "")
                if isinstance(requirement, dict)
                else ""
            ),
            confirmation_message=(
                str(requirement.get("message") or "")
                if isinstance(requirement, dict)
                else ""
            ),
        )

    def _refresh_submit_validity(self, *_args: object) -> None:
        validation = self._current_submission_validation()
        if validation is None:
            return
        baseline_error = (
            validation.message
            if validation.issue is EpochSubmissionIssue.BASELINE
            else ""
        )
        if self.baseline_error_label is not None:
            self.baseline_error_label.setText(baseline_error)
            self.baseline_error_label.setVisible(bool(baseline_error))
        if self.warning_label is not None:
            window_error = (
                validation.message
                if validation.issue
                not in {
                    EpochSubmissionIssue.NONE,
                    EpochSubmissionIssue.BASELINE,
                    EpochSubmissionIssue.CONFIRMATION_REQUIRED,
                }
                else ""
            )
            notice = window_error or self._default_window_notice()
            self.warning_label.setText(notice)
            self.warning_label.setVisible(bool(notice))
        if self.create_button is not None:
            self.create_button.setEnabled(validation.allowed)
        self._grow_to_visible_content()

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

        self.duration_label.setText(
            f"{duration:.2f} s window ({tmin:.2f} to {tmax:.2f} s)"
        )

        self._refresh_submit_validity()

    def _default_window_notice(self) -> str:
        context_warning = str(self.epoch_context.get("window_warning") or "").strip()
        if context_warning:
            return context_warning
        if self.tmin_spin is None or self.tmax_spin is None:
            return ""
        if self.tmax_spin.value() - self.tmin_spin.value() < 1.0:
            return (
                "Short analysis window. Exact compatibility with the selected model "
                "will be checked before training."
            )
        return ""

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

        self._refresh_confirmation_requirement()
        selected_events = self._selected_event_names()
        tmin = self.tmin_spin.value()
        tmax = self.tmax_spin.value()
        validation = self._current_submission_validation()
        if validation is None:
            return
        if not validation.allowed:
            QMessageBox.warning(self, validation.title, validation.message)
            return

        baseline = None
        if self.baseline_check.isChecked():
            baseline_min = self.b_min_spin.value()
            baseline_max = self.b_max_spin.value()
            baseline = (baseline_min, baseline_max)
        self.confirmation_receipt = (
            str(self.confirmation_requirement["receipt"])
            if self.confirmation_requirement is not None
            else None
        )
        self.params = (baseline, selected_events, tmin, tmax)
        super().accept()

    def _selected_event_names(self) -> list[str]:
        if self.event_list is None:
            return []
        checked_events: list[str] = []
        for row in range(self.event_list.rowCount()):
            check_item = self.event_list.item(row, 0)
            event_item = self.event_list.item(row, 1)
            if check_item is None or event_item is None:
                continue
            if check_item.checkState() == Qt.CheckState.Checked:
                checked_events.append(event_item.text())
        return checked_events

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

    def get_confirmation_receipt(self) -> str | None:
        """Return the backend-issued receipt accepted for the current parameters."""
        return self.confirmation_receipt
