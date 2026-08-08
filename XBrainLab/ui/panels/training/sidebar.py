"""Sidebar widget for the training panel with configuration and execution controls."""

from collections.abc import Callable
from typing import Any, cast

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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
    DatasetGenerationMode,
    ErrorType,
    GenerateDatasetCommand,
    QueryStateCommand,
    StopTrainingCommand,
    TrainCommand,
)
from XBrainLab.backend.application.resource_guard import (
    RISK_BLOCKING,
    RISK_SAFE,
    RISK_UNKNOWN,
    RISK_WARNING,
    ResourceChecker,
)
from XBrainLab.backend.application.resource_preflight import (
    ResourcePreflightContractError,
    ResourcePreflightView,
)
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    ApplicationUiRuntime,
    ControllerCompatibilityUnavailableError,
    DatasetSplitDialogBinding,
    blocked_reason,
    execute_application_command,
    execute_application_command_async,
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
from XBrainLab.ui.status import show_status_message
from XBrainLab.ui.styles.stylesheets import Stylesheets

_TRAINING_SETTING_SUGGESTION_KEYS = frozenset(
    {
        "epoch",
        "batch_size",
        "learning_rate",
        "repeat",
        "optimizer",
        "device",
    }
)
_PUBLICATION_UNSET = object()


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
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.init_ui()

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
        self.btn_start.setStyleSheet(Stylesheets.BTN_PRIMARY)
        self.btn_start.clicked.connect(self.start_training_ui_action)
        self.btn_start.setEnabled(False)
        exec_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop Training")
        self.btn_stop.setStyleSheet(Stylesheets.BTN_WARNING)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_training)
        exec_layout.addWidget(self.btn_stop)

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
            self._published_capability(publication, CommandName.GENERATE_DATASET)
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

        replacement_required = self._requires_dataset_replacement_confirmation(
            generate_capability,
        )
        if replacement_required:
            reply = QMessageBox.question(
                self,
                "Reset Training Data",
                "Applying new data splitting will clear existing datasets "
                "and training history. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return InteractionOutcome.cancelled(
                    "Data splitting was cancelled before replacing training data."
                )

        split_config = win.get_result()
        if not split_config:
            return InteractionOutcome.accepted(
                "The data splitting dialog was accepted without a saved change."
            )
        command = GenerateDatasetCommand(
            split_config=dict(split_config),
            replacement_mode=(
                DatasetGenerationMode.REPLACE_EXISTING
                if replacement_required
                else DatasetGenerationMode.CREATE
            ),
            confirmed=replacement_required,
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
            busy_target=self.panel,
            expected_publication_generation=(
                publication.generation if publication is not None else None
            ),
        ):
            return InteractionOutcome.accepted("Dataset generation was scheduled.")

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
            generate_capability = self._command_capability(CommandName.GENERATE_DATASET)
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

    def _requires_dataset_replacement_confirmation(
        self,
        generate_capability=None,
    ) -> bool:
        """Read replacement intent from capability policy, never display text."""
        if generate_capability is None:
            generate_capability = self._command_capability(CommandName.GENERATE_DATASET)
        if generate_capability is None:
            available, should_clear = self._compatibility_controller_value(
                lambda: self.controller.has_datasets() or self.controller.get_trainer(),
            )
            return bool(should_clear) if available else False
        return bool(
            generate_capability.enabled
            and getattr(generate_capability, "requires_confirmation", False)
        )

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
            success_status=f"Model selected: {command.model_name}",
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
        option = self._collect_training_option(initial_option)
        if isinstance(option, InteractionOutcome):
            return option

        return self._apply_training_configuration(
            self._configure_training_command(
                model_holder=model_holder,
                training_option=option,
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
        win = ModelSelectionDialog(
            self,
            self.controller,
            initial_model_name=suggested_model,
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
        option = self._collect_training_option(initial_option)
        if isinstance(option, InteractionOutcome):
            return option
        return self._apply_training_configuration(
            self._configure_training_command(training_option=option),
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
    ) -> Any | InteractionOutcome:
        win = TrainingSettingDialog(
            self,
            self.controller,
            initial_option=initial_option,
        )
        if not win.exec():
            return InteractionOutcome.cancelled("Training settings were cancelled.")
        option = win.get_result()
        if option is None:
            message = "No training settings were selected."
            QMessageBox.warning(self, "Training Settings", message)
            return InteractionOutcome.failed(message)
        return option

    @staticmethod
    def _configure_training_command(
        *,
        model_holder: Any | None = None,
        training_option: Any | None = None,
    ) -> ConfigureTrainingCommand:
        fields: dict[str, Any] = {}
        if model_holder is not None:
            fields.update(
                model_name=(
                    getattr(model_holder, "model_id", None)
                    or model_holder.target_model.__name__
                ),
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
                device=("cpu" if use_cpu else f"cuda:{gpu_idx or 0}"),
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
        return ConfigureTrainingCommand(**fields)

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
        return InteractionOutcome.completed(result.message)

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

        self._show_status("Checking resources and preparing training...")
        if expected_publication_generation is None:
            started = self._execute_action_async(
                command,
                on_result=_handle_result,
                on_error=_handle_error,
                busy_target=self,
            )
        else:
            started = self._execute_action_async(
                command,
                on_result=_handle_result,
                on_error=_handle_error,
                busy_target=self,
                expected_publication_generation=expected_publication_generation,
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
                self._show_status("Training start cancelled")
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
