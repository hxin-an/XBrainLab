"""Real chart bounds protect long names without trading away readable text."""

from itertools import pairwise

import numpy as np
import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QScrollArea

from XBrainLab.backend.application import EvaluationRenderData
from XBrainLab.ui.panels.evaluation.confusion_matrix import ConfusionMatrixWidget
from XBrainLab.ui.panels.evaluation.metrics_bar_chart import MetricsBarChartWidget


@pytest.mark.parametrize("chart_type", [ConfusionMatrixWidget, MetricsBarChartWidget])
@pytest.mark.parametrize("horizontal", [False, True])
@pytest.mark.parametrize("input_kind", ["wheel", "pixel", "pixel_and_angle"])
@pytest.mark.parametrize("inverted", [False, True])
def test_wheel_over_chart_scrolls_both_directions(
    qtbot, chart_type, horizontal, input_kind, inverted
):
    chart = chart_type()
    qtbot.addWidget(chart)
    chart.resize(360, 240)
    chart.show()
    names = {i: f"Imagined left hand movement condition {i}" for i in range(20)}
    if isinstance(chart, ConfusionMatrixWidget):
        chart.update_plot(
            EvaluationRenderData(
                labels=np.arange(20),
                outputs=np.eye(20),
                metrics={},
                class_labels=names,
                summary_identity=None,
                evaluation_split="test",
            )
        )
    else:
        chart.update_plot(
            {i: {"precision": 0.8, "recall": 0.7, "f1-score": 0.75} for i in names},
            class_names=names,
        )
    QApplication.processEvents()
    scroll = chart.findChild(QScrollArea)
    bar = scroll.horizontalScrollBar() if horizontal else scroll.verticalScrollBar()
    qtbot.waitUntil(lambda: bar.maximum() > 0, timeout=1000)

    def wheel(delta):
        position = QPoint(50, 50)
        vector = QPoint(delta, 0) if horizontal else QPoint(0, delta)
        event = QWheelEvent(
            QPointF(position),
            QPointF(chart.canvas.mapToGlobal(position)),
            vector if input_kind != "wheel" else QPoint(),
            vector if input_kind != "pixel" else QPoint(),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            inverted,
        )
        QApplication.sendEvent(chart.canvas, event)
        QApplication.processEvents()

    bar.setValue(0)
    step = 120 if input_kind == "wheel" else 30
    wheel(-step)
    advanced = bar.value()
    assert advanced > 0
    if input_kind != "wheel":
        assert advanced == step  # Pixels take precedence; do not also apply angleDelta.
    wheel(step)
    assert bar.value() < advanced
    if input_kind != "wheel":
        assert bar.value() == 0
        wheel(-1)
        wheel(-2)
        assert bar.value() == 3  # Preserve small, continuous touchpad movements.
    bar.setValue(0)
    wheel(120)
    assert bar.value() == 0
    bar.setValue(bar.maximum())
    wheel(-120)
    assert bar.value() == bar.maximum()


def test_confusion_matrix_is_square_large_and_horizontally_centered(qtbot):
    chart = ConfusionMatrixWidget()
    qtbot.addWidget(chart)
    chart.resize(850, 520)
    chart.show()
    chart.update_plot(
        EvaluationRenderData(
            labels=np.arange(4),
            outputs=np.eye(4),
            metrics={},
            class_labels={
                i: f"Left hand motor imagery condition {i}" for i in range(4)
            },
            summary_identity=None,
            evaluation_split="test",
        )
    )
    QApplication.processEvents()
    chart.canvas.draw()
    bounds = chart.fig.axes[0].get_window_extent(chart.canvas.get_renderer())
    assert abs(bounds.width - bounds.height) < 1
    assert bounds.width / chart.canvas.device_pixel_ratio >= 280
    assert abs((bounds.x0 + bounds.x1) / 2 - chart.fig.bbox.width / 2) < 1


@pytest.mark.parametrize("chart_type", [ConfusionMatrixWidget, MetricsBarChartWidget])
def test_four_ordinary_eeg_names_fit_the_actual_panel_viewport(qtbot, chart_type):
    names = dict(
        enumerate(
            [
                "Left hand motor imagery",
                "Right hand motor imagery",
                "Both feet motor imagery",
                "Tongue movement motor imagery",
            ]
        )
    )
    chart = chart_type()
    qtbot.addWidget(chart)
    # A full-width tab now protects the matrix's square shape and readable size.
    if isinstance(chart, ConfusionMatrixWidget):
        chart.resize(850, 520)
    else:
        chart.resize(460, 350)
    chart.show()
    if isinstance(chart, ConfusionMatrixWidget):
        chart.update_plot(
            EvaluationRenderData(
                labels=np.arange(4),
                outputs=np.eye(4),
                metrics={},
                class_labels=names,
                summary_identity=None,
                evaluation_split="test",
            )
        )
    else:
        chart.update_plot(
            {i: {"precision": 0.8, "recall": 0.7, "f1-score": 0.75} for i in names},
            class_names=names,
        )
    qtbot.wait(50)
    scroll = chart.findChild(QScrollArea)
    assert scroll is not None
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() == 0
    chart.canvas.draw()
    renderer = chart.canvas.get_renderer()
    for labels in (
        chart.fig.axes[0].get_xticklabels(),
        chart.fig.axes[0].get_yticklabels(),
    ):
        boxes = [label.get_window_extent(renderer) for label in labels]
        assert all(not a.overlaps(b) for a, b in pairwise(boxes))


