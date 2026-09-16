"""Product-state tests for the Data Import loading surface."""

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QLabel, QPushButton

from XBrainLab.ui.dialogs.dataset.data_interpretation_loading_dialog import (
    DataInterpretationLoadingDialog,
)
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)


@pytest.mark.parametrize(
    "dialog_class", [DataInterpretationLoadingDialog, DataInterpretationPreviewDialog]
)
def test_import_first_frame_reveal_follows_native_platform_contract(
    qapp, qtbot, dialog_class
):
    initial_opacity = 0 if qapp.platformName() == "windows" else 1
    dialog = dialog_class()
    qtbot.addWidget(dialog)
    events = []

    class PaintObserver(QObject):
        def eventFilter(self, obj, event):
            if event.type() in (QEvent.Type.Show, QEvent.Type.Paint):
                events.append((event.type(), obj.windowOpacity()))
            return False

    observer = PaintObserver(dialog)
    dialog.installEventFilter(observer)
    dialog.show()
    qtbot.waitUntil(
        lambda: any(kind == QEvent.Type.Paint for kind, _ in events)
        and dialog.windowOpacity() == 1,
    )

    assert dialog.isVisible()
    assert [opacity for kind, opacity in events if kind == QEvent.Type.Show] == [
        initial_opacity
    ]
    assert (
        next(opacity for kind, opacity in events if kind == QEvent.Type.Paint)
        == initial_opacity
    )


@pytest.mark.parametrize(
    "dialog_class", [DataInterpretationLoadingDialog, DataInterpretationPreviewDialog]
)
def test_import_first_frame_reveal_does_not_reopen_or_outlive_closed_dialog(
    qtbot, dialog_class
):
    dialog = dialog_class()
    qtbot.addWidget(dialog)
    QTimer.singleShot(0, dialog.reject)
    dialog.show()
    qtbot.waitUntil(lambda: not dialog.isVisible())
    qtbot.wait(0)
    assert not dialog.isVisible()
    dialog.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(dialog))


def test_loading_dialog_shows_wizard_context_and_cancel(qtbot):
    dialog = DataInterpretationLoadingDialog(initial_step="Match Labels")
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.windowTitle() == "Import EEG Data"
    assert dialog.status_title.text() == "Checking selected EEG data"
    assert dialog.status_detail.text() == (
        "Checking the selected label values and EEG events."
    )
    assert dialog.progress_bar.minimum() == 0
    assert dialog.progress_bar.maximum() == 0
    assert dialog.progress_bar.property("operationKind") == ""
    assert dialog.cancel_button.text() == "Cancel Import"
    assert dialog.cancel_button.icon().isNull()
    assert all(label.isVisible() for label in dialog.step_labels)


def test_loading_dialog_error_state_supports_retry_without_technical_traceback(qtbot):
    dialog = DataInterpretationLoadingDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.show_error(
        "The selected source could not be reviewed.",
        retry_available=True,
    )

    assert dialog.status_title.text() == "Import review could not be prepared"
    assert dialog.status_detail.text() == "The selected source could not be reviewed."
    assert not dialog.progress_bar.isVisible()
    assert dialog.retry_button.isVisible()
    assert dialog.retry_button.text() == "Retry"
    assert dialog.cancel_button.text() == "Cancel Import"
    visible_text = " ".join(
        label.text() for label in dialog.findChildren(QLabel) if label.isVisible()
    )
    assert "Traceback" not in visible_text
    assert all(button.icon().isNull() for button in dialog.findChildren(QPushButton))


def test_loading_dialog_compacts_step_labels_when_width_is_limited(qtbot):
    dialog = DataInterpretationLoadingDialog()
    qtbot.addWidget(dialog)
    dialog.resize(760, 760)
    dialog.show()
    qtbot.wait(20)

    assert all(
        label.fontMetrics().horizontalAdvance(label.text())
        <= label.contentsRect().width()
        for label in dialog.step_labels
    )
    if dialog.step_labels[0].text() == "1. EEG":
        assert dialog.step_labels[0].toolTip() == "Choose EEG Data"
