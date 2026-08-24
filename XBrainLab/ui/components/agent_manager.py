"""Qt composition and presentation adapter for the in-app assistant."""

from dataclasses import dataclass, replace
from typing import Any, cast

from PyQt6.QtCore import (
    QObject,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QWidget,
)

from XBrainLab.backend.application import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationService,
    ApplicationViewPublication,
    get_application_service,
)
from XBrainLab.backend.application.pipeline_stage import workflow_command_label
from XBrainLab.backend.controller.chat_controller import (
    ChatController,
    ChatMessagePresentationKind,
)
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.debug.tool_debug_mode import ToolDebugMode
from XBrainLab.llm.agent.assistant_activity import (
    AssistantDecisionOwner,
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
)
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
    AssistantResponseKind,
    AssistantResponsePresentation,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import (
    AssistantTurnCorrelation,
    AssistantTurnScope,
    AssistantTurnTerminal,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffKind,
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import local_model_spec
from XBrainLab.llm.core.model_download_lifecycle import ModelDownloadLifecycle
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeSelectionFailureCode,
)
from XBrainLab.llm.tools.result_contract import (
    redact_public_text,
    safe_unexpected_failure,
)
from XBrainLab.ui.chat.panel import ChatPanel
from XBrainLab.ui.chat.presentation import (
    ChatTurnPresentation,
    present_assistant_activity,
)
from XBrainLab.ui.chat.turn_state import (
    AssistantUiTurnPhase,
    AssistantUiTurnStateMachine,
    AssistantUiTurnSubmission,
)
from XBrainLab.ui.components.agent_presentation_service import (
    AgentPresentationService,
)
from XBrainLab.ui.components.assistant_application_publication_coordinator import (
    AssistantApplicationPublicationCoordinator,
)
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycle,
    RuntimeActivationResult,
    RuntimeActivationStatus,
    RuntimeCommandAdmissionResult,
    RuntimeSetupAction,
)
from XBrainLab.ui.components.assistant_status_projection import (
    AssistantStatusProjection,
    build_assistant_status_projection,
)
from XBrainLab.ui.components.vram_checker import VRAMConflictChecker
from XBrainLab.ui.components.workflow_ui_handoff_host import WorkflowUiHandoffHost
from XBrainLab.ui.core.observer_bridge import QtObserverBridge
from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog
from XBrainLab.ui.styles.icons import Icons
from XBrainLab.ui.styles.stylesheets import Stylesheets

VIZ_TAB_3D_PLOT = 3
"""Index of the 3D Plot tab in the visualization panel."""

_CHAT_PRUNE_NOTICE = (
    "Older messages were removed from this view to keep the conversation responsive."
)


@dataclass(frozen=True, slots=True)
class AssistantTurnAdmissionResult:
    """Exact outcome of one UI-to-runtime assistant turn admission."""

    correlation: AssistantTurnCorrelation | None = None

    @property
    def accepted(self) -> bool:
        return self.correlation is not None


# Panel indices in the main window stack
PANEL_DATASET = 0
PANEL_PREPROCESS = 1
PANEL_TRAINING = 2
PANEL_EVALUATION = 3
PANEL_VISUALIZATION = 4

_ASSISTANT_CONTROLLER_UI_SIGNALS = (
    "response_presentation_ready",
    "status_update",
    "activity_changed",
    "confirmation_requested",
    "panel_navigation_requested",
    "workflow_ui_handoff_requested",
    "application_command_completed",
    "application_command_started",
    "turn_finished",
)

_DELIVERY_TERMINAL_MESSAGES = {
    "delivery_error": (
        "The assistant could not receive this request. Retry the request. "
        "If it happens again, restart the assistant from Settings."
    ),
    "delivery_rejected": (
        "The assistant did not accept this request. Retry the request. "
        "If it happens again, restart the assistant from Settings."
    ),
    "rejected_busy": (
        "The assistant did not accept this request. Retry the request. "
        "If it happens again, restart the assistant from Settings."
    ),
    "rejected_closing": (
        "The assistant did not accept this request. Retry the request. "
        "If it happens again, restart the assistant from Settings."
    ),
    "delivery_timeout": (
        "The assistant did not acknowledge this request. Retry the request. "
        "If it happens again, restart the assistant from Settings."
    ),
}

_APPLICATION_PUBLICATION_RETRY_INTERVAL_MS = 25
_APPLICATION_PUBLICATION_MAX_RETRIES = 3
_APPLICATION_PUBLICATION_RECOVERY_INTERVAL_MS = 500
_ASSISTANT_TERMINAL_RENDER_RETRY_INTERVAL_MS = 500


class AssistantDockTitleBar(QWidget):
    """Product header for the fixed-right assistant dock."""

    MINIMUM_DOCK_WIDTH = 320

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title_label: QLabel | None = None
        self.status_indicator: QWidget | None = None
        self.status_dot: QFrame | None = None
        self.status_badge: QLabel | None = None

    def set_assistant_status(self, text: str) -> None:
        """Expose runtime status without adding a competing header badge."""
        normalized = " ".join(str(text or "Local · Setup").split())
        state_text = normalized.rsplit("·", 1)[-1].strip() or "Setup"
        state = state_text.lower()
        self.setProperty("assistantState", state)
        self.setToolTip(normalized)
        self.setAccessibleDescription(f"Assistant status: {normalized}")
        if self.title_label is not None:
            self.title_label.setToolTip(normalized)
            self.title_label.setAccessibleDescription(f"Assistant status: {normalized}")

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """Do not let platform font hints widen the dock past its product floor."""
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), self.MINIMUM_DOCK_WIDTH), hint.height())

    def resizeEvent(self, event):  # noqa: N802
        """Keep essential title actions readable at narrow dock widths."""
        super().resizeEvent(event)
        QTimer.singleShot(0, self._finalize_title_layout)

    def showEvent(self, event):  # noqa: N802
        """Settle action geometry after the dock installs its title bar."""
        super().showEvent(event)
        QTimer.singleShot(0, self._finalize_title_layout)

    def _finalize_title_layout(self) -> None:
        """Reflow once after Qt applies the parent dock geometry."""
        layout = self.layout()
        if layout is None:
            return
        layout.invalidate()
        layout.activate()
        self.updateGeometry()