@pytest.mark.parametrize("chart_type", [ConfusionMatrixWidget, MetricsBarChartWidget])
@pytest.mark.parametrize("class_count", [3, 12])
def test_chart_long_labels_remain_complete_separate_and_scrollable(
    qtbot, chart_type, class_count
):
    names = {
        index: f"Imagined movement of the left hand and forearm class {index}"
        for index in range(class_count)
    }
    chart = chart_type()
    qtbot.addWidget(chart)
    chart.resize(480, 420)
    chart.show()
    if isinstance(chart, ConfusionMatrixWidget):
        chart.update_plot(
            EvaluationRenderData(
                labels=np.arange(class_count),
                outputs=np.eye(class_count),
                metrics={},
                class_labels=names,
                summary_identity=None,
                evaluation_split="test",
            )
        )
    else:
        chart.update_plot(
            {
                index: {"precision": 0.8, "recall": 0.7, "f1-score": 0.75}
                for index in names
            },
            class_names=names,
        )

    for width in (480, 320, 900, 480):
        chart.resize(width, 420)
        qtbot.wait(30)
        chart.canvas.draw()
        renderer = chart.canvas.get_renderer()
        axis = chart.fig.axes[0]
        labels = axis.get_xticklabels()
        assert [" ".join(label.get_text().split()) for label in labels] == list(
            names.values()
        )
        assert all(label.get_fontsize() >= 10 for label in labels)
        boxes = [label.get_window_extent(renderer) for label in labels]
        for previous, following in pairwise(boxes):
            assert not previous.overlaps(following)
        decorations = [*labels, axis.xaxis.label, axis.yaxis.label, axis.title]
        if isinstance(chart, ConfusionMatrixWidget):
            y_labels = axis.get_yticklabels()
            decorations.extend(y_labels)
            y_boxes = [label.get_window_extent(renderer) for label in y_labels]
            for previous, following in pairwise(y_boxes):
                assert not previous.overlaps(following)
        for text in decorations:
            bounds = text.get_window_extent(renderer)
            assert bounds.x0 >= 0 and bounds.y0 >= 0
            assert bounds.x1 <= chart.fig.bbox.width
            assert bounds.y1 <= chart.fig.bbox.height
        assert chart.width() == width
        scroll = chart.findChild(QScrollArea)
        assert scroll is not None
        assert scroll.viewport().width() <= width
        scroll.horizontalScrollBar().setValue(scroll.horizontalScrollBar().maximum())
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        assert scroll.widget().geometry().right() <= scroll.viewport().width()
        assert scroll.widget().geometry().bottom() <= scroll.viewport().height()


@pytest.mark.parametrize("chart_type", [ConfusionMatrixWidget, MetricsBarChartWidget])
def test_chart_short_or_empty_results_release_previous_scroll_extent(qtbot, chart_type):
    chart = chart_type()
    qtbot.addWidget(chart)
    chart.resize(600, 420)
    chart.show()

    def update(names):
        if isinstance(chart, ConfusionMatrixWidget):
            chart.update_plot(
                EvaluationRenderData(
                    labels=np.arange(len(names)),
                    outputs=np.eye(len(names)),
                    metrics={},
                    class_labels=names,
                    summary_identity=None,
                    evaluation_split="test",
                )
                if names
                else None
            )
        else:
            chart.update_plot(
                {
                    index: {"precision": 0.8, "recall": 0.7, "f1-score": 0.75}
                    for index in names
                },
                class_names=names,
            )
        qtbot.wait(30)

    scroll = chart.findChild(QScrollArea)
    assert scroll is not None
    update(
        {
            index: f"VeryLongUnbrokenClassIdentifierForMovement{index}"
            for index in range(4)
        }
    )
    assert (
        max(
            scroll.horizontalScrollBar().maximum(), scroll.verticalScrollBar().maximum()
        )
        > 0
    )
    chart.resize(900, 700)
    update({0: "Left hand", 1: "Right hand"})
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() == 0
    assert [label.get_text() for label in chart.fig.axes[0].get_xticklabels()] == [
        "Left hand",
        "Right hand",
    ]
    update({})
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() == 0
