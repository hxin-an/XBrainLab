import sys
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.ui.chat_panel import ChatPanel
from XBrainLab.ui.dashboard_panel.dataset import DatasetPanel
from XBrainLab.ui.dashboard_panel.preprocess import PreprocessPanel
from XBrainLab.ui.evaluation.panel import EvaluationPanel
from XBrainLab.ui.training.panel import TrainingPanel
from XBrainLab.ui.visualization.montage_picker import PickMontageWindow
from XBrainLab.ui.visualization.panel import VisualizationPanel


class MainWindow(QMainWindow):
    """
    The main application window for XBrainLab (PyQt6 version).

    This window manages the overall layout, including:
    - Top Navigation Bar: For switching between main panels (Dataset, Preprocess, \
Training, etc.).
    - Stacked Widget: Holds the content of each panel.
    - Dock Widgets: For the AI Assistant and Data Info panel.
    - Agent System: Initializes and manages the background AI agent thread.
    """

    # Signals to control the worker
    sig_init_agent = pyqtSignal()
    sig_generate = pyqtSignal(str, str)

    def __init__(self, study):
        super().__init__()
        self.study = study
        self.setWindowTitle("XBrainLab")
        self.resize(1280, 800)

        self.agent_initialized = False  # Flag for lazy loading

        # Apply VS Code Dark Theme (Adjusted for Top Bar)
        self.apply_vscode_theme()

        # Central Widget & Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Vertical Layout: Top Bar | Main Content
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Top Navigation Bar
        self.top_bar = QFrame()
        self.top_bar.setObjectName("TopBar")
        self.top_bar.setFixedHeight(50)
        self.top_bar_layout = QHBoxLayout(self.top_bar)
        self.top_bar_layout.setContentsMargins(10, 0, 10, 0)
        self.top_bar_layout.setSpacing(10)

        # Navigation Buttons
        self.nav_btns = []
        self.add_nav_btn("Dataset", 0, "Dataset")
        self.add_nav_btn("Preprocess", 1, "Preprocess")
        self.add_nav_btn("Training", 2, "Training")
        self.add_nav_btn("Evaluation", 3, "Evaluation")
        self.add_nav_btn("Visualization", 4, "Visualization")

        self.top_bar_layout.addStretch()

        # AI Toggle Button
        self.ai_btn = QPushButton("AI Assistant")
        self.ai_btn.setCheckable(True)
        self.ai_btn.setChecked(False)  # Default Off
        self.ai_btn.clicked.connect(self.toggle_ai_dock)
        self.ai_btn.setObjectName("ActionBtn")
        self.top_bar_layout.addWidget(self.ai_btn)

        main_layout.addWidget(self.top_bar)

        # 2. Stacked Widget (Content Area)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # Initialize Panels
        self.init_panels()

        # Initialize Agent System
        self.init_agent()

        logger.info("MainWindow initialized")

    def apply_vscode_theme(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #1e1e1e;
                color: #cccccc;
            }
            QWidget {
                background-color: #1e1e1e;
                color: #cccccc;
                font-family: 'Segoe UI', 'Arial';
                font-size: 10pt;
            }
            /* Top Bar */
            QFrame#TopBar {
                background-color: #333333;
                border-bottom: 1px solid #252526;
            }

            /* Nav Buttons (Tabs style) */
            QPushButton#NavButton {
                background-color: transparent;
                color: #cccccc;
                border: none;
                border-bottom: 2px solid transparent;
                padding: 0 15px;
                font-weight: bold;
                height: 48px;
            }
            QPushButton#NavButton:hover {
                background-color: #3e3e42;
                color: #ffffff;
            }
            QPushButton#NavButton:checked {
                color: #ffffff;
                border-bottom: 2px solid #007acc;
                background-color: #1e1e1e;
            }

            /* Action Buttons (Import, AI) */
            QPushButton#ActionBtn {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton#ActionBtn:hover {
                background-color: #1177bb;
            }
            QPushButton#ActionBtn:pressed {
                background-color: #094771;
            }
            QPushButton#ActionBtn:checked {
                background-color: #094771;
                border: 1px solid #007acc;
            }

            /* Content Area */
            QStackedWidget {
                background-color: #1e1e1e;
            }

            /* Standard Widgets */
            QLabel { color: #cccccc; }
            QGroupBox {
                border: 1px solid #454545;
                margin-top: 1.5em;
                border-radius: 4px;
                font-weight: bold;
                color: #cccccc;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #cccccc;
            }
            /* Table Widget */
            QTableWidget {
                background-color: #1e1e1e;
                gridline-color: #333333;
                border: 1px solid #454545;
                color: #cccccc;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #cccccc;
                padding: 4px;
                border: 1px solid #333333;
            }
            QTableWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QDockWidget::title {
                background: #252526;
                text-align: left;
                padding: 5px;
                color: #cccccc;
            }

            /* Card Widget */
            QFrame#CardWidget {
                background-color: #252526;
                border: 1px solid #3e3e42;
                border-radius: 8px;
            }
            QLabel#CardTitle {
                font-size: 12pt;
                font-weight: bold;
                color: #ffffff;
                padding-bottom: 10px;
                border-bottom: 1px solid #3e3e42;
                margin-bottom: 5px;
            }

            /* Modern Buttons in Cards */
            QPushButton {
                background-color: #3e3e42;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4e4e52;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
        """
        )

    def add_nav_btn(self, name, index, text):
        btn = QPushButton(text)
        btn.setToolTip(name)
        btn.setCheckable(True)
        btn.setObjectName("NavButton")

        btn.clicked.connect(lambda: self.switch_page(index))

        self.top_bar_layout.addWidget(btn)
        self.nav_btns.append(btn)

        if index == 0:
            btn.setChecked(True)
        elif index == 1:
            # This block was added based on the instruction's intent.
            # Assuming it was meant to be a conditional check.
            pass
            # The original instruction had invalid syntax.
            # Keeping this as a placeholder for potential future logic.

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_btns):
            btn.setChecked(i == index)

        # Unified Update Logic: Always call update_panel() on result
        target_panel: Any = None
        if index == 0 and hasattr(self, "dataset_panel"):
            target_panel = self.dataset_panel
        elif index == 1 and hasattr(self, "preprocess_panel"):
            target_panel = self.preprocess_panel
        elif index == 2 and hasattr(self, "training_panel"):
            target_panel = self.training_panel
        elif index == 3 and hasattr(self, "evaluation_panel"):
            target_panel = self.evaluation_panel
        elif index == 4 and hasattr(self, "visualization_panel"):
            target_panel = self.visualization_panel

        if target_panel and hasattr(target_panel, "update_panel"):
            target_panel.update_panel()

    def init_panels(self):
        """
        Initializes and adds all main functional panels to the stacked widget.
        The order of addition corresponds to the index used in navigation.
        """
        # 0. Dataset
        self.dataset_panel = DatasetPanel(self)
        self.stack.addWidget(self.dataset_panel)

        # 1. Preprocess
        self.preprocess_panel = PreprocessPanel(self)
        self.stack.addWidget(self.preprocess_panel)

        # 2. Training
        self.training_panel = TrainingPanel(self)
        self.stack.addWidget(self.training_panel)

        # 3. Evaluation
        self.evaluation_panel = EvaluationPanel(self)
        self.stack.addWidget(self.evaluation_panel)

        # 4. Visualization
        self.visualization_panel = VisualizationPanel(self)
        self.stack.addWidget(self.visualization_panel)

    def init_agent(self):
        # 1. Create Chat Panel (Dockable)
        self.chat_panel = ChatPanel()
        self.chat_dock = QDockWidget("AI Assistant", self)
        self.chat_dock.setWidget(self.chat_panel)
        self.chat_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)

        self.chat_dock.visibilityChanged.connect(self.update_ai_btn_state)
        self.chat_dock.hide()  # Hide by default

    def start_agent_system(self):
        """
        Initializes the AI Agent system.
        This is done lazily (only when requested) to save resources.
        """
        if self.agent_initialized:
            return

        # 2. Create Controller
        self.agent_controller = LLMController(self.study)

        # 3. Connect Signals
        self.chat_panel.send_message.connect(self.handle_user_input)

        self.agent_controller.response_ready.connect(
            lambda sender, text: self.chat_panel.append_message(sender, text)
        )
        self.agent_controller.status_update.connect(self.chat_panel.set_status)
        self.agent_controller.status_update.connect(self.chat_panel.set_status)
        self.agent_controller.error_occurred.connect(self.handle_agent_error)
        self.agent_controller.request_user_interaction.connect(
            self.handle_user_interaction
        )

        # Initialize

        # Initialize
        self.agent_controller.initialize()

        self.agent_initialized = True

    def toggle_ai_dock(self):
        if not self.agent_initialized:
            # Show Warning
            reply = QMessageBox.warning(
                self,
                "Activate AI Assistant",
                "You are about to activate the AI Assistant.\n\n"
                "This feature uses an LLM (Large Language Model) which requires "
                "significant system resources (GPU/VRAM).\n"
                "It may slow down other operations on lower-end systems.\n"
                "Do you want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.start_agent_system()
                self.chat_dock.show()
                self.ai_btn.setChecked(True)
            else:
                self.ai_btn.setChecked(False)  # Revert check state
                return
        elif self.chat_dock.isVisible():
            self.chat_dock.close()
        else:
            self.chat_dock.show()

    def update_ai_btn_state(self, visible):
        self.ai_btn.blockSignals(True)
        self.ai_btn.setChecked(visible)
        self.ai_btn.blockSignals(False)

    def update_info_panel(self):
        if hasattr(self, "info_panel"):
            self.info_panel.update_info()

    def handle_user_input(self, text):
        # Forward to controller
        if hasattr(self, "agent_controller"):
            self.agent_controller.handle_user_input(text)

    def handle_user_interaction(self, command, params):
        """Dispatcher for Human-in-the-loop requests."""
        if command == "confirm_montage":
            # Open Montage Picker
            self.open_montage_picker_dialog(params)

    def open_montage_picker_dialog(self, params):
        if not self.study.epoch_data:
            self.chat_panel.append_message(
                "System", "Error: No epoch data available for montage."
            )
            return

        # Get channel names from backend
        chs = self.study.epoch_data.get_mne().info["ch_names"]

        dialog = PickMontageWindow(self, chs)
        if dialog.exec():
            # Get result from dialog and save to study
            chs, positions = dialog.get_result()
            if chs and positions is not None:
                self.study.set_channels(chs, positions)

                # Resume Agent
                self.chat_panel.append_message("User", "Montage Confirmed.")
                self.agent_controller.handle_user_input("Montage Confirmed.")
            else:
                self.chat_panel.append_message(
                    "System", "Error: No valid montage configuration returned."
                )
                self.agent_controller.handle_user_input("Montage Selection Failed.")
        else:
            # User Cancelled
            self.chat_panel.append_message("User", "Operation Cancelled.")
            self.agent_controller.handle_user_input(
                "Montage Selection Cancelled by User."
            )

    def handle_agent_error(self, error_msg):
        self.chat_panel.set_status("Error")
        self.chat_panel.append_message("System", f"Error: {error_msg}")
        logger.error(f"Agent Error: {error_msg}")

    def closeEvent(self, event):  # noqa: N802
        logger.info("Closing application...")
        if hasattr(self, "agent_controller"):
            self.agent_controller.close()
        super().closeEvent(event)

    def refresh_panels(self):
        """Refresh all panels to synchronize data."""
        # Update Dataset Panel (which updates its own Aggregate Info)
        if hasattr(self, "dataset_panel"):
            self.dataset_panel.update_panel()

        # Update Preprocess Panel
        if hasattr(self, "preprocess_panel"):
            self.preprocess_panel.update_panel()

        # Update Training Panel
        if hasattr(self, "training_panel"):
            self.training_panel.update_info()

        # Update Evaluation Panel
        if hasattr(self, "evaluation_panel"):
            self.evaluation_panel.update_info()

        # Update Visualization Panel
        if hasattr(self, "visualization_panel"):
            self.visualization_panel.update_info()


def global_exception_handler(exctype, value, traceback):
    if issubclass(exctype, KeyboardInterrupt):
        sys.__excepthook__(exctype, value, traceback)
        return
    logger.error("Uncaught exception", exc_info=(exctype, value, traceback))
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setText("An unexpected error occurred.")
    msg.setInformativeText(str(value))
    msg.setWindowTitle("Error")
    msg.exec()


# Only set exception hook if not running under pytest

if "pytest" not in sys.modules:
    sys.excepthook = global_exception_handler
