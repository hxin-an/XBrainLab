"""Tests for the Data Interpretation preview dialog."""

from PyQt6.QtWidgets import QComboBox, QDialogButtonBox

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


def test_data_interpretation_preview_dialog_returns_label_carrier_review(qtbot):
    label_path = "/tmp/source/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [label_path],
        },
        preview={
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "A01T.mat",
                    "format": "MAT",
                    "label_candidates": ["classlabel", "target"],
                    "anchor_candidates": ["cue_onset", "trial"],
                    "selected_label_field": "",
                    "selected_anchor": "",
                    "time_model": "trial_order",
                    "granularity": "trial",
                    "reason": "MAT variables need review before apply.",
                }
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    assert dialog.label_carrier_tree.topLevelItemCount() == 1
    carrier_item = dialog.label_carrier_tree.topLevelItem(0)
    assert carrier_item is not None
    assert carrier_item.text(0) == "A01T.mat"
    assert carrier_item.text(1) == "A01T.gdf"
    assert carrier_item.text(2) == "MAT"
    assert "classlabel" in carrier_item.toolTip(3)
    assert "cue_onset" in carrier_item.toolTip(4)

    carrier_item.setText(3, "classlabel")
    carrier_item.setText(4, "cue_onset")
    carrier_item.setText(5, "sample_index")

    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"] == {
        label_path: {
            "label_field": "classlabel",
            "anchor": "cue_onset",
            "time_model": "sample_index",
            "granularity": "trial",
        }
    }


def test_data_interpretation_preview_dialog_shows_label_carrier_matches(qtbot):
    events_1 = "/tmp/source/sub-01_task-mi_run-1_events.tsv"
    events_2 = "/tmp/source/sub-01_task-mi_run-2_events.tsv"
    generic_events = "/tmp/source/events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [
                "/tmp/source/sub-01_task-mi_run-1_raw.fif",
                "/tmp/source/sub-01_task-mi_run-2_raw.fif",
            ],
            "label_carriers": [events_1, events_2, generic_events],
        },
        preview={
            "label_carrier_preview": [
                {
                    "path": events_1,
                    "name": "sub-01_task-mi_run-1_events.tsv",
                    "format": "BIDS events",
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "trial",
                },
                {
                    "path": events_2,
                    "name": "sub-01_task-mi_run-2_events.tsv",
                    "format": "BIDS events",
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "trial",
                },
                {
                    "path": generic_events,
                    "name": "events.tsv",
                    "format": "BIDS events",
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "trial",
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    first = dialog.label_carrier_tree.topLevelItem(0)
    second = dialog.label_carrier_tree.topLevelItem(1)
    generic = dialog.label_carrier_tree.topLevelItem(2)

    assert first is not None
    assert first.text(1) == "sub-01_task-mi_run-1_raw.fif"
    assert second is not None
    assert second.text(1) == "sub-01_task-mi_run-2_raw.fif"
    assert generic is not None
    assert generic.text(1) == "Needs review"


def test_data_interpretation_preview_dialog_returns_manual_label_target_mapping(qtbot):
    generic_events = "/tmp/source/events.tsv"
    target_name = "sub-01_task-mi_run-2_raw.fif"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [
                "/tmp/source/sub-01_task-mi_run-1_raw.fif",
                f"/tmp/source/{target_name}",
            ],
            "label_carriers": [generic_events],
        },
        preview={
            "label_carrier_preview": [
                {
                    "path": generic_events,
                    "name": "events.tsv",
                    "format": "BIDS events",
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "trial",
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    carrier_item = dialog.label_carrier_tree.topLevelItem(0)
    assert carrier_item is not None
    assert carrier_item.text(1) == "Needs review"
    target_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 1)
    assert isinstance(target_selector, QComboBox)
    assert [
        target_selector.itemText(index) for index in range(target_selector.count())
    ] == [
        "Needs review",
        "sub-01_task-mi_run-1_raw.fif",
        target_name,
    ]

    target_selector.setCurrentText(target_name)
    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"] == {
        generic_events: {
            "target_file": target_name,
            "label_field": "trial_type",
            "anchor": "onset",
            "time_model": "seconds",
            "granularity": "trial",
        }
    }


def test_data_interpretation_preview_dialog_shows_format_boundaries(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "format_capabilities": [
                {
                    "name": "brainvision.vhdr",
                    "format": "BrainVision",
                    "status": "needs_review",
                    "message": "Review stimulus, response, sync, and segment markers.",
                },
                {
                    "name": "lsl_recording.xdf",
                    "format": "XDF / LSL",
                    "status": "blocked",
                    "message": (
                        "XDF / LSL stream selection is not available in this "
                        "import wizard yet."
                    ),
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    details = dialog.review_text.toPlainText()

    assert "Format capabilities:" in details
    assert "BrainVision: needs review" in details
    assert "XDF / LSL: blocked" in details
    assert "stream selection is not available" in details


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
