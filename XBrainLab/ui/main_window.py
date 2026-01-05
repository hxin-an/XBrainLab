import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QStackedWidget, QMessageBox, QDockWidget, QPushButton, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QAction

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.agent_worker import AgentWorker
from XBrainLab.ui.chat_panel import ChatPanel
from XBrainLab.ui.dashboard_panel.dataset import DatasetPanel
from XBrainLab.ui.dashboard_panel.preprocess import PreprocessPanel
from XBrainLab.ui.dashboard_panel.info import AggregateInfoPanel
from XBrainLab.ui.training.panel import TrainingPanel
from XBrainLab.ui.evaluation.panel import EvaluationPanel
from XBrainLab.ui.visualization.panel import VisualizationPanel

class MainWindow(QMainWindow):
    """
    The main application window for XBrainLab (PyQt6 version).
    
    This window manages the overall layout, including:
    - Top Navigation Bar: For switching between main panels (Dataset, Preprocess, Training, etc.).
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
        
        self.agent_initialized = False # Flag for lazy loading
        
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
        self.ai_btn.setChecked(False) # Default Off
        self.ai_btn.clicked.connect(self.toggle_ai_dock)
        self.ai_btn.setObjectName("ActionBtn")
        self.top_bar_layout.addWidget(self.ai_btn)

        # Info Toggle Button
        self.info_btn = QPushButton("Data Info")
        self.info_btn.setCheckable(True)
        self.info_btn.setChecked(True)
        self.info_btn.clicked.connect(self.toggle_info_dock)
        self.info_btn.setObjectName("ActionBtn")
        self.top_bar_layout.addWidget(self.info_btn)
        
        main_layout.addWidget(self.top_bar)
        
        # 2. Stacked Widget (Content Area)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        
        # Initialize Panels
        self.init_panels()

        # Initialize Info Dock
        self.init_info_dock()
        
        # Initialize Agent System
        self.init_agent()
        
        logger.info("MainWindow initialized")

    def apply_vscode_theme(self):
        self.setStyleSheet("""
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
        """)

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
        elif index == 1: # This block was added based on the instruction's intent, assuming it was meant to be a conditional check.
            pass # The original instruction had `self.preprocess_panel.update_panel()d(True)` which is syntactically incorrect and `preprocess_panel` would not exist yet.
                 # Keeping this as a placeholder for potential future logic, but not adding the incorrect code.

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_btns):
            btn.setChecked(i == index)
        
        # Call update_panel if the Preprocess panel is selected
        if index == 1 and hasattr(self, 'preprocess_panel'):
            self.preprocess_panel.update_panel()
            
        # Call refresh_data if Evaluation or Visualization panel is selected
        if index == 3 and hasattr(self, 'evaluation_panel'):
            self.evaluation_panel.refresh_data()
            
        if index == 4 and hasattr(self, 'visualization_panel'):
            self.visualization_panel.refresh_data()

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
        self.chat_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)
        
        self.chat_dock.visibilityChanged.connect(self.update_ai_btn_state)
        self.chat_dock.hide() # Hide by default

    def start_agent_system(self):
        """
        Initializes the AI Agent system in a separate thread.
        This is done lazily (only when requested) to save resources.
        """
        if self.agent_initialized:
            return

        # 2. Setup Thread and Worker
        self.agent_thread = QThread()
        self.agent_worker = AgentWorker()
        self.agent_worker.moveToThread(self.agent_thread)
        
        # 3. Connect Signals
        self.chat_panel.send_message.connect(self.handle_user_input)
        self.sig_init_agent.connect(self.agent_worker.initialize_agent)
        self.sig_generate.connect(self.agent_worker.generate)
        self.agent_worker.finished.connect(self.handle_agent_response)
        self.agent_worker.error.connect(self.handle_agent_error)
        self.agent_worker.log.connect(self.handle_agent_log)
        
        self.agent_thread.start()
        
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.trigger_agent_init)
        
        self.agent_initialized = True

    def trigger_agent_init(self):
        self.sig_init_agent.emit()

    def toggle_ai_dock(self):
        if not self.agent_initialized:
            # Show Warning
            reply = QMessageBox.warning(
                self, "Activate AI Assistant",
                "You are about to activate the AI Assistant.\n\n"
                "This feature uses an LLM (Large Language Model) which requires significant system resources (GPU/VRAM).\n"
                "It may slow down other operations on lower-end systems.\n"
                "Do you want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.start_agent_system()
                self.chat_dock.show()
                self.ai_btn.setChecked(True)
            else:
                self.ai_btn.setChecked(False) # Revert check state
                return
        else:
            if self.chat_dock.isVisible():
                self.chat_dock.close()
            else:
                self.chat_dock.show()

    def update_ai_btn_state(self, visible):
        self.ai_btn.blockSignals(True)
        self.ai_btn.setChecked(visible)
        self.ai_btn.blockSignals(False)

    def init_info_dock(self):
        self.info_panel = AggregateInfoPanel(self)
        self.info_dock = QDockWidget("Data Info", self)
        self.info_dock.setWidget(self.info_panel)
        self.info_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.info_dock)
        self.info_dock.visibilityChanged.connect(self.update_info_btn_state)

    def toggle_info_dock(self):
        if self.info_dock.isVisible():
            self.info_dock.close()
        else:
            self.info_dock.show()

    def update_info_btn_state(self, visible):
        self.info_btn.blockSignals(True)
        self.info_btn.setChecked(visible)
        self.info_btn.blockSignals(False)

    def update_info_panel(self):
        if hasattr(self, 'info_panel'):
            self.info_panel.update_info()

    def handle_user_input(self, text):
        history = "" 
        self.sig_generate.emit(history, text)

    def handle_agent_response(self, commands):
        self.chat_panel.set_status("Ready")
        response_text = ""
        for cmd in commands:
            if "text" in cmd:
                response_text += cmd["text"] + "\n"
            elif "command" in cmd:
                response_text += f"[Command] {cmd['command']}: {cmd['parameters']}\n"
        
        if not response_text:
            response_text = "(No response generated)"
            
        self.chat_panel.append_message("Agent", response_text)

    def handle_agent_error(self, error_msg):
        self.chat_panel.set_status("Error")
        self.chat_panel.append_message("System", f"Error: {error_msg}")
        logger.error(f"Agent Error: {error_msg}")

    def handle_agent_log(self, msg):
        self.chat_panel.set_status(msg)

    def closeEvent(self, event):
        logger.info("Closing application...")
        if hasattr(self, 'agent_thread') and self.agent_thread.isRunning():
            logger.info("Stopping agent thread...")
            self.agent_thread.requestInterruption()
            self.agent_thread.quit()
            if not self.agent_thread.wait(500): 
                logger.warning("Agent thread is busy, letting application exit anyway.")
        super().closeEvent(event)

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

sys.excepthook = global_exception_handler
