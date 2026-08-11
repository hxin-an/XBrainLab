"""Confusion matrix widget for displaying classification results."""

import warnings
from contextlib import suppress
from typing import Any, Literal, cast

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.text import Text
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from XBrainLab.backend.application import EvaluationRenderData
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.styles.theme import Theme

CONFUSION_MATRIX_LOAD_FAILED_TEXT = (
    "Confusion matrix could not be displayed. "
    "Select another completed run or refresh Evaluation."
)


def _balanced_two_line_label(text: str) -> str:
    """Wrap a class name once without dropping its user-reviewed meaning."""
    words = text.split()
    if len(words) < 2:
        return text
    split_at = min(
        range(1, len(words)),
        key=lambda index: abs(
            len(" ".join(words[:index])) - len(" ".join(words[index:]))
        ),
    )
    return f"{' '.join(words[:split_at])}\n{' '.join(words[split_at:])}"


class _ResponsiveFigureCanvas(FigureCanvas):
    """Reflow figure margins after Qt assigns a narrower canvas geometry."""

    def __init__(self, figure: Figure) -> None:
        super().__init__(figure)
        self._responsive_tick_state: dict[
            Text,
            tuple[float, Literal["left", "center", "right"], float, str],
        ] = {}
        self._responsive_text_size_state: dict[Text, float] = {}

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
            x_labels = [
                label for label in primary_axis.get_xticklabels() if label.get_text()
            ]
            y_labels = [
                label for label in primary_axis.get_yticklabels() if label.get_text()
            ]
            if self.width() < 480:
                if self.width() < 240:
                    rotation = 90
                elif self.width() < 320:
                    rotation = 70
                else:
                    rotation = 45
                for label in x_labels:
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
                    label.set_fontsize(7 if self.width() < 240 else 8)
            else:
                for label in x_labels:
                    original = self._responsive_tick_state.pop(label, None)
                    if original is not None:
                        original_rotation, alignment, font_size, text = original
                        label.set_text(text)
                        label.set_rotation(original_rotation)
                        label.set_horizontalalignment(alignment)
                        label.set_rotation_mode("default")
                        label.set_fontsize(font_size)
            if self.width() < 240:
                for label in y_labels:
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
                    original_text = self._responsive_tick_state[label][3]
                    label.set_text(_balanced_two_line_label(original_text))
                    label.set_fontsize(7)
            else:
                for label in y_labels:
                    original = self._responsive_tick_state.pop(label, None)
                    if original is not None:
                        original_rotation, alignment, font_size, text = original
                        label.set_text(text)
                        label.set_rotation(original_rotation)
                        label.set_horizontalalignment(alignment)
                        label.set_rotation_mode("default")
                        label.set_fontsize(font_size)
            decorated_text = (
                primary_axis.title,
                primary_axis.xaxis.label,
                primary_axis.yaxis.label,
            )
            if self.width() < 240:
                compact_sizes = (9.0, 8.0, 8.0)
                for text, compact_size in zip(
                    decorated_text,
                    compact_sizes,
                    strict=True,
                ):
                    self._responsive_text_size_state.setdefault(
                        text,
                        float(text.get_fontsize()),
                    )
                    text.set_fontsize(compact_size)
            else:
                for text in decorated_text:
                    original_size = self._responsive_text_size_state.pop(text, None)
                    if original_size is not None:
                        text.set_fontsize(original_size)
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
        layout.addWidget(self.plot_container)

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
        axis.set_title("Confusion matrix", color="#cccccc", pad=20)
        axis.set_xlabel("Predicted Label", labelpad=10, color="#cccccc")
        axis.set_ylabel("True Label", labelpad=10, color="#cccccc")
        image = axis.imshow(plot_data, cmap="magma", interpolation="nearest")
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
        axis.set_xticks(range(class_count), class_names, rotation=0, ha="center")
        axis.set_yticks(range(class_count), class_names, va="center")
        axis.tick_params(axis="x", colors="#cccccc")
        axis.tick_params(axis="y", colors="#cccccc")
        for spine in axis.spines.values():
            spine.set_edgecolor("#444444")
        figure.tight_layout()
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
