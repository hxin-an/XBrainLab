from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QAbstractItemView

from XBrainLab.ui.dialogs.dataset.bids_subject_selection_dialog import (
    BidsSubjectSelectionDialog,
)
from XBrainLab.ui.styles.theme import Theme


def _subject(
    subject: str,
    *,
    eeg_file_count: int,
    sessions: list[str] | None = None,
    tasks: list[str] | None = None,
    runs: list[str] | None = None,
    label: str | None = None,
) -> dict[str, object]:
    return {
        "subject": subject,
        "label": label or f"sub-{subject}",
        "eeg_file_count": eeg_file_count,
        "sessions": sessions or [],
        "tasks": tasks or [],
        "runs": runs or [],
    }


def _catalog(*subjects: dict[str, object]) -> dict[str, object]:
    return {
        "root": "/data/bids",
        "subject_count": len(subjects),
        "eeg_file_count": sum(int(subject["eeg_file_count"]) for subject in subjects),
        "subjects": list(subjects),
        "warnings": [],
    }


def _button_contains_color(button, color: str) -> bool:
    image = button.grab().toImage()
    expected = QColor(color)
    matching = 0
    sampled = 0
    for x in range(4, max(image.width() - 4, 4)):
        for y in range(4, max(image.height() - 4, 4)):
            sampled += 1
            pixel = image.pixelColor(x, y)
            if (
                abs(pixel.red() - expected.red()) <= 3
                and abs(pixel.green() - expected.green()) <= 3
                and abs(pixel.blue() - expected.blue()) <= 3
            ):
                matching += 1
    return sampled > 0 and matching / sampled >= 0.2


def test_continue_renders_as_the_primary_action_across_enabled_states(qtbot) -> None:
    dialog = BidsSubjectSelectionDialog(
        None,
        catalog=_catalog(_subject("01", eeg_file_count=1, runs=["1"])),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.continue_button.isVisible())

    assert dialog.continue_button.text() == "Continue"
    assert dialog.continue_button.objectName() == "PrimaryConfirmButton"
    assert dialog.continue_button.isEnabled()
    assert _button_contains_color(dialog.continue_button, Theme.BLUE_PRIMARY)

    dialog.subject_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    qtbot.waitUntil(lambda: not dialog.continue_button.isEnabled())
    assert not _button_contains_color(dialog.continue_button, Theme.BLUE_PRIMARY)

    dialog.subject_table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    qtbot.waitUntil(lambda: dialog.continue_button.isEnabled())
    assert _button_contains_color(dialog.continue_button, Theme.BLUE_PRIMARY)


