import contextlib
from typing import Any

import matplotlib
from PyQt6.QtWidgets import QDialog, QSizePolicy, QVBoxLayout

# Only force QtAgg if we are not in a headless testing environment (Agg)
if matplotlib.get_backend().lower() != "agg":
    with contextlib.suppress(ImportError):
        matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar


class SinglePlotWindow(QDialog):
    PLOT_COUNTER = 0

    def __init__(self, parent, figsize=None, dpi=None, title="Plot"):
        super().__init__(parent)
        self.setWindowTitle(title)

        if figsize is None:
            figsize = (6.4, 4.8)
        if dpi is None:
            dpi = 100

        self.figsize = figsize
        self.dpi = dpi

        self.main_layout = QVBoxLayout(self)
        self.figure_canvas = None
        self.plot_number: str | None = None
        self.fig_param: dict[str, Any] = {}
        self.toolbar: Any = None

        self.init_figure()

        # Resize logic (approximate)
        width = int(figsize[0] * dpi)
        height = int(figsize[1] * dpi)
        self.resize(width + 50, height + 100)  # Add padding for toolbar/margins

    def active_figure(self):
        plt.figure(self.plot_number)

    def init_figure(self):
        self.plot_number = f"SinglePlotWindow-{SinglePlotWindow.PLOT_COUNTER}"
        SinglePlotWindow.PLOT_COUNTER += 1

        figure = plt.figure(num=self.plot_number, figsize=self.figsize, dpi=self.dpi)
        self.set_figure(figure, self.figsize, self.dpi)
        self.active_figure()

    def get_figure_params(self):
        # Check if figure needs re-initialization (e.g., if closed or cleared).
        if self.plot_number is None or not plt.fignum_exists(self.plot_number):
            self.init_figure()
        return self.fig_param

    def clear_figure(self):
        plt.clf()
        self.redraw()

    def show_drawing(self):
        self.clear_figure()
        plt.text(0.5, 0.5, "Drawing.", ha="center", va="center")
        self.redraw()

    def empty_data_figure(self):
        self.clear_figure()
        plt.text(0.5, 0.5, "No Data Available", ha="center", va="center")
        self.redraw()

    def set_figure(self, figure, figsize, dpi):
        if self.figure_canvas:
            self.main_layout.removeWidget(self.figure_canvas)
            self.figure_canvas.setParent(None)
            self.figure_canvas.deleteLater()
            if hasattr(self, "toolbar"):
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
        if self.figure_canvas:
            self.fig_param["fig"].tight_layout()
            self.figure_canvas.draw()
