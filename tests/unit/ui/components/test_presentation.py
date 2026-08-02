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
