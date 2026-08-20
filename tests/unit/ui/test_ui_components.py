"""Deeper coverage tests for main_window, training panel, dataset panel, and more."""

from __future__ import annotations

import warnings
from itertools import pairwise
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtWidgets import QMainWindow, QWidget

# ============ SinglePlotWindow ============


class TestSinglePlotWindow:
    def test_creates(self, qtbot):
        from XBrainLab.ui.components.single_plot_window import SinglePlotWindow

        w = SinglePlotWindow(None, title="Test Plot")
        qtbot.addWidget(w)
        assert w.windowTitle() == "Test Plot"

    def test_has_figure_canvas(self, qtbot):
        from XBrainLab.ui.components.single_plot_window import SinglePlotWindow

        w = SinglePlotWindow(None, title="Test")
        qtbot.addWidget(w)
        assert isinstance(w.figure_canvas, QWidget)

    def test_close_releases_current_figure_and_qt_widgets(self, qtbot):
        from matplotlib.figure import Figure
        from PyQt6.QtGui import QCloseEvent

        from XBrainLab.ui.components import single_plot_window
        from XBrainLab.ui.components.single_plot_window import SinglePlotWindow

        w = SinglePlotWindow(None, title="Test")
        qtbot.addWidget(w)
        external_figure = Figure()
        w.set_figure(external_figure, w.figsize, w.dpi)

        with patch.object(single_plot_window.plt, "close") as close_figure:
            w.closeEvent(QCloseEvent())

        assert external_figure in [call.args[0] for call in close_figure.call_args_list]
        assert w.figure_canvas is None
        assert w.toolbar is None
        assert w.plot_number is None

    def test_set_figure_reuses_same_figure_without_closing_it(self, qtbot):
        from XBrainLab.ui.components import single_plot_window
        from XBrainLab.ui.components.single_plot_window import SinglePlotWindow

        w = SinglePlotWindow(None, title="Test")
        qtbot.addWidget(w)
        current_figure = w.fig_param["fig"]

        with patch.object(single_plot_window.plt, "close") as close_figure:
            w.set_figure(current_figure, w.figsize, w.dpi)

        close_figure.assert_not_called()
        assert w.fig_param["fig"] is current_figure


# ============ MessageBubble ============


class TestMessageBubble:
    def test_set_text(self, qtbot):
        from XBrainLab.ui.chat.message_bubble import MessageBubble

        b = MessageBubble(text="initial", is_user=False)
        qtbot.addWidget(b)
        b.set_text("updated")


# ============ ConfusionMatrix & MetricsBarChart ============


