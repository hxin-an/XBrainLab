from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import QDockWidget, QMessageBox

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.ui.chat import ChatPanel
from XBrainLab.ui.dialogs.visualization import PickMontageDialog


class AgentManager(QObject):
    """
    Manages the lifecycle and UI integration of the AI Agent System.
    Decouples Agent logic from the MainWindow.
    """

    def __init__(self, main_window, study):
        super().__init__(main_window)
        self.main_window = main_window
        self.study = study

        self.chat_panel = None
        self.chat_dock = None
        self.agent_controller = None
        self.agent_initialized = False

    def init_ui(self):
        """Initialize Dock and Panel UI components (but not the heavy Controller)."""
        self.chat_panel = ChatPanel()
        self.chat_dock = QDockWidget("AI Assistant", self.main_window)
        self.chat_dock.setWidget(self.chat_panel)
        self.chat_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.main_window.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock
        )

        self.chat_dock.visibilityChanged.connect(self.update_ai_btn_state)
        self.chat_dock.hide()

    def update_ai_btn_state(self, visible):
        if hasattr(self.main_window, "ai_btn"):
            self.main_window.ai_btn.blockSignals(True)
            self.main_window.ai_btn.setChecked(visible)
            self.main_window.ai_btn.blockSignals(False)

    def toggle(self):
        """Toggle the visibility of the Agent Dock, initializing if needed."""
        if not self.agent_initialized:
            # Show Warning
            reply = QMessageBox.warning(
                self.main_window,
                "Activate AI Assistant",
                "You are about to activate the AI Assistant.\n\n"
                "This feature uses an LLM (Large Language Model) which requires "
                "significant system resources (GPU/VRAM).\n"
                "It may slow down other operations on lower-end systems.\n"
                "Do you want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.start_system()
                if self.chat_dock:
                    self.chat_dock.show()
                if hasattr(self.main_window, "ai_btn"):
                    self.main_window.ai_btn.setChecked(True)
            else:
                if hasattr(self.main_window, "ai_btn"):
                    self.main_window.ai_btn.setChecked(False)
                return
        elif self.chat_dock and self.chat_dock.isVisible():
            self.chat_dock.close()
        elif self.chat_dock:
            self.chat_dock.show()

    def start_system(self):
        """Lazily initialize the Agent Controller."""
        if self.agent_initialized:
            return

        if not self.chat_panel:
            return

        self.agent_controller = LLMController(self.study)

        # Connect Signals
        self.chat_panel.send_message.connect(self.handle_user_input)

        self.agent_controller.response_ready.connect(
            lambda sender, text: self.chat_panel.append_message(sender, text)
            if self.chat_panel
            else None
        )
        self.agent_controller.chunk_received.connect(self.chat_panel.on_chunk_received)
        self.agent_controller.status_update.connect(self.on_agent_status_update)
        self.agent_controller.error_occurred.connect(self.handle_agent_error)
        self.agent_controller.request_user_interaction.connect(
            self.handle_user_interaction
        )
        self.agent_controller.generation_started.connect(
            lambda: (
                self.chat_panel.set_processing_state(True) if self.chat_panel else None,
                self.chat_panel.start_agent_message() if self.chat_panel else None,
            )
        )
        self.agent_controller.remove_content.connect(
            self.chat_panel.collapse_agent_message
        )

        # New Controls
        self.chat_panel.stop_generation.connect(self.agent_controller.stop_generation)
        self.chat_panel.model_changed.connect(self.agent_controller.set_model)

        self.agent_controller.initialize()
        self.agent_initialized = True

    def handle_user_input(self, text):
        if self.agent_controller:
            self.agent_controller.handle_user_input(text)

    def on_agent_status_update(self, msg):
        sb = self.main_window.statusBar()
        if sb:
            sb.showMessage(msg)
        if ("Ready" in msg or "Error" in msg or "Stopping" in msg) and self.chat_panel:
            self.chat_panel.set_processing_state(False)

    def handle_agent_error(self, error_msg):
        if self.chat_panel:
            self.chat_panel.set_status("Error")
            self.chat_panel.add_message(f"??Error: {error_msg}", is_user=False)
        logger.error(f"Agent Error: {error_msg}")

    def close(self):
        if self.agent_controller:
            self.agent_controller.close()

    def handle_user_interaction(self, command, params):
        """Dispatcher for Human-in-the-loop requests."""
        if command == "confirm_montage":
            self.open_montage_picker_dialog(params)
        elif command == "switch_panel":
            self.switch_panel(params)

    def switch_panel(self, params):
        panel_name = params.get("panel", "").lower()
        target_index = -1

        # Access MainWindow's nav buttons/stack
        # This assumes MainWindow structure (nav_btns, stack)

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

            sb = self.main_window.statusBar()
            if sb:
                sb.showMessage(f"Switched to {panel_name}")
        else:
            sb = self.main_window.statusBar()
            if sb:
                sb.showMessage(f"Error: Unknown panel '{panel_name}'")
            self.handle_user_input(f"Error: Could not switch to {panel_name}")

    def open_montage_picker_dialog(self, params):
        if not self.study.epoch_data:
            sb = self.main_window.statusBar()
            if sb:
                sb.showMessage("Error: No epoch data available for montage.")
            return

        chs = self.study.epoch_data.get_mne().info["ch_names"]
        dialog = PickMontageDialog(self.main_window, chs)

        if dialog.exec():
            chs, positions = dialog.get_result()
            if chs and positions is not None:
                self.study.set_channels(chs, positions)
                if self.chat_panel:
                    self.chat_panel.add_message("Montage Confirmed.", is_user=True)
                self.handle_user_input("Montage Confirmed.")
            else:
                sb = self.main_window.statusBar()
                if sb:
                    sb.showMessage("Error: No valid montage configuration")
                self.handle_user_input("Montage Selection Failed.")
        else:
            if self.chat_panel:
                self.chat_panel.add_message("Operation Cancelled.", is_user=True)
            self.handle_user_input("Montage Selection Cancelled by User.")
