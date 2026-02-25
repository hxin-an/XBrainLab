"""Confusion matrix widget for displaying classification results."""

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import PlotType
from XBrainLab.ui.styles.theme import Theme


class ConfusionMatrixWidget(QWidget):
    """Widget for rendering a confusion matrix plot.

    Displays per-class classification performance using a color-coded
    matrix. Supports optional percentage display.

    Attributes:
        plot_type: ``PlotType.CONFUSION`` identifier for the plot kind.
        fig: Current ``matplotlib.figure.Figure`` instance.
        canvas: ``FigureCanvas`` embedding the figure into Qt.
        ax: The matplotlib ``Axes`` used for the initial placeholder.

    """

    def __init__(self, parent=None):
        """Initialize the confusion matrix widget.

        Args:
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self.plot_type = PlotType.CONFUSION
        self.init_ui()

    def init_ui(self):
        """Build the initial layout with a placeholder plot."""
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
            "Select a group to view Confusion Matrix",
            color=Theme.TEXT_SECONDARY,
            ha="center",
            va="center",
        )
        self.ax.axis("off")

        self.plot_layout.addWidget(self.canvas)
        layout.addWidget(self.plot_container)

    def update_plot(self, plan, show_percentage: bool = False):
        """Update the confusion matrix plot.

        Args:
            plan: TrainingPlanHolder or TrainRecord
            show_percentage: Whether to show percentage

        """
        try:
            for i in reversed(range(self.plot_layout.count())):
                item = self.plot_layout.itemAt(i)
                if item:
                    w = item.widget()
                    if w:
                        w.setParent(None)

            # Close old matplotlib figure to prevent memory leak
            if hasattr(self, "fig") and self.fig is not None:
                plt.close(self.fig)

            if plan is None:
                self._show_message("No Data Available")
                return

            # Get the plotting function
            # If plan is TrainingPlanHolder, it might not have get_confusion_figure
            # directly?
            # Wait, TrainingPlanHolder usually delegates or we need to pass TrainRecord.
            # The backend method get_confusion_figure is in TrainRecord.
            # So 'plan' argument here should ideally be a TrainRecord.

            if hasattr(plan, "get_confusion_figure"):
                target_func = plan.get_confusion_figure
            elif hasattr(plan, "get_plans"):
                # Fallback if a PlanHolder is passed: use the first record
                # But ideally the caller should pass the specific record.
                records = plan.get_plans()
                if records:
                    target_func = records[0].get_confusion_figure
                else:
                    raise ValueError("Plan has no records")  # noqa: TRY301
            else:
                # Try getattr with PlotType value just in case
                target_func = getattr(plan, self.plot_type.value, None)

            if not target_func:
                raise ValueError(  # noqa: TRY301
                    f"Object {type(plan)} has no method for confusion matrix",
                )

            # Call the function with show_percentage
            self.fig = target_func(show_percentage=show_percentage)

            if self.fig:
                # Apply Dark Theme
                Theme.apply_matplotlib_dark_theme(self.fig)

                # Re-create canvas
                self.canvas = FigureCanvas(self.fig)
                self.plot_layout.addWidget(self.canvas)
            else:
                self._show_message("No data available for this plan.")

        except Exception as e:
            logger.error("Error plotting matrix: %s", e, exc_info=True)
            self._show_message(f"Error: {e}", color=Theme.ERROR)

    def _show_message(self, message, color=Theme.TEXT_MUTED):
        """Display a centered text message in place of the plot.

        Args:
            message: The text to display.
            color: CSS color string for the message text.

        """
        lbl = QLabel(message)
        lbl.setStyleSheet(f"color: {color};")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_layout.addWidget(lbl)
