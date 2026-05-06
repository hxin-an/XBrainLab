"""Tests for the Data Interpretation preview dialog."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QGroupBox,
    QHeaderView,
    QPlainTextEdit,
)

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
    assert "Select source | Scan result | Preview" in (
        dialog.workflow_steps_label.text()
    )
    assert dialog.file_tree.topLevelItemCount() == 1
    assert dialog.event_tree.topLevelItemCount() == 4
    group_titles = {group.title() for group in dialog.findChildren(QGroupBox)}
    assert "Label and Event Interpretation" in group_titles
    assert "Found 1 EEG file" in dialog.summary_label.text()
    assert "Review and confirm" in dialog.decision_label.text()
    review_text = _tree_text(dialog.review_tree)
    assert dialog.confirmation_label.text() == (
        "Review the items marked Needs confirmation, then confirm and apply."
    )
    assert "Confirm session metadata." in review_text
    assert "Downstream impact" in review_text
    assert "Training uses this recipe trace." in review_text
    assert not dialog.findChildren(QPlainTextEdit)
    ok_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button is not None
    assert ok_button.text() == "Confirm and Apply"
    assert dialog.get_result() == {
        "confirmed": True,
        "save_recipe": True,
        "choices": {},
    }


def test_data_interpretation_preview_dialog_tables_fit_product_layout(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_run-01.fif"],
            "label_carriers": ["/tmp/source/sub-01_task-mi_run-01_events.tsv"],
        },
        preview={
            "label_carrier_preview": [
                {
                    "path": "/tmp/source/sub-01_task-mi_run-01_events.tsv",
                    "name": "sub-01_task-mi_run-01_events.tsv",
                    "format": "TSV",
                    "label_candidates": ["trial_type", "value"],
                    "anchor_candidates": ["onset", "sample"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "event",
                    "role": "class cue labels",
                },
            ],
            "warnings": ["Review label-event mapping before applying."],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)
    dialog._fit_all_tree_columns_to_viewport()
    qtbot.wait(0)

    assert dialog.label_carrier_tree.textElideMode() == Qt.TextElideMode.ElideRight
    assert dialog.event_tree.textElideMode() == Qt.TextElideMode.ElideRight
    assert dialog.review_tree.textElideMode() == Qt.TextElideMode.ElideRight
    for tree in (
        dialog.file_tree,
        dialog.label_carrier_tree,
        dialog.event_tree,
        dialog.review_tree,
    ):
        header = tree.header()
        assert header is not None
        assert not header.stretchLastSection()
        for column in range(tree.columnCount()):
            assert (
                header.sectionResizeMode(column) == QHeaderView.ResizeMode.Interactive
            )
        viewport = tree.viewport()
        assert viewport is not None
        assert abs(header.length() - viewport.width()) <= 2
    assert dialog.review_tree.alternatingRowColors()
    assert "alternate-background-color" in dialog.styleSheet()
    assert "#232323" in dialog.styleSheet().lower()
    assert "#ffffff" not in dialog.styleSheet().lower()
    assert "#000000" not in dialog.styleSheet().lower()

    label_field_selector = dialog.label_carrier_tree.itemWidget(
        dialog.label_carrier_tree.topLevelItem(0),
        3,
    )
    assert isinstance(label_field_selector, QComboBox)
    assert label_field_selector.currentText() == "Trial type"
    assert label_field_selector.currentData() == "trial_type"
    assert dialog.label_carrier_tree.columnWidth(2) >= 96


def test_data_interpretation_preview_dialog_tables_shrink_without_overflow(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_run-01.fif"],
            "label_carriers": ["/tmp/source/sub-01_task-mi_run-01_events.tsv"],
        },
        preview={
            "metadata_preview": [
                {
                    "file": "sub-01_task-mi_run-01.fif",
                    "subject": {"value": "01", "decision": "safe"},
                    "session": {"value": "session-01", "decision": "safe"},
                    "task": {"value": "motor-imagery", "decision": "safe"},
                    "run": {"value": "01", "decision": "safe"},
                },
            ],
            "label_carrier_preview": [
                {
                    "path": "/tmp/source/sub-01_task-mi_run-01_events.tsv",
                    "name": "sub-01_task-mi_run-01_events.tsv",
                    "format": "BIDS events",
                    "label_candidates": ["trial_type"],
                    "anchor_candidates": ["onset"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "trial",
                    "role": "class cue labels",
                },
            ],
            "event_roles": {"trial_type": "class cue"},
            "recipe_trace": ["scan:scan-1", "candidate:candidate-1"],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(760, 720)
    dialog.show()
    qtbot.wait(0)
    dialog._fit_all_tree_columns_to_viewport()

    for tree in (
        dialog.file_tree,
        dialog.label_carrier_tree,
        dialog.event_tree,
        dialog.review_tree,
    ):
        header = tree.header()
        assert header is not None
        viewport = tree.viewport()
        horizontal_scrollbar = tree.horizontalScrollBar()
        assert viewport is not None
        assert horizontal_scrollbar is not None
        assert abs(header.length() - viewport.width()) <= 2
        assert horizontal_scrollbar.maximum() == 0


def test_data_interpretation_preview_dialog_label_selectors_fit_review_text(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [
                "/tmp/source/sub-01_task-mi_run-1_raw.fif",
                "/tmp/source/sub-01_task-mi_run-2_raw.fif",
            ],
            "label_carriers": ["/tmp/source/events.tsv"],
        },
        preview={
            "label_carrier_preview": [
                {
                    "path": "/tmp/source/events.tsv",
                    "name": "events.tsv",
                    "format": "TSV",
                    "selected_label_field": "",
                    "selected_anchor": "",
                    "time_model": "",
                    "granularity": "",
                    "role": "external labels",
                },
            ],
        },
        validation_decision={"decision": "blocked", "blocked_reasons": ["review"]},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 860)
    dialog.show()
    qtbot.wait(0)
    dialog._fit_all_tree_columns_to_viewport()
    qtbot.wait(0)

    item = dialog.label_carrier_tree.topLevelItem(0)
    assert item is not None
    for column in (5, 6):
        selector = dialog.label_carrier_tree.itemWidget(item, column)
        assert isinstance(selector, QComboBox)
        visible_text_width = selector.fontMetrics().horizontalAdvance(
            selector.currentText(),
        )
        assert dialog.label_carrier_tree.columnWidth(column) >= visible_text_width + 42


def test_data_interpretation_preview_dialog_review_summary_shows_whole_rows(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "warnings": [
                "Multiple EEG files were discovered; review subject/session mapping.",
                "External label/event carriers require preview before apply.",
            ],
            "confirmation_items": [
                "Confirm label carrier alignment.",
                "Confirm session metadata for sub-01.",
                "Confirm event role mapping.",
            ],
            "downstream_impacts": [
                "Training will use the confirmed recipe.",
                "Evaluation will use the same class map.",
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)

    review_tree = dialog.review_tree
    assert review_tree.topLevelItemCount() == 7
    viewport = review_tree.viewport()
    scrollbar = review_tree.verticalScrollBar()
    assert viewport is not None
    assert scrollbar is not None
    viewport_rect = viewport.rect()

    for row in range(review_tree.topLevelItemCount()):
        item = review_tree.topLevelItem(row)
        assert item is not None
        row_rect = review_tree.visualItemRect(item)
        if row_rect.isValid() and row_rect.top() < viewport_rect.bottom():
            assert row_rect.bottom() <= viewport_rect.bottom()
    assert scrollbar.maximum() > 0


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


def test_data_interpretation_preview_dialog_returns_event_role_review(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "event_roles": {
                "cue": "class label candidate",
                "onset": "time anchor",
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    for index in range(dialog.event_tree.topLevelItemCount()):
        item = dialog.event_tree.topLevelItem(index)
        if item is not None and item.text(0) == "Cue":
            role_selector = dialog.event_tree.itemWidget(item, 2)
            assert isinstance(role_selector, QComboBox)
            assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)
            assert role_selector.currentData() == "class label candidate"
            role_selector.setCurrentText("Class cue")

    result = dialog.get_result()

    assert result["choices"]["event_roles"] == {
        "cue": "class cue",
        "onset": "time anchor",
    }


def test_data_interpretation_preview_dialog_humanizes_event_role_names(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "event_roles": {
                "label_carrier": "external label or event source",
                "trial_type": "class cue",
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    visible_names = []
    for index in range(dialog.event_tree.topLevelItemCount()):
        item = dialog.event_tree.topLevelItem(index)
        if item is not None:
            visible_names.append(item.text(0))

    assert "Label carrier" in visible_names
    assert "Trial type" in visible_names
    assert "label_carrier" not in visible_names

    for index in range(dialog.event_tree.topLevelItemCount()):
        item = dialog.event_tree.topLevelItem(index)
        if item is not None and item.text(0) == "Label carrier":
            selector = dialog.event_tree.itemWidget(item, 2)
            assert isinstance(selector, QComboBox)
            selector.setCurrentText("Ignored")

    result = dialog.get_result()

    assert result["choices"]["event_roles"] == {
        "label_carrier": "ignored",
        "trial_type": "class cue",
    }


def test_data_interpretation_preview_dialog_uses_user_facing_decision_copy(qtbot):
    needs_review = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={},
        validation_decision={"decision": "needs_confirmation"},
    )
    ready = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={},
        validation_decision={"decision": "safe"},
    )
    blocked = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={},
        validation_decision={
            "decision": "blocked",
            "blocked_reasons": ["No supported EEG data files were found."],
        },
    )
    qtbot.addWidget(needs_review)
    qtbot.addWidget(ready)
    qtbot.addWidget(blocked)

    assert needs_review.decision_label.text() == (
        "Review and confirm these choices before applying."
    )
    assert ready.decision_label.text() == "Ready to apply."
    assert blocked.decision_label.text() == (
        "This source cannot be applied yet. Review the blocked items below."
    )
    assert "Validation" not in needs_review.decision_label.text()
    assert "safe" not in ready.decision_label.text().lower()


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
                    "role": "external labels",
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

    label_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 3)
    anchor_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 4)
    time_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 5)
    role_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 7)
    assert isinstance(label_selector, QComboBox)
    assert isinstance(anchor_selector, QComboBox)
    assert isinstance(time_selector, QComboBox)
    assert isinstance(role_selector, QComboBox)
    label_selector.setCurrentText("Classlabel")
    anchor_selector.setCurrentText("Cue onset")
    time_selector.setCurrentText("Sample index")
    role_selector.setCurrentText("Class cue labels")

    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"] == {
        label_path: {
            "label_field": "classlabel",
            "anchor": "cue_onset",
            "time_model": "sample_index",
            "granularity": "trial",
            "role": "class cue labels",
        }
    }


def test_data_interpretation_preview_dialog_uses_label_carrier_selectors(qtbot):
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
                    "selected_label_field": "classlabel",
                    "selected_anchor": "trial",
                    "time_model": "trial_order",
                    "granularity": "trial",
                    "role": "external labels",
                }
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    carrier_item = dialog.label_carrier_tree.topLevelItem(0)
    assert carrier_item is not None
    label_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 3)
    anchor_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 4)
    time_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 5)
    granularity_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 6)
    role_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 7)
    assert isinstance(label_selector, QComboBox)
    assert isinstance(anchor_selector, QComboBox)
    assert isinstance(time_selector, QComboBox)
    assert isinstance(granularity_selector, QComboBox)
    assert isinstance(role_selector, QComboBox)

    anchor_selector.setCurrentText("Cue onset")
    time_selector.setCurrentText("Sample index")
    role_selector.setCurrentText("Class cue labels")

    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"] == {
        label_path: {
            "label_field": "classlabel",
            "anchor": "cue_onset",
            "time_model": "sample_index",
            "granularity": "trial",
            "role": "class cue labels",
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
    assert first.text(1) == "sub-01 run-1"
    assert second is not None
    assert second.text(1) == "sub-01 run-2"
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
        "sub-01 run-1",
        "sub-01 run-2",
    ]

    target_selector.setCurrentIndex(target_selector.findData(target_name))
    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"] == {
        generic_events: {
            "target_file": target_name,
            "label_field": "trial_type",
            "anchor": "onset",
            "time_model": "seconds",
            "granularity": "trial",
            "role": "external labels",
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

    details = _tree_text(dialog.review_tree)

    assert "Format capability" in details
    assert "BrainVision: needs review" in details
    assert "XDF / LSL: blocked" in details
    assert "stream selection is not available" in details


def test_data_interpretation_preview_dialog_shows_recipe_reload_summary(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "recipe_reload_summary": {
                "message": (
                    "Saved recipe choices were reapplied before validation: "
                    "metadata overrides, event roles."
                ),
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    details = _tree_text(dialog.review_tree)

    assert "Reloaded recipe" in details
    assert "Reapplied" in details
    assert "Saved recipe choices were reapplied before validation" in details


def test_data_interpretation_preview_dialog_shows_recipe_reload_diff(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "recipe_reload_summary": {
                "message": "Saved recipe choices were reapplied before validation.",
                "diff_rows": [
                    {
                        "item": "EEG files",
                        "status": "Changed",
                        "detail": (
                            "Matched 1 saved file(s). Missing from scan: "
                            "missing.fif. New in scan: sub-02.fif."
                        ),
                    },
                    {
                        "item": "Saved choices",
                        "status": "Reapplied",
                        "detail": "metadata overrides, event roles.",
                    },
                ],
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    details = _tree_text(dialog.review_tree)

    assert "EEG files" in details
    assert "Changed" in details
    assert "missing.fif" in details
    assert "Saved choices" in details


def test_data_interpretation_preview_dialog_returns_label_carrier_remap(qtbot):
    old_events = "/tmp/source/old_events.tsv"
    new_events = "/tmp/source/renamed_events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_raw.fif"],
            "label_carriers": [new_events],
        },
        preview={
            "recipe_reload_summary": {
                "message": "Saved recipe choices were reapplied before validation.",
                "label_carrier_remap_options": [
                    {
                        "saved": old_events,
                        "saved_name": "old_events.tsv",
                        "candidates": [
                            {
                                "path": new_events,
                                "name": "renamed_events.tsv",
                            }
                        ],
                    }
                ],
            },
        },
        validation_decision={
            "decision": "blocked",
            "blocked_reasons": [
                "Saved label/event carrier(s) were not found in the current scan: old_events.tsv.",
            ],
        },
    )
    qtbot.addWidget(dialog)

    ok_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button is not None
    assert ok_button.isEnabled()
    assert ok_button.text() == "Apply Remap"
    assert (
        dialog.decision_label.text()
        == "Choose the replacement label/event carrier before applying."
    )
    assert "replacement label/event carrier" in dialog.confirmation_label.text()
    assert "cannot be applied" not in dialog.confirmation_label.text()

    details = _tree_text(dialog.review_tree)
    assert "Remap label carrier" in details
    assert "Select" in details
    assert "old_events.tsv" in details

    selector = next(iter(dialog._label_carrier_remap_widgets.values()))
    assert isinstance(selector, QComboBox)
    assert selector.currentData() == new_events

    result = dialog.get_result()

    assert result["confirmed"] is True
    assert result["choices"]["label_carrier_remap"] == {
        old_events: new_events,
    }


def test_data_interpretation_preview_dialog_returns_eeg_file_remap(qtbot):
    old_file = "/tmp/source/old_raw.fif"
    new_file = "/tmp/source/renamed_raw.fif"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [new_file],
            "label_carriers": [],
        },
        preview={
            "recipe_reload_summary": {
                "message": "Saved recipe choices were reapplied before validation.",
                "eeg_file_remap_options": [
                    {
                        "saved": old_file,
                        "saved_name": "old_raw.fif",
                        "candidates": [
                            {
                                "path": new_file,
                                "name": "renamed_raw.fif",
                            }
                        ],
                    }
                ],
            },
        },
        validation_decision={
            "decision": "blocked",
            "blocked_reasons": [
                "Selected EEG file(s) were not found in the current scan: old_raw.fif.",
            ],
        },
    )
    qtbot.addWidget(dialog)

    ok_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button is not None
    assert ok_button.isEnabled()
    assert ok_button.text() == "Apply Remap"
    assert dialog.decision_label.text() == (
        "Choose the replacement EEG file before applying."
    )
    assert "replacement EEG file" in dialog.confirmation_label.text()

    details = _tree_text(dialog.review_tree)
    assert "Remap EEG file" in details
    assert "old_raw.fif" in details

    selector = next(iter(dialog._eeg_file_remap_widgets.values()))
    assert isinstance(selector, QComboBox)
    assert selector.currentData() == new_file

    result = dialog.get_result()

    assert result["confirmed"] is True
    assert result["choices"]["eeg_file_remap"] == {
        old_file: new_file,
    }


def test_data_interpretation_preview_dialog_requires_each_remap_choice(qtbot):
    old_file = "/tmp/source/old_raw.fif"
    first_file = "/tmp/source/sub-01_raw.fif"
    second_file = "/tmp/source/sub-02_raw.fif"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [first_file, second_file],
            "label_carriers": [],
        },
        preview={
            "recipe_reload_summary": {
                "message": "Saved recipe choices were reapplied before validation.",
                "eeg_file_remap_options": [
                    {
                        "saved": old_file,
                        "saved_name": "old_raw.fif",
                        "candidates": [
                            {"path": first_file, "name": "sub-01_raw.fif"},
                            {"path": second_file, "name": "sub-02_raw.fif"},
                        ],
                    }
                ],
            },
        },
        validation_decision={
            "decision": "blocked",
            "blocked_reasons": [
                "Selected EEG file(s) were not found in the current scan: old_raw.fif.",
            ],
        },
    )
    qtbot.addWidget(dialog)

    ok_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
    selector = next(iter(dialog._eeg_file_remap_widgets.values()))
    assert ok_button is not None
    assert isinstance(selector, QComboBox)
    assert not ok_button.isEnabled()
    assert dialog.get_result()["confirmed"] is False

    selector.setCurrentIndex(selector.findData(second_file))

    assert ok_button.isEnabled()
    assert dialog.get_result()["confirmed"] is True
    assert dialog.get_result()["choices"]["eeg_file_remap"] == {
        old_file: second_file,
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


def _tree_text(tree) -> str:
    values: list[str] = []
    for row in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(row)
        if item is None:
            continue
        for column in range(tree.columnCount()):
            text = item.text(column).strip()
            if text:
                values.append(text)
    return "\n".join(values)
