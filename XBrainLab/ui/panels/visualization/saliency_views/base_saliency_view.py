import logging
import threading
import traceback
from collections.abc import Callable
from contextlib import suppress

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QSizePolicy, QVBoxLayout, QWidget

from XBrainLab.ui.styles.theme import Theme

logger = logging.getLogger(__name__)
_MATPLOTLIB_RENDER_LOCK = threading.Lock()


class BaseSaliencyView(QWidget):
    """Abstract base class for all Saliency views (Map, Spectrogram, Topo, 3D).
    Standardizes layout, error handling, and placeholder display.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = (
            parent.main_window if parent and hasattr(parent, "main_window") else None
        )
        # Try to resolve controller from parent panel (VisualizationPanel)
        self.controller = (
            parent.controller if parent and hasattr(parent, "controller") else None
        )
        self._plot_generation = 0

        self.init_ui()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Matplotlib Canvas (Default, subclasses can override)
        self.fig: Figure | None = Figure(figsize=(5, 4), dpi=100)
        self.canvas: FigureCanvas | None = FigureCanvas(self.fig)

        # Apply Theme
        Theme.apply_matplotlib_dark_theme(self.fig)

        self.main_layout.addWidget(self.canvas)

        # 2. Error Message (Hidden by default)
        self.error_label = QLabel()
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.setContentsMargins(16, 8, 16, 8)
        self.error_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.error_label.setStyleSheet(
            f"color: {Theme.ACCENT_ERROR}; font-size: 14px; font-weight: bold;",
        )
        self.error_label.hide()
        self.main_layout.addWidget(self.error_label)

    def show_error(self, message):
        """Display an error message overlaid on the view."""
        self._cancel_pending_render()
        self._display_error(message)

    def _display_error(self, message):
        if self.canvas is not None:
            self.canvas.hide()
        self.error_label.setStyleSheet(
            f"color: {Theme.ACCENT_ERROR}; font-size: 14px; font-weight: bold;",
        )
        self.error_label.setText(f"Error: {message}")
        self.error_label.show()

    def show_message(self, message):
        """Display a neutral placeholder message over the view."""
        self._cancel_pending_render()
        self._display_message(message)

    def _display_message(self, message):
        if self.canvas is not None:
            self.canvas.hide()
        self.error_label.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; font-size: 14px; font-weight: bold;",
        )
        self.error_label.setText(message)
        self.error_label.show()

    def clear_plot(self):
        """Clear the plot and reset error state."""
        self.error_label.hide()
        self.error_label.setStyleSheet(
            f"color: {Theme.ACCENT_ERROR}; font-size: 14px; font-weight: bold;",
        )
        if self.canvas is not None:
            self.canvas.show()
        if self.fig is None or self.canvas is None:
            return
        self.fig.clear()
        self._draw_canvas_now()

    def _draw_canvas_now(self) -> None:
        if self.canvas is None:
            return
        # Qt can destroy the backing widget while saliency tabs are being
        # replaced. Treat late canvas draws as stale rather than crashing.
        with suppress(RuntimeError):
            self.canvas.draw()

    def update_view(self, result, params):
        """Update the view with calculation results.
        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def _close_current_figure(self) -> None:
        if self.fig is not None:
            plt.close(self.fig)
            self.fig = None

    def _release_canvas(self) -> None:
        if self.canvas is None:
            return
        canvas = self.canvas
        if hasattr(canvas, "_draw_pending"):
            canvas._draw_pending = False
        app = QApplication.instance()
        if app is not None:
            with suppress(RuntimeError):
                app.processEvents()
        self.main_layout.removeWidget(canvas)
        canvas.setParent(None)
        canvas.hide()
        canvas.close()
        self.canvas = None

    def _replace_figure(self, figure: Figure) -> None:
        self._release_canvas()
        self._close_current_figure()
        self.fig = figure
        Theme.apply_matplotlib_dark_theme(self.fig)
        self.canvas = FigureCanvas(self.fig)
        self.main_layout.insertWidget(0, self.canvas)
        self.error_label.hide()

    def _render_figure_async(
        self,
        render_fn: Callable[[], Figure | None],
        *,
        error_context: str,
    ) -> None:
        """Render a Matplotlib figure on the UI thread and install the result."""
        self._plot_generation += 1
        generation = self._plot_generation
        self.clear_plot()
        self._display_message("Rendering saliency...")
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

        def _locked_render() -> Figure | None:
            with _MATPLOTLIB_RENDER_LOCK:
                return render_fn()

        try:
            figure = _locked_render()
        except Exception as exc:
            self._handle_plot_error(
                generation,
                error_context,
                (type(exc), exc, traceback.format_exc()),
            )
        else:
            self._handle_plot_result(generation, figure)
        finally:
            self._finish_plot_render(generation)

    def _handle_plot_result(self, generation: int, figure: Figure | None) -> None:
        if generation != self._plot_generation:
            if figure is not None:
                plt.close(figure)
            return
        if figure is None:
            self._display_error("No Data Available")
            return
        self._replace_figure(figure)

    def _handle_plot_error(self, generation: int, context: str, error: tuple) -> None:
        if generation != self._plot_generation:
            return
        _, value, formatted_traceback = error
        logger.error("Error rendering %s: %s\n%s", context, value, formatted_traceback)
        self._display_error(str(value))

    def _finish_plot_render(self, generation: int) -> None:
        if generation == self._plot_generation:
            return

    def _cancel_pending_render(self) -> None:
        self._plot_generation += 1

    def closeEvent(self, event):  # noqa: N802
        """Release matplotlib figure and canvas widgets to prevent leaks."""
        self._cancel_pending_render()
        self._release_canvas()
        self._close_current_figure()
        super().closeEvent(event)