class TestConfusionMatrix:
    def test_update_plot_no_data(self, qtbot):
        from XBrainLab.ui.panels.evaluation.confusion_matrix import (
            ConfusionMatrixWidget,
        )

        w = ConfusionMatrixWidget()
        qtbot.addWidget(w)
        w.update_plot(None)

    def test_update_none_releases_previous_canvas_and_children(self, qtbot):
        from PyQt6.QtWidgets import QLabel

        from XBrainLab.ui.panels.evaluation import confusion_matrix
        from XBrainLab.ui.panels.evaluation.confusion_matrix import (
            ConfusionMatrixWidget,
        )

        class CleanupLabel(QLabel):
            deleted = False

            def deleteLater(self):
                self.deleted = True
                super().deleteLater()

        w = ConfusionMatrixWidget()
        qtbot.addWidget(w)
        old_fig = w.fig
        old_canvas = w.canvas
        assert old_canvas is not None
        old_canvas._draw_pending = True
        temporary_label = CleanupLabel("temporary")
        w.plot_layout.addWidget(temporary_label)

        with patch.object(confusion_matrix.plt, "close") as close_figure:
            w.update_plot(None)

        close_figure.assert_called_once_with(old_fig)
        assert temporary_label.deleted is True
        assert old_canvas.parent() is None
        assert old_canvas._draw_pending is False
        assert w.fig is None
        assert w.canvas is None

    @pytest.mark.parametrize(
        ("canvas_width", "class_labels"),
        [
            (175, {0: "left", 1: "right"}),
            (270, {0: "Left hand", 1: "Right hand"}),
            (390, {0: "Left hand", 1: "Right hand"}),
        ],
    )
    def test_narrow_canvas_keeps_class_labels_inside_figure(
        self,
        qtbot,
        canvas_width,
        class_labels,
    ):
        from XBrainLab.backend.application import (
            EvaluationPlanIdentity,
            EvaluationRenderData,
            EvaluationSummaryIdentity,
        )
        from XBrainLab.ui.panels.evaluation.confusion_matrix import (
            ConfusionMatrixWidget,
        )

        plan = EvaluationPlanIdentity(plan_index=0)
        render_data = EvaluationRenderData(
            labels=np.array([0, 1]),
            outputs=np.array([[1.0, 0.0], [0.0, 1.0]]),
            metrics={},
            class_labels=class_labels,
            summary_identity=EvaluationSummaryIdentity(plan=plan),
            evaluation_split="test",
        )

        widget = ConfusionMatrixWidget()
        qtbot.addWidget(widget)
        widget.setFixedSize(canvas_width, 350)
        widget.show()
        qtbot.wait(20)

        widget.update_plot(render_data)
        qtbot.wait(20)
        assert widget.canvas is not None
        assert widget.fig is not None
        # Match the product path: the Evaluation panel starts wide, then the
        # Assistant dock narrows the plot canvas.
        widget.canvas.setFixedSize(530, 320)
        widget.fit_plot_to_canvas()
        widget.canvas.setFixedSize(canvas_width, 280)
        widget.fit_plot_to_canvas()
        assert widget.canvas.width() == canvas_width
        widget.canvas.draw()
        renderer = widget.canvas.get_renderer()

        label_bounds = [
            label.get_window_extent(renderer)
            for label in widget.fig.axes[0].get_yticklabels()
        ]
        assert label_bounds
        assert min(bounds.x0 for bounds in label_bounds) >= 0
        x_tick_bounds = [
            label.get_window_extent(renderer)
            for label in widget.fig.axes[0].get_xticklabels()
        ]
        x_tick_rows = [
            (label.get_text(), bounds.x0, bounds.x1)
            for label, bounds in zip(
                widget.fig.axes[0].get_xticklabels(),
                x_tick_bounds,
                strict=True,
            )
        ]
        assert all(
            left.x1 + 6 <= right.x0 for left, right in pairwise(x_tick_bounds)
        ), x_tick_rows
        decorated_text = [
            widget.fig.axes[0].xaxis.label,
            widget.fig.axes[0].yaxis.label,
            widget.fig.axes[0].title,
        ]
        decorated_bounds = [text.get_window_extent(renderer) for text in decorated_text]
        assert min(bounds.x0 for bounds in decorated_bounds) >= 0, decorated_bounds
        assert max(bounds.x1 for bounds in decorated_bounds) <= widget.canvas.width()
        assert min(bounds.y0 for bounds in decorated_bounds) >= 0
        assert max(bounds.y1 for bounds in decorated_bounds) <= widget.canvas.height()

    def test_responsive_layout_contains_known_tight_layout_warning(self, qtbot):
        from XBrainLab.ui.panels.evaluation.confusion_matrix import (
            ConfusionMatrixWidget,
        )

        widget = ConfusionMatrixWidget()
        qtbot.addWidget(widget)
        assert widget.canvas is not None

        def warn_about_transient_geometry(*args, **kwargs):
            del args, kwargs
            warnings.warn(
                "Tight layout not applied. The left and right margins cannot be made large enough.",
                UserWarning,
                stacklevel=2,
            )

        widget.fig.tight_layout = warn_about_transient_geometry

        with warnings.catch_warnings(record=True) as escaped_warnings:
            warnings.simplefilter("always")
            widget.fit_plot_to_canvas()

        assert escaped_warnings == []


