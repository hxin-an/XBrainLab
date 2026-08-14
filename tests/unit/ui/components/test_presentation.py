from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from XBrainLab.ui.components.presentation import ElidingComboBox, ResponsiveControlsBar


def test_eliding_combo_box_elides_display_without_losing_selection(qtbot):
    combo = ElidingComboBox()
    qtbot.addWidget(combo)
    selection = "Fold 1: EEGNet with a deliberately long model label"
    payload = object()
    combo.addItem(selection, payload)
    combo.resize(150, combo.sizeHint().height())
    combo.show()
    qtbot.wait(0)

    assert combo.elideMode() == Qt.TextElideMode.ElideRight
    assert combo.elided_current_text() != selection
    assert combo.currentText() == selection
    assert combo.currentData() is payload
    assert combo.toolTip() == selection


def test_responsive_controls_bar_stacks_trailing_controls_at_narrow_width(qtbot):
    model = ElidingComboBox()
    run = ElidingComboBox()
    percent = QLabel("Percent")
    provenance = QLabel("Final · Test split")
    bar = ResponsiveControlsBar(
        [("Model", model), ("Run", run)],
        [percent, provenance],
        wrap_width=600,
    )
    qtbot.addWidget(bar)
    bar.resize(240, 180)
    bar.show()
    qtbot.wait(0)

    assert bar.is_wrapped() is True
    assert percent.y() > run.geometry().bottom()
    assert provenance.y() > percent.geometry().bottom()
    assert percent.geometry().right() <= bar.contentsRect().right()
    assert provenance.geometry().right() <= bar.contentsRect().right()


def test_greedy_controls_bar_ignores_hidden_trailing_width_and_reflows_on_show(
    qtbot,
    monkeypatch,
):
    model = ElidingComboBox()
    model.setMinimumWidth(100)
    percent = QLabel("Percent")
    hidden_cancel = QLabel("Hidden cancel action")
    hidden_cancel.setFixedWidth(300)
    hidden_cancel.hide()
    bar = ResponsiveControlsBar(
        [("Model", model)],
        [percent, hidden_cancel],
        greedy_wrap=True,
    )
    qtbot.addWidget(bar)
    bar.resize(360, 120)
    bar.show()
    qtbot.wait(0)

    assert bar.is_wrapped() is False

    refresh_count = 0
    refresh_layout = bar.refresh_layout

    def counted_refresh_layout() -> None:
        nonlocal refresh_count
        refresh_count += 1
        refresh_layout()

    monkeypatch.setattr(bar, "refresh_layout", counted_refresh_layout)
    hidden_cancel.show()
    qtbot.waitUntil(bar.is_wrapped, timeout=1_000)
    qtbot.wait(30)

    assert refresh_count <= 4
    assert bar._settled_reflow_pending is False
