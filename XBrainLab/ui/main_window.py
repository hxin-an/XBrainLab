import sys
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
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
from XBrainLab.ui.components.agent_manager import AgentManager
from XBrainLab.ui.components.info_panel_service import InfoPanelService

# LLMController, ChatPanel, PickMontageDialog moved to AgentManager
from XBrainLab.ui.panels.dataset.panel import DatasetPanel
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel
from XBrainLab.ui.panels.training.panel import TrainingPanel
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel
from XBrainLab.ui.styles.stylesheets import Stylesheets


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

        # 3. Services
        self.info_service = InfoPanelService(self.study)

        # Initialize Agent System
        self.init_agent()

        logger.info("MainWindow initialized")

    def apply_vscode_theme(self):
        self.setStyleSheet(Stylesheets.MAIN_WINDOW)

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
        # Get Controllers
        dataset_ctrl = self.study.get_controller("dataset")
        preprocess_ctrl = self.study.get_controller("preprocess")
        training_ctrl = self.study.get_controller("training")
        eval_ctrl = self.study.get_controller("evaluation")
        viz_ctrl = self.study.get_controller("visualization")

        # 0. Dataset
        self.dataset_panel = DatasetPanel(dataset_ctrl, self)
        self.stack.addWidget(self.dataset_panel)

        # 1. Preprocess
        self.preprocess_panel = PreprocessPanel(preprocess_ctrl, dataset_ctrl, self)
        self.stack.addWidget(self.preprocess_panel)

        # 2. Training
        self.training_panel = TrainingPanel(training_ctrl, dataset_ctrl, self)
        self.stack.addWidget(self.training_panel)

        # 3. Evaluation
        self.evaluation_panel = EvaluationPanel(eval_ctrl, training_ctrl, self)
        self.stack.addWidget(self.evaluation_panel)

        # 4. Visualization
        self.visualization_panel = VisualizationPanel(viz_ctrl, training_ctrl, self)
        self.stack.addWidget(self.visualization_panel)

    def init_agent(self):
        # Delegate to AgentManager
        self.agent_manager = AgentManager(self, self.study)
        self.agent_manager.init_ui()

    def toggle_ai_dock(self):
        self.agent_manager.toggle()

    def update_info_panel(self):
        if hasattr(self, "info_panel"):
            self.info_panel.update_info()

    def closeEvent(self, event):  # noqa: N802
        logger.info("Closing application...")
        if hasattr(self, "agent_manager"):
            self.agent_manager.close()
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


# Only set exception hook if not running under pytest

if "pytest" not in sys.modules:
    sys.excepthook = global_exception_handler
