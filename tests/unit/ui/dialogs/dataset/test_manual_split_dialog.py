"""Observable safeguards for manual split selection."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox

from XBrainLab.ui.dialogs.dataset.manual_split_dialog import ManualSplitDialog


def test_empty_manual_selection_remains_open_for_correction(qtbot) -> None:
    dialog = ManualSplitDialog(None, [("sub-01", "Subject 01")])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button is not None

    qtbot.mouseClick(ok_button, Qt.MouseButton.LeftButton)

    assert dialog.isVisible()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.get_result() == []
    assert dialog.selection_error_label is not None
    assert dialog.selection_error_label.isVisible()
    assert dialog.selection_error_label.text() == "Select at least one item."