def test_one_subject_is_the_conservative_default_and_keyboard_operable(qtbot) -> None:
    dialog = BidsSubjectSelectionDialog(
        None,
        catalog=_catalog(
            _subject(
                "01",
                eeg_file_count=3,
                sessions=["01", "02"],
                tasks=["p300"],
                runs=["1", "2", "3"],
            ),
            _subject("02", eeg_file_count=2, tasks=["rest"], runs=["1", "2"]),
            _subject("10", eeg_file_count=1, sessions=["01"], tasks=["mi"]),
        ),
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.subject_table.rowCount() == 3
    assert dialog.subject_table.item(0, 0).checkState() is Qt.CheckState.Checked
    assert dialog.subject_table.item(1, 0).checkState() is Qt.CheckState.Unchecked
    assert dialog.get_result() == ["01"]
    assert dialog.selection_summary.text() == (
        "1 subject (sub-01) · 3 EEG files · Runs 1, 2, 3"
    )
    assert dialog.continue_button.isEnabled() is True
    assert (
        dialog.subject_table.selectionMode()
        is QAbstractItemView.SelectionMode.NoSelection
    )

    dialog.subject_table.setCurrentCell(0, 0)
    dialog.subject_table.setFocus()
    qtbot.keyClick(dialog.subject_table, Qt.Key.Key_Space)

    assert dialog.get_result() == []
    assert dialog.continue_button.isEnabled() is False
    assert dialog.selection_summary.text() == "Select at least one subject."


def test_three_selected_subjects_show_compact_ids_files_and_runs(qtbot) -> None:
    dialog = BidsSubjectSelectionDialog(
        None,
        catalog=_catalog(
            _subject("01", eeg_file_count=3, runs=["1", "2", "3"]),
            _subject("02", eeg_file_count=2, runs=["1", "2"]),
            _subject("10", eeg_file_count=1),
        ),
    )
    qtbot.addWidget(dialog)

    dialog.subject_table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    dialog.subject_table.item(2, 0).setCheckState(Qt.CheckState.Checked)

    assert dialog.get_result() == ["01", "02", "10"]
    assert dialog.selection_summary.text() == (
        "3 subjects (sub-01, sub-02, sub-10) · 6 EEG files · Runs 1, 2, 3"
    )
    assert dialog.selection_summary.toolTip() == (
        "Subjects: sub-01, sub-02, sub-10\nEEG files: 6\nRuns: 1, 2, 3"
    )


def test_three_standard_bids_subject_ids_remain_visible_in_summary(qtbot) -> None:
    dialog = BidsSubjectSelectionDialog(
        None,
        catalog=_catalog(
            _subject("001", eeg_file_count=3, runs=["1", "2", "3"]),
            _subject("002", eeg_file_count=3, runs=["1", "2", "3"]),
            _subject("003", eeg_file_count=3, runs=["1", "2", "3"]),
        ),
    )
    qtbot.addWidget(dialog)

    for row in range(1, dialog.subject_table.rowCount()):
        dialog.subject_table.item(row, 0).setCheckState(Qt.CheckState.Checked)

    assert dialog.selection_summary.text() == (
        "3 subjects (sub-001, sub-002, sub-003) · 9 EEG files · Runs 1, 2, 3"
    )


def test_zero_file_row_is_wholly_noninteractive_and_skipped_by_default(qtbot) -> None:
    dialog = BidsSubjectSelectionDialog(
        None,
        catalog=_catalog(
            _subject("empty", eeg_file_count=0, sessions=["01"], runs=["1"]),
            _subject("usable", eeg_file_count=1, sessions=["02"], runs=["2"]),
        ),
    )
    qtbot.addWidget(dialog)

    for column in range(dialog.subject_table.columnCount()):
        assert dialog.subject_table.item(0, column).flags() == Qt.ItemFlag.NoItemFlags
    assert dialog.subject_table.item(0, 0).checkState() is Qt.CheckState.Unchecked
    assert dialog.subject_table.item(1, 0).checkState() is Qt.CheckState.Checked
    assert dialog.get_result() == ["usable"]


def test_long_scope_is_bounded_and_full_values_remain_in_tooltips(qtbot) -> None:
    subjects = [
        _subject(
            f"participant-with-a-very-long-identifier-{index}",
            eeg_file_count=1,
            runs=[f"recording-run-with-a-very-long-identifier-{index}"],
        )
        for index in range(1, 5)
    ]
    dialog = BidsSubjectSelectionDialog(None, catalog=_catalog(*subjects))
    qtbot.addWidget(dialog)

    for row in range(1, dialog.subject_table.rowCount()):
        dialog.subject_table.item(row, 0).setCheckState(Qt.CheckState.Checked)

    summary = dialog.selection_summary.text()
    assert summary.startswith("4 subjects (sub-participant-")
    assert ", +3) · 4 EEG files · Runs recording-run-" in summary
    assert summary.endswith(", +3")
    assert len(summary) <= 100
    assert dialog.subject_table.item(0, 0).toolTip() == subjects[0]["label"]
    assert dialog.subject_table.item(0, 4).toolTip() == subjects[0]["runs"][0]
    assert dialog.selection_summary.toolTip() == (
        "Subjects: "
        + ", ".join(str(subject["label"]) for subject in subjects)
        + "\nEEG files: 4\nRuns: "
        + ", ".join(str(subject["runs"][0]) for subject in subjects)
    )


def test_summary_and_display_cells_are_read_only(qtbot) -> None:
    dialog = BidsSubjectSelectionDialog(
        None,
        catalog=_catalog(
            _subject(
                "01", eeg_file_count=1, sessions=["01"], tasks=["rest"], runs=["1"]
            )
        ),
    )
    qtbot.addWidget(dialog)

    subject_flags = dialog.subject_table.item(0, 0).flags()
    assert subject_flags & Qt.ItemFlag.ItemIsUserCheckable
    assert subject_flags & Qt.ItemFlag.ItemIsSelectable
    assert not subject_flags & Qt.ItemFlag.ItemIsEditable
    for column in range(1, dialog.subject_table.columnCount()):
        flags = dialog.subject_table.item(0, column).flags()
        assert flags == Qt.ItemFlag.ItemIsEnabled
