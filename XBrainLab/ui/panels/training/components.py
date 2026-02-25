"""Reusable metric-tab component for training loss and accuracy plots."""

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from XBrainLab.ui.styles.theme import Theme


class MetricTab(QWidget):
    """A tab component containing a Matplotlib plot for a specific training metric.
    Updates dynamically with epoch data.
    """

    def __init__(self, metric_name, color=Theme.ACCENT_SUCCESS):
        """Initialize the metric tab.

        Args:
            metric_name: Display name of the metric (e.g., ``'Accuracy'``,
                ``'Loss'``).
            color: Matplotlib-compatible color string for the train curve.

        """
        super().__init__()
        self.metric_name = metric_name
        self.color = color
        self.init_ui()

    def init_ui(self):
        """Build the layout with a matplotlib figure and empty axes."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)

        # 1. Plot
        self.fig = Figure(figsize=(5, 3), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)

        # Apply Theme
        Theme.apply_matplotlib_dark_theme(self.fig, ax=self.ax)

        self.ax.set_title(f"{self.metric_name} vs Epoch")
        self.ax.set_xlabel("Epoch")

        # Add Units
        ylabel = self.metric_name
        if "Accuracy" in self.metric_name:
            ylabel += " (%)"
        self.ax.set_ylabel(ylabel)

        self.ax.grid(
            True,
            linestyle="--",
            alpha=0.3,
            color=Theme.TEXT_SECONDARY,
        )  # Subtle grid
        self.fig.tight_layout()
        layout.addWidget(self.canvas, stretch=1)

        self.epochs = []
        self.train_vals = []
        self.val_vals = []

    def update_plot(self, epoch, train_val, val_val):
        """Append a new data point and redraw the plot.

        Args:
            epoch: The epoch number (1-based).
            train_val: Training metric value for this epoch.
            val_val: Validation metric value for this epoch.

        """
        self.epochs.append(epoch)
        self.train_vals.append(train_val)
        self.val_vals.append(val_val)

        self.ax.clear()

        # Plot Lines
        self.ax.plot(
            self.epochs,
            self.train_vals,
            marker="o",
            markersize=4,
            linestyle="-",
            color=self.color,
            label=f"Train {self.metric_name}",
        )
        # Improved Validation Line: Dashed, lighter color, smaller dot marker
        self.ax.plot(
            self.epochs,
            self.val_vals,
            marker="o",
            markersize=4,
            linestyle="--",
            color=Theme.TEXT_SECONDARY,
            label=f"Val {self.metric_name}",
        )

        self.ax.set_title(f"{self.metric_name} vs Epoch")
        self.ax.set_xlabel("Epoch")

        # Add Units
        ylabel = self.metric_name
        if "Accuracy" in self.metric_name:
            ylabel += " (%)"
        self.ax.set_ylabel(ylabel)

        self.ax.grid(True, linestyle="--", alpha=0.3, color=Theme.TEXT_SECONDARY)

        # Create Legend (Standard colors, will be themed)
        self.ax.legend(facecolor=Theme.BACKGROUND_MID, edgecolor=Theme.TEXT_MUTED)

        # Apply Theme (Handles styles for axes, ticks, spines, labels, and legend)
        Theme.apply_matplotlib_dark_theme(self.fig, ax=self.ax)

        self.canvas.draw()

    def clear(self):
        """Clear the plot and reset accumulated data history."""
        # Clear plot
        self.ax.clear()
        self.ax.set_title(f"{self.metric_name} vs Epoch")
        self.ax.set_xlabel("Epoch")

        # Add Units
        ylabel = self.metric_name
        if "Accuracy" in self.metric_name:
            ylabel += " (%)"
        self.ax.set_ylabel(ylabel)

        self.ax.grid(True, linestyle="--", alpha=0.3, color=Theme.TEXT_SECONDARY)
        self.canvas.draw()

        # Clear history data
        if hasattr(self, "epochs"):
            self.epochs = []
        if hasattr(self, "train_vals"):
            self.train_vals = []
        if hasattr(self, "val_vals"):
            self.val_vals = []
