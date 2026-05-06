"""Agent Manager for AI assistant lifecycle and UI integration.

Orchestrates the ChatController, LLMController, and ChatPanel dock widget,
handling initialization, user interaction, model switching, and VRAM checks.
"""

from PyQt6.QtCore import QObject, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QWidget,
)

from XBrainLab.backend.application import (
    ApplyMontageCommand,
    CommandName,
    QueryStateCommand,
)
from XBrainLab.backend.controller.chat_controller import ChatController
from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.ui.application_capabilities import (
    LegacyControllerFallbackUnavailableError,
    blocked_reason,
    execute_application_command,
    get_command_capability,
    run_legacy_controller_fallback,
)
from XBrainLab.ui.chat.panel import ChatPanel
from XBrainLab.ui.components.vram_checker import VRAMConflictChecker
from XBrainLab.ui.dialogs.local_runtime_first_run_dialog import (
    LocalRuntimeFirstRunDialog,
)
from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog
from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import PickMontageDialog
from XBrainLab.ui.montage_positions import normalize_montage_positions
from XBrainLab.ui.product_language import (
    command_labels,
    tool_action_label,
    workflow_stage_label,
)
from XBrainLab.ui.styles.stylesheets import Stylesheets

VIZ_TAB_3D_PLOT = 3
"""Index of the 3D Plot tab in the visualization panel."""

# Panel indices in the main window stack
PANEL_DATASET = 0
PANEL_PREPROCESS = 1
PANEL_TRAINING = 2
PANEL_EVALUATION = 3
PANEL_VISUALIZATION = 4


