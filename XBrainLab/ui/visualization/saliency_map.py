from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from XBrainLab.backend.visualization import VisualizerType, supported_saliency_methods

class SaliencyMapWidget(QWidget):
    def __init__(self, parent, trainers):
        super().__init__(parent)
        self.trainers = trainers
        self.trainer_map = {t.get_name(): t for t in trainers}
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Controls
        ctrl_layout = QHBoxLayout()
        
        # Plan Selector
        lbl_plan = QLabel("Plan:")
        lbl_plan.setStyleSheet("color: #cccccc;")
        ctrl_layout.addWidget(lbl_plan)
        
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("Select a plan")
        self.plan_combo.addItems(list(self.trainer_map.keys()))
        self.plan_combo.setStyleSheet("""
            QComboBox {
                background-color: #3e3e42;
                color: #cccccc;
                border: 1px solid #555;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
        """)
        self.plan_combo.currentTextChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.plan_combo)
        
        ctrl_layout.addSpacing(20)
        
        # Saliency Method Selector
        lbl_method = QLabel("Method:")
        lbl_method.setStyleSheet("color: #cccccc;")
        ctrl_layout.addWidget(lbl_method)
        
        self.saliency_combo = QComboBox()
        self.saliency_combo.addItem('Gradient')
        self.saliency_combo.addItem('Gradient * Input')
        self.saliency_combo.addItems(supported_saliency_methods)
        self.saliency_combo.setStyleSheet(self.plan_combo.styleSheet())
        self.saliency_combo.currentTextChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.saliency_combo)
        
        ctrl_layout.addSpacing(20)
        
        # Absolute Checkbox
        self.abs_check = QCheckBox("Absolute Value")
        self.abs_check.setStyleSheet("color: #cccccc;")
        self.abs_check.stateChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.abs_check)
        
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)
        
        # Plot Area
        self.plot_container = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_container)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)
        
        # Initial Placeholder
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.fig.patch.set_facecolor('#2d2d2d')
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#2d2d2d')
        self.ax.text(0.5, 0.5, "Select a plan and method to visualize", 
                     color='#666666', ha='center', va='center')
        self.ax.axis('off')
        
        self.plot_layout.addWidget(self.canvas)
        layout.addWidget(self.plot_container, stretch=1)

    def on_update(self):
        plan_name = self.plan_combo.currentText()
        method_name = self.saliency_combo.currentText()
        
        if plan_name == "Select a plan" or plan_name not in self.trainer_map:
            return
            
        trainer = self.trainer_map[plan_name]
        plans = trainer.get_plans()
        if not plans:
            return
        
        # Use first plan for now
        target_plan = plans[0]
        
        self.plot_saliency(target_plan, trainer, method_name, self.abs_check.isChecked())

    def plot_saliency(self, plan, trainer, method, absolute):
        try:
            # Clear previous
            for i in reversed(range(self.plot_layout.count())): 
                self.plot_layout.itemAt(i).widget().setParent(None)
            
            # Get Data
            eval_record = plan.get_eval_record()
            if not eval_record:
                raise ValueError("No evaluation record found.")
                
            epoch_data = trainer.get_dataset().get_epoch_data()
            
            # Instantiate Visualizer
            # VisualizerType.SaliencyMap is a class
            visualizer = VisualizerType.SaliencyMap.value(
                eval_record, epoch_data
            )
            
            # Get Figure
            self.fig = visualizer.get_plt(method=method, absolute=absolute)
            
            if self.fig:
                # Apply Dark Theme
                self.fig.patch.set_facecolor('#2d2d2d')
                for ax in self.fig.axes:
                    ax.set_facecolor('#2d2d2d')
                    ax.tick_params(colors='#cccccc')
                    for spine in ax.spines.values():
                        spine.set_color('#555555')
                    ax.xaxis.label.set_color('#cccccc')
                    ax.yaxis.label.set_color('#cccccc')
                    ax.title.set_color('#cccccc')
                
                # Re-create canvas
                self.canvas = FigureCanvas(self.fig)
                self.plot_layout.addWidget(self.canvas)
            else:
                lbl = QLabel("No data available.")
                lbl.setStyleSheet("color: #999;")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.plot_layout.addWidget(lbl)
                
        except Exception as e:
            print(f"Error plotting saliency map: {e}")
            lbl = QLabel(f"Error: {e}")
            lbl.setStyleSheet("color: #ef5350;")
            self.plot_layout.addWidget(lbl)