class TestMetricsBarChart:
    def test_update_plot_no_data(self, qtbot):
        from XBrainLab.ui.panels.evaluation.metrics_bar_chart import (
            MetricsBarChartWidget,
        )

        w = MetricsBarChartWidget()
        qtbot.addWidget(w)
        w.update_plot(None)

    def test_update_plot_draws_without_queued_qt_callback(self, qtbot):
        from XBrainLab.ui.panels.evaluation.metrics_bar_chart import (
            MetricsBarChartWidget,
        )

        w = MetricsBarChartWidget()
        qtbot.addWidget(w)
        assert w.canvas is not None
        w.canvas.draw = MagicMock()
        w.canvas.draw_idle = MagicMock()

        w.update_plot(None)

        w.canvas.draw.assert_called_once_with()
        w.canvas.draw_idle.assert_not_called()

    def test_close_releases_figure_and_canvas(self, qtbot):
        import matplotlib.pyplot as plt
        from PyQt6.QtGui import QCloseEvent

        from XBrainLab.ui.panels.evaluation.metrics_bar_chart import (
            MetricsBarChartWidget,
        )

        w = MetricsBarChartWidget()
        qtbot.addWidget(w)
        old_fig = w.fig
        old_canvas = w.canvas
        assert old_canvas is not None
        old_canvas._draw_pending = True

        with patch.object(plt, "close") as close_figure:
            w.closeEvent(QCloseEvent())

        close_figure.assert_called_once_with(old_fig)
        assert old_canvas.parent() is None
        assert old_canvas._draw_pending is False
        assert w.fig is None
        assert w.canvas is None

    def test_repeated_parent_teardown_has_no_deleted_canvas_callback(
        self,
        qtbot,
    ):
        import gc
        import weakref

        from PyQt6 import sip
        from PyQt6.QtCore import QCoreApplication, QEvent

        from XBrainLab.ui.panels.evaluation.metrics_bar_chart import (
            MetricsBarChartWidget,
        )

        figure_refs = []
        metrics = {
            0: {"precision": 0.8, "recall": 0.7, "f1-score": 0.75},
            1: {"precision": 0.6, "recall": 0.5, "f1-score": 0.55},
        }
        for _ in range(10):
            parent = QWidget()
            qtbot.addWidget(parent)
            chart = MetricsBarChartWidget(parent)
            canvas = chart.canvas
            figure = chart.fig
            assert canvas is not None
            assert figure is not None
            figure_refs.append(weakref.ref(figure))
            chart.update_plot(metrics)

            parent.deleteLater()
            QCoreApplication.sendPostedEvents(
                None,
                QEvent.Type.DeferredDelete,
            )
            QCoreApplication.processEvents()

            assert sip.isdeleted(canvas)
            del figure
            del canvas
            del chart
            del parent

        gc.collect()
        QCoreApplication.processEvents()

        # pytest-qt turns uncaught Qt callback exceptions into test failures.
        # Keep the lifecycle assertions direct so this gate also runs when the
        # test temp root is a Windows-mounted path.
        assert all(reference() is None for reference in figure_refs)

    def test_update_plot_layout_failure_is_not_logged_as_error(self, qtbot):
        from XBrainLab.ui.panels.evaluation import metrics_bar_chart
        from XBrainLab.ui.panels.evaluation.metrics_bar_chart import (
            MetricsBarChartWidget,
        )

        w = MetricsBarChartWidget()
        qtbot.addWidget(w)
        assert w.fig is not None
        w.fig.tight_layout = MagicMock(side_effect=np.linalg.LinAlgError("singular"))

        with patch.object(metrics_bar_chart.logger, "error") as error_logger:
            w.update_plot(
                {
                    0: {"precision": 0.0, "recall": 0.0, "f1-score": 0.0},
                    1: {"precision": 0.0, "recall": 0.0, "f1-score": 0.0},
                },
            )

        error_logger.assert_not_called()

    def test_update_plot_styles_per_class_metric_text_for_dark_theme(self, qtbot):
        from XBrainLab.ui.panels.evaluation.metrics_bar_chart import (
            MetricsBarChartWidget,
        )
        from XBrainLab.ui.styles.theme import Theme

        w = MetricsBarChartWidget()
        qtbot.addWidget(w)

        w.update_plot(
            {
                0: {"precision": 0.8, "recall": 0.7, "f1-score": 0.75},
                1: {"precision": 0.6, "recall": 0.5, "f1-score": 0.55},
            },
        )

        legend = w.ax.legend_
        assert legend is not None
        assert {text.get_color() for text in legend.get_texts()} == {Theme.TEXT_PRIMARY}
        assert w.ax.title.get_color() == Theme.TEXT_MUTED
        assert w.ax.yaxis.label.get_color() == Theme.TEXT_MUTED
        assert all(
            label.get_color() == Theme.TEXT_PRIMARY for label in w.ax.get_xticklabels()
        )


# ============ History Table ============


class TestHistoryTable:
    def test_clear_history(self, qtbot):
        from XBrainLab.ui.panels.training.history_table import TrainingHistoryTable

        w = TrainingHistoryTable()
        qtbot.addWidget(w)
        w.clear_history()
        assert w.rowCount() == 0
        assert w.row_identity_by_index == {}


# ============ FilteringDialog ============


class TestFilteringDialog:
    def test_get_params_default(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.filtering_dialog import FilteringDialog

        d = FilteringDialog(None)
        qtbot.addWidget(d)
        # get_params returns None before the dialog returns a confirmed result.
        result = d.get_params()
        assert result is None or isinstance(result, tuple)


# ============ DatasetPanel ============


class TestDatasetPanel:
    @pytest.fixture
    def panel(self, qtbot):
        with patch("XBrainLab.ui.core.base_panel.QtObserverBridge"):
            from XBrainLab.ui.panels.dataset.panel import DatasetPanel

            ctrl = MagicMock()
            ctrl.get_loaded_data_list.return_value = []
            p = DatasetPanel(controller=ctrl)
            qtbot.addWidget(p)
            yield p

    def test_update_panel(self, panel):
        panel.update_panel()


# ============ TrainingPanel ============


class TestTrainingPanel:
    @pytest.fixture
    def panel(self, qtbot):
        with patch("XBrainLab.ui.core.base_panel.QtObserverBridge"):
            from XBrainLab.ui.panels.training.panel import TrainingPanel

            ctrl = MagicMock()
            ctrl.has_datasets.return_value = False
            ctrl.has_model.return_value = False
            ctrl.has_training_option.return_value = False
            ctrl.is_training.return_value = False
            ctrl.get_trainers.return_value = []
            ds_ctrl = MagicMock()
            parent = QMainWindow()
            qtbot.addWidget(parent)
            p = TrainingPanel(
                controller=ctrl,
                dataset_controller=ds_ctrl,
                parent=parent,
            )
            yield p

    def test_update_panel(self, panel):
        panel.update_panel()

    def test_update_info(self, panel):
        panel.update_info()
