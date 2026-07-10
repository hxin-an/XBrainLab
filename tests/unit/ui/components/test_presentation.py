from PyQt6.QtCore import Qt

from XBrainLab.ui.components.presentation import ElidingComboBox


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
