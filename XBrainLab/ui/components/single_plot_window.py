"""Single plot window dialog wrapping a Matplotlib figure canvas."""

import contextlib
from typing import Any

import matplotlib
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout

# Only force QtAgg if we are not in a headless testing environment (Agg)
if matplotlib.get_backend().lower() != "agg":
    with contextlib.suppress(ImportError):
        matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

from XBrainLab.ui.core.base_dialog import BaseDialog


class SinglePlotWindow(BaseDialog):
    """A dialog window hosting a single Matplotlib figure with navigation toolbar.

    Manages figure creation, canvas embedding via ``FigureCanvasQTAgg``,
    and toolbar integration. Serves as a base class for specialized
    plot windows.

    Attributes:
        PLOT_COUNTER: Class-level counter for unique plot identifiers.
        figsize: Tuple ``(width, height)`` in inches.
        dpi: Dots per inch for the figure.
        figure_canvas: The embedded ``FigureCanvasQTAgg``, or ``None``.
        plot_number: Unique Matplotlib figure identifier string.
        fig_param: Dictionary of current figure parameters.
        toolbar: The ``NavigationToolbar2QT`` instance.
    """

    PLOT_COUNTER: int = 0

    def __init__(self, parent, figsize=None, dpi=None, title="Plot"):
        """Initialize the single plot window.

        Args:
            parent: Parent widget.
            figsize: Optional figure size as ``(width, height)`` in inches.
                Defaults to ``(6.4, 4.8)``.
            dpi: Optional dots-per-inch for the figure. Defaults to 100.
            title: Window title string.
        """
        if figsize is None:
            figsize = (6.4, 4.8)
        if dpi is None:
            dpi = 100

        self.figsize = figsize
        self.dpi = dpi

        self.figure_canvas = None
        self.plot_number: str | None = None
        self.fig_param: dict[str, Any] = {}
        self.toolbar: Any = None

        # Call super last because it invokes init_ui which needs self.figsize/dpi
        super().__init__(parent, title=title)

    def init_ui(self):
        """Build the layout and initialize the Matplotlib figure canvas."""
        self.main_layout = QVBoxLayout(self)
        self.init_figure()

        # Resize logic (approximate)
        width = int(self.figsize[0] * self.dpi)
        height = int(self.figsize[1] * self.dpi)
        self.resize(width + 50, height + 100)  # Add padding for toolbar/margins

    def get_result(self):
        """Return dialog result (always ``None`` for view-only dialogs).

        Returns:
            ``None``.
        """
        # View-only dialog, no result
        return None

    def active_figure(self):
        """Activate this window's Matplotlib figure as the current figure."""
        plt.figure(self.plot_number)

    def init_figure(self):
        """Create a new Matplotlib figure and embed it in the canvas."""
        self.plot_number = f"SinglePlotWindow-{SinglePlotWindow.PLOT_COUNTER}"
        SinglePlotWindow.PLOT_COUNTER += 1

        figure = plt.figure(num=self.plot_number, figsize=self.figsize, dpi=self.dpi)
        self.set_figure(figure, self.figsize, self.dpi)
        self.active_figure()

    def get_figure_params(self):
        """Get or reinitialize the current figure parameters.

        Returns:
            Dictionary with ``"fig"``, ``"figsize"``, and ``"dpi"`` keys.
        """
        # Check if figure needs re-initialization (e.g., if closed or cleared).
        if self.plot_number is None or not plt.fignum_exists(self.plot_number):
            self.init_figure()
        return self.fig_param

    def clear_figure(self):
        """Clear the current figure and redraw the canvas."""
        self.active_figure()
        plt.clf()
        self.redraw()

    def show_drawing(self):
        """Display a 'Drawing.' placeholder text on the figure."""
        self.clear_figure()
        plt.text(0.5, 0.5, "Drawing.", ha="center", va="center")
        self.redraw()

    def empty_data_figure(self):
        """Display a 'No Data Available' placeholder on the figure."""
        self.clear_figure()
        plt.text(0.5, 0.5, "No Data Available", ha="center", va="center")
        self.redraw()

    def set_figure(self, figure, figsize, dpi):
        """Replace the current figure canvas with a new figure.

        Removes the existing canvas and toolbar, creates new ones from
        the provided figure, and adds them to the layout.

        Args:
            figure: The Matplotlib ``Figure`` object.
            figsize: Tuple ``(width, height)`` in inches.
            dpi: Dots per inch for the figure.
        """
        if self.figure_canvas:
            self.main_layout.removeWidget(self.figure_canvas)
            self.figure_canvas.setParent(None)
            self.figure_canvas.deleteLater()
            if self.toolbar:
                self.main_layout.removeWidget(self.toolbar)
                self.toolbar.setParent(None)
                self.toolbar.deleteLater()

        self.figure_canvas = FigureCanvasQTAgg(figure)
        self.figure_canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.figure_canvas.updateGeometry()

        self.toolbar = NavigationToolbar(self.figure_canvas, self)

        self.main_layout.addWidget(self.toolbar)
        self.main_layout.addWidget(self.figure_canvas)

        self.fig_param = {"fig": figure, "figsize": figsize, "dpi": dpi}

    def redraw(self):
        """Apply tight layout and redraw the figure canvas."""
        if self.figure_canvas:
            self.fig_param["fig"].tight_layout()
            self.figure_canvas.draw()

    def closeEvent(self, event):  # noqa: N802
        """Close the Matplotlib figure to prevent memory leaks."""
        if self.plot_number is not None and plt.fignum_exists(self.plot_number):
            plt.close(self.plot_number)
        super().closeEvent(event)