class AgentManager(QObject):
    """Compose assistant collaborators and adapt their signals to product UI.

    Runtime readiness, controller ownership, command dispatch, model switching,
    and shutdown belong to ``AssistantRuntimeLifecycle``. This class owns the
    dock, dialogs, navigation, presentation, and Qt signal wiring only.

    Attributes:
        main_window: Reference to the parent ``MainWindow``.
        study: The application ``Study`` instance.
        chat_panel: The ``ChatPanel`` widget, or ``None`` before init.
        chat_dock: The ``QDockWidget`` hosting the chat panel.
        chat_controller: The ``ChatController`` managing chat state.
        agent_controller: Read-only access to the lifecycle-owned controller.
        agent_initialized: Read-only lifecycle initialization state.

    """

    assistant_deactivation_finished = pyqtSignal(bool, str)

    def __init__(
        self,
        main_window,
        study,
        *,
        application_service: ApplicationService | None = None,
        runtime_lifecycle: AssistantRuntimeLifecycle | None = None,
        model_download_lifecycle: ModelDownloadLifecycle | None = None,
    ):
        """Initialize the AgentManager.

        Args:
            main_window: The parent ``MainWindow`` instance.
            study: The application ``Study`` instance providing
                controllers and shared state.

        """
        super().__init__(main_window)
        self.main_window = main_window
        self.study = study
        self.application_service = (
            application_service
            if application_service is not None
            else get_application_service(study)
        )
        self._closing = False
        self._application_publication_coordinator = (
            AssistantApplicationPublicationCoordinator(
                retry_interval_ms=_APPLICATION_PUBLICATION_RETRY_INTERVAL_MS,
                max_fast_retries=_APPLICATION_PUBLICATION_MAX_RETRIES,
                recovery_interval_ms=_APPLICATION_PUBLICATION_RECOVERY_INTERVAL_MS,
            )
        )
        self._application_publication_retry_timer = QTimer(self)
        self._application_publication_retry_timer.setSingleShot(True)
        self._application_publication_retry_timer.setInterval(
            _APPLICATION_PUBLICATION_RETRY_INTERVAL_MS
        )
        self._application_publication_retry_timer.timeout.connect(
            self._retry_latest_application_view_publication
        )
        self._application_publication_bridge = QtObserverBridge(
            self.application_service,
            APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
            self,
        )
        self._application_publication_bridge.connect_to(
            self._on_application_view_publication_changed
        )

        self.chat_panel: ChatPanel | None = None
        self.chat_dock: QDockWidget | None = None
        self.chat_controller = ChatController()
        # Connect Chat Controller Signals
        self.chat_controller.processing_state_changed.connect(
            self.on_processing_state_changed,
        )
        self._pending_prune_notice = False
        self._runtime_unavailable_notice: str | None = None
        self._assistant_status_projection: AssistantStatusProjection | None = None
        self._application_command_in_flight = False
        self._assistant_training_terminal_retry_timer = QTimer(self)
        self._assistant_training_terminal_retry_timer.setSingleShot(True)
        self._assistant_training_terminal_retry_timer.timeout.connect(
            self._flush_assistant_training_terminal
        )
        self._last_assistant_activity: AssistantTurnActivity | None = None
        self._active_turn_scope_summary = ""
        self._assistant_turn_state = AssistantUiTurnStateMachine()
        self._deferred_submission_events: list[tuple[str, object]] | None = None
        self._assistant_runtime = runtime_lifecycle or AssistantRuntimeLifecycle(
            study,
            controller_factory=self._create_assistant_controller,
            parent=self,
        )
        self._assistant_runtime.controller_created.connect(
            self._wire_assistant_controller,
        )
        self._assistant_runtime.runtime_snapshot_changed.connect(
            self._render_assistant_runtime,
        )
        self._assistant_runtime.turn_finished.connect(
            self._on_assistant_turn_finished,
        )
        deactivation_signal = getattr(
            self._assistant_runtime,
            "deactivation_finished",
            None,
        )
        connect_deactivation = getattr(deactivation_signal, "connect", None)
        if callable(connect_deactivation):
            connect_deactivation(self._on_assistant_deactivation_finished)
        self._model_download_lifecycle = (
            model_download_lifecycle or ModelDownloadLifecycle(parent=self)
        )
        self._presentation = AgentPresentationService()
        self._workflow_ui_handoff_host = WorkflowUiHandoffHost(self.main_window)
        # M3.4 VRAM Monitoring — delegated to VRAMConflictChecker
        self.vram_checker = VRAMConflictChecker(
            self.main_window,
            lambda: self._assistant_runtime.current,
        )
        self._visualization_monitor_connected = False
        self.connect_visualization_monitor()

    @property
    def agent_controller(self) -> LLMController | None:
        """Return the controller owned by ``AssistantRuntimeLifecycle``."""
        return cast(LLMController | None, self._assistant_runtime.controller)

    @property
    def assistant_runtime(self) -> AssistantRuntimeLifecycle:
        """Expose the focused runtime contract for diagnostics and integration."""
        return self._assistant_runtime

    @property
    def model_download_lifecycle(self) -> ModelDownloadLifecycle:
        """Expose app-owned model download state without transferring ownership."""
        return self._model_download_lifecycle

    @property
    def assistant_status_projection(self) -> AssistantStatusProjection | None:
        """Return the last atomically derived workflow status projection."""
        return self._assistant_status_projection

    @property
    def agent_initialized(self) -> bool:
        """Return whether the runtime owner initialized its controller."""
        return self._assistant_runtime.initialized

    def connect_visualization_monitor(self) -> None:
        """Connect visualization-tab VRAM checks when the panel has been loaded."""
        if self._visualization_monitor_connected:
            return
        visualization_panel = getattr(self.main_window, "visualization_panel", None)
        tabs = getattr(visualization_panel, "tabs", None)
        if tabs is None:
            return
        tabs.currentChanged.connect(self.vram_checker.on_viz_tab_changed)
        self._visualization_monitor_connected = True

    def init_ui(self):
        """Initialize the chat dock widget and panel UI components.

        Creates the ``ChatPanel``, wires its signals, builds the dock
        title bar with settings/new-conversation buttons, and
        adds the dock to the main window's right area.
        """
        chat_panel = ChatPanel()
        self.chat_panel = chat_panel
        self._assistant_runtime.replay_runtime_snapshot()

        # Connect UI to ChatController
        chat_panel.connect_controller(self.chat_controller)

        # Connect ChatPanel signals to self (for further dispatch)
        chat_panel.send_message.connect(self.handle_user_input)
        chat_panel.stop_generation.connect(self.stop_generation)
        chat_panel.debug_tool_requested.connect(self._handle_debug_tool_requested)
        chat_panel.open_settings_requested.connect(self.open_settings_dialog)
        chat_panel.inline_setup_requested.connect(self._handle_inline_setup)
        retry_runtime_requested = getattr(
            chat_panel,
            "retry_local_assistant_requested",
            None,
        )
        if retry_runtime_requested is not None:
            retry_runtime_requested.connect(self.retry_local_assistant)
        chat_panel.confirmation_decision_requested.connect(
            self._resolve_action_confirmation
        )

        chat_dock = QDockWidget("XBrainLab", self.main_window)
        self.chat_dock = chat_dock
        chat_dock.setWidget(chat_panel)
        # QDockWidget's native frame consumes platform-dependent horizontal
        # chrome. Keep the supported 320 px floor on the actual assistant
        # surface so Windows does not receive a narrower first layout.
        chat_panel.setMinimumWidth(320)
        chat_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        chat_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable,
        )
        # Custom title bar for the fixed-right Assistant surface.
        title_bar = AssistantDockTitleBar(chat_dock)
        self.assistant_header = title_bar
        title_bar.setStyleSheet(Stylesheets.AGENT_TITLE_BAR)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 6, 6, 6)
        title_layout.setSpacing(6)

        title_label = QLabel("XBrainLab Assistant")
        title_label.setObjectName("AssistantDockTitle")
        title_label.setStyleSheet(Stylesheets.AGENT_TITLE_LABEL)
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_label.setMinimumWidth(title_label.sizeHint().width())
        title_bar.title_label = title_label
        title_layout.addWidget(title_label)
        title_bar.set_assistant_status(chat_panel.header_status_text)
        title_layout.addStretch()
        chat_panel.header_status_changed.connect(title_bar.set_assistant_status)

        title_style = title_bar.style()
        if title_style is None:
            title_style = QApplication.style()
        if title_style is None:
            raise RuntimeError("Qt application style is unavailable.")

        # New chat clears only the assistant conversation, never workflow state.
        self.new_conv_title_btn = QPushButton("+")
        self.new_conv_title_btn.setAutoDefault(False)
        self.new_conv_title_btn.setDefault(False)
        self.new_conv_title_btn.setIconSize(QSize(16, 16))
        self.new_conv_title_btn.setFixedSize(30, 30)
        self.new_conv_title_btn.setToolTip("New chat")
        self.new_conv_title_btn.setAccessibleName("New chat")
        self.new_conv_title_btn.setAccessibleDescription(
            "Clear the assistant conversation without changing the EEG workflow."
        )
        self.new_conv_title_btn.setStyleSheet(Stylesheets.AGENT_NEW_CONV_BTN)
        self.new_conv_title_btn.clicked.connect(self.start_new_conversation)
        title_layout.addWidget(self.new_conv_title_btn)

        # Settings is a direct action; dock controls have their own buttons.
        self.settings_btn = QPushButton()
        settings_icon = QIcon(Icons.SETTINGS.path)
        if settings_icon.isNull():
            settings_icon = title_style.standardIcon(
                QStyle.StandardPixmap.SP_FileDialogDetailedView
            )
        self.settings_btn.setIcon(settings_icon)
        self.settings_btn.setIconSize(QSize(16, 16))
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setToolTip("Assistant settings")
        self.settings_btn.setAccessibleName("Assistant settings")
        self.settings_btn.setAccessibleDescription("Open Assistant settings.")
        self.settings_btn.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        self.settings_btn.clicked.connect(
            lambda _checked=False: self.open_settings_dialog()
        )
        title_layout.addWidget(self.settings_btn)

        self.close_btn = QPushButton()
        self.close_btn.setIcon(
            title_style.standardIcon(QStyle.StandardPixmap.SP_DockWidgetCloseButton)
        )
        self.close_btn.setIconSize(QSize(16, 16))
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setToolTip("Hide assistant")
        self.close_btn.setAccessibleName("Hide assistant")
        self.close_btn.setAccessibleDescription(
            "Hide the Assistant panel without ending the conversation."
        )
        self.close_btn.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        self.close_btn.clicked.connect(chat_dock.close)
        title_layout.addWidget(self.close_btn)

        chat_dock.setTitleBarWidget(title_bar)
        self.main_window.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            chat_dock,
        )

        chat_dock.visibilityChanged.connect(self.update_ai_btn_state)
        chat_dock.hide()
        self.refresh_backend_status()

    def update_ai_btn_state(self, visible):
        """Sync the AI toggle button checked state with dock visibility.

        Args:
            visible: Whether the dock is currently visible.

        """
        if hasattr(self.main_window, "ai_btn"):
            self.main_window.ai_btn.blockSignals(True)
            self.main_window.ai_btn.setChecked(visible)
            self.main_window.ai_btn.blockSignals(False)

    def toggle(self):
        """Toggle the Agent dock visibility, initializing on first open."""
        if (
            not self.agent_initialized
            and self.chat_dock
            and self.chat_dock.isVisible() is True
        ):
            self.chat_dock.close()
            return

        if not self.agent_initialized:
            if not self.chat_panel or not self.chat_dock:
                logger.warning("Agent dock requested before init_ui completed")
                if hasattr(self.main_window, "ai_btn"):
                    self.main_window.ai_btn.setChecked(False)
                return

            self.chat_dock.show()
            if hasattr(self.main_window, "ai_btn"):
                self.main_window.ai_btn.setChecked(True)

            if self._tool_debug_enabled():
                started = self._assistant_runtime.start_diagnostics()
                self.refresh_backend_status()
                if not started:
                    self._show_runtime_unavailable(
                        self._assistant_runtime.current.error
                        or "Tool diagnostics could not start."
                    )
                return

            config = self._assistant_runtime.load_config()
            if self._assistant_runtime.needs_first_run(config):
                self._show_inline_setup(config)
                return
            activation = self._assistant_runtime.activate(config)
            self.refresh_backend_status()
            if activation.available:
                self._runtime_unavailable_notice = None
            elif self._activation_is_disabled_setup(activation):
                self._show_runtime_setup_required(activation.message)
            else:
                self._show_runtime_unavailable(activation.message)
        elif self.chat_dock and self.chat_dock.isVisible():
            self.chat_dock.close()
        elif self.chat_dock:
            self.chat_dock.show()

    def _show_inline_setup(self, config: LLMConfig) -> None:
        chat_panel = self.chat_panel
        if chat_panel is None:
            return
        resolution = self._assistant_runtime.preview_launch(config)
        spec = local_model_spec(config.model_name)
        label = spec.label if spec else str(config.model_name)
        memory = (
            f"Estimated {spec.estimated_vram_gb:g} GB VRAM"
            if spec
            else "Model details unavailable"
        )
        cache_ready = resolution.failure is None
        chat_panel.show_inline_setup(f"{label}\n{memory}", cache_ready=cache_ready)

    def _handle_inline_setup(self, action: str) -> None:
        config = self._assistant_runtime.load_config()
        if action == "open_settings":
            self.open_settings_dialog()
            return
        outcome = self._assistant_runtime.apply_first_run_choice(config, "enable")
        if outcome.action is RuntimeSetupAction.CONTINUE:
            activation = self._assistant_runtime.activate(
                self._assistant_runtime.load_config(),
            )
            self.refresh_backend_status()
            if activation.available:
                self._runtime_unavailable_notice = None
            elif self._activation_is_disabled_setup(activation):
                self._show_runtime_setup_required(activation.message)
            else:
                self._show_runtime_unavailable(activation.message)

    def _show_runtime_unavailable(self, message: str) -> None:
        """Surface assistant startup blockers in the chat panel."""
        safe_message = redact_public_text(message)
        if self._runtime_unavailable_notice == safe_message:
            return

        self._runtime_unavailable_notice = safe_message
        logger.info(
            "Assistant runtime unavailable: %s",
            redact_public_text(safe_message),
        )
        if self.chat_panel and hasattr(self.chat_panel, "show_runtime_notice"):
            self.chat_panel.show_runtime_notice(
                self._presentation.runtime_unavailable_message(safe_message),
            )

    def _show_runtime_setup_required(self, message: str) -> None:
        """Keep intentional setup deferral visible without presenting a crash."""
        visible = self._presentation.runtime_setup_message(
            redact_public_text(message),
        )
        self._runtime_unavailable_notice = None
        if self.chat_panel:
            self.chat_panel.set_runtime_state(
                AssistantRuntimePhase.IDLE.value,
                visible,
            )
        self._show_global_status(visible)

    @staticmethod
    def _activation_is_disabled_setup(
        activation: RuntimeActivationResult,
    ) -> bool:
        failure = getattr(activation, "failure", None)
        return bool(
            failure is not None
            and failure.code is AssistantRuntimeSelectionFailureCode.RUNTIME_DISABLED
        )

    def open_settings_dialog(self):
        """Open settings and apply an accepted local runtime selection."""
        # Pass self to allow the dialog to request model unloading/switching
        dialog = ModelSettingsDialog(
            self.main_window,
            agent_manager=self,
            download_lifecycle=self._model_download_lifecycle,
        )
        if not dialog.exec():
            return

        activation = self._assistant_runtime.activate_persisted()
        self.refresh_backend_status()
        if not activation.available:
            if self._activation_is_disabled_setup(activation):
                self._show_runtime_setup_required(activation.message)
                return
            self._show_runtime_unavailable(activation.message)
            return

        self._runtime_unavailable_notice = None
        if (
            activation.status is RuntimeActivationStatus.ALREADY_READY
            and self.chat_panel
        ):
            self.chat_panel.set_runtime_state(AssistantRuntimePhase.READY.value)

    def request_assistant_deactivation(
        self,
        config: LLMConfig,
    ) -> RuntimeCommandAdmissionResult:
        """Delegate Disable admission to the existing runtime owner."""
        return self._assistant_runtime.request_deactivation(config)

    def _on_assistant_deactivation_finished(self, ok: bool, message: str) -> None:
        """Clear Assistant-only presentation after runtime ownership is released."""
        if ok:
            self._clear_conversation_presentation()
            self._runtime_unavailable_notice = None
            self.refresh_backend_status()
        self.assistant_deactivation_finished.emit(bool(ok), str(message or ""))

    def prepare_model_deletion(self, model_name: str) -> bool:
        """Return whether runtime ownership allows model file deletion.

        Called by ``ModelSettingsDialog`` before deleting a model. If the
        model is currently loaded in local mode, block deletion until the
        assistant is switched away from that active local backend.

        Args:
            model_name: The name of the model being deleted.

        Returns:
            ``True`` if it is safe to proceed with deletion.

        """
        if self._assistant_runtime.active_local_runtime_blocks_model_deletion():
            logger.info(
                "Blocking deletion of active local model: %s",
                redact_public_text(model_name),
            )
            return False

        return True

    def start_system(self):
        """Start the runtime owner after the assistant UI is available."""
        if not self.chat_panel:
            return
        started = (
            self._assistant_runtime.start_diagnostics()
            if self._tool_debug_enabled()
            else self._assistant_runtime.start()
        )
        if started:
            self.refresh_backend_status()

    def _tool_debug_enabled(self) -> bool:
        """Return whether this real chat panel owns a debug script session."""
        return isinstance(
            getattr(self.chat_panel, "debug_mode", None),
            ToolDebugMode,
        )

    def _create_assistant_controller(self, study: object) -> LLMController:
        """Create a controller only when its product UI contract is complete."""
        controller = LLMController(study)
        try:
            self._validate_assistant_controller_contract(controller)
        except Exception:
            close = getattr(controller, "close", None)
            if callable(close):
                close()
            raise
        return controller

    @staticmethod
    def _validate_assistant_controller_contract(controller: object) -> None:
        """Fail before wiring when a product controller lacks core signals."""
        missing = [
            signal_name
            for signal_name in _ASSISTANT_CONTROLLER_UI_SIGNALS
            if not callable(
                getattr(getattr(controller, signal_name, None), "connect", None)
            )
        ]
        if missing:
            formatted = ", ".join(missing)
            raise TypeError(
                f"Assistant controller core signal contract is incomplete: {formatted}."
            )

    def _wire_assistant_controller(self, controller) -> None:
        """Connect one newly created runtime controller to product UI slots."""
        self._validate_assistant_controller_contract(controller)
        controller.response_presentation_ready.connect(
            self._handle_response_presentation
        )
        controller.status_update.connect(self.on_agent_status_update)
        controller.activity_changed.connect(self.on_assistant_activity_changed)
        controller.confirmation_requested.connect(self._show_action_confirmation)
        controller.panel_navigation_requested.connect(self.handle_panel_navigation)
        controller.workflow_ui_handoff_requested.connect(
            self.handle_workflow_ui_handoff
        )
        controller.application_command_completed.connect(
            self._on_application_command_completed
        )
        controller.application_command_started.connect(
            self._on_application_command_started
        )

    def _on_application_command_started(self) -> None:
        """Mark one Assistant command as in flight and render its activity."""
        self._application_command_in_flight = True
        if not self.chat_controller.is_processing:
            self.chat_controller.set_processing(True)
        if self.chat_panel:
            if self._assistant_turn_state.phase is AssistantUiTurnPhase.STOPPING:
                presentation = ChatTurnPresentation.stopping()
            else:
                activity = self._last_assistant_activity
                presentation = (
                    present_assistant_activity(
                        activity,
                        application_command_in_flight=True,
                    )
                    if isinstance(activity, AssistantTurnActivity)
                    else ChatTurnPresentation.application_command()
                )
            self.chat_panel.set_turn_activity(self._with_active_scope(presentation))

    def _on_application_command_completed(self, result) -> None:
        """Release command ownership and track asynchronous training completion."""
        self._application_command_in_flight = False
        self._begin_assistant_training_watch(result)

    def _begin_assistant_training_watch(self, result: object) -> None:
        """Track only an asynchronous training run started by this Assistant."""
        correlation = self._assistant_turn_state.lease
        if not isinstance(correlation, AssistantTurnCorrelation):
            return
        if not self._application_publication_coordinator.begin_training_watch(
            result,
            correlation,
        ):
            return
        self._reconcile_assistant_training_terminal()

    def _reconcile_assistant_training_terminal(self) -> None:
        """Replay committed truth when a fast run finished before result delivery."""
        try:
            publication = self.application_service.get_view_publication()
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="agent_manager",
                operation="reconcile_assistant_training_terminal",
            )
            return
        if isinstance(publication, ApplicationViewPublication):
            self._observe_assistant_training_publication(publication)

    def handle_user_input(self, text: str) -> AssistantTurnAdmissionResult:
        """Handle text input from ChatPanel.

        Adds the message to ``ChatController`` history and forwards it
        to the ``LLMController`` for processing.

        Args:
            text: The user's message text.

        """
        text = text.strip()
        if not text:
            return AssistantTurnAdmissionResult()
        if self.agent_controller is None:
            activation = self._assistant_runtime.activate_persisted()
            if activation.available:
                self._reject_user_submission(
                    text,
                    "Wait for the local assistant to finish loading.",
                )
            else:
                self._show_runtime_unavailable(activation.message)
                self._reject_user_submission(text, activation.message)
            return AssistantTurnAdmissionResult()

        # Reserve the runtime turn before changing the transcript. A rejected
        # command must not leave an unanswered user bubble behind.
        submission = self._begin_assistant_turn_submission()
        self._deferred_submission_events = []
        admission = self._assistant_runtime.submit(
            text,
            generation=submission.generation,
        )
        if not isinstance(admission, RuntimeCommandAdmissionResult):
            self._finish_assistant_turn_submission(submission, accepted=False)
            self._deferred_submission_events = None
            logger.error("Assistant runtime returned an invalid admission result")
            self._reject_user_submission(
                text,
                "The assistant could not accept this request. Try again.",
            )
            return AssistantTurnAdmissionResult()
        if not admission.accepted:
            self._finish_assistant_turn_submission(submission, accepted=False)
            self._deferred_submission_events = None
            self._reject_user_submission(text, admission.message)
            return AssistantTurnAdmissionResult()

        correlation = admission.correlation
        if correlation is None:
            self._finish_assistant_turn_submission(submission, accepted=False)
            self._deferred_submission_events = None
            logger.error("Assistant admission is missing exact turn correlation")
            self._reject_user_submission(
                text,
                "The assistant could not correlate this request. Try again.",
            )
            return AssistantTurnAdmissionResult()

        deferred_events = self._deferred_submission_events
        self._deferred_submission_events = None
        if not self._finish_assistant_turn_submission(
            submission,
            accepted=True,
            correlation=correlation,
        ):
            self._reject_user_submission(
                text,
                "The assistant could not correlate this request. Try again.",
            )
            return AssistantTurnAdmissionResult()
        self._prepare_admitted_transcript_turn()
        self._active_turn_scope_summary = self._scope_summary_for_admission(admission)
        self.chat_controller.add_user_message(text)
        if self.chat_panel is not None and hasattr(
            self.chat_panel, "accept_composer_submission"
        ):
            self.chat_panel.accept_composer_submission(text)
        self._replay_deferred_submission_events(deferred_events)
        return AssistantTurnAdmissionResult(correlation=correlation)

    @staticmethod
    def _scope_summary_for_admission(
        admission: RuntimeCommandAdmissionResult,
    ) -> str:
        """Describe host-enforced autonomy without exposing an internal mode."""
        if admission.scope is AssistantTurnScope.GUIDED_WORKFLOW:
            if admission.terminal_command:
                label = workflow_command_label(admission.terminal_command)
                summary = f"Scope: Continue through {label}; stop for decisions."
            else:
                summary = (
                    "Scope: Continue one verified step at a time; stop for decisions."
                )
        else:
            summary = "Scope: Only this request."
        if admission.excluded_commands:
            exclusions = ", ".join(
                workflow_command_label(command).rstrip(".")
                for command in admission.excluded_commands
            )
            summary = f"{summary} Excluded: {exclusions}."
        return summary

    def _with_active_scope(
        self,
        presentation: ChatTurnPresentation,
    ) -> ChatTurnPresentation:
        """Attach the admitted host scope to one active progress projection."""
        if not self._active_turn_scope_summary or not presentation.is_visible:
            return presentation
        return replace(
            presentation,
            scope_summary=self._active_turn_scope_summary,
        )

    def _handle_debug_tool_requested(
        self,
        tool_name: str,
        params: dict[str, Any],
        confirmed: bool = False,
        authorization_text: str = "",
    ) -> None:
        """Admit one debug-script action through the normal correlated turn lease."""
        if self.agent_controller is None:
            if self.chat_panel:
                self.chat_panel.reject_debug_step(
                    "The assistant runtime must be ready before running diagnostics."
                )
            self._show_low_priority_notice(
                "The assistant runtime must be ready before running diagnostics."
            )
            return
        submission = self._begin_assistant_turn_submission()
        self._deferred_submission_events = []
        debug_options: dict[str, Any] = {"generation": submission.generation}
        if confirmed:
            debug_options["confirmed"] = True
        if authorization_text:
            debug_options["authorization_text"] = authorization_text
        admission = self._assistant_runtime.debug(
            tool_name,
            dict(params),
            **debug_options,
        )
        if not isinstance(admission, RuntimeCommandAdmissionResult):
            self._finish_assistant_turn_submission(submission, accepted=False)
            self._deferred_submission_events = None
            logger.error("Assistant debug runtime returned an invalid admission result")
            self._show_low_priority_notice(
                "The diagnostic action could not be started. Try again."
            )
            if self.chat_panel:
                self.chat_panel.reject_debug_step(
                    "The diagnostic action could not be started. Try again."
                )
            return
        if not admission.accepted:
            self._finish_assistant_turn_submission(submission, accepted=False)
            self._deferred_submission_events = None
            self._show_low_priority_notice(admission.message)
            if self.chat_panel:
                self.chat_panel.reject_debug_step(admission.message)
            return
        correlation = admission.correlation
        deferred_events = self._deferred_submission_events
        self._deferred_submission_events = None
        if not self._finish_assistant_turn_submission(
            submission,
            accepted=True,
            correlation=correlation,
        ):
            self._show_low_priority_notice(
                "The diagnostic action could not be correlated. Try again."
            )
            if self.chat_panel:
                self.chat_panel.reject_debug_step(
                    "The diagnostic action could not be correlated. Try again."
                )
            return
        self._prepare_admitted_transcript_turn()
        self._replay_deferred_submission_events(deferred_events)

    def _prepare_admitted_transcript_turn(self) -> None:
        """Establish one bounded transcript budget after runtime admission."""
        pruned_rows = self.chat_controller.prepare_for_turn()
        self._pending_prune_notice = bool(pruned_rows)
        if pruned_rows:
            self._show_low_priority_notice(_CHAT_PRUNE_NOTICE)

    def _replay_deferred_submission_events(
        self,
        events: list[tuple[str, object]] | None,
    ) -> None:
        """Replay controller events emitted before UI admission was committed."""
        for event_kind, event_payload in events or ():
            if event_kind == "activity":
                self.on_assistant_activity_changed(event_payload)
            elif event_kind == "response":
                self._handle_response_presentation(event_payload)
            elif event_kind == "terminal":
                self._on_assistant_turn_finished(event_payload)
            elif event_kind == "confirmation":
                self._show_action_confirmation(event_payload)
            elif event_kind == "workflow_handoff":
                self.handle_workflow_ui_handoff(event_payload)

    def _begin_assistant_turn_submission(self) -> AssistantUiTurnSubmission:
        """Create one UI generation before asking the runtime for admission."""
        return self._assistant_turn_state.begin_submission()

    def _finish_assistant_turn_submission(
        self,
        submission: AssistantUiTurnSubmission,
        *,
        accepted: bool,
        correlation: AssistantTurnCorrelation | None = None,
    ) -> bool:
        """Commit or discard exactly the UI generation submitted to the runtime."""
        if not accepted:
            return self._assistant_turn_state.reject_admission(submission)
        if correlation is None:
            self._assistant_turn_state.reject_admission(submission)
            logger.error("Assistant admission omitted its turn correlation")
            return False
        accepted_admission = self._assistant_turn_state.accept_admission(
            submission,
            correlation,
        )
        if not accepted_admission:
            logger.error("Assistant admission did not match its UI submission")
        return accepted_admission

    def _render_visible_assistant_response(
        self,
        presentation: AssistantResponsePresentation,
    ) -> None:
        """Persist one response after mapping only its typed source state."""
        if (
            not self._pending_prune_notice
            and self.chat_panel
            and hasattr(self.chat_panel, "show_notice")
        ):
            self.chat_panel.show_notice("")
        kind = self._chat_presentation_kind(presentation)
        visible_text = self._presentation.assistant_transcript_message(
            presentation.text
        )
        self.chat_controller.add_agent_message(
            visible_text,
            presentation_kind=kind,
        )
        if self._pending_prune_notice:
            self._show_low_priority_notice(_CHAT_PRUNE_NOTICE)

    def _chat_presentation_kind(
        self,
        presentation: AssistantResponsePresentation,
    ) -> ChatMessagePresentationKind:
        """Map only the response's authoritative typed display meaning."""
        if presentation.kind is AssistantResponseKind.TOOL_RESULT:
            return ChatMessagePresentationKind.TOOL_RESULT
        if presentation.kind is AssistantResponseKind.CLARIFICATION:
            return ChatMessagePresentationKind.CLARIFICATION
        if presentation.kind is AssistantResponseKind.ERROR:
            return ChatMessagePresentationKind.ERROR
        if presentation.kind is AssistantResponseKind.BLOCKED:
            return ChatMessagePresentationKind.ATTENTION
        if presentation.kind is AssistantResponseKind.CANCELLED:
            return ChatMessagePresentationKind.CANCELLED
        return ChatMessagePresentationKind.ASSISTANT

    def _handle_response_presentation(self, payload: object) -> None:
        """Render one typed response for its correlated turn."""
        if not isinstance(payload, AssistantResponsePresentation):
            logger.error(
                "Ignored invalid assistant response presentation: %s",
                redact_public_text(payload),
            )
            return
        if self._defer_provisional_turn_event(
            "response",
            payload,
            payload.correlation,
        ):
            return
        terminal_cancellation = payload.kind is AssistantResponseKind.CANCELLED
        if not self._assistant_turn_state.accepts_response(
            payload.correlation,
            terminal_cancellation=terminal_cancellation,
        ):
            logger.warning(
                "Ignored stale assistant response presentation for %s",
                redact_public_text(payload.correlation),
            )
            return
        self._try_render_visible_assistant_response(payload)

    def _try_render_visible_assistant_response(
        self,
        presentation: AssistantResponsePresentation,
        *,
        recover_capacity: bool = False,
    ) -> bool:
        """Render one bounded response without leaking contract errors into Qt."""
        try:
            self._render_visible_assistant_response(presentation)
        except ValueError as exc:
            if not recover_capacity:
                logger.error(
                    "Ignored assistant response outside the chat presentation "
                    "contract: %s",
                    redact_public_text(exc),
                )
                return False
            self._prepare_admitted_transcript_turn()
            try:
                self._render_visible_assistant_response(presentation)
            except (TypeError, ValueError) as retry_exc:
                logger.error(
                    "Ignored assistant response outside the chat presentation "
                    "contract after capacity recovery: %s",
                    redact_public_text(retry_exc),
                )
                return False
            return True
        except TypeError as exc:
            logger.error(
                "Ignored assistant response outside the chat presentation contract: %s",
                redact_public_text(exc),
            )
            return False
        return True

    def _open_assistant_panel_target(
        self,
        target: AssistantPanelTarget,
        *,
        view_mode: str = "",
        on_terminal: Any | None = None,
    ) -> int:
        """Open one typed existing main-window panel without mutating workflow."""
        panel_index = {
            AssistantPanelTarget.DATASET: PANEL_DATASET,
            AssistantPanelTarget.PREPROCESS: PANEL_PREPROCESS,
            AssistantPanelTarget.TRAINING: PANEL_TRAINING,
            AssistantPanelTarget.EVALUATION: PANEL_EVALUATION,
            AssistantPanelTarget.VISUALIZATION: PANEL_VISUALIZATION,
        }[target]
        status_bar = self.main_window.statusBar()

        ready_callback_delivered = False

        def _on_ready(_panel: object) -> None:
            nonlocal ready_callback_delivered
            ready_callback_delivered = True
            if view_mode:
                self._switch_sub_view(panel_index, view_mode)
            if status_bar:
                status_bar.showMessage(f"Opened {target.value.title()} panel.")
            if on_terminal is not None:
                on_terminal(True)

        def _on_failed(_failure: object) -> None:
            if status_bar:
                status_bar.showMessage(f"Could not open {target.value.title()} panel.")
            if on_terminal is not None:
                on_terminal(False)

        if on_terminal is not None:
            materialized = self.main_window.switch_page(
                panel_index,
                on_ready=_on_ready,
                on_failed=_on_failed,
            )
        elif view_mode:
            materialized = self.main_window.switch_page(
                panel_index,
                on_ready=_on_ready,
            )
        else:
            materialized = self.main_window.switch_page(panel_index)
            if materialized is not False and status_bar:
                status_bar.showMessage(f"Opened {target.value.title()} panel.")
        if (
            materialized is not False
            and not ready_callback_delivered
            and (view_mode or on_terminal is not None)
        ):
            _on_ready(None)

        if materialized is False and status_bar:
            status_bar.showMessage(f"Opening {target.value.title()}...")
        return panel_index

    def retry_local_assistant(self) -> None:
        """Retry the persisted local runtime after a visible startup failure."""
        if self._assistant_runtime.current.phase is AssistantRuntimePhase.LOADING:
            return
        activation = self._assistant_runtime.activate_persisted()
        self.refresh_backend_status()
        if not activation.available:
            if self._activation_is_disabled_setup(activation):
                self._show_runtime_setup_required(activation.message)
                return
            self._runtime_unavailable_notice = None
            self._show_runtime_unavailable(activation.message)
            return
        self._runtime_unavailable_notice = None

    def stop_generation(self):
        """Stop the currently running LLM generation."""
        if self.agent_controller:
            if self._assistant_turn_state.phase is AssistantUiTurnPhase.STOPPING:
                return
            if self._application_command_in_flight:
                self._show_low_priority_notice(
                    "This action has already started and cannot be stopped safely. "
                    "Wait for it to finish."
                )
                return
            active_before_stop = self._assistant_turn_state.lease
            result = self._assistant_runtime.stop_generation()
            accepted = self._surface_runtime_command_result(
                result,
                fallback="The assistant could not stop the current request.",
            )
            if accepted:
                correlation = result.correlation
                if correlation is None or correlation != active_before_stop:
                    logger.error("Assistant Stop admission had no matching turn lease")
                    self._show_low_priority_notice(
                        "The assistant could not correlate the Stop request."
                    )
                    return
                if self._assistant_turn_state.lease is None:
                    return
                if (
                    self._assistant_turn_state.phase
                    is not AssistantUiTurnPhase.STOPPING
                    and not self._assistant_turn_state.latch_stop(correlation)
                ):
                    logger.error("Assistant Stop could not latch its active turn lease")
                    return
                self._workflow_ui_handoff_host.abandon_active()
                if self.chat_panel:
                    self.chat_panel.set_turn_activity(
                        self._with_active_scope(ChatTurnPresentation.stopping())
                    )

    def set_model(self, model_name):
        """Switch the active LLM model and check for VRAM conflicts.

        Args:
            model_name: Runtime mode key or backend-specific identifier.

        """
        activation = self._assistant_runtime.switch_model(model_name)
        if not activation.available:
            self._show_low_priority_notice(activation.message)
            return
        target = activation.model_id
        if activation.fallback_used:
            self._show_low_priority_notice(activation.message)

        # VRAM Check on Mode Switch
        if target in set(LLMConfig.allowed_local_model_ids()):
            self.vram_checker.check(switching_to_local=True)
        self.refresh_backend_status()

    def on_viz_tab_changed(self, index):
        """Monitor visualization tab changes for VRAM conflict.

        Args:
            index: The newly selected tab index.

        """
        self.vram_checker.on_viz_tab_changed(index)

    def check_vram_conflict(self, switching_to_local=False, switching_to_3d=False):
        """Check for VRAM conflict between local LLM and 3D visualization.

        Delegates to :class:`VRAMConflictChecker`.

        Args:
            switching_to_local: Whether the user is switching to local
                model mode.
            switching_to_3d: Whether the user is switching to the 3D
                visualization tab.

        """
        self.vram_checker.check(
            switching_to_local=switching_to_local,
            switching_to_3d=switching_to_3d,
        )

    def on_processing_state_changed(self, is_processing):
        """Forward processing state changes to the ChatPanel.

        Args:
            is_processing: Whether the agent is currently generating.

        """
        if self.chat_panel:
            self.chat_panel.set_processing_state(is_processing)

    def start_new_conversation(self):
        """Start a new chat without mutating the application workflow state."""
        logger.info("Starting new chat - clearing assistant conversation state")

        # Reset the runtime first so a busy turn cannot orphan visible output.
        if self.agent_controller and not self._surface_runtime_command_result(
            self._assistant_runtime.reset_conversation(),
            fallback="The assistant conversation could not be reset.",
        ):
            return

        # Clear the transcript only after the runtime accepts the boundary.
        self._clear_conversation_presentation()

        # Keep a runtime blocker actionable after the transcript is cleared.
        runtime = self._assistant_runtime.current
        if runtime.phase is AssistantRuntimePhase.FAILED:
            self._runtime_unavailable_notice = None
            self._show_runtime_unavailable(runtime.error)

        self.refresh_backend_status()

    def _clear_conversation_presentation(self) -> None:
        """Clear Assistant transcript/UI state without changing EEG workflow."""
        self.chat_controller.clear_conversation()
        self._pending_prune_notice = False
        self._application_publication_coordinator.clear_training()
        if self.chat_panel:
            self.chat_panel.clear_confirmation_request()
        if not self._assistant_turn_state.reset_idle():
            logger.error(
                "Runtime reset accepted while an assistant turn still owned UI"
            )
        if self.chat_panel and hasattr(self.chat_panel, "show_notice"):
            self.chat_panel.show_notice("")

        if self.agent_controller:
            logger.info("Assistant conversation state reset successfully")

    # Signal to notify Main Window (or other listeners) about status updates
    status_message_received = pyqtSignal(str)

    def _show_low_priority_notice(self, message: str) -> None:
        """Surface an assistant-owned notice without duplicating global status."""
        safe_message = redact_public_text(message)
        if self.chat_panel and hasattr(self.chat_panel, "show_notice"):
            self.chat_panel.show_notice(safe_message)

    def _reject_user_submission(self, text: str, message: str) -> None:
        """Keep a runtime-rejected request editable at the product boundary."""
        safe_message = redact_public_text(message)
        if self.chat_panel and hasattr(self.chat_panel, "reject_composer_submission"):
            self.chat_panel.reject_composer_submission(text, safe_message)
            return
        self._show_low_priority_notice(safe_message)

    def _surface_runtime_command_result(
        self,
        result: object,
        *,
        fallback: str,
    ) -> bool:
        """Surface a typed runtime transport rejection instead of dropping it."""
        if not isinstance(result, RuntimeCommandAdmissionResult):
            logger.error(
                "Assistant runtime returned an invalid command result: %s",
                redact_public_text(result),
            )
            self._show_low_priority_notice(fallback)
            return False
        if result.accepted:
            return True
        self._show_low_priority_notice(result.message or fallback)
        return False

    def _show_global_status(self, message: str) -> None:
        """Publish a host-level status when the assistant surface is not visible."""
        safe_message = redact_public_text(message)
        try:
            self.status_message_received.emit(safe_message)
        except RuntimeError:
            logger.debug(
                "Status notice could not be emitted: %s",
                redact_public_text(safe_message),
            )

    def on_agent_status_update(self, msg):
        """Forward agent status messages and handle error states.

        Args:
            msg: The status message string from the agent.

        """
        diagnostic = self._presentation.raw_status_diagnostic(redact_public_text(msg))
        logger.debug(
            "Assistant status update: %s",
            redact_public_text(diagnostic),
        )

    def on_assistant_activity_changed(self, payload: object) -> None:
        """Render one typed turn-local activity without inferring workflow state."""
        if not isinstance(payload, AssistantTurnActivity):
            logger.error(
                "Ignored untyped assistant activity: %s",
                redact_public_text(payload),
            )
            return
        if self._defer_provisional_turn_event(
            "activity",
            payload,
            payload.correlation,
        ):
            return
        if not self._accept_assistant_activity(payload):
            return
        if payload.phase is AssistantTurnActivityPhase.STOPPING:
            correlation = payload.correlation
            if correlation is not None:
                self._assistant_turn_state.latch_stop(correlation)
        self._last_assistant_activity = payload
        presentation = self._with_active_scope(
            present_assistant_activity(
                payload,
                application_command_in_flight=self._application_command_in_flight,
            )
        )
        processing = presentation.is_busy
        if self.chat_controller.is_processing != processing:
            self.chat_controller.set_processing(processing)
        if self.chat_panel:
            if (
                processing
                and not self._pending_prune_notice
                and hasattr(self.chat_panel, "show_notice")
            ):
                self.chat_panel.show_notice("")
            self.chat_panel.set_turn_activity(presentation)
        if not processing:
            self.refresh_backend_status()

    def _accept_assistant_activity(self, payload: AssistantTurnActivity) -> bool:
        """Accept activity only for the exact admitted UI/runtime lease."""
        return self._assistant_turn_state.accepts_activity(
            payload.correlation,
            payload.phase,
        )

    def _on_assistant_turn_finished(self, payload: object) -> None:
        """Release only the Stop/turn lease named by a typed terminal event."""
        if not isinstance(payload, AssistantTurnTerminal):
            logger.error(
                "Ignored untyped assistant turn terminal: %s",
                redact_public_text(payload),
            )
            return
        if self._defer_provisional_turn_event(
            "terminal",
            payload,
            payload.correlation,
        ):
            return
        if not self._assistant_turn_state.accept_terminal(payload):
            logger.warning(
                "Ignored stale assistant UI terminal for %s",
                redact_public_text(payload.correlation),
            )
            return
        self._render_delivery_terminal_error(payload)
        if self.chat_panel:
            self.chat_panel.complete_debug_step(payload.outcome)
        self._pending_prune_notice = False
        if self.chat_panel:
            self.chat_panel.clear_confirmation_request()
        self._last_assistant_activity = None
        self._active_turn_scope_summary = ""
        if self.chat_controller.is_processing:
            self.chat_controller.set_processing(False)
        elif self.chat_panel:
            self.chat_panel.set_turn_activity(ChatTurnPresentation.idle())
        if self.chat_panel:
            self.chat_panel.restore_composer_focus_after_turn()
        self._flush_assistant_training_terminal()
        self.refresh_backend_status()

    def _render_delivery_terminal_error(
        self,
        terminal: AssistantTurnTerminal,
    ) -> None:
        """Persist one actionable error for a failed host-to-controller delivery."""
        message = _DELIVERY_TERMINAL_MESSAGES.get(terminal.outcome)
        if message is None:
            return
        self._try_render_visible_assistant_response(
            AssistantResponsePresentation(
                text=message,
                correlation=terminal.correlation,
                kind=AssistantResponseKind.ERROR,
            )
        )

    def _defer_provisional_turn_event(
        self,
        event_kind: str,
        payload: object,
        correlation: AssistantTurnCorrelation | None,
    ) -> bool:
        """Preserve exact synchronous events until runtime admission commits."""
        events = self._deferred_submission_events
        submission = self._assistant_turn_state.submission
        if (
            events is None
            or submission is None
            or correlation is None
            or correlation.generation != submission.generation
        ):
            return False
        events.append((event_kind, payload))
        return True

    def _defer_provisional_controller_event(
        self,
        event_kind: str,
        payload: object,
    ) -> bool:
        """Hold synchronous decision events until their turn lease is admitted."""
        events = self._deferred_submission_events
        submission = self._assistant_turn_state.submission
        if events is None or submission is None:
            return False
        events.append((event_kind, payload))
        return True

    def _render_assistant_runtime(
        self,
        snapshot: AssistantRuntimeSnapshot,
    ) -> None:
        if snapshot.phase in {
            AssistantRuntimePhase.LOADING,
            AssistantRuntimePhase.READY,
        }:
            if self.chat_panel and hasattr(self.chat_panel, "clear_runtime_notice"):
                self.chat_panel.clear_runtime_notice()
            self._runtime_unavailable_notice = None
        if self.chat_panel:
            safe_error = (
                self._presentation.runtime_status_message(snapshot.error)
                if snapshot.phase is AssistantRuntimePhase.FAILED
                else ""
            )
            runtime_kwargs = (
                {"execution_device": snapshot.execution_device}
                if snapshot.execution_device
                else {}
            )
            self.chat_panel.set_runtime_state(
                snapshot.phase.value,
                safe_error,
                **runtime_kwargs,
            )
            projection = self._assistant_status_projection
            if projection is not None:
                self._render_assistant_status_projection(
                    projection,
                    runtime_snapshot=snapshot,
                )

    def refresh_backend_status(self):
        """Refresh the compact backend/model status shown in the chat panel."""
        if not self.chat_panel or not hasattr(self.chat_panel, "set_status_summary"):
            return

        try:
            publication = self.application_service.get_view_publication()
            self._render_backend_publication(publication)
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="agent_manager",
                operation="refresh_backend_status",
            )
            self._assistant_status_projection = None
            self.chat_panel.set_status_summary(
                "Workflow status unavailable",
                self._presentation.status_refresh_error(),
            )
            self.status_message_received.emit(
                "Workflow status unavailable · Try again",
            )

    def _on_application_view_publication_changed(
        self,
        publication: object,
    ) -> bool:
        """Render only current committed backend truth delivered across Qt."""
        if not isinstance(publication, ApplicationViewPublication):
            logger.error("Ignored malformed application publication event")
            return False
        return self._render_backend_publication(
            cast(ApplicationViewPublication, publication),
        )

    def _render_backend_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> bool:
        """Render one newer publication; pulls and pushes share this revision gate."""
        if self._closing:
            return False
        if not self.chat_panel or not hasattr(self.chat_panel, "set_status_summary"):
            self._schedule_application_view_publication_retry(publication)
            return False
        current = self._assistant_status_projection
        if current is not None and publication.revision <= current.publication_revision:
            return True
        try:
            projection = build_assistant_status_projection(publication)
            rendered = self._render_assistant_status_projection(projection)
        except Exception:
            self._schedule_application_view_publication_retry(publication)
            raise
        if rendered is not True:
            self._schedule_application_view_publication_retry(publication)
            return False
        self._assistant_status_projection = projection
        self._observe_assistant_training_publication(publication)
        self._complete_application_view_publication_retry(publication.revision)
        return True

    def _observe_assistant_training_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        """Translate one verified Assistant-started run into one terminal notice."""
        coordinator = self._application_publication_coordinator
        watch = coordinator.snapshot().training_watch
        outcome = publication.state.training.terminal_outcome
        if (
            watch is not None
            and outcome.is_terminal
            and (watch.run is None or outcome.run != watch.run)
        ):
            logger.warning(
                "Ignored Assistant training terminal without the current run identity"
            )
            return
        notice = coordinator.observe_training_publication(publication)
        if notice is None:
            return
        self._flush_assistant_training_terminal()

    def _flush_assistant_training_terminal(self) -> bool:
        """Append a terminal result only after its initiating turn is idle."""
        notice = self._application_publication_coordinator.terminal_notice_if_idle(
            is_idle=self._assistant_turn_state.phase is AssistantUiTurnPhase.IDLE,
        )
        if notice is None:
            return False
        copy = {
            TrainingOutcomeState.COMPLETED: (
                "Training completed. Results are ready in Evaluation.",
                AssistantResponseKind.TOOL_RESULT,
            ),
            TrainingOutcomeState.FAILED: (
                "Training failed. Review the Training panel, adjust the "
                "configuration, and try again.",
                AssistantResponseKind.ERROR,
            ),
            TrainingOutcomeState.CANCELLED: (
                "Training was cancelled.",
                AssistantResponseKind.CANCELLED,
            ),
        }.get(notice.outcome)
        if copy is None:
            self._application_publication_coordinator.complete_terminal_notice(notice)
            self._assistant_training_terminal_retry_timer.stop()
            return False
        message, presentation_kind = copy
        rendered = self._try_render_visible_assistant_response(
            AssistantResponsePresentation(
                text=message,
                correlation=notice.correlation,
                kind=presentation_kind,
            ),
            recover_capacity=True,
        )
        if rendered:
            self._application_publication_coordinator.complete_terminal_notice(notice)
            self._assistant_training_terminal_retry_timer.stop()
            return True
        if not self._closing:
            self._assistant_training_terminal_retry_timer.start(
                _ASSISTANT_TERMINAL_RENDER_RETRY_INTERVAL_MS
            )
        return False

    def _schedule_application_view_publication_retry(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        """Coalesce failed renders into fast retries plus low-frequency recovery."""
        if self._closing:
            return
        schedule = self._application_publication_coordinator.schedule_publication_retry(
            publication
        )
        if schedule is None:
            return
        if schedule.pending_changed:
            self._application_publication_retry_timer.stop()
        if self._application_publication_retry_timer.isActive():
            return
        self._application_publication_retry_timer.start(schedule.interval_ms)

    def _retry_latest_application_view_publication(self) -> None:
        """Retry the latest revision without abandoning its delivery obligation."""
        if self._closing:
            return
        publication = (
            self._application_publication_coordinator.begin_publication_retry()
        )
        if publication is None:
            return
        try:
            self._render_backend_publication(publication)
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="agent_manager",
                operation="retry_view_publication_render",
            )

    def _complete_application_view_publication_retry(self, revision: int) -> None:
        """Clear retry state only after this or a newer revision rendered."""
        if self._application_publication_coordinator.complete_publication(revision):
            self._application_publication_retry_timer.stop()

    def _render_assistant_status_projection(
        self,
        projection: AssistantStatusProjection,
        *,
        runtime_snapshot: AssistantRuntimeSnapshot | None = None,
    ) -> bool:
        """Render workflow truth with the latest local-runtime phase."""
        if not self.chat_panel or not hasattr(self.chat_panel, "set_status_summary"):
            return False
        runtime = runtime_snapshot or self._assistant_runtime.current
        model_status = (
            "Unknown"
            if not projection.usable
            else {
                AssistantRuntimePhase.READY: "Ready",
                AssistantRuntimePhase.LOADING: "Loading",
                AssistantRuntimePhase.IDLE: "Setup needed",
                AssistantRuntimePhase.FAILED: "Setup needed",
            }[runtime.phase]
        )

        if hasattr(self.chat_panel, "set_product_status"):
            self.chat_panel.set_product_status(
                stage=projection.stage,
                model_status=model_status,
                available_commands=list(projection.available_commands),
                tooltip=projection.tooltip,
                blocked_reason=projection.blocked_reason,
            )
        else:
            self.chat_panel.set_status_summary(
                projection.stage,
                projection.tooltip,
            )
        self.status_message_received.emit(projection.footer_hint)
        return True

    def close(self) -> bool:
        """Clean up the agent controller resources."""
        self._closing = True
        publication_coordinator = getattr(
            self,
            "_application_publication_coordinator",
            None,
        )
        if publication_coordinator is not None:
            publication_coordinator.clear()
        assistant_terminal_retry_timer = getattr(
            self,
            "_assistant_training_terminal_retry_timer",
            None,
        )
        if assistant_terminal_retry_timer is not None:
            assistant_terminal_retry_timer.stop()
        publication_retry_timer = getattr(
            self,
            "_application_publication_retry_timer",
            None,
        )
        if publication_retry_timer is not None:
            publication_retry_timer.stop()
        publication_bridge = getattr(
            self,
            "_application_publication_bridge",
            None,
        )
        if publication_bridge is not None:
            publication_bridge.cleanup()
        chat_panel = getattr(self, "chat_panel", None)
        if chat_panel:
            chat_panel.clear_confirmation_request()
        self._workflow_ui_handoff_host.abandon_active()
        downloads_idle = self._model_download_lifecycle.request_shutdown()
        runtime_closed = self._assistant_runtime.close()
        if runtime_closed:
            terminal = self._assistant_turn_state.shutdown_terminal()
            if terminal is not None:
                self._on_assistant_turn_finished(terminal)
        return runtime_closed and downloads_idle

    def handle_panel_navigation(self, payload: object) -> None:
        """Open one controller-validated panel request without guessing payloads."""
        if not isinstance(payload, AssistantPanelNavigationRequest):
            logger.error(
                "Ignored invalid assistant panel navigation: %s",
                redact_public_text(payload),
            )
            self._show_low_priority_notice(
                "The requested XBrainLab view could not be opened."
            )
            return

        def _resolve(success: bool) -> None:
            controller = self.agent_controller
            if controller is not None:
                controller.on_panel_navigation_resolved(payload, success=success)

        if payload.correlation is not None:
            self._open_assistant_panel_target(
                payload.target,
                view_mode=payload.view_mode or "",
                on_terminal=_resolve,
            )
        elif payload.view_mode:
            self._open_assistant_panel_target(
                payload.target,
                view_mode=payload.view_mode,
            )
        else:
            self._open_assistant_panel_target(payload.target)

    def handle_workflow_ui_handoff(self, payload: object) -> None:
        """Route one typed backend workflow decision to existing product UI."""
        if not isinstance(payload, WorkflowUiHandoffRequest):
            logger.error(
                "Ignored invalid workflow UI handoff: %s",
                redact_public_text(payload),
            )
            self._show_low_priority_notice(
                "The requested XBrainLab settings could not be opened."
            )
            return
        if self._defer_provisional_controller_event("workflow_handoff", payload):
            return
        if not self._workflow_handoff_identity_matches_active_turn(payload):
            logger.warning(
                "Ignored workflow UI handoff outside its active turn: %s",
                redact_public_text(payload.request_id),
            )
            return
        try:
            resolution = self._workflow_ui_handoff_host.open(
                payload,
                on_terminal=self._handle_workflow_ui_handoff_terminal,
            )
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="agent_manager",
                operation="open_workflow_ui_handoff",
            )
            resolution = WorkflowUiHandoffResolution.for_request(
                payload,
                status=WorkflowUiHandoffResolutionStatus.FAILED,
                message="The requested XBrainLab settings could not be opened.",
            )
        if not resolution.matches(payload):
            logger.error("Ignored mismatched workflow UI handoff resolution")
            self._show_low_priority_notice(
                "The requested XBrainLab settings did not return a valid result."
            )
            return
        self._forward_workflow_ui_handoff_resolution(resolution)

    def _handle_workflow_ui_handoff_terminal(self, payload: object) -> bool:
        """Forward one host-validated terminal callback to the runtime owner."""
        if not isinstance(payload, WorkflowUiHandoffResolution):
            logger.error(
                "Ignored invalid terminal workflow UI handoff: %s",
                redact_public_text(payload),
            )
            self._show_low_priority_notice(
                "The XBrainLab settings command returned an invalid result."
            )
            return False
        if not payload.status.is_terminal:
            logger.error(
                "Ignored nonterminal workflow UI callback: %s",
                redact_public_text(payload.status),
            )
            return False
        return self._forward_workflow_ui_handoff_resolution(payload)

    def _forward_workflow_ui_handoff_resolution(
        self,
        resolution: WorkflowUiHandoffResolution,
    ) -> bool:
        accepted = self._surface_runtime_command_result(
            self._assistant_runtime.resolve_ui_handoff(resolution),
            fallback=(
                "The assistant could not receive the completed XBrainLab settings step."
            ),
        )
        if not accepted and not resolution.status.is_terminal:
            self._workflow_ui_handoff_host.abandon_active()
        return accepted

    def _show_action_confirmation(self, request: object) -> None:
        """Present one exact assistant action in the transcript for a decision."""
        if not isinstance(request, AgentConfirmationRequest):
            logger.error(
                "Ignored untyped assistant confirmation request: %s",
                redact_public_text(request),
            )
            return
        if self._defer_provisional_controller_event("confirmation", request):
            return
        if not self._confirmation_identity_matches_active_turn(
            request_id=request.request_id,
            command_name=request.command_name,
        ):
            logger.warning(
                "Ignored assistant confirmation outside its active turn: %s",
                redact_public_text(request.request_id),
            )
            return
        if self.chat_panel is None:
            logger.error("Assistant confirmation arrived before the panel was ready.")
            return

        current_values, current_context_changed = self._confirmation_current_values(
            request
        )
        self.chat_panel.show_confirmation_request(
            request,
            current_values=current_values,
            current_context_changed=current_context_changed,
        )
        if self.chat_dock is not None:
            self.chat_dock.show()
            self.chat_dock.raise_()

    def _resolve_action_confirmation(
        self,
        resolution: object,
    ) -> None:
        """Return one correlated card decision through the runtime transport."""
        if not isinstance(resolution, AgentConfirmationResolution):
            logger.error(
                "Ignored untyped assistant confirmation decision: %s",
                redact_public_text(resolution),
            )
            return
        if not self._confirmation_identity_matches_active_turn(
            request_id=resolution.request_id,
            command_name=resolution.command_name,
        ):
            logger.warning(
                "Ignored stale assistant confirmation decision: %s",
                redact_public_text(resolution.request_id),
            )
            if self.chat_panel is not None:
                self.chat_panel.clear_confirmation_request(resolution.request_id)
            return
        accepted = self._surface_runtime_command_result(
            self._assistant_runtime.confirm(resolution),
            fallback="The assistant could not receive your confirmation.",
        )
        if self.chat_panel is None:
            return
        if accepted:
            self.chat_panel.clear_confirmation_request(resolution.request_id)
        else:
            self.chat_panel.set_confirmation_submitting(
                resolution.request_id,
                False,
            )

    def _confirmation_identity_matches_active_turn(
        self,
        *,
        request_id: str,
        command_name: str,
    ) -> bool:
        """Bind one confirmation card to the exact active UI/runtime turn."""
        activity = self._last_assistant_activity
        lease = self._assistant_turn_state.lease
        return bool(
            lease is not None
            and isinstance(activity, AssistantTurnActivity)
            and activity.phase is AssistantTurnActivityPhase.WAITING_FOR_DECISION
            and activity.decision_owner is AssistantDecisionOwner.CONFIRMATION_CARD
            and activity.correlation == lease
            and activity.request_id == request_id
            and activity.command_name == command_name
        )

    def _workflow_handoff_identity_matches_active_turn(
        self,
        request: WorkflowUiHandoffRequest,
    ) -> bool:
        """Bind one product-UI request to its exact active waiting lease."""
        activity = self._last_assistant_activity
        lease = self._assistant_turn_state.lease
        if request.kind is WorkflowUiHandoffKind.ACTION_REQUESTED:
            phase_matches = bool(
                isinstance(activity, AssistantTurnActivity)
                and activity.phase is AssistantTurnActivityPhase.RUNNING_COMMAND
                and activity.decision_owner is None
            )
        else:
            phase_matches = bool(
                isinstance(activity, AssistantTurnActivity)
                and activity.phase is AssistantTurnActivityPhase.WAITING_FOR_DECISION
                and activity.decision_owner
                in {
                    AssistantDecisionOwner.GUI_DIALOG,
                    AssistantDecisionOwner.PANEL_HANDOFF,
                }
            )
        return bool(
            lease is not None
            and isinstance(activity, AssistantTurnActivity)
            and phase_matches
            and activity.correlation == lease
            and activity.request_id == request.request_id
            and activity.command_name == request.tool_name
        )

    def _confirmation_current_values(
        self,
        request: AgentConfirmationRequest,
    ) -> tuple[dict[str, str] | None, bool]:
        """Read display-only current values from one matching publication."""
        try:
            publication = self.application_service.get_view_publication()
        except Exception as exc:
            logger.debug(
                "Could not read confirmation comparison values: %s",
                redact_public_text(exc),
            )
            return None, False

        request_generation = request.publication_generation
        if not getattr(publication, "usable", False) or not getattr(
            publication.state, "state_reliable", False
        ):
            return None, False
        if (
            request_generation is not None
            and publication.generation != request_generation
        ):
            return {}, True
        if request_generation is None:
            return None, False

        training = publication.state.training
        candidates: dict[str, object] = {}
        if training.has_training_option:
            candidates.update(training.training_option)
            if "checkpoint_epoch" in candidates:
                candidates["save_checkpoints_every"] = candidates["checkpoint_epoch"]
        if training.has_model:
            candidates.update(training.model_params)
            if training.model_name:
                candidates["model_name"] = training.model_name

        display_values = {
            str(key).replace("_", " ").strip().capitalize(): (
                AgentManager._confirmation_display_value(str(key), value)
            )
            for key, value in candidates.items()
        }
        requested_labels = {label for label, _value in request.parameter_rows}
        if not requested_labels.issubset(display_values):
            return None, False
        return (
            {
                label: value
                for label, value in display_values.items()
                if label in requested_labels
            },
            False,
        )

    @classmethod
    def _confirmation_display_value(cls, key: str, value: object) -> str:
        """Normalize authoritative display aliases for proposal comparison."""
        normalized_key = key.strip().casefold()
        if isinstance(value, str):
            normalized_value = " ".join(value.strip().casefold().split())
            if normalized_key == "optimizer":
                value = normalized_value
            elif normalized_key == "device" and normalized_value.startswith("cuda:"):
                value = "cuda"
            elif normalized_key == "evaluation_option":
                value = {
                    "best validation loss": "val_loss",
                    "best validation auc": "val_auc",
                    "best validation performance": "val_acc",
                    "last epoch": "last_epoch",
                }.get(normalized_value, normalized_value)
        return cls._display_ui_value(value)

    @staticmethod
    def _display_ui_value(value: object) -> str:
        """Format safe snapshot values without exposing object representations."""
        if value is None:
            return "None"
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, (str, int, float)):
            return str(value)
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value[:8])
        return "Configured"

    def _switch_sub_view(self, panel_index, view_mode):
        """Switch to a specific tab or view within a panel.

        Args:
            panel_index: Index of the panel in the stacked widget.
            view_mode: String identifier for the target sub-view
                (e.g., ``"saliency_map"``, ``"3d_plot"``).

        """
        # Map panel index to view mode mapping
        view_map = {
            4: {  # Visualization Panel
                "saliency_map": 0,
                "spectrogram": 1,
                "topographic_map": 2,
                "3d_plot": VIZ_TAB_3D_PLOT,
            },
            # Future: Add Preprocess or Evaluation panels if they have tabs
        }

        if panel_index in view_map and view_mode in view_map[panel_index]:
            target_panel = self.main_window.stack.widget(panel_index)
            target_tab_index = view_map[panel_index][view_mode]

            if hasattr(target_panel, "tabs"):
                target_panel.tabs.setCurrentIndex(target_tab_index)
                logger.info(
                    "Switched sub-view to %s (Tab %d)",
                    redact_public_text(view_mode),
                    target_tab_index,
                )
