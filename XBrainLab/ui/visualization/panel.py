from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGroupBox, QTabWidget, QMessageBox, QTextEdit, QFrame, QLabel
)
from PyQt6.QtCore import Qt
from .montage_picker import PickMontageWindow
from .saliency_setting import SetSaliencyWindow
from .saliency_map import SaliencyMapWidget
from .saliency_topomap import SaliencyTopographicMapWidget
from .saliency_spectrogram import SaliencySpectrogramWidget
from .saliency_3Dplot import Saliency3DPlotWidget
from .export_saliency import ExportSaliencyWindow
from .model_summary import ModelSummaryWindow
from XBrainLab.ui.dashboard_panel.info import AggregateInfoPanel

class VisualizationPanel(QWidget):
    """
    Panel for visualizing data and model explanations.
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
        
        # Visualization Group
        viz_group = QGroupBox("VISUALIZATION PLOTS")
        viz_layout = QVBoxLayout(viz_group)
        viz_layout.setContentsMargins(10, 20, 10, 10)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 0; }")
        
        # Get trainers for initialization
        trainers = self.get_trainers()
        trainers_list = trainers if trainers else []
        
        # Tab 1: Saliency Map
        self.tab_map = SaliencyMapWidget(self, trainers_list)
        self.tabs.addTab(self.tab_map, "Saliency Map")
        
        # Tab 2: Topographic Map
        self.tab_topo = SaliencyTopographicMapWidget(self, trainers_list)
        self.tabs.addTab(self.tab_topo, "Topographic Map")
        
        # Tab 3: Spectrogram
        self.tab_spectro = SaliencySpectrogramWidget(self, trainers_list)
        self.tabs.addTab(self.tab_spectro, "Spectrogram")
        
        # Tab 4: 3D Plot
        self.tab_3d = Saliency3DPlotWidget(self, trainers_list)
        self.tabs.addTab(self.tab_3d, "3D Plot")
        
        viz_layout.addWidget(self.tabs)
        left_layout.addWidget(viz_group)
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
        
        self.btn_montage = QPushButton("Set Montage")
        self.btn_montage.clicked.connect(self.set_montage)
        config_layout.addWidget(self.btn_montage)
        
        self.btn_saliency = QPushButton("Set Saliency Methods")
        self.btn_saliency.clicked.connect(self.set_saliency)
        config_layout.addWidget(self.btn_saliency)
        
        right_layout.addWidget(config_group)
        right_layout.addSpacing(20)
        
        # Group 2: Operations
        ops_group = QGroupBox("OPERATIONS")
        ops_layout = QVBoxLayout(ops_group)
        ops_layout.setContentsMargins(0, 10, 0, 0)
        
        self.btn_export = QPushButton("Export Saliency")
        self.btn_export.clicked.connect(self.export_saliency)
        ops_layout.addWidget(self.btn_export)
        
        self.btn_summary = QPushButton("Model Summary")
        self.btn_summary.clicked.connect(self.model_summary)
        ops_layout.addWidget(self.btn_summary)
        
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

    def set_montage(self):
        if not self.study.epoch_data:
             QMessageBox.warning(self, "Warning", "No epoch data available.")
             return
        win = PickMontageWindow(self, self.study.epoch_data.get_channel_names())
        if win.exec():
            chs, positions = win.get_result()
            if chs is not None and positions is not None:
                self.study.set_channels(chs, positions)
                QMessageBox.information(self, "Success", "Montage set")

    def set_saliency(self):
        win = SetSaliencyWindow(self, self.study.get_saliency_params())
        if win.exec():
            params = win.get_result()
            if params:
                self.study.set_saliency_params(params)
                QMessageBox.information(self, "Success", "Saliency parameters set")

    def export_saliency(self):
        trainers = self.get_trainers()
        if not trainers:
            QMessageBox.warning(self, "Warning", "No training results available.")
            return
        win = ExportSaliencyWindow(self, trainers)
        win.exec()

    def model_summary(self):
        trainers = self.get_trainers()
        if not trainers:
            QMessageBox.warning(self, "Warning", "No training results available.")
            return
        win = ModelSummaryWindow(self, trainers)
        win.exec()

    def refresh_data(self):
        trainers = self.get_trainers()
        if not trainers:
            QMessageBox.warning(self, "Warning", "No training results available.")
            return
            
        # Re-create widgets
        self.tab_map.setParent(None)
        self.tab_map = SaliencyMapWidget(self, trainers)
        self.tabs.removeTab(0)
        self.tabs.insertTab(0, self.tab_map, "Saliency Map")
        
        self.tab_topo.setParent(None)
        self.tab_topo = SaliencyTopographicMapWidget(self, trainers)
        self.tabs.removeTab(1)
        self.tabs.insertTab(1, self.tab_topo, "Topographic Map")
        
        self.tab_spectro.setParent(None)
        self.tab_spectro = SaliencySpectrogramWidget(self, trainers)
        self.tabs.removeTab(2)
        self.tabs.insertTab(2, self.tab_spectro, "Spectrogram")
        
        self.tab_3d.setParent(None)
        self.tab_3d = Saliency3DPlotWidget(self, trainers)
        self.tabs.removeTab(3)
        self.tabs.insertTab(3, self.tab_3d, "3D Plot")
        
        self.tabs.setCurrentIndex(0)
        self.tabs.setCurrentIndex(0)
        
        QMessageBox.information(self, "Success", "Visualization data refreshed.")

    def update_info(self):
        """Update the Aggregate Info Panel."""
        if hasattr(self, 'info_panel'):
            self.info_panel.update_info()

