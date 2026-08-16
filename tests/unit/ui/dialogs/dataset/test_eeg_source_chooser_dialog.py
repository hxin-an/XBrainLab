from PyQt6.QtWidgets import QDialogButtonBox

from XBrainLab.ui.dialogs.dataset.eeg_source_chooser_dialog import (
    EegSourceChooserDialog,
    EegSourceSelection,
)


def test_chooser_stays_detached_until_user_accepts(qtbot) -> None:
    dialog = EegSourceChooserDialog(None)
    qtbot.addWidget(dialog)

    continue_button = dialog.button_box.button(
        QDialogButtonBox.StandardButton.Ok,
    )
    assert continue_button is not None
    assert continue_button.text() == "Continue"
    assert continue_button.isEnabled() is False
    assert dialog.get_result() is None

    dialog.path_edit.setText("/data/subject-01")

    assert continue_button.isEnabled() is True
    assert dialog.get_result() is None

    dialog.accept()

    assert dialog.get_result() == EegSourceSelection(
        kind="auto",
        paths=("/data/subject-01",),
    )


def test_chooser_keeps_multiple_files_as_typed_selection(qtbot) -> None:
    dialog = EegSourceChooserDialog(
        None,
        choose_files=lambda: ["/data/a.vhdr", "/data/b.edf"],
    )
    qtbot.addWidget(dialog)

    dialog.choose_files_button.click()

    assert dialog.selection_summary.text() == "2 files selected"
    dialog.accept()
    assert dialog.get_result() == EegSourceSelection(
        kind="files",
        paths=("/data/a.vhdr", "/data/b.edf"),
    )


def test_chooser_replaces_file_selection_with_one_folder(qtbot) -> None:
    dialog = EegSourceChooserDialog(
        None,
        choose_files=lambda: ["/data/a.vhdr"],
        choose_folder=lambda: "/data/bids",
    )
    qtbot.addWidget(dialog)

    dialog.choose_files_button.click()
    dialog.choose_folder_button.click()
    dialog.accept()

    assert dialog.get_result() == EegSourceSelection(
        kind="folder",
        paths=("/data/bids",),
    )
