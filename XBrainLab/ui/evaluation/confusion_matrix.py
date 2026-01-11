from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel
)
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from XBrainLab.backend.visualization import PlotType

class ConfusionMatrixWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plot_type = PlotType.CONFUSION
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
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
        self.ax.text(0.5, 0.5, "Select a group to view Confusion Matrix", 
                     color='#666666', ha='center', va='center')
        self.ax.axis('off')
        
        self.plot_layout.addWidget(self.canvas)
        layout.addWidget(self.plot_container)

    def update_plot(self, plan, show_percentage: bool = False):
        """Update the confusion matrix plot.
        
        Args:
            plan: TrainingPlanHolder or TrainRecord
            show_percentage: Whether to show percentage
        """
        try:
            # Clear previous
            for i in reversed(range(self.plot_layout.count())): 
                self.plot_layout.itemAt(i).widget().setParent(None)
                
            # Get the plotting function
            # If plan is TrainingPlanHolder, it might not have get_confusion_figure directly?
            # Wait, TrainingPlanHolder usually delegates or we need to pass TrainRecord.
            # The backend method get_confusion_figure is in TrainRecord.
            # So 'plan' argument here should ideally be a TrainRecord.
            
            if hasattr(plan, 'get_confusion_figure'):
                target_func = plan.get_confusion_figure
            elif hasattr(plan, 'get_plans'):
                # Fallback if a PlanHolder is passed: use the first record
                # But ideally the caller should pass the specific record.
                records = plan.get_plans()
                if records:
                    target_func = records[0].get_confusion_figure
                else:
                    raise ValueError("Plan has no records")
            else:
                # Try getattr with PlotType value just in case
                target_func = getattr(plan, self.plot_type.value, None)
                
            if not target_func:
                raise ValueError(f"Object {type(plan)} has no method for confusion matrix")

            # Call the function with show_percentage
            self.fig = target_func(show_percentage=show_percentage)
            
            if self.fig:
                # Apply Dark Theme
                self.fig.patch.set_facecolor('#2d2d2d')
                ax = self.fig.gca()
                ax.set_facecolor('#2d2d2d')
                
                # Style text elements
                # Axis labels and title
                ax.title.set_color('#cccccc')
                ax.xaxis.label.set_color('#cccccc')
                ax.yaxis.label.set_color('#cccccc')
                ax.tick_params(axis='x', colors='#cccccc')
                ax.tick_params(axis='y', colors='#cccccc')
                
                # Re-create canvas
                self.canvas = FigureCanvas(self.fig)
                self.plot_layout.addWidget(self.canvas)
            else:
                self._show_message("No data available for this plan.")
                
        except Exception as e:
            print(f"Error plotting matrix: {e}")
            self._show_message(f"Error: {e}", color="#ef5350")

    def _show_message(self, message, color="#999"):
        lbl = QLabel(message)
        lbl.setStyleSheet(f"color: {color};")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_layout.addWidget(lbl)

