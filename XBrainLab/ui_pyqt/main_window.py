import sys
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QTabWidget, QMessageBox, QDockWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from XBrainLab.utils.logger import logger
from XBrainLab.ui_pyqt.agent_worker import AgentWorker
from XBrainLab.ui_pyqt.chat_panel import ChatPanel
from XBrainLab.ui_pyqt.dataset_panel import DatasetPanel

class MainWindow(QMainWindow):
    # Signals to control the worker
    sig_init_agent = pyqtSignal()
    sig_generate = pyqtSignal(str, str)

    def __init__(self, study):
        super().__init__()
        self.study = study
        self.setWindowTitle("XBrainLab (PyQt6)")
        self.resize(1200, 800)
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Layout
        layout = QVBoxLayout(central_widget)
        
        # Tabs for different panels
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Initialize Tabs (Placeholders for now)
        self.init_tabs()
        
        # Initialize Agent System
        self.init_agent()
        
        logger.info("MainWindow initialized")

    def init_agent(self):
        """Setup the Agent Worker and Chat Interface."""
        # 1. Create Chat Panel (Dockable)
        self.chat_panel = ChatPanel()
        self.chat_dock = QDockWidget("AI Assistant", self)
        self.chat_dock.setWidget(self.chat_panel)
        self.chat_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)
        
        # 2. Setup Thread and Worker
        self.agent_thread = QThread()
        self.agent_worker = AgentWorker()
        self.agent_worker.moveToThread(self.agent_thread)
        
        # 3. Connect Signals
        # UI -> Worker
        self.chat_panel.send_message.connect(self.handle_user_input)
        
        # MainWindow -> Worker (Signals)
        self.sig_init_agent.connect(self.agent_worker.initialize_agent)
        self.sig_generate.connect(self.agent_worker.generate)

        # Worker -> UI
        self.agent_worker.finished.connect(self.handle_agent_response)
        self.agent_worker.error.connect(self.handle_agent_error)
        self.agent_worker.log.connect(self.handle_agent_log)
        
        # Start Thread
        self.agent_thread.start()
        
        # Initialize Agent in background
        # We use QMetaObject.invokeMethod to ensure it runs in the thread
        # Or simply define a slot. For simplicity, let's use a signal or direct call if thread safe.
        # Best practice: emit a signal to start initialization
        # But here we can just call a method that runs in the thread if we connected it.
        # Let's add a signal to MainWindow to trigger init
        pass 
        # Actually, let's trigger it via a single shot timer or just call it? 
        # No, direct call runs in caller thread.
        # Let's add a signal to AgentWorker "start_init"
        
        # For now, let's just connect thread started to worker init?
        # self.agent_thread.started.connect(self.agent_worker.initialize_agent) 
        # But we already started it.
        
        # Let's just run it:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.trigger_agent_init)

    def trigger_agent_init(self):
        """Trigger agent initialization in the worker thread."""
        self.sig_init_agent.emit()

    def handle_user_input(self, text):
        """Handle input from ChatPanel."""
        # Get history (mock for now, or maintain state)
        history = "" 
        
        # Send to worker via signal
        self.sig_generate.emit(history, text)

    def handle_agent_response(self, commands):
        """Handle commands returned by Agent."""
        self.chat_panel.set_status("Ready")
        
        # Format response
        response_text = ""
        for cmd in commands:
            if "text" in cmd:
                response_text += cmd["text"] + "\n"
            elif "command" in cmd:
                response_text += f"[Command] {cmd['command']}: {cmd['parameters']}\n"
        
        if not response_text:
            response_text = "(No response generated)"
            
        self.chat_panel.append_message("Agent", response_text)
        
        # TODO: Execute commands automatically or ask for confirmation?
        # For now, just display.

    def handle_agent_error(self, error_msg):
        self.chat_panel.set_status("Error")
        self.chat_panel.append_message("System", f"Error: {error_msg}")
        logger.error(f"Agent Error: {error_msg}")

    def handle_agent_log(self, msg):
        self.chat_panel.set_status(msg)

    def closeEvent(self, event):
        """Cleanup threads on close."""
        self.agent_thread.quit()
        self.agent_thread.wait()
        super().closeEvent(event)

    def init_tabs(self):
        """Initialize the tabs for the application."""
        self.dataset_panel = DatasetPanel(self)
        self.tabs.addTab(self.dataset_panel, "Dataset")
        
        self.tabs.addTab(QLabel("Preprocess Panel (Coming Soon)"), "Preprocess")
        self.tabs.addTab(QLabel("Training Panel (Coming Soon)"), "Training")
        self.tabs.addTab(QLabel("Evaluation Panel (Coming Soon)"), "Evaluation")
        self.tabs.addTab(QLabel("Visualization Panel (Coming Soon)"), "Visualization")

def global_exception_handler(exctype, value, traceback):
    """
    Global exception handler to catch unhandled exceptions and log them.
    Also displays an error message box to the user.
    """
    # Log the error
    if issubclass(exctype, KeyboardInterrupt):
        sys.__excepthook__(exctype, value, traceback)
        return

    logger.error("Uncaught exception", exc_info=(exctype, value, traceback))
    
    # Show error message to user
    # Note: We need a QApplication instance to show QMessageBox, 
    # but since this is a global handler, we assume app exists.
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setText("An unexpected error occurred.")
    msg.setInformativeText(str(value))
    msg.setWindowTitle("Error")
    msg.exec()

# Set the global exception handler
sys.excepthook = global_exception_handler
