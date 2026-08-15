from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialogButtonBox

from XBrainLab.ui.dialogs.dataset.channel_selection_dialog import (
    ChannelSelectionDialog,
)


def _channels(count: int) -> list[str]:
    return [
        f"EEG channel with a long display name {index:03d}" for index in range(count)
    ]


def test_channel_selection_dialog_uses_current_dialog_hierarchy(qtbot) -> None:
    dialog = ChannelSelectionDialog(None, _channels(64))
    qtbot.addWidget(dialog)
    dialog.show()

    margins = dialog.layout().contentsMargins()
    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None
    ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
    cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)

    assert dialog.objectName() == "ChannelSelectionDialog"
    assert dialog.width() >= 460
    assert dialog.height() >= 480
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        20,
        18,
        20,
        16,
    )
    assert dialog.layout().spacing() == 10
    assert dialog.search_bar.objectName() == "ChannelSearchInput"
    assert dialog.list_widget.objectName() == "ChannelSelectionList"
    assert dialog.btn_all.objectName() == "SecondaryDialogButton"
    assert dialog.btn_none.objectName() == "SecondaryDialogButton"
    assert ok_button.objectName() == "PrimaryConfirmButton"
    assert cancel_button.objectName() == "SecondaryDialogButton"
    assert button_box.layoutDirection() is Qt.LayoutDirection.LeftToRight
    assert cancel_button.geometry().right() < ok_button.geometry().left()
    assert button_box.geometry().right() == (
        dialog.contentsRect().right() - dialog.layout().contentsMargins().right()
    )


def test_channel_selection_dialog_keeps_footer_and_list_usable_when_narrow(
    qtbot,
) -> None:
    dialog = ChannelSelectionDialog(None, _channels(128))
    qtbot.addWidget(dialog)
    dialog.resize(432, 552)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.list_widget.verticalScrollBar().maximum() > 0)

    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None
    assert dialog.minimumSizeHint().width() <= 432
    assert dialog.list_widget.horizontalScrollBarPolicy() is (
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert dialog.list_widget.horizontalScrollBar().maximum() == 0
    assert button_box.isVisible()
    assert button_box.geometry().bottom() <= dialog.contentsRect().bottom()
    ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
    cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel_button.geometry().right() < ok_button.geometry().left()


def test_channel_selection_behavior_and_copy_are_unchanged(qtbot) -> None:
    dialog = ChannelSelectionDialog(None, ["C3", "C4", "Cz"])
    qtbot.addWidget(dialog)
    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None

    assert dialog.search_bar.placeholderText() == "Search channels..."
    assert button_box.button(QDialogButtonBox.StandardButton.Ok).text() == "OK"
    assert button_box.button(QDialogButtonBox.StandardButton.Cancel).text() == "Cancel"
    assert all(
        dialog.list_widget.item(index).checkState() is Qt.CheckState.Checked
        for index in range(dialog.list_widget.count())
    )

    dialog.filter_channels("c3")
    assert dialog.list_widget.item(0).isHidden() is False
    assert dialog.list_widget.item(1).isHidden() is True

    dialog.set_all_checked(False)
    assert all(
        dialog.list_widget.item(index).checkState() is Qt.CheckState.Unchecked
        for index in range(dialog.list_widget.count())
    )
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as warning:
        dialog.accept()
        warning.assert_called_once_with(
            dialog,
            "Warning",
            "Please select at least one channel.",
        )

    dialog.set_all_checked(True)
    dialog.accept()
    assert dialog.get_result() == ["C3", "C4", "Cz"]
