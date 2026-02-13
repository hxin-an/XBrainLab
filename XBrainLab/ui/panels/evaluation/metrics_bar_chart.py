import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from XBrainLab.ui.styles.theme import Theme


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
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)

        Theme.apply_matplotlib_dark_theme(self.fig, ax=self.ax)

        self.ax.text(
            0.5,
            0.5,
            "No Data Available",
            color=Theme.TEXT_SECONDARY,
            ha="center",
            va="center",
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

            # Theme applied later, but we need to set initial facecolor if clearing?
            # Actually Theme.apply_matplotlib_dark_theme handles it.
            # We will call apply at end.

            if not metrics:
                self.ax.text(
                    0.5,
                    0.5,
                    "No Data Available",
                    color=Theme.TEXT_MUTED,
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
                    0.5,
                    0.5,
                    "No Class Data",
                    color=Theme.TEXT_MUTED,
                    ha="center",
                    va="center",
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
            # Keep semantic colors for bars as they are data-representative
            # (Precision/Recall/F1)
            self.ax.bar(
                x - width,
                precision,
                width,
                label="Precision",
                color=Theme.CHART_SECONDARY,
            )
            self.ax.bar(x, recall, width, label="Recall", color=Theme.CHART_PRIMARY)
            self.ax.bar(
                x + width, f1, width, label="F1-Score", color=Theme.CHART_TERTIARY
            )

            # Apply Theme
            Theme.apply_matplotlib_dark_theme(self.fig, ax=self.ax)

            # Styling
            self.ax.set_ylabel("Score")
            self.ax.set_title("Per-Class Metrics")
            self.ax.set_xticks(x)
            self.ax.set_xticklabels([f"Class {c}" for c in classes])
            self.ax.tick_params(axis="x", colors=Theme.TEXT_PRIMARY)
            self.ax.tick_params(axis="y", colors=Theme.TEXT_PRIMARY)
            self.ax.set_ylim(0, 1.1)

            # Legend
            self.ax.legend(facecolor=Theme.BACKGROUND_MID, edgecolor=Theme.TEXT_MUTED)

            # Grid
            self.ax.grid(
                True, axis="y", linestyle="--", alpha=0.3, color=Theme.TEXT_MUTED
            )

            self.fig.tight_layout()
            self.canvas.draw()

        except Exception as e:
            print(f"Error plotting bar chart: {e}")
