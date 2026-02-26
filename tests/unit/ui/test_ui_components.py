"""Deeper coverage tests for main_window, training panel, dataset panel, and more."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMainWindow

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
        assert w.figure_canvas is not None


# ============ MessageBubble ============


class TestMessageBubble:
    def test_creates_user(self, qtbot):
        from XBrainLab.ui.chat.message_bubble import MessageBubble

        b = MessageBubble(text="Hello!", is_user=True)
        qtbot.addWidget(b)
        assert b is not None

    def test_creates_assistant(self, qtbot):
        from XBrainLab.ui.chat.message_bubble import MessageBubble

        b = MessageBubble(text="Hi there!", is_user=False)
        qtbot.addWidget(b)
        assert b is not None

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
        assert w is not None

    def test_update_plot_no_data(self, qtbot):
        from XBrainLab.ui.panels.evaluation.confusion_matrix import (
            ConfusionMatrixWidget,
        )

        w = ConfusionMatrixWidget()
        qtbot.addWidget(w)
        w.update_plot(None)


class TestMetricsBarChart:
    def test_creates(self, qtbot):
        from XBrainLab.ui.panels.evaluation.metrics_bar_chart import (
            MetricsBarChartWidget,
        )

        w = MetricsBarChartWidget()
        qtbot.addWidget(w)
        assert w is not None

    def test_update_plot_no_data(self, qtbot):
        from XBrainLab.ui.panels.evaluation.metrics_bar_chart import (
            MetricsBarChartWidget,
        )

        w = MetricsBarChartWidget()
        qtbot.addWidget(w)
        w.update_plot(None)


# ============ History Table ============


class TestHistoryTable:
    def test_creates(self, qtbot):
        from XBrainLab.ui.panels.training.history_table import TrainingHistoryTable

        w = TrainingHistoryTable()
        qtbot.addWidget(w)
        assert w is not None

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
        assert d is not None

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
        with patch("XBrainLab.ui.panels.dataset.panel.QtObserverBridge"):
            from XBrainLab.ui.panels.dataset.panel import DatasetPanel

            ctrl = MagicMock()
            ctrl.get_loaded_data_list.return_value = []
            p = DatasetPanel(controller=ctrl)
            qtbot.addWidget(p)
            yield p

    def test_creates(self, panel):
        assert panel is not None

    def test_update_panel(self, panel):
        panel.update_panel()


# ============ TrainingPanel ============


class TestTrainingPanel:
    @pytest.fixture
    def panel(self, qtbot):
        with patch("XBrainLab.ui.panels.training.panel.QtObserverBridge"):
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
        assert panel is not None

    def test_update_panel(self, panel):
        panel.update_panel()

    def test_update_info(self, panel):
        panel.update_info()
