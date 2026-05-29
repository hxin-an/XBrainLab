import pytest
from matplotlib.figure import Figure

from XBrainLab.ui.panels.training.components import MetricTab
from XBrainLab.ui.styles.theme import Theme


@pytest.fixture
def metric_tab(qtbot):
    widget = MetricTab("Test Metric")
    qtbot.addWidget(widget)
    return widget


def test_init(metric_tab):
    assert metric_tab.metric_name == "Test Metric"
    assert isinstance(metric_tab.fig, Figure)
    assert len(metric_tab.epochs) == 0
    assert len(metric_tab.train_vals) == 0
    assert len(metric_tab.val_vals) == 0


def test_update_plot(metric_tab):
    metric_tab.update_plot(1, 0.5, 0.6)
    assert len(metric_tab.epochs) == 1
    assert metric_tab.epochs[0] == 1
    assert metric_tab.train_vals[0] == 0.5
    assert metric_tab.val_vals[0] == 0.6

    # Check if lines were plotted (2 lines: train + val)
    assert len(metric_tab.ax.lines) == 2


def test_set_series_draws_full_history_once(metric_tab, monkeypatch):
    draw_calls = []
    monkeypatch.setattr(metric_tab.canvas, "draw_idle", lambda: draw_calls.append(True))

    metric_tab.set_series([1, 2, 3], [0.4, 0.5, 0.6], [0.3, 0.4, 0.5])

    assert metric_tab.epochs == [1, 2, 3]
    assert metric_tab.train_vals == [0.4, 0.5, 0.6]
    assert metric_tab.val_vals == [0.3, 0.4, 0.5]
    assert len(metric_tab.ax.lines) == 2
    assert len(draw_calls) == 1


def test_empty_plot_uses_dark_theme_text(metric_tab):
    assert metric_tab.ax.title.get_color() == Theme.TEXT_MUTED
    assert metric_tab.ax.xaxis.label.get_color() == Theme.TEXT_MUTED
    assert metric_tab.ax.yaxis.label.get_color() == Theme.TEXT_MUTED


def test_clear(metric_tab):
    metric_tab.update_plot(1, 0.5, 0.6)
    metric_tab.clear()

    assert len(metric_tab.epochs) == 0
    assert len(metric_tab.train_vals) == 0
    assert len(metric_tab.val_vals) == 0
    assert len(metric_tab.ax.lines) == 0
    assert metric_tab.ax.title.get_color() == Theme.TEXT_MUTED
    assert metric_tab.ax.xaxis.label.get_color() == Theme.TEXT_MUTED
    assert metric_tab.ax.yaxis.label.get_color() == Theme.TEXT_MUTED
