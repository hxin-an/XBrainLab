from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialogButtonBox, QScrollArea

from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog


def test_epoching_content_owns_vertical_scroll_above_fixed_footer(qtbot):
    dialog = EpochingDialog(
        None,
        [],
        epoch_context={
            "available_events": [
                {"name": f"event_{index:02d}", "count": 20} for index in range(16)
            ],
            "has_import_hint": True,
            "source": "loaded label files",
            "placement_label": "Label interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "window_evidence": "Suggested from imported event timing.",
        },
    )
    qtbot.addWidget(dialog)
    dialog.resize(620, 420)
    dialog.show()
    qtbot.wait(0)

    scroll = dialog.findChild(QScrollArea, "EpochDialogContentScroll")
    event_list = dialog.event_list
    footer = dialog.findChild(QDialogButtonBox)
    assert scroll is not None
    assert event_list is not None
    assert footer is not None
    event_scrollbar = event_list.verticalScrollBar()
    content_scrollbar = scroll.verticalScrollBar()
    last_event = event_list.item(15, 1)
    assert event_scrollbar is not None
    assert content_scrollbar is not None
    assert last_event is not None

    assert scroll.widgetResizable()
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert event_list.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert event_scrollbar.maximum() == 0
    assert last_event.text() == "event_15"
    assert content_scrollbar.maximum() > 0
    assert footer.isVisibleTo(dialog)

    footer_y = footer.mapTo(dialog, footer.rect().topLeft()).y()
    content_scrollbar.setValue(content_scrollbar.maximum())
    qtbot.wait(0)

    assert footer.mapTo(dialog, footer.rect().topLeft()).y() == footer_y
