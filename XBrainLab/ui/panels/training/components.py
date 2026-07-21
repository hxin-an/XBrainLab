"""Reusable metric-tab component for training loss and accuracy plots."""

from contextlib import suppress
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.styles.theme import Theme


class _OwnedDrawFigureCanvas(FigureCanvasQTAgg):
    """Qt canvas whose deferred redraw can be cancelled during teardown."""

    def __init__(self, figure: Figure) -> None:
        super().__init__(figure)
        self._draw_timer = QTimer(self)
        self._draw_timer.setSingleShot(True)
        self._draw_timer.timeout.connect(self._draw_idle)

    def draw_idle(self) -> None:
        if self._draw_pending or self._is_drawing:
            return
        self._draw_pending = True
        self._draw_timer.start(0)

    def _draw_idle(self) -> None:
        """Flush a queued redraw without touching a deleted Qt canvas."""
        if sip.isdeleted(self):
            self._draw_pending = False
            return
        with self._idle_draw_cntx():
            if not self._draw_pending:
                return
            self._draw_pending = False
            try:
                if sip.isdeleted(self) or self.height() <= 0 or self.width() <= 0:
                    return
                self.draw()
            except RuntimeError as error:
                if sip.isdeleted(self) or "has been deleted" in str(error):
                    return
                logger.exception("Training metric canvas redraw failed")
            except Exception:
                logger.exception("Training metric canvas redraw failed")

    def cancel_pending_draw(self) -> None:
        if not sip.isdeleted(self._draw_timer):
            self._draw_timer.stop()
            with suppress(TypeError, RuntimeError):
                self._draw_timer.timeout.disconnect(self._draw_idle)
        self._draw_pending = False


class MetricTab(QWidget):
    """A tab component containing a Matplotlib plot for a specific training metric.
    Updates dynamically with epoch data.
    """

    def __init__(self, metric_name, color=Theme.ACCENT_SUCCESS, parent=None):
        """Initialize the metric tab.

        Args:
            metric_name: Display name of the metric (e.g., ``'Accuracy'``,
                ``'Loss'``).
            color: Matplotlib-compatible color string for the train curve.

        """
        super().__init__(parent)
        self.metric_name = metric_name
        self.color = color
        self.init_ui()

    def init_ui(self):
        """Build the layout with a matplotlib figure and empty axes."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)

        self.empty_state_label = QLabel(
            "Training metrics will appear after the first epoch.",
            self,
        )
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.setWordWrap(True)
        self.empty_state_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.empty_state_label.setStyleSheet(
            f"color: {Theme.TEXT_MUTED}; background: transparent;"
        )
        layout.addWidget(self.empty_state_label, stretch=1)

        self.fig = Figure(figsize=(5, 3), dpi=100)
        self.canvas = _OwnedDrawFigureCanvas(self.fig)
        self.ax: Any = self.fig.add_subplot(111)

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
        Theme.apply_matplotlib_dark_theme(self.fig, ax=self.ax)
        self._fit_axes()
        layout.addWidget(self.canvas, stretch=1)
        self.canvas.hide()

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
        self._draw_series()

    def set_series(self, epochs, train_vals, val_vals):
        """Replace the full metric series and redraw once."""
        self.epochs = list(epochs)
        self.train_vals = list(train_vals)
        self.val_vals = list(val_vals)
        self._draw_series()

    def _draw_series(self) -> None:
        """Render the current metric series in one canvas pass."""
        if self.fig is None or self.canvas is None or self.ax is None:
            return
        self.ax.clear()

        # Plot Lines
        train_points = [
            (epoch_value, value)
            for epoch_value, value in zip(self.epochs, self.train_vals, strict=False)
            if value is not None
        ]
        val_points = [
            (epoch_value, value)
            for epoch_value, value in zip(self.epochs, self.val_vals, strict=False)
            if value is not None
        ]
        if not train_points and not val_points:
            self._set_empty_state_visible(True)
            return

        self._set_empty_state_visible(False)
        if train_points:
            xs, ys = zip(*train_points, strict=False)
            self.ax.plot(
                xs,
                ys,
                marker="o",
                markersize=4,
                linestyle="-",
                color=self.color,
                label=f"Train {self.metric_name}",
            )
        if val_points:
            xs, ys = zip(*val_points, strict=False)
            self.ax.plot(
                xs,
                ys,
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
        if train_points or val_points:
            self.ax.legend(facecolor=Theme.BACKGROUND_MID, edgecolor=Theme.TEXT_MUTED)

        # Apply Theme (Handles styles for axes, ticks, spines, labels, and legend)
        Theme.apply_matplotlib_dark_theme(self.fig, ax=self.ax)
        self._fit_axes()

        self._draw_canvas_now()

    def _set_empty_state_visible(self, visible: bool) -> None:
        self.empty_state_label.setVisible(visible)
        if self.canvas is not None:
            self.canvas.setVisible(not visible)

    def _draw_canvas_now(self) -> None:
        """Draw without leaving a callback that can outlive the Qt canvas."""
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        with suppress(RuntimeError):
            canvas.draw()

    def _fit_axes(self):
        """Keep dark themed axis labels visible in compact panel captures."""
        if self.fig is None:
            return
        self.fig.subplots_adjust(left=0.14, right=0.95, top=0.88, bottom=0.16)

    def clear(self, *, redraw: bool = True):
        """Clear the plot and reset accumulated data history."""
        if self.fig is None or self.canvas is None or self.ax is None:
            return
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
        Theme.apply_matplotlib_dark_theme(self.fig, ax=self.ax)
        self._fit_axes()
        if redraw:
            self._draw_canvas_now()

        # Clear history data
        if hasattr(self, "epochs"):
            self.epochs = []
        if hasattr(self, "train_vals"):
            self.train_vals = []
        if hasattr(self, "val_vals"):
            self.val_vals = []
        self._set_empty_state_visible(True)

    def _release_canvas(self) -> None:
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        figure = getattr(canvas, "figure", None)
        cancel_pending_draw = getattr(canvas, "cancel_pending_draw", None)
        if callable(cancel_pending_draw):
            cancel_pending_draw()
        elif hasattr(canvas, "_draw_pending"):
            canvas._draw_pending = False
        layout = self.layout()
        if layout is not None:
            with suppress(RuntimeError):
                layout.removeWidget(canvas)
        with suppress(RuntimeError):
            canvas.setParent(None)
        with suppress(RuntimeError):
            canvas.close()
        if figure is not None and getattr(figure, "canvas", None) is canvas:
            figure.canvas = None
        canvas.figure = None
        with suppress(RuntimeError):
            canvas.deleteLater()
        self.canvas = None

    def _close_figure(self) -> None:
        fig = getattr(self, "fig", None)
        if fig is not None:
            plt.close(fig)
            self.fig = None

    def closeEvent(self, event):  # noqa: N802
        self._release_canvas()
        self._close_figure()
        super().closeEvent(event)
