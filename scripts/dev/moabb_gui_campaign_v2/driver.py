"""User-like Qt primitives for the MainWindow MOABB campaign.

The driver deliberately knows controls, not datasets. Dataset roots enter only
through :class:`QFileDialogPathBoundary`; subject choices come from the plan.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QTableWidget,
    QTabWidget,
    QWidget,
)

from XBrainLab.ui.status import (
    IMPORT_APPLY_STATUS_LABEL,
    IMPORT_REVIEW_STATUS_LABEL,
)


class DriverContractError(RuntimeError):
    """The visible product surface cannot satisfy the campaign contract."""


class VisibleControl(StrEnum):
    """Dataset-agnostic names for every control used by the v2 journey."""

    IMPORT_BIDS = "import_bids"
    SUBJECT_TABLE = "subject_table"
    SUBJECT_CONTINUE = "subject_continue"
    DATASET_RESOURCE_CHECK_YES = "dataset_resource_check_yes"
    WIZARD_NEXT = "wizard_next"
    WIZARD_CONFIRM = "wizard_confirm"
    OPERATION_CANCEL = "operation_cancel"
    OPERATION_PROGRESS = "operation_progress"
    NAV_PREPROCESS = "nav_preprocess"
    FILTERING = "filtering"
    FILTERING_BANDPASS = "filtering_bandpass"
    FILTERING_LOW_FREQUENCY = "filtering_low_frequency"
    FILTERING_HIGH_FREQUENCY = "filtering_high_frequency"
    FILTERING_NOTCH = "filtering_notch"
    FILTERING_NOTCH_MODE = "filtering_notch_mode"
    FILTERING_NOTCH_FREQUENCY = "filtering_notch_frequency"
    DIALOG_CONFIRM = "dialog_confirm"
    CREATE_EPOCH = "create_epoch"
    EPOCH_WINDOW_MODE = "epoch_window_mode"
    EPOCH_START = "epoch_start"
    EPOCH_END = "epoch_end"
    EPOCH_BASELINE = "epoch_baseline"
    EPOCH_BASELINE_START = "epoch_baseline_start"
    EPOCH_BASELINE_END = "epoch_baseline_end"
    EPOCH_EVENT_TABLE = "epoch_event_table"
    EPOCH_CONFIRM = "epoch_confirm"
    NAV_TRAINING = "nav_training"
    SPLIT = "split"
    SPLIT_CONFIRM = "split_confirm"
    SPLIT_PREVIEW_CONFIRM = "split_preview_confirm"
    SPLIT_TRAINING_MODE = "split_training_mode"
    SPLIT_TESTING_STRATEGY = "split_testing_strategy"
    SPLIT_VALIDATION_STRATEGY = "split_validation_strategy"
    MODEL = "model"
    MODEL_COMBO = "model_combo"
    MODEL_CONFIRM = "model_confirm"
    TRAINING_SETTINGS = "training_settings"
    TRAINING_EPOCHS = "training_epochs"
    TRAINING_REPEATS = "training_repeats"
    TRAINING_BATCH_SIZE = "training_batch_size"
    TRAINING_LEARNING_RATE = "training_learning_rate"
    TRAINING_OPTIMIZER = "training_optimizer"
    TRAINING_DEVICE = "training_device"
    TRAINING_EVALUATION = "training_evaluation"
    TRAINING_CONFIRM = "training_confirm"
    START_TRAINING = "start_training"
    STOP_TRAINING = "stop_training"
    TRAINING_HISTORY = "training_history"
    NAV_EVALUATION = "nav_evaluation"
    EVALUATION_METRICS = "evaluation_metrics"
    NAV_VISUALIZATION = "nav_visualization"
    COMPUTE_SALIENCY = "compute_saliency"
    SALIENCY_TABS = "saliency_tabs"
    SALIENCY_MAP_STATUS = "saliency_map_status"
    SPECTROGRAM_STATUS = "spectrogram_status"
    SPLIT_CROSS_VALIDATION = "split_cross_validation"


@dataclass(frozen=True)
class ControlLocator:
    """Public object/accessibility identity for one production control."""

    object_name: str | None = None
    accessible_label: str | None = None
    accessible_prefix: str | None = None
    widget_type: type[Any] | None = None


CONTROL_LOCATORS = {
    VisibleControl.IMPORT_BIDS: ControlLocator(
        object_name="DatasetImportBidsButton",
        accessible_label="Import BIDS",
        widget_type=QAbstractButton,
    ),
    VisibleControl.SUBJECT_TABLE: ControlLocator(
        object_name="BidsSubjectSelectionTable",
        widget_type=QTableWidget,
    ),
    VisibleControl.SUBJECT_CONTINUE: ControlLocator(
        object_name="BidsSubjectContinueButton",
        accessible_label="Continue",
        widget_type=QAbstractButton,
    ),
    VisibleControl.WIZARD_NEXT: ControlLocator(
        object_name="DataImportNextButton",
        accessible_prefix="Next",
        widget_type=QAbstractButton,
    ),
    VisibleControl.WIZARD_CONFIRM: ControlLocator(
        object_name="DataImportConfirmButton",
        accessible_label="Confirm and Import",
        widget_type=QAbstractButton,
    ),
    VisibleControl.OPERATION_CANCEL: ControlLocator(
        object_name="OwnedOperationCancelButton",
        accessible_label="Cancel",
        widget_type=QAbstractButton,
    ),
    VisibleControl.OPERATION_PROGRESS: ControlLocator(
        object_name="OwnedOperationProgress",
        widget_type=QWidget,
    ),
    VisibleControl.NAV_PREPROCESS: ControlLocator(
        object_name="NavPreprocessButton",
        accessible_label="Preprocess",
        widget_type=QAbstractButton,
    ),
    VisibleControl.FILTERING: ControlLocator(
        object_name="PreprocessFilteringButton",
        accessible_label="Filtering",
        widget_type=QAbstractButton,
    ),
    VisibleControl.FILTERING_BANDPASS: ControlLocator(
        object_name="FilteringBandpassToggle",
        widget_type=QAbstractButton,
    ),
    VisibleControl.FILTERING_LOW_FREQUENCY: ControlLocator(
        object_name="FilteringLowFrequencyInput",
        widget_type=QWidget,
    ),
    VisibleControl.FILTERING_HIGH_FREQUENCY: ControlLocator(
        object_name="FilteringHighFrequencyInput",
        widget_type=QWidget,
    ),
    VisibleControl.FILTERING_NOTCH: ControlLocator(
        object_name="FilteringNotchToggle",
        widget_type=QAbstractButton,
    ),
    VisibleControl.FILTERING_NOTCH_MODE: ControlLocator(
        object_name="FilteringNotchModeInput",
        widget_type=QComboBox,
    ),
    VisibleControl.FILTERING_NOTCH_FREQUENCY: ControlLocator(
        object_name="FilteringNotchFrequencyInput",
        widget_type=QWidget,
    ),
    VisibleControl.DIALOG_CONFIRM: ControlLocator(
        object_name="PrimaryConfirmButton",
        accessible_label="OK",
        widget_type=QAbstractButton,
    ),
    VisibleControl.CREATE_EPOCH: ControlLocator(
        object_name="PreprocessCreateEpochButton",
        accessible_label="Create EEG Epochs",
        widget_type=QAbstractButton,
    ),
    VisibleControl.EPOCH_WINDOW_MODE: ControlLocator(
        object_name="EpochWindowModeLabel",
        widget_type=QWidget,
    ),
    VisibleControl.EPOCH_START: ControlLocator(
        object_name="EpochStartInput",
        widget_type=QWidget,
    ),
    VisibleControl.EPOCH_END: ControlLocator(
        object_name="EpochEndInput",
        widget_type=QWidget,
    ),
    VisibleControl.EPOCH_BASELINE: ControlLocator(
        object_name="PreprocessToggle",
        accessible_label="Baseline correction",
        widget_type=QAbstractButton,
    ),
    VisibleControl.EPOCH_BASELINE_START: ControlLocator(
        object_name="EpochBaselineStartInput",
        widget_type=QWidget,
    ),
    VisibleControl.EPOCH_BASELINE_END: ControlLocator(
        object_name="EpochBaselineEndInput",
        widget_type=QWidget,
    ),
    VisibleControl.EPOCH_EVENT_TABLE: ControlLocator(
        object_name="EpochEventTable",
        widget_type=QTableWidget,
    ),
    VisibleControl.EPOCH_CONFIRM: ControlLocator(
        object_name="EpochPrimaryButton",
        accessible_label="Create EEG Epochs",
        widget_type=QAbstractButton,
    ),
    VisibleControl.NAV_TRAINING: ControlLocator(
        object_name="NavTrainingButton",
        accessible_label="Training",
        widget_type=QAbstractButton,
    ),
    VisibleControl.SPLIT: ControlLocator(
        object_name="TrainingSplitButton",
        accessible_label="Dataset Splitting",
        widget_type=QAbstractButton,
    ),
    VisibleControl.SPLIT_CONFIRM: ControlLocator(
        object_name="PrimaryConfirmButton",
        accessible_label="Confirm",
        widget_type=QAbstractButton,
    ),
    VisibleControl.SPLIT_PREVIEW_CONFIRM: ControlLocator(
        object_name="DataSplitPreviewConfirmButton",
        accessible_label="Confirm",
        widget_type=QAbstractButton,
    ),
    VisibleControl.SPLIT_TRAINING_MODE: ControlLocator(
        object_name="DataSplitTrainingModeInput",
        widget_type=QComboBox,
    ),
    VisibleControl.SPLIT_TESTING_STRATEGY: ControlLocator(
        object_name="DataSplitTestingStrategyInput",
        widget_type=QComboBox,
    ),
    VisibleControl.SPLIT_VALIDATION_STRATEGY: ControlLocator(
        object_name="DataSplitValidationStrategyInput",
        widget_type=QComboBox,
    ),
    VisibleControl.MODEL: ControlLocator(
        object_name="TrainingModelButton",
        accessible_label="Model Selection",
        widget_type=QAbstractButton,
    ),
    VisibleControl.MODEL_COMBO: ControlLocator(
        object_name="ModelSelectionCombo",
        widget_type=QComboBox,
    ),
    VisibleControl.MODEL_CONFIRM: ControlLocator(
        object_name="PrimaryConfirmButton",
        accessible_label="Confirm",
        widget_type=QAbstractButton,
    ),
    VisibleControl.TRAINING_SETTINGS: ControlLocator(
        object_name="TrainingSettingsButton",
        accessible_label="Training Setting",
        widget_type=QAbstractButton,
    ),
    VisibleControl.TRAINING_EPOCHS: ControlLocator(
        object_name="TrainingEpochsInput",
        widget_type=QLineEdit,
    ),
    VisibleControl.TRAINING_REPEATS: ControlLocator(
        object_name="TrainingRepeatsInput",
        widget_type=QLineEdit,
    ),
    VisibleControl.TRAINING_BATCH_SIZE: ControlLocator(
        object_name="TrainingBatchSizeInput",
        widget_type=QLineEdit,
    ),
    VisibleControl.TRAINING_LEARNING_RATE: ControlLocator(
        object_name="TrainingLearningRateInput",
        widget_type=QLineEdit,
    ),
    VisibleControl.TRAINING_OPTIMIZER: ControlLocator(
        object_name="TrainingOptimizerValue",
        widget_type=QWidget,
    ),
    VisibleControl.TRAINING_DEVICE: ControlLocator(
        object_name="TrainingDeviceValue",
        widget_type=QWidget,
    ),
    VisibleControl.TRAINING_EVALUATION: ControlLocator(
        object_name="TrainingEvaluationInput",
        widget_type=QComboBox,
    ),
    VisibleControl.TRAINING_CONFIRM: ControlLocator(
        object_name="TrainingSettingsConfirmButton",
        accessible_label="OK",
        widget_type=QAbstractButton,
    ),
    VisibleControl.START_TRAINING: ControlLocator(
        object_name="TrainingStartButton",
        accessible_label="Start Training",
        widget_type=QAbstractButton,
    ),
    VisibleControl.STOP_TRAINING: ControlLocator(
        object_name="TrainingStopButton",
        accessible_label="Stop Training",
        widget_type=QAbstractButton,
    ),
    VisibleControl.TRAINING_HISTORY: ControlLocator(
        object_name="TrainingHistoryTable",
        widget_type=QTableWidget,
    ),
    VisibleControl.NAV_EVALUATION: ControlLocator(
        object_name="NavEvaluationButton",
        accessible_label="Evaluation",
        widget_type=QAbstractButton,
    ),
    VisibleControl.EVALUATION_METRICS: ControlLocator(
        object_name="EvaluationMetricsTable",
        widget_type=QTableWidget,
    ),
    VisibleControl.NAV_VISUALIZATION: ControlLocator(
        object_name="NavVisualizationButton",
        accessible_label="Visualization",
        widget_type=QAbstractButton,
    ),
    VisibleControl.COMPUTE_SALIENCY: ControlLocator(
        object_name="ComputeSaliencyButton",
        accessible_label="Compute Saliency",
        widget_type=QAbstractButton,
    ),
    VisibleControl.SALIENCY_TABS: ControlLocator(
        object_name="SaliencyViewTabs",
        widget_type=QTabWidget,
    ),
    VisibleControl.SALIENCY_MAP_STATUS: ControlLocator(
        object_name="SaliencyMapRenderStatus",
        widget_type=QWidget,
    ),
    VisibleControl.SPECTROGRAM_STATUS: ControlLocator(
        object_name="SpectrogramRenderStatus",
        widget_type=QWidget,
    ),
    VisibleControl.SPLIT_CROSS_VALIDATION: ControlLocator(
        object_name="DataSplitCrossValidationCheck",
        widget_type=QCheckBox,
    ),
}

# These controls currently have neither a unique object name nor a safe
# accessibility identity. Buttons with stable visible/accessibility text do not
# need an extra hook. The campaign never substitutes private dialog attributes.
MINIMUM_PRODUCTION_HOOKS = (
    "DatasetImportBidsButton",
    "DataImportNextButton",
    "EventValueDecisionEditor",
    "DataImportValueDecisionTable",
    "DataImportValueDecisionValue",
    "EventValueUseSelector",
    "EventValueClassNameEditor",
    "OwnedOperationProgress",
    "OwnedOperationCancelButton",
    "FilteringBandpassToggle",
    "FilteringLowFrequencyInput",
    "FilteringHighFrequencyInput",
    "FilteringNotchToggle",
    "FilteringNotchModeInput",
    "FilteringNotchFrequencyInput",
    "EpochWindowModeLabel",
    "EpochStartInput",
    "EpochEndInput",
    "EpochBaselineStartInput",
    "EpochBaselineEndInput",
    "DataSplitTrainingModeInput",
    "DataSplitTestingStrategyInput",
    "DataSplitValidationStrategyInput",
    "ModelSelectionCombo",
    "TrainingEpochsInput",
    "TrainingRepeatsInput",
    "TrainingBatchSizeInput",
    "TrainingLearningRateInput",
    "TrainingOptimizerValue",
    "TrainingDeviceValue",
    "TrainingEvaluationInput",
    "TrainingHistoryTable",
    "EvaluationMetricsTable",
    "DataSplitCrossValidationCheck",
    "DataSplitPreviewConfirmButton",
    "ComputeSaliencyButton",
    "SaliencyViewTabs",
    "SaliencyMapRenderStatus",
    "SpectrogramRenderStatus",
)


def missing_product_source_hooks(repo_root: Path) -> tuple[str, ...]:
    """Audit stable public object names in product UI source before a campaign."""
    ui_root = repo_root / "XBrainLab" / "ui"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(ui_root.rglob("*.py"))
    )
    return tuple(
        name
        for name in MINIMUM_PRODUCTION_HOOKS
        if f'setObjectName("{name}")' not in source
    )


@dataclass(frozen=True)
class ClickAcknowledgement:
    """Timing and public identity captured for one user-like click."""

    control: VisibleControl
    object_name: str
    accessible_name: str
    elapsed_seconds: float


@dataclass(frozen=True)
class ProgressWaitEvidence:
    """Visible operation progress observed while awaiting the next control."""

    operation_id: str | None
    heartbeat_count: int
    max_progress_silence_seconds: float
    elapsed_seconds: float


@dataclass(frozen=True)
class ActiveOperationEvidence:
    """Exact visible owned-work identity immediately before cancellation."""

    operation_id: str
    stage: str
    phase: str
    progress: Mapping[str, int | bool | str | None]
    operation_kind: str = ""


@dataclass
class OperationKindProbe:
    """Timer-owned capture armed before a synchronous modal action unwinds."""

    expected_kind: str
    predecessor_kinds: frozenset[str]
    excluding_operation_id: str | None
    started_at: float
    deadline: float
    max_progress_silence_seconds: float
    last_heartbeat_at: float
    timer: QTimer
    resource_check_timer: QTimer
    failures: list[BaseException]
    evidence: ActiveOperationEvidence | None = None
    captured_at: float | None = None
    previous_signature: tuple[str, ...] | None = None
    predecessors: list[ActiveOperationEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class OperationTerminalEvidence:
    """Visible lifecycle proof for a cancellation request."""

    operation_id: str
    terminal_phase: str
    elapsed_seconds: float


class QFileDialogPathBoundary(AbstractContextManager["QFileDialogPathBoundary"]):
    """Inject exactly one BIDS root at the product QFileDialog boundary."""

    def __init__(self, bids_root: Path) -> None:
        self.bids_root = bids_root.expanduser().resolve()
        self._file_dialog: Any | None = None
        self._original: Any | None = None
        self.selection_count = 0

    def __enter__(self) -> QFileDialogPathBoundary:
        from XBrainLab.ui.panels.dataset import actions

        file_dialog: Any = actions.QFileDialog
        if file_dialog is None:
            raise DriverContractError("QFileDialog boundary is unavailable")
        self._file_dialog = file_dialog
        self._original = file_dialog.getExistingDirectory

        def choose_bids_root(*_args: Any, **_kwargs: Any) -> str:
            self.selection_count += 1
            return str(self.bids_root)

        file_dialog.getExistingDirectory = staticmethod(choose_bids_root)
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._file_dialog is not None and self._original is not None:
            self._file_dialog.getExistingDirectory = self._original
        self._file_dialog = None
        self._original = None


class GuiCampaignDriver:
    """Locate and operate only visible, enabled production controls."""

    def __init__(
        self,
        root: QWidget | None = None,
        *,
        control_lookup: Callable[[VisibleControl], Any] | None = None,
        acknowledgement_seconds: float = 2.0,
        poll_interval_ms: int = 25,
    ) -> None:
        if root is None and control_lookup is None:
            raise ValueError("root or control_lookup is required")
        self.root = root
        self._control_lookup = control_lookup
        self.acknowledgement_seconds = acknowledgement_seconds
        self.poll_interval_ms = poll_interval_ms
        self.clicks: list[ClickAcknowledgement] = []
        self.close_completed = False
        self.close_background_snapshot: dict[str, Any] | None = None
        self.close_terminal_snapshot_observed = False
        self._observed_control_properties: dict[tuple[VisibleControl, str], Any] = {}

    def control(
        self,
        name: VisibleControl,
        *,
        timeout_seconds: float = 2.0,
    ) -> Any:
        """Wait for one matching visible and enabled public control."""
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        last_reason = "not found"
        while True:
            widget = self._lookup(name)
            if widget is not None:
                if not bool(widget.isVisible()):
                    last_reason = "not visible"
                elif not bool(widget.isEnabled()):
                    last_reason = "not enabled"
                else:
                    return widget
            if time.monotonic() >= deadline:
                raise DriverContractError(f"{name.value} is {last_reason}")
            self._settle_once()

    def click(
        self,
        name: VisibleControl,
        *,
        timeout_seconds: float = 2.0,
    ) -> ClickAcknowledgement:
        """Issue one mouse click and keep the GUI responsive within two seconds."""
        widget = self.control(name, timeout_seconds=timeout_seconds)
        started = time.monotonic()
        acknowledgement_time: list[float] = []
        if self._control_lookup is None:
            QTimer.singleShot(0, lambda: acknowledgement_time.append(time.monotonic()))
        if isinstance(widget, QAbstractButton):
            QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
        elif self._control_lookup is not None:
            click = getattr(widget, "click", None)
            if not callable(click):
                raise DriverContractError(f"{name.value} is not a clickable control")
            click()
        else:
            raise DriverContractError(
                f"{name.value} is not a production button controlled by QTest"
            )
        self._settle_once()
        elapsed = (
            acknowledgement_time[0] if acknowledgement_time else time.monotonic()
        ) - started
        if elapsed > self.acknowledgement_seconds:
            raise DriverContractError(
                f"{name.value} acknowledgement exceeded "
                f"{self.acknowledgement_seconds:.3f}s"
            )
        acknowledgement = ClickAcknowledgement(
            control=name,
            object_name=str(widget.objectName() or ""),
            accessible_name=self._accessible_name(widget),
            elapsed_seconds=elapsed,
        )
        self.clicks.append(acknowledgement)
        return acknowledgement

    def open_split_dialog_and_confirm(
        self,
        *,
        before_first_confirm: Callable[[], None] | None = None,
        before_preview_confirm: Callable[[], None] | None = None,
        timeout_seconds: float = 30.0,
    ) -> tuple[ClickAcknowledgement, ClickAcknowledgement, ClickAcknowledgement]:
        """Traverse the two real nested split dialogs through public controls."""
        acknowledgements: list[ClickAcknowledgement | None] = [None, None]
        failure: list[BaseException] = []
        deadline = time.monotonic() + timeout_seconds
        first_click_started = False
        preview_click_started = False

        def click_preview_confirm() -> None:
            nonlocal preview_click_started
            if failure or acknowledgements[1] is not None or preview_click_started:
                return
            try:
                self.control(
                    VisibleControl.SPLIT_PREVIEW_CONFIRM,
                    timeout_seconds=0.0,
                )
            except DriverContractError as exc:
                if time.monotonic() >= deadline:
                    failure.append(exc)
                    return
                QTimer.singleShot(self.poll_interval_ms, click_preview_confirm)
                return
            try:
                if before_preview_confirm is not None:
                    before_preview_confirm()
                preview_click_started = True
                acknowledgements[1] = self.click(
                    VisibleControl.SPLIT_PREVIEW_CONFIRM,
                    timeout_seconds=0.0,
                )
            except BaseException as exc:
                failure.append(exc)

        def click_first_confirm() -> None:
            nonlocal first_click_started
            if failure or acknowledgements[0] is not None or first_click_started:
                return
            try:
                self.control(VisibleControl.SPLIT_CONFIRM, timeout_seconds=0.0)
            except DriverContractError as exc:
                if time.monotonic() >= deadline:
                    failure.append(exc)
                    return
                QTimer.singleShot(self.poll_interval_ms, click_first_confirm)
                return
            try:
                if before_first_confirm is not None:
                    before_first_confirm()
                first_click_started = True
                QTimer.singleShot(0, click_preview_confirm)
                acknowledgements[0] = self.click(
                    VisibleControl.SPLIT_CONFIRM,
                    timeout_seconds=0.0,
                )
            except BaseException as exc:
                failure.append(exc)

        QTimer.singleShot(0, click_first_confirm)
        opener = self.click(VisibleControl.SPLIT, timeout_seconds=timeout_seconds)
        while (
            any(item is None for item in acknowledgements)
            and not failure
            and time.monotonic() < deadline
        ):
            self._settle_once()
        if failure:
            raise failure[0]
        if any(item is None for item in acknowledgements):
            raise DriverContractError("split dialog chain did not complete")
        first, preview = acknowledgements
        if first is None or preview is None:
            raise DriverContractError("split dialog chain did not complete")
        return opener, first, preview

    def open_modal_and_click(
        self,
        opener: VisibleControl,
        confirm: VisibleControl,
        *,
        before_confirm: Callable[[], None] | None = None,
        timeout_seconds: float = 30.0,
    ) -> tuple[
        ClickAcknowledgement,
        ClickAcknowledgement,
        ProgressWaitEvidence,
    ]:
        """Click a production opener and its nested modal action via QTest."""
        result: list[ClickAcknowledgement] = []
        failure: list[BaseException] = []
        deadline = time.monotonic() + timeout_seconds
        started = time.monotonic()
        last_heartbeat_at = started
        max_silence = 0.0
        heartbeat_count = 0
        operation_id: str | None = None
        previous_signature: tuple[str, ...] | None = None

        def click_when_modal_is_ready() -> None:
            nonlocal heartbeat_count
            nonlocal last_heartbeat_at
            nonlocal max_silence
            nonlocal operation_id
            nonlocal previous_signature
            if failure or result:
                return
            now = time.monotonic()
            progress = self._visible_operation_progress()
            if progress is not None:
                candidate = str(progress.property("operationId") or "").strip()
                if candidate:
                    operation_id = candidate
                signature = self._progress_signature(progress)
                explicit_indeterminate = bool(progress.property("indeterminate"))
                if signature != previous_signature:
                    max_silence = max(max_silence, now - last_heartbeat_at)
                    last_heartbeat_at = now
                    previous_signature = signature
                    heartbeat_count += 1
                elif explicit_indeterminate:
                    max_silence = max(max_silence, now - last_heartbeat_at)
                    last_heartbeat_at = now
            silence = now - last_heartbeat_at
            max_silence = max(max_silence, silence)
            if silence > 5.0:
                failure.append(
                    DriverContractError(
                        f"{confirm.value} had no visible progress for {silence:.3f}s"
                    )
                )
                return
            try:
                self.control(confirm, timeout_seconds=0.0)
            except DriverContractError as exc:
                if time.monotonic() >= deadline:
                    failure.append(exc)
                    return
                QTimer.singleShot(self.poll_interval_ms, click_when_modal_is_ready)
                return
            try:
                if before_confirm is not None:
                    before_confirm()
                result.append(self.click(confirm, timeout_seconds=0.0))
            except BaseException as exc:
                failure.append(exc)

        QTimer.singleShot(0, click_when_modal_is_ready)
        opener_acknowledgement = self.click(
            opener,
            timeout_seconds=timeout_seconds,
        )
        while not result and not failure and time.monotonic() < deadline:
            self._settle_once()
        if failure:
            raise failure[0]
        if not result:
            raise DriverContractError(
                f"{confirm.value} was not clicked before the modal closed"
            )
        return (
            opener_acknowledgement,
            result[0],
            ProgressWaitEvidence(
                operation_id=operation_id,
                heartbeat_count=heartbeat_count,
                max_progress_silence_seconds=max_silence,
                elapsed_seconds=time.monotonic() - started,
            ),
        )

    def wait_for_transition(
        self,
        target: VisibleControl,
        *,
        timeout_seconds: float,
        max_progress_silence_seconds: float = 5.0,
    ) -> tuple[Any, ProgressWaitEvidence]:
        """Await a target while requiring visible operation progress after 5 s."""
        started = time.monotonic()
        last_heartbeat_at = started
        max_silence = 0.0
        heartbeat_count = 0
        operation_id: str | None = None
        previous_signature: tuple[str, ...] | None = None
        modal_failure: list[BaseException] = []
        resource_check_probe = self._start_dataset_resource_check_probe(modal_failure)
        try:
            while True:
                if modal_failure:
                    raise modal_failure[0]
                try:
                    widget = self.control(target, timeout_seconds=0.0)
                except DriverContractError:
                    widget = None
                now = time.monotonic()
                if widget is not None:
                    progress = self._visible_operation_progress()
                    if progress is not None:
                        raw_operation_id = progress.property("operationId")
                        if str(raw_operation_id or "").strip():
                            operation_id = str(raw_operation_id).strip()
                    return widget, ProgressWaitEvidence(
                        operation_id=operation_id,
                        heartbeat_count=heartbeat_count,
                        max_progress_silence_seconds=max_silence,
                        elapsed_seconds=now - started,
                    )
                progress = self._visible_operation_progress()
                if progress is not None:
                    signature = self._progress_signature(progress)
                    raw_operation_id = progress.property("operationId")
                    if str(raw_operation_id or "").strip():
                        operation_id = str(raw_operation_id).strip()
                    explicit_indeterminate = bool(progress.property("indeterminate"))
                    if signature != previous_signature:
                        silence = now - last_heartbeat_at
                        max_silence = max(max_silence, silence)
                        last_heartbeat_at = now
                        previous_signature = signature
                        heartbeat_count += 1
                    elif explicit_indeterminate:
                        max_silence = max(max_silence, now - last_heartbeat_at)
                        last_heartbeat_at = now
                silence = now - last_heartbeat_at
                max_silence = max(max_silence, silence)
                if silence > max_progress_silence_seconds:
                    raise DriverContractError(
                        f"{target.value} had no visible progress for {silence:.3f}s"
                    )
                if now - started > timeout_seconds:
                    raise DriverContractError(
                        f"{target.value} did not become ready within "
                        f"{timeout_seconds:.3f}s"
                    )
                self._settle_once()
        finally:
            resource_check_probe.stop()

    def _start_dataset_resource_check_probe(
        self,
        failure: list[BaseException],
    ) -> QTimer:
        """Accept only the exact product resource check inside nested Qt loops."""
        probe = QTimer(self.root)
        probe.setInterval(self.poll_interval_ms)
        handled: set[int] = set()

        def inspect_active_message_box() -> None:
            if failure:
                return
            app = QApplication.instance()
            modal = app.activeModalWidget() if app is not None else None
            if app is not None and not isinstance(modal, QMessageBox):
                visible_modals = [
                    widget
                    for widget in app.topLevelWidgets()
                    if isinstance(widget, QMessageBox) and widget.isVisible()
                ]
                if len(visible_modals) > 1:
                    failure.append(
                        DriverContractError(
                            "multiple active message boxes while awaiting dataset "
                            "review"
                        )
                    )
                    for message_box in visible_modals:
                        message_box.reject()
                    return
                modal = visible_modals[0] if visible_modals else None
            if not isinstance(modal, QMessageBox) or id(modal) in handled:
                return
            message_box: QMessageBox = modal
            handled.add(id(message_box))
            if message_box.windowTitle() != "Dataset Resource Check":
                failure.append(
                    DriverContractError(
                        "unexpected message box while awaiting dataset review: "
                        f"{message_box.windowTitle()!r}"
                    )
                )
                message_box.reject()
                return
            yes_button = message_box.button(QMessageBox.StandardButton.Yes)
            if (
                yes_button is None
                or not yes_button.isVisible()
                or not yes_button.isEnabled()
            ):
                failure.append(
                    DriverContractError(
                        "Dataset Resource Check has no visible enabled Yes action"
                    )
                )
                message_box.reject()
                return
            started = time.monotonic()
            QTest.mouseClick(yes_button, Qt.MouseButton.LeftButton)
            elapsed = time.monotonic() - started
            self.clicks.append(
                ClickAcknowledgement(
                    control=VisibleControl.DATASET_RESOURCE_CHECK_YES,
                    object_name=str(yes_button.objectName() or ""),
                    accessible_name=self._accessible_name(yes_button),
                    elapsed_seconds=elapsed,
                )
            )
            if elapsed > self.acknowledgement_seconds:
                failure.append(
                    DriverContractError(
                        "Dataset Resource Check Yes acknowledgement exceeded "
                        f"{self.acknowledgement_seconds:.3f}s"
                    )
                )

        probe.timeout.connect(inspect_active_message_box)
        probe.start()
        return probe

    def wait_for_modal_interaction(
        self,
        target: VisibleControl,
        interaction: Callable[[ProgressWaitEvidence], None],
        *,
        timeout_seconds: float,
        max_progress_silence_seconds: float = 5.0,
    ) -> None:
        """Wait inside nested ``exec()`` and interact through visible controls."""
        started = time.monotonic()
        last_heartbeat_at = started
        max_silence = 0.0
        heartbeat_count = 0
        operation_id: str | None = None
        previous_signature: tuple[str, ...] | None = None
        finished = False
        failure: BaseException | None = None
        modal_failures: list[BaseException] = []
        resource_check_probe = self._start_dataset_resource_check_probe(modal_failures)

        def probe() -> None:
            nonlocal finished
            nonlocal failure
            nonlocal heartbeat_count
            nonlocal last_heartbeat_at
            nonlocal max_silence
            nonlocal operation_id
            nonlocal previous_signature
            if finished or failure is not None:
                return
            if modal_failures:
                failure = modal_failures[0]
                return
            now = time.monotonic()
            progress = self._visible_operation_progress()
            if progress is not None:
                candidate = str(progress.property("operationId") or "").strip()
                if candidate:
                    operation_id = candidate
                signature = self._progress_signature(progress)
                explicit_indeterminate = bool(progress.property("indeterminate"))
                if signature != previous_signature:
                    max_silence = max(max_silence, now - last_heartbeat_at)
                    last_heartbeat_at = now
                    previous_signature = signature
                    heartbeat_count += 1
                elif explicit_indeterminate:
                    max_silence = max(max_silence, now - last_heartbeat_at)
                    last_heartbeat_at = now
            try:
                widget = self.control(target, timeout_seconds=0.0)
            except DriverContractError:
                widget = None
            if widget is not None:
                evidence = ProgressWaitEvidence(
                    operation_id=operation_id,
                    heartbeat_count=heartbeat_count,
                    max_progress_silence_seconds=max_silence,
                    elapsed_seconds=now - started,
                )
                try:
                    interaction(evidence)
                except BaseException as exc:
                    failure = exc
                else:
                    finished = True
                return
            silence = now - last_heartbeat_at
            max_silence = max(max_silence, silence)
            if silence > max_progress_silence_seconds:
                failure = DriverContractError(
                    f"{target.value} had no visible progress for {silence:.3f}s"
                )
                return
            if now - started > timeout_seconds:
                failure = DriverContractError(
                    f"{target.value} did not become ready within {timeout_seconds:.3f}s"
                )
                return
            QTimer.singleShot(self.poll_interval_ms, probe)

        try:
            QTimer.singleShot(0, probe)
            while not finished and failure is None:
                self._settle_once()
            if failure is not None:
                raise failure
        finally:
            resource_check_probe.stop()

    def wait_for_active_operation(
        self,
        *,
        timeout_seconds: float = 5.0,
        excluding_operation_id: str | None = None,
    ) -> str:
        """Wait for a visible non-terminal operation allocated by a real click."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() <= deadline:
            progress = self._visible_operation_progress()
            if progress is not None:
                operation_id = str(progress.property("operationId") or "").strip()
                phase = str(progress.property("operationPhase") or "").casefold()
                if (
                    operation_id
                    and operation_id != excluding_operation_id
                    and phase in {"pending", "running", "cancelling"}
                ):
                    return operation_id
            self._settle_once()
        raise DriverContractError("no visible active owned operation was published")

    def wait_for_meaningful_active_operation(
        self,
        *,
        allowed_stages: Collection[str],
        timeout_seconds: float = 5.0,
        excluding_operation_id: str | None = None,
    ) -> ActiveOperationEvidence:
        """Wait until real work reaches a target-specific cancellable stage."""
        allowed = frozenset(str(stage).strip() for stage in allowed_stages if stage)
        if not allowed:
            raise ValueError("allowed_stages must contain a meaningful product stage")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() <= deadline:
            progress = self._visible_operation_progress()
            if progress is not None:
                operation_id = str(progress.property("operationId") or "").strip()
                phase = str(progress.property("operationPhase") or "").casefold()
                stage = str(progress.property("stage") or "").strip()
                if (
                    operation_id
                    and operation_id != excluding_operation_id
                    and phase == "running"
                    and stage in allowed
                ):
                    return self._active_operation_evidence(progress)
            self._settle_once()
        raise DriverContractError(
            "no visible active owned operation reached a target-specific "
            "meaningful stage"
        )

    def wait_for_active_operation_kind(
        self,
        operation_kind: str,
        *,
        timeout_seconds: float,
        excluding_operation_id: str | None = None,
    ) -> ActiveOperationEvidence:
        """Pin a newly published owner by backend-owned work kind.

        A preceding review/validation owner may legitimately remain visible
        while its result callback schedules Apply. Liveness for the target
        begins after its exact identity is pinned; this transition wait is
        bounded by ``timeout_seconds`` and still handles the product's public
        resource-confirmation modal.
        """
        expected_kind = str(operation_kind or "").strip()
        if not expected_kind:
            raise ValueError("operation_kind must be non-empty")
        started = time.monotonic()
        modal_failures: list[BaseException] = []
        resource_check_probe = self._start_dataset_resource_check_probe(modal_failures)
        try:
            while True:
                if modal_failures:
                    raise modal_failures[0]
                progress = self._visible_operation_progress()
                if progress is not None:
                    operation_id = str(progress.property("operationId") or "").strip()
                    phase = str(progress.property("operationPhase") or "").casefold()
                    observed_kind = str(
                        progress.property("operationKind") or ""
                    ).strip()
                    if (
                        operation_id
                        and operation_id != excluding_operation_id
                        and observed_kind == expected_kind
                    ):
                        evidence = self._active_operation_evidence(progress)
                        if evidence.operation_kind != expected_kind:
                            raise DriverContractError(
                                "visible operation kind changed while it was pinned"
                            )
                        if phase in {"pending", "running", "cancelling", "completed"}:
                            return evidence
                        if phase in {"cancelled", "failed"}:
                            raise DriverContractError(
                                f"operation {operation_id} reached {phase!r}"
                            )
                if time.monotonic() - started > timeout_seconds:
                    raise DriverContractError(
                        f"no visible active {expected_kind} operation was published"
                    )
                self._settle_once()
        finally:
            resource_check_probe.stop()

    def arm_operation_kind_probe(
        self,
        operation_kind: str,
        *,
        predecessor_kinds: Collection[str] = (),
        timeout_seconds: float,
        max_progress_silence_seconds: float = 5.0,
        excluding_operation_id: str | None = None,
    ) -> OperationKindProbe:
        """Arm visible owner capture before a synchronous modal callback returns.

        A fast follow-up operation can be published and complete while Qt is
        unwinding the dialog/result callback that scheduled it.  Polling must
        therefore already be armed at the user-action boundary; observing the
        status only after ``QDialog.exec()`` has fully unwound can miss that
        truthful but short-lived public owner.
        """
        expected_kind = str(operation_kind or "").strip()
        if not expected_kind:
            raise ValueError("operation_kind must be non-empty")
        predecessors = frozenset(
            str(kind or "").strip() for kind in predecessor_kinds if str(kind).strip()
        )
        if expected_kind in predecessors:
            raise ValueError("target operation kind cannot also be a predecessor")
        if max_progress_silence_seconds <= 0:
            raise ValueError("max_progress_silence_seconds must be positive")
        failures: list[BaseException] = []
        resource_check_timer = self._start_dataset_resource_check_probe(failures)
        timer = QTimer(self.root)
        timer.setInterval(max(1, min(self.poll_interval_ms, 5)))
        started_at = time.monotonic()
        probe = OperationKindProbe(
            expected_kind=expected_kind,
            predecessor_kinds=predecessors,
            excluding_operation_id=excluding_operation_id,
            started_at=started_at,
            deadline=started_at + max(0.0, timeout_seconds),
            max_progress_silence_seconds=max_progress_silence_seconds,
            last_heartbeat_at=started_at,
            timer=timer,
            resource_check_timer=resource_check_timer,
            failures=failures,
        )

        def inspect() -> None:
            if probe.evidence is not None or probe.failures:
                probe.timer.stop()
                probe.resource_check_timer.stop()
                return
            try:
                progress = self._visible_operation_progress()
                if progress is not None:
                    operation_id = str(progress.property("operationId") or "").strip()
                    phase = str(progress.property("operationPhase") or "").casefold()
                    observed_kind = str(
                        progress.property("operationKind") or ""
                    ).strip()
                    if operation_id and operation_id != excluding_operation_id:
                        evidence = self._active_operation_evidence(progress)
                        if observed_kind == expected_kind and phase in {
                            "pending",
                            "running",
                            "cancelling",
                            "completed",
                        }:
                            probe.evidence = evidence
                            probe.captured_at = time.monotonic()
                            probe.timer.stop()
                            probe.resource_check_timer.stop()
                            return
                        if phase in {"cancelled", "failed"}:
                            probe.failures.append(
                                DriverContractError(
                                    f"operation {operation_id} reached {phase!r}"
                                )
                            )
                        elif observed_kind not in probe.predecessor_kinds:
                            probe.failures.append(
                                DriverContractError(
                                    "unexpected visible operation while awaiting "
                                    f"{expected_kind}: kind={observed_kind!r}, "
                                    f"operation_id={operation_id!r}"
                                )
                            )
                        else:
                            signature = self._progress_signature(progress)
                            if signature != probe.previous_signature:
                                probe.previous_signature = signature
                                probe.last_heartbeat_at = time.monotonic()
                            if not any(
                                item.operation_id == operation_id
                                for item in probe.predecessors
                            ):
                                probe.predecessors.append(evidence)
            except BaseException as exc:
                probe.failures.append(exc)
            if not probe.failures and probe.evidence is None:
                now = time.monotonic()
                if now > probe.deadline:
                    probe.failures.append(
                        DriverContractError(
                            f"no visible active {expected_kind} operation was published"
                        )
                    )
                else:
                    silence = now - probe.last_heartbeat_at
                    if silence > probe.max_progress_silence_seconds:
                        last = probe.predecessors[-1] if probe.predecessors else None
                        detail = (
                            ""
                            if last is None
                            else (
                                f"; last kind={last.operation_kind!r}, "
                                f"operation_id={last.operation_id!r}, "
                                f"stage={last.stage!r}, phase={last.phase!r}"
                            )
                        )
                        probe.failures.append(
                            DriverContractError(
                                "post-confirm operation chain had no visible progress "
                                f"for {silence:.3f}s{detail}"
                            )
                        )
            if probe.failures:
                probe.timer.stop()
                probe.resource_check_timer.stop()

        timer.timeout.connect(inspect)
        timer.start()
        inspect()
        return probe

    def wait_for_operation_kind_probe(
        self,
        probe: OperationKindProbe,
    ) -> ActiveOperationEvidence:
        """Wait for one pre-armed visible owner capture without re-arming it."""
        try:
            while probe.evidence is None and not probe.failures:
                if time.monotonic() > probe.deadline:
                    raise DriverContractError(
                        f"no visible active {probe.expected_kind} operation was "
                        "published"
                    )
                self._settle_once()
            if probe.failures:
                raise probe.failures[0]
            if probe.evidence is None:
                raise DriverContractError(
                    f"no visible active {probe.expected_kind} operation was published"
                )
            return probe.evidence
        finally:
            probe.timer.stop()
            probe.resource_check_timer.stop()

    def click_active_operation_cancel(
        self,
        name: VisibleControl,
        *,
        expected_operation_id: str,
        allowed_stages: Collection[str],
    ) -> tuple[ClickAcknowledgement, ActiveOperationEvidence]:
        """Snapshot the exact meaningful operation, then click visible Cancel."""
        self.control(name, timeout_seconds=0.0)
        progress = self._visible_operation_progress()
        if progress is None:
            raise DriverContractError(
                "visible operation progress disappeared before the cancel click"
            )
        evidence = self._active_operation_evidence(progress)
        allowed = frozenset(str(stage).strip() for stage in allowed_stages if stage)
        if evidence.operation_id != str(expected_operation_id).strip():
            raise DriverContractError(
                "visible operation owner changed before the cancel click"
            )
        if evidence.phase != "running" or evidence.stage not in allowed:
            raise DriverContractError(
                "visible operation left its meaningful stage before the cancel click"
            )
        acknowledgement = self.click(name, timeout_seconds=0.0)
        return acknowledgement, evidence

    def visible_operation_id(self) -> str | None:
        """Return the currently published operation identity, if any."""
        progress = self._visible_operation_progress()
        if progress is None:
            return None
        operation_id = str(progress.property("operationId") or "").strip()
        return operation_id or None

    def control_operation_id(self, name: VisibleControl) -> str | None:
        """Read the exact operation identity retained by one visible control."""
        widget = self._lookup(name)
        if widget is None or not bool(widget.isVisible()):
            return None
        operation_id = str(widget.property("operationId") or "").strip()
        return operation_id or None

    def wait_for_control_operation_completion(
        self,
        name: VisibleControl,
        *,
        timeout_seconds: float,
        excluding_operation_id: str | None = None,
        max_progress_silence_seconds: float = 5.0,
    ) -> ProgressWaitEvidence:
        """Await the operation retained by ``name``, never a later status owner."""
        started = time.monotonic()
        last_heartbeat_at = started
        max_silence = 0.0
        heartbeat_count = 0
        previous_signature: tuple[str, ...] | None = None
        operation_id: str | None = None
        while True:
            now = time.monotonic()
            widget = self._lookup(name)
            if widget is not None and bool(widget.isVisible()):
                candidate = str(widget.property("operationId") or "").strip()
                if candidate and candidate != excluding_operation_id:
                    operation_id = candidate
                    phase = str(widget.property("operationPhase") or "").casefold()
                    if phase == "completed":
                        return ProgressWaitEvidence(
                            operation_id=operation_id,
                            heartbeat_count=heartbeat_count,
                            max_progress_silence_seconds=max_silence,
                            elapsed_seconds=now - started,
                        )
                    if phase in {"cancelled", "failed"}:
                        raise DriverContractError(
                            f"operation {operation_id} reached {phase!r}"
                        )
            progress = self._visible_operation_progress()
            if progress is not None:
                progress_id = str(progress.property("operationId") or "").strip()
                if operation_id is None or progress_id == operation_id:
                    signature = self._progress_signature(progress)
                    explicit_indeterminate = bool(progress.property("indeterminate"))
                    if signature != previous_signature:
                        max_silence = max(max_silence, now - last_heartbeat_at)
                        last_heartbeat_at = now
                        previous_signature = signature
                        heartbeat_count += 1
                    elif explicit_indeterminate:
                        max_silence = max(max_silence, now - last_heartbeat_at)
                        last_heartbeat_at = now
            silence = now - last_heartbeat_at
            max_silence = max(max_silence, silence)
            if silence > max_progress_silence_seconds:
                raise DriverContractError(
                    f"{name.value} had no visible progress for {silence:.3f}s"
                )
            if now - started > timeout_seconds:
                raise DriverContractError(f"{name.value} operation did not complete")
            self._settle_once()

    def wait_for_owned_operation_completion(
        self,
        *,
        timeout_seconds: float,
        excluding_operation_id: str | None = None,
        max_progress_silence_seconds: float = 5.0,
    ) -> ProgressWaitEvidence:
        """Observe a newly published operation through successful completion."""
        started = time.monotonic()
        last_heartbeat_at = started
        max_silence = 0.0
        heartbeat_count = 0
        previous_signature: tuple[str, ...] | None = None
        operation_id: str | None = None
        while True:
            now = time.monotonic()
            progress = self._visible_operation_progress()
            if progress is not None:
                candidate = str(progress.property("operationId") or "").strip()
                if candidate and candidate != excluding_operation_id:
                    operation_id = candidate
                    signature = self._progress_signature(progress)
                    explicit_indeterminate = bool(progress.property("indeterminate"))
                    if signature != previous_signature:
                        max_silence = max(max_silence, now - last_heartbeat_at)
                        last_heartbeat_at = now
                        previous_signature = signature
                        heartbeat_count += 1
                    elif explicit_indeterminate:
                        max_silence = max(max_silence, now - last_heartbeat_at)
                        last_heartbeat_at = now
                    phase = str(progress.property("operationPhase") or "").casefold()
                    if phase == "completed":
                        return ProgressWaitEvidence(
                            operation_id=operation_id,
                            heartbeat_count=heartbeat_count,
                            max_progress_silence_seconds=max_silence,
                            elapsed_seconds=now - started,
                        )
                    if phase in {"cancelled", "failed"}:
                        raise DriverContractError(
                            f"operation {operation_id} reached {phase!r}"
                        )
            silence = now - last_heartbeat_at
            max_silence = max(max_silence, silence)
            if silence > max_progress_silence_seconds:
                raise DriverContractError(
                    f"owned operation had no visible progress for {silence:.3f}s"
                )
            if now - started > timeout_seconds:
                raise DriverContractError("owned operation did not complete")
            self._settle_once()

    def wait_for_exact_owned_operation_completion(
        self,
        operation_id: str,
        *,
        timeout_seconds: float,
        max_progress_silence_seconds: float = 5.0,
    ) -> ProgressWaitEvidence:
        """Observe one already-pinned visible owner through completion."""
        expected_id = str(operation_id or "").strip()
        if not expected_id:
            raise ValueError("operation_id must be non-empty")
        started = time.monotonic()
        last_heartbeat_at = started
        max_silence = 0.0
        heartbeat_count = 0
        previous_signature: tuple[str, ...] | None = None
        last_observed: ActiveOperationEvidence | None = None
        while True:
            now = time.monotonic()
            progress = self._visible_operation_progress()
            if progress is not None:
                candidate = str(progress.property("operationId") or "").strip()
                phase = str(progress.property("operationPhase") or "").casefold()
                if (
                    candidate
                    and candidate != expected_id
                    and phase
                    in {
                        "pending",
                        "running",
                        "cancelling",
                    }
                ):
                    raise DriverContractError(
                        "visible operation owner changed before the exact operation "
                        "completed"
                    )
                if candidate == expected_id:
                    last_observed = self._active_operation_evidence(progress)
                    signature = self._progress_signature(progress)
                    if signature != previous_signature:
                        max_silence = max(max_silence, now - last_heartbeat_at)
                        last_heartbeat_at = now
                        previous_signature = signature
                        heartbeat_count += 1
                    if phase == "completed":
                        return ProgressWaitEvidence(
                            operation_id=expected_id,
                            heartbeat_count=heartbeat_count,
                            max_progress_silence_seconds=max_silence,
                            elapsed_seconds=now - started,
                        )
                    if phase in {"cancelled", "failed"}:
                        raise DriverContractError(
                            f"operation {expected_id} reached {phase!r}"
                        )
            silence = now - last_heartbeat_at
            max_silence = max(max_silence, silence)
            if silence > max_progress_silence_seconds:
                detail = (
                    ""
                    if last_observed is None
                    else (
                        f"; kind={last_observed.operation_kind!r}, "
                        f"stage={last_observed.stage!r}, "
                        f"phase={last_observed.phase!r}, "
                        f"progress={last_observed.progress['display']!r}"
                    )
                )
                raise DriverContractError(
                    f"operation {expected_id} had no visible progress for "
                    f"{silence:.3f}s{detail}"
                )
            if now - started > timeout_seconds:
                raise DriverContractError(f"operation {expected_id} did not complete")
            self._settle_once()

    def wait_for_operation_terminal(
        self,
        operation_id: str,
        *,
        timeout_seconds: float = 30.0,
        expected_phase: str = "cancelled",
    ) -> OperationTerminalEvidence:
        """Wait for the same visible operation to reach a terminal phase."""
        started = time.monotonic()
        deadline = started + timeout_seconds
        while time.monotonic() <= deadline:
            progress = self._visible_operation_progress()
            if (
                progress is not None
                and str(progress.property("operationId") or "").strip() == operation_id
            ):
                phase = str(progress.property("operationPhase") or "").casefold()
                if phase in {"completed", "cancelled", "failed"}:
                    if phase != expected_phase:
                        raise DriverContractError(
                            f"operation {operation_id} reached {phase!r}, "
                            f"expected {expected_phase!r}"
                        )
                    return OperationTerminalEvidence(
                        operation_id=operation_id,
                        terminal_phase=phase,
                        elapsed_seconds=time.monotonic() - started,
                    )
            self._settle_once()
        raise DriverContractError(
            f"operation {operation_id} did not reach {expected_phase!r}"
        )

    def wait_for_training_completion(
        self,
        *,
        timeout_seconds: float,
        excluding_operation_id: str | None = None,
        max_progress_silence_seconds: float = 5.0,
    ) -> ProgressWaitEvidence:
        """Wait for a visible history row to publish terminal completion."""
        started = time.monotonic()
        last_heartbeat_at = started
        previous_signature: tuple[str, ...] | None = None
        heartbeat_count = 0
        max_silence = 0.0
        operation_id: str | None = None
        while True:
            try:
                table = self.control(
                    VisibleControl.TRAINING_HISTORY,
                    timeout_seconds=0.0,
                )
            except DriverContractError:
                table = None
            statuses = self._table_column_values(table, "Status")
            now = time.monotonic()
            progress = self._visible_operation_progress()
            if progress is not None:
                raw_operation_id = progress.property("operationId")
                candidate_operation_id = str(raw_operation_id or "").strip()
                stage = str(progress.property("stage") or "").casefold()
                if (
                    candidate_operation_id
                    and candidate_operation_id != excluding_operation_id
                ):
                    if operation_id is None and "train" in stage:
                        operation_id = candidate_operation_id
                    elif (
                        operation_id is not None
                        and candidate_operation_id != operation_id
                    ):
                        raise DriverContractError(
                            "visible progress changed owner before training completed"
                        )
                signature = self._progress_signature(progress)
                explicit_indeterminate = bool(progress.property("indeterminate"))
                if signature != previous_signature:
                    max_silence = max(max_silence, now - last_heartbeat_at)
                    last_heartbeat_at = now
                    previous_signature = signature
                    heartbeat_count += 1
                elif explicit_indeterminate:
                    max_silence = max(max_silence, now - last_heartbeat_at)
                    last_heartbeat_at = now
            active_statuses = {"Queued", "Running", "Stopping", "Preparing"}
            if (
                statuses
                and statuses[-1] == "Completed"
                and not any(status in active_statuses for status in statuses)
            ):
                if operation_id is None:
                    raise DriverContractError(
                        "completed training lacks its visible operation identity"
                    )
                return ProgressWaitEvidence(
                    operation_id=operation_id,
                    heartbeat_count=heartbeat_count,
                    max_progress_silence_seconds=max_silence,
                    elapsed_seconds=now - started,
                )
            silence = now - last_heartbeat_at
            max_silence = max(max_silence, silence)
            if silence > max_progress_silence_seconds:
                raise DriverContractError(
                    f"training had no visible progress for {silence:.3f}s"
                )
            if now - started > timeout_seconds:
                raise DriverContractError("training did not complete before timeout")
            self._settle_once()

    def wait_for_table_rows(
        self,
        name: VisibleControl,
        *,
        timeout_seconds: float,
    ) -> QTableWidget:
        """Wait until a visible production table contains at least one row."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() <= deadline:
            try:
                table = self.control(name, timeout_seconds=0.0)
            except DriverContractError:
                table = None
            if isinstance(table, QTableWidget):
                table_widget: Any = table
                if table_widget.rowCount() > 0:
                    return table_widget
            self._settle_once()
        raise DriverContractError(f"{name.value} did not publish any rows")

    def wait_for_render_status(
        self,
        name: VisibleControl,
        *,
        timeout_seconds: float,
        max_progress_silence_seconds: float = 5.0,
    ) -> ProgressWaitEvidence:
        """Wait until a public render-status hook reports ``completed``."""
        if name not in {
            VisibleControl.SALIENCY_MAP_STATUS,
            VisibleControl.SPECTROGRAM_STATUS,
        }:
            raise ValueError(f"{name.value} is not a render-status control")
        started = time.monotonic()
        last_heartbeat_at = started
        max_silence = 0.0
        heartbeat_count = 0
        operation_id: str | None = None
        previous_status_signature: tuple[str, ...] | None = None
        previous_progress_signature: tuple[str, ...] | None = None
        while True:
            try:
                status_widget = self.control(name, timeout_seconds=0.0)
            except DriverContractError:
                status_widget = None
            now = time.monotonic()
            if status_widget is not None:
                status = str(status_widget.property("renderStatus") or "").casefold()
                raw_operation_id = status_widget.property("operationId")
                if str(raw_operation_id or "").strip():
                    operation_id = str(raw_operation_id).strip()
                signature = self._progress_signature(status_widget)
                explicit_indeterminate = bool(status_widget.property("indeterminate"))
                if signature != previous_status_signature:
                    max_silence = max(max_silence, now - last_heartbeat_at)
                    last_heartbeat_at = now
                    previous_status_signature = signature
                    heartbeat_count += 1
                elif explicit_indeterminate:
                    max_silence = max(max_silence, now - last_heartbeat_at)
                    last_heartbeat_at = now
                if status == "completed":
                    return ProgressWaitEvidence(
                        operation_id=operation_id,
                        heartbeat_count=heartbeat_count,
                        max_progress_silence_seconds=max_silence,
                        elapsed_seconds=now - started,
                    )
                if status in {"failed", "cancelled", "stale"}:
                    raise DriverContractError(
                        f"{name.value} reached terminal render status {status!r}"
                    )
            progress = self._visible_operation_progress()
            if progress is not None:
                signature = self._progress_signature(progress)
                raw_operation_id = progress.property("operationId")
                if str(raw_operation_id or "").strip():
                    operation_id = str(raw_operation_id).strip()
                if signature != previous_progress_signature:
                    max_silence = max(max_silence, now - last_heartbeat_at)
                    last_heartbeat_at = now
                    previous_progress_signature = signature
                    heartbeat_count += 1
            silence = now - last_heartbeat_at
            max_silence = max(max_silence, silence)
            if silence > max_progress_silence_seconds:
                raise DriverContractError(
                    f"{name.value} had no visible progress for {silence:.3f}s"
                )
            if now - started > timeout_seconds:
                raise DriverContractError(
                    f"{name.value} did not render within {timeout_seconds:.3f}s"
                )
            self._settle_once()

    def select_subjects(
        self,
        subjects: Sequence[int],
        *,
        timeout_seconds: float = 2.0,
    ) -> float:
        """Select the exact visible BIDS subject rows with checkbox clicks."""
        table = self.control(
            VisibleControl.SUBJECT_TABLE,
            timeout_seconds=timeout_seconds,
        )
        if not isinstance(table, QTableWidget):
            raise DriverContractError("subject_table is not a QTableWidget")
        wanted = {int(subject) for subject in subjects}
        observed: set[int] = set()
        max_acknowledgement = 0.0
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is None:
                continue
            label = item.text().strip()
            if not label:
                continue
            match = re.fullmatch(r"sub-0*([1-9][0-9]*)", label, flags=re.IGNORECASE)
            if match is None:
                continue
            subject_number = int(match.group(1))
            observed.add(subject_number)
            should_check = subject_number in wanted
            checked = item.checkState() is Qt.CheckState.Checked
            if should_check == checked:
                continue
            table.scrollToItem(item)
            self._settle_once()
            rect = table.visualItemRect(item)
            checkbox_point = QPoint(
                rect.left() + min(12, rect.width() // 3), rect.center().y()
            )
            started = time.monotonic()
            QTest.mouseClick(
                table.viewport(),
                Qt.MouseButton.LeftButton,
                pos=checkbox_point,
            )
            self._settle_once()
            acknowledgement = time.monotonic() - started
            max_acknowledgement = max(max_acknowledgement, acknowledgement)
            if acknowledgement > self.acknowledgement_seconds:
                raise DriverContractError(
                    f"subject row acknowledgement exceeded "
                    f"{self.acknowledgement_seconds:.3f}s"
                )
            if (item.checkState() is Qt.CheckState.Checked) != should_check:
                raise DriverContractError(f"could not select visible subject {label}")
        missing = sorted(wanted.difference(observed))
        if missing:
            raise DriverContractError(
                "selected subjects are absent from the visible catalog: "
                + ", ".join(f"sub-{subject}" for subject in missing)
            )
        return max_acknowledgement

    def resolve_visible_event_value_decisions(
        self,
        *,
        expected_events: Collection[str],
        expected_classes: Collection[str],
        timeout_seconds: float = 30.0,
    ) -> list[dict[str, str]]:
        """Resolve every visible Match Labels row through product controls.

        The locked oracle supplies semantic truth without naming a dataset in
        the driver: an expected class remains a training class with its exact
        raw value as class name; every other expected event remains imported
        but is excluded from supervised classes.
        """
        expected_event_values = tuple(
            str(value).strip() for value in expected_events if str(value).strip()
        )
        expected_class_values = tuple(
            str(value).strip() for value in expected_classes if str(value).strip()
        )
        if not expected_event_values or len(set(expected_event_values)) != len(
            expected_event_values
        ):
            raise DriverContractError(
                "Match Labels expected-events oracle must be non-empty and unique"
            )
        if not expected_class_values or len(set(expected_class_values)) != len(
            expected_class_values
        ):
            raise DriverContractError(
                "Match Labels expected-classes oracle must be non-empty and unique"
            )
        expected_event_set = set(expected_event_values)
        expected_class_set = set(expected_class_values)
        if not expected_class_set.issubset(expected_event_set):
            raise DriverContractError(
                "Match Labels expected classes are absent from expected events"
            )

        editor = self._visible_named_widget(
            "EventValueDecisionEditor",
            QWidget,
            timeout_seconds=timeout_seconds,
        )
        table_matches = [
            widget
            for widget in editor.findChildren(QWidget, "DataImportValueDecisionTable")
            if widget.isVisible() and widget.isEnabled()
        ]
        if len(table_matches) != 1:
            raise DriverContractError(
                "Match Labels must expose one visible event-value decision table"
            )
        layout = table_matches[0].layout()
        if not isinstance(layout, QGridLayout):
            raise DriverContractError(
                "Match Labels event-value decisions lack a public row layout"
            )

        rows: list[tuple[str, QComboBox, QLineEdit]] = []
        for row_index in range(1, layout.rowCount()):
            value_item = layout.itemAtPosition(row_index, 0)
            use_item = layout.itemAtPosition(row_index, 1)
            class_item = layout.itemAtPosition(row_index, 2)
            if value_item is None and use_item is None and class_item is None:
                continue
            value_cell = value_item.widget() if value_item is not None else None
            use_selector = use_item.widget() if use_item is not None else None
            class_editor = class_item.widget() if class_item is not None else None
            if not isinstance(value_cell, QWidget):
                raise DriverContractError(
                    "Match Labels event-value row lacks its public value cell"
                )
            value_widget = cast(QWidget, value_cell)
            labels = value_widget.findChildren(
                QLabel,
                "DataImportValueDecisionValue",
            )
            if len(labels) != 1:
                raise DriverContractError(
                    "Match Labels event-value row lacks its public value label"
                )
            if not isinstance(use_selector, QComboBox):
                raise DriverContractError(
                    "Match Labels event-value row lacks its public use control"
                )
            if not isinstance(class_editor, QLineEdit):
                raise DriverContractError(
                    "Match Labels event-value row lacks its public class control"
                )
            use_combo = cast(QComboBox, use_selector)
            class_line_edit = cast(QLineEdit, class_editor)
            if (
                use_combo.objectName() != "EventValueUseSelector"
                or class_line_edit.objectName() != "EventValueClassNameEditor"
            ):
                raise DriverContractError(
                    "Match Labels event-value row lacks stable public controls"
                )
            raw_value = self._accessible_name(labels[0]).strip()
            if not raw_value:
                raise DriverContractError(
                    "Match Labels event-value row lacks its accessible raw value"
                )
            self._ensure_widget_visible(labels[0])
            if not labels[0].isVisible() or not labels[0].isEnabled():
                raise DriverContractError(
                    f"Match Labels raw value {raw_value!r} is not visible"
                )
            rows.append((raw_value, use_combo, class_line_edit))

        observed_event_set = {raw_value for raw_value, _use, _class in rows}
        if len(observed_event_set) != len(rows):
            raise DriverContractError(
                "Match Labels exposes duplicate raw-value decisions"
            )
        if not rows or observed_event_set != expected_event_set:
            missing = sorted(expected_event_set.difference(observed_event_set))
            unexpected = sorted(observed_event_set.difference(expected_event_set))
            raise DriverContractError(
                "Match Labels visible raw-value set differs from the locked oracle "
                f"(missing={missing!r}, unexpected={unexpected!r})"
            )

        decisions: list[dict[str, str]] = []
        for raw_value, use_selector, class_editor in rows:
            self._ensure_widget_visible(use_selector)
            if not use_selector.isVisible() or not use_selector.isEnabled():
                raise DriverContractError(
                    f"Match Labels use control for {raw_value!r} is not usable"
                )
            use = "class" if raw_value in expected_class_set else "ignore"
            use_index = use_selector.findData(use)
            if use_index < 0 or not use_selector.itemText(use_index).strip():
                raise DriverContractError(
                    f"Match Labels does not display the required {use!r} choice"
                )
            if use_selector.currentData() != use:
                self._choose_combo_index_with_qtest(use_selector, use_index)

            class_name = ""
            selection_basis = "oracle_nonclass_event"
            if use == "class":
                self._ensure_widget_visible(class_editor)
                if (
                    not class_editor.isVisible()
                    or not class_editor.isEnabled()
                    or class_editor.isReadOnly()
                ):
                    raise DriverContractError(
                        f"Match Labels class-name control for {raw_value!r} is not usable"
                    )
                if class_editor.text() != raw_value:
                    self._replace_line_edit_text_with_qtest(class_editor, raw_value)
                class_name = class_editor.text().strip()
                selection_basis = "oracle_expected_class"
                if class_name != raw_value:
                    raise DriverContractError(
                        f"Match Labels class name for {raw_value!r} was not applied"
                    )
            elif class_editor.isVisible():
                raise DriverContractError(
                    f"Match Labels ignored value {raw_value!r} still exposes a class name"
                )
            decisions.append(
                {
                    "event_value": raw_value,
                    "use": use,
                    "class_name": class_name,
                    "selection_basis": selection_basis,
                }
            )

        self.control(VisibleControl.WIZARD_NEXT, timeout_seconds=timeout_seconds)
        return decisions

    def replace_text(
        self,
        name: VisibleControl,
        value: str,
        *,
        timeout_seconds: float = 2.0,
    ) -> None:
        """Edit one visible public line editor through keyboard interaction."""
        editor = self.control(name, timeout_seconds=timeout_seconds)
        if not isinstance(editor, QLineEdit):
            raise DriverContractError(f"{name.value} is not a line editor")
        QTest.mouseClick(editor, Qt.MouseButton.LeftButton)
        QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(editor, value)
        self._settle_once()
        if editor.text() != value:
            raise DriverContractError(
                f"{name.value} did not accept the requested value"
            )

    def choose_combo_text(
        self,
        name: VisibleControl,
        value: str,
        *,
        timeout_seconds: float = 2.0,
    ) -> None:
        """Choose an existing combo entry with visible keyboard navigation."""
        combo = self.control(name, timeout_seconds=timeout_seconds)
        if not isinstance(combo, QComboBox):
            raise DriverContractError(f"{name.value} is not a combo box")
        index = combo.findText(value)
        if index < 0:
            raise DriverContractError(f"{name.value} does not expose {value!r}")
        QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
        QTest.keyClick(combo, Qt.Key.Key_Home)
        for _ in range(index):
            QTest.keyClick(combo, Qt.Key.Key_Down)
        QTest.keyClick(combo, Qt.Key.Key_Return)
        self._settle_once()
        if combo.currentText() != value:
            raise DriverContractError(f"{name.value} did not select {value!r}")

    def _choose_combo_index_with_qtest(
        self,
        combo: QComboBox,
        index: int,
    ) -> None:
        if not combo.isVisible() or not combo.isEnabled():
            raise DriverContractError("combo choice is not visible and enabled")
        if index < 0 or index >= combo.count():
            raise DriverContractError("combo choice index is outside the visible list")
        started = time.monotonic()
        QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
        if index == 0:
            QTest.keyClick(combo, Qt.Key.Key_Home)
        elif index == combo.count() - 1:
            QTest.keyClick(combo, Qt.Key.Key_End)
        else:
            QTest.keyClicks(combo, combo.itemText(index))
        QTest.keyClick(combo, Qt.Key.Key_Return)
        self._settle_once()
        if combo.currentIndex() != index:
            raise DriverContractError("combo did not accept its visible choice")
        if time.monotonic() - started > self.acknowledgement_seconds:
            raise DriverContractError(
                "event-value choice acknowledgement exceeded "
                f"{self.acknowledgement_seconds:.3f}s"
            )

    def _replace_line_edit_text_with_qtest(
        self,
        editor: QLineEdit,
        value: str,
    ) -> None:
        if not editor.isVisible() or not editor.isEnabled() or editor.isReadOnly():
            raise DriverContractError("line editor is not visible and editable")
        started = time.monotonic()
        QTest.mouseClick(editor, Qt.MouseButton.LeftButton)
        QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(editor, value)
        self._settle_once()
        if editor.text() != value:
            raise DriverContractError("line editor did not accept visible input")
        if time.monotonic() - started > self.acknowledgement_seconds:
            raise DriverContractError(
                "event-value input acknowledgement exceeded "
                f"{self.acknowledgement_seconds:.3f}s"
            )

    def read_control_value(
        self,
        name: VisibleControl,
        *,
        timeout_seconds: float = 2.0,
    ) -> Any:
        """Read one visible production value without private dialog access."""
        widget = self.control(name, timeout_seconds=timeout_seconds)
        if isinstance(widget, QAbstractButton) and widget.isCheckable():
            return bool(widget.isChecked())
        if isinstance(widget, QComboBox):
            return {
                "display": str(widget.currentText()),
                "value": self._json_value(widget.currentData()),
            }
        if isinstance(widget, QLineEdit):
            return str(widget.text())
        value = getattr(widget, "value", None)
        if callable(value):
            return self._json_value(value())
        text = getattr(widget, "text", None)
        if callable(text):
            return str(text())
        raise DriverContractError(f"{name.value} has no public readable value")

    def read_control_property(
        self,
        name: VisibleControl,
        property_name: str,
        *,
        timeout_seconds: float = 2.0,
    ) -> Any:
        """Read a documented public automation/evidence property."""
        widget = self.control(name, timeout_seconds=timeout_seconds)
        value = widget.property(property_name)
        if value is None:
            raise DriverContractError(
                f"{name.value} lacks public property {property_name!r}"
            )
        detached = self._json_value(value)
        self._observed_control_properties[(name, property_name)] = detached
        return detached

    def last_seen_control_property(
        self,
        name: VisibleControl,
        property_name: str,
    ) -> Any:
        """Return a property captured from the exact control before it closed."""
        key = (name, property_name)
        if key not in self._observed_control_properties:
            raise DriverContractError(
                f"{name.value} property {property_name!r} was not observed"
            )
        return self._observed_control_properties[key]

    def workflow_state_identity(
        self,
        target: str,
        *,
        timeout_seconds: float = 5.0,
    ) -> dict[str, Any]:
        """Hash target-specific protected state from the visible publication owner."""
        if self.root is None:
            raise DriverContractError("MainWindow workflow state is unavailable")
        getter = getattr(self.root, "workflow_state_snapshot", None)
        if not callable(getter):
            raise DriverContractError("MainWindow lacks a workflow state snapshot")
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            try:
                raw = getter()
            except RuntimeError as error:
                if time.monotonic() >= deadline:
                    raise DriverContractError(
                        "MainWindow did not fully render the current workflow "
                        "publication before evidence capture"
                    ) from error
                self._settle_once()
                continue
            break
        if not isinstance(raw, dict) or not isinstance(raw.get("state"), dict):
            raise DriverContractError("MainWindow workflow state snapshot is invalid")
        state = json.loads(json.dumps(raw["state"], sort_keys=True))
        if not isinstance(state, dict):
            raise DriverContractError("MainWindow workflow state snapshot is invalid")
        training = state.get("training")
        if not isinstance(training, dict):
            raise DriverContractError("MainWindow training state is unavailable")
        workflow_inputs = {
            "raw": state.get("raw"),
            "preprocessed": state.get("preprocessed"),
            "epoch": state.get("epoch"),
            "dataset": state.get("dataset"),
            "training_configuration": {
                field: training.get(field)
                for field in (
                    "has_model",
                    "model_name",
                    "model_params",
                    "has_training_option",
                    "training_option",
                )
            },
        }
        visualization = state.get("visualization")
        saliency_output = dict(visualization) if isinstance(visualization, dict) else {}
        saliency_output.pop("post_training_saliency", None)
        protected_state = state
        if target in {"training", "saliency"}:
            protected_state = {
                "workflow_inputs": workflow_inputs,
                "interpretation": state.get("interpretation"),
                "training_producer": {
                    field: training.get(field)
                    for field in (
                        "has_model",
                        "model_name",
                        "model_params",
                        "has_training_option",
                        "training_option",
                        "finished_run_count",
                    )
                },
                "saliency_output": saliency_output,
            }
        return {
            "publication_generation": int(raw["generation"]),
            "publication_revision": int(raw["revision"]),
            "application_state_sha256": self._canonical_sha256(protected_state),
            "workflow_inputs_sha256": self._canonical_sha256(workflow_inputs),
            "saliency_output_sha256": self._canonical_sha256(saliency_output),
            "finished_run_count": int(training.get("finished_run_count") or 0),
        }

    @staticmethod
    def _canonical_sha256(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def choose_tab(
        self,
        tab_text: str,
        *,
        timeout_seconds: float = 2.0,
    ) -> ClickAcknowledgement:
        """Click a named visible Saliency tab through its real tab bar."""
        tabs = self.control(
            VisibleControl.SALIENCY_TABS,
            timeout_seconds=timeout_seconds,
        )
        if not isinstance(tabs, QTabWidget):
            raise DriverContractError("saliency_tabs is not a QTabWidget")
        index = next(
            (i for i in range(tabs.count()) if tabs.tabText(i) == tab_text),
            -1,
        )
        if (
            index < 0
            or not tabs.isTabEnabled(index)
            or tabs.tabBar().isTabVisible(index) is False
        ):
            raise DriverContractError(f"Saliency tab {tab_text!r} is unavailable")
        started = time.monotonic()
        QTest.mouseClick(
            tabs.tabBar(),
            Qt.MouseButton.LeftButton,
            pos=tabs.tabBar().tabRect(index).center(),
        )
        self._settle_once()
        if tabs.currentIndex() != index:
            raise DriverContractError(f"Saliency tab {tab_text!r} did not activate")
        elapsed = time.monotonic() - started
        if elapsed > self.acknowledgement_seconds:
            raise DriverContractError(
                "saliency_tabs acknowledgement exceeded "
                f"{self.acknowledgement_seconds:.3f}s"
            )
        acknowledgement = ClickAcknowledgement(
            control=VisibleControl.SALIENCY_TABS,
            object_name=str(tabs.objectName() or ""),
            accessible_name=tab_text,
            elapsed_seconds=elapsed,
        )
        self.clicks.append(acknowledgement)
        return acknowledgement

    def close_main_window(self, *, timeout_seconds: float = 30.0) -> None:
        """Request the same close path as a user's Alt+F4 action."""
        if self.root is None or not self.root.isVisible():
            raise DriverContractError("MainWindow is not visible for clean close")
        shutdown_completed = getattr(self.root, "shutdown_completed", None)
        connect = getattr(shutdown_completed, "connect", None)
        if not callable(connect):
            raise DriverContractError(
                "MainWindow lacks a terminal shutdown snapshot signal"
            )

        def retain_terminal_snapshot(value: object) -> None:
            if not isinstance(value, dict):
                return
            snapshot = dict(value)
            close_attempt_id = snapshot.get("close_attempt_id")
            workers = snapshot.get("pre_close_remaining_workers")
            subprocesses = snapshot.get("pre_close_remaining_subprocesses")
            if (
                isinstance(close_attempt_id, str)
                and bool(close_attempt_id.strip())
                and snapshot.get("application_closed") is True
                and snapshot.get("pre_close_application_idle") is True
                and isinstance(workers, int)
                and not isinstance(workers, bool)
                and workers == 0
                and isinstance(subprocesses, int)
                and not isinstance(subprocesses, bool)
                and subprocesses == 0
            ):
                self.close_background_snapshot = snapshot
                self.close_terminal_snapshot_observed = True

        connect(retain_terminal_snapshot)
        QTest.keyClick(
            self.root,
            Qt.Key.Key_F4,
            Qt.KeyboardModifier.AltModifier,
        )
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() <= deadline:
            try:
                visible = bool(self.root.isVisible())
            except RuntimeError:
                visible = False
            if not visible:
                if not self.close_terminal_snapshot_observed:
                    raise DriverContractError(
                        "MainWindow closed without a terminal shutdown snapshot"
                    )
                self.close_completed = True
                return
            self._settle_once()
        raise DriverContractError("MainWindow did not complete its clean close path")

    def missing_object_name_hooks(self) -> tuple[str, ...]:
        """Report missing stable object names without using a private fallback."""
        if self.root is None:
            return MINIMUM_PRODUCTION_HOOKS
        observed = {
            widget.objectName()
            for widget in self._candidate_widgets()
            if widget.objectName()
        }
        return tuple(name for name in MINIMUM_PRODUCTION_HOOKS if name not in observed)

    def _visible_operation_progress(self) -> QWidget | None:
        app = QApplication.instance()
        loading_progress_by_id: dict[int, QWidget] = {}
        for root in app.topLevelWidgets() if app is not None else ():
            if not isinstance(root, QWidget) or not root.isVisible():
                continue
            for widget in (root, *root.findChildren(QWidget)):
                if (
                    widget.objectName() == "DataImportLoadingProgress"
                    and widget.isVisible()
                ):
                    loading_progress_by_id[id(widget)] = widget
        loading_progress = list(loading_progress_by_id.values())
        if len(loading_progress) > 1:
            raise DriverContractError("DataImportLoadingProgress is ambiguous")
        if loading_progress:
            return loading_progress[0]
        expected_name = "OwnedOperationProgress"
        matching = [
            widget
            for widget in self._candidate_widgets()
            if widget.objectName() == expected_name and widget.isVisible()
        ]
        if len(matching) > 1:
            raise DriverContractError(f"{expected_name} is ambiguous")
        if not matching:
            return None
        progress = matching[0]
        phase = str(progress.property("operationPhase") or "").casefold()
        if phase in {"pending", "running", "cancelling"}:
            stage = str(progress.property("stage") or "").strip()
            kind = str(progress.property("operationKind") or "").strip()
            detail = str(progress.property("operationDetail") or "").strip()
            current_message = getattr(progress, "currentMessage", None)
            message = str(current_message() or "") if callable(current_message) else ""
            stable_label = {
                "import_review": IMPORT_REVIEW_STATUS_LABEL,
                "import_apply": IMPORT_APPLY_STATUS_LABEL,
            }.get(kind, "")
            if stable_label:
                stable_message_visible = (
                    message == f"Cancelling · {stable_label}"
                    if phase == "cancelling"
                    else message.startswith(f"{stable_label} ·")
                )
                if not stage or not stable_message_visible or detail != stage:
                    return None
            elif stage and stage not in message:
                return None
        return progress

    @staticmethod
    def _active_operation_evidence(widget: QWidget) -> ActiveOperationEvidence:
        operation_id = str(widget.property("operationId") or "").strip()
        stage = str(widget.property("stage") or "").strip()
        phase = str(widget.property("operationPhase") or "").casefold()
        display = str(widget.property("progress") or "").strip()
        raw_indeterminate = widget.property("indeterminate")
        if not operation_id or not stage or not phase:
            raise DriverContractError("visible operation identity is incomplete")
        if type(raw_indeterminate) is not bool:
            raise DriverContractError(
                "visible operation progress mode is not a product boolean"
            )
        indeterminate = raw_indeterminate
        if indeterminate:
            if display != "indeterminate":
                raise DriverContractError(
                    "visible indeterminate operation progress is inconsistent"
                )
            completed: int | None = None
            total: int | None = None
        else:
            match = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", display)
            if match is None:
                raise DriverContractError(
                    "visible determinate operation progress is malformed"
                )
            completed = int(match.group(1))
            total = int(match.group(2))
            if completed > total:
                raise DriverContractError(
                    "visible operation progress exceeds its declared total"
                )
        return ActiveOperationEvidence(
            operation_id=operation_id,
            stage=stage,
            phase=phase,
            progress={
                "display": display,
                "completed": completed,
                "total": total,
                "indeterminate": indeterminate,
            },
            operation_kind=str(widget.property("operationKind") or "").strip(),
        )

    @staticmethod
    def _progress_signature(widget: QWidget) -> tuple[str, ...]:
        values = [
            str(widget.property("operationId") or ""),
            str(widget.property("operationKind") or ""),
            str(widget.property("stage") or ""),
            str(widget.property("progress") or ""),
        ]
        text = getattr(widget, "text", None)
        if callable(text):
            values.append(str(text() or ""))
        value = getattr(widget, "value", None)
        if callable(value):
            values.append(str(value()))
        current_message = getattr(widget, "currentMessage", None)
        if callable(current_message):
            values.append(str(current_message() or ""))
        return tuple(values)

    @staticmethod
    def _table_column_values(table: Any, heading: str) -> list[str]:
        if not isinstance(table, QTableWidget):
            return []
        column = next(
            (
                index
                for index in range(table.columnCount())
                if table.horizontalHeaderItem(index) is not None
                and table.horizontalHeaderItem(index).text().strip() == heading
            ),
            -1,
        )
        if column < 0:
            return []
        return [
            item.text().strip()
            for row in range(table.rowCount())
            if (item := table.item(row, column)) is not None and item.text().strip()
        ]

    def _lookup(self, name: VisibleControl) -> Any | None:
        if self._control_lookup is not None:
            return self._control_lookup(name)
        locator = CONTROL_LOCATORS[name]
        matching: list[QWidget] = []
        for widget in self._candidate_widgets():
            if locator.widget_type is not None and not isinstance(
                widget, locator.widget_type
            ):
                continue
            object_matches = bool(
                locator.object_name and widget.objectName() == locator.object_name
            )
            accessible = self._accessible_name(widget)
            accessible_matches = bool(
                locator.accessible_label and accessible == locator.accessible_label
            )
            prefix_matches = bool(
                locator.accessible_prefix
                and accessible.startswith(locator.accessible_prefix)
            )
            if object_matches or accessible_matches or prefix_matches:
                matching.append(widget)
        usable = [
            widget for widget in matching if widget.isVisible() and widget.isEnabled()
        ]
        if len(usable) > 1:
            identities = ", ".join(
                f"{widget.objectName()}:{self._accessible_name(widget)}"
                for widget in usable
            )
            raise DriverContractError(f"{name.value} is ambiguous: {identities}")
        return usable[0] if usable else matching[0] if len(matching) == 1 else None

    def _visible_named_widget(
        self,
        object_name: str,
        widget_type: type[Any],
        *,
        timeout_seconds: float,
    ) -> Any:
        """Find exactly one usable public widget on the active product surface."""
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            matching = [
                widget
                for widget in self._candidate_widgets()
                if isinstance(widget, widget_type)
                and widget.objectName() == object_name
                and widget.isVisible()
                and widget.isEnabled()
            ]
            if len(matching) == 1:
                return matching[0]
            if len(matching) > 1:
                raise DriverContractError(f"public widget {object_name!r} is ambiguous")
            if time.monotonic() >= deadline:
                raise DriverContractError(
                    f"public widget {object_name!r} is not visible and enabled"
                )
            self._settle_once()

    def _ensure_widget_visible(self, widget: QWidget) -> None:
        ancestor = widget.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QScrollArea):
                ancestor.ensureWidgetVisible(widget)
            ancestor = ancestor.parentWidget()
        self._settle_once()

    def _candidate_widgets(self) -> Iterator[QWidget]:
        seen: set[int] = set()
        app = QApplication.instance()
        roots: list[QWidget] = []
        if app is not None:
            modal = app.activeModalWidget()
            if modal is not None and modal.isVisible():
                roots.append(modal)
            else:
                roots.extend(
                    widget
                    for widget in app.topLevelWidgets()
                    if isinstance(widget, QWidget) and widget.isVisible()
                )
        if self.root is not None and not roots:
            roots.append(self.root)
        for root in roots:
            for widget in (root, *root.findChildren(QWidget)):
                identity = id(widget)
                if identity in seen:
                    continue
                seen.add(identity)
                yield widget

    @staticmethod
    def _accessible_name(widget: Any) -> str:
        accessible_name = getattr(widget, "accessibleName", None)
        accessible = (
            str(accessible_name() or "").strip() if callable(accessible_name) else ""
        )
        if accessible:
            return accessible
        text = getattr(widget, "text", None)
        return str(text() or "").strip() if callable(text) else ""

    @classmethod
    def _json_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, dict):
            return {str(key): cls._json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_value(item) for item in value]
        enum_value = getattr(value, "value", None)
        if enum_value is not None and enum_value is not value:
            return cls._json_value(enum_value)
        return str(value)

    def _settle_once(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
            QTest.qWait(self.poll_interval_ms)
            app.processEvents()
