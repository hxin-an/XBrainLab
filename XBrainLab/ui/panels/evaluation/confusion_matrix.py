"""Confusion matrix widget for displaying classification results."""

from contextlib import suppress
from math import ceil
from textwrap import fill
from typing import Any, cast

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import EvaluationRenderData
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.styles.theme import Theme

CONFUSION_MATRIX_LOAD_FAILED_TEXT = (
    "Confusion matrix could not be displayed. "
    "Select another completed run or refresh Evaluation."
)


class _ResponsiveFigureCanvas(FigureCanvas):
    """Keep full-sized text readable; the containing viewport handles overflow."""

    def wheelEvent(self, event):  # noqa: N802
        # Evaluation has no wheel zoom. The chart is nested inside a container;
        # Reuse its existing scroll area rather than Matplotlib's wheel handler.
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, QScrollArea):
            parent = parent.parentWidget()
        viewport = parent.viewport() if parent is not None else None
        if parent is None or viewport is None:
            event.ignore()
            return
        pixels = event.pixelDelta()
        if not pixels.isNull():
            # Qt's scrollbar wheel path may ignore pixel-only touchpad events.
            # Deltas already include the platform's natural-scroll direction.
            moved = False
            for bar, delta in (
                (parent.horizontalScrollBar(), pixels.x()),
                (parent.verticalScrollBar(), pixels.y()),
            ):
                previous = bar.value()
                bar.setValue(previous - delta)
                moved = moved or bar.value() != previous
            event.setAccepted(moved)
            return
        forwarded = QWheelEvent(
            QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())),
            event.globalPosition(),
            event.pixelDelta(),
            event.angleDelta(),
            event.buttons(),
            event.modifiers(),
            event.phase(),
            event.inverted(),
            device=event.pointingDevice(),
        )
        QApplication.sendEvent(viewport, forwarded)
        event.setAccepted(forwarded.isAccepted())

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if not any(axis.axison for axis in self.figure.axes):
            return
        self.fit_layout()

    def fit_layout(self) -> None:
        """Measure rendered labels instead of reducing fonts at fixed widths."""
        axis = next((axis for axis in self.figure.axes if axis.axison), None)
        if axis is None:
            self.setMinimumSize(0, 0)
            with suppress(RuntimeError):
                self.draw()
            return
        renderer = self.get_renderer()
        scale = self.device_pixel_ratio
        x_boxes = [
            label.get_window_extent(renderer) for label in axis.get_xticklabels()
        ]
        y_boxes = [
            label.get_window_extent(renderer) for label in axis.get_yticklabels()
        ]
        left = max((box.width / scale for box in y_boxes), default=0) + 40
        bottom = max((box.height / scale for box in x_boxes), default=0) + 35
        matrix = bool(axis.images)
        cell_width = max((box.width / scale for box in x_boxes), default=0) + 8
        cell_height = max((box.height / scale for box in y_boxes), default=0) + 8
        right = 65 if matrix else 20
        plot_width = max(160, len(x_boxes) * cell_width)
        plot_height = max(120, len(y_boxes) * cell_height) if matrix else 180
        if matrix:
            left = right = max(left, right)
            plot_width = plot_height = max(280, plot_width, plot_height)
        self.setMinimumSize(
            ceil(left + plot_width + right), ceil(bottom + plot_height + 35)
        )
        width, height = self.width(), self.height()
        available_width = max(1, width - left - right)
        available_height = max(1, height - bottom - 35)
        if matrix:
            side = min(available_width, available_height)
            left += (available_width - side) / 2
            bottom += (available_height - side) / 2
            available_width = available_height = side
        axis.set_position(
            [
                left / width,
                bottom / height,
                available_width / width,
                available_height / height,
            ]
        )
        if matrix and len(self.figure.axes) > 1:
            bounds = axis.get_position()
            self.figure.axes[1].set_position(
                [bounds.x1 + 18 / width, bounds.y0, 16 / width, bounds.height]
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
        figure = Figure(figsize=(5, 4), dpi=100)
        canvas = _ResponsiveFigureCanvas(figure)
        self.fig: Figure | None = figure
        self.canvas: FigureCanvas | None = canvas
        self.ax = figure.add_subplot(111)

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

        self.plot_layout.addWidget(canvas)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.plot_container)
        layout.addWidget(scroll)

    def update_plot(
        self,
        data: EvaluationRenderData | None,
        show_percentage: bool = False,
    ):
        """Update the confusion matrix plot.

        Args:
            data: Detached Evaluation arrays and class labels.
            show_percentage: Whether to show percentage

        """
        try:
            self._clear_plot_widgets()
            self._close_current_figure()

            if data is None:
                self._show_message("No Data Available")
                return
            self._require_detached_data(data)

            self.fig = self._build_figure(
                data,
                show_percentage=show_percentage,
            )

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

    @staticmethod
    def _require_detached_data(data: object) -> None:
        if not isinstance(data, EvaluationRenderData):
            raise TypeError("data must be detached EvaluationRenderData")

    @staticmethod
    def _build_figure(
        data: EvaluationRenderData,
        *,
        show_percentage: bool,
    ) -> Figure:
        outputs = np.asarray(data.outputs)
        labels = np.asarray(data.labels)
        class_count = outputs.shape[1]
        if class_count < 1:
            raise ValueError("Evaluation outputs contain no classes")
        integer_labels = labels.astype(np.int64)
        if not np.array_equal(labels, integer_labels) or np.any(integer_labels < 0):
            raise ValueError("Evaluation labels contain invalid class indices")
        if np.any(integer_labels >= class_count):
            raise ValueError("Evaluation labels exceed the model class count")
        predicted = outputs.argmax(axis=1)
        confusion = np.zeros((class_count, class_count), dtype=np.uint64)
        np.add.at(confusion, (integer_labels, predicted), 1)

        if show_percentage:
            row_sums = confusion.sum(axis=1, keepdims=True)
            plot_data = np.divide(
                confusion,
                row_sums,
                out=np.zeros_like(confusion, dtype=float),
                where=row_sums != 0,
            )
        else:
            plot_data = confusion

        figure = Figure(figsize=(6.4, 4.8), dpi=100)
        axis = figure.add_subplot(111)
        axis.set_title("Confusion matrix", color="#cccccc", pad=10)
        axis.set_xlabel("Predicted Label", labelpad=6, color="#cccccc")
        axis.set_ylabel("True Label", labelpad=6, color="#cccccc")
        image = axis.imshow(
            plot_data, cmap="magma", interpolation="nearest", aspect="auto"
        )
        threshold = (float(plot_data.max()) + float(plot_data.min())) / 2
        for row in range(class_count):
            for column in range(class_count):
                value = plot_data[row][column]
                axis.annotate(
                    f"{value:.1%}" if show_percentage else str(int(value)),
                    xy=(column, row),
                    horizontalalignment="center",
                    verticalalignment="center",
                    color="k" if value > threshold else "w",
                )
        colorbar = figure.colorbar(image)
        colorbar.ax.yaxis.set_tick_params(color="#cccccc")
        plt.setp(colorbar.ax.get_yticklabels(), color="#cccccc")
        class_names = [
            data.class_labels.get(index, f"Class {index}")
            for index in range(class_count)
        ]
        axis.set_xticks(
            range(class_count),
            [fill(name, width=10, break_long_words=False) for name in class_names],
            rotation=0,
            ha="center",
        )
        axis.set_yticks(
            range(class_count),
            [fill(name, width=18, break_long_words=False) for name in class_names],
            va="center",
        )
        axis.tick_params(axis="x", colors="#cccccc")
        axis.tick_params(axis="y", colors="#cccccc")
        for spine in axis.spines.values():
            spine.set_edgecolor("#444444")
        return figure

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
                    # Detaching a visible QTAgg canvas first can briefly make it
                    # a top-level widget and schedule one more native paint.
                    # Quiesce painting before changing ownership.
                    widget.setUpdatesEnabled(False)
                    widget.hide()
                    with suppress(RuntimeError):
                        widget.close()
                    widget.setParent(None)
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

    def cleanup(self) -> None:
        """Synchronously quiesce Qt canvases before their parent is destroyed."""
        self._clear_plot_widgets()
        self._close_current_figure()

    def closeEvent(self, event):  # noqa: N802
        self.cleanup()
        super().closeEvent(event)
