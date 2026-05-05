"""Deeper coverage tests for main_window, training panel, dataset panel, and more."""

from __future__ import annotations

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


# ============ MessageBubble ============


class TestMessageBubble:
    def test_creates_user(self, qtbot):
        from XBrainLab.ui.chat.message_bubble import MessageBubble

        b = MessageBubble(text="Hello!", is_user=True)
        qtbot.addWidget(b)
        assert isinstance(b, MessageBubble)

    def test_creates_assistant(self, qtbot):
        from XBrainLab.ui.chat.message_bubble import MessageBubble

        b = MessageBubble(text="Hi there!", is_user=False)
        qtbot.addWidget(b)
        assert isinstance(b, MessageBubble)

    def test_set_text(self, qtbot):
        from XBrainLab.ui.chat.message_bubble import MessageBubble

        b = MessageBubble(text="initial", is_user=False)
        qtbot.addWidget(b)
        b.set_text("updated")


# ============ ConfusionMatrix & MetricsBarChart ============


class TestConfusionMatrix:
    def test_creates(self, qtbot):
        from XBrainLab.ui.panels.evaluation.confusion_matrix import (
            ConfusionMatrixWidget,
        )

        w = ConfusionMatrixWidget()
        qtbot.addWidget(w)
        assert isinstance(w, ConfusionMatrixWidget)

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
        temporary_label = CleanupLabel("temporary")
        w.plot_layout.addWidget(temporary_label)

        with patch.object(confusion_matrix.plt, "close") as close_figure:
            w.update_plot(None)

        close_figure.assert_called_once_with(old_fig)
        assert temporary_label.deleted is True
        assert old_canvas.parent() is None
        assert w.fig is None
        assert w.canvas is None


class TestMetricsBarChart:
    def test_creates(self, qtbot):
        from XBrainLab.ui.panels.evaluation.metrics_bar_chart import (
            MetricsBarChartWidget,
        )

        w = MetricsBarChartWidget()
        qtbot.addWidget(w)
        assert isinstance(w, MetricsBarChartWidget)

    def test_update_plot_no_data(self, qtbot):
        from XBrainLab.ui.panels.evaluation.metrics_bar_chart import (
            MetricsBarChartWidget,
        )

        w = MetricsBarChartWidget()
        qtbot.addWidget(w)
        w.update_plot(None)

    def test_update_plot_layout_failure_is_not_logged_as_error(self, qtbot):
        from XBrainLab.ui.panels.evaluation import metrics_bar_chart
        from XBrainLab.ui.panels.evaluation.metrics_bar_chart import (
            MetricsBarChartWidget,
        )

        w = MetricsBarChartWidget()
        qtbot.addWidget(w)
        w.fig.tight_layout = MagicMock(side_effect=np.linalg.LinAlgError("singular"))

        with patch.object(metrics_bar_chart.logger, "error") as error_logger:
            w.update_plot(
                {
                    0: {"precision": 0.0, "recall": 0.0, "f1-score": 0.0},
                    1: {"precision": 0.0, "recall": 0.0, "f1-score": 0.0},
                },
            )

        error_logger.assert_not_called()


# ============ History Table ============


class TestHistoryTable:
    def test_creates(self, qtbot):
        from XBrainLab.ui.panels.training.history_table import TrainingHistoryTable

        w = TrainingHistoryTable()
        qtbot.addWidget(w)
        assert isinstance(w, TrainingHistoryTable)

    def test_clear_history(self, qtbot):
        from XBrainLab.ui.panels.training.history_table import TrainingHistoryTable

        w = TrainingHistoryTable()
        qtbot.addWidget(w)
        w.clear_history()
        assert w.rowCount() == 0
        assert w.row_map == {}


# ============ FilteringDialog ============


class TestFilteringDialog:
    def test_creates(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.filtering_dialog import FilteringDialog

        d = FilteringDialog(None)
        qtbot.addWidget(d)
        assert isinstance(d, FilteringDialog)

    def test_get_params_default(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.filtering_dialog import FilteringDialog

        d = FilteringDialog(None)
        qtbot.addWidget(d)
        # get_params returns None before the dialog is accepted
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

    def test_creates(self, panel):
        assert isinstance(panel, QWidget)

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

    def test_creates(self, panel):
        assert isinstance(panel, QWidget)

    def test_update_panel(self, panel):
        panel.update_panel()

    def test_update_info(self, panel):
        panel.update_info()
