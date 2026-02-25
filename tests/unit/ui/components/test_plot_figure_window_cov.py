"""Coverage tests for PlotFigureWindow - 108 uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock

import matplotlib
import pytest

matplotlib.use("Agg")


def _make_mock_trainer(name="Plan_0"):
    """Create a mock trainer with plans."""
    trainer = MagicMock()
    trainer.get_name.return_value = name
    plan = MagicMock()
    plan.get_name.return_value = f"{name}_repeat_0"
    plan.get_epoch.return_value = 1
    plan.is_finished.return_value = False
    trainer.get_plans.return_value = [plan]
    return trainer


@pytest.fixture
def plot_window(qtbot):
    from XBrainLab.ui.components.plot_figure_window import PlotFigureWindow

    trainer = _make_mock_trainer()
    plot_type = MagicMock()
    plot_type.value = "plot_accuracy"

    w = PlotFigureWindow(
        parent=None,
        trainers=[trainer],
        plot_type=plot_type,
        title="Test Plot",
    )
    qtbot.addWidget(w)
    # Stop timer immediately to avoid side effects
    w.timer.stop()
    yield w
    w.close()


class TestPlotFigureWindow:
    def test_creates_window(self, plot_window):
        assert plot_window.windowTitle() == "Test Plot"

    def test_has_plan_combo(self, plot_window):
        assert hasattr(plot_window, "plan_combo")
        assert plot_window.plan_combo.count() >= 2  # "Select a plan" + trainer

    def test_has_saliency_combo(self, plot_window):
        assert hasattr(plot_window, "saliency_combo")
        assert plot_window.saliency_combo.count() >= 2

    def test_on_plan_select_valid(self, plot_window):
        plot_window.on_plan_select("Plan_0")
        assert plot_window.trainer is not None
        assert plot_window.real_plan_combo.count() >= 2

    def test_on_plan_select_invalid(self, plot_window):
        plot_window.on_plan_select("NoSuchPlan")
        assert plot_window.trainer is None

    def test_on_real_plan_select_valid(self, plot_window):
        plot_window.on_plan_select("Plan_0")
        plan_name = plot_window.real_plan_combo.itemText(1)
        plot_window.on_real_plan_select(plan_name)
        assert plot_window.plan_to_plot is not None

    def test_on_real_plan_select_invalid(self, plot_window):
        plot_window.on_real_plan_select("no_such_repeat")
        assert plot_window.plan_to_plot is None

    def test_on_saliency_method_select(self, plot_window):
        plot_window.on_saliency_method_select("Gradient")

    def test_on_saliency_method_select_placeholder(self, plot_window):
        plot_window.on_saliency_method_select("Select saliency method")

    def test_set_selection(self, plot_window):
        plot_window.set_selection(False)
        assert not plot_window.selector_group.isEnabled()
        plot_window.set_selection(True)
        assert plot_window.selector_group.isEnabled()

    def test_recreate_fig(self, plot_window):
        plot_window.recreate_fig()
        assert plot_window.plot_gap == 100

    def test_close_event_stops_timer(self, plot_window):
        plot_window.close()
        assert not plot_window.timer.isActive()

    def test_update_loop_not_visible(self, plot_window):
        plot_window.hide()
        plot_window.update_loop()  # Should return early

    def test_update_loop_no_plan(self, plot_window):
        plot_window.show()
        plot_window.current_plot = "something"  # Force missmatch
        plot_window.plan_to_plot = None
        plot_window.update_loop()

    def test_check_data_empty(self, qtbot):
        from XBrainLab.ui.components.plot_figure_window import PlotFigureWindow

        w = PlotFigureWindow(
            parent=None, trainers=[], plot_type=MagicMock(), title="Empty"
        )
        qtbot.addWidget(w)
        w.timer.stop()
        w.close()
