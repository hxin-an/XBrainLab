from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from XBrainLab.backend.visualization import VisualizerType


class SaliencyMapWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
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
        self.ax.text(0.5, 0.5, "Select a plan and method to visualize",
                     color='#666666', ha='center', va='center')
        self.ax.axis('off')

        self.plot_layout.addWidget(self.canvas)
        layout.addWidget(self.plot_container, stretch=1)

    def show_error(self, msg):
        for i in reversed(range(self.plot_layout.count())):
            self.plot_layout.itemAt(i).widget().setParent(None)
        lbl = QLabel(msg)
        lbl.setStyleSheet("color: #ef5350; font-size: 14px; font-weight: bold;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_layout.addWidget(lbl)

    def update_plot(self, plan, trainer, method, absolute, eval_record):
        try:
            # Clear previous
            for i in reversed(range(self.plot_layout.count())):
                self.plot_layout.itemAt(i).widget().setParent(None)

            # Get Data
            if eval_record is None:
                eval_record = plan.get_eval_record()

            if not eval_record:
                raise ValueError("No evaluation record found.")

            epoch_data = trainer.get_dataset().get_epoch_data()

            # Instantiate Visualizer
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
                self.show_error("No Data Available")

        except Exception as e:
            print(f"Error plotting saliency map: {e}")
            self.show_error(f"Error: {e}")
