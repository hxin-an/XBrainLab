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
        
        # Friendly names
        self.friendly_map = {}
        for i, trainer in enumerate(self.trainers):
            model_name = trainer.model_holder.target_model.__name__
            friendly_name = f"Group {i+1} ({model_name})"
            self.friendly_map[friendly_name] = trainer
            self.plan_combo.addItem(friendly_name)
            
        self.plan_combo.setStyleSheet(self.get_combo_style())
        self.plan_combo.currentTextChanged.connect(self.on_plan_change)
        h1.addWidget(self.plan_combo)
        ctrl_layout.addLayout(h1)
        
        # Repeat Selector
        h2 = QHBoxLayout()
        lbl2 = QLabel("Run:") # Changed from Repeat to Run for consistency
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
        
        if plan_name != "---" and plan_name in self.friendly_map:
            trainer = self.friendly_map[plan_name]
            # Add runs
            for i in range(trainer.option.repeat_num):
                self.repeat_combo.addItem(f"Run {i+1}")
            # Add Average
            self.repeat_combo.addItem("Average")
        else:
            pass
            
    def on_repeat_change(self, repeat_name):
        self.event_combo.clear()
        self.event_combo.addItem("---")
        
        plan_name = self.plan_combo.currentText()
        if plan_name == "---" or plan_name not in self.friendly_map:
            return
            
        trainer = self.friendly_map[plan_name]
        
        # Get events from dataset (same for all runs)
        epoch_data = trainer.get_dataset().get_epoch_data()
        if epoch_data:
            events = list(epoch_data.event_id.keys())
            self.event_combo.addItems(events)
            
    def get_averaged_record(self, trainer):
        """Compute average EvalRecord from all finished runs."""
        import numpy as np
        from XBrainLab.backend.training.record.eval import EvalRecord
        
        plans = trainer.get_plans()
        records = [p.get_eval_record() for p in plans if p.get_eval_record() is not None]
        
        if not records:
            return None
            
        base = records[0]
        
        def avg_dict(attr_name):
            result = {}
            keys = getattr(base, attr_name).keys()
            for k in keys:
                arrays = [getattr(r, attr_name)[k] for r in records]
                result[k] = np.mean(np.stack(arrays), axis=0)
            return result

        avg_gradient = avg_dict('gradient')
        avg_gradient_input = avg_dict('gradient_input')
        avg_smoothgrad = avg_dict('smoothgrad')
        avg_smoothgrad_sq = avg_dict('smoothgrad_sq')
        avg_vargrad = avg_dict('vargrad')
        
        return EvalRecord(
            label=base.label,
            output=base.output,
            gradient=avg_gradient,
            gradient_input=avg_gradient_input,
            smoothgrad=avg_smoothgrad,
            smoothgrad_sq=avg_smoothgrad_sq,
            vargrad=avg_vargrad
        )

    def show_plot(self):
        plan_name = self.plan_combo.currentText()
        repeat_name = self.repeat_combo.currentText()
        event_name = self.event_combo.currentText()
        
        if plan_name == "---" or repeat_name == "---" or event_name == "---":
            QMessageBox.warning(self, "Warning", "Please select Plan, Run, and Event.")
            return
            
        trainer = self.friendly_map[plan_name]
        
        target_plan = None
        eval_record = None
        
        if repeat_name == "Average":
            eval_record = self.get_averaged_record(trainer)
            if not eval_record:
                QMessageBox.warning(self, "Warning", "No finished runs to average.")
                return
            target_plan = trainer.get_plans()[0]
        else:
            try:
                run_idx = int(repeat_name.split(" ")[1]) - 1
                plans = trainer.get_plans()
                if 0 <= run_idx < len(plans):
                    target_plan = plans[run_idx]
                    eval_record = target_plan.get_eval_record()
            except:
                pass
        
        if not eval_record:
            QMessageBox.warning(self, "Warning", "Selected run has no evaluation record.")
            return

        epoch_data = trainer.get_dataset().get_epoch_data()
        
        try:
            saliency = Saliency3D(
                eval_record, epoch_data, event_name
            )
            plot = saliency.get3dHeadPlot()
            plot.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch 3D plot: {e}")
