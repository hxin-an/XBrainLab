import traceback

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import VisualizerType


class SaliencyTopographicMapWidget(QWidget):
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
        self.fig.patch.set_facecolor("#2d2d2d")
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#2d2d2d")
        self.ax.text(
            0.5,
            0.5,
            "Select a plan and method to visualize",
            color="#666666",
            ha="center",
            va="center",
        )
        self.ax.axis("off")

        self.plot_layout.addWidget(self.canvas)
        layout.addWidget(self.plot_container, stretch=1)

    def show_error(self, msg):
        for i in reversed(range(self.plot_layout.count())):
            item = self.plot_layout.itemAt(i)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)
        lbl = QLabel(msg)
        lbl.setStyleSheet("color: #ef5350; font-size: 14px; font-weight: bold;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_layout.addWidget(lbl)

    def show_message(self, msg):
        for i in reversed(range(self.plot_layout.count())):
            item = self.plot_layout.itemAt(i)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)
        lbl = QLabel(msg)
        lbl.setStyleSheet("color: #ff9800; font-size: 16px; font-weight: bold;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_layout.addWidget(lbl)

    def update_plot(self, plan, trainer, method, absolute, eval_record):
        try:
            # Clear previous
            for i in reversed(range(self.plot_layout.count())):
                item = self.plot_layout.itemAt(i)
                if item:
                    w = item.widget()
                    if w:
                        w.setParent(None)

            # Get Data
            if eval_record is None:
                eval_record = plan.get_eval_record()

            if not eval_record:
                raise ValueError("No evaluation record found.")  # noqa: TRY301

            epoch_data = trainer.get_dataset().get_epoch_data()

            # Montage Check
            if epoch_data.get_montage_position() is None:
                self.show_message(
                    "Please Set Montage First\n(Go to Configuration -> Set Montage)"
                )
                return

            # Instantiate Visualizer
            # Clear existing matplotlib figures to avoid conflict with previous canvas
            plt.close("all")
            plt.figure()

            visualizer = VisualizerType.SaliencyTopoMap.value(eval_record, epoch_data)

            # Get Figure
            self.fig = visualizer.get_plt(method=method, absolute=absolute)

            if self.fig:
                # Apply Dark Theme
                self.fig.patch.set_facecolor("#2d2d2d")
                for _ax in self.fig.axes:
                    # Topomap axes are complex, but we can try to style what we can
                    # ax.set_facecolor('#2d2d2d') # Often fails for topomap
                    pass

                # Re-create canvas
                self.canvas = FigureCanvas(self.fig)
                self.plot_layout.addWidget(self.canvas)
            else:
                self.show_error("No Data Available")

        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error plotting topomap: {e}", exc_info=True)
            self.show_error(f"Error: {e}")
