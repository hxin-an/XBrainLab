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
    assert dialog.windowTitle() == "Import EEG Data"
    assert dialog.heading_label.text() == "Choose EEG data"
    assert "BIDS is detected automatically" in dialog.guidance_label.text()
    assert dialog.choose_files_button.parent() is dialog.source_bar
    assert dialog.choose_folder_button.parent() is dialog.source_bar
    assert dialog.choose_files_button.text() == "Files…"
    assert dialog.choose_folder_button.text() == "Folder…"
    assert dialog.choose_files_button.icon().isNull() is False
    assert dialog.choose_folder_button.icon().isNull() is False

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

    assert dialog.path_edit.text() == "/data/a.vhdr"
    assert dialog.selection_summary.text() == "2 files selected · a.vhdr +1 more"
    assert "/data/a.vhdr" in dialog.path_edit.toolTip()
    assert "/data/b.edf" in dialog.path_edit.toolTip()
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
    assert dialog.path_edit.text() == "/data/bids"
    assert dialog.path_edit.cursorPosition() == 0
    assert dialog.selection_summary.text() == (
        "Folder selected · BIDS is detected after Continue"
    )
    dialog.accept()

    assert dialog.get_result() == EegSourceSelection(
        kind="folder",
        paths=("/data/bids",),
    )


def test_chooser_source_bar_and_footer_fit_at_narrow_width(qtbot) -> None:
    dialog = EegSourceChooserDialog(None)
    qtbot.addWidget(dialog)
    dialog.resize(320, 250)
    dialog.show()
    qtbot.wait(1)

    assert dialog.minimumSizeHint().width() <= 320
    assert dialog.rect().contains(dialog.source_bar.geometry())
    assert dialog.source_bar.rect().contains(dialog.path_edit.geometry())
    assert dialog.source_bar.rect().contains(dialog.choose_files_button.geometry())
    assert dialog.source_bar.rect().contains(dialog.choose_folder_button.geometry())
    assert dialog.rect().contains(dialog.button_box.geometry())
    assert not dialog.source_bar.geometry().intersects(dialog.button_box.geometry())


def test_manual_path_edit_replaces_browser_selection_and_clear_disables_continue(
    qtbot,
) -> None:
    dialog = EegSourceChooserDialog(
        None,
        choose_files=lambda: ["/data/a.vhdr", "/data/b.edf"],
    )
    qtbot.addWidget(dialog)
    continue_button = dialog.button_box.button(
        QDialogButtonBox.StandardButton.Ok,
    )
    assert continue_button is not None

    dialog.choose_files_button.click()
    dialog.path_edit.setText("/data/manual.edf")
    dialog.accept()

    assert dialog.get_result() == EegSourceSelection(
        kind="auto",
        paths=("/data/manual.edf",),
    )

    dialog.path_edit.clear()
    assert continue_button.isEnabled() is False
