from PyQt6.QtCore import Qt

from XBrainLab.ui.dialogs.dataset.bids_subject_selection_dialog import (
    BidsSubjectSelectionDialog,
)


def _catalog():
    return {
        "root": "/data/bids",
        "subject_count": 3,
        "eeg_file_count": 6,
        "subjects": [
            {
                "subject": "01",
                "label": "sub-01",
                "eeg_file_count": 3,
                "sessions": ["01", "02"],
                "tasks": ["p300"],
                "runs": ["1", "2", "3"],
            },
            {
                "subject": "02",
                "label": "sub-02",
                "eeg_file_count": 2,
                "sessions": [],
                "tasks": ["rest"],
                "runs": ["1", "2"],
            },
            {
                "subject": "10",
                "label": "sub-10",
                "eeg_file_count": 1,
                "sessions": ["01"],
                "tasks": ["mi"],
                "runs": [],
            },
        ],
        "warnings": [],
    }


def test_dialog_defaults_to_first_subject_and_shows_scope_summary(qtbot) -> None:
    dialog = BidsSubjectSelectionDialog(None, catalog=_catalog())
    qtbot.addWidget(dialog)

    assert dialog.subject_table.rowCount() == 3
    assert dialog.subject_table.item(0, 0).checkState() is Qt.CheckState.Checked
    assert dialog.subject_table.item(1, 0).checkState() is Qt.CheckState.Unchecked
    assert dialog.subject_table.item(0, 2).text() == "01, 02"
    assert dialog.subject_table.item(1, 2).text() == "Not specified"
    assert dialog.continue_button.isEnabled() is True
    assert dialog.get_result() == ["01"]


def test_dialog_requires_at_least_one_selected_subject(qtbot) -> None:
    dialog = BidsSubjectSelectionDialog(None, catalog=_catalog())
    qtbot.addWidget(dialog)

    dialog.subject_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)

    assert dialog.continue_button.isEnabled() is False
    assert dialog.selection_summary.text() == "Select at least one subject."


def test_dialog_returns_multiple_selected_subjects(qtbot) -> None:
    dialog = BidsSubjectSelectionDialog(None, catalog=_catalog())
    qtbot.addWidget(dialog)

    dialog.subject_table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    dialog.subject_table.item(2, 0).setCheckState(Qt.CheckState.Checked)

    assert dialog.get_result() == ["01", "02", "10"]
    assert dialog.selection_summary.text() == "3 subjects selected · 6 EEG files"
