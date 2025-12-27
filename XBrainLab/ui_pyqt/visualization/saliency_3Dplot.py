from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt
from .plot_3d_head import Saliency3D

class Saliency3DPlotWidget(QWidget):
    def __init__(self, parent, trainers):
        super().__init__(parent)
        self.trainers = trainers
        self.trainer_map = {trainer.get_name(): trainer for trainer in trainers}
        self.real_plan_opt = {}
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Controls Container
        ctrl_container = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_container)
        ctrl_layout.setSpacing(15)
        
        # Plan Selector
        h1 = QHBoxLayout()
        lbl1 = QLabel("Plan:")
        lbl1.setStyleSheet("color: #cccccc; font-weight: bold;")
        h1.addWidget(lbl1)
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("---")
        self.plan_combo.addItems(list(self.trainer_map.keys()))
        self.plan_combo.setStyleSheet(self.get_combo_style())
        self.plan_combo.currentTextChanged.connect(self.on_plan_change)
        h1.addWidget(self.plan_combo)
        ctrl_layout.addLayout(h1)
        
        # Repeat Selector
        h2 = QHBoxLayout()
        lbl2 = QLabel("Repeat:")
        lbl2.setStyleSheet("color: #cccccc; font-weight: bold;")
        h2.addWidget(lbl2)
        self.repeat_combo = QComboBox()
        self.repeat_combo.addItem("---")
        self.repeat_combo.setStyleSheet(self.get_combo_style())
        self.repeat_combo.currentTextChanged.connect(self.on_repeat_change)
        h2.addWidget(self.repeat_combo)
        ctrl_layout.addLayout(h2)
        
        # Event Selector
        h3 = QHBoxLayout()
        lbl3 = QLabel("Event:")
        lbl3.setStyleSheet("color: #cccccc; font-weight: bold;")
        h3.addWidget(lbl3)
        self.event_combo = QComboBox()
        self.event_combo.addItem("---")
        self.event_combo.setStyleSheet(self.get_combo_style())
        h3.addWidget(self.event_combo)
        ctrl_layout.addLayout(h3)
        
        layout.addWidget(ctrl_container)
        layout.addSpacing(20)
        
        # Launch Button Area
        btn_container = QWidget()
        btn_layout = QVBoxLayout(btn_container)
        
        self.btn_launch = QPushButton("Launch 3D View")
        self.btn_launch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_launch.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0098ff;
            }
            QPushButton:pressed {
                background-color: #005c99;
            }
        """)
        self.btn_launch.clicked.connect(self.show_plot)
        btn_layout.addWidget(self.btn_launch, alignment=Qt.AlignmentFlag.AlignCenter)
        
        lbl_hint = QLabel("Opens an interactive 3D window")
        lbl_hint.setStyleSheet("color: #666666; font-style: italic;")
        btn_layout.addWidget(lbl_hint, alignment=Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(btn_container)
        layout.addStretch()

    def get_combo_style(self):
        return """
            QComboBox {
                background-color: #3e3e42;
                color: #cccccc;
                border: 1px solid #555;
                padding: 5px;
                min-width: 200px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
        """

    def on_plan_change(self, plan_name):
        self.repeat_combo.clear()
        self.repeat_combo.addItem("---")
        
        if plan_name != "---":
            trainer = self.trainer_map[plan_name]
            self.real_plan_opt = {
                plan.get_name(): plan
                for plan in trainer.get_plans()
            }
            self.repeat_combo.addItems(list(self.real_plan_opt.keys()))
        else:
            self.real_plan_opt = {}
            
    def on_repeat_change(self, repeat_name):
        self.event_combo.clear()
        self.event_combo.addItem("---")
        
        if repeat_name != "---" and repeat_name in self.real_plan_opt:
            real_plan = self.real_plan_opt[repeat_name]
            events = list(real_plan.dataset.get_epoch_data().event_id.keys())
            self.event_combo.addItems(events)
            
    def show_plot(self):
        plan_name = self.plan_combo.currentText()
        repeat_name = self.repeat_combo.currentText()
        event_name = self.event_combo.currentText()
        
        if plan_name == "---" or repeat_name == "---" or event_name == "---":
            QMessageBox.warning(self, "Warning", "Please select Plan, Repeat, and Event.")
            return
            
        real_plan = self.real_plan_opt[repeat_name]
        eval_record = real_plan.get_eval_record()
        epoch_data = real_plan.dataset.get_epoch_data()
        
        try:
            saliency = Saliency3D(
                eval_record, epoch_data, event_name
            )
            plot = saliency.get3dHeadPlot()
            plot.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch 3D plot: {e}")
