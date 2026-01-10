from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGroupBox, QMessageBox, QTabWidget, QTextEdit, QLabel, QFrame
)
from PyQt6.QtCore import Qt
from .confusion_matrix import ConfusionMatrixWidget
from .evaluation_table import EvaluationTableWidget
from .model_output import ModelOutputWindow
from XBrainLab.ui.dashboard_panel.info import AggregateInfoPanel

class EvaluationPanel(QWidget):
    """
    Panel for evaluating trained models.
    """
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.study = main_window.study
        
        self.init_ui()
        
    def init_ui(self):
        # Main Layout: Horizontal (Left: Content, Right: Controls)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- Left Column: Tabs ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(0)
        
        # Evaluation Results Group
        eval_group = QGroupBox("EVALUATION RESULTS")
        eval_layout = QVBoxLayout(eval_group)
        eval_layout.setContentsMargins(10, 20, 10, 10)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 0; }")
        
        # Tab 1: Performance Table
        trainers = self.get_trainers()
        self.tab_table = EvaluationTableWidget(self, trainers if trainers else [])
        self.tabs.addTab(self.tab_table, "Performance Table")
        
        # Tab 2: Confusion Matrix
        self.tab_matrix = ConfusionMatrixWidget(self, trainers if trainers else [])
        self.tabs.addTab(self.tab_matrix, "Confusion Matrix")
        
        # Tab 3: Model Output (Placeholder or embedded)
        self.tab_output = QTextEdit()
        self.tab_output.setReadOnly(True)
        self.tab_output.setPlaceholderText("Model output details will appear here...")
        self.tab_output.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333; color: #aaa; font-family: monospace;")
        self.tabs.addTab(self.tab_output, "Model Output")
        
        eval_layout.addWidget(self.tabs)
        left_layout.addWidget(eval_group)
        main_layout.addWidget(left_widget, stretch=1)
        
        # --- Right Side: Sidebar ---
        right_panel = QWidget()
        right_panel.setFixedWidth(260)
        right_panel.setObjectName("RightPanel")
        right_panel.setStyleSheet("""
            #RightPanel { 
                background-color: #252526; 
                border-left: 1px solid #3e3e42; 
            }
            QGroupBox {
                background-color: transparent;
                border: none;
                margin-top: 15px;
                font-weight: bold;
                color: #808080;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
                padding: 0 0px;
                color: #808080;
            }
            QPushButton {
                background-color: #3e3e42; 
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                color: #ffffff;
                font-weight: normal;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4e4e52;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
        """)
        
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 20, 10, 20)
        
        # 0. Logo Removed
        
        # 1. Aggregate Information (New)
        self.info_panel = AggregateInfoPanel(self.main_window)
        right_layout.addWidget(self.info_panel, stretch=1)
        
        # Add separator line with spacing to center it
        right_layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #3e3e42; border: none;")
        line.setFixedHeight(1)
        right_layout.addWidget(line)
        right_layout.addSpacing(10)

        
        # Add separator line with spacing
        right_layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #3e3e42; border: none;")
        line.setFixedHeight(1)
        # Add separator line with spacing
        right_layout.addSpacing(10)
        
        # Group 1: Configuration
        config_group = QGroupBox("CONFIGURATION")
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(0, 10, 0, 0)
        
        self.btn_export = QPushButton("Export Results")
        self.btn_export.clicked.connect(self.export_results)
        config_layout.addWidget(self.btn_export)
        
        self.btn_report = QPushButton("Save Report")
        self.btn_report.clicked.connect(self.save_report)
        config_layout.addWidget(self.btn_report)
        
        right_layout.addWidget(config_group)
        right_layout.addSpacing(20)
        
        # Group 2: Operations
        ops_group = QGroupBox("OPERATIONS")
        ops_layout = QVBoxLayout(ops_group)
        ops_layout.setContentsMargins(0, 10, 0, 0)
        
        self.btn_refresh = QPushButton("Refresh Data")
        self.btn_refresh.clicked.connect(self.refresh_data)
        ops_layout.addWidget(self.btn_refresh)
        
        right_layout.addWidget(ops_group)
        right_layout.addStretch()
        
        main_layout.addWidget(right_panel, stretch=0)

    def get_trainers(self):
        if self.study.trainer:
            return self.study.trainer.get_training_plan_holders()
        return None

    def export_results(self):
        QMessageBox.information(self, "Info", "Export Results feature coming soon.")

    def save_report(self):
        QMessageBox.information(self, "Info", "Save Report feature coming soon.")

    def refresh_data(self):
        trainers = self.get_trainers()
        if not trainers:
            QMessageBox.warning(self, "Warning", "No training results available.")
            return
            
        # Re-create widgets
        self.tab_table.setParent(None)
        self.tab_table = EvaluationTableWidget(self, trainers)
        
        self.tab_matrix.setParent(None)
        self.tab_matrix = ConfusionMatrixWidget(self, trainers)

        # Update Model Output
        output_text = ""
        for i, trainer in enumerate(trainers):
            output_text += f"=== Group {i+1}: {trainer.get_name()} ===\n"
            for plan in trainer.get_plans():
                output_text += plan.get_model_output()
                output_text += "\n\n" + "-"*50 + "\n\n"
        
        self.tab_output.setPlainText(output_text)

        # Clear and re-add all tabs to avoid index issues
        self.tabs.clear()
        self.tabs.addTab(self.tab_table, "Performance Table")
        self.tabs.addTab(self.tab_matrix, "Confusion Matrix")
        self.tabs.addTab(self.tab_output, "Model Output")
        
        self.tabs.setCurrentIndex(0)
        
        QMessageBox.information(self, "Success", "Evaluation data refreshed.")

    def update_info(self):
        """Update the Aggregate Info Panel."""
        if hasattr(self, 'info_panel'):
            self.info_panel.update_info()

