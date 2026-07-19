from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QTreeWidget

from scripts.dev.report_data_interpretation_format_matrix import (
    FORMAT_CASES,
    FormatCase,
    _write_case_fixture,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.study import Study
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)

STEP_TITLES = (
    "Choose EEG Data",
    "Load Labels",
    "Review Metadata",
    "Match Labels",
    "Review and Import",
)
PUBLIC_BIDS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "data"
    / "public"
    / "mne-bids-tiny-eeg"
)
PUBLIC_BIDS_EEG = (
    PUBLIC_BIDS_ROOT
    / "sub-01"
    / "ses-eeg"
    / "eeg"
    / "sub-01_ses-eeg_task-rest_eeg.vhdr"
)
PUBLIC_BIDS_EVENTS = PUBLIC_BIDS_EEG.with_name("sub-01_ses-eeg_task-rest_events.tsv")


@pytest.mark.parametrize("case", FORMAT_CASES, ids=lambda case: case.case_id)
def test_data_import_wizard_opens_all_steps_for_format_matrix(
    qtbot,
    tmp_path: Path,
    case: FormatCase,
) -> None:
    """Every supported format-boundary case should survive the real wizard shell."""

    case_dir = tmp_path / case.case_id
    _write_case_fixture(case_dir, case)
    source_path = case_dir / case.source_entry
    service = ApplicationService(Study())

    scan = service.execute(
        ScanSourceCommand(
            source_path=str(source_path),
            source_hint=case.source_hint,
        ),
    )
    assert scan.ok, scan.message

    preview = service.execute(PreviewInterpretationCommand())
    assert preview.ok, preview.message

    validation = service.execute(ValidateInterpretationCommand())
    assert validation.ok, validation.message
    validation_decision = validation.diagnostics["validation_decision"]
    assert validation_decision["decision"] == case.expected_validation

    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result=scan.diagnostics["scan_result"],
        preview=preview.diagnostics["preview"],
        validation_decision=validation_decision,
    )
    qtbot.addWidget(dialog)
    dialog.resize(1220, 920)
    dialog.show()
    qtbot.wait(0)

    for step_title in STEP_TITLES:
        dialog._go_to_step(dialog._step_titles.index(step_title))
        qtbot.wait(0)

        assert dialog.cancel_button.isVisibleTo(dialog)
        assert dialog.back_button.isVisibleTo(dialog)
        assert _visible_step_text(dialog).strip()
        assert _nested_tree_scrollbars_are_disabled(dialog)

        if step_title == "Review and Import":
            assert dialog.apply_button.isVisibleTo(dialog)
            assert not dialog.next_button.isVisibleTo(dialog)
        else:
            assert dialog.next_button.isVisibleTo(dialog)
            assert step_title in dialog._step_titles

    assert "Found" in str(preview.diagnostics["preview"].get("summary", ""))


def test_public_bids_wizard_completes_through_visible_next_and_apply_buttons(
    qtbot,
) -> None:
    """A downloaded public BIDS source must survive the user-facing click path."""
    if not PUBLIC_BIDS_EEG.exists():
        pytest.skip(
            "MNE-BIDS tiny fixture not downloaded; run "
            "scripts/dev/fetch_public_eeg_fixtures.py first."
        )

    choices = {
        "selected_eeg_files": [str(PUBLIC_BIDS_EEG)],
        "label_carrier_choices": {
            str(PUBLIC_BIDS_EVENTS): {
                "label_field": "trial_type",
                "anchor": "onset",
                "duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
            }
        },
    }
    service = ApplicationService(Study())
    scan = service.execute(
        ScanSourceCommand(
            source_path=str(PUBLIC_BIDS_ROOT),
            source_hint="bids",
        )
    )
    assert scan.ok, scan.message
    preview = service.execute(PreviewInterpretationCommand(choices=choices))
    assert preview.ok, preview.message
    validation = service.execute(ValidateInterpretationCommand())
    assert validation.ok, validation.message
    assert validation.diagnostics["validation_decision"]["decision"] == "blocked"

    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result=scan.diagnostics["scan_result"],
        preview=preview.diagnostics["preview"],
        validation_decision=validation.diagnostics["validation_decision"],
    )
    qtbot.addWidget(dialog)
    dialog.resize(1220, 920)
    dialog.show()
    qtbot.wait(0)

    assert dialog.step_stack.currentIndex() == 0
    for expected_index, expected_title in enumerate(STEP_TITLES[1:], start=1):
        assert dialog.next_button.isVisibleTo(dialog)
        qtbot.mouseClick(dialog.next_button, Qt.MouseButton.LeftButton)
        qtbot.wait(0)
        assert dialog.step_stack.currentIndex() == expected_index
        assert dialog._step_titles[expected_index] == expected_title
        assert _visible_step_text(dialog).strip()
        assert _nested_tree_scrollbars_are_disabled(dialog)
        if expected_title == "Match Labels":
            editor = dialog.event_value_editor
            assert editor is not None
            assert editor.unresolved_values() == [
                "show_stimulus",
                "start_experiment",
            ]
            editor.set_value_decision(
                "show_stimulus",
                role="stimulus",
                use="class",
                class_name="Stimulus",
            )
            editor.set_value_decision(
                "start_experiment",
                role="system",
                use="event",
            )
            assert editor.is_complete()

    assert dialog.apply_button.isVisibleTo(dialog)
    assert dialog.apply_button.isEnabled()
    qtbot.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
    qtbot.wait(0)
    assert dialog.result() == QDialog.DialogCode.Accepted

    dialog_result = dialog.get_result()
    reviewed_choices = {
        **choices,
        **dict(dialog_result.get("choices") or {}),
    }
    reviewed_preview = service.execute(
        PreviewInterpretationCommand(choices=reviewed_choices)
    )
    assert reviewed_preview.ok, reviewed_preview.message
    reviewed_validation = service.execute(ValidateInterpretationCommand())
    assert reviewed_validation.ok, reviewed_validation.message
    assert reviewed_validation.diagnostics["validation_decision"]["decision"] == (
        "safe"
    )
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))
    assert applied.ok, applied.message
    assert applied.state.raw.files == [PUBLIC_BIDS_EEG.name]
    assert applied.state.interpretation.epoch_handoff["label_source"] == ("bids_events")


def _visible_step_text(dialog: DataInterpretationPreviewDialog) -> str:
    current = dialog.step_stack.currentWidget()
    assert current is not None
    return "\n".join(
        label.text()
        for label in current.findChildren(QLabel)
        if label.isVisibleTo(current) and label.text().strip()
    )


def _nested_tree_scrollbars_are_disabled(
    dialog: DataInterpretationPreviewDialog,
) -> bool:
    return all(
        tree.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        for tree in dialog.findChildren(QTreeWidget)
    )
