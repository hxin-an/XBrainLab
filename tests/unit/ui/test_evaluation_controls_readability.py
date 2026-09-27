"""User-visible Evaluation selector and table layout regressions."""

from dataclasses import replace

import numpy as np
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QScrollArea, QVBoxLayout

from tests.unit.ui.test_evaluation_panel_redesign import (
    MockMainWindow,
    _detached_render,
    _install_evaluation_read_side,
    _serialized_evaluation_result,
)
from XBrainLab.backend.application import EvaluationPlanIdentity
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel


def test_long_labels_use_full_width_chart_tabs_and_restore_parallel_layout(
    qtbot, monkeypatch
):
    runtime, _ = _install_evaluation_read_side(
        monkeypatch,
        lambda *_a, **_k: _serialized_evaluation_result(second_run_finished=True),
    )
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

    def render(request):
        result = _detached_render(request)
        return replace(
            result,
            data=replace(
                result.data,
                labels=np.arange(4),
                outputs=np.eye(4),
                class_labels=names,
                metrics={
                    i: {"precision": 0.8, "recall": 0.7, "f1-score": 0.75, "support": 1}
                    for i in names
                },
            ),
        )

    runtime.render = render
    parent = MockMainWindow()
    qtbot.addWidget(parent)
    panel = EvaluationPanel(parent=parent)
    layout = QVBoxLayout(parent)
    layout.addWidget(panel)
    parent.resize(1280, 920)
    parent.show()
    panel.update_panel()
    qtbot.waitUntil(
        lambda: panel._charts_are_tabbed and panel.metrics_table.rowCount() == 4
    )
    assert panel.chart_tabs.currentWidget() is panel.matrix_widget
    assert panel.matrix_widget.width() > 750
    matrix_scroll = panel.matrix_widget.findChild(QScrollArea)
    qtbot.waitUntil(lambda: matrix_scroll.verticalScrollBar().maximum() == 0)
    assert matrix_scroll.horizontalScrollBar().maximum() == 0
    original_selection = panel.run_combo.currentData()
    panel.chart_tabs.setCurrentWidget(panel.bar_chart)
    assert panel.bar_chart.isVisible()
    for width in (1500, 1600):
        parent.resize(width, 920)
        QApplication.processEvents()
        qtbot.waitUntil(lambda: panel._charts_are_tabbed)
        panel.chart_tabs.setCurrentWidget(panel.matrix_widget)
        qtbot.waitUntil(lambda: matrix_scroll.horizontalScrollBar().maximum() == 0)
    parent.resize(1800, 920)
    qtbot.waitUntil(lambda: not panel._charts_are_tabbed)
    assert panel.matrix_widget.isVisible() and panel.bar_chart.isVisible()
    parent.resize(1280, 920)
    qtbot.waitUntil(lambda: panel._charts_are_tabbed)
    assert panel.run_combo.currentData() == original_selection
    panel.matrix_widget.canvas.draw()
    bounds = panel.matrix_widget.fig.axes[0].get_window_extent()
    assert abs(bounds.width - bounds.height) < 1


@pytest.mark.parametrize("second_finished", [False, True])
def test_summary_requires_multiple_completed_runs(qtbot, monkeypatch, second_finished):
    _install_evaluation_read_side(
        monkeypatch,
        lambda *_args, **_kwargs: _serialized_evaluation_result(
            second_run_finished=second_finished,
        ),
    )
    parent = MockMainWindow()
    qtbot.addWidget(parent)
    panel = EvaluationPanel(parent=parent)
    panel.update_panel()
    qtbot.waitUntil(panel.evaluation_background_work_idle, timeout=2000)
    expected = ["Run 1", "Run 2", "Summary"] if second_finished else ["Run 1"]
    assert [
        panel.run_combo.itemText(i) for i in range(panel.run_combo.count())
    ] == expected
    if second_finished:
        assert panel.run_combo.itemData(2) == EvaluationPlanIdentity(plan_index=0)


def test_many_metric_rows_scroll_without_stealing_plot_height(qtbot):
    panel = EvaluationPanel()
    qtbot.addWidget(panel)
    panel.resize(1280, 760)
    panel.show()
    metric = {"precision": 0.8, "recall": 0.7, "f1-score": 0.75, "support": 10}
    panel.metrics_table.update_data(dict.fromkeys(range(3), metric))
    QApplication.processEvents()
    initial_plot_height = panel.plots_group.height()
    panel.metrics_table.update_data(dict.fromkeys(range(40), metric))
    QApplication.processEvents()
    assert panel.plots_group.height() >= initial_plot_height - 2
    assert panel.plots_group.height() > panel.bottom_tabs.height()
    table = panel.metrics_table
    assert table.verticalScrollBar().isVisible()
    table.scrollToItem(table.item(39, 0))
    QApplication.processEvents()
    assert (
        table.viewport()
        .rect()
        .contains(table.visualItemRect(table.item(39, 0)).center())
    )


def test_full_class_name_remains_available_in_metric_table(qtbot):
    panel = EvaluationPanel()
    qtbot.addWidget(panel)
    label = "Imagined movement of the left hand and forearm"
    panel.metrics_table.update_data(
        {0: {"precision": 0.8, "recall": 0.7, "f1-score": 0.75, "support": 10}},
        class_names={0: label},
    )
    item = panel.metrics_table.item(0, 0)
    assert item.text() == label
    assert item.toolTip() == label


@pytest.mark.parametrize("selector", ["model_combo", "run_combo", "split_combo"])
@pytest.mark.parametrize("count", [2, 50])
def test_evaluation_popup_edges_and_last_item(qtbot, qapp, tmp_path, selector, count):
    previous_style = qapp.style().objectName()
    qapp.setStyle("Fusion")
    panel = EvaluationPanel()
    qtbot.addWidget(panel)
    combo = getattr(panel, selector)
    combo.blockSignals(True)  # Only isolate result loading, not native popup painting.
    combo.clear()
    combo.addItems([f"Result {i + 1}" for i in range(count)])
    combo.setEnabled(True)
    combo.setMaxVisibleItems(8)
    panel.resize(1100, 700)
    with qtbot.waitExposed(panel):
        panel.show()
    try:
        combo.showPopup()
        popup = combo.view().window()
        qtbot.waitUntil(popup.isVisible)
        QApplication.processEvents()
        pixmap = popup.grab()
        image = pixmap.toImage()
        pixmap.save(str(tmp_path / f"{selector}-{count}.png"))
        for y in (2, image.height() - 3):
            colors = [image.pixelColor(x, y) for x in range(3, image.width() - 3)]
            white = sum(min(c.red(), c.green(), c.blue()) >= 220 for c in colors)
            assert white / len(colors) < 0.1, f"White band at {y}; capture: {tmp_path}"
        qtbot.keyClick(combo.view(), Qt.Key.Key_End)
        current = combo.view().currentIndex()
        assert current.row() == count - 1
        qtbot.waitUntil(
            lambda: combo.view()
            .viewport()
            .rect()
            .contains(combo.view().visualRect(current).center()),
            timeout=1000,
        )
        qtbot.keyClick(combo.view(), Qt.Key.Key_Return)
        assert combo.currentIndex() == count - 1
        assert not popup.isVisible()
    finally:
        combo.hidePopup()
        combo.blockSignals(False)
        qapp.setStyle(previous_style)
