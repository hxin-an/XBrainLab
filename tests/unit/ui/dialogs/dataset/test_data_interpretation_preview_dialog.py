"""Tests for the Data Interpretation preview dialog."""

from PyQt6.QtWidgets import QDialogButtonBox

from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)


def test_data_interpretation_preview_dialog_renders_payload(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi.fif"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "metadata_preview": [
                {
                    "file": "sub-01_task-mi.fif",
                    "subject": {"value": "01", "decision": "safe"},
                    "session": {"value": None, "decision": "needs_confirmation"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": None, "decision": "needs_confirmation"},
                },
            ],
            "warnings": ["Review metadata."],
            "confirmation_items": ["Confirm session metadata."],
            "event_roles": {
                "cue": "class label candidate",
                "onset": "time anchor",
            },
            "class_map": {"1": "left", "2": "right"},
            "downstream_impacts": ["Training uses this recipe trace."],
        },
        validation_decision={
            "decision": "needs_confirmation",
            "required_confirmations": ["Confirm session metadata."],
            "blocked_reasons": [],
        },
    )
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Interpret Data Source"
    assert dialog.decision == "needs_confirmation"
    assert "Scan -> Preview -> Validate" in dialog.workflow_steps_label.text()
    assert dialog.file_tree.topLevelItemCount() == 1
    assert dialog.event_tree.topLevelItemCount() == 4
    assert "Found 1 EEG file" in dialog.summary_label.text()
    assert "Validation needs confirmation" in dialog.decision_label.text()
    assert "Confirm session metadata." in dialog.confirmation_label.text()
    assert "Training uses this recipe trace." in dialog.review_text.toPlainText()
    ok_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button is not None
    assert ok_button.text() == "Confirm and Apply"
    assert dialog.get_result() == {
        "confirmed": True,
        "save_recipe": True,
        "choices": {},
    }


def test_data_interpretation_preview_dialog_returns_review_edits(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "metadata_preview": [
                {
                    "file": "sub-01_task-mi.fif",
                    "subject": {"value": "01", "decision": "safe"},
                    "session": {"value": None, "decision": "needs_confirmation"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": None, "decision": "needs_confirmation"},
                },
            ],
            "class_map": {"1": "left", "2": "right"},
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    metadata_item = dialog.file_tree.topLevelItem(0)
    assert metadata_item is not None
    metadata_item.setText(2, "session-01")

    for index in range(dialog.event_tree.topLevelItemCount()):
        item = dialog.event_tree.topLevelItem(index)
        if item is not None and item.text(0) == "1":
            item.setText(2, "left hand")

    result = dialog.get_result()

    assert result["choices"]["metadata_overrides"] == {
        "sub-01_task-mi.fif": {"session": "session-01"}
    }
    assert result["choices"]["class_map"] == {
        "1": "left hand",
        "2": "right",
    }


def test_data_interpretation_preview_dialog_blocks_apply(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "folder",
            "eeg_files": [],
            "label_carriers": [],
        },
        preview={
            "summary": "No supported EEG files were found.",
            "metadata_preview": [],
            "blocked_reasons": ["No supported EEG data files were found."],
        },
        validation_decision={
            "decision": "blocked",
            "blocked_reasons": ["No supported EEG data files were found."],
        },
    )
    qtbot.addWidget(dialog)

    ok_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button is not None
    assert not ok_button.isEnabled()
    assert not dialog.save_recipe_check.isEnabled()
    assert "blocked" in dialog.decision_label.text().lower()
    empty_event_item = dialog.event_tree.topLevelItem(0)
    assert empty_event_item is not None
    assert empty_event_item.text(0) == "No label/event carrier detected"
