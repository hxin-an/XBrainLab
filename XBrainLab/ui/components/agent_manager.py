"""Qt composition and presentation adapter for the in-app assistant."""

from typing import Any, cast

from PyQt6.QtCore import (
    QObject,
    QRect,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QWidget,
)

from XBrainLab.backend.application import (
    get_application_service,
)
from XBrainLab.backend.controller.chat_controller import (
    ChatController,
    ChatMessagePresentationKind,
    ChatResponseAction,
    ChatResponseActionKind,
    ChatResponseActionSelection,
)
from XBrainLab.backend.controller.chat_controller import (
    ChatPanelTarget as ChatHistoryPanelTarget,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.agent.assistant_activity import (
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
    AssistantResponseAction,
    AssistantResponseActionKind,
    AssistantResponseKind,
    AssistantResponsePresentation,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation, AssistantTurnTerminal
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.llm.core.config import LLMConfig
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
    ChatResponseActionSelectionView,
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
from XBrainLab.ui.dialogs.local_runtime_first_run_dialog import (
    LocalRuntimeFirstRunDialog,
)
from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog
from XBrainLab.ui.refresh_coordinator import (
    begin_command_refresh_suppression,
    complete_command_refresh_suppression,
)
from XBrainLab.ui.styles.icons import Icons
from XBrainLab.ui.styles.stylesheets import Stylesheets

VIZ_TAB_3D_PLOT = 3
"""Index of the 3D Plot tab in the visualization panel."""

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
    "execution_mode_changed",
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


class AssistantDockTitleBar(QWidget):
    """Product header for the assistant dock with native drag behavior."""

    def __init__(self, on_float_toggle, parent=None):
        super().__init__(parent)
        self._on_float_toggle = on_float_toggle
        self.status_badge: QLabel | None = None
        self.retry_button: QPushButton | None = None
        self.float_button: QPushButton | None = None
        self._retry_available = False
        self._retry_enabled = False

    def set_assistant_status(self, text: str) -> None:
        """Render one compact status without exposing runtime diagnostics."""
        if self.status_badge is None:
            return
        normalized = " ".join(str(text or "Local · Setup").split())
        self.status_badge.setText(normalized)
        self.status_badge.setToolTip(normalized)
        state = normalized.rsplit("·", 1)[-1].strip().lower()
        self.status_badge.setProperty("assistantState", state)
        style = self.status_badge.style()
        if style is not None:
            style.unpolish(self.status_badge)
            style.polish(self.status_badge)

    def resizeEvent(self, event):  # noqa: N802
        """Keep essential title actions readable at narrow dock widths."""
        super().resizeEvent(event)
        self._sync_responsive_actions()

    def set_retry_available(self, available: bool, *, enabled: bool) -> None:
        """Show title-bar Retry only when space and request state allow it."""
        self._retry_available = bool(available)
        self._retry_enabled = bool(enabled)
        self._sync_responsive_actions()

    def _sync_responsive_actions(self) -> None:
        """Hide optional controls before allowing the product title to clip."""
        if self.status_badge is not None:
            self.status_badge.setVisible(self.width() >= 400)
        compact = self.width() < 470
        if self.retry_button is not None:
            self.retry_button.setVisible(self._retry_available and not compact)
            self.retry_button.setEnabled(self._retry_enabled and not compact)
        if self.float_button is not None:
            self.float_button.setVisible(not compact)

    def mousePressEvent(self, event):  # noqa: N802
        """Let QDockWidget handle title-bar drags from empty title space."""
        if event.button() == Qt.MouseButton.LeftButton:
            event.ignore()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        """Let QDockWidget continue native dock drag handling."""
        event.ignore()

    def mouseReleaseEvent(self, event):  # noqa: N802
        """Let QDockWidget finish native dock drag handling."""
        event.ignore()

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        """Mirror native title-bar double-click float/dock behavior."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_float_toggle()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


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

    def __init__(
        self,
        main_window,
        study,
        *,
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
        self.application_service = get_application_service(study)
        self.main_window.destroyed.connect(self._on_main_window_destroyed)

        self.chat_panel = None
        self.chat_dock = None

        self.chat_controller = ChatController()
        # Connect Chat Controller Signals
        self.chat_controller.processing_state_changed.connect(
            self.on_processing_state_changed,
        )
        self._last_user_input: str | None = None
        self._runtime_unavailable_notice: str | None = None
        self._assistant_status_projection: AssistantStatusProjection | None = None
        self._active_response_presentation_id: str | None = None
        self._application_command_in_flight = False
        self._last_assistant_activity: AssistantTurnActivity | None = None
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
        self._model_download_lifecycle = (
            model_download_lifecycle or ModelDownloadLifecycle(parent=self)
        )
        self._presentation = AgentPresentationService()
        self._execution_mode = "single"
        self._workflow_ui_handoff_host = WorkflowUiHandoffHost(
            self.main_window,
            application_service=self.application_service,
        )
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

    def _on_main_window_destroyed(self, _object=None) -> None:
        """Stop assistant threads before Qt destroys QObject children."""
        self.close()

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
        title bar with float/settings/new-conversation buttons, and
        adds the dock to the main window's right area.
        """
        self.chat_panel = ChatPanel()
        self._assistant_runtime.replay_runtime_snapshot()

        # Connect UI to ChatController
        self.chat_panel.active_response_presentation_changed.connect(
            self._on_active_response_presentation_changed
        )
        self.chat_panel.connect_controller(self.chat_controller)

        # Connect ChatPanel signals to self (for further dispatch)
        self.chat_panel.send_message.connect(self.handle_user_input)
        self.chat_panel.stop_generation.connect(self.stop_generation)
        self.chat_panel.execution_mode_changed.connect(self._on_execution_mode_changed)
        self.chat_panel.debug_tool_requested.connect(self._handle_debug_tool_requested)
        self.chat_panel.open_settings_requested.connect(self.open_settings_dialog)
        retry_runtime_requested = getattr(
            self.chat_panel,
            "retry_local_assistant_requested",
            None,
        )
        if retry_runtime_requested is not None:
            retry_runtime_requested.connect(self.retry_local_assistant)
        self.chat_panel.response_action_requested.connect(
            self._handle_response_action_selection
        )
        self.chat_panel.confirmation_decision_requested.connect(
            self._resolve_action_confirmation
        )

        self.chat_dock = QDockWidget("XBrainLab", self.main_window)
        self.chat_dock.setWidget(self.chat_panel)
        self.chat_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea,
        )
        self.chat_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable,
        )
        self.chat_dock.setMinimumWidth(320)

        # Custom title bar with conversation controls and native dock dragging.
        title_bar = AssistantDockTitleBar(self._toggle_float, self.chat_dock)
        self.assistant_header = title_bar
        title_bar.setStyleSheet(Stylesheets.AGENT_TITLE_BAR)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(10, 3, 5, 3)
        title_layout.setSpacing(5)

        title_label = QLabel("XBrainLab Assistant")
        title_label.setObjectName("AssistantDockTitle")
        title_label.setStyleSheet(Stylesheets.AGENT_TITLE_LABEL)
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_label.setMinimumWidth(title_label.sizeHint().width())
        title_layout.addWidget(title_label)

        status_badge = QLabel("")
        status_badge.setObjectName("AssistantDockStatus")
        status_badge.setStyleSheet(Stylesheets.AGENT_STATUS_BADGE)
        status_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_bar.status_badge = status_badge
        title_bar.set_assistant_status(self.chat_panel.header_status_text)
        title_layout.addWidget(status_badge)
        title_layout.addStretch()
        self.chat_panel.header_status_changed.connect(title_bar.set_assistant_status)

        title_style = title_bar.style()
        if title_style is None:
            title_style = QApplication.style()
        if title_style is None:
            raise RuntimeError("Qt application style is unavailable.")

        self.retry_title_btn = QPushButton()
        self.retry_title_btn.setIcon(
            title_style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.retry_title_btn.setIconSize(QSize(16, 16))
        self.retry_title_btn.setFixedSize(28, 28)
        self.retry_title_btn.setToolTip("Send a request before retrying.")
        self.retry_title_btn.setAccessibleName("Retry last request")
        self.retry_title_btn.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        self.retry_title_btn.setEnabled(False)
        self.retry_title_btn.setVisible(False)
        self.retry_title_btn.clicked.connect(self.retry_last_user_input)
        title_bar.retry_button = self.retry_title_btn
        title_layout.addWidget(self.retry_title_btn)

        # New chat clears only the assistant conversation, never workflow state.
        self.new_conv_title_btn = QPushButton("+")
        self.new_conv_title_btn.setFixedSize(28, 28)
        self.new_conv_title_btn.setToolTip("New chat")
        self.new_conv_title_btn.setAccessibleName("New chat")
        self.new_conv_title_btn.setAccessibleDescription(
            "Clear the assistant conversation without changing the EEG workflow."
        )
        self.new_conv_title_btn.setStyleSheet(Stylesheets.AGENT_NEW_CONV_BTN)
        self.new_conv_title_btn.clicked.connect(self.start_new_conversation)
        title_layout.addWidget(self.new_conv_title_btn)

        # Options menu. Keep it to real, implemented actions.
        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(QIcon(Icons.SETTINGS.path))
        self.settings_btn.setIconSize(QSize(16, 16))
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setToolTip("Assistant settings")
        self.settings_btn.setAccessibleName("Assistant settings")
        self.settings_btn.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        self.settings_menu = QMenu(self.settings_btn)
        settings_action = QAction("Assistant settings", self.settings_btn)
        settings_action.triggered.connect(
            lambda _checked=False: self.open_settings_dialog()
        )
        self.settings_menu.addAction(settings_action)
        self.clear_conversation_title_action = QAction(
            "New chat",
            self.settings_btn,
        )
        self.clear_conversation_title_action.setToolTip(
            "Clear the assistant conversation without changing the EEG workflow."
        )
        self.clear_conversation_title_action.setEnabled(False)
        self.clear_conversation_title_action.triggered.connect(
            lambda _checked=False: self.start_new_conversation()
        )
        self.settings_menu.addAction(self.clear_conversation_title_action)
        self.settings_btn.setMenu(self.settings_menu)
        title_layout.addWidget(self.settings_btn)

        self.float_btn = QPushButton()
        self.float_btn.setIcon(
            title_style.standardIcon(QStyle.StandardPixmap.SP_TitleBarNormalButton)
        )
        self.float_btn.setIconSize(QSize(16, 16))
        self.float_btn.setFixedSize(28, 28)
        self.float_btn.setToolTip("Float assistant")
        self.float_btn.setAccessibleName("Float assistant")
        self.float_btn.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        self.float_btn.clicked.connect(self._toggle_float)
        title_bar.float_button = self.float_btn
        title_layout.addWidget(self.float_btn)

        self.close_btn = QPushButton()
        self.close_btn.setIcon(
            title_style.standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton)
        )
        self.close_btn.setIconSize(QSize(16, 16))
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setToolTip("Close assistant")
        self.close_btn.setAccessibleName("Close assistant")
        self.close_btn.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        self.close_btn.clicked.connect(self.chat_dock.close)
        title_layout.addWidget(self.close_btn)

        self.chat_dock.setTitleBarWidget(title_bar)
        title_bar._sync_responsive_actions()
        self.chat_dock.topLevelChanged.connect(self._on_dock_top_level_changed)

        self.main_window.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.chat_dock,
        )

        self.chat_dock.visibilityChanged.connect(self.update_ai_btn_state)
        self.chat_dock.hide()
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

    def _toggle_float(self):
        """Toggle floating/docked state of the chat dock."""
        if self.chat_dock:
            should_float = not self.chat_dock.isFloating()
            self.chat_dock.setFloating(should_float)
            if should_float:
                self._place_floating_dock()

    def _on_dock_top_level_changed(self, floating: bool) -> None:
        """Keep the assistant dock usable when it becomes a floating window."""
        action = "Dock assistant" if floating else "Float assistant"
        if hasattr(self, "float_btn"):
            self.float_btn.setToolTip(action)
            self.float_btn.setAccessibleName(action)
        if floating:
            self._place_floating_dock()

    def _place_floating_dock(self) -> None:
        """Size and clamp the floating assistant dock within the active screen."""
        if not self.chat_dock:
            return

        available = self._available_screen_geometry()
        main_frame = self.main_window.frameGeometry()
        dock_width = min(max(self.chat_dock.width(), 420), available.width())
        dock_height = min(
            max(self.chat_dock.height(), min(self.main_window.height(), 720)),
            available.height(),
        )

        x = main_frame.right() - dock_width
        y = main_frame.top() + 48
        x = min(max(x, available.left()), available.right() - dock_width + 1)
        y = min(max(y, available.top()), available.bottom() - dock_height + 1)

        self.chat_dock.setMinimumSize(QSize(320, 520))
        self.chat_dock.setGeometry(QRect(x, y, dock_width, dock_height))

    def _available_screen_geometry(self) -> QRect:
        """Return the usable screen area for the main window or primary screen."""
        screen = self.main_window.screen() or QApplication.primaryScreen()
        if screen is not None:
            return screen.availableGeometry()
        return QRect(0, 0, 1280, 800)

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

            config = self._assistant_runtime.load_config()
            if self._assistant_runtime.needs_first_run(config):
                choice = self._show_local_runtime_first_run_dialog(config)
                outcome = self._assistant_runtime.apply_first_run_choice(
                    config,
                    choice,
                )
                if outcome.action is RuntimeSetupAction.OPEN_SETTINGS:
                    self.open_settings_dialog()
                    return
                if outcome.action is RuntimeSetupAction.STOP:
                    self.refresh_backend_status()
                    self._show_runtime_setup_required(outcome.message)
                    return
                config = self._assistant_runtime.load_config()

            activation = self._assistant_runtime.activate(
                config,
                execution_mode=self._execution_mode,
            )
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

    def _show_local_runtime_first_run_dialog(self, config: LLMConfig) -> str:
        """Show the local-runtime consent dialog and return the selected choice."""
        dialog = LocalRuntimeFirstRunDialog(self.main_window, config)
        if dialog.exec():
            return dialog.choice
        return LocalRuntimeFirstRunDialog.LATER

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

        activation = self._assistant_runtime.activate_persisted(
            execution_mode=self._execution_mode,
        )
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

    def prepare_model_deletion(self, model_name: str):
        """Prepare for model file deletion by switching away if active.

        Called by ``ModelSettingsDialog`` before deleting a model. If the
        model is currently loaded in local mode, block deletion until the
        assistant is switched away from that active local backend.

        Args:
            model_name: The name of the model being deleted.

        Returns:
            ``True`` if it is safe to proceed with deletion.

        """
        if self.agent_controller is None:
            return True
        if self._assistant_runtime.active_local_runtime_blocks_model_deletion():
            logger.info(
                "Blocking deletion of active local model: %s",
                redact_public_text(model_name),
            )
            QMessageBox.warning(
                self.main_window,
                "Assistant Model In Use",
                "The AI assistant is currently using this local model.\n"
                "Close the assistant or select a different model before deleting it.",
            )
            return False

        return True

    def start_system(self):
        """Start the runtime owner after the assistant UI is available."""
        if not self.chat_panel:
            return
        if self._assistant_runtime.start(self._execution_mode):
            self.refresh_backend_status()

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
        controller.execution_mode_changed.connect(
            self._sync_execution_mode_ui,
        )

    def _on_application_command_started(self) -> None:
        """Suppress observer refresh until the agent command result arrives."""
        self._application_command_in_flight = True
        begin_command_refresh_suppression(self.main_window)
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
            self.chat_panel.set_turn_activity(presentation)

    def _on_application_command_completed(self, result) -> None:
        """Refresh product panels from the agent command result envelope."""
        self._application_command_in_flight = False
        complete_command_refresh_suppression(
            self.main_window,
            getattr(result, "changed_state", None),
        )

    def handle_user_input(self, text):
        """Handle text input from ChatPanel.

        Adds the message to ``ChatController`` history and forwards it
        to the ``LLMController`` for processing.

        Args:
            text: The user's message text.

        """
        text = text.strip()
        if not text:
            return
        if self.agent_controller is None:
            activation = self._assistant_runtime.activate_persisted(
                execution_mode=self._execution_mode,
            )
            if activation.available:
                self._show_low_priority_notice(
                    "Wait for the local assistant to finish loading."
                )
            else:
                self._show_runtime_unavailable(activation.message)
            return

        if not self.chat_controller.can_accept_turn():
            self._show_low_priority_notice(
                "Chat history is full. Clear the conversation before sending "
                "another request."
            )
            return

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
            self._show_low_priority_notice(
                "The assistant could not accept this request. Try again."
            )
            return
        if not admission.accepted:
            self._finish_assistant_turn_submission(submission, accepted=False)
            self._deferred_submission_events = None
            self._show_low_priority_notice(admission.message)
            return

        correlation = admission.correlation
        if correlation is None:
            self._finish_assistant_turn_submission(submission, accepted=False)
            self._deferred_submission_events = None
            logger.error("Assistant admission is missing exact turn correlation")
            self._show_low_priority_notice(
                "The assistant could not correlate this request. Try again."
            )
            return

        deferred_events = self._deferred_submission_events
        self._deferred_submission_events = None
        if not self._finish_assistant_turn_submission(
            submission,
            accepted=True,
            correlation=correlation,
        ):
            self._show_low_priority_notice(
                "The assistant could not correlate this request. Try again."
            )
            return
        if self.chat_panel and hasattr(self.chat_panel, "clear_response_actions"):
            self.chat_panel.clear_response_actions()
        self.chat_controller.add_user_message(text)
        self._last_user_input = text
        self._set_retry_available(True)
        self._replay_deferred_submission_events(deferred_events)

    def _handle_debug_tool_requested(
        self,
        tool_name: str,
        params: dict[str, Any],
        confirmed: bool = False,
        authorization_text: str = "",
    ) -> None:
        """Admit one debug-script action through the normal correlated turn lease."""
        if self.agent_controller is None:
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
            return
        if not admission.accepted:
            self._finish_assistant_turn_submission(submission, accepted=False)
            self._deferred_submission_events = None
            self._show_low_priority_notice(admission.message)
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
            return
        if self.chat_panel and hasattr(self.chat_panel, "clear_response_actions"):
            self.chat_panel.clear_response_actions()
        self._replay_deferred_submission_events(deferred_events)

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
        if self.chat_panel and hasattr(self.chat_panel, "show_notice"):
            self.chat_panel.show_notice("")
        kind = self._chat_presentation_kind(presentation)
        typed_actions = presentation.actions
        if (
            presentation.kind is AssistantResponseKind.ERROR
            and not typed_actions
            and self._last_user_input
        ):
            typed_actions = (
                AssistantResponseAction.send_message(
                    "Try again",
                    self._last_user_input,
                ),
            )
        actions = tuple(self._chat_response_action(action) for action in typed_actions)
        visible_text = self._presentation.assistant_transcript_message(
            presentation.text
        )
        self.chat_controller.add_agent_message(
            visible_text,
            presentation_kind=kind,
            presentation_id=presentation.presentation_id,
            actions=actions,
        )

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

    @staticmethod
    def _chat_response_action(
        action: AssistantResponseAction,
    ) -> ChatResponseAction:
        """Convert one typed runtime action into the persisted UI contract."""
        if action.kind is AssistantResponseActionKind.SEND_MESSAGE:
            return ChatResponseAction(
                action_id=action.action_id,
                label=action.label,
                kind=ChatResponseActionKind.SEND_MESSAGE,
                prompt=action.prompt,
            )
        if action.panel is None:
            raise ValueError("Open-panel assistant action is missing its target.")
        return ChatResponseAction(
            action_id=action.action_id,
            label=action.label,
            kind=ChatResponseActionKind.OPEN_PANEL,
            panel=ChatHistoryPanelTarget(action.panel.value),
        )

    def _handle_response_presentation(self, payload: object) -> None:
        """Render one typed response and its correlated next actions."""
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
        terminal_cancellation = bool(
            payload.kind is AssistantResponseKind.CANCELLED and not payload.actions
        )
        if not self._assistant_turn_state.accepts_response(
            payload.correlation,
            terminal_cancellation=terminal_cancellation,
        ):
            logger.warning(
                "Ignored stale assistant response presentation for %s",
                redact_public_text(payload.correlation),
            )
            return
        self._render_visible_assistant_response(payload)

    def _on_active_response_presentation_changed(self, payload: object) -> None:
        """Accept the ChatPanel's immutable active-action identity as authoritative."""
        if payload is None:
            self._active_response_presentation_id = None
            return
        if not isinstance(payload, str) or not payload:
            logger.error(
                "Ignored invalid active response presentation ID: %s",
                redact_public_text(payload),
            )
            return
        self._active_response_presentation_id = payload

    def _clear_active_response_actions(self) -> None:
        """Retire response actions when Stop/cancel closes their live turn."""
        self._on_active_response_presentation_changed(None)
        self.chat_controller.consume_all_response_actions()
        if self.chat_panel and hasattr(self.chat_panel, "clear_response_actions"):
            self.chat_panel.clear_response_actions()

    def _handle_response_action_selection(self, payload: object) -> None:
        """Route only an action belonging to the still-current presentation."""
        if not isinstance(payload, ChatResponseActionSelectionView):
            logger.error(
                "Ignored invalid assistant response action: %s",
                redact_public_text(payload),
            )
            return
        if payload.presentation_id != self._active_response_presentation_id:
            logger.warning("Ignored stale assistant response action selection")
            return
        view_action = payload.action
        try:
            selection = ChatResponseActionSelection(
                presentation_id=payload.presentation_id,
                action_id=view_action.action_id,
                label=view_action.label,
                kind=ChatResponseActionKind(view_action.kind.value),
                prompt=view_action.prompt,
                panel=(
                    ChatHistoryPanelTarget(view_action.panel.value)
                    if view_action.panel is not None
                    else None
                ),
            )
        except (TypeError, ValueError):
            logger.warning("Ignored malformed assistant response action selection")
            return
        action = self.chat_controller.resolve_and_consume_response_action(selection)
        if action is None:
            logger.warning("Ignored forged, stale, or consumed response action")
            return
        self._on_active_response_presentation_changed(None)
        if action.kind is ChatResponseActionKind.SEND_MESSAGE:
            self.handle_user_input(action.prompt)
            return
        if action.panel is not None:
            self._open_assistant_panel_target(AssistantPanelTarget(action.panel.value))

    def _open_assistant_panel_target(
        self,
        target: AssistantPanelTarget,
        *,
        view_mode: str = "",
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
                status_bar.showMessage(f"{target.value.title()} is open.")

        if view_mode:
            materialized = self.main_window.switch_page(
                panel_index,
                on_ready=_on_ready,
            )
            if materialized is not False and not ready_callback_delivered:
                _on_ready(None)
        else:
            materialized = self.main_window.switch_page(panel_index)
            if materialized is not False and status_bar:
                status_bar.showMessage(f"{target.value.title()} is open.")

        if materialized is False and status_bar:
            status_bar.showMessage(f"Opening {target.value.title()}...")
        return panel_index

    def retry_last_user_input(self):
        """Retry the most recent user request if the assistant is idle."""
        if not self._last_user_input:
            self._show_low_priority_notice("Send a request before using Retry.")
            return
        self.handle_user_input(self._last_user_input)

    def retry_local_assistant(self) -> None:
        """Retry the persisted local runtime after a visible startup failure."""
        if self._assistant_runtime.current.phase is AssistantRuntimePhase.LOADING:
            return
        activation = self._assistant_runtime.activate_persisted(
            execution_mode=self._execution_mode,
        )
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
                self._clear_active_response_actions()
                if self.chat_panel:
                    self.chat_panel.set_turn_activity(ChatTurnPresentation.stopping())

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
        self._update_title_action_buttons()

    def _set_retry_available(self, available: bool) -> None:
        """Synchronize retry/clear affordances in the dock title bar."""
        self._update_title_action_buttons()

    def _update_title_action_buttons(self) -> None:
        """Keep title-bar actions enabled only when they can run."""
        is_processing = bool(
            self.chat_controller
            and getattr(self.chat_controller, "is_processing", False)
        )
        retry_available = bool(self._last_user_input)
        enabled = retry_available and not is_processing

        if hasattr(self, "retry_title_btn"):
            header = getattr(self, "assistant_header", None)
            if isinstance(header, AssistantDockTitleBar):
                header.set_retry_available(retry_available, enabled=enabled)
            else:
                self.retry_title_btn.setEnabled(enabled)
                self.retry_title_btn.setVisible(retry_available)
            self.retry_title_btn.setToolTip(
                "Retry the last request"
                if retry_available
                else "Send a request before retrying."
            )
        if hasattr(self, "clear_conversation_title_action"):
            self.clear_conversation_title_action.setEnabled(enabled)

    def _on_execution_mode_changed(self, mode: str):
        """Forward execution mode change from ChatPanel to controller.

        Args:
            mode: ``'single'`` or ``'multi'``.

        """
        self._execution_mode = "multi" if mode == "multi" else "single"
        result = self._assistant_runtime.set_execution_mode(self._execution_mode)
        if isinstance(result, RuntimeCommandAdmissionResult) and not result.accepted:
            # The selected mode is still retained locally and will be applied
            # during the next activation; no transient startup notice is needed.
            logger.info(
                "Assistant mode update deferred: %s",
                redact_public_text(result.message),
            )

    def _sync_execution_mode_ui(self, mode: str):
        """Sync execution mode button text from controller to ChatPanel.

        Args:
            mode: ``'single'`` or ``'multi'``.

        """
        self._execution_mode = "multi" if mode == "multi" else "single"
        if self.chat_panel:
            sync_mode = getattr(self.chat_panel, "set_execution_mode", None)
            if callable(sync_mode):
                sync_mode(self._execution_mode)

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
        self.chat_controller.clear_conversation()
        if self.chat_panel:
            self.chat_panel.clear_confirmation_request()
        self._last_user_input = None
        self._on_active_response_presentation_changed(None)
        if not self._assistant_turn_state.reset_idle():
            logger.error(
                "Runtime reset accepted while an assistant turn still owned UI"
            )
        self._set_retry_available(False)
        if self.chat_panel and hasattr(self.chat_panel, "show_notice"):
            self.chat_panel.show_notice("")

        if self.agent_controller:
            logger.info("Assistant conversation state reset successfully")

        # Keep a runtime blocker actionable after the transcript is cleared.
        runtime = self._assistant_runtime.current
        if runtime.phase is AssistantRuntimePhase.FAILED:
            self._runtime_unavailable_notice = None
            self._show_runtime_unavailable(runtime.error)

        self.refresh_backend_status()

    # Signal to notify Main Window (or other listeners) about status updates
    status_message_received = pyqtSignal(str)

    def _show_low_priority_notice(self, message: str) -> None:
        """Surface an assistant-owned notice without duplicating global status."""
        safe_message = redact_public_text(message)
        if self.chat_panel and hasattr(self.chat_panel, "show_notice"):
            self.chat_panel.show_notice(safe_message)

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
        presentation = present_assistant_activity(
            payload,
            application_command_in_flight=self._application_command_in_flight,
        )
        processing = presentation.is_busy
        if self.chat_controller.is_processing != processing:
            self.chat_controller.set_processing(processing)
        if self.chat_panel:
            if processing and hasattr(self.chat_panel, "show_notice"):
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
        phase_before_terminal = self._assistant_turn_state.phase
        if not self._assistant_turn_state.accept_terminal(payload):
            logger.warning(
                "Ignored stale assistant UI terminal for %s",
                redact_public_text(payload.correlation),
            )
            return
        self._render_delivery_terminal_error(payload)
        if self.chat_panel:
            self.chat_panel.clear_confirmation_request()
        cancelled_outcomes = {"cancelled", "shutdown_cancelled"}
        if (
            phase_before_terminal is AssistantUiTurnPhase.STOPPING
            or payload.outcome in cancelled_outcomes
        ):
            self._clear_active_response_actions()
        self._last_assistant_activity = None
        if self.chat_controller.is_processing:
            self.chat_controller.set_processing(False)
        elif self.chat_panel:
            self.chat_panel.set_turn_activity(ChatTurnPresentation.idle())
        self.refresh_backend_status()

    def _render_delivery_terminal_error(
        self,
        terminal: AssistantTurnTerminal,
    ) -> None:
        """Persist one actionable error for a failed host-to-controller delivery."""
        message = _DELIVERY_TERMINAL_MESSAGES.get(terminal.outcome)
        if message is None:
            return
        self._render_visible_assistant_response(
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
            self.chat_panel.set_runtime_state(snapshot.phase.value, safe_error)

    def refresh_backend_status(self):
        """Refresh the compact backend/model status shown in the chat panel."""
        if not self.chat_panel or not hasattr(self.chat_panel, "set_status_summary"):
            return

        try:
            publication = self.application_service.get_view_publication()
            projection = build_assistant_status_projection(publication)
            self._assistant_status_projection = projection
            runtime = self._assistant_runtime.current
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

            self.status_message_received.emit(
                projection.footer_hint,
            )
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

    def close(self) -> bool:
        """Clean up the agent controller resources."""
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
        if payload.view_mode:
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

    def _confirmation_current_values(
        self,
        request: AgentConfirmationRequest,
    ) -> tuple[dict[str, str], bool]:
        """Read display-only current values from one matching publication."""
        try:
            publication = self.application_service.get_view_publication()
        except Exception as exc:
            logger.debug(
                "Could not read confirmation comparison values: %s",
                redact_public_text(exc),
            )
            return {}, False

        request_generation = request.publication_generation
        if not getattr(publication, "usable", False) or not getattr(
            publication.state, "state_reliable", False
        ):
            return {}, False
        if (
            request_generation is not None
            and publication.generation != request_generation
        ):
            return {}, True
        if request_generation is None:
            return {}, False

        training = publication.state.training
        candidates: dict[str, object] = {}
        if training.has_training_option:
            candidates.update(training.training_option)
        if training.has_model:
            candidates.update(training.model_params)
            if training.model_name:
                candidates["model"] = training.model_name

        display_values = {
            str(key).replace("_", " ").strip().capitalize(): self._display_ui_value(
                value
            )
            for key, value in candidates.items()
        }
        requested_labels = {label for label, _value in request.parameter_rows}
        return (
            {
                label: value
                for label, value in display_values.items()
                if label in requested_labels
            },
            False,
        )

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
