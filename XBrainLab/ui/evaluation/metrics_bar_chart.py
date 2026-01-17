import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class MetricsBarChartWidget(QWidget):
    def __init__(self, parent=None):
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
            0.5, 0.5, "No Data Available", color="#666666", ha="center", va="center"
        )
        self.ax.axis("off")

        self.plot_layout.addWidget(self.canvas)
        layout.addWidget(self.plot_container)

    def update_plot(self, metrics):
        """Update the bar chart with metrics data.

        Args:
            metrics: Dictionary containing per-class metrics from EvalRecord.
        """
        try:
            self.ax.clear()
            self.ax.set_facecolor("#2d2d2d")

            if not metrics:
                self.ax.text(
                    0.5,
                    0.5,
                    "No Data Available",
                    color="#666666",
                    ha="center",
                    va="center",
                )
                self.ax.axis("off")
                self.canvas.draw()
                return

            # Extract data
            classes = [k for k in metrics if isinstance(k, int)]
            classes.sort()

            if not classes:
                self.ax.text(
                    0.5, 0.5, "No Class Data", color="#666666", ha="center", va="center"
                )
                self.ax.axis("off")
                self.canvas.draw()
                return

            precision = [metrics[c]["precision"] for c in classes]
            recall = [metrics[c]["recall"] for c in classes]
            f1 = [metrics[c]["f1-score"] for c in classes]

            x = np.arange(len(classes))
            width = 0.25

            # Plot Bars
            self.ax.bar(x - width, precision, width, label="Precision", color="#4CAF50")
            self.ax.bar(x, recall, width, label="Recall", color="#2196F3")
            self.ax.bar(x + width, f1, width, label="F1-Score", color="#FFC107")

            # Styling
            self.ax.set_ylabel("Score", color="#cccccc")
            self.ax.set_title("Per-Class Metrics", color="#cccccc")
            self.ax.set_xticks(x)
            self.ax.set_xticklabels([f"Class {c}" for c in classes], color="#cccccc")
            self.ax.set_ylim(0, 1.1)

            # Legend
            legend = self.ax.legend(facecolor="#2d2d2d", edgecolor="#cccccc")
            for text in legend.get_texts():
                text.set_color("#cccccc")

            # Grid and Spines
            self.ax.grid(True, axis="y", linestyle="--", alpha=0.3, color="#666666")
            self.ax.spines["bottom"].set_color("#cccccc")
            self.ax.spines["top"].set_color("#cccccc")
            self.ax.spines["right"].set_color("#cccccc")
            self.ax.spines["left"].set_color("#cccccc")
            self.ax.tick_params(axis="x", colors="#cccccc")
            self.ax.tick_params(axis="y", colors="#cccccc")

            self.fig.tight_layout()
            self.canvas.draw()

        except Exception as e:
            print(f"Error plotting bar chart: {e}")
