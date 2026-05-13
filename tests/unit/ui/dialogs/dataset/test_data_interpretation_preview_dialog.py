"""Tests for the Data Interpretation preview dialog."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
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
            "source_selection": "Single file",
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

    assert dialog.windowTitle() == "Import EEG Data"
    assert dialog.decision == "needs_confirmation"
    assert "Choose EEG Data | Load Labels | Review Metadata" in (
        dialog.workflow_steps_label.text()
    )
    assert dialog.file_tree.topLevelItemCount() == 1
    assert dialog.event_tree.topLevelItemCount() == 2
    panel_titles = set(_panel_titles(dialog))
    assert "Choose EEG Data" in panel_titles
    assert "Load Labels" in panel_titles
    assert "Review Metadata" in panel_titles
    assert "Match Labels" in panel_titles
    assert "Review and Import" in panel_titles
    assert dialog.event_group.title() == ""
    event_group_text = "\n".join(
        label.text()
        for label in dialog.event_group.findChildren(QLabel)
        if label.text().strip()
    )
    assert "Labels inside EEG files" in event_group_text
    assert "Found 1 EEG file" in dialog.summary_label.text()
    assert "Review and confirm" in dialog.decision_label.text()
    review_text = _tree_text(dialog.review_tree)
    scope_text = _group_text(dialog, "Choose EEG Data")
    assert "Selected scope" in scope_text
    assert "Single file" in scope_text
    assert "Scan location" in scope_text
    assert "Type" not in scope_text
    review_header = dialog.review_tree.headerItem()
    assert review_header is not None
    assert [
        review_header.text(index) for index in range(dialog.review_tree.columnCount())
    ] == [
        "Target step",
        "Issue",
        "Impact",
        "Next action",
    ]
    assert dialog.confirmation_label.text() == (
        "Review the items marked Needs confirmation, then confirm and apply."
    )
    assert "Confirm session metadata." in review_text
    assert "After import" not in review_text
    assert "Training uses this recipe trace." not in review_text
    assert not dialog.findChildren(QPlainTextEdit)
    assert dialog.apply_button.text() == "Confirm and Apply"
    assert dialog.get_result() == {
        "confirmed": True,
        "save_recipe": True,
        "choices": {},
    }


def test_data_interpretation_preview_dialog_uses_one_panel_per_step(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_raw.fif"],
            "label_carriers": ["/tmp/source/events.tsv"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "metadata_preview": [
                {
                    "file": "sub-01_task-mi_raw.fif",
                    "subject": {"value": "01", "decision": "safe"},
                    "session": {"value": "01", "decision": "safe"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": "1", "decision": "safe"},
                },
            ],
            "label_carrier_preview": [
                {
                    "path": "/tmp/source/events.tsv",
                    "name": "events.tsv",
                    "format": "TSV",
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "trial",
                    "role": "class cue labels",
                },
            ],
            "event_roles": {"trial_type": "class cue"},
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(960, 640)
    dialog.show()
    qtbot.wait(0)

    ok_button = dialog.apply_button
    cancel_button = dialog.cancel_button

    assert dialog.step_stack.currentIndex() == 0
    assert _visible_group_titles(dialog) == ["Choose EEG Data"]
    assert not dialog.back_button.isEnabled()
    assert dialog.next_button.isVisible()
    assert _widget_left(cancel_button, dialog) < _widget_left(
        dialog.back_button,
        dialog,
    )
    assert dialog.next_button.text() == "Next: Load Labels"
    assert not ok_button.isVisible()

    dialog.next_button.click()
    qtbot.wait(0)
    assert dialog.step_stack.currentIndex() == 1
    assert _visible_group_titles(dialog) == ["Load Labels"]
    assert dialog.back_button.isEnabled()
    assert dialog.next_button.text() == "Next: Review Metadata"
    assert not ok_button.isVisible()

    dialog.next_button.click()
    qtbot.wait(0)
    assert dialog.step_stack.currentIndex() == 2
    assert _visible_group_titles(dialog) == ["Review Metadata"]
    assert dialog.next_button.text() == "Next: Match Labels"

    dialog.next_button.click()
    qtbot.wait(0)
    assert dialog.step_stack.currentIndex() == 3
    assert _visible_group_titles(dialog) == ["Match Labels"]
    assert dialog.next_button.text() == "Next: Review and Import"

    dialog.next_button.click()
    qtbot.wait(0)
    assert dialog.step_stack.currentIndex() == 4
    assert _visible_group_titles(dialog) == ["Review and Import"]
    assert not dialog.next_button.isVisible()
    assert ok_button.isVisible()
    assert ok_button.text() == "Apply Interpretation"
    assert dialog.confirmation_label.isVisible()
    assert dialog.save_recipe_check.isVisible()


def test_data_interpretation_preview_dialog_shows_selected_files_not_scan_type(qtbot):
    scanned_files = [f"/tmp/source/A{index:02d}T.gdf" for index in range(1, 17)]
    selected_files = scanned_files[:3]
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "folder",
            "eeg_files": scanned_files,
        },
        preview={
            "summary": "Found 3 EEG file(s).",
            "source_selection": "3 selected file(s)",
            "selected_eeg_files": selected_files,
            "file_count": 3,
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    scope_text = _group_text(dialog, "Choose EEG Data")

    assert "3 selected file(s)" in scope_text
    assert "A01T.gdf, A02T.gdf, A03T.gdf" in scope_text
    assert "+13 more" not in scope_text
    assert "Scan location" in scope_text
    assert "folder" not in scope_text.lower()


def test_choose_eeg_data_cards_stay_compact_for_small_selection(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "folder",
            "eeg_files": [f"/tmp/source/A{index:02d}T.gdf" for index in range(1, 17)],
            "label_carriers": [
                "/tmp/source/events.tsv",
                "/tmp/source/events.json",
                "/tmp/source/markers.csv",
            ],
        },
        preview={
            "summary": "Found 3 EEG file(s) and 3 label/event carrier(s).",
            "source_selection": "3 selected file(s)",
            "selected_eeg_files": [
                "/tmp/source/A01T.gdf",
                "/tmp/source/A02T.gdf",
                "/tmp/source/A03T.gdf",
            ],
            "file_count": 3,
            "label_carrier_count": 3,
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    _show_step(dialog, "Choose EEG Data")
    qtbot.wait(0)

    metric_cards = [
        card
        for card in dialog.findChildren(QFrame)
        if card.objectName() == "DataImportMetricCard"
    ]
    assert metric_cards
    assert max(card.height() for card in metric_cards) <= 150
    scrollbar = dialog.scroll_area.verticalScrollBar()
    assert scrollbar is not None
    assert scrollbar.maximum() == 0
    assert (
        dialog.scroll_area.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


def test_load_labels_step_does_not_hidden_scroll_when_content_fits(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [
                "/tmp/source/labels/A01T.mat",
                "/tmp/source/labels/A02T.mat",
                "/tmp/source/labels/A03T.mat",
            ],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 3 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": f"/tmp/source/labels/A0{index}T.mat",
                    "name": f"A0{index}T.mat",
                    "source_kind": "auto",
                    "source_location": "/tmp/source/labels",
                }
                for index in range(1, 4)
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    scrollbar = dialog.scroll_area.verticalScrollBar()
    assert scrollbar is not None
    assert (
        dialog.scroll_area.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert scrollbar.maximum() == 0
    scrollbar.setValue(20)
    dialog._sync_scroll_policy()
    assert scrollbar.value() == 0


def test_data_interpretation_preview_dialog_uses_task_oriented_label_headers(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_raw.fif"],
            "label_carriers": ["/tmp/labels/sub-01_task-mi_events.tsv"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "label_carrier_preview": [
                {
                    "path": "/tmp/labels/sub-01_task-mi_events.tsv",
                    "name": "sub-01_task-mi_events.tsv",
                    "format": "TSV",
                    "label_candidates": ["trial_type"],
                    "anchor_candidates": ["onset"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "trial",
                    "role": "class cue labels",
                    "source_kind": "user_added",
                    "source_location": "/tmp/labels",
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    label_header = dialog.label_carrier_tree.headerItem()
    assert label_header is not None
    headers = [
        label_header.text(index)
        for index in range(dialog.label_carrier_tree.columnCount())
    ]

    assert headers == [
        "Label file",
        "EEG file",
        "Label source",
        "Alignment",
        "Label unit",
        "Use as",
    ]
    assert "Anchor" not in headers
    assert "Time" not in headers
    assert "Granularity" not in headers
    assert "Role" not in headers


def test_match_labels_uses_selected_scope_not_scanned_folder(qtbot):
    scanned_files = [f"/tmp/source/A{index:02d}T.gdf" for index in range(1, 17)]
    selected_files = scanned_files[:3]
    labels = [f"/tmp/source/labels/A{index:02d}T.mat" for index in range(1, 4)]
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "folder",
            "eeg_files": scanned_files,
            "label_carriers": labels,
        },
        preview={
            "summary": "Found 3 EEG file(s) and 3 label/event carrier(s).",
            "source_selection": "3 selected file(s)",
            "selected_eeg_files": selected_files,
            "file_count": 3,
            "label_carrier_count": 3,
            "label_carrier_preview": [
                {
                    "path": labels[index],
                    "name": f"A{index + 1:02d}T.mat",
                    "format": "MAT",
                    "selected_label_field": "classlabel",
                    "selected_anchor": "trial order",
                    "time_model": "trial_order",
                    "granularity": "trial",
                    "role": "class cue labels",
                }
                for index in range(3)
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    _show_step(dialog, "Match Labels")

    assert "3/3 EEG files paired" in dialog.pairing_status_label.text()
    assert "13" not in dialog.pairing_status_label.text()
    assert sorted(dialog._eeg_label_widgets) == [
        "A01T.gdf",
        "A02T.gdf",
        "A03T.gdf",
    ]
    header = dialog.label_pairing_rows_widget.findChild(
        QFrame,
        "DataImportPairingHeader",
    )
    assert header is not None
    assert [label.text() for label in header.findChildren(QLabel)] == [
        "EEG file",
        "Label file",
        "Status",
    ]

    first_carrier = dialog.label_carrier_tree.topLevelItem(0)
    assert first_carrier is not None
    target_selector = dialog._label_target_widgets[id(first_carrier)]
    assert [
        target_selector.itemText(index) for index in range(target_selector.count())
    ] == [
        "Choose EEG file",
        "A01T.gdf",
        "A02T.gdf",
        "A03T.gdf",
    ]


def test_match_labels_pairing_board_applies_dataset_level_choices(qtbot):
    labels = ["/tmp/source/A01T.mat", "/tmp/source/A02T.mat"]
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf", "/tmp/source/A02T.gdf"],
            "label_carriers": labels,
        },
        preview={
            "summary": "Found 2 EEG file(s) and 2 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": labels[index],
                    "name": f"A0{index + 1}T.mat",
                    "format": "MAT",
                    "label_candidates": ["classlabel", "target"],
                    "anchor_candidates": ["trial order", "cue_onset"],
                    "selected_label_field": "",
                    "selected_anchor": "",
                    "time_model": "trial_order",
                    "granularity": "trial",
                    "role": "external labels",
                }
                for index in range(2)
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    _show_step(dialog, "Match Labels")

    assert dialog.label_match_mode_combo.currentData() == "filename_stem"
    assert "2/2 EEG files paired" in dialog.pairing_status_label.text()
    assert "2/2 paired" in dialog.rule_status_label.text()

    dialog.rule_label_field_combo.setCurrentIndex(
        dialog.rule_label_field_combo.findData("target")
    )
    dialog.rule_alignment_combo.setCurrentIndex(
        dialog.rule_alignment_combo.findData("cue_onset")
    )
    dialog.rule_use_as_combo.setCurrentIndex(
        dialog.rule_use_as_combo.findData("class cue labels")
    )

    for row in range(2):
        item = dialog.label_carrier_tree.topLevelItem(row)
        assert item is not None
        label_selector = dialog.label_carrier_tree.itemWidget(item, 2)
        anchor_selector = dialog.label_carrier_tree.itemWidget(item, 3)
        role_selector = dialog.label_carrier_tree.itemWidget(item, 5)
        assert isinstance(label_selector, QComboBox)
        assert isinstance(anchor_selector, QComboBox)
        assert isinstance(role_selector, QComboBox)
        assert label_selector.currentData() == "target"
        assert anchor_selector.currentData() == "cue_onset"
        assert role_selector.currentData() == "class cue labels"

    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"] == {
        labels[0]: {
            "label_field": "target",
            "anchor": "cue_onset",
            "time_model": "trial_order",
            "placement_method": "eeg_event",
            "granularity": "trial",
            "role": "class cue labels",
        },
        labels[1]: {
            "label_field": "target",
            "anchor": "cue_onset",
            "time_model": "trial_order",
            "placement_method": "eeg_event",
            "granularity": "trial",
            "role": "class cue labels",
        },
    }
    assert "Target · EEG event order · at Cue onset" in dialog.rule_status_label.text()


def test_match_labels_internal_source_hides_loaded_label_setup(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "event_roles": {"internal_events": "class cue"},
            "class_map": {"769": "left", "770": "right"},
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    assert dialog.label_source_mode_combo.currentData() == "internal_events"
    assert dialog.label_source_mode_combo.width() == 225
    assert dialog.label_source_mode_combo.maximumWidth() == 225
    assert "Use labels from" not in _visible_step_text(dialog, "Match Labels")
    assert "Source" in _visible_step_text(dialog, "Match Labels")
    assert "Use events inside the EEG files" not in _visible_step_text(
        dialog,
        "Match Labels",
    )
    assert not dialog.internal_event_card.isVisible()
    assert dialog.event_group.isVisible()
    assert dialog.event_group.title() == ""
    event_group_text = "\n".join(
        label.text()
        for label in dialog.event_group.findChildren(QLabel)
        if label.text().strip()
    )
    assert "Labels inside EEG files" in event_group_text
    assert not dialog.pairing_card.isVisible()
    assert not dialog.label_values_card.isVisible()
    assert not dialog.placement_card.isVisible()
    assert "Using labels inside EEG files" in dialog.rule_status_label.text()


def test_match_labels_internal_source_does_not_return_label_file_choices(qtbot):
    label_path = "/tmp/labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [label_path],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "A01T.mat",
                    "format": "MAT",
                    "label_candidates": ["classlabel"],
                    "anchor_candidates": ["trial order"],
                    "selected_label_field": "classlabel",
                    "selected_anchor": "trial order",
                    "time_model": "trial_order",
                    "granularity": "trial",
                    "placement_method": "eeg_event",
                    "role": "class cue labels",
                },
            ],
            "event_roles": {"internal_events": "event role candidates"},
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    _show_step(dialog, "Match Labels")

    dialog.label_source_mode_combo.setCurrentIndex(
        dialog.label_source_mode_combo.findData("internal_events")
    )
    result = dialog.get_result()

    assert result["choices"]["label_carrier"] == "embedded_events"
    assert "label_carrier_choices" not in result["choices"]


def test_match_labels_internal_source_hides_label_file_class_map(qtbot):
    label_path = "/tmp/labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [label_path],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "A01T.mat",
                    "format": "MAT",
                    "selected_label_field": "classlabel",
                    "selected_anchor": "trial order",
                },
            ],
            "class_map": {"1": "1", "2": "2", "3": "3", "4": "4"},
            "class_map_source": "label_carriers",
            "event_roles": {"internal_events": "event role candidates"},
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    _show_step(dialog, "Match Labels")

    assert [item[1] for item in dialog._class_map_items] == ["1", "2", "3", "4"]

    dialog.label_source_mode_combo.setCurrentIndex(
        dialog.label_source_mode_combo.findData("internal_events")
    )
    result = dialog.get_result()

    assert dialog._class_map_items == []
    assert "class_map" not in result["choices"]
    assert result["choices"]["label_carrier"] == "embedded_events"
    assert "Internal EEG events" in _tree_text(dialog.event_tree)


def test_match_labels_can_toggle_source_after_class_map_widget_rebuild(qtbot):
    label_path = "/tmp/labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [label_path],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "A01T.mat",
                    "format": "MAT",
                    "selected_label_field": "classlabel",
                    "selected_anchor": "trial order",
                },
            ],
            "class_map": {"1": "1", "2": "2"},
            "class_map_source": "label_carriers",
            "event_roles": {"internal_events": "event role candidates"},
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    dialog.label_source_mode_combo.setCurrentIndex(
        dialog.label_source_mode_combo.findData("internal_events")
    )
    qtbot.wait(0)
    dialog.label_source_mode_combo.setCurrentIndex(
        dialog.label_source_mode_combo.findData("loaded_label_files")
    )
    qtbot.wait(0)
    dialog.label_source_mode_combo.setCurrentIndex(
        dialog.label_source_mode_combo.findData("internal_events")
    )
    qtbot.wait(0)

    assert dialog._class_map_items == []
    assert "class_map" not in dialog.get_result()["choices"]


def test_match_labels_internal_source_uses_task_panel_for_suggested_events(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [
                "/tmp/source/A01T.gdf",
                "/tmp/source/A02T.gdf",
                "/tmp/source/A03T.gdf",
            ],
        },
        preview={
            "summary": "Found 3 EEG file(s).",
            "internal_event_preview": {
                "pattern_status": "Shared event pattern detected",
                "names_reliable": False,
                "candidate_label_events": [
                    {
                        "code": "1",
                        "event_code": "769",
                        "use_as": "Class label",
                        "coverage": "3/3 files",
                        "event_count": 288,
                        "evidence": "Repeats once per trial",
                    },
                    {
                        "code": "2",
                        "event_code": "770",
                        "use_as": "Class label",
                        "coverage": "3/3 files",
                        "event_count": 288,
                        "evidence": "Repeats once per trial",
                    },
                ],
                "not_used_events": [
                    {
                        "code": "768",
                        "use_as": "Epoch anchor",
                        "reason": "Trial start event",
                        "event_count": 288,
                    },
                    {
                        "code": "1023",
                        "use_as": "Exclude",
                        "reason": "Rejected trial / artifact",
                        "event_count": 6,
                    },
                ],
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    visible_text = "\n".join(
        label.text()
        for label in dialog.event_group.findChildren(QLabel)
        if label.text().strip()
    )
    assert "Suggested training labels" in visible_text
    assert "Use this when class labels are stored as EEG events." not in visible_text
    assert "Other EEG events" in visible_text
    assert "not currently used as class labels" in visible_text
    assert "Selection preview: train on 769, 770" in visible_text
    assert "not used: 768, 1023" in visible_text
    assert "Event names need review" in visible_text
    assert "769" in visible_text
    assert "770" in visible_text
    assert "Class label" in visible_text
    assert "Repeats once per trial" in visible_text
    assert "288 events · 3/3 files" in visible_text
    assert "6 events · 3/3 files" in visible_text
    assert "768" in visible_text
    assert "Epoch anchor" in visible_text
    assert "Trial start event" in visible_text
    assert dialog.event_group.title() == ""
    assert dialog.event_group.maximumHeight() > 1000

    assert [item[1] for item in dialog._class_map_items] == ["769", "770"]
    first_item = dialog.event_tree.topLevelItem(0)
    assert first_item is not None
    class_selector = dialog.event_tree.itemWidget(first_item, 2)
    assert isinstance(class_selector, QComboBox)
    assert class_selector.currentText() == ""

    class_selector.setCurrentText("Left hand")

    assert dialog.get_result()["choices"]["class_map"] == {"769": "left hand"}


def test_match_labels_internal_source_moves_events_between_sections(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf", "/tmp/source/A02T.gdf"],
        },
        preview={
            "summary": "Found 2 EEG file(s).",
            "internal_event_preview": {
                "pattern_status": "Shared event pattern detected",
                "candidate_label_events": [
                    {"code": "1", "event_code": "769", "coverage": "2/2 files"},
                    {"code": "2", "event_code": "770", "coverage": "2/2 files"},
                ],
                "not_used_events": [
                    {
                        "code": "768",
                        "use_as": "Trial timing",
                        "reason": "Trial start marker",
                        "coverage": "2/2 files",
                    },
                ],
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    assert [item[1] for item in dialog._class_map_items] == ["769", "770"]

    _click_button(dialog, "Not a label", event_code="769")
    qtbot.wait(0)

    visible_text = "\n".join(
        label.text()
        for label in dialog.event_group.findChildren(QLabel)
        if label.text().strip()
    )
    assert "Changed by user" in visible_text
    assert [item[1] for item in dialog._class_map_items] == ["770"]
    assert dialog.get_result()["choices"]["event_roles"] == {"769": "not a label"}

    _click_button(dialog, "Use as label", event_code="769")
    qtbot.wait(0)

    assert [item[1] for item in dialog._class_map_items] == ["769", "770"]
    assert dialog.get_result()["choices"]["event_roles"] == {"769": "class label"}


def test_match_labels_class_names_are_sorted_by_code(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "class_map": {"770": "right", "769": "left", "771": "feet"},
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    assert [item[1] for item in dialog._class_map_items] == ["769", "770", "771"]


def test_match_labels_preserves_placement_and_duration_for_epoch_handoff(qtbot):
    events_path = "/tmp/labels/sub-01_task-mi_events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_raw.fif"],
            "label_carriers": [events_path],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": events_path,
                    "name": "sub-01_task-mi_events.tsv",
                    "format": "BIDS events",
                    "label_candidates": ["trial_type", "value"],
                    "anchor_candidates": ["onset"],
                    "duration_candidates": ["duration", "end"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "time_model": "seconds",
                    "granularity": "event",
                    "placement_method": "interval",
                    "role": "external labels",
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    _show_step(dialog, "Match Labels")

    assert dialog.label_source_mode_combo.currentData() == "loaded_label_files"
    assert dialog.rule_placement_method_combo.currentData() == "interval"
    assert dialog.rule_duration_field_combo.currentData() == "duration"

    dialog.rule_duration_field_combo.setCurrentIndex(
        dialog.rule_duration_field_combo.findData("end")
    )
    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"] == {
        events_path: {
            "label_field": "trial_type",
            "anchor": "onset",
            "time_model": "seconds",
            "placement_method": "interval",
            "duration_field": "end",
            "granularity": "event",
            "role": "external labels",
        }
    }
    assert "Label interval" in dialog.placement_status_label.text()
    assert "duration/end field End" in dialog.placement_status_label.text()


def test_match_labels_loaded_label_files_use_discussed_rule_wording(qtbot):
    label_path = "/tmp/labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [label_path],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "A01T.mat",
                    "format": "MAT",
                    "target_file": "A01T.gdf",
                    "label_candidates": ["classlabel"],
                    "anchor_candidates": ["trial order"],
                    "selected_label_field": "classlabel",
                    "selected_anchor": "trial order",
                    "time_model": "trial_order",
                    "granularity": "trial",
                    "role": "external labels",
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    visible_text = _visible_step_text(dialog, "Match Labels")

    assert "File pairing" in visible_text
    assert "Label values and placement" in visible_text
    assert "Read labels from" in visible_text
    assert "Place labels by" in visible_text
    assert "Target EEG events" in visible_text
    assert "Use as" in visible_text
    assert "Label field" not in visible_text
    assert "Align to" not in visible_text
    assert "Label unit" not in visible_text
    assert "<-" not in visible_text
    assert "Target event / time" not in visible_text
    assert "Placement method" not in visible_text


def test_match_labels_eeg_event_order_shows_target_event_check(qtbot):
    label_path = "/tmp/labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [label_path],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "A01T.mat",
                    "format": "MAT",
                    "target_file": "A01T.gdf",
                    "label_candidates": ["classlabel"],
                    "anchor_candidates": ["trial order"],
                    "selected_label_field": "classlabel",
                    "selected_anchor": "trial order",
                    "label_row_count": 282,
                    "label_value_counts": {"1": 72, "2": 70, "3": 70, "4": 70},
                    "time_model": "trial_order",
                    "granularity": "trial",
                    "placement_method": "eeg_event",
                    "role": "external labels",
                },
            ],
            "internal_event_preview": {
                "candidate_label_events": [
                    {
                        "event_code": "769",
                        "use_as": "Class label",
                        "event_count": 72,
                    }
                ],
                "not_used_events": [
                    {
                        "event_code": "768",
                        "use_as": "Trial timing",
                        "event_count": 288,
                        "reason": "Count matches candidate label group",
                    },
                    {
                        "event_code": "1023",
                        "use_as": "Artifact",
                        "event_count": 6,
                    },
                ],
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    assert dialog.rule_placement_method_combo.currentData() == "eeg_event"
    assert "768" in [
        dialog.rule_alignment_combo.itemData(index)
        for index in range(dialog.rule_alignment_combo.count())
    ]

    dialog.rule_alignment_combo.setCurrentIndex(
        dialog.rule_alignment_combo.findData("768")
    )
    qtbot.wait(0)

    visible_text = _visible_step_text(dialog, "Match Labels")
    assert "EEG event order" in visible_text
    assert "Target EEG events" in visible_text
    assert "Target" in visible_text
    assert "Event" in visible_text
    assert "Suggestion evidence" in visible_text
    assert "Use" in visible_text
    assert "768" in visible_text
    assert "288 selected EEG events" in visible_text
    assert "282 label rows" in visible_text
    assert "6 unlabeled EEG events" in visible_text
    assert "6 EEG events excluded" in visible_text

    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"][label_path]["anchor"] == "768"
    assert (
        result["choices"]["label_carrier_choices"][label_path]["placement_method"]
        == "eeg_event"
    )


def test_match_labels_placement_methods_use_mode_specific_panels(qtbot):
    label_path = "/tmp/labels/sub-01_events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_raw.fif"],
            "label_carriers": [label_path],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "sub-01_events.tsv",
                    "format": "TSV",
                    "target_file": "sub-01_task-mi_raw.fif",
                    "label_candidates": ["trial_type", "value"],
                    "anchor_candidates": ["onset", "event_code"],
                    "time_field_candidates": ["onset"],
                    "interval_start_candidates": ["onset"],
                    "event_code_candidates": ["event_code"],
                    "duration_candidates": ["duration", "end"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "label_row_count": 12,
                    "label_value_counts": {"left": 6, "right": 6},
                    "time_model": "seconds",
                    "granularity": "event",
                    "placement_method": "time_field",
                    "role": "external labels",
                    "placement_reviews": {
                        "time_field": {
                            "method": "time_field",
                            "status": "ready",
                            "time_field": "onset",
                            "summary": "12/12 numeric rows, range 0 to 11.",
                        },
                        "interval": {
                            "method": "interval",
                            "status": "ready",
                            "time_field": "onset",
                            "duration_field": "duration",
                            "summary": "12 interval rows using onset and duration.",
                        },
                        "event_code": {
                            "method": "event_code",
                            "status": "needs_review",
                            "event_code_field": "event_code",
                            "summary": "1/2 label event codes were found in EEG events.",
                        },
                    },
                },
            ],
            "internal_event_preview": {
                "not_used_events": [
                    {
                        "event_code": "768",
                        "use_as": "Trial timing",
                        "event_count": 12,
                    },
                ],
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    expectations = {
        "eeg_event": ("Target EEG events", "Label time field"),
        "time_field": ("Label time field", "Target EEG events"),
        "interval": ("Start field", "Label event code field"),
        "event_code": ("Label event code field", "Start field"),
    }
    for method, (included, excluded) in expectations.items():
        dialog.placement_method_buttons[method].click()
        qtbot.wait(0)
        visible_text = _visible_step_text(dialog, "Match Labels")
        assert dialog.rule_placement_method_combo.currentData() == method
        assert included in visible_text
        assert excluded not in visible_text
        assert "Align to" not in visible_text
        if method == "event_code":
            assert "1/2 label event codes were found" in (
                dialog.placement_status_label.text()
            )

    target_buttons = [
        button
        for button in dialog.findChildren(QRadioButton)
        if button.objectName() == "DataImportTargetEventRadio"
    ]
    assert target_buttons


def test_match_labels_shows_conversion_card_when_label_rows_are_unknown(qtbot):
    label_path = "/tmp/labels/custom_labels.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [label_path],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "custom_labels.mat",
                    "format": "MAT",
                    "target_file": "A01T.gdf",
                    "label_candidates": [],
                    "anchor_candidates": [],
                    "selected_label_field": "",
                    "selected_anchor": "",
                    "label_row_count": 0,
                    "label_value_counts": {},
                    "time_model": "unknown",
                    "granularity": "unknown",
                    "placement_method": "eeg_event",
                    "role": "external labels",
                },
            ],
        },
        validation_decision={
            "decision": "blocked",
            "blocked_reasons": ["Label file needs conversion before matching."],
        },
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    assert dialog.label_conversion_card.isVisible()
    assert not dialog.label_values_card.isVisible()
    assert not dialog.match_check_card.isVisible()
    assert not dialog.apply_button.isEnabled()

    visible_text = _visible_step_text(dialog, "Match Labels")
    assert "Label format needs conversion" in visible_text
    assert "loaded the label file" in visible_text
    assert "one label, trial, event, or interval" in visible_text
    assert "Label values and placement" not in visible_text

    examples_button = dialog.label_conversion_card.findChild(QPushButton)
    assert examples_button is not None
    assert examples_button.text() == "View required table"


def test_data_interpretation_preview_dialog_records_attached_label_folder(
    qtbot,
    monkeypatch,
):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_raw.fif"],
        },
        preview={"summary": "Found 1 EEG file(s)."},
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: "/tmp/external-labels",
    )

    dialog.add_label_folder_btn.click()

    result = dialog.get_result()
    assert result["label_sources"] == ["/tmp/external-labels"]
    assert result["label_sources_changed"] is True
    assert "external-labels" in _group_text(dialog, "Load Labels")
    assert dialog.label_sources_label.isHidden()


def test_load_labels_step_removes_loaded_label_source(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_raw.fif"],
            "label_sources": ["/tmp/external-labels"],
        },
        preview={"summary": "Found 1 EEG file(s)."},
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    remove_buttons = [
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == "Remove"
    ]
    assert len(remove_buttons) == 1

    remove_buttons[0].click()
    qtbot.wait(0)

    result = dialog.get_result()
    assert result["label_sources"] == []
    assert result["label_sources_changed"] is True
    visible_text = _visible_step_text(dialog, "Load Labels")
    assert "external-labels" not in visible_text
    assert dialog.label_sources_label.text() == "Removed label source."


def test_load_labels_step_can_remove_auto_detected_label_carrier(qtbot):
    auto_label = "/tmp/source/labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [auto_label],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": auto_label,
                    "name": "A01T.mat",
                    "source_kind": "auto",
                    "source_location": "/tmp/source/labels",
                }
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    remove_buttons = [
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == "Remove"
    ]
    assert len(remove_buttons) == 1

    remove_buttons[0].click()
    qtbot.wait(0)

    result = dialog.get_result()
    assert result["choices"]["excluded_label_carriers"] == [auto_label]
    assert "A01T.mat" not in _visible_step_text(dialog, "Load Labels")
    _show_step(dialog, "Match Labels")
    assert "A01T.mat" not in _tree_text(dialog.label_carrier_tree)
    assert dialog.label_sources_label.text() == "Removed label file."


def test_load_labels_step_keeps_remove_for_loaded_source_after_rescan(qtbot):
    label_source = "/tmp/external-labels"
    label_file = "/tmp/external-labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_sources": [label_source],
            "label_carriers": [label_file],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_file,
                    "name": "A01T.mat",
                    "source_kind": "user_added",
                    "source_location": label_source,
                }
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    remove_buttons = [
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == "Remove"
    ]
    assert len(remove_buttons) == 2
    visible_text = _visible_step_text(dialog, "Load Labels")
    assert "Folder path" in visible_text
    assert "Will scan" not in visible_text

    remove_buttons[-1].click()
    qtbot.wait(0)

    result = dialog.get_result()
    assert result["label_sources"] == []
    assert result["label_sources_changed"] is True
    assert result["choices"]["excluded_label_carriers"] == [label_file]
    assert "A01T.mat" not in _visible_step_text(dialog, "Load Labels")
    _show_step(dialog, "Match Labels")
    assert "A01T.mat" not in _tree_text(dialog.label_carrier_tree)


def test_data_interpretation_preview_dialog_rejects_duplicate_label_sources(
    qtbot,
    monkeypatch,
):
    auto_label = "/tmp/source/labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [auto_label],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": auto_label,
                    "name": "A01T.mat",
                    "source_kind": "auto",
                    "source_location": "/tmp/source/labels",
                }
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    _show_step(dialog, "Load Labels")
    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog.QFileDialog.getOpenFileNames",
        lambda *_args, **_kwargs: ([auto_label], ""),
    )

    before_rows = len(
        dialog.label_source_rows_widget.findChildren(QFrame, "DataImportSourceRow")
    )
    dialog.add_label_file_btn.click()
    after_rows = len(
        dialog.label_source_rows_widget.findChildren(QFrame, "DataImportSourceRow")
    )

    assert before_rows == after_rows == 1
    assert "label_sources" not in dialog.get_result()
    assert "Already included" in dialog.label_sources_label.text()


def test_data_interpretation_preview_dialog_rejects_duplicate_label_folder(
    qtbot,
    monkeypatch,
):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": ["/tmp/source/labels/A01T.mat"],
        },
        preview={"summary": "Found 1 EEG file(s)."},
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    _show_step(dialog, "Load Labels")
    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: "/tmp/source/labels",
    )

    dialog.add_label_folder_btn.click()

    assert "label_sources" not in dialog.get_result()
    assert "Already included" in dialog.label_sources_label.text()


def test_data_interpretation_preview_dialog_product_flow_adds_label_folder_then_reviews(
    qtbot,
    monkeypatch,
):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_raw.fif"],
            "label_carriers": ["/tmp/labels/sub-01_task-mi_events.tsv"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "metadata_preview": [
                {
                    "file": "sub-01_task-mi_raw.fif",
                    "subject": {"value": "01", "decision": "safe"},
                    "session": {"value": "", "decision": "needs_confirmation"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": "1", "decision": "safe"},
                },
            ],
            "label_carrier_preview": [
                {
                    "path": "/tmp/labels/sub-01_task-mi_events.tsv",
                    "name": "sub-01_task-mi_events.tsv",
                    "format": "TSV",
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "trial",
                    "role": "class cue labels",
                    "source_kind": "user_added",
                    "source_location": "/tmp/labels",
                },
            ],
            "action_items": [
                {
                    "target_step": "Review Metadata",
                    "issue": "Confirm session metadata.",
                    "impact": "Session labels affect split and traceability.",
                    "next_action": "Review Metadata",
                    "severity": "needs_confirmation",
                }
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: "/tmp/external-labels",
    )

    assert _visible_group_titles_after_show(qtbot, dialog) == ["Choose EEG Data"]
    dialog.next_button.click()
    qtbot.wait(0)
    assert _visible_group_titles(dialog) == ["Load Labels"]

    dialog.add_label_folder_btn.click()
    assert "external-labels" in _group_text(dialog, "Load Labels")

    dialog.next_button.click()
    qtbot.wait(0)
    assert _visible_group_titles(dialog) == ["Review Metadata"]
    metadata_item = dialog.file_tree.topLevelItem(0)
    assert metadata_item is not None
    metadata_item.setText(2, "session-01")

    dialog.next_button.click()
    qtbot.wait(0)
    assert _visible_group_titles(dialog) == ["Match Labels"]
    assert dialog.label_carrier_tree.topLevelItemCount() == 1

    dialog.next_button.click()
    qtbot.wait(0)
    ok_button = dialog.apply_button
    assert _visible_group_titles(dialog) == ["Review and Import"]
    assert ok_button.isVisible()
    assert ok_button.text() == "Confirm and Apply"
    review_text = _group_text(dialog, "Review and Import")
    assert "Review Metadata" in review_text
    assert "Confirm session metadata." in review_text
    assert "Session labels affect split and traceability." in review_text
    assert "Impact" in review_text
    assert "Next" in review_text

    result = dialog.get_result()
    assert result["label_sources"] == ["/tmp/external-labels"]
    assert result["label_sources_changed"] is True
    assert result["choices"]["metadata_overrides"] == {
        "sub-01_task-mi_raw.fif": {"session": "session-01"}
    }


def test_data_interpretation_preview_dialog_skip_labels_marks_choice(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_raw.fif"],
        },
        preview={"summary": "Found 1 EEG file(s)."},
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)

    dialog.skip_labels_btn.click()

    result = dialog.get_result()
    assert result["choices"]["skip_labels"] is True
    assert "Skipped" in dialog.label_sources_label.text()


def test_attach_labels_buttons_use_clear_action_hierarchy(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_raw.fif"],
        },
        preview={"summary": "Found 1 EEG file(s)."},
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)

    assert dialog.add_label_file_btn.objectName() == "DataImportToolButton"
    assert dialog.add_label_folder_btn.objectName() == "DataImportToolButton"
    assert dialog.skip_labels_btn.objectName() == "DataImportTertiaryButton"
    assert "supervised workflows" in dialog.skip_labels_btn.toolTip()


def test_data_interpretation_preview_dialog_prefers_preview_counts(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [
                "/tmp/source/sub-01.fif",
                "/tmp/source/sub-02.fif",
                "/tmp/source/sub-03.fif",
            ],
            "label_carriers": ["/tmp/source/events.tsv"],
        },
        preview={
            "summary": "Found 2 EEG file(s).",
            "file_count": 2,
            "label_carrier_count": 0,
            "metadata_preview": [
                {
                    "file": "sub-01.fif",
                    "subject": {"value": "01", "decision": "safe"},
                    "session": {"value": None, "decision": "safe"},
                    "task": {"value": None, "decision": "safe"},
                    "run": {"value": None, "decision": "safe"},
                },
                {
                    "file": "sub-03.fif",
                    "subject": {"value": "03", "decision": "safe"},
                    "session": {"value": None, "decision": "safe"},
                    "task": {"value": None, "decision": "safe"},
                    "run": {"value": None, "decision": "safe"},
                },
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)

    assert dialog._file_count() == 2
    assert dialog._label_carrier_count() == 0
    assert dialog.file_tree.topLevelItemCount() == 2


def test_data_interpretation_preview_dialog_keeps_apply_actions_visible(qtbot):
    metadata_preview = [
        {
            "file": f"sub-{index:02d}_task-mi_raw.fif",
            "subject": {"value": f"{index:02d}", "decision": "safe"},
            "session": {"value": "01", "decision": "safe"},
            "task": {"value": "mi", "decision": "safe"},
            "run": {"value": "1", "decision": "safe"},
        }
        for index in range(1, 18)
    ]
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [
                f"/tmp/source/sub-{index:02d}_task-mi_raw.fif" for index in range(1, 18)
            ],
        },
        preview={
            "summary": "Found 17 EEG file(s).",
            "file_count": 17,
            "metadata_preview": metadata_preview,
            "event_roles": {
                f"event_{index}": "class label candidate" for index in range(1, 16)
            },
            "confirmation_items": [
                f"Confirm event_{index} role." for index in range(1, 16)
            ],
        },
        validation_decision={
            "decision": "needs_confirmation",
            "required_confirmations": [
                f"Confirm event_{index} role." for index in range(1, 16)
            ],
        },
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 520)
    dialog.show()
    qtbot.wait(0)

    scroll_areas = dialog.findChildren(QScrollArea)
    assert scroll_areas
    assert scroll_areas[0].widget() is not None
    ok_button = dialog.apply_button
    cancel_button = dialog.cancel_button
    assert cancel_button.isVisible()
    assert _widget_left(cancel_button, dialog) < _widget_left(
        dialog.back_button, dialog
    )
    assert cancel_button.geometry().bottom() <= dialog.contentsRect().bottom()


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
        assert tree.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert dialog.review_tree.alternatingRowColors()
    assert "alternate-background-color" in dialog.styleSheet()
    assert "#232323" in dialog.styleSheet().lower()
    assert "#ffffff" not in dialog.styleSheet().lower()
    assert "#000000" not in dialog.styleSheet().lower()

    label_field_selector = dialog.label_carrier_tree.itemWidget(
        dialog.label_carrier_tree.topLevelItem(0),
        2,
    )
    assert isinstance(label_field_selector, QComboBox)
    assert label_field_selector.currentText() == "Trial type"
    assert label_field_selector.currentData() == "trial_type"
    assert dialog.label_carrier_tree.columnWidth(0) >= 96


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

    for step_title, tree in (
        ("Review Metadata", dialog.file_tree),
        ("Match Labels", dialog.label_carrier_tree),
        ("Match Labels", dialog.event_tree),
        ("Review and Import", dialog.review_tree),
    ):
        _show_step(dialog, step_title)
        qtbot.wait(0)
        if tree is dialog.review_tree and not tree.isVisible():
            assert dialog.review_actions_panel.isVisible()
            continue
        dialog._fit_all_tree_columns_to_viewport()
        qtbot.wait(0)
        header = tree.header()
        assert header is not None
        viewport = tree.viewport()
        horizontal_scrollbar = tree.horizontalScrollBar()
        assert viewport is not None
        assert horizontal_scrollbar is not None
        assert abs(header.length() - viewport.width()) <= 2
        assert horizontal_scrollbar.maximum() == 0, step_title


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
    for column in (4, 5):
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
    _show_step(dialog, "Review and Import")
    qtbot.wait(0)

    review_tree = dialog.review_tree
    assert review_tree.topLevelItemCount() == 5
    viewport = review_tree.viewport()
    assert viewport is not None
    viewport_rect = viewport.rect()

    for row in range(review_tree.topLevelItemCount()):
        item = review_tree.topLevelItem(row)
        assert item is not None
        row_rect = review_tree.visualItemRect(item)
        if row_rect.isValid() and row_rect.top() < viewport_rect.bottom():
            assert row_rect.bottom() <= viewport_rect.bottom()
    assert (
        review_tree.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


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
            class_selector = dialog.event_tree.itemWidget(item, 2)
            assert isinstance(class_selector, QComboBox)
            assert class_selector.isEditable()
            class_selector.setCurrentText("Left hand")

    result = dialog.get_result()

    assert result["choices"]["metadata_overrides"] == {
        "sub-01_task-mi.fif": {"session": "session-01"}
    }
    assert result["choices"]["class_map"] == {
        "1": "left hand",
        "2": "right",
    }


def test_data_interpretation_preview_dialog_class_map_editor_has_bci_suggestions(
    qtbot,
):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={"class_map": {"769": "left", "770": "right"}},
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    left_item = dialog.event_tree.topLevelItem(0)
    assert left_item is not None
    selector = dialog.event_tree.itemWidget(left_item, 2)
    assert isinstance(selector, QComboBox)
    assert selector.isEditable()
    assert [selector.itemText(index) for index in range(selector.count())][:6] == [
        "Left",
        "Left hand",
        "Right hand",
        "Feet",
        "Tongue",
        "Rest",
    ]

    selector.setCurrentText("Feet")

    assert dialog.get_result()["choices"]["class_map"] == {
        "769": "feet",
        "770": "right",
    }


def test_data_interpretation_preview_dialog_class_map_preserves_custom_label(
    qtbot,
):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={"class_map": {"custom": "custom"}},
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    class_item = dialog.event_tree.topLevelItem(0)
    assert class_item is not None
    selector = dialog.event_tree.itemWidget(class_item, 2)
    assert isinstance(selector, QComboBox)

    selector.setCurrentText("MI_A")

    assert dialog.get_result()["choices"]["class_map"] == {
        "custom": "MI A",
    }


def test_data_interpretation_preview_dialog_keeps_unchanged_sidecar_class_label(
    qtbot,
):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={"class_map": {"left": "Left hand", "right": "Right hand"}},
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    assert dialog.get_result()["choices"] == {}


def test_data_interpretation_preview_dialog_event_rows_fit_after_class_map_preview(
    qtbot,
):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "label_carriers": ["/tmp/source/events.tsv"],
        },
        preview={
            "event_roles": {
                "label_carrier": "external label or event source",
                "onset": "time anchor",
                "duration": "event duration",
                "trial_type": "class label candidate",
            },
            "class_map": {"left": "left", "right": "right"},
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)
    dialog._fit_event_tree_height()
    qtbot.wait(0)

    assert dialog.event_tree.topLevelItemCount() == 2
    assert _partial_visible_tree_rows(dialog.event_tree) == []
    assert (
        dialog.event_tree.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


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

    assert "External label source" in visible_names
    assert "Trial type" in visible_names
    assert "label_carrier" not in visible_names

    for index in range(dialog.event_tree.topLevelItemCount()):
        item = dialog.event_tree.topLevelItem(index)
        if item is not None and item.text(0) == "External label source":
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
    assert "classlabel" in carrier_item.toolTip(2)
    assert "cue_onset" in carrier_item.toolTip(3)

    label_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 2)
    anchor_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 3)
    role_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 5)
    assert isinstance(label_selector, QComboBox)
    assert isinstance(anchor_selector, QComboBox)
    assert isinstance(role_selector, QComboBox)
    label_selector.setCurrentText("Classlabel")
    anchor_selector.setCurrentText("Cue onset")
    role_selector.setCurrentText("Class labels")

    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"] == {
        label_path: {
            "label_field": "classlabel",
            "anchor": "cue_onset",
            "time_model": "trial_order",
            "placement_method": "eeg_event",
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
    label_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 2)
    anchor_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 3)
    granularity_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 4)
    role_selector = dialog.label_carrier_tree.itemWidget(carrier_item, 5)
    assert isinstance(label_selector, QComboBox)
    assert isinstance(anchor_selector, QComboBox)
    assert isinstance(granularity_selector, QComboBox)
    assert isinstance(role_selector, QComboBox)

    anchor_selector.setCurrentText("Cue onset")
    role_selector.setCurrentText("Class labels")

    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"] == {
        label_path: {
            "label_field": "classlabel",
            "anchor": "cue_onset",
            "time_model": "trial_order",
            "placement_method": "eeg_event",
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
    target_selector = dialog._label_target_widgets[id(carrier_item)]
    assert [
        target_selector.itemText(index) for index in range(target_selector.count())
    ] == [
        "Choose EEG file",
        "sub-01 run-1",
        "sub-01 run-2",
    ]

    visible_selector = dialog._eeg_label_widgets[target_name]
    assert [
        visible_selector.itemText(index) for index in range(visible_selector.count())
    ] == [
        "Choose label file",
        "events.tsv",
    ]

    visible_selector.setCurrentIndex(visible_selector.findData(generic_events))
    assert target_selector.currentData() == target_name
    assert "1/2 EEG files paired" in dialog.pairing_status_label.text()
    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"] == {
        generic_events: {
            "target_file": target_name,
            "label_field": "trial_type",
            "anchor": "onset",
            "time_model": "seconds",
            "placement_method": "time_field",
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

    assert "Format support" in details
    assert "Check format" in details
    assert "BrainVision: needs review" not in details
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
    assert "Review any changed files" in details
    assert "Saved recipe choices were reapplied before validation" in details


def test_data_interpretation_preview_dialog_humanizes_recipe_trace(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "recipe_trace": [
                "scan:scan-1",
                "candidate:candidate-1",
                "metadata:subject",
                "metadata_override:session",
                "choices:metadata_overrides",
                "choices:event_roles",
                "choices:label_carriers",
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    details = _group_text(dialog, "Review and Import")
    review_tree_text = _tree_text(dialog.review_tree)

    assert "Source scan" in details
    assert "Interpretation candidate" in details
    assert "Metadata decision" in details
    assert "Metadata override" in details
    assert "Metadata choices" in details
    assert "Event use choices" in details
    assert "Label carrier choices" in details
    assert "Recipe records:" in details
    assert "Source scan" not in review_tree_text
    assert "scan:scan-1" not in details
    assert "candidate:candidate-1" not in details
    assert "metadata:subject" not in details
    assert "choices:metadata_overrides" not in details


def test_review_and_import_summarizes_bids_scope_and_epoch_next(qtbot):
    bids_payload = {
        "is_bids": True,
        "subjects": ["01"],
        "sessions": ["01"],
        "tasks": ["mi"],
        "runs": ["1"],
        "datatypes": ["eeg"],
        "eeg_file_count": 1,
        "events_files": ["/tmp/bids/sub-01_task-mi_run-1_events.tsv"],
        "channels_files": ["/tmp/bids/sub-01_task-mi_run-1_channels.tsv"],
        "participant_count": 1,
        "selected_scope": {
            "subjects": ["01"],
            "sessions": ["01"],
            "tasks": ["mi"],
            "runs": ["1"],
            "datatypes": ["eeg"],
            "eeg_file_count": 1,
            "events_files": ["/tmp/bids/sub-01_task-mi_run-1_events.tsv"],
            "channels_files": ["/tmp/bids/sub-01_task-mi_run-1_channels.tsv"],
        },
    }
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/bids",
            "source_kind": "bids",
            "bids": bids_payload,
        },
        preview={
            "source_selection": "1 selected file(s)",
            "bids": bids_payload,
            "label_carrier_preview": [
                {
                    "path": "/tmp/bids/sub-01_task-mi_run-1_events.tsv",
                    "name": "sub-01_task-mi_run-1_events.tsv",
                    "format": "BIDS events",
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "placement_method": "interval",
                }
            ],
            "class_map": {"left": "Left hand", "right": "Right hand"},
            "class_map_source": "label_carriers",
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)

    _show_step(dialog, "Review and Import")
    details = _group_text(dialog, "Review and Import")

    assert "Import summary" in details
    assert "Label source: BIDS events.tsv" in details
    assert "BIDS scope: sub-01" in details
    assert "Epoch next: Left hand, Right hand" in details
    assert "BIDS-like" not in details


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

    ok_button = dialog.apply_button
    assert ok_button.isEnabled()
    assert ok_button.text() == "Apply Remap"
    assert (
        dialog.decision_label.text()
        == "Choose the replacement label/event carrier before applying."
    )
    assert "replacement label/event carrier" in dialog.confirmation_label.text()
    assert "cannot be applied" not in dialog.confirmation_label.text()

    details = _tree_text(dialog.review_tree)
    assert "Recipe label file" in details
    assert "Choose file" in details
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

    ok_button = dialog.apply_button
    assert ok_button.isEnabled()
    assert ok_button.text() == "Apply Remap"
    assert dialog.decision_label.text() == (
        "Choose the replacement EEG file before applying."
    )
    assert "replacement EEG file" in dialog.confirmation_label.text()

    details = _tree_text(dialog.review_tree)
    assert "Recipe EEG file" in details
    assert "Choose file" in details
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

    ok_button = dialog.apply_button
    selector = next(iter(dialog._eeg_file_remap_widgets.values()))
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

    ok_button = dialog.apply_button
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


def _group_text(dialog, title: str) -> str:
    if title in getattr(dialog, "_step_titles", []):
        panel = dialog.step_stack.widget(dialog._step_titles.index(title))
        if panel is not None:
            return "\n".join(
                label.text()
                for label in panel.findChildren(QLabel)
                if label.text().strip()
            )
    for group in dialog.findChildren(QGroupBox):
        if group.title() != title:
            continue
        return "\n".join(
            label.text() for label in group.findChildren(QLabel) if label.text().strip()
        )
    return ""


def _visible_step_text(dialog, title: str) -> str:
    panel = dialog.step_stack.widget(dialog._step_titles.index(title))
    return "\n".join(
        label.text()
        for label in panel.findChildren(QLabel)
        if label.text().strip() and label.isVisibleTo(panel)
    )


def _click_button(dialog, text: str, *, event_code: str | None = None) -> None:
    panel = dialog.step_stack.currentWidget()
    fallback: QPushButton | None = None
    for button in panel.findChildren(QPushButton):
        if button.text() == text:
            if event_code is not None and button.property("event_code") != event_code:
                continue
            if button.isVisibleTo(panel):
                button.click()
                return
            fallback = button
    if fallback is not None:
        fallback.click()
        return
    raise AssertionError(f"No visible button with text {text!r}")


def _panel_titles(dialog) -> list[str]:
    return [
        label.text()
        for label in dialog.findChildren(QLabel)
        if label.objectName() == "DataImportPanelTitle" and label.text().strip()
    ]


def _visible_group_titles(dialog) -> list[str]:
    panel_titles = [
        label.text()
        for label in dialog.findChildren(QLabel)
        if (
            label.objectName() == "DataImportPanelTitle"
            and label.text().strip()
            and label.isVisible()
        )
    ]
    group_titles = [
        group.title()
        for group in dialog.findChildren(QGroupBox)
        if group.title() and group.isVisible()
    ]
    return [*panel_titles, *group_titles]


def _visible_group_titles_after_show(qtbot, dialog) -> list[str]:
    dialog.resize(960, 640)
    dialog.show()
    qtbot.wait(0)
    return _visible_group_titles(dialog)


def _show_step(dialog, title: str) -> None:
    index = dialog._step_titles.index(title)
    dialog._go_to_step(index)


def _widget_left(widget, dialog) -> int:
    return widget.mapTo(dialog, widget.rect().topLeft()).x()


def _partial_visible_tree_rows(tree) -> list[int]:
    viewport = tree.viewport()
    if viewport is None:
        return []
    viewport_bottom = viewport.rect().bottom()
    partial: list[int] = []
    for row in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(row)
        if item is None:
            continue
        rect = tree.visualItemRect(item)
        if rect.isValid() and rect.top() < viewport_bottom < rect.bottom():
            partial.append(row)
    return partial
