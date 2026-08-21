"""Sidebar widget for the training panel with configuration and execution controls."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, cast

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGroupBox,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import (
    ApplicationError,
    ClearTrainingHistoryCommand,
    CommandCapability,
    CommandName,
    ConfigureTrainingCommand,
    DiscardTrainingPreparationCommand,
    ErrorType,
    QueryStateCommand,
    SaveDatasetSplitCommand,
    StopTrainingCommand,
    TrainCommand,
)
from XBrainLab.backend.application.resource_guard import (
    RISK_BLOCKING,
    RISK_SAFE,
    RISK_UNKNOWN,
    RISK_WARNING,
    ResourceChecker,
    TrainingResourcePreviewReceipt,
    TrainingResourcePreviewRequest,
    TrainingResourcePreviewResult,
)
from XBrainLab.backend.application.resource_preflight import (
    ResourcePreflightContractError,
    ResourcePreflightView,
)
from XBrainLab.backend.application.training_recommendation import (
    TrainingRecommendation,
    TrainingRecommendationField,
)
from XBrainLab.backend.application.training_resource_preview_coordinator import (
    TrainingResourcePreviewTicket,
)
from XBrainLab.backend.application.training_submission import (
    attach_training_submission_provenance,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    ApplicationUiRuntime,
    ControllerCompatibilityUnavailableError,
    DatasetSplitDialogBinding,
    blocked_reason,
    cancel_application_operation,
    execute_application_command,
    execute_application_command_async,
    get_application_operation,
    get_application_view_publication,
    get_command_capability,
    get_command_review_context,
    get_dataset_split_dialog_binding,
    has_real_application_context,
    is_stale_publication_result,
    run_controller_compatibility_call,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel, SidebarScrollArea
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)

# Dialog imports will be local to avoid circular deps if needed,
# or top level if no circular dep.
# TrainingPanel imports Sidebar. Sidebar imports Dialogs.
# Dialogs don't import Panel/Sidebar.
from XBrainLab.ui.dialogs.dataset import DataSplittingDialog
from XBrainLab.ui.dialogs.training import ModelSelectionDialog, TrainingSettingDialog
from XBrainLab.ui.interaction_outcome import InteractionOutcome
from XBrainLab.ui.owned_operation_presenter import OwnedOperationPresenter
from XBrainLab.ui.status import show_status_message
from XBrainLab.ui.styles.stylesheets import Stylesheets

_TRAINING_SETTING_SUGGESTION_KEYS = frozenset(
    {
        "epoch",
        "batch_size",
        "learning_rate",
        "repeat",
        "optimizer",
        "evaluation_option",
        "evaluation_strategy",
        "device",
    }
)
_PUBLICATION_UNSET = object()


@dataclass(frozen=True, slots=True)
class _TrainingSettingSelection:
    option: Any
    device: str
    edited_recommendation_fields: frozenset[TrainingRecommendationField]
    resource_preview_receipt: TrainingResourcePreviewReceipt | None = None


@dataclass(frozen=True, slots=True)
class _TrainingResourcePreviewTask:
    request: TrainingResourcePreviewRequest
    callback: Callable[[TrainingResourcePreviewResult], object]
    token: int


class TrainingSidebar(QWidget):
    """Sidebar for ``TrainingPanel`` providing configuration and execution controls.

    Hosts data-splitting, model-selection, training-setting dialogs,
    and start/stop/clear buttons.  Validates readiness before enabling
    the start button.

    Attributes:
        panel: The parent ``TrainingPanel`` reference.
        info_panel: ``AggregateInfoPanel`` displaying summary statistics.
        btn_split: Button for dataset splitting configuration.
        btn_model: Button for model selection.
        btn_setting: Button for training hyperparameter settings.
        btn_start: Button to start training (enabled when ready).
        btn_stop: Button to stop an in-progress training run.
        btn_clear: Button to clear training history.

    """

    def __init__(self, panel, parent=None):
        """Initialize the training sidebar.

        Args:
            panel: The parent ``TrainingPanel``.
            parent: Optional parent widget.

        """
        super().__init__()
        self.panel = panel
        self._training_resource_preview_ticket: TrainingResourcePreviewTicket | None = (
            None
        )
        self._training_resource_preview_active_task: (
            _TrainingResourcePreviewTask | None
        ) = None
        self._training_resource_preview_timer = QTimer(self)
        self._training_resource_preview_timer.setInterval(25)
        self._training_resource_preview_timer.timeout.connect(
            self._poll_training_resource_preview
        )
        self._training_resource_preview_token = 0
        self._training_resource_preview_shutdown_requested = False
        if isinstance(panel, QWidget):
            panel.installEventFilter(self)
        application = QApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(
                self._shutdown_training_resource_previews,
            )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.init_ui()

    def eventFilter(self, watched, event):  # noqa: N802
        """Stop advisory preview delivery when the owning panel closes."""
        if (
            watched is getattr(self, "panel", None)
            and event is not None
            and event.type() == QEvent.Type.Close
        ):
            self._shutdown_training_resource_previews()
        return super().eventFilter(watched, event)

    def closeEvent(self, event):  # noqa: N802
        """Abandon advisory preview work without delaying widget close."""
        self._shutdown_training_resource_previews()
        super().closeEvent(event)

    @property
    def controller(self):
        """TrainingController: The training controller from the parent panel."""
        return self.panel.controller

    @property
    def dataset_controller(self):
        """DatasetController: The dataset controller from the parent panel."""
        return self.panel.dataset_controller

    @property
    def main_window(self):
        """QMainWindow: The application main window reference."""
        return self.panel.main_window

    def _has_typed_product_context(self) -> bool:
        return getattr(self.panel, "_typed_port_mode", False) is True

    def _panel_port(self, name: str):
        panel_state = getattr(self.panel, "__dict__", {})
        return panel_state.get(name) if isinstance(panel_state, dict) else None

    def _application_publication(self):
        publication_port = self._panel_port("_publication_port")
        if self._has_typed_product_context() and publication_port is None:
            return None
        return get_application_view_publication(
            self,
            runtime=(
                cast(ApplicationUiRuntime, publication_port)
                if publication_port is not None
                else None
            ),
        )

    def _command_capability(self, command_name: CommandName | str):
        publication_port = self._panel_port("_publication_port")
        if self._has_typed_product_context() and publication_port is None:
            return None
        return get_command_capability(
            self,
            command_name,
            runtime=(
                cast(ApplicationUiRuntime, publication_port)
                if publication_port is not None
                else None
            ),
        )

    def _command_review_context(self, command_name: CommandName | str):
        publication_port = self._panel_port("_publication_port")
        if self._has_typed_product_context() and publication_port is None:
            return None
        return get_command_review_context(
            self,
            command_name,
            runtime=(
                cast(ApplicationUiRuntime, publication_port)
                if publication_port is not None
                else None
            ),
        )

    @staticmethod
    def _published_capability(
        publication: Any,
        command_name: CommandName,
    ) -> CommandCapability | None:
        """Read an optional capability without trusting a partial policy."""
        capabilities = getattr(publication, "effective_capabilities", None)
        lookup = getattr(capabilities, "get", None)
        if not callable(lookup):
            return None
        for key in (command_name, command_name.value):
            try:
                candidate = lookup(key)
            except (KeyError, TypeError, ValueError):
                continue
            if isinstance(candidate, CommandCapability):
                return candidate
        return None

    def _execute_action(self, command, **kwargs):
        action_port = self._panel_port("_action_port")
        if self._has_typed_product_context() and action_port is None:
            return None
        return execute_application_command(
            self,
            command,
            runtime=(
                cast(ApplicationUiRuntime, action_port)
                if action_port is not None
                else None
            ),
            **kwargs,
        )

    def _execute_action_async(self, command, **kwargs) -> bool:
        action_port = self._panel_port("_action_port")
        if self._has_typed_product_context() and action_port is None:
            return False
        return execute_application_command_async(
            self,
            command,
            runtime=(
                cast(ApplicationUiRuntime, action_port)
                if action_port is not None
                else None
            ),
            **kwargs,
        )

    def init_ui(self):
        """Build the sidebar layout with info, configuration, and execution groups."""
        self.setFixedWidth(260)
        self.setObjectName("RightPanel")
        self.setStyleSheet(Stylesheets.SIDEBAR_CONTAINER)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.scroll_area = SidebarScrollArea(self)
        root_layout.addWidget(self.scroll_area)
        layout = self.scroll_area.content_layout

        self.info_panel = AggregateInfoPanel(self.main_window)
        self.info_panel.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        layout.addWidget(self.info_panel)

        layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(Stylesheets.SEPARATOR_HORIZONTAL)
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(10)

        # Group 1: Configuration
        config_group = QGroupBox("CONFIGURATION")
        config_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        config_group.setMinimumHeight(Stylesheets.SIDEBAR_PRIMARY_GROUP_MIN_HEIGHT)
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(0, 10, 0, 0)
        config_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_split = QPushButton("Dataset Splitting")
        self.btn_split.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_split.clicked.connect(self.split_data)
        config_layout.addWidget(self.btn_split)

        self.btn_model = QPushButton("Model Selection")
        self.btn_model.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_model.clicked.connect(self.select_model)
        config_layout.addWidget(self.btn_model)

        self.btn_setting = QPushButton("Training Setting")
        self.btn_setting.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_setting.clicked.connect(self.training_setting)
        config_layout.addWidget(self.btn_setting)

        layout.addWidget(config_group)
        layout.addSpacing(Stylesheets.SIDEBAR_GROUP_GAP)

        # Group 2: Execution
        exec_group = QGroupBox("EXECUTION")
        exec_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        exec_layout = QVBoxLayout(exec_group)
        exec_layout.setContentsMargins(0, 10, 0, 0)
        exec_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_start = QPushButton("Start Training")
        self.btn_start.setObjectName("TrainingStartButton")
        self.btn_start.setStyleSheet(Stylesheets.BTN_PRIMARY)
        self.btn_start.clicked.connect(self.start_training_ui_action)
        self.btn_start.setEnabled(False)
        exec_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop Training")
        self.btn_stop.setObjectName("TrainingStopButton")
        self.btn_stop.setStyleSheet(Stylesheets.BTN_WARNING)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_training)
        exec_layout.addWidget(self.btn_stop)

        self._training_operation_presenter = OwnedOperationPresenter(
            self,
            cancel_button=self.btn_stop,
            snapshot_getter=lambda operation_id: get_application_operation(
                self,
                operation_id,
            ),
            canceller=lambda operation_id: cancel_application_operation(
                self,
                operation_id,
            ),
            connect_button=False,
            hide_when_idle=False,
        )

        self.btn_clear = QPushButton("Clear History")
        self.btn_clear.setStyleSheet(Stylesheets.BTN_DANGER)
        self.btn_clear.clicked.connect(self.clear_history)
        exec_layout.addWidget(self.btn_clear)

        layout.addWidget(exec_group)
        layout.addStretch()

        # Initial check
        self.check_ready_to_train()

    def set_busy(self, busy: bool) -> None:
        """Prevent duplicate starts without disabling the whole Training page."""
        if busy:
            self.btn_start.setEnabled(False)
            self.btn_start.setToolTip("Training is being prepared.")
            return
        self.check_ready_to_train()

    def _compatibility_controller_value(
        self,
        fallback: Callable[[], Any],
        *,
        blocked_title: str | None = None,
    ) -> tuple[bool, Any]:
        """Read controller compatibility state only for mock UI contexts."""
        if self._has_product_publication_context():
            if blocked_title is not None:
                QMessageBox.warning(
                    self,
                    blocked_title,
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
            return False, None
        try:
            return True, run_controller_compatibility_call(self, fallback)
        except ControllerCompatibilityUnavailableError as exc:
            if blocked_title is not None:
                QMessageBox.warning(self, blocked_title, str(exc))
            return False, None

    def check_ready_to_train(
        self,
        *args,
        publication: Any = _PUBLICATION_UNSET,
    ):
        """Check if all configurations are set and enable/disable start button."""
        if publication is _PUBLICATION_UNSET:
            publication = self._application_publication()
        self._sync_clear_history_presentation(publication)
        real_application_context = self._has_product_publication_context()
        train_capability: CommandCapability | None = None
        if publication is not None and bool(getattr(publication, "usable", False)):
            train_capability = self._published_capability(
                publication,
                CommandName.TRAIN,
            )
        elif not real_application_context:
            train_capability = self._command_capability(CommandName.TRAIN)
        if train_capability is None and real_application_context:
            self.btn_start.setEnabled(False)
            self.btn_start.setToolTip("Training state is unavailable right now.")
            return
        if train_capability is None:
            available, ready_value = self._compatibility_controller_value(
                self.controller.validate_ready,
            )
            if not available:
                self.btn_start.setEnabled(False)
                self.btn_start.setToolTip(
                    "Training state is unavailable right now.",
                )
                return
            ready = bool(ready_value)
        else:
            ready = train_capability.enabled
        self.btn_start.setEnabled(ready)

        if not ready:
            if train_capability is None:
                available, missing = self._compatibility_controller_value(
                    self._compatibility_missing_training_config,
                )
                if not available:
                    self.btn_start.setToolTip(
                        "Training state is unavailable right now.",
                    )
                    return
                self.btn_start.setToolTip(f"Please configure: {', '.join(missing)}")
            else:
                self.btn_start.setToolTip(
                    blocked_reason(
                        train_capability,
                        "Training is not ready. Check dataset, model, and settings.",
                    )
                )
        else:
            self.btn_start.setToolTip("Start Training")

    def _sync_clear_history_presentation(self, publication: Any) -> None:
        """Project the published clear-history capability onto its button."""
        if publication is None:
            return
        if not bool(getattr(publication, "usable", False)):
            self.btn_clear.setEnabled(False)
            self.btn_clear.setToolTip("Training state is unavailable right now.")
            return
        clear_capability = self._published_capability(
            publication,
            CommandName.CLEAR_TRAINING_HISTORY,
        )
        if clear_capability is None:
            self.btn_clear.setEnabled(False)
            self.btn_clear.setToolTip("Training history state is unavailable.")
            return
        self.btn_clear.setEnabled(clear_capability.enabled)
        self.btn_clear.setToolTip(
            "Clear training history"
            if clear_capability.enabled
            else blocked_reason(
                clear_capability,
                "Training history cannot be cleared right now.",
            )
        )

    def _has_product_publication_context(self) -> bool:
        panel_state = getattr(self.panel, "__dict__", {})
        publication_port = (
            panel_state.get("_publication_port")
            if isinstance(panel_state, dict)
            else None
        )
        return (
            self._has_typed_product_context()
            or has_real_application_context(self)
            or publication_port is not None
        )

    def _compatibility_missing_training_config(self) -> list[str]:
        missing = []
        if not self.controller.has_datasets():
            missing.append("Data Splitting")
        if not self.controller.has_model():
            missing.append("Model Selection")
        if not self.controller.has_training_option():
            missing.append("Training Settings")
        return missing

    @staticmethod
    def _resource_preflight_from_command_result(
        result: Any,
    ) -> ResourcePreflightView | None:
        """Read the sole typed UI view from backend-owned diagnostics."""
        diagnostics = getattr(result, "diagnostics", {}) or {}
        try:
            return ResourcePreflightView.from_diagnostics(diagnostics)
        except ResourcePreflightContractError:
            return None

    def _show_training_resource_blocking_dialog(self, message: str) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle("Training Resource Check")
        dialog.setText("Training cannot start safely.")
        dialog.setInformativeText(message)
        adjust_button = dialog.addButton(
            "Adjust Settings",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(adjust_button)
        dialog.exec()
        if dialog.clickedButton() is adjust_button:
            self.training_setting()

    def _training_resource_dialog_message(
        self,
        result: ResourcePreflightView,
    ) -> str:
        model_name = result.model_name or "Unknown"
        batch_size = result.batch_size
        gpu_name = result.vram.gpu_name
        risk_level = self._training_resource_risk_level(result)
        risk_label = {
            RISK_BLOCKING: "Too large",
            RISK_WARNING: "Warning",
            RISK_UNKNOWN: "Unknown",
        }.get(risk_level, "Safe")
        message_title = str(
            next(iter(result.issues or result.warnings or result.unknowns), "")
            or result.message
            or result.vram.message
            or "Training resource check"
        )
        message_title = message_title.splitlines()[0]

        lines = [
            message_title,
            "",
            f"Model: {model_name}",
            f"Batch size: {batch_size if batch_size is not None else 'Unknown'}",
        ]
        if gpu_name:
            lines.append(f"GPU: {gpu_name}")
        lines.extend(
            [
                f"Risk level: {risk_label}",
                "",
                "RAM",
                "Estimated RAM required: "
                f"{ResourceChecker.format_memory_size(result.dataset_ram.required_memory_bytes)}",
                "Available RAM: "
                f"{ResourceChecker.format_memory_size(result.dataset_ram.available_memory_bytes)}",
                "RAM risk level: "
                f"{self._training_resource_risk_label(result.dataset_ram.risk_level)}",
                "",
                "GPU memory",
                "Estimated VRAM required: "
                f"{ResourceChecker.format_memory_size(result.vram.required_memory_bytes)}",
                "Available VRAM: "
                f"{ResourceChecker.format_memory_size(result.vram.available_memory_bytes)}",
                "VRAM risk level: "
                f"{self._training_resource_risk_label(result.vram.risk_level)}",
            ]
        )
        reasons = self._training_resource_unknown_reasons(result)
        if reasons:
            lines.extend(["", "Why the estimate is unknown:"])
            lines.extend(f"- {reason}" for reason in reasons)
        suggestions = list(result.suggestions)
        suggestions.extend(result.dataset_ram.suggestions)
        suggestions.extend(result.vram.suggestions)
        unique_suggestions = list(dict.fromkeys(str(item) for item in suggestions))
        if unique_suggestions:
            lines.extend(["", "Suggestions:"])
            lines.extend(f"- {suggestion}" for suggestion in unique_suggestions)
        return "\n".join(lines)

    @staticmethod
    def _training_resource_risk_level(result: ResourcePreflightView) -> str:
        return result.risk_level

    @staticmethod
    def _training_resource_risk_label(risk_level: Any) -> str:
        return {
            RISK_BLOCKING: "Too large",
            RISK_WARNING: "Warning",
            RISK_UNKNOWN: "Unknown",
            RISK_SAFE: "Safe",
        }.get(str(risk_level), "Unknown")

    @staticmethod
    def _training_model_name(model_holder: Any | None) -> str:
        if model_holder is None:
            return "Unknown"
        target_model = getattr(model_holder, "target_model", None)
        name = getattr(target_model, "__name__", None)
        if name:
            return str(name)
        for attr in ("model_name", "name"):
            value = getattr(model_holder, attr, None)
            if value:
                return str(value)
        return "Unknown"

    @staticmethod
    def _training_resource_unknown_reasons(
        result: ResourcePreflightView,
    ) -> list[str]:
        reasons: list[str] = []
        if result.dataset_ram.risk_level == RISK_UNKNOWN:
            reasons.append("Available system RAM could not be read.")

        reason = result.vram.reason or result.reason
        if reason == "application_preflight_unavailable":
            reasons.append(
                "The current ApplicationService configuration could not be read "
                "after one retry."
            )
        elif reason == "missing_training_option":
            reasons.append("Training settings have not been saved.")
        elif result.vram.risk_level == RISK_UNKNOWN:
            if result.vram.gpu_index is not None:
                reasons.append("GPU memory could not be read for the selected device.")
            else:
                reasons.append("CUDA did not report available GPU memory.")
        return list(dict.fromkeys(reasons))

    def update_info(self):
        """Refresh the aggregate info panel (delegated to InfoPanelService)."""
        if not self.info_panel:
            return

        # Handled by InfoPanelService

    def _show_status(self, message: str) -> None:
        panel_status = getattr(self.panel, "show_status_message", None)
        if callable(panel_status) and panel_status(message):
            return
        show_status_message(self, message)

    # --- Actions ---

    def _configuration_blocked(
        self,
        fallback_message: str,
        *,
        review_context: Any | None = None,
        context_resolved: bool = False,
    ) -> bool:
        """Return whether training configuration edits should be blocked."""
        configure_capability = (
            getattr(review_context, "capability", None)
            if context_resolved
            else self._command_capability(CommandName.CONFIGURE_TRAINING)
        )
        if configure_capability is not None and not configure_capability.enabled:
            QMessageBox.warning(
                self,
                "Training Configuration Blocked",
                blocked_reason(configure_capability, fallback_message),
            )
            return True
        if configure_capability is None:
            available, is_training = self._compatibility_controller_value(
                self.controller.is_training,
                blocked_title="Training Configuration Blocked",
            )
            if not available:
                return True
            if not is_training:
                return False
            QMessageBox.warning(
                self,
                "Training Running",
                fallback_message,
            )
            return True
        return False

    def split_data(
        self,
        *,
        suggested_values: dict[str, str] | None = None,
    ) -> InteractionOutcome:
        """Open the data-splitting dialog and apply the configuration.

        Validates that epoched data exists and training is not running.
        Warns if existing datasets/history will be cleared.
        """
        publication = self._application_publication()
        generate_capability = (
            self._published_capability(publication, CommandName.CONFIGURE_DATASET_SPLIT)
            if publication is not None
            else None
        )
        if self._data_splitting_blocked(
            generate_capability,
            capability_resolved=True,
        ):
            return InteractionOutcome.blocked("Data splitting is not available.")

        if (
            generate_capability is None
            and self._compatibility_data_splitting_preflight_blocked()
        ):
            return InteractionOutcome.blocked(
                "Data splitting prerequisites could not be verified."
            )

        dialog_binding = self._data_splitting_dialog_context(
            expected_publication_generation=(
                publication.generation if publication is not None else None
            ),
        )
        if dialog_binding is None:
            return InteractionOutcome.blocked(
                "EEG epochs are unavailable for data splitting."
            )

        win = DataSplittingDialog(
            self,
            split_context=dialog_binding.split_context,
            publication_generation=dialog_binding.publication_generation,
            preview_provider=dialog_binding.preview_provider,
            preview_canceller=dialog_binding.preview_canceller,
            initial_values=dict(suggested_values or {}),
        )
        if not win.exec():
            return InteractionOutcome.cancelled("Data splitting was cancelled.")

        split_config = win.get_result()
        preview_receipt = win.get_preview_receipt()
        if not split_config or preview_receipt is None:
            return InteractionOutcome.blocked(
                "The accepted data split no longer matches its preview."
            )
        command = SaveDatasetSplitCommand(
            split_config=dict(split_config),
            preview_receipt=preview_receipt,
        )

        def _handle_generate_result(result) -> InteractionOutcome:
            if is_stale_publication_result(result):
                self._show_message_box(
                    QMessageBox.Icon.Warning,
                    "Review Data Splitting Again",
                    result.message,
                )
                return InteractionOutcome.blocked(result.message)
            if result.failed:
                self._show_message_box(
                    QMessageBox.Icon.Critical,
                    "Data Splitting Failed",
                    result.message,
                )
                return self._interaction_failure_outcome(result)
            self._show_status("Data splitting configuration saved")
            return InteractionOutcome.completed(result.message)

        def _handle_generate_error(error: tuple) -> None:
            present_unexpected_error(
                self,
                UnexpectedErrorContext.TRAINING_DATA_SPLITTING,
                error_info=error,
                message_box=QMessageBox,
            )

        if self._execute_action_async(
            command,
            on_result=_handle_generate_result,
            on_error=_handle_generate_error,
            busy_target=self,
            expected_publication_generation=(
                publication.generation if publication is not None else None
            ),
        ):
            return InteractionOutcome.accepted("Data splitting settings will be saved.")

        if self._has_product_publication_context():
            QMessageBox.warning(
                self,
                "Data Splitting Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return InteractionOutcome.blocked(
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )

        result = self._execute_action(
            command,
            expected_publication_generation=(
                publication.generation if publication is not None else None
            ),
        )
        if result is None:
            QMessageBox.warning(
                self,
                "Data Splitting Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return InteractionOutcome.blocked(
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )
        return _handle_generate_result(result)

    def _show_message_box(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
    ) -> None:
        message = QMessageBox(self)
        message.setIcon(icon)
        message.setWindowTitle(title)
        message.setText(text)
        message.setStandardButtons(QMessageBox.StandardButton.Ok)
        for button in message.buttons():
            if isinstance(button, QPushButton):
                button.setAutoDefault(False)
                button.setDefault(False)
        message.exec()

    def _compatibility_data_splitting_preflight_blocked(self) -> bool:
        available, data_list = self._compatibility_controller_value(
            self.controller.get_loaded_data_list,
            blocked_title="Data Splitting Blocked",
        )
        if not available:
            return True
        if not data_list:
            QMessageBox.warning(
                self,
                "No Data",
                "Please load and preprocess data first.",
            )
            return True

        available, epoch_data = self._compatibility_controller_value(
            self.controller.get_epoch_data,
            blocked_title="Data Splitting Blocked",
        )
        if not available:
            return True
        if epoch_data is None:
            QMessageBox.warning(
                self,
                "No EEG Epochs",
                "Create EEG epochs in the Preprocess panel first.",
            )
            return True

        available, is_training = self._compatibility_controller_value(
            self.controller.is_training,
            blocked_title="Data Splitting Blocked",
        )
        if not available:
            return True
        if is_training:
            QMessageBox.warning(
                self,
                "Training Running",
                "Cannot change data splitting while training is running.",
            )
            return True
        return False

    def _data_splitting_blocked(
        self,
        generate_capability=None,
        *,
        capability_resolved: bool = False,
    ) -> bool:
        if not capability_resolved:
            generate_capability = self._command_capability(
                CommandName.CONFIGURE_DATASET_SPLIT
            )
        if generate_capability is None or generate_capability.enabled:
            return False

        QMessageBox.warning(
            self,
            "Data Splitting Blocked",
            blocked_reason(
                generate_capability,
                "Create EEG epochs before generating training datasets.",
            ),
        )
        return True

    def _data_splitting_dialog_context(
        self,
        *,
        expected_publication_generation: int | None = None,
    ) -> DatasetSplitDialogBinding | None:
        if expected_publication_generation is None:
            QMessageBox.warning(
                self,
                "Data Splitting Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return None
        try:
            query_port = self._panel_port("_query_port")
            if self._has_typed_product_context() and query_port is None:
                return None
            if query_port is None:
                binding = get_dataset_split_dialog_binding(
                    self,
                    publication_generation=expected_publication_generation,
                )
            else:
                binding = get_dataset_split_dialog_binding(
                    self,
                    publication_generation=expected_publication_generation,
                    runtime=cast(ApplicationUiRuntime, query_port),
                )
        except ApplicationError as exc:
            diagnostics = getattr(exc, "diagnostics", {}) or {}
            stale_context = "requested_generation" in diagnostics and any(
                key in diagnostics
                for key in (
                    "current_generation",
                    "before_generation",
                    "after_generation",
                )
            )
            QMessageBox.warning(
                self,
                (
                    "Review Data Splitting Again"
                    if stale_context
                    else "Data Splitting Blocked"
                ),
                str(exc),
            )
            return None
        except (TypeError, ValueError):
            QMessageBox.warning(
                self,
                "Data Splitting Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return None
        if binding is None or not binding.split_context.epoch_available:
            QMessageBox.warning(
                self,
                "Data Splitting Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return None
        return binding

    def select_model(
        self,
        suggested_model: str | None = None,
    ) -> InteractionOutcome:
        """Open the model-selection dialog and store the chosen model.

        Blocked while training is running.
        """
        if not isinstance(suggested_model, str):
            suggested_model = None
        review_context = self._command_review_context(CommandName.CONFIGURE_TRAINING)
        if self._configuration_blocked(
            "Cannot change model while training is running.",
            review_context=review_context,
            context_resolved=True,
        ):
            return InteractionOutcome.blocked(
                "The model cannot be changed while training is running."
            )

        model_holder = self._collect_model_selection(suggested_model)
        if isinstance(model_holder, InteractionOutcome):
            return model_holder
        command = self._configure_training_command(model_holder=model_holder)
        return self._apply_training_configuration(
            command,
            blocked_title="Model Selection Blocked",
            failed_title="Model Selection Failed",
            success_status=f"Model selected: {command.model_name}.",
            expected_publication_generation=(
                review_context.publication_generation
                if review_context is not None
                else None
            ),
        )

    def configure_training(
        self,
        *,
        suggested_model: str | None = None,
        suggested_values: dict[str, str] | None = None,
    ) -> InteractionOutcome:
        """Collect model and option choices, then commit one atomic command."""
        if not isinstance(suggested_model, str):
            suggested_model = None
        if not isinstance(suggested_values, dict):
            suggested_values = None
        review_context = self._command_review_context(CommandName.CONFIGURE_TRAINING)
        expected_generation = (
            review_context.publication_generation
            if review_context is not None
            else None
        )
        if self._configuration_blocked(
            "Cannot change training configuration while training is running.",
            review_context=review_context,
            context_resolved=True,
        ):
            return InteractionOutcome.blocked(
                "Training configuration cannot be changed while training is running."
            )

        initial_option = self._training_setting_initial_option(
            suggested_values,
            expected_publication_generation=expected_generation,
        )
        if isinstance(initial_option, InteractionOutcome):
            return initial_option
        model_holder = self._collect_model_selection(suggested_model)
        if isinstance(model_holder, InteractionOutcome):
            return model_holder
        prospective_model = self._configure_training_command(
            model_holder=model_holder,
        )
        recommendation = self._training_setting_recommendation(
            expected_publication_generation=expected_generation,
            prospective_model_name=prospective_model.model_name,
            prospective_model_params=dict(prospective_model.model_params),
        )
        resource_preview_request = self._training_resource_preview_request(
            initial_option,
            recommendation=recommendation,
            proposed_values=suggested_values,
            expected_publication_generation=expected_generation,
            prospective_model_name=prospective_model.model_name,
            prospective_model_params=dict(prospective_model.model_params),
        )
        selection = self._collect_training_option(
            initial_option,
            recommendation=recommendation,
            proposed_values=suggested_values,
            device_recommendation_provider=lambda device: (
                self._training_device_recommendation(
                    device,
                    expected_publication_generation=expected_generation,
                    prospective_model_name=prospective_model.model_name,
                    prospective_model_params=dict(prospective_model.model_params),
                )
            ),
            resource_preview_request=resource_preview_request,
        )
        if isinstance(selection, InteractionOutcome):
            return selection

        return self._apply_training_configuration(
            self._configure_training_command(
                model_holder=model_holder,
                training_option=selection.option,
                device=selection.device,
                edited_recommendation_fields=(selection.edited_recommendation_fields),
                resource_preview_receipt=selection.resource_preview_receipt,
            ),
            blocked_title="Training Configuration Blocked",
            failed_title="Training Configuration Failed",
            success_status="Training configuration saved",
            expected_publication_generation=expected_generation,
        )

    def _collect_model_selection(
        self,
        suggested_model: str | None,
    ) -> Any | InteractionOutcome:
        query_port = self._panel_port("_query_port")
        dialog_kwargs: dict[str, Any] = {
            "initial_model_name": suggested_model,
        }
        if query_port is not None:
            dialog_kwargs["query_port"] = query_port
        win = ModelSelectionDialog(
            self,
            self.controller,
            **dialog_kwargs,
        )
        if not win.exec():
            return InteractionOutcome.cancelled("Model selection was cancelled.")

        model_holder = win.get_result()
        if model_holder is None:
            message = "No model was selected."
            QMessageBox.warning(self, "Model Selection", message)
            return InteractionOutcome.failed(message)
        return model_holder

    def training_setting(
        self,
        suggested_values: dict[str, str] | None = None,
    ) -> InteractionOutcome:
        """Open the training-settings dialog and store the configuration.

        Blocked while training is running.
        """
        if not isinstance(suggested_values, dict):
            suggested_values = None
        review_context = self._command_review_context(CommandName.CONFIGURE_TRAINING)
        expected_generation = (
            review_context.publication_generation
            if review_context is not None
            else None
        )
        if self._configuration_blocked(
            "Cannot change training settings while training is running.",
            review_context=review_context,
            context_resolved=True,
        ):
            return InteractionOutcome.blocked(
                "Training settings cannot be changed while training is running."
            )

        initial_option = self._training_setting_initial_option(
            suggested_values,
            expected_publication_generation=expected_generation,
        )
        if isinstance(initial_option, InteractionOutcome):
            return initial_option
        recommendation = self._training_setting_recommendation(
            expected_publication_generation=expected_generation,
        )
        resource_preview_request = self._training_resource_preview_request(
            initial_option,
            recommendation=recommendation,
            proposed_values=suggested_values,
            expected_publication_generation=expected_generation,
        )
        selection = self._collect_training_option(
            initial_option,
            recommendation=recommendation,
            proposed_values=suggested_values,
            device_recommendation_provider=lambda device: (
                self._training_device_recommendation(
                    device,
                    expected_publication_generation=expected_generation,
                )
            ),
            resource_preview_request=resource_preview_request,
        )
        if isinstance(selection, InteractionOutcome):
            return selection
        return self._apply_training_configuration(
            self._configure_training_command(
                training_option=selection.option,
                device=selection.device,
                edited_recommendation_fields=(selection.edited_recommendation_fields),
            ),
            blocked_title="Training Settings Blocked",
            failed_title="Training Settings Failed",
            success_status="Training settings saved",
            expected_publication_generation=expected_generation,
        )

    def _training_setting_initial_option(
        self,
        suggested_values: dict[str, str] | None,
        *,
        expected_publication_generation: int | None = None,
    ) -> dict[str, Any] | InteractionOutcome:
        snapshot = (
            self._training_option_snapshot(
                expected_publication_generation=expected_publication_generation,
            )
            if expected_publication_generation is not None
            else self._training_option_snapshot()
        )
        if isinstance(snapshot, InteractionOutcome):
            return snapshot
        initial_option: dict[str, Any] = dict(snapshot)
        if suggested_values:
            initial_option.update(
                {
                    key: suggested_values[key]
                    for key in _TRAINING_SETTING_SUGGESTION_KEYS
                    if key in suggested_values
                    and isinstance(suggested_values[key], str)
                }
            )
        return initial_option

    def _collect_training_option(
        self,
        initial_option: dict[str, Any],
        *,
        recommendation: TrainingRecommendation | None = None,
        proposed_values: dict[str, str] | None = None,
        device_recommendation_provider: (
            Callable[[str], TrainingRecommendation | None] | None
        ) = None,
        resource_preview_request: TrainingResourcePreviewRequest | None = None,
    ) -> _TrainingSettingSelection | InteractionOutcome:
        win = TrainingSettingDialog(
            self,
            self.controller,
            initial_option=initial_option,
            recommendation=recommendation,
            proposed_values=proposed_values,
            device_recommendation_provider=(device_recommendation_provider),
            resource_preview_request=resource_preview_request,
            resource_preview_dispatcher=(
                self._dispatch_training_resource_preview
                if resource_preview_request is not None
                else None
            ),
        )
        if not win.exec():
            return InteractionOutcome.cancelled("Training settings were cancelled.")
        option = win.get_result()
        if option is None:
            message = "No training settings were selected."
            QMessageBox.warning(self, "Training Settings", message)
            return InteractionOutcome.failed(message)
        device_getter = getattr(win, "get_device_value", None)
        device = device_getter() if callable(device_getter) else None
        if not isinstance(device, str) or not device.strip():
            use_cpu = bool(getattr(option, "use_cpu", True))
            gpu_idx = getattr(option, "gpu_idx", None)
            device = "cpu" if use_cpu else f"cuda:{gpu_idx or 0}"

        edited_getter = getattr(win, "get_edited_recommendation_fields", None)
        raw_edited = edited_getter() if callable(edited_getter) else ()
        if isinstance(raw_edited, (str, bytes)) or not isinstance(raw_edited, Iterable):
            raw_edited = ()
        try:
            edited_fields = frozenset(
                field
                if isinstance(field, TrainingRecommendationField)
                else TrainingRecommendationField(str(field))
                for field in raw_edited
            )
        except (TypeError, ValueError):
            edited_fields = frozenset()
        receipt_getter = getattr(win, "get_applied_resource_preview_receipt", None)
        resource_preview_receipt = (
            receipt_getter() if callable(receipt_getter) else None
        )
        if not isinstance(resource_preview_receipt, TrainingResourcePreviewReceipt):
            resource_preview_receipt = None
        return _TrainingSettingSelection(
            option=option,
            device=device,
            edited_recommendation_fields=edited_fields,
            resource_preview_receipt=resource_preview_receipt,
        )

    def _training_setting_recommendation(
        self,
        *,
        expected_publication_generation: int | None,
        prospective_model_name: str | None = None,
        prospective_model_params: dict[str, Any] | None = None,
        prospective_device: str | None = None,
    ) -> TrainingRecommendation | None:
        """Query the backend starting point only at the dialog-open boundary."""
        query_port = self._panel_port("_query_port")
        if query_port is None:
            return None
        getter = getattr(query_port, "get_training_recommendation", None)
        if not callable(getter):
            return None
        try:
            query_args: dict[str, Any] = {
                "expected_publication_generation": (expected_publication_generation),
            }
            if prospective_model_name is not None:
                query_args.update(
                    prospective_model_name=prospective_model_name,
                    prospective_model_params=dict(prospective_model_params or {}),
                )
            if prospective_device is not None:
                query_args["prospective_device"] = prospective_device
            recommendation = getter(
                **query_args,
            )
        except ApplicationError as exc:
            logger.info("Training recommendation unavailable: %s", exc)
            return None
        if not isinstance(recommendation, TrainingRecommendation):
            logger.info("Training recommendation returned an invalid contract.")
            return None
        return recommendation

    def _training_device_recommendation(
        self,
        device: str,
        *,
        expected_publication_generation: int | None,
        prospective_model_name: str | None = None,
        prospective_model_params: dict[str, Any] | None = None,
    ) -> TrainingRecommendation | None:
        """Query backend-owned device-sensitive defaults for the active context."""
        return self._training_setting_recommendation(
            expected_publication_generation=expected_publication_generation,
            prospective_model_name=prospective_model_name,
            prospective_model_params=prospective_model_params,
            prospective_device=device,
        )

    def _training_resource_preview_request(
        self,
        initial_option: dict[str, Any],
        *,
        recommendation: TrainingRecommendation | None,
        proposed_values: dict[str, str] | None,
        expected_publication_generation: int | None,
        prospective_model_name: str | None = None,
        prospective_model_params: dict[str, Any] | None = None,
    ) -> TrainingResourcePreviewRequest | None:
        """Bind visible draft fields to one detached publication input shape."""
        publication = self._application_publication()
        if (
            publication is None
            or expected_publication_generation is None
            or publication.generation != expected_publication_generation
        ):
            return None
        state = publication.state
        epoch = state.epoch
        training = state.training
        if not epoch.available:
            return None

        recommended = recommendation.values if recommendation is not None else None
        batch_value: Any = (
            recommended.batch_size
            if recommended is not None
            else initial_option.get("batch_size")
        )
        optimizer_value: Any = (
            recommended.optimizer
            if recommended is not None
            else initial_option.get("optimizer") or "Adam"
        )
        device_value: Any = initial_option.get("device") or "auto"
        if proposed_values:
            batch_value = proposed_values.get("batch_size", batch_value)
            optimizer_value = proposed_values.get("optimizer", optimizer_value)
            device_value = proposed_values.get("device", device_value)
        try:
            batch_size = int(batch_value)
        except (TypeError, ValueError):
            return None
        if batch_size <= 0:
            return None

        model_name = prospective_model_name or training.model_name
        model_params = (
            dict(prospective_model_params or {})
            if prospective_model_name is not None
            else dict(training.model_params or {})
        )
        return TrainingResourcePreviewRequest(
            request_generation=0,
            publication_generation=expected_publication_generation,
            model_name=model_name,
            model_params=model_params,
            device=str(device_value),
            batch_size=batch_size,
            optimizer=str(optimizer_value),
        )

    def _dispatch_training_resource_preview(
        self,
        request: TrainingResourcePreviewRequest,
        callback: Callable[[TrainingResourcePreviewResult], object],
    ) -> bool:
        """Coalesce draft previews while one backend query is in flight."""
        query_port = self._panel_port("_query_port")
        if query_port is None or self._training_resource_preview_shutdown_requested:
            return False

        self._training_resource_preview_token += 1
        task = _TrainingResourcePreviewTask(
            request=request,
            callback=callback,
            token=self._training_resource_preview_token,
        )
        return self._start_training_resource_preview(query_port, task)

    def _start_training_resource_preview(
        self,
        query_port: Any,
        task: _TrainingResourcePreviewTask,
    ) -> bool:
        """Start one detached advisory query and retain terminal ownership."""
        if (
            self._training_resource_preview_shutdown_requested
            or task.token != self._training_resource_preview_token
        ):
            return False

        submit = getattr(query_port, "begin_training_resource_preview", None)
        if not callable(submit):
            logger.info("Training resource preview query is unavailable.")
            return False
        try:
            ticket = submit(task.request)
        except Exception as exc:
            logger.info("Training resource preview could not start: %s", exc)
            return False
        if not isinstance(ticket, TrainingResourcePreviewTicket):
            logger.info("Training resource preview returned an invalid ticket.")
            return False
        self._training_resource_preview_ticket = ticket
        self._training_resource_preview_active_task = task
        self._training_resource_preview_timer.start()
        return True

    def _poll_training_resource_preview(self) -> None:
        """Observe backend completion without introducing a second UI worker."""
        ticket = self._training_resource_preview_ticket
        task = self._training_resource_preview_active_task
        if ticket is None or task is None:
            self._training_resource_preview_timer.stop()
            return
        if not ticket.done:
            return
        self._training_resource_preview_timer.stop()
        self._training_resource_preview_ticket = None
        self._training_resource_preview_active_task = None
        try:
            result = ticket.result(timeout=0.0)
        except Exception as exc:
            self._report_training_resource_preview_error(task, exc)
            return
        self._deliver_training_resource_preview(task, result)

    def _deliver_training_resource_preview(
        self,
        task: _TrainingResourcePreviewTask,
        result: TrainingResourcePreviewResult,
    ) -> None:
        """Deliver a result only while its task is still the newest draft."""
        if (
            self._training_resource_preview_shutdown_requested
            or task.token != self._training_resource_preview_token
        ):
            return
        try:
            task.callback(result)
        except RuntimeError:
            logger.info("Training resource preview receiver is no longer available.")

    def _report_training_resource_preview_error(
        self,
        task: _TrainingResourcePreviewTask,
        error: BaseException,
    ) -> None:
        if (
            self._training_resource_preview_shutdown_requested
            or task.token != self._training_resource_preview_token
        ):
            return
        logger.info(
            "Training resource preview unavailable: %s",
            error,
        )

    def _shutdown_training_resource_previews(self, *_args: Any) -> None:
        """Fence backend previews and invalidate callback delivery during close."""
        if self._training_resource_preview_shutdown_requested:
            return
        self._training_resource_preview_shutdown_requested = True
        self._training_resource_preview_token += 1
        self._training_resource_preview_timer.stop()
        self._training_resource_preview_ticket = None
        self._training_resource_preview_active_task = None
        query_port = self._panel_port("_query_port")
        begin_shutdown = getattr(
            query_port,
            "begin_training_resource_preview_shutdown",
            None,
        )
        if callable(begin_shutdown):
            begin_shutdown()

    def _cancel_training_resource_preview_shutdown(self) -> None:
        """Reopen backend preview admission after a cancelled close attempt."""
        if not self._training_resource_preview_shutdown_requested:
            return
        query_port = self._panel_port("_query_port")
        cancel_shutdown = getattr(
            query_port,
            "cancel_training_resource_preview_shutdown",
            None,
        )
        if callable(cancel_shutdown) and cancel_shutdown():
            self._training_resource_preview_shutdown_requested = False

    @staticmethod
    def _positive_summary_count(
        summary: Any,
        key: str,
        *,
        allow_zero: bool = False,
    ) -> int | None:
        if not isinstance(summary, dict):
            return None
        value = summary.get(key)
        if value is None or isinstance(value, bool):
            return None
        try:
            parsed = int(cast(Any, value))
        except (TypeError, ValueError):
            return None
        if parsed > 0 or (allow_zero and parsed == 0):
            return parsed
        return None

    @staticmethod
    def _configure_training_command(
        *,
        model_holder: Any | None = None,
        training_option: Any | None = None,
        device: str | None = None,
        edited_recommendation_fields: frozenset[
            TrainingRecommendationField
        ] = frozenset(),
        resource_preview_receipt: TrainingResourcePreviewReceipt | None = None,
    ) -> ConfigureTrainingCommand:
        fields: dict[str, Any] = {}
        if model_holder is not None:
            stable_model_id = getattr(model_holder, "model_id", None)
            model_name = (
                stable_model_id.strip()
                if isinstance(stable_model_id, str) and stable_model_id.strip()
                else model_holder.target_model.__name__
            )
            fields.update(
                model_name=model_name,
                model_params=dict(model_holder.model_params_map),
                pretrained_weight_path=model_holder.pretrained_weight_path,
            )
        if training_option is not None:
            option = training_option
            optimizer_name = getattr(
                getattr(option, "optim", None),
                "__name__",
                "adam",
            )
            use_cpu = bool(getattr(option, "use_cpu", True))
            gpu_idx = getattr(option, "gpu_idx", None)
            fields.update(
                epoch=getattr(option, "epoch", None),
                batch_size=getattr(option, "bs", None),
                learning_rate=getattr(option, "lr", None),
                repeat=getattr(option, "repeat_num", 1),
                device=(
                    device
                    if isinstance(device, str) and device.strip()
                    else ("cpu" if use_cpu else f"cuda:{gpu_idx or 0}")
                ),
                optimizer=optimizer_name,
                optimizer_params=dict(getattr(option, "optim_params", {}) or {}),
                save_checkpoints_every=getattr(option, "checkpoint_epoch", 0),
                output_dir=getattr(
                    option,
                    "output_dir",
                    ConfigureTrainingCommand().output_dir,
                ),
                evaluation_option=getattr(
                    getattr(option, "evaluation_option", None),
                    "value",
                    None,
                ),
            )
        return attach_training_submission_provenance(
            ConfigureTrainingCommand(**fields),
            edited_recommendation_fields,
            resource_preview_receipt=resource_preview_receipt,
        )

    def _apply_training_configuration(
        self,
        command: ConfigureTrainingCommand,
        *,
        blocked_title: str,
        failed_title: str,
        success_status: str,
        expected_publication_generation: int | None = None,
    ) -> InteractionOutcome:
        command_kwargs: dict[str, Any] = {}
        if expected_publication_generation is not None:
            command_kwargs["expected_publication_generation"] = (
                expected_publication_generation
            )
        result = self._execute_action(
            command,
            **command_kwargs,
        )
        if result is None:
            QMessageBox.warning(
                self,
                blocked_title,
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return InteractionOutcome.blocked(
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )
        if is_stale_publication_result(result):
            QMessageBox.warning(
                self,
                "Review Training Configuration Again",
                result.message,
            )
            return InteractionOutcome.blocked(result.message)
        if result.failed:
            QMessageBox.critical(
                self,
                failed_title,
                result.message,
            )
            return self._interaction_failure_outcome(result)
        self._show_status(success_status)
        return InteractionOutcome.completed(success_status)

    @staticmethod
    def _interaction_failure_outcome(result) -> InteractionOutcome:
        if bool(getattr(result, "recoverable", False)):
            return InteractionOutcome.blocked(result.message)
        return InteractionOutcome.failed(result.message)

    def _training_option_snapshot(
        self,
        *,
        expected_publication_generation: int | None = None,
    ) -> dict | InteractionOutcome:
        command_kwargs: dict[str, Any] = {"refresh": False}
        if expected_publication_generation is not None:
            command_kwargs["expected_publication_generation"] = (
                expected_publication_generation
            )
        query_port = self._panel_port("_query_port")
        if self._has_typed_product_context():
            if query_port is None:
                result = None
            else:
                result = query_port.query_training_state(
                    expected_publication_generation=expected_publication_generation,
                )
        else:
            result = execute_application_command(
                self,
                QueryStateCommand(query="state"),
                **command_kwargs,
            )
        if result is None:
            QMessageBox.warning(
                self,
                "Training Settings Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return InteractionOutcome.blocked(
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )
        if is_stale_publication_result(result):
            QMessageBox.warning(
                self,
                "Review Training Configuration Again",
                result.message,
            )
            return InteractionOutcome.blocked(result.message)
        if result.failed:
            title = (
                "Training Settings Blocked"
                if result.recoverable
                else "Training Settings Failed"
            )
            QMessageBox.warning(
                self,
                title,
                result.message,
            )
            return self._interaction_failure_outcome(result)
        diagnostics = getattr(result, "diagnostics", {}) or {}
        state = diagnostics.get("state")
        training = state.get("training") if isinstance(state, dict) else {}
        option = training.get("training_option") if isinstance(training, dict) else None
        return dict(option) if isinstance(option, dict) else {}

    def start_training_ui_action(self):
        """Schedule resource validation and plan construction off the GUI thread."""
        try:
            review_context = self._command_review_context(CommandName.TRAIN)
            if review_context is None and self._has_product_publication_context():
                QMessageBox.warning(
                    self,
                    "Start Training Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            train_capability = (
                getattr(review_context, "capability", None)
                if review_context is not None
                else self._command_capability(CommandName.TRAIN)
            )
            if review_context is not None and train_capability is None:
                QMessageBox.warning(
                    self,
                    "Start Training Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            if train_capability is not None and not train_capability.enabled:
                QMessageBox.warning(
                    self,
                    "Training Not Ready",
                    blocked_reason(
                        train_capability,
                        "Training is not ready.",
                    ),
                )
                return
            if self._should_start_training(train_capability):
                self._dispatch_start_training(
                    expected_publication_generation=(
                        review_context.publication_generation
                        if review_context is not None
                        else None
                    ),
                )
        except Exception:
            present_unexpected_error(
                self,
                UnexpectedErrorContext.TRAINING_START,
                message_box=QMessageBox,
            )

    def _dispatch_start_training(
        self,
        *,
        resource_preflight_confirmed: bool = False,
        resource_preflight_token: str | None = None,
        unknown_retried: bool = False,
        expected_publication_generation: int | None = None,
    ) -> bool:
        """Dispatch one backend-owned training attempt outside the GUI thread."""
        command = TrainCommand(
            confirmed=True,
            resource_preflight_confirmed=resource_preflight_confirmed,
            resource_preflight_token=resource_preflight_token,
        )

        def _handle_result(result) -> None:
            self._handle_start_training_result(
                result,
                unknown_retried=unknown_retried,
                expected_publication_generation=(expected_publication_generation),
            )

        def _handle_error(error: tuple) -> None:
            self._show_status("Training could not start · Check settings")
            present_unexpected_error(
                self,
                UnexpectedErrorContext.TRAINING_START,
                error_info=error,
                message_box=QMessageBox,
            )

        self._show_status("Preparing data split")

        def operation_callback(operation_id: str) -> None:
            self._training_operation_presenter.bind(
                operation_id,
                stage="Preparing training",
            )

        if expected_publication_generation is None:
            started = self._execute_action_async(
                command,
                on_result=_handle_result,
                on_error=_handle_error,
                busy_target=self,
                on_operation_started=operation_callback,
            )
        else:
            started = self._execute_action_async(
                command,
                on_result=_handle_result,
                on_error=_handle_error,
                busy_target=self,
                expected_publication_generation=expected_publication_generation,
                on_operation_started=operation_callback,
            )
        if started:
            return True
        QMessageBox.warning(
            self,
            "Start Training Blocked",
            CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
        )
        return False

    def _handle_start_training_result(
        self,
        result: Any,
        *,
        unknown_retried: bool,
        expected_publication_generation: int | None = None,
    ) -> None:
        """Resolve backend resource outcomes on the GUI thread."""
        if not result.failed:
            if self._training_start_ack_is_current():
                self._show_status("Training started")
            return

        if is_stale_publication_result(result):
            self._show_status("Training start changed · Review settings again")
            QMessageBox.warning(
                self,
                "Review Training Again",
                result.message,
            )
            return

        preflight = self._resource_preflight_from_command_result(result)
        risk_level = (
            self._training_resource_risk_level(preflight)
            if preflight is not None
            else None
        )
        confirmation_required = result.error_type is ErrorType.CONFIRMATION_REQUIRED

        if confirmation_required and preflight is not None:
            if risk_level == RISK_UNKNOWN and not unknown_retried:
                self._show_status("Rechecking training resources...")
                self._dispatch_start_training(
                    unknown_retried=True,
                    expected_publication_generation=(expected_publication_generation),
                )
                return
            reply = QMessageBox.question(
                self,
                "Training Resource Check",
                self._training_resource_dialog_message(preflight)
                + "\n\nContinue starting training?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                challenge = preflight.challenge
                if challenge is None:
                    self._show_status("Training could not start · Recheck resources")
                    QMessageBox.critical(
                        self,
                        "Training Resource Check",
                        "XBrainLab could not verify this resource warning. "
                        "Run the training check again before continuing.",
                    )
                    return
                self._dispatch_start_training(
                    resource_preflight_confirmed=True,
                    resource_preflight_token=challenge.challenge_id,
                    unknown_retried=True,
                    expected_publication_generation=(expected_publication_generation),
                )
            else:
                discard = self._execute_action(
                    DiscardTrainingPreparationCommand(
                        resource_preflight_token=(
                            preflight.challenge.challenge_id
                            if preflight.challenge is not None
                            else None
                        ),
                    ),
                    **(
                        {
                            "expected_publication_generation": (
                                expected_publication_generation
                            )
                        }
                        if expected_publication_generation is not None
                        else {}
                    ),
                )
                if discard is not None and not discard.failed:
                    self._show_status("Training start cancelled")
                else:
                    self._show_status("Training cancellation could not be verified")
            return

        if risk_level == RISK_BLOCKING and preflight is not None:
            self._show_training_resource_blocking_dialog(
                self._training_resource_dialog_message(preflight),
            )
            self._show_status("Training blocked · Adjust settings")
            return

        self._show_status("Training could not start · Check settings")
        QMessageBox.critical(
            self,
            "Error",
            f"Failed to start training: {result.message}",
        )

    def _training_start_ack_is_current(self) -> bool:
        """Reject a command acknowledgement superseded by typed terminal truth."""
        publication = self._application_publication()
        if publication is None:
            return not self._has_product_publication_context()
        if not bool(getattr(publication, "usable", False)):
            return False
        training = getattr(getattr(publication, "state", None), "training", None)
        outcome = getattr(training, "terminal_outcome", None)
        return outcome is not None and not bool(getattr(outcome, "is_terminal", True))

    def _should_start_training(self, train_capability) -> bool:
        if train_capability is None:
            available, is_training = self._compatibility_controller_value(
                self.controller.is_training,
                blocked_title="Start Training Blocked",
            )
            return bool(available and not is_training)
        return train_capability.enabled

    def stop_training(self):
        """Request ApplicationService to stop the current training run."""
        if (
            self._training_operation_presenter.active_operation_id is not None
            and self._training_operation_presenter.request_cancel()
        ):
            self._show_status("Training stop requested")
            return
        stop_capability = self._command_capability(CommandName.STOP_TRAINING)
        if stop_capability is not None and not stop_capability.enabled:
            QMessageBox.warning(
                self,
                "Stop Training Blocked",
                blocked_reason(stop_capability, "No training run is active."),
            )
            return

        if stop_capability is None:
            available, is_training = self._compatibility_controller_value(
                self.controller.is_training,
                blocked_title="Stop Training Blocked",
            )
            if not available or not is_training:
                return

        result = self._execute_action(StopTrainingCommand())
        if result is None:
            QMessageBox.warning(
                self,
                "Stop Training Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return
        elif result.failed:
            QMessageBox.warning(
                self,
                "Warning",
                f"Failed to stop training: {result.message}",
            )
            return
        self._show_status("Training stop requested")

    def clear_history(self):
        """Clear all training history records.

        Blocked while training is running.
        """
        try:
            publication = self._application_publication()
            if publication is None and self._has_product_publication_context():
                QMessageBox.warning(
                    self,
                    "Clear History Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            clear_capability = (
                self._published_capability(
                    publication,
                    CommandName.CLEAR_TRAINING_HISTORY,
                )
                if publication is not None
                else self._command_capability(CommandName.CLEAR_TRAINING_HISTORY)
            )
            if clear_capability is None and self._has_product_publication_context():
                QMessageBox.warning(
                    self,
                    "Clear History Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            if clear_capability is not None and not clear_capability.enabled:
                QMessageBox.warning(
                    self,
                    "Clear History Blocked",
                    blocked_reason(
                        clear_capability,
                        "No training history is available to clear.",
                    ),
                )
                return
            if clear_capability is None:
                available, is_training = self._compatibility_controller_value(
                    self.controller.is_training,
                    blocked_title="Clear History Blocked",
                )
                if not available:
                    return
                if is_training:
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "Cannot clear history while training is running.",
                    )
                    return
            reply = QMessageBox.question(
                self,
                "Clear Training History",
                "Clear all training history records? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return
            result = self._execute_action(
                ClearTrainingHistoryCommand(confirmed=True),
                expected_publication_generation=(
                    publication.generation if publication is not None else None
                ),
            )
            if result is None:
                QMessageBox.warning(
                    self,
                    "Clear History Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif is_stale_publication_result(result):
                QMessageBox.warning(
                    self,
                    "Review Clear History Again",
                    result.message,
                )
                return
            elif result.failed:
                QMessageBox.warning(self, "Warning", result.message)
                return

            self._show_status("Training history cleared")
        except Exception:
            present_unexpected_error(
                self,
                UnexpectedErrorContext.TRAINING_HISTORY_CLEAR,
                message_box=QMessageBox,
            )

    def on_training_started(self, *, refresh_ready: bool = True):
        """Update button states when training begins."""
        self.btn_stop.setEnabled(True)
        if refresh_ready:
            self.check_ready_to_train()

    def on_training_stopped(self, *, refresh_ready: bool = True):
        """Update button states when training ends."""
        self.btn_stop.setEnabled(False)
        if refresh_ready:
            self.check_ready_to_train()
