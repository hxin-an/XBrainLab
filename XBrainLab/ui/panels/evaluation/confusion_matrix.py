"""Confusion matrix widget for displaying classification results."""

import warnings
from contextlib import suppress
from typing import Any, Literal, cast

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import PlotType
from XBrainLab.ui.styles.theme import Theme

CONFUSION_MATRIX_LOAD_FAILED_TEXT = (
    "Confusion matrix could not be displayed. "
    "Select another completed run or refresh Evaluation."
)


class _ResponsiveFigureCanvas(FigureCanvas):
    """Reflow figure margins after Qt assigns a narrower canvas geometry."""

    def __init__(self, figure: Figure) -> None:
        super().__init__(figure)
        self._responsive_tick_state: dict[
            object,
            tuple[float, Literal["left", "center", "right"], float, str],
        ] = {}

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if not any(axis.axison for axis in self.figure.axes):
            return
        self.fit_layout()

    def fit_layout(self) -> None:
        """Fit labels and margins to the current canvas without losing wide layout."""
        primary_axis = next(
            (axis for axis in self.figure.axes if axis.axison),
            None,
        )
        if primary_axis is not None:
            labels = [
                label for label in primary_axis.get_xticklabels() if label.get_text()
            ]
            if self.width() < 480:
                rotation = 70 if self.width() < 320 else 45
                for label in labels:
                    if label not in self._responsive_tick_state:
                        self._responsive_tick_state[label] = (
                            float(label.get_rotation()),
                            cast(
                                Literal["left", "center", "right"],
                                label.get_horizontalalignment(),
                            ),
                            float(label.get_fontsize()),
                            str(label.get_text()),
                        )
                    label.set_rotation(rotation)
                    label.set_horizontalalignment("right")
                    label.set_rotation_mode("anchor")
                    label.set_fontsize(8)
            else:
                for label in labels:
                    original = self._responsive_tick_state.pop(label, None)
                    if original is not None:
                        rotation, alignment, font_size, text = original
                        label.set_text(text)
                        label.set_rotation(rotation)
                        label.set_horizontalalignment(alignment)
                        label.set_rotation_mode("default")
                        label.set_fontsize(font_size)
        try:
            # Qt can briefly assign a canvas geometry too small for Matplotlib's
            # solver while docks are opening or closing. The previous valid
            # layout remains usable, so contain only that known transient warning.
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r"Tight layout not applied\..*",
                    category=UserWarning,
                )
                self.figure.tight_layout(pad=1.0)
        except Exception as layout_error:
            logger.warning(
                "Skipping confusion matrix responsive layout: %s",
                layout_error,
            )
        if hasattr(self, "_draw_pending"):
            self._draw_pending = False
        with suppress(RuntimeError):
            self.draw()


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
        self.fig: Figure | None = Figure(figsize=(5, 4), dpi=100)
        self.canvas: FigureCanvas | None = _ResponsiveFigureCanvas(self.fig)
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
            self._clear_plot_widgets()
            self._close_current_figure()

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
                self.canvas = _ResponsiveFigureCanvas(self.fig)
                self.plot_layout.addWidget(self.canvas)
                self.fit_plot_to_canvas()
            else:
                self._show_message("No data available for this plan.")

        except Exception as e:
            logger.error("Error plotting matrix: %s", e, exc_info=True)
            self._show_message(CONFUSION_MATRIX_LOAD_FAILED_TEXT, color=Theme.ERROR)

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

    def _clear_plot_widgets(self) -> None:
        for i in reversed(range(self.plot_layout.count())):
            item = self.plot_layout.itemAt(i)
            if item:
                widget = item.widget()
                if widget:
                    if hasattr(widget, "_draw_pending"):
                        cast(Any, widget)._draw_pending = False
                    widget.setParent(None)
                    with suppress(RuntimeError):
                        widget.close()
                    widget.deleteLater()
        self.canvas = None

    def _close_current_figure(self) -> None:
        if self.fig is not None:
            plt.close(self.fig)
            self.fig = None

    def fit_plot_to_canvas(self) -> None:
        """Recompute plot margins for the canvas' current on-screen width."""
        if self.fig is None or self.canvas is None:
            return
        self.plot_layout.activate()
        if isinstance(self.canvas, _ResponsiveFigureCanvas):
            self.canvas.fit_layout()

    def closeEvent(self, event):  # noqa: N802
        self._clear_plot_widgets()
        self._close_current_figure()
        super().closeEvent(event)
