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
    assert len(metric_tab.test_vals) == 0
    assert metric_tab.empty_state_label.text() == (
        "Training metrics will appear after the first training epoch."
    )
    assert metric_tab.empty_state_label.isVisibleTo(metric_tab)
    assert metric_tab.canvas.isHidden()


def test_update_plot(metric_tab):
    metric_tab.update_plot(1, 0.5, 0.6)
    assert len(metric_tab.epochs) == 1
    assert metric_tab.epochs[0] == 1
    assert metric_tab.train_vals[0] == 0.5
    assert metric_tab.val_vals[0] == 0.6

    # Check if lines were plotted (2 lines: train + val)
    assert len(metric_tab.ax.lines) == 2
    assert metric_tab.empty_state_label.isHidden()
    assert not metric_tab.canvas.isHidden()


def test_set_series_draws_full_history_once(metric_tab, monkeypatch):
    draw_calls = []
    monkeypatch.setattr(metric_tab.canvas, "draw", lambda: draw_calls.append(True))

    metric_tab.set_series([1, 2, 3], [0.4, 0.5, 0.6], [0.3, 0.4, 0.5])

    assert metric_tab.epochs == [1, 2, 3]
    assert metric_tab.train_vals == [0.4, 0.5, 0.6]
    assert metric_tab.val_vals == [0.3, 0.4, 0.5]
    assert len(metric_tab.ax.lines) == 2
    assert len(draw_calls) == 1


def test_set_series_draws_final_test_value_at_last_training_epoch(metric_tab):
    metric_tab.set_series(
        [1, 2, 3],
        [0.4, 0.5, 0.6],
        [0.3, 0.4, 0.5],
        [0.55],
    )

    assert metric_tab.test_vals == [0.55]
    assert len(metric_tab.ax.lines) == 3
    test_line = next(
        line for line in metric_tab.ax.lines if line.get_label() == "Test Test Metric"
    )
    assert list(test_line.get_xdata()) == [3]
    assert list(test_line.get_ydata()) == [0.55]


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
    assert len(metric_tab.test_vals) == 0
    assert len(metric_tab.ax.lines) == 0
    assert metric_tab.ax.title.get_color() == Theme.TEXT_MUTED
    assert metric_tab.ax.xaxis.label.get_color() == Theme.TEXT_MUTED
    assert metric_tab.ax.yaxis.label.get_color() == Theme.TEXT_MUTED
    assert metric_tab.empty_state_label.isVisibleTo(metric_tab)
    assert metric_tab.canvas.isHidden()


def test_close_releases_canvas_and_cancels_pending_draw(metric_tab, qtbot):
    metric_tab.update_plot(1, 0.5, 0.6)
    old_canvas = metric_tab.canvas
    old_figure = metric_tab.fig
    old_canvas.draw_idle()
    assert old_canvas._draw_timer.isActive()

    metric_tab.close()
    qtbot.wait(0)

    assert metric_tab.canvas is None
    assert old_canvas.parent() is None
    assert old_canvas._draw_pending is False
    assert not old_canvas._draw_timer.isActive()
    assert old_canvas.figure is None
    assert old_figure.canvas is None


def test_parent_teardown_leaves_no_pending_canvas_callback(qtbot):
    import gc

    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QWidget

    for _index in range(5):
        parent = QWidget()
        qtbot.addWidget(parent)
        tab = MetricTab("Accuracy", parent=parent)
        canvas = tab.canvas
        tab.set_series([1], [0.5], [0.4])

        parent.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QCoreApplication.processEvents()

        assert sip.isdeleted(canvas)
        del tab
        del canvas
        del parent

    gc.collect()
    QCoreApplication.processEvents()
    # pytest-qt fails on uncaught Qt callbacks; explicit fd capture is redundant
    # and is not portable to every Windows-mounted test temp root.


def test_queued_draw_callback_is_safe_after_canvas_deletion(metric_tab, qtbot):
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent

    old_canvas = metric_tab.canvas
    queued_callback = old_canvas._draw_idle
    old_canvas.draw_idle()

    metric_tab._release_canvas()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()

    assert sip.isdeleted(old_canvas)
    queued_callback()
    assert old_canvas._draw_pending is False
