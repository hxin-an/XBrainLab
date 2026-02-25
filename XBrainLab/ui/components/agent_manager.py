"""Agent Manager for AI assistant lifecycle and UI integration.

Orchestrates the ChatController, LLMController, and ChatPanel dock widget,
handling initialization, user interaction, model switching, and VRAM checks.
"""

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from XBrainLab.backend.controller.chat_controller import ChatController
from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.ui.chat.panel import ChatPanel
from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog
from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import PickMontageDialog
from XBrainLab.ui.styles.stylesheets import Stylesheets

VIZ_TAB_3D_PLOT = 3
"""Index of the 3D Plot tab in the visualization panel."""


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

        # M3.4 VRAM Monitoring
        # Connect to Visualization Panel signals if available
        if hasattr(self.main_window, "visualization_panel"):
            self.main_window.visualization_panel.tabs.currentChanged.connect(
                self.on_viz_tab_changed,
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
        self.chat_panel.new_conversation_requested.connect(self.start_new_conversation)

        self.chat_dock = QDockWidget("AI Assistant", self.main_window)
        self.chat_dock.setWidget(self.chat_panel)
        self.chat_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea,
        )

        # Custom Title Bar with Float + New Conversation Buttons
        title_bar = QWidget()
        title_bar.setStyleSheet(Stylesheets.AGENT_TITLE_BAR)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(8, 2, 4, 2)
        title_layout.setSpacing(4)

        title_label = QLabel("AI Assistant")
        title_label.setStyleSheet(Stylesheets.AGENT_TITLE_LABEL)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        # New Conversation Button (+ icon)
        self.new_conv_title_btn = QPushButton("+")
        self.new_conv_title_btn.setFixedSize(20, 20)
        self.new_conv_title_btn.setToolTip("New Conversation")
        self.new_conv_title_btn.setStyleSheet(Stylesheets.AGENT_NEW_CONV_BTN)
        self.new_conv_title_btn.clicked.connect(self.start_new_conversation)
        title_layout.addWidget(self.new_conv_title_btn)

        # Settings Button (≡ icon)
        self.settings_btn = QPushButton("≡")
        self.settings_btn.setFixedSize(20, 20)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        title_layout.addWidget(self.settings_btn)

        # Float Button (❐ icon) - allows undocking
        self.float_btn = QPushButton("❐")
        self.float_btn.setFixedSize(20, 20)
        self.float_btn.setToolTip("Float / Dock")
        self.float_btn.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        self.float_btn.clicked.connect(self._toggle_float)
        title_layout.addWidget(self.float_btn)

        self.chat_dock.setTitleBarWidget(title_bar)

        self.main_window.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.chat_dock,
        )

        self.chat_dock.visibilityChanged.connect(self.update_ai_btn_state)
        self.chat_dock.hide()

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
            self.chat_dock.setFloating(not self.chat_dock.isFloating())

    def toggle(self):
        """Toggle the Agent dock visibility, initializing on first open.

        On first invocation, shows the ``ModelSettingsDialog`` to
        configure the LLM backend before starting the agent system.
        """
        if not self.agent_initialized:
            # Show Model Settings Dialog instead of Warning
            dialog = ModelSettingsDialog(self.main_window)

            if dialog.exec():
                # User set up config and clicked Activate
                self.start_system()
                if self.chat_dock:
                    self.chat_dock.show()
                if hasattr(self.main_window, "ai_btn"):
                    self.main_window.ai_btn.setChecked(True)
            else:
                # User cancelled
                if hasattr(self.main_window, "ai_btn"):
                    self.main_window.ai_btn.setChecked(False)
                return
        elif self.chat_dock and self.chat_dock.isVisible():
            self.chat_dock.close()
        elif self.chat_dock:
            self.chat_dock.show()

    def open_settings_dialog(self):
        """Open the model settings dialog and refresh the UI on accept."""
        # Pass self to allow the dialog to request model unloading/switching
        dialog = ModelSettingsDialog(self.main_window, agent_manager=self)
        if dialog.exec() and self.chat_panel:
            # Refresh UI based on new settings (e.g. enable/disable Local mode)
            self.chat_panel.update_model_menu()

    def prepare_model_deletion(self, model_name: str):
        """Prepare for model file deletion by switching away if active.

        Called by ``ModelSettingsDialog`` before deleting a model. If the
        model is currently loaded in local mode, switches to Gemini.

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
        current_mode = config.active_mode  # "local", "gemini"

        # Heuristic: If we are in local mode, and the model name matches (roughly)
        # Detailed check: verify if the deleting model is the one loaded.
        # But for safety, if we are in local mode at all, we should switch out
        # to release locks if the user is deleting the *local* model.

        if current_mode == "local":
            logger.info("User deleting model while active. Switching to Gemini.")
            # Switch to Gemini (or Dummy if Gemini not avail? Assuming Gemini is backup)
            # Use set_model to trigger reinit via controller
            self.agent_controller.set_model("Gemini")
            # Wait for switch? it's async signals.
            # But the interaction is modal dialog.
            # The switch might take a moment.
            # We assume effectively immediate config change + backend switch
            # starts lock release.
            return True

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
        self.agent_controller.response_ready.connect(
            lambda sender, text: self.chat_controller.add_agent_message(text),
        )

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

        # 8. M3.1 Debug Mode: Handled by MainWindow (offline support)
        # self.chat_panel.debug_tool_requested.connect(
        #     self.agent_controller.execute_debug_tool
        # )

        # 8. Finished Signal (Robust)
        self.agent_controller.processing_finished.connect(self.on_processing_finished)

        self.agent_controller.initialize()
        self.agent_initialized = True

    def handle_user_input(self, text):
        """Handle text input from ChatPanel.

        Adds the message to ``ChatController`` history and forwards it
        to the ``LLMController`` for processing.

        Args:
            text: The user's message text.

        """
        # 1. Add to ChatController (Update History)
        self.chat_controller.add_user_message(text)

        # 2. Forward to Agent
        if self.agent_controller:
            self.agent_controller.handle_user_input(text)

    def stop_generation(self):
        """Stop the currently running LLM generation."""
        if self.agent_controller:
            self.agent_controller.stop_generation()
        self.chat_controller.set_processing(False)

    def set_model(self, model_name):
        """Switch the active LLM model and check for VRAM conflicts.

        Args:
            model_name: The model name to switch to (e.g., ``"Gemini"``,
                ``"Local"``).

        """
        if self.agent_controller:
            self.agent_controller.set_model(model_name)

        # VRAM Check on Mode Switch
        if "local" in model_name.lower():
            self.check_vram_conflict(switching_to_local=True)

    def on_viz_tab_changed(self, index):
        """Monitor visualization tab changes for VRAM conflict.

        Args:
            index: The newly selected tab index.

        """
        # 3D Plot tab triggers VRAM check
        if index == VIZ_TAB_3D_PLOT:
            self.check_vram_conflict(switching_to_3d=True)

    def check_vram_conflict(self, switching_to_local=False, switching_to_3d=False):
        """Check for VRAM conflict between local LLM and 3D visualization.

        Warns the user if both the local model and 3D visualization are
        active simultaneously, which may cause memory exhaustion.

        Args:
            switching_to_local: Whether the user is switching to local
                model mode.
            switching_to_3d: Whether the user is switching to the 3D
                visualization tab.

        """
        # 1. Check Agent Mode
        # If we are switching TO local, we assume local.
        # Otherwise check current config.
        is_local = False
        if switching_to_local:
            is_local = True
        elif self.agent_controller and self.agent_controller.worker:
            # Use cached config from running agent if available
            # This avoids blocking IO from LLMConfig.load_from_file()
            try:
                # Check active_backend or config directly
                # Accessing worker.engine.config is safe as it's an object reference
                if self.agent_controller.worker.engine:
                    mode = self.agent_controller.worker.engine.config.active_mode
                    if mode == "local":
                        is_local = True
            except Exception:
                logger.debug(
                    "Engine not yet initialized, skipping local mode check",
                    exc_info=True,
                )

        if not is_local:
            return

        # 2. Check Visualization State
        # If we are switching TO 3D, assume 3D.
        # Otherwise check current tab.
        is_3d_active = False
        viz_panel = self.main_window.visualization_panel
        if switching_to_3d or (
            viz_panel.tabs.currentIndex() == VIZ_TAB_3D_PLOT
            and not viz_panel.isHidden()
            and self.main_window.stack.currentIndex() == 4
        ):
            is_3d_active = True

        if is_local and is_3d_active:
            QMessageBox.warning(
                self.main_window,
                "VRAM Warning",
                "This requires significant VRAM (Video Memory). "
                "If you experience crashes or lag, please close the 3D view "
                "or switch to Gemini mode.",
            )

    def on_processing_state_changed(self, is_processing):
        """Forward processing state changes to the ChatPanel.

        Args:
            is_processing: Whether the agent is currently generating.

        """
        if self.chat_panel:
            self.chat_panel.set_processing_state(is_processing)

    def start_new_conversation(self):
        """Clear the chat UI and reset the agent conversation state."""
        logger.info("Starting new conversation - clearing UI and resetting agent state")

        # 1. Clear UI / History
        self.chat_controller.clear_conversation()

        # 2. Reset Agent State
        if self.agent_controller and hasattr(
            self.agent_controller,
            "reset_conversation",
        ):
            self.agent_controller.reset_conversation()
            logger.info("Agent conversation state reset successfully")
        elif self.agent_controller:
            # Fallback if method missing (though we plan to add it)
            logger.warning("reset_conversation method not found on agent_controller")

        # 3. Do not add greeting, keep it empty as requested
        # self.chat_controller.add_agent_message("Conversation cleared.")

    # Signal to notify Main Window (or other listeners) about status updates
    status_message_received = pyqtSignal(str)

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

    def on_agent_status_update(self, msg):
        """Forward agent status messages and handle error states.

        Args:
            msg: The status message string from the agent.

        """
        self.status_message_received.emit(msg)

        # Note: We now rely on processing_finished signal for state handling!
        # Legacy checks can be kept for fallback or removed.
        if "Error" in msg or "Stopping" in msg:
            self.chat_controller.set_processing(False)

    def handle_agent_error(self, error_msg):
        """Handle an agent error by resetting state and showing the error.

        Args:
            error_msg: The error message string.

        """
        self.chat_controller.set_processing(False)
        self.chat_controller.add_agent_message(f"?? **Error**: {error_msg}")
        logger.error("Agent Error: %s", error_msg)

    def close(self):
        """Clean up the agent controller resources."""
        if self.agent_controller:
            self.agent_controller.close()

    def handle_user_interaction(self, command, params):
        """Dispatch human-in-the-loop interaction requests.

        Args:
            command: The interaction command (e.g., ``"confirm_montage"``,
                ``"switch_panel"``).
            params: Dictionary of parameters for the command.

        """
        if command == "confirm_montage":
            self.open_montage_picker_dialog(params)
        elif command == "switch_panel":
            self.switch_panel(params)

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
            target_index = 0
        elif "preprocess" in panel_name:
            target_index = 1
        elif "training" in panel_name:
            target_index = 2
        elif "eval" in panel_name:
            target_index = 3
        elif "visual" in panel_name:
            target_index = 4

        if target_index >= 0:
            self.main_window.stack.setCurrentIndex(target_index)
            if target_index < len(self.main_window.nav_btns):
                self.main_window.nav_btns[target_index].setChecked(True)

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
                "3d_plot": 3,
            },
            # Future: Add Preprocess or Evaluation panels if they have tabs
        }

        if panel_index in view_map and view_mode in view_map[panel_index]:
            target_panel = self.main_window.stack.widget(panel_index)
            target_tab_index = view_map[panel_index][view_mode]

            if hasattr(target_panel, "tabs"):
                target_panel.tabs.setCurrentIndex(target_tab_index)
                logger.info(
                    f"Switched sub-view to {view_mode} (Tab {target_tab_index})",
                )

    def open_montage_picker_dialog(self, params):
        """Open the montage picker dialog for channel configuration.

        Presents a ``PickMontageDialog`` pre-populated with an optional
        montage suggestion from the agent. On acceptance, applies the
        montage via the preprocess controller.

        Args:
            params: Dictionary with optional ``"montage_name"`` key.

        """
        montage_name = params.get("montage_name")  # Pre-selected montage from Agent

        if not self.study.epoch_data:
            sb = self.main_window.statusBar()
            if sb:
                sb.showMessage("Error: No epoch data available for montage.")
            return

        chs = self.study.epoch_data.get_mne().info["ch_names"]
        dialog = PickMontageDialog(self.main_window, chs, default_montage=montage_name)

        if dialog.exec():
            chs, positions = dialog.get_result()
            if chs and positions is not None:
                # M3.6 Refactor: Use PreprocessController instead of direct study access
                self.preprocess_controller.apply_montage(chs, positions)
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