class AssistantDockTitleBar(QWidget):
    """Minimal dock title bar that preserves native dock dragging."""

    def __init__(self, on_float_toggle, parent=None):
        super().__init__(parent)
        self._on_float_toggle = on_float_toggle

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
    """Manages the lifecycle and UI integration of the AI Agent System.

    Orchestrates the interaction between the ``ChatController`` (UI-side
    state management), ``LLMController`` (AI inference), and the
    ``ChatPanel`` (visual chat interface).

    Attributes:
        main_window: Reference to the parent ``MainWindow``.
        study: The application ``Study`` instance.
        chat_panel: The ``ChatPanel`` widget, or ``None`` before init.
        chat_dock: The ``QDockWidget`` hosting the chat panel.
        chat_controller: The ``ChatController`` managing chat state.
        preprocess_controller: Controller for preprocessing operations.
        agent_controller: The ``LLMController`` for AI inference, or
            ``None`` before lazy initialization.
        agent_initialized: Whether the agent system has been started.

    """

    def __init__(self, main_window, study):
        """Initialize the AgentManager.

        Args:
            main_window: The parent ``MainWindow`` instance.
            study: The application ``Study`` instance providing
                controllers and shared state.

        """
        super().__init__(main_window)
        self.main_window = main_window
        self.study = study
        self.backend_facade = BackendFacade(study)

        self.chat_panel = None
        self.chat_dock = None

        self.chat_controller = ChatController()
        # Connect Chat Controller Signals
        self.chat_controller.processing_state_changed.connect(
            self.on_processing_state_changed,
        )
        self.preprocess_controller = study.get_controller("preprocess")  # M3.6
        self.agent_controller = None

        self.agent_initialized = False
        self._last_user_input: str | None = None
        self._runtime_unavailable_notice: str | None = None

        # M3.4 VRAM Monitoring — delegated to VRAMConflictChecker
        self.vram_checker = VRAMConflictChecker(
            self.main_window,
            lambda: self.agent_controller,
        )
        if hasattr(self.main_window, "visualization_panel"):
            self.main_window.visualization_panel.tabs.currentChanged.connect(
                self.vram_checker.on_viz_tab_changed,
            )

    def init_ui(self):
        """Initialize the chat dock widget and panel UI components.

        Creates the ``ChatPanel``, wires its signals, builds the dock
        title bar with float/settings/new-conversation buttons, and
        adds the dock to the main window's right area.
        """
        self.chat_panel = ChatPanel()

        # Connect UI to ChatController
        self.chat_panel.connect_controller(self.chat_controller)

        # Connect ChatPanel signals to self (for further dispatch)
        self.chat_panel.send_message.connect(self.handle_user_input)
        self.chat_panel.stop_generation.connect(self.stop_generation)
        self.chat_panel.model_changed.connect(self.set_model)
        self.chat_panel.execution_mode_changed.connect(self._on_execution_mode_changed)
        self.chat_panel.settings_requested.connect(self.open_settings_dialog)
        self.chat_panel.new_conversation_requested.connect(self.start_new_conversation)
        self.chat_panel.retry_requested.connect(self.retry_last_user_input)

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
        title_bar.setStyleSheet(Stylesheets.AGENT_TITLE_BAR)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(8, 2, 4, 2)
        title_layout.setSpacing(4)

        title_label = QLabel("XBrainLab")
        title_label.setStyleSheet(Stylesheets.AGENT_TITLE_LABEL)
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.retry_title_btn = QPushButton("↻")
        self.retry_title_btn.setFixedSize(20, 20)
        self.retry_title_btn.setToolTip("Send a request before retrying.")
        self.retry_title_btn.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        self.retry_title_btn.setEnabled(False)
        self.retry_title_btn.clicked.connect(self.retry_last_user_input)
        title_layout.addWidget(self.retry_title_btn)

        # New Conversation Button (+ icon)
        self.new_conv_title_btn = QPushButton("+")
        self.new_conv_title_btn.setFixedSize(20, 20)
        self.new_conv_title_btn.setToolTip("New Conversation")
        self.new_conv_title_btn.setStyleSheet(Stylesheets.AGENT_NEW_CONV_BTN)
        self.new_conv_title_btn.clicked.connect(self.start_new_conversation)
        title_layout.addWidget(self.new_conv_title_btn)

        # Options menu. Keep it to real, implemented actions.
        self.settings_btn = QPushButton("...")
        self.settings_btn.setFixedSize(26, 20)
        self.settings_btn.setToolTip("Options")
        self.settings_btn.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        self.settings_menu = QMenu(self.settings_btn)
        settings_action = QAction("Assistant settings", self.settings_btn)
        settings_action.triggered.connect(
            lambda _checked=False: self.open_settings_dialog()
        )
        self.settings_menu.addAction(settings_action)
        self.clear_conversation_title_action = QAction(
            "Clear conversation",
            self.settings_btn,
        )
        self.clear_conversation_title_action.setEnabled(False)
        self.clear_conversation_title_action.triggered.connect(
            lambda _checked=False: self.start_new_conversation()
        )
        self.settings_menu.addAction(self.clear_conversation_title_action)
        self.settings_btn.setMenu(self.settings_menu)
        title_layout.addWidget(self.settings_btn)

        # Float Button (❐ icon) - allows undocking
        self.float_btn = QPushButton("❐")
        self.float_btn.setFixedSize(20, 20)
        self.float_btn.setToolTip("Float / Dock")
        self.float_btn.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        self.float_btn.clicked.connect(self._toggle_float)
        title_layout.addWidget(self.float_btn)

        self.chat_dock.setTitleBarWidget(title_bar)
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

            config = self._load_runtime_config()
            if self._needs_local_runtime_first_run(config):
                choice = self._show_local_runtime_first_run_dialog(config)
                if not self._handle_local_runtime_first_run_choice(config, choice):
                    return
                config = self._load_runtime_config()

            ready, message = self._assistant_runtime_start_status(config)
            self.refresh_backend_status()
            if ready:
                self.start_system()
                self._runtime_unavailable_notice = None
            else:
                self._show_runtime_unavailable(message)
        elif self.chat_dock and self.chat_dock.isVisible():
            self.chat_dock.close()
        elif self.chat_dock:
            self.chat_dock.show()

    @staticmethod
    def _needs_local_runtime_first_run(config: LLMConfig) -> bool:
        """Return whether local runtime consent should be shown before startup."""
        if not hasattr(config, "model_name"):
            return False
        selection = LLMConfig.assistant_runtime_selection_from(config)
        return (
            selection.backend_mode == "local"
            and bool(getattr(config, "local_model_enabled", True))
            and not bool(
                getattr(config, "local_runtime_notice_acknowledged", False),
            )
        )

    def _show_local_runtime_first_run_dialog(self, config: LLMConfig) -> str:
        """Show the local-runtime consent dialog and return the selected choice."""
        dialog = LocalRuntimeFirstRunDialog(self.main_window, config)
        if dialog.exec():
            return dialog.choice
        return LocalRuntimeFirstRunDialog.LATER

    def _handle_local_runtime_first_run_choice(
        self,
        config: LLMConfig,
        choice: str,
    ) -> bool:
        """Apply a first-run runtime choice.

        Returns ``True`` when startup may continue immediately, otherwise the
        assistant dock remains open with a visible status message.
        """
        if choice in {
            LocalRuntimeFirstRunDialog.ENABLE,
            LocalRuntimeFirstRunDialog.USE_CACHE,
        }:
            config.local_model_enabled = True
            config.local_runtime_notice_acknowledged = True
            config.save_to_file()
            return True

        if choice == LocalRuntimeFirstRunDialog.DOWNLOAD:
            config.local_runtime_notice_acknowledged = True
            config.save_to_file()
            self.open_settings_dialog()
            updated_config = self._load_runtime_config()
            ready, message = self._assistant_runtime_start_status(updated_config)
            self.refresh_backend_status()
            if ready:
                return True
            self._show_runtime_unavailable(message)
            return False

        if choice == LocalRuntimeFirstRunDialog.DISABLE:
            config.local_model_enabled = False
            config.local_runtime_notice_acknowledged = True
            config.save_to_file()
            self.refresh_backend_status()
            self.chat_controller.add_agent_message(
                "Assistant is disabled. Open assistant settings when you want "
                "to enable it."
            )
            return False

        self.chat_controller.add_agent_message(
            "Assistant setup was deferred. Open assistant settings when you are "
            "ready to continue."
        )
        return False

    @staticmethod
    def _load_runtime_config() -> LLMConfig:
        """Load persisted assistant runtime config with a safe fallback."""
        return LLMConfig.load_from_file() or LLMConfig()

    @staticmethod
    def _assistant_runtime_start_status(config: LLMConfig) -> tuple[bool, str]:
        """Return whether the assistant runtime can start and why."""
        selection = LLMConfig.assistant_runtime_selection_from(config)

        if selection.backend_mode == "local":
            if not config.local_model_enabled:
                return (
                    False,
                    "Local assistant runtime is disabled. Enable it in assistant "
                    "settings when you want to use the local model.",
                )
            model_id, message = config.available_local_model_id(selection.model_id)
            return model_id is not None, message

        return (
            False,
            "Assistant runtime is local-only. Open assistant settings to select "
            "an approved local model.",
        )

    def _show_runtime_unavailable(self, message: str) -> None:
        """Surface assistant startup blockers in the chat panel."""
        if self._runtime_unavailable_notice == message:
            return

        self._runtime_unavailable_notice = message
        logger.info("Assistant runtime unavailable: %s", message)
        self.chat_controller.add_agent_message(
            self._runtime_unavailable_message(message),
        )

    @staticmethod
    def _runtime_unavailable_message(message: str) -> str:
        """Return a concise, user-facing assistant startup blocker."""
        reason = " ".join(str(message or "").split())
        lowered = reason.lower()
        if "disabled" in lowered:
            return (
                "**Assistant unavailable**: Assistant is disabled. Open assistant "
                "settings to enable it."
            )
        if "unavailable" in lowered or "not found" in lowered or "missing" in lowered:
            return (
                "**Assistant unavailable**: Required assistant files are unavailable. "
                "Open assistant settings to finish setup."
            )
        if reason:
            return f"**Assistant unavailable**: {reason}"
        return "**Assistant unavailable**: Open assistant settings to finish setup."

    def open_settings_dialog(self):
        """Open the model settings dialog and refresh the UI on accept."""
        # Pass self to allow the dialog to request model unloading/switching
        dialog = ModelSettingsDialog(self.main_window, agent_manager=self)
        if dialog.exec() and self.chat_panel:
            # Refresh UI based on new settings (e.g. enable/disable Local mode)
            self.chat_panel.update_model_menu()
            self.refresh_backend_status()

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
        if not self.agent_controller or not self.agent_controller.worker:
            return True

        worker = self.agent_controller.worker
        if not worker.engine:
            return True  # Not initialized

        # Check if active
        config = worker.engine.config
        current_mode = LLMConfig.assistant_runtime_selection_from(config).backend_mode

        # Heuristic: If we are in local mode, and the model name matches (roughly)
        # Detailed check: verify if the deleting model is the one loaded.
        # But for safety, if we are in local mode at all, we should switch out
        # to release locks if the user is deleting the *local* model.

        if current_mode == "local":
            logger.info("Blocking deletion of active local model: %s", model_name)
            QMessageBox.warning(
                self.main_window,
                "Local Model Active",
                "The AI assistant is currently using the local backend.\n"
                "Close the assistant or switch it away from Local before deleting "
                "this model.",
            )
            return False

        return True

    def start_system(self):
        """Lazily initialize the Agent Controller."""
        if self.agent_initialized:
            return

        if not self.chat_panel:
            return

        self.agent_controller = LLMController(self.study)

        # --- Connect LLMController Signals to ChatController ---

        # 1. Response Ready -> Add to ChatController
        # Note: 'sender' argument from LLMController is usually 'Assistant' or 'Tool'
        self.agent_controller.response_ready.connect(self._handle_agent_response)

        # 2. Status Updates -> Update UI Status (Legacy behavior, maybe simplify later)
        self.agent_controller.status_update.connect(self.on_agent_status_update)

        # 3. Error -> Add Error Message
        self.agent_controller.error_occurred.connect(self.handle_agent_error)

        # 4. Human Interaction
        self.agent_controller.request_user_interaction.connect(
            self.handle_user_interaction,
        )

        # 5. Generation Started -> Set Processing State AND Reset Bubble
        self.agent_controller.generation_started.connect(self._on_generation_started)

        # 6. Streaming: Chunk Received -> Forward to ChatPanel directly (for now)
        # In M0 plan we kept streaming in UI for simplicity.
        self.agent_controller.chunk_received.connect(self.chat_panel.on_chunk_received)

        # 7. Remove Content (Tool Calls) -> Forward to ChatPanel
        self.agent_controller.remove_content.connect(
            self.chat_panel.collapse_agent_message,
        )

        # 8. M3.1 Debug Mode: direct UI -> agent tool flow for offline testing.
        self.chat_panel.debug_tool_requested.connect(
            self.agent_controller.execute_debug_tool,
        )

        # 8. Finished Signal (Robust)
        self.agent_controller.processing_finished.connect(self.on_processing_finished)

        # 9. Execution Mode Sync
        self.agent_controller.execution_mode_changed.connect(
            self._sync_execution_mode_ui,
        )

        self.agent_controller.initialize()
        self.agent_initialized = True
        self.refresh_backend_status()

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

        if (
            self.agent_controller
            and getattr(
                self.agent_controller,
                "is_processing",
                False,
            )
            is True
        ):
            self.chat_controller.add_agent_message(
                "The assistant is still processing the previous request. "
                "Use Stop or wait for the current response before sending again.",
            )
            return

        # 1. Add to ChatController (Update History)
        self.chat_controller.add_user_message(text)
        self._last_user_input = text
        self._set_retry_available(True)

        # 2. Forward to Agent
        if self.agent_controller:
            self.agent_controller.handle_user_input(text)
        else:
            config = self._load_runtime_config()
            _ready, message = self._assistant_runtime_start_status(config)
            logger.info("Assistant unavailable on user request: %s", message)
            self.chat_controller.add_agent_message(
                self._runtime_unavailable_message(message),
            )

    def _handle_agent_response(self, sender: str, text: str) -> None:
        """Add assistant responses while keeping internal tool output out of chat."""
        if self._looks_like_internal_tool_output(sender, text):
            self._show_low_priority_notice(self._tool_output_notice(text))
            return
        self.chat_controller.add_agent_message(text)

    @staticmethod
    def _looks_like_internal_tool_output(sender: str, text: str) -> bool:
        """Return whether a response is an implementation detail, not chat copy."""
        sender_key = str(sender or "").strip().lower()
        if sender_key == "debug":
            return True

        normalized = " ".join(str(text or "").split()).lower()
        internal_markers = (
            "tool output:",
            "tool call:",
            "tool ",
            "request:",
            "```json",
            '{"',
            "[{",
            "applicationservice",
            "backendfacade",
        )
        if sender_key == "tool":
            return normalized.startswith(internal_markers)
        return normalized.startswith(internal_markers)

    @staticmethod
    def _tool_output_notice(text: str) -> str:
        """Translate internal tool diagnostics to a low-noise product notice."""
        normalized = " ".join(str(text or "").split()).lower()
        if "error" in normalized or "required" in normalized:
            return (
                "The assistant could not complete that action. Check the request "
                "and try again."
            )
        return "The assistant completed a background action."

    def retry_last_user_input(self):
        """Retry the most recent user request if the assistant is idle."""
        if self.chat_controller.is_processing:
            return
        if not self._last_user_input:
            self._show_low_priority_notice("Send a request before using Retry.")
            return
        self.handle_user_input(self._last_user_input)

    def stop_generation(self):
        """Stop the currently running LLM generation."""
        if self.agent_controller:
            self.agent_controller.stop_generation()
        self.chat_controller.set_processing(False)

    def set_model(self, model_name):
        """Switch the active LLM model and check for VRAM conflicts.

        Args:
            model_name: Runtime mode key or backend-specific identifier.

        """
        normalized_mode = LLMConfig.normalize_backend_mode(model_name, fallback="")
        if self.agent_controller:
            self.agent_controller.set_model(
                normalized_mode if normalized_mode else model_name
            )

        # VRAM Check on Mode Switch
        if normalized_mode == "local":
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
        """Synchronize retry/clear affordances across the dock controls."""
        if self.chat_panel and hasattr(self.chat_panel, "set_retry_available"):
            self.chat_panel.set_retry_available(available)
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
            self.retry_title_btn.setEnabled(enabled)
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
        if self.agent_controller:
            self.agent_controller.set_execution_mode(mode)

    def _sync_execution_mode_ui(self, mode: str):
        """Sync execution mode button text from controller to ChatPanel.

        Args:
            mode: ``'single'`` or ``'multi'``.

        """
        _ = mode
        if self.chat_panel:
            self.chat_panel.mode_btn.setText("")

    def start_new_conversation(self):
        """Clear the chat UI and reset the agent conversation state."""
        logger.info("Starting new conversation - clearing UI and resetting agent state")

        # 1. Clear UI / History
        self.chat_controller.clear_conversation()
        self._last_user_input = None
        self._set_retry_available(False)
        if self.chat_panel and hasattr(self.chat_panel, "show_notice"):
            self.chat_panel.show_notice("")

        # 2. Reset Agent State
        if self.agent_controller:
            self.agent_controller.reset_conversation()
            logger.info("Agent conversation state reset successfully")

        # 3. Do not add greeting, keep it empty as requested
        # self.chat_controller.add_agent_message("Conversation cleared.")
        self.refresh_backend_status()

    # Signal to notify Main Window (or other listeners) about status updates
    status_message_received = pyqtSignal(str)

    def _show_low_priority_notice(self, message: str) -> None:
        """Surface notices in the dock footer/status bar without polluting chat."""
        if self.chat_panel and hasattr(self.chat_panel, "show_notice"):
            self.chat_panel.show_notice(message)
        try:
            self.status_message_received.emit(message)
        except RuntimeError:
            logger.debug("Status notice could not be emitted: %s", message)

    def _on_generation_started(self):
        """Handle the start of a new LLM response generation.

        Resets the current agent bubble reference and sets processing
        state to ``True``.
        """
        # Reset bubble reference so a new one will be created for this turn
        if self.chat_panel:
            self.chat_panel.current_agent_bubble = None
        self.chat_controller.set_processing(True)

    def on_processing_finished(self):
        """Handle the end of LLM processing by resetting state."""
        self.chat_controller.set_processing(False)
        self.refresh_backend_status()

    def on_agent_status_update(self, msg):
        """Forward agent status messages and handle error states.

        Args:
            msg: The status message string from the agent.

        """
        logger.debug("Assistant status update: %s", msg)
        if "Error" in msg or "Stopping" in msg:
            self.chat_controller.set_processing(False)
            if self.chat_panel and hasattr(self.chat_panel, "show_notice"):
                self.chat_panel.show_notice(
                    "Assistant needs attention · Check the conversation",
                )

    def handle_agent_error(self, error_msg):
        """Handle an agent error by resetting state and showing the error.

        Args:
            error_msg: The error message string.

        """
        self.chat_controller.set_processing(False)
        self.chat_controller.add_agent_message(
            self._user_facing_error_message(error_msg),
        )
        logger.error("Agent Error: %s", error_msg)
        self.refresh_backend_status()

    @classmethod
    def _user_facing_error_message(cls, error_msg: str) -> str:
        """Return a concise error message without tool/debug internals."""
        if cls._looks_like_internal_tool_output("", error_msg):
            return (
                "**Assistant needs input**: The requested action needs more "
                "information. Check the request and try again."
            )
        reason = " ".join(str(error_msg or "").split())
        if not reason:
            return "**Assistant needs input**: Try again with a little more detail."
        return f"**Error**: {reason}"

    def refresh_backend_status(self):
        """Refresh the compact backend/model status shown in the chat panel."""
        if not self.chat_panel or not hasattr(self.chat_panel, "set_status_summary"):
            return

        try:
            state = self.backend_facade.get_state()
            capabilities = self.backend_facade.get_capabilities()
            enabled = self._product_next_steps(state, capabilities)
            stage = workflow_stage_label(state)
            model_config = LLMConfig.load_from_file() or LLMConfig()
            selection = LLMConfig.assistant_runtime_selection_from(model_config)
            model_ready = model_config.local_backend_ready(selection.model_id)
            model_status = "Ready" if model_ready else "Setup needed"

            train_capability = capabilities.get("train")
            tooltip_lines = [
                f"Workflow stage: {stage}",
                "Options hold setup details.",
                "Suggested next actions: "
                + (", ".join(command_labels(enabled)) if enabled else "none"),
            ]
            if train_capability.reasons:
                tooltip_lines.append(
                    "Train blocked: " + "; ".join(train_capability.reasons),
                )
            if state.last_error:
                tooltip_lines.append(f"Last workflow error: {state.last_error.message}")

            blocked_reason = None
            if train_capability.reasons:
                blocked_reason = "; ".join(train_capability.reasons)

            if hasattr(self.chat_panel, "set_product_status"):
                self.chat_panel.set_product_status(
                    stage=stage,
                    model_status=model_status,
                    available_commands=enabled,
                    tooltip="\n".join(tooltip_lines),
                    blocked_reason=blocked_reason,
                )
            else:
                self.chat_panel.set_status_summary(stage, "\n".join(tooltip_lines))

            self.status_message_received.emit(
                self._workflow_footer_hint(stage, enabled, blocked_reason),
            )
        except Exception as exc:
            logger.debug("Failed to refresh backend status", exc_info=True)
            self.chat_panel.set_status_summary(
                "Workflow status unavailable",
                f"Status refresh failed: {exc}",
            )
            self.status_message_received.emit(
                "Workflow status unavailable · Try again",
            )

    @staticmethod
    def _workflow_footer_hint(
        stage: str,
        command_names: list[str],
        blocked_reason: str | None = None,
    ) -> str:
        """Return a user-facing status-bar hint with no runtime diagnostics."""
        labels = command_labels(command_names)
        if labels:
            if stage == "No data loaded" and labels[0] == "Scan data source":
                return "No EEG data open · Scan a data source to begin"
            return f"{stage} · {labels[0]}"
        if blocked_reason:
            return f"{stage} · Ask what is blocking training"
        if stage == "No data loaded":
            return "No EEG data open · Import files to begin"
        return f"{stage} · Ask what is ready"

    @staticmethod
    def _product_next_steps(state, capabilities) -> list[str]:
        """Return user-facing next-step command IDs, not every enabled command."""
        active_dataset = state.active_dataset
        training = state.training
        evaluation = state.evaluation

        candidates: list[str]
        if evaluation.finished_runs:
            candidates = ["evaluate", "visualize", "saliency"]
        elif active_dataset.has_datasets:
            if training.has_model and training.has_training_option:
                candidates = ["train"]
            else:
                candidates = ["configure_training"]
        elif active_dataset.has_epoch_data:
            candidates = ["generate_dataset"]
        elif active_dataset.has_preprocessed_data:
            candidates = ["create_epoch"]
        elif active_dataset.has_raw_data:
            candidates = ["preprocess"]
        else:
            candidates = ["scan_source"]

        return [
            command_name
            for command_name in candidates
            if capabilities.get(command_name).enabled
        ]

    def close(self):
        """Clean up the agent controller resources."""
        if self.agent_controller:
            self.agent_controller.close()

    def handle_user_interaction(self, command, params):
        """Dispatch human-in-the-loop interaction requests.

        Args:
            command: The interaction command (e.g., ``"confirm_montage"``,
                ``"switch_panel"``, ``"confirm_action"``).
            params: Dictionary of parameters for the command.

        """
        if command == "confirm_montage":
            self.open_montage_picker_dialog(params)
        elif command == "switch_panel":
            self.switch_panel(params)
        elif command == "confirm_action":
            self._show_action_confirmation(params)

    def switch_panel(self, params):
        """Switch the main window to a specified panel and optional sub-view.

        Args:
            params: Dictionary with ``"panel"`` (panel name) and optional
                ``"view_mode"`` (sub-tab identifier).

        """
        panel_name = params.get("panel", "").lower()
        view_mode = params.get("view_mode")
        target_index = -1

        if "dataset" in panel_name:
            target_index = PANEL_DATASET
        elif "preprocess" in panel_name:
            target_index = PANEL_PREPROCESS
        elif "training" in panel_name:
            target_index = PANEL_TRAINING
        elif "eval" in panel_name:
            target_index = PANEL_EVALUATION
        elif "visual" in panel_name:
            target_index = PANEL_VISUALIZATION

        if target_index >= 0:
            self.main_window.switch_page(target_index)

            # Handle sub-view switching
            if view_mode:
                self._switch_sub_view(target_index, view_mode)

            sb = self.main_window.statusBar()
            if sb:
                sb.showMessage(
                    f"Switched to {panel_name} "
                    f"(View: {view_mode if view_mode else 'Default'})",
                )
        else:
            sb = self.main_window.statusBar()
            if sb:
                sb.showMessage(f"Error: Unknown panel '{panel_name}'")
            # Notify user via chat
            self.chat_controller.add_agent_message(
                f"Error: Could not switch to {panel_name}",
            )

    def _show_action_confirmation(self, params):
        """Show a confirmation dialog for dangerous tool actions.

        Presents a ``QMessageBox`` asking the user to approve or reject
        an irreversible operation such as clearing data or starting
        training.

        Args:
            params: Dictionary with ``"tool_name"``, ``"params"``, and
                ``"description"`` keys from the controller.

        """
        tool_name = params.get("tool_name", "unknown")
        action_label = tool_action_label(tool_name)
        description = params.get("description", "")
        tool_params = params.get("params", {})

        detail = ""
        if tool_params:
            detail = "\n".join(
                f"  {str(k).replace('_', ' ').title()}: {v}"
                for k, v in tool_params.items()
            )

        msg = QMessageBox(self.main_window)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Confirm Action")
        msg.setText(
            "The assistant wants to run an action that may change your workspace:\n\n"
            f"  Action: {action_label}\n"
            f"  Details: {description or action_label}"
        )
        if detail:
            msg.setDetailedText(detail)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)

        result = msg.exec()
        approved = result == QMessageBox.StandardButton.Yes

        if approved:
            self.chat_controller.add_agent_message(
                f"Confirmed: {action_label}.",
            )
        else:
            self.chat_controller.add_agent_message(
                f"Cancelled: {action_label}.",
            )

        if self.agent_controller:
            self.agent_controller.on_user_confirmed(approved)

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
                    view_mode,
                    target_tab_index,
                )

    def open_montage_picker_dialog(self, params):
        """Open the montage picker dialog for channel configuration.

        Presents a ``PickMontageDialog`` pre-populated with an optional
        montage suggestion from the agent. Real Study-backed paths use the
        ApplicationService command layer; legacy mock paths may fall back to
        the preprocess controller for test compatibility.

        Args:
            params: Dictionary with optional ``"montage_name"`` key.

        """
        montage_name = params.get("montage_name")  # Pre-selected montage from Agent

        capability = get_command_capability(self, CommandName.APPLY_MONTAGE)
        if capability is not None and not capability.enabled:
            sb = self.main_window.statusBar()
            if sb:
                sb.showMessage(
                    blocked_reason(
                        capability,
                        "Create epochs before applying a montage.",
                    ),
                )
            return

        chs = self._montage_channel_names_for_dialog()
        if chs is None:
            return
        if not chs:
            sb = self.main_window.statusBar()
            if sb:
                sb.showMessage(
                    "No epoch channel names are available for montage setup."
                )
            return

        dialog = PickMontageDialog(self.main_window, chs, default_montage=montage_name)

        if dialog.exec():
            chs, positions = dialog.get_result()
            if chs and positions is not None:
                try:
                    normalized_positions = normalize_montage_positions(chs, positions)
                except Exception as exc:
                    sb = self.main_window.statusBar()
                    if sb:
                        sb.showMessage(f"Montage setup failed: {exc}")
                    return

                result = execute_application_command(
                    self,
                    ApplyMontageCommand(
                        channels=list(chs),
                        positions=normalized_positions,
                        montage_name=montage_name,
                    ),
                )
                if result is None:
                    try:
                        run_legacy_controller_fallback(
                            self,
                            lambda: self.preprocess_controller.apply_montage(
                                chs,
                                positions,
                            ),
                        )
                    except LegacyControllerFallbackUnavailableError as exc:
                        sb = self.main_window.statusBar()
                        if sb:
                            sb.showMessage(f"Montage setup blocked: {exc}")
                        self.handle_user_input("Montage Selection Failed.")
                        return
                elif result.failed:
                    sb = self.main_window.statusBar()
                    if sb:
                        sb.showMessage(f"Error: {result.message}")
                    self.handle_user_input("Montage Selection Failed.")
                    return
                self.chat_controller.add_agent_message("Montage Confirmed.")

                # If in Debug Mode, do NOT trigger LLM generation loop
                # (avoids double tool execution)
                is_debug = False
                if (
                    self.chat_panel
                    and hasattr(self.chat_panel, "debug_mode")
                    and self.chat_panel.debug_mode
                ):
                    is_debug = True

                if is_debug:
                    # Just add to history visually, don't trigger Agent
                    self.chat_controller.add_user_message("Montage Confirmed.")
                else:
                    # Normal mode: Tell Agent user confirmed, enabling it to continue
                    self.handle_user_input("Montage Confirmed.")
            else:
                sb = self.main_window.statusBar()
                if sb:
                    sb.showMessage("Error: No valid montage configuration")
                self.handle_user_input("Montage Selection Failed.")
        else:
            self.chat_controller.add_agent_message("Operation Cancelled.")
            self.handle_user_input("Montage Selection Cancelled by User.")

    def _montage_channel_names_for_dialog(self) -> list[str] | None:
        """Return montage channel names through the command spine when available."""
        result = execute_application_command(
            self,
            QueryStateCommand(query="state"),
            refresh=False,
        )
        if result is None:
            try:
                return run_legacy_controller_fallback(
                    self,
                    self._legacy_montage_channel_names,
                )
            except LegacyControllerFallbackUnavailableError as exc:
                sb = self.main_window.statusBar()
                if sb:
                    sb.showMessage(f"Montage setup blocked: {exc}")
                self.handle_user_input("Montage Selection Failed.")
                return None
        if result.failed:
            sb = self.main_window.statusBar()
            if sb:
                sb.showMessage(f"Montage setup blocked: {result.message}")
            self.handle_user_input("Montage Selection Failed.")
            return None

        diagnostics = getattr(result, "diagnostics", {}) or {}
        state = diagnostics.get("state")
        epoch = state.get("epoch") if isinstance(state, dict) else {}
        channel_names = epoch.get("channel_names") if isinstance(epoch, dict) else None
        if not isinstance(channel_names, list):
            return []
        return [str(name) for name in channel_names]

    def _legacy_montage_channel_names(self) -> list[str]:
        """Read montage channel names only for mock / legacy UI contexts."""
        epoch_data = self.study.epoch_data
        if not epoch_data:
            return []

        getter = getattr(epoch_data, "get_channel_names", None)
        if callable(getter):
            try:
                names = getter()
                if isinstance(names, list | tuple):
                    return [str(name) for name in names]
            except Exception:
                logger.debug("Legacy montage channel-name getter failed", exc_info=True)

        try:
            mne_obj = epoch_data.get_mne()
        except Exception:
            return []

        names = getattr(mne_obj, "ch_names", None)
        if isinstance(names, list | tuple):
            return [str(name) for name in names]

        info = getattr(mne_obj, "info", None)
        if isinstance(info, dict):
            info_names = info.get("ch_names")
            if isinstance(info_names, list | tuple):
                return [str(name) for name in info_names]
        return []
