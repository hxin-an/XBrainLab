"""Product-state tests for the Data Import loading surface."""

from PyQt6.QtWidgets import QLabel, QPushButton

from XBrainLab.ui.dialogs.dataset.data_interpretation_loading_dialog import (
    DataInterpretationLoadingDialog,
)


def test_loading_dialog_shows_wizard_context_and_cancel(qtbot):
    dialog = DataInterpretationLoadingDialog(initial_step="Match Labels")
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.windowTitle() == "Import EEG Data"
    assert dialog.status_title.text() == "Updating label matches"
    assert dialog.status_detail.text() == (
        "Checking the selected label values and EEG events."
    )
    assert dialog.progress_bar.minimum() == 0
    assert dialog.progress_bar.maximum() == 0
    assert dialog.cancel_button.text() == "Cancel"
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
    assert dialog.cancel_button.text() == "Cancel"
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
