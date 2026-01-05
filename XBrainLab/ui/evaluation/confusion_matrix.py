from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QGroupBox
)
from PyQt6.QtCore import QTimer, Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from XBrainLab.backend.visualization import PlotType

class ConfusionMatrixWidget(QWidget):
    def __init__(self, parent, trainers):
        super().__init__(parent)
        self.trainers = trainers
        self.trainer_map = {t.get_name(): t for t in trainers}
        self.plot_type = PlotType.CONFUSION
        
        self.current_plan = None
        self.current_fig = None
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Controls
        ctrl_layout = QHBoxLayout()
        lbl = QLabel("Plan:")
        lbl.setStyleSheet("color: #cccccc;")
        ctrl_layout.addWidget(lbl)
        
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
        self.plan_combo.currentTextChanged.connect(self.on_plan_select)
        ctrl_layout.addWidget(self.plan_combo)
        
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
        self.ax.text(0.5, 0.5, "Select a plan to view Confusion Matrix", 
                     color='#666666', ha='center', va='center')
        self.ax.axis('off')
        
        self.plot_layout.addWidget(self.canvas)
        layout.addWidget(self.plot_container, stretch=1)

    def on_plan_select(self, plan_name):
        if plan_name == "Select a plan" or plan_name not in self.trainer_map:
            return
            
        trainer = self.trainer_map[plan_name]
        plans = trainer.get_plans()
        if not plans:
            return
            
        # For simplicity, take the first plan or average? 
        # Usually confusion matrix is for a specific model run.
        # Let's take the best plan or the first one.
        # Ideally we should let user select sub-plan (repeat), but for now let's pick the first one to keep UI simple.
        target_plan = plans[0] 
        
        self.plot_matrix(target_plan)

    def plot_matrix(self, plan):
        try:
            # Clear previous
            for i in reversed(range(self.plot_layout.count())): 
                self.plot_layout.itemAt(i).widget().setParent(None)
                
            # Create new figure using backend logic
            # The backend returns a matplotlib Figure
            target_func = getattr(plan, self.plot_type.value)
            # We need to pass params. Confusion matrix usually needs none or standard ones.
            # Let's try calling it.
            # Note: The backend might return a figure with default white background.
            # We might need to style it after creation.
            
            self.fig = target_func()
            
            if self.fig:
                # Apply Dark Theme
                self.fig.patch.set_facecolor('#2d2d2d')
                ax = self.fig.gca()
                ax.set_facecolor('#2d2d2d')
                
                # Style text elements
                for text in self.fig.findobj(match=lambda x: hasattr(x, 'set_color')):
                    # This is a bit aggressive, might overwrite heatmap text colors.
                    # Better to target specific elements if possible.
                    # For confusion matrix, the heatmap text needs to be readable against the colors.
                    # The titles and labels should be light.
                    pass

                # Re-create canvas
                self.canvas = FigureCanvas(self.fig)
                self.plot_layout.addWidget(self.canvas)
            else:
                lbl = QLabel("No data available for this plan.")
                lbl.setStyleSheet("color: #999;")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.plot_layout.addWidget(lbl)
                
        except Exception as e:
            print(f"Error plotting matrix: {e}")
            lbl = QLabel(f"Error: {e}")
            lbl.setStyleSheet("color: #ef5350;")
            self.plot_layout.addWidget(lbl)
