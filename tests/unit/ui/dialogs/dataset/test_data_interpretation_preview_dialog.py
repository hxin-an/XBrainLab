"""Tests for the Data Interpretation preview dialog."""

import inspect
import re
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
)

from XBrainLab.ui.components.presentation import ElidingComboBox
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
    _ConvertedLabelTableDialog,
)
from XBrainLab.ui.dialogs.dataset.review_import_step import ReviewImportStepMixin


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
    assert "Choose EEG Data  >  Load Labels  >  Review Metadata" in (
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
    advanced_header = dialog.match_advanced_toggle.parentWidget()
    assert advanced_header is not None
    assert advanced_header.objectName() == "DataImportPanelHeader"
    assert dialog.event_group.title() == ""
    event_group_text = "\n".join(
        label.text()
        for label in dialog.event_group.findChildren(QLabel)
        if label.text().strip()
    )
    assert "Labels inside EEG files" in event_group_text
    assert "Found 1 EEG file" in dialog.summary_label.text()
    assert "Review these choices" in dialog.decision_label.text()
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
    ] == ["Target step", "Issue", "Impact", "Next action"]
    assert dialog.confirmation_label.text() == ""
    assert "Review import choices" not in review_text
    assert dialog.review_tree.topLevelItemCount() == 0
    dialog.resize(1040, 760)
    dialog.show()
    _show_step(dialog, "Review and Import")
    qtbot.wait(0)
    dialog.import_report_toggle.click()
    qtbot.wait(0)
    assert not dialog.review_tree.isVisibleTo(dialog)
    assert dialog.review_report_empty_label.isVisibleTo(dialog)
    assert (
        dialog.review_report_empty_label.text()
        == "No review items. This import is ready to apply."
    )
    assert "Confirm session metadata." not in review_text
    assert "After import" not in review_text
    assert "Training uses this recipe trace." not in review_text
    assert not dialog.findChildren(QPlainTextEdit)
    assert dialog.apply_button.text() == "Confirm and Import"
    assert dialog.get_result() == {
        "confirmed": True,
        "save_recipe": False,
        "choices": {"label_carrier": "embedded_events"},
    }


def test_review_and_import_renders_structured_resource_preflight(qtbot):
    resource_preflight = {
        "risk_level": "safe",
        "requires_confirmation": False,
        "issues": [],
        "warnings": [],
        "unknowns": [],
        "message": "Resource check: Safe",
        "required_memory_bytes": 2 * 1024**3,
        "available_memory_bytes": 8 * 1024**3,
        "total_memory_bytes": 16 * 1024**3,
        "used_memory_bytes": 8 * 1024**3,
    }
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "selected_eeg_files": ["/tmp/source/A01T.gdf"],
            "metadata_preview": [
                {
                    "file": "A01T.gdf",
                    "subject": {"value": "A01", "decision": "safe"},
                    "session": {"value": "", "decision": "safe"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": "", "decision": "safe"},
                },
            ],
            "label_carrier_preview": [
                {
                    "path": "/tmp/source/A01T_events.tsv",
                    "name": "A01T_events.tsv",
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                },
            ],
            "resource_preflight": resource_preflight,
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)

    _show_step(dialog, "Review and Import")
    review_text = _visible_step_text(dialog, "Review and Import")

    assert "Resource check" in review_text
    assert "Safe" in review_text
    assert "Estimated RAM 2.0 GB / Available RAM 8.0 GB" in review_text


def test_review_resource_check_replaces_status_from_changed_preview_result(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "selected_eeg_files": ["/tmp/source/A01T.gdf"],
            "metadata_preview": [],
            "resource_preflight": {
                "risk_level": "safe",
                "required_memory_bytes": 1 * 1024**3,
                "available_memory_bytes": 8 * 1024**3,
                "message": "Resource check: Safe",
            },
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    _show_step(dialog, "Review and Import")
    assert "Safe" in _visible_step_text(dialog, "Review and Import")

    changed_command_result = {
        "preview": {
            **dialog.preview,
            "resource_preflight": {
                "risk_level": "blocking",
                "required_memory_bytes": 12 * 1024**3,
                "available_memory_bytes": 8 * 1024**3,
                "message": "Dataset is too large to load safely.",
            },
        }
    }
    dialog.preview = changed_command_result["preview"]
    dialog._refresh_review_import_summary()
    dialog._sync_apply_state()
    qtbot.wait(0)

    review_text = _visible_step_text(dialog, "Review and Import")
    assert "Blocking" in review_text
    assert "Estimated RAM 12.0 GB / Available RAM 8.0 GB" in review_text
    assert "Estimated RAM 1.0 GB" not in review_text
    assert dialog.apply_button.isEnabled() is False
    assert dialog.can_submit_for_backend_review() is False
    assert dialog.get_result()["confirmed"] is False
    go_to_data = next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == "Go to EEG Data" and button.isVisibleTo(dialog)
    )
    go_to_data.click()
    assert dialog.step_stack.currentIndex() == dialog._step_titles.index(
        "Choose EEG Data"
    )


def test_review_import_widget_does_not_recompute_resource_preflight():
    source = inspect.getsource(ReviewImportStepMixin)

    assert "ResourceChecker" not in source
    assert "check_import_resource_preflight" not in source


def test_review_resource_check_uses_contract_risk_language(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={},
        preview={},
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)

    expected = {
        "safe": ("Safe", ""),
        "warning": ("Warning", ""),
        "blocking": ("Blocking", "Go to EEG Data"),
        "unknown": ("Unknown", ""),
    }
    for risk_level, (status, action) in expected.items():
        dialog.preview = {
            "resource_preflight": {
                "risk_level": risk_level,
                "message": f"Backend resource status: {risk_level}",
            }
        }

        row = dialog._resource_check_status_row()

        assert row["status"] == status
        assert row["summary"] == f"Backend resource status: {risk_level}"
        assert row["action"] == action


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
                    "target_file": "sub-01_task-mi_raw.fif",
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
    assert ok_button.text() == "Confirm and Import"
    assert not dialog.confirmation_label.isVisible()
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
    vertical_scrollbar = dialog.scroll_area.verticalScrollBar()
    assert vertical_scrollbar is not None
    assert vertical_scrollbar.maximum() == 0
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
    if scrollbar.maximum() == 0:
        assert (
            dialog.scroll_area.verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scrollbar.setValue(20)
        dialog._sync_scroll_policy()
        assert scrollbar.value() == 0
    else:
        assert (
            dialog.scroll_area.verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )


def test_load_labels_many_file_rows_use_compact_source_context(qtbot):
    label_files = [f"/tmp/source/labels/A{index:02d}T.mat" for index in range(1, 9)]
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": label_files,
        },
        preview={
            "summary": "Found 1 EEG file(s) and 8 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_file,
                    "name": Path(label_file).name,
                    "source_kind": "auto",
                    "source_location": "/tmp/source/labels",
                }
                for label_file in label_files
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    rows = _visible_source_rows(dialog)
    details = [row.findChild(QLabel, "DataImportSourceDetail") for row in rows]

    assert len(rows) == 8
    assert all(row.property("dense") is True for row in rows)
    assert all(detail is not None for detail in details)
    assert all(detail.wordWrap() is False for detail in details if detail is not None)
    assert all(
        detail.text() == "Detected nearby · labels"
        for detail in details
        if detail is not None
    )
    assert "/tmp/source/labels" not in _visible_step_text(dialog, "Load Labels")
    assert all(
        detail.toolTip() == "Found in folder: /tmp/source/labels"
        for detail in details
        if detail is not None
    )


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
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    assert dialog.label_match_mode_combo.currentData() == "filename_stem"
    assert not dialog.label_match_mode_combo.isVisibleTo(dialog)
    visible_text = _visible_step_text(dialog, "Match Labels")
    assert "Pair by" not in visible_text
    assert "Same base name" not in visible_text
    assert "2/2 EEG files paired" in dialog.pairing_status_label.text()
    assert "2/2 paired" in dialog.rule_status_label.text()
    pairing_rows = [
        row
        for row in dialog.label_pairing_rows_widget.findChildren(
            QFrame,
            "DataImportPairingRow",
        )
        if row.findChildren(QComboBox)
    ]
    assert pairing_rows
    first_row = pairing_rows[0]
    eeg_label = next(
        label for label in first_row.findChildren(QLabel) if label.text() == "A01T.gdf"
    )
    label_selector = first_row.findChildren(QComboBox)[0]
    assert _widget_left(eeg_label, dialog) < _widget_left(label_selector, dialog)

    dialog.rule_label_field_combo.setCurrentIndex(
        dialog.rule_label_field_combo.findData("target")
    )
    dialog.rule_alignment_combo.setCurrentIndex(
        dialog.rule_alignment_combo.findData("cue_onset")
    )
    dialog.rule_use_as_combo.setCurrentIndex(
        dialog.rule_use_as_combo.findData("class cue labels")
    )
    qtbot.wait(0)

    assert dialog.next_button.isEnabled() is True
    assert dialog.next_button.text() == "Refresh label preview"

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


def test_match_labels_pairing_header_has_vertical_text_breathing_room(qtbot):
    label_path = "/tmp/source/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [label_path],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "selected_eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "A01T.mat",
                    "format": "MAT",
                    "selected_label_field": "classlabel",
                    "selected_anchor": "trial order",
                    "time_model": "trial_order",
                    "granularity": "trial",
                    "role": "external labels",
                }
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 860)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    header = dialog.findChild(QFrame, "DataImportPairingHeader")
    assert header is not None
    labels = header.findChildren(QLabel, "DataImportPairingHeaderLabel")
    assert [label.text() for label in labels] == [
        "EEG file",
        "Label file",
        "Status",
    ]
    assert all(label.height() >= label.fontMetrics().height() + 4 for label in labels)
    assert header.height() >= max(label.height() for label in labels) + 4
    visible_header_labels = [
        label
        for label in dialog.findChildren(QLabel, "DataImportPairingHeaderLabel")
        if label.isVisible()
    ]
    assert visible_header_labels
    assert all(
        label.height() >= label.fontMetrics().height() + 4
        for label in visible_header_labels
    )


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
    assert dialog.get_result()["choices"]["label_carrier"] == "embedded_events"


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

    internal_index = dialog.label_source_mode_combo.findData("internal_events")
    dialog.label_source_mode_combo.setCurrentIndex(internal_index)
    dialog.label_source_mode_combo.activated.emit(internal_index)
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

    internal_index = dialog.label_source_mode_combo.findData("internal_events")
    dialog.label_source_mode_combo.setCurrentIndex(internal_index)
    dialog.label_source_mode_combo.activated.emit(internal_index)
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

    visible_text = _visible_step_text(dialog, "Match Labels")
    assert "Suggested training labels" in visible_text
    assert "Source evidence" not in visible_text
    assert "Use this when class labels are stored as EEG events." not in visible_text
    assert "Other EEG events" in visible_text
    assert "can be added as training labels" in visible_text
    assert "Selection preview: train on 769, 770" in visible_text
    assert "other events: 768, 1023" in visible_text
    assert "Event names need review" in visible_text
    assert "769" in visible_text
    assert "770" in visible_text
    assert "Training class" in visible_text
    assert "Repeats once per trial" not in visible_text
    assert "288 events · 3/3 files" in visible_text
    assert "6 events · 3/3 files" in visible_text
    assert "768" in visible_text
    assert "EEG event only" in visible_text
    assert "Not used for training" not in visible_text
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


def test_class_name_suggestions_do_not_mix_in_non_class_event_uses() -> None:
    choices = dict(DataInterpretationPreviewDialog._class_label_choices(""))

    assert "Artifact" not in choices
    assert "Ignored" not in choices


def test_match_labels_advanced_details_fit_at_752_and_explain_evidence(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "internal_event_preview": {
                "candidate_label_events": [
                    {
                        "event_code": "769",
                        "event_count": 48,
                    },
                ],
                "not_used_events": [
                    {
                        "event_code": "768",
                        "event_count": 48,
                    },
                ],
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(752, 720)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    first_layer_text = _visible_step_text(dialog, "Match Labels")
    assert "Use as" in first_layer_text
    assert "Action" in first_layer_text
    assert (
        re.search(
            r"\b(?:role|evidence)\b",
            first_layer_text,
            re.IGNORECASE,
        )
        is None
    )
    assert dialog.match_advanced_toggle.isVisibleTo(dialog)
    assert (
        dialog.match_advanced_toggle.mapTo(
            dialog,
            dialog.match_advanced_toggle.rect().topRight(),
        ).x()
        <= dialog.contentsRect().right()
    )

    dialog.match_advanced_toggle.click()
    qtbot.wait(0)

    tables = [
        dialog.findChild(QFrame, "DataImportInternalLabelsTable"),
        dialog.findChild(QFrame, "DataImportInternalOtherEventsTable"),
    ]
    assert all(table is not None for table in tables)
    expected_headers = [
        [
            "Event",
            "Use as",
            "Occurrences",
            "Class name",
            "Action",
            "Source evidence",
        ],
        [
            "Event",
            "Use as",
            "Occurrences",
            "Action",
            "Source evidence",
        ],
    ]
    viewport = dialog.scroll_area.viewport()
    assert viewport is not None
    for table, headers in zip(tables, expected_headers, strict=True):
        assert table is not None
        visible_headers = [
            label.text()
            for label in table.findChildren(QLabel, "DataImportPairingHeaderLabel")
            if label.isVisibleTo(table)
        ]
        assert visible_headers == headers
        assert table.mapTo(viewport, table.rect().topLeft()).x() >= (
            viewport.contentsRect().left()
        )
        assert (
            table.mapTo(viewport, table.rect().topRight()).x()
            <= viewport.contentsRect().right()
        )

    other_table = tables[1]
    assert other_table is not None
    other_text = "\n".join(
        label.text()
        for label in other_table.findChildren(QLabel)
        if label.text().strip() and label.isVisibleTo(other_table)
    )
    assert "No source evidence was provided by the import preview." in other_text
    assert "Suggested by event pattern" not in other_text


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

    _click_button(dialog, "Exclude from training", event_code="769")
    qtbot.wait(0)

    visible_text = _visible_step_text(dialog, "Match Labels")
    assert "Changed by user" not in visible_text
    assert [item[1] for item in dialog._class_map_items] == ["770"]
    assert dialog.get_result()["choices"]["event_roles"] == {"769": "not a label"}

    _click_button(dialog, "Use for training", event_code="769")
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

    target_checks = {
        check.property("event_code"): check
        for check in dialog.findChildren(QCheckBox)
        if check.objectName() == "DataImportTargetEventCheckbox"
    }
    assert "checkmark.svg" in dialog.styleSheet()
    for code, check in target_checks.items():
        check.setChecked(code == "768")
    qtbot.wait(0)

    visible_text = _visible_step_text(dialog, "Match Labels")
    assert "EEG event order" in visible_text
    assert "Target EEG events" in visible_text
    assert "Target" in visible_text
    assert "Event" in visible_text
    assert "Source evidence" not in visible_text
    assert "Use" in visible_text
    assert "768" in visible_text
    assert "288 selected EEG events" in visible_text
    assert "282 label rows" in visible_text
    assert "6 selected EEG events have no label" in visible_text
    assert "Uncheck extra target events or choose another label field" in visible_text
    assert "6 EEG events excluded" in visible_text
    assert "Label file needs conversion" not in visible_text
    assert visible_text.count("Check:") == 1
    assert not dialog.match_check_card.isVisibleTo(dialog.step_stack.currentWidget())

    result = dialog.get_result()

    assert result["choices"]["label_carrier_choices"][label_path]["anchor"] == "768"
    assert result["choices"]["label_carrier_choices"][label_path][
        "target_event_codes"
    ] == ["768"]
    assert (
        result["choices"]["label_carrier_choices"][label_path]["placement_method"]
        == "eeg_event"
    )


def test_match_labels_eeg_event_order_allows_multiple_target_events(qtbot):
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
                    "selected_target_event_codes": [],
                    "label_row_count": 4,
                    "label_value_counts": {"1": 2, "2": 2},
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
                        "event_count": 2,
                        "evidence": "Balanced candidate label event",
                    },
                    {
                        "event_code": "770",
                        "use_as": "Class label",
                        "event_count": 2,
                        "evidence": "Balanced candidate label event",
                    },
                ],
                "not_used_events": [
                    {
                        "event_code": "768",
                        "use_as": "Trial timing",
                        "event_count": 4,
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

    target_checks = {
        check.property("event_code"): check
        for check in dialog.findChildren(QCheckBox)
        if check.objectName() == "DataImportTargetEventCheckbox"
    }
    assert set(target_checks) >= {"768", "769", "770"}

    target_checks["768"].setChecked(False)
    target_checks["769"].setChecked(True)
    target_checks["770"].setChecked(True)
    qtbot.wait(0)

    visible_text = _visible_step_text(dialog, "Match Labels")
    assert "4 selected EEG events" in visible_text
    assert "4 label rows" in visible_text

    choices = dialog.get_result()["choices"]["label_carrier_choices"][label_path]
    assert choices["target_event_codes"] == ["769", "770"]
    assert choices["anchor"] == "769"
    assert choices["placement_method"] == "eeg_event"


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
                    "time_label_preview": [
                        {"time": "0", "label": "left"},
                        {"time": "5.5", "label": "right"},
                        {"time": "11", "label": "left"},
                    ],
                    "placement_reviews": {
                        "time_field": {
                            "method": "time_field",
                            "status": "ready",
                            "time_field": "onset",
                            "label_rows": 12,
                            "numeric_rows": 12,
                            "time_min": 0,
                            "time_max": 11,
                            "time_model": "seconds",
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
                            "label_code_count": 2,
                            "matched_code_count": 1,
                            "matched_codes": ["11"],
                            "missing_codes": ["13"],
                            "code_mappings": [
                                {
                                    "event_code": "11",
                                    "label_values": ["left"],
                                    "label_rows": 6,
                                    "eeg_event_count": 6,
                                    "status": "ready",
                                    "review": "Ready.",
                                },
                                {
                                    "event_code": "13",
                                    "label_values": ["right"],
                                    "label_rows": 6,
                                    "eeg_event_count": None,
                                    "status": "needs_review",
                                    "review": "Not found in EEG events.",
                                },
                            ],
                            "unlabeled_eeg_events": [
                                {
                                    "event_code": "768",
                                    "use_as": "Trial timing",
                                    "event_count": 12,
                                }
                            ],
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
        "eeg_event": ("Target EEG events", "Time column"),
        "time_field": ("Time column", "Target EEG events"),
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
        if method == "time_field":
            assert (
                "If rows simply follow EEG events, use EEG event order" in visible_text
            )
            assert "Time numbers mean" in visible_text
            time_model_values = [
                dialog.rule_time_model_combo.itemData(index)
                for index in range(dialog.rule_time_model_combo.count())
            ]
            assert "trial_order" not in time_model_values
            assert "Preview rows" in visible_text
            assert "Time in EEG" in visible_text
            assert "Label value" in visible_text
            assert "Showing first 3 rows from trial_type using onset" in visible_text
            assert dialog.time_field_preview_row_labels[0][0].text() == "0"
            assert dialog.time_field_preview_row_labels[0][1].text() == "left"
            assert dialog.time_field_preview_row_labels[1][0].text() == "5.5"
            assert dialog.time_field_preview_row_labels[1][1].text() == "right"
            assert "Check" in visible_text
            assert "12/12 rows have usable time values" in visible_text
            assert "Range: 0 to 11 seconds" in visible_text
            assert "The EEG epoch window will be set later" in visible_text
        if method == "event_code":
            assert "Code mapping review" in visible_text
            assert "Label code" in visible_text
            assert "Label value" in visible_text
            assert "11" in visible_text
            assert "left" in visible_text
            assert "13" in visible_text
            assert "Not found in EEG events" in visible_text
            assert "EEG events not labeled" in visible_text
            assert "Trial timing" in visible_text
            assert "1/2 label event codes were found" in (
                dialog.placement_status_label.text()
            )

    target_checks = [
        checkbox
        for checkbox in dialog.findChildren(QCheckBox)
        if checkbox.objectName() == "DataImportTargetEventCheckbox"
    ]
    assert target_checks


def test_match_labels_label_time_records_time_base_choice(qtbot):
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
                    "label_candidates": ["trial_type"],
                    "anchor_candidates": ["onset", "sample"],
                    "time_field_candidates": ["onset", "sample"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "label_row_count": 2,
                    "time_model": "seconds",
                    "granularity": "event",
                    "placement_method": "time_field",
                    "role": "external labels",
                    "placement_reviews": {
                        "time_field": {
                            "method": "time_field",
                            "status": "ready",
                            "time_field": "onset",
                            "label_rows": 2,
                            "numeric_rows": 2,
                            "time_min": 0,
                            "time_max": 1,
                            "time_model": "seconds",
                            "summary": "2/2 numeric rows, range 0 to 1.",
                        },
                    },
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    assert dialog.rule_time_model_combo.currentData() == "seconds"
    dialog.rule_time_model_combo.setCurrentIndex(
        dialog.rule_time_model_combo.findData("sample_index")
    )
    qtbot.wait(0)

    choices = dialog.get_result()["choices"]["label_carrier_choices"][label_path]
    assert choices["time_model"] == "sample_index"
    assert choices["placement_method"] == "time_field"
    assert choices["anchor"] == "onset"


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
        if button.text() == "Remove all from this folder"
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


def test_load_labels_removing_only_file_from_loaded_folder_removes_folder_source(qtbot):
    label_folder = "/tmp/external-labels"
    label_file = f"{label_folder}/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_sources": [label_folder],
            "label_carriers": [label_file],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_file,
                    "name": "A01T.mat",
                    "format": "MAT",
                    "source_kind": "user_added",
                    "source_location": label_folder,
                }
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    assert _source_scope_texts(dialog) == [f"Label source: {label_folder}"]
    assert _source_row_titles(dialog) == ["A01T.mat"]

    _click_source_row_button(dialog, "A01T.mat", "Remove file")
    qtbot.wait(0)

    assert _source_scope_texts(dialog) == []
    assert _source_row_titles(dialog) == []
    result = dialog.get_result()
    assert result["label_sources"] == []
    assert result["label_sources_changed"] is True
    assert "A01T.mat" not in _visible_step_text(dialog, "Load Labels")


def test_load_labels_removing_one_file_keeps_multi_file_folder_source(qtbot):
    label_folder = "/tmp/external-labels"
    first_label = f"{label_folder}/A01T.mat"
    second_label = f"{label_folder}/A02T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf", "/tmp/source/A02T.gdf"],
            "label_sources": [label_folder],
            "label_carriers": [first_label, second_label],
        },
        preview={
            "summary": "Found 2 EEG file(s) and 2 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": first_label,
                    "name": "A01T.mat",
                    "format": "MAT",
                    "source_kind": "user_added",
                    "source_location": label_folder,
                },
                {
                    "path": second_label,
                    "name": "A02T.mat",
                    "format": "MAT",
                    "source_kind": "user_added",
                    "source_location": label_folder,
                },
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    _click_source_row_button(dialog, "A01T.mat", "Remove file")
    qtbot.wait(0)

    assert [row.get("name") for row in dialog._label_carrier_preview_rows()] == [
        "A02T.mat"
    ]
    result = dialog.get_result()
    assert "label_sources_changed" not in result
    assert result["choices"]["excluded_label_carriers"] == [first_label]


def test_load_labels_step_keeps_custom_fallback_out_of_first_layer(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={"summary": "Found 1 EEG file(s)."},
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    visible_text = _visible_step_text(dialog, "Load Labels")
    assert "Load label file" not in visible_text
    assert "Custom label format?" not in visible_text
    assert "XBrainLab label table" not in visible_text
    assert "Required: label" not in visible_text
    assert "event_code" not in visible_text
    assert "Python file" not in visible_text
    assert "custom parser" not in visible_text


def test_converted_label_table_dialog_shows_required_format(qtbot):
    dialog = _ConvertedLabelTableDialog(parent=None)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(0)

    visible_text = "\n".join(
        label.text()
        for label in dialog.findChildren(QLabel)
        if label.text().strip() and label.isVisibleTo(dialog)
    )
    assert "XBrainLab label table" in visible_text
    assert "which values are labels" in visible_text
    assert "One row per label" in visible_text
    assert "Column named label" in visible_text
    assert "One placement column" in visible_text
    assert "Choose the placement that matches your file" in visible_text
    assert "event_code,label" in visible_text
    assert "onset_seconds,label" in visible_text
    assert "sample,label" in visible_text
    assert "onset_seconds,duration_seconds,label" in visible_text
    assert "Example: labels follow EEG event codes" in visible_text
    assert "769,left_hand" in visible_text
    assert "Example: labels have timestamps" in visible_text
    assert "12.50,left_hand" in visible_text
    button_texts = [button.text() for button in dialog.findChildren(QPushButton)]
    assert "Close" in button_texts
    assert "Choose CSV/TSV table" not in button_texts


def test_match_labels_shows_conversion_fallback_when_label_field_is_missing(
    qtbot,
    monkeypatch,
):
    label_path = "/tmp/labels/custom_labels.mat"
    opened = {"value": False}
    monkeypatch.setattr(
        DataInterpretationPreviewDialog,
        "_show_converted_label_table_format",
        lambda _dialog: opened.__setitem__("value", True),
    )
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
                    "placement_method": "eeg_event",
                }
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    visible_text = _visible_step_text(dialog, "Match Labels")
    assert "label format needs conversion" in visible_text
    assert "ready to place on EEG" not in visible_text
    assert "Needs setup" in visible_text
    assert "Matched" not in visible_text
    assert "XBrainLab cannot match this label file yet" in visible_text
    assert "cannot tell which column or variable contains the labels" in visible_text
    current_widget = dialog.step_stack.currentWidget()
    assert current_widget is not None
    visible_buttons = [
        button.text()
        for button in current_widget.findChildren(QPushButton)
        if button.isVisibleTo(current_widget)
    ]
    assert "View required format" in visible_buttons
    assert "Go to Load Labels" in visible_buttons
    assert dialog.next_button.isEnabled() is False
    assert "Resolve label matching" in dialog.next_button.toolTip()
    assert "One row per label" not in visible_text
    assert "One placement column" not in visible_text
    assert "event_code,label" not in visible_text
    assert "769,left_hand" not in visible_text
    assert "Label values and placement" not in visible_text
    assert "Read labels from" not in visible_text
    assert "Place labels by" not in visible_text
    assert "Check" not in visible_text
    assert "converted CSV/TSV" not in visible_text

    _click_button(dialog, "View required format")
    qtbot.wait(0)

    assert opened["value"] is True

    _click_button(dialog, "Go to Load Labels")
    qtbot.wait(0)

    assert dialog._step_titles[dialog.step_stack.currentIndex()] == "Load Labels"


def test_match_labels_keeps_controls_visible_when_target_events_need_selection(
    qtbot,
):
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
                    "selected_target_event_codes": [],
                    "label_row_count": 4,
                    "label_value_counts": {"1": 2, "2": 2},
                    "value_decisions": {
                        "1": {"role": "", "use_as": "", "class_name": ""},
                        "2": {"role": "", "use_as": "", "class_name": ""},
                    },
                    "placement_method": "eeg_event",
                    "time_model": "trial_order",
                    "granularity": "trial",
                    "role": "external labels",
                    "placement_reviews": {
                        "eeg_event": {
                            "method": "eeg_event",
                            "status": "blocked",
                            "decision_code": "sequence_target_events_required",
                            "summary": "Select one or more target EEG events.",
                        }
                    },
                    "placement_review": {
                        "method": "eeg_event",
                        "status": "blocked",
                        "decision_code": "sequence_target_events_required",
                        "summary": "Select one or more target EEG events.",
                    },
                }
            ],
            "internal_event_preview": {
                "candidate_label_events": [
                    {
                        "event_code": "769",
                        "use_as": "Class label",
                        "event_count": 2,
                    },
                    {
                        "event_code": "770",
                        "use_as": "Class label",
                        "event_count": 2,
                    },
                ]
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)

    current = dialog.step_stack.currentWidget()
    assert current is not None
    assert dialog.label_table_fallback_card.isVisibleTo(current) is False
    assert dialog.label_values_card.isVisibleTo(current) is True
    assert dialog.placement_card.isVisibleTo(current) is True
    assert dialog.event_value_editor is not None
    assert dialog.event_value_editor.isVisibleTo(current) is True
    visible_text = _visible_step_text(dialog, "Match Labels")
    assert "Event value decisions" in visible_text
    assert "Target EEG events" in visible_text


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
        if button.text() == "Remove file"
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


def test_load_labels_step_can_restore_removed_auto_detected_label_carrier(
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
                    "selected_label_field": "classlabel",
                    "selected_anchor": "768",
                    "placement_method": "eeg_event_order",
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
        if button.text() == "Remove file"
    ]
    assert len(remove_buttons) == 1
    remove_buttons[0].click()
    qtbot.wait(0)
    assert "A01T.mat" not in _visible_step_text(dialog, "Load Labels")

    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog.QFileDialog.getOpenFileNames",
        lambda *_args, **_kwargs: ([auto_label], ""),
    )
    dialog.add_label_file_btn.click()
    qtbot.waitUntil(
        lambda: "A01T.mat" in _visible_step_text(dialog, "Load Labels"),
        timeout=1000,
    )

    assert "excluded_label_carriers" not in dialog.get_result()["choices"]
    visible_lines = _visible_step_text(dialog, "Load Labels").splitlines()
    assert visible_lines.count("A01T.mat") == 1
    _show_step(dialog, "Match Labels")
    assert "A01T.mat" in _tree_text(dialog.label_carrier_tree)


def test_load_labels_step_hides_file_source_when_carrier_row_exists(qtbot):
    label_file = "/tmp/external-labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_sources": [label_file],
            "label_carriers": [label_file],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_file,
                    "name": "A01T.mat",
                    "source_kind": "user_added",
                    "source_location": label_file,
                }
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    visible_lines = _visible_step_text(dialog, "Load Labels").splitlines()
    assert visible_lines.count("A01T.mat") == 1
    assert not any(line.startswith("File path:") for line in visible_lines)


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

    assert _source_row_button_texts(dialog) == ["Remove file"]
    assert _source_scope_button_texts(dialog) == ["Remove all from this folder"]
    visible_text = _visible_step_text(dialog, "Load Labels")
    assert "Label source: /tmp/external-labels" in visible_text
    assert "Will scan" not in visible_text

    _click_source_scope_button(dialog, "Label source: /tmp/external-labels")
    qtbot.wait(0)

    result = dialog.get_result()
    assert result["label_sources"] == []
    assert result["label_sources_changed"] is True
    assert result["choices"]["excluded_label_carriers"] == [label_file]
    assert "A01T.mat" not in _visible_step_text(dialog, "Load Labels")
    _show_step(dialog, "Match Labels")
    assert "A01T.mat" not in _tree_text(dialog.label_carrier_tree)


def test_load_labels_step_removes_one_file_from_loaded_folder(qtbot):
    label_source = "/tmp/external-labels"
    label_files = [
        f"{label_source}/A01T.mat",
        f"{label_source}/A02T.mat",
        f"{label_source}/A03T.mat",
    ]
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [
                "/tmp/source/A01T.gdf",
                "/tmp/source/A02T.gdf",
                "/tmp/source/A03T.gdf",
            ],
            "label_sources": [label_source],
            "label_carriers": label_files,
        },
        preview={
            "summary": "Found 3 EEG file(s) and 3 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_file,
                    "name": label_file.rsplit("/", 1)[-1],
                    "source_kind": "user_added",
                    "source_location": label_source,
                }
                for label_file in label_files
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    assert _source_row_button_texts(dialog) == [
        "Remove file",
        "Remove file",
        "Remove file",
    ]
    assert _source_scope_button_texts(dialog) == ["Remove all from this folder"]

    _click_source_row_button(dialog, "A02T.mat", "Remove file")
    qtbot.waitUntil(
        lambda: "A01T.mat" in _visible_step_text(dialog, "Load Labels"),
        timeout=1000,
    )

    result = dialog.get_result()
    assert result["choices"]["excluded_label_carriers"] == [label_files[1]]
    visible_text = _visible_step_text(dialog, "Load Labels")
    assert "A01T.mat" in visible_text
    assert "A02T.mat" not in visible_text
    assert "A03T.mat" in visible_text
    assert "Label source: /tmp/external-labels" in visible_text
    _show_step(dialog, "Match Labels")
    tree_text = _tree_text(dialog.label_carrier_tree)
    assert "A01T.mat" in tree_text
    assert "A02T.mat" not in tree_text
    assert "A03T.mat" in tree_text


def test_load_labels_step_names_loaded_folder_as_scope_not_basename(qtbot):
    label_source = "/tmp/source/label"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_sources": [label_source],
        },
        preview={"summary": "Found 1 EEG file(s)."},
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    assert _source_row_titles(dialog) == []
    assert _source_scope_texts(dialog) == ["Label source: /tmp/source/label"]
    visible_lines = _visible_step_text(dialog, "Load Labels").splitlines()
    assert "label" not in visible_lines
    assert "Loaded folder" not in visible_lines
    assert "Label source: /tmp/source/label" in visible_lines


def test_load_labels_step_readds_removed_folder_carrier_as_single_file_source(
    qtbot,
    monkeypatch,
):
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

    assert _source_row_button_texts(dialog) == ["Remove file"]
    assert _source_scope_button_texts(dialog) == ["Remove all from this folder"]
    _click_source_row_button(dialog, "A01T.mat", "Remove file")
    qtbot.wait(0)
    assert "A01T.mat" not in _visible_step_text(dialog, "Load Labels")

    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog.QFileDialog.getOpenFileNames",
        lambda *_args, **_kwargs: ([label_file], ""),
    )
    dialog.add_label_file_btn.click()
    qtbot.waitUntil(
        lambda: "A01T.mat" in _visible_step_text(dialog, "Load Labels"),
        timeout=1000,
    )

    result = dialog.get_result()
    assert result["label_sources"] == [label_file]
    assert result["label_sources_changed"] is True
    assert "excluded_label_carriers" not in result["choices"]
    visible_lines = _visible_step_text(dialog, "Load Labels").splitlines()
    assert visible_lines.count("A01T.mat") == 1
    assert "Label source: /tmp/external-labels" not in visible_lines
    _show_step(dialog, "Match Labels")
    assert "A01T.mat" in _tree_text(dialog.label_carrier_tree)


def test_load_labels_step_replaces_stale_button_after_reload(qtbot, monkeypatch):
    label_file = "/tmp/source/labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [label_file],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": label_file,
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

    _click_source_row_button(dialog, "A01T.mat", "Remove file")
    qtbot.wait(0)
    assert "A01T.mat" not in _visible_step_text(dialog, "Load Labels")

    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog.QFileDialog.getOpenFileNames",
        lambda *_args, **_kwargs: ([label_file], ""),
    )
    dialog.add_label_file_btn.click()
    qtbot.waitUntil(
        lambda: "A01T.mat" in _visible_step_text(dialog, "Load Labels"),
        timeout=1000,
    )

    remove_buttons = [
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == "Remove file"
    ]
    assert len(remove_buttons) == 1
    remove_buttons[0].click()
    qtbot.waitUntil(
        lambda: "A01T.mat" not in _visible_step_text(dialog, "Load Labels"),
        timeout=1000,
    )


def test_load_labels_next_requests_rescan_for_new_label_source(qtbot, monkeypatch):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={"summary": "Found 1 EEG file(s)."},
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)
    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: "/tmp/external-labels",
    )

    dialog.add_label_folder_btn.click()
    qtbot.wait(0)
    dialog.next_button.click()
    qtbot.wait(0)

    assert dialog.result() == QDialog.DialogCode.Accepted
    result = dialog.get_result()
    assert result["label_sources_changed"] is True
    assert result["label_sources"] == ["/tmp/external-labels"]
    assert result["resume_step"] == "Review Metadata"


def test_data_interpretation_preview_dialog_can_open_at_resume_step(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={"summary": "Found 1 EEG file(s)."},
        validation_decision={"decision": "safe"},
        initial_step="Review Metadata",
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(0)

    assert dialog.step_stack.currentIndex() == 2
    assert _visible_group_titles(dialog) == ["Review Metadata"]
    assert dialog.next_button.text() == "Next: Match Labels"


def test_load_labels_next_returns_sources_for_outer_review_rerun(
    qtbot,
    monkeypatch,
):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={"summary": "Found 1 EEG file(s)."},
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)
    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: "/tmp/external-labels",
    )

    dialog.add_label_folder_btn.click()
    qtbot.wait(0)
    dialog.next_button.click()
    qtbot.wait(0)

    assert dialog.result() == QDialog.DialogCode.Accepted
    result = dialog.get_result()
    assert result["label_sources_changed"] is True
    assert result["label_sources"] == ["/tmp/external-labels"]
    assert result["resume_step"] == "Review Metadata"
    assert dialog.scan_result.get("label_carriers") is None


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


def test_label_source_identity_does_not_resolve_the_filesystem(monkeypatch):
    def _unexpected_resolve(*_args, **_kwargs):
        raise AssertionError("UI label-source identity must not resolve the filesystem")

    monkeypatch.setattr(Path, "resolve", _unexpected_resolve)

    assert (
        DataInterpretationPreviewDialog._normalized_label_source_key(
            r"D:\\datasets\\labels\\A01T.mat"
        )
        == "d:/datasets/labels/a01t.mat"
    )
    assert (
        DataInterpretationPreviewDialog._normalized_label_source_key(
            "/mnt/d/datasets/labels/A01T.mat/"
        )
        == "/mnt/d/datasets/labels/A01T.mat"
    )


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


def test_data_interpretation_preview_dialog_add_label_folder_requests_rescan(
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
    assert dialog.result() == QDialog.DialogCode.Accepted

    result = dialog.get_result()
    assert result["label_sources"] == ["/tmp/external-labels"]
    assert result["label_sources_changed"] is True


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
    assert "label_carrier" not in result["choices"]
    assert "label_carrier_choices" not in result["choices"]
    assert "Skipped" in dialog.label_sources_label.text()


def test_match_labels_selecting_source_after_skip_clears_skip_choice(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "internal_event_preview": {
                "pattern_status": "Shared event pattern detected",
                "candidate_label_events": [
                    {
                        "event_code": "769",
                        "use_as": "Class label",
                        "event_count": 72,
                        "coverage": "1/1 files",
                        "evidence": "Repeated count",
                    }
                ],
                "not_used_events": [],
            },
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    dialog.skip_labels_btn.click()
    qtbot.wait(0)
    assert dialog.get_result()["choices"]["skip_labels"] is True

    _show_step(dialog, "Match Labels")
    qtbot.wait(0)
    internal_index = dialog.label_source_mode_combo.findData("internal_events")
    dialog.label_source_mode_combo.setCurrentIndex(internal_index)
    dialog.label_source_mode_combo.activated.emit(internal_index)
    qtbot.wait(0)

    result = dialog.get_result()
    assert "skip_labels" not in result["choices"]
    assert result["choices"]["label_carrier"] == "embedded_events"


def test_dialog_rehydrates_skip_exclusions_and_embedded_source_choices(qtbot):
    label_path = "/tmp/source/labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [label_path],
        },
        preview={
            "label_carrier_preview": [],
            "internal_event_preview": {
                "candidate_label_events": [
                    {
                        "event_code": "769",
                        "use_as": "Class label",
                        "event_count": 72,
                        "coverage": "1/1 files",
                        "evidence": "Repeated count",
                    }
                ],
                "not_used_events": [],
            },
        },
        validation_decision={"decision": "safe"},
        choices={
            "skip_labels": True,
            "excluded_label_carriers": [label_path],
            "label_carrier": "embedded_events",
        },
    )
    qtbot.addWidget(dialog)

    assert dialog._skip_labels is True
    assert dialog._excluded_label_carriers == [label_path]
    assert dialog.label_source_mode_combo.currentData() == "internal_events"
    assert dialog._label_carrier_preview_rows() == []


def test_explicit_empty_label_carrier_preview_does_not_restore_scan_carriers(qtbot):
    label_path = "/tmp/source/labels/A01T.mat"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [label_path],
        },
        preview={"label_carrier_preview": []},
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)

    assert dialog._label_carrier_preview_rows() == []
    assert dialog.label_carrier_tree.topLevelItemCount() == 1
    first = dialog.label_carrier_tree.topLevelItem(0)
    assert first is not None
    assert first.text(0) == "No external label file"


def test_load_labels_duplicate_source_after_skip_reenables_existing_labels(
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
                    "selected_label_field": "classlabel",
                    "selected_anchor": "768",
                    "placement_method": "eeg_event",
                }
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    dialog.skip_labels_btn.click()
    qtbot.wait(0)
    assert dialog.get_result()["choices"]["skip_labels"] is True

    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog.QFileDialog.getOpenFileNames",
        lambda *_args, **_kwargs: ([auto_label], ""),
    )
    dialog.add_label_file_btn.click()
    qtbot.wait(0)

    result = dialog.get_result()
    assert "skip_labels" not in result["choices"]
    assert "Already included" in dialog.label_sources_label.text()
    qtbot.waitUntil(
        lambda: _visible_step_text(dialog, "Load Labels").splitlines().count("A01T.mat")
        == 1,
        timeout=1000,
    )
    assert _visible_step_text(dialog, "Load Labels").splitlines().count("A01T.mat") == 1
    _show_step(dialog, "Match Labels")
    assert dialog.label_source_mode_combo.currentData() == "loaded_label_files"
    assert "A01T.mat" in _tree_text(dialog.label_carrier_tree)


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
            "class_map": {"left": "Left hand", "right": "Right hand"},
            "class_map_source": "label_carriers",
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
    assert dialog.review_tree.textElideMode() == Qt.TextElideMode.ElideNone
    assert dialog.review_tree.wordWrap()
    assert not dialog.review_tree.uniformRowHeights()
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


def test_match_labels_step_surfaces_bids_event_review(qtbot):
    events_path = "/tmp/source/sub-01_task-mi_run-01_events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "bids",
            "eeg_files": ["/tmp/source/sub-01_task-mi_run-01_raw.fif"],
            "label_carriers": [events_path],
            "bids": {
                "is_bids": True,
                "subjects": ["01"],
                "sessions": [],
                "tasks": ["mi"],
                "runs": ["01"],
                "events_files": [events_path],
            },
        },
        preview={
            "class_map": {"left": "Left hand", "right": "Right hand"},
            "class_map_source": "label_carriers",
            "label_carrier_preview": [
                {
                    "path": events_path,
                    "name": "sub-01_task-mi_run-01_events.tsv",
                    "format": "BIDS events",
                    "bids_event_columns": ["onset", "duration", "trial_type"],
                    "label_candidates": ["trial_type"],
                    "anchor_candidates": ["onset"],
                    "time_field_candidates": ["onset"],
                    "duration_candidates": ["duration"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "label_value_counts": {"left": 3, "right": 3},
                    "value_decisions": {
                        "left": {
                            "role": "unknown",
                            "keep_event": None,
                            "use_as_class": None,
                            "suggested_name": "Left hand",
                            "decision": "unresolved",
                            "count": 3,
                        },
                        "right": {
                            "role": "unknown",
                            "keep_event": None,
                            "use_as_class": None,
                            "suggested_name": "Right hand",
                            "decision": "unresolved",
                            "count": 3,
                        },
                    },
                    "time_model": "seconds",
                    "placement_method": "time_field",
                    "granularity": "trial",
                    "warnings": [
                        "sub-01_task-mi_run-01_events.tsv events.json sidecar is "
                        "missing; class names and event semantics need confirmation."
                    ],
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 820)
    dialog.show()
    qtbot.wait(0)

    _show_step(dialog, "Match Labels")
    qtbot.wait(0)
    text = _visible_step_text(dialog, "Match Labels")

    assert "BIDS events.tsv" in text
    assert (
        "Review BIDS event timing and class fields for subject 01, task mi, run 01"
        in text
    )
    assert "events.tsv columns" in text
    assert "onset, duration, trial_type" in text
    assert "EEG/event pairing" in text
    assert "Matched by BIDS subject/session/task/run entities" in text
    assert "Label field" in text
    assert "trial_type recommended" in text
    assert "Timing fields" in text
    assert "onset + duration" in text
    assert "Event value decisions" in text
    assert dialog.event_value_editor is not None
    assert any(
        editor.text() == "Left hand"
        for editor in dialog.event_value_editor.findChildren(QLineEdit)
    )
    assert "3 · 1/1" in text
    assert "events.json sidecar is missing" in text
    assert "BIDS label values" in text
    assert "File pairing" not in text
    assert "Place labels by" not in text
    assert dialog.label_values_card.isVisibleTo(dialog)
    assert not dialog.pairing_card.isVisibleTo(dialog)
    assert not dialog.placement_card.isVisibleTo(dialog)


def test_bids_value_decisions_are_returned_to_backend_choices(qtbot):
    events_path = "/tmp/source/sub-01_task-mi_events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "bids",
            "eeg_files": ["/tmp/source/sub-01_task-mi_eeg.vhdr"],
            "label_carriers": [events_path],
            "bids": {"is_bids": True, "events_files": [events_path]},
        },
        preview={
            "metadata_preview": [
                {
                    "file": "sub-01_task-mi_eeg.vhdr",
                    "subject": {"value": "01", "decision": "resolved"},
                    "session": {"value": "", "decision": "optional"},
                    "task": {"value": "mi", "decision": "resolved"},
                    "run": {"value": "", "decision": "optional"},
                }
            ],
            "label_carrier_preview": [
                {
                    "path": events_path,
                    "name": "sub-01_task-mi_events.tsv",
                    "format": "BIDS events",
                    "selected_target_file": "/tmp/source/sub-01_task-mi_eeg.vhdr",
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "time_model": "seconds",
                    "placement_method": "interval",
                    "granularity": "event",
                    "role": "external labels",
                    "value_decisions": {
                        "left": {
                            "role": "unknown",
                            "keep_event": None,
                            "use_as_class": None,
                            "suggested_name": "Left hand",
                            "decision": "unresolved",
                            "count": 3,
                        },
                        "button_press": {
                            "role": "unknown",
                            "keep_event": None,
                            "use_as_class": None,
                            "suggested_name": "Button press",
                            "decision": "unresolved",
                            "count": 3,
                        },
                    },
                }
            ],
        },
        validation_decision={"decision": "blocked"},
    )
    qtbot.addWidget(dialog)

    assert dialog.event_value_editor is not None
    dialog.event_value_editor.set_value_decision(
        "left",
        role="stimulus",
        use="class",
        class_name="Left hand",
    )
    dialog.event_value_editor.set_value_decision(
        "button_press",
        role="response",
        use="event",
    )

    submission = dialog._submission_projection()
    result = dialog.get_result()
    choices = result["choices"]["label_carrier_choices"][events_path]
    assert choices["value_decisions"]["left"]["use_as_class"] is True
    assert choices["value_decisions"]["button_press"] == {
        "role": "response",
        "keep_event": True,
        "use_as_class": False,
        "suggested_name": "Button press",
        "decision_source": "user_choice",
        "provenance": "ui_event_value_editor",
    }
    assert dialog._has_unresolved_required_decisions() is False
    assert dialog.can_submit_for_backend_review() is True
    assert result["confirmed"] is submission.confirmed_on_accept
    assert submission.confirmed_on_accept is True


def test_event_value_edits_defer_hidden_review_rebuilds(qtbot, monkeypatch):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={},
        preview={},
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    _show_step(dialog, "Match Labels")
    calls: list[str] = []
    monkeypatch.setattr(
        dialog,
        "_sync_apply_state",
        lambda: calls.append("apply"),
    )
    monkeypatch.setattr(
        dialog,
        "_sync_review_status_copy",
        lambda: calls.append("status"),
    )
    monkeypatch.setattr(
        dialog,
        "_refresh_review_action_cards",
        lambda: calls.append("actions"),
    )
    monkeypatch.setattr(
        dialog,
        "_refresh_review_import_summary",
        lambda: calls.append("summary"),
    )

    dialog._handle_event_value_decisions_changed()

    assert calls == ["apply"]


def test_completed_event_values_can_recheck_with_only_optional_metadata_missing(qtbot):
    events_path = "/tmp/source/sub-01_task-mi_events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "bids",
            "eeg_files": ["/tmp/source/sub-01_task-mi_eeg.vhdr"],
            "label_carriers": [events_path],
            "bids": {"is_bids": True, "events_files": [events_path]},
        },
        preview={
            "metadata_preview": [
                {
                    "file": "sub-01_task-mi_eeg.vhdr",
                    "subject": {"value": "01", "decision": "resolved"},
                    "session": {"value": "", "decision": "optional"},
                    "task": {"value": "", "decision": "blocked"},
                    "run": {"value": "", "decision": "optional"},
                }
            ],
            "label_carrier_preview": [
                {
                    "path": events_path,
                    "name": "sub-01_task-mi_events.tsv",
                    "format": "BIDS events",
                    "selected_target_file": "/tmp/source/sub-01_task-mi_eeg.vhdr",
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "time_model": "seconds",
                    "placement_method": "interval",
                    "granularity": "event",
                    "role": "external labels",
                    "value_decisions": {
                        "left": {
                            "role": "unknown",
                            "keep_event": None,
                            "use_as_class": None,
                            "suggested_name": "Left hand",
                            "decision": "unresolved",
                            "count": 3,
                        },
                    },
                }
            ],
        },
        validation_decision={"decision": "blocked"},
    )
    qtbot.addWidget(dialog)

    assert dialog.event_value_editor is not None
    dialog.event_value_editor.set_value_decision(
        "left",
        role="stimulus",
        use="class",
        class_name="Left hand",
    )

    assert dialog._event_value_decisions_ready_for_recheck() is True
    assert dialog._has_unresolved_required_decisions() is False
    assert dialog.can_submit_for_backend_review() is True
    assert dialog._review_ready_for_recheck() is True
    assert dialog.apply_button.isEnabled() is True
    submission = dialog._submission_projection()
    assert dialog.get_result()["confirmed"] is submission.confirmed_on_accept
    assert submission.confirmed_on_accept is True


def test_regular_folder_events_tsv_uses_general_label_flow(qtbot):
    events_path = "/tmp/source/events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "folder",
            "eeg_files": ["/tmp/source/A01T.gdf"],
            "label_carriers": [events_path],
            "bids": {
                "is_bids": False,
                "looks_like_bids": False,
                "events_files": [events_path],
            },
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": events_path,
                    "name": "events.tsv",
                    "format": "BIDS events",
                    "bids_event_columns": ["onset", "duration", "trial_type"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "time_model": "seconds",
                    "placement_method": "interval",
                    "granularity": "trial",
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 820)
    dialog.show()
    qtbot.wait(0)

    _show_step(dialog, "Choose EEG Data")
    choose_text = _visible_step_text(dialog, "Choose EEG Data")
    assert "BIDS folder import" not in choose_text

    _show_step(dialog, "Load Labels")
    load_text = _visible_step_text(dialog, "Load Labels")
    assert "Label files" in load_text
    assert "BIDS events.tsv" not in load_text
    assert dialog.add_label_file_btn.isVisibleTo(dialog)
    assert dialog.add_label_folder_btn.isVisibleTo(dialog)
    assert dialog.skip_labels_btn.isVisibleTo(dialog)

    _show_step(dialog, "Match Labels")
    qtbot.wait(0)
    assert not dialog.bids_event_review_card.isVisibleTo(dialog)
    assert dialog.pairing_card.isVisibleTo(dialog)
    assert dialog.placement_card.isVisibleTo(dialog)
    assert dialog.label_source_mode_combo.currentText() == "Loaded label files"


def test_load_labels_removing_bids_events_refreshes_active_bids_state(qtbot):
    events_path = "/tmp/source/sub-01_task-mi_run-01_events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "bids",
            "eeg_files": ["/tmp/source/sub-01_task-mi_run-01_raw.fif"],
            "label_carriers": [events_path],
            "bids": {
                "is_bids": True,
                "subjects": ["01"],
                "tasks": ["mi"],
                "runs": ["01"],
                "events_files": [events_path],
            },
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "label_carrier_preview": [
                {
                    "path": events_path,
                    "name": "sub-01_task-mi_run-01_events.tsv",
                    "format": "BIDS events",
                    "bids_event_columns": ["onset", "duration", "trial_type"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "time_model": "seconds",
                    "placement_method": "interval",
                    "granularity": "trial",
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Load Labels")
    qtbot.wait(0)

    assert dialog._has_bids_events()
    assert not dialog.skip_labels_btn.isVisibleTo(dialog)
    assert not dialog.add_label_file_btn.isVisibleTo(dialog)
    assert not dialog.add_label_folder_btn.isVisibleTo(dialog)

    _click_source_row_button(
        dialog,
        "sub-01_task-mi_run-01_events.tsv",
        "Remove file",
    )
    qtbot.wait(0)

    assert not dialog._has_bids_events()
    assert not dialog.skip_labels_btn.isVisibleTo(dialog)
    assert not dialog.add_label_file_btn.isVisibleTo(dialog)
    assert not dialog.add_label_folder_btn.isVisibleTo(dialog)
    assert "BIDS events.tsv" in _visible_step_text(dialog, "Load Labels")
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)
    assert not dialog.bids_event_review_card.isVisibleTo(dialog)
    assert dialog.get_result()["choices"]["excluded_label_carriers"] == [events_path]


def test_bids_preset_surfaces_scope_labels_metadata_and_review(qtbot):
    events_path = "/tmp/source/sub-01_task-mi_run-01_events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "bids",
            "eeg_files": ["/tmp/source/sub-01_task-mi_run-01_raw.fif"],
            "label_carriers": [events_path],
            "bids": {
                "is_bids": True,
                "subjects": ["01"],
                "tasks": ["mi"],
                "runs": ["01"],
                "events_files": [events_path],
                "has_participants_tsv": False,
            },
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "source_selection": "BIDS folder",
            "metadata_preview": [
                {
                    "file": "sub-01_task-mi_run-01_raw.fif",
                    "subject": {"value": "01", "decision": "safe"},
                    "session": {"value": "", "decision": "safe"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": "01", "decision": "safe"},
                }
            ],
            "label_carrier_preview": [
                {
                    "path": events_path,
                    "name": "sub-01_task-mi_run-01_events.tsv",
                    "format": "BIDS events",
                    "bids_event_columns": ["onset", "duration", "trial_type"],
                    "label_candidates": ["trial_type", "value"],
                    "anchor_candidates": ["onset"],
                    "duration_candidates": ["duration"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "time_model": "seconds",
                    "placement_method": "interval",
                    "granularity": "trial",
                    "warnings": ["events.json sidecar is missing."],
                },
            ],
            "action_items": [
                {
                    "target_step": "Match Labels",
                    "issue": "Confirm BIDS class names.",
                    "impact": "events.json was not found.",
                    "next_action": "Confirm class names in Match Labels.",
                }
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 820)
    dialog.show()
    qtbot.wait(0)

    _show_step(dialog, "Choose EEG Data")
    choose_text = _visible_step_text(dialog, "Choose EEG Data")
    assert "BIDS folder import" in choose_text
    assert "1 subject" in choose_text
    assert "1 task" in choose_text
    assert "1 events.tsv file" in choose_text
    assert "Not a full BIDS validator" in choose_text

    _show_step(dialog, "Load Labels")
    load_text = _visible_step_text(dialog, "Load Labels")
    assert "BIDS events.tsv" in load_text
    assert "default label and timing source" in load_text
    assert "events.json" in load_text
    assert "Missing" in load_text
    assert not dialog.skip_labels_btn.isVisibleTo(dialog)
    assert not dialog.add_label_file_btn.isVisibleTo(dialog)
    assert not dialog.add_label_folder_btn.isVisibleTo(dialog)

    _show_step(dialog, "Review Metadata")
    metadata_text = _visible_step_text(dialog, "Review Metadata")
    assert "BIDS metadata" in metadata_text
    assert "participants.tsv" in metadata_text
    assert "Not found" in metadata_text
    assert dialog.smart_parse_btn.text() == "Adjust parsing"

    _show_step(dialog, "Review and Import")
    qtbot.wait(0)
    review_text = _visible_step_text(dialog, "Review and Import")
    assert "BIDS entities reviewed" in review_text
    assert "BIDS events.tsv" in review_text
    assert "Trial type" in review_text
    assert "Label interval" in review_text
    assert "Recipe" in review_text
    action_text = "\n".join(
        label.text()
        for label in dialog.review_actions_panel.findChildren(QLabel)
        if label.text().strip()
    )
    assert "Import review" in review_text
    assert "Review before import" not in review_text
    assert "Needs your decision" not in action_text
    assert "Confirm class names in Match Labels." not in action_text
    assert not any(
        button.text() == "Fix Match Labels"
        for button in dialog.review_actions_panel.findChildren(QPushButton)
    )


def test_bids_review_blocks_when_one_selected_run_has_no_events_tsv(qtbot):
    eeg_1 = "/tmp/source/sub-01_task-mi_run-01_raw.fif"
    eeg_2 = "/tmp/source/sub-01_task-mi_run-02_raw.fif"
    events_1 = "/tmp/source/sub-01_task-mi_run-01_events.tsv"
    blocker = (
        "Label carrier pairing is incomplete: 1/2 selected EEG files are paired; "
        "unpaired EEG files: sub-01_task-mi_run-02_raw.fif."
    )
    action_item = {
        "target_step": "Match Labels",
        "issue": blocker,
        "impact": "Every selected EEG file needs a label carrier.",
        "next_action": "Go to Label Alignment.",
        "severity": "blocked",
    }
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "bids",
            "eeg_files": [eeg_1, eeg_2],
            "label_carriers": [events_1],
            "bids": {"is_bids": True, "events_files": [events_1]},
        },
        preview={
            "summary": "Found 2 EEG file(s) and 1 label/event carrier(s).",
            "source_selection": "BIDS folder",
            "selected_eeg_files": [eeg_1, eeg_2],
            "metadata_preview": [
                {
                    "file": eeg.rsplit("/", 1)[-1],
                    "subject": {"value": "01", "decision": "safe"},
                    "session": {"value": "", "decision": "safe"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": run, "decision": "safe"},
                }
                for eeg, run in ((eeg_1, "01"), (eeg_2, "02"))
            ],
            "label_carrier_preview": [
                {
                    "path": events_1,
                    "name": "sub-01_task-mi_run-01_events.tsv",
                    "format": "BIDS events",
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "time_model": "seconds",
                    "placement_method": "interval",
                    "granularity": "trial",
                }
            ],
            "blocked_reasons": [blocker],
            "action_items": [action_item],
        },
        validation_decision={
            "decision": "blocked",
            "blocked_reasons": [blocker],
            "action_items": [action_item],
        },
    )
    qtbot.addWidget(dialog)
    dialog.show()
    _show_step(dialog, "Review and Import")
    qtbot.wait(0)

    review_text = _visible_step_text(dialog, "Review and Import")
    assert "1/2 EEG files paired" in review_text
    assert "1 need label" in review_text
    assert "Needs review" in review_text
    assert not dialog.apply_button.isEnabled()

    metadata_item, _original_metadata = dialog._metadata_items[0]
    metadata_item.setText(3, "updated-task")
    dialog._sync_apply_state()

    assert not dialog.apply_button.isEnabled()


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

    rendered_step_labels = [label.text() for label in dialog.step_labels]
    full_step_labels = [
        "1. Choose EEG Data",
        "2. Load Labels",
        "3. Review Metadata",
        "4. Match Labels",
        "5. Review and Import",
    ]
    compact_step_labels = [
        "1. EEG",
        "2. Labels",
        "3. Details",
        "4. Match",
        "5. Review",
    ]
    assert rendered_step_labels in (full_step_labels, compact_step_labels)
    if rendered_step_labels == compact_step_labels:
        assert [label.toolTip() for label in dialog.step_labels] == [
            "Choose EEG Data",
            "Load Labels",
            "Review Metadata",
            "Match Labels",
            "Review and Import",
        ]
    assert all(
        label.fontMetrics().horizontalAdvance(label.text())
        <= label.contentsRect().width() + 1
        for label in dialog.step_labels
    )

    for step_title, tree in (
        ("Review Metadata", dialog.file_tree),
        ("Match Labels", dialog.label_carrier_tree),
        ("Match Labels", dialog.event_tree),
        ("Review and Import", dialog.review_tree),
    ):
        _show_step(dialog, step_title)
        qtbot.wait(0)
        if tree is dialog.review_tree and not tree.isVisible():
            assert not dialog.review_actions_panel.isVisible()
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

    for label, text in zip(dialog.step_labels, full_step_labels, strict=True):
        label.setText(text)
        label.setFixedWidth(126)
    dialog._compact_clipped_step_labels()

    assert [label.text() for label in dialog.step_labels] == compact_step_labels
    assert all(
        label.fontMetrics().horizontalAdvance(label.text())
        <= label.contentsRect().width() + 1
        for label in dialog.step_labels
    )


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
    _show_step(dialog, "Match Labels")
    qtbot.wait(0)
    dialog._fit_all_tree_columns_to_viewport()
    qtbot.wait(0)

    item = dialog.label_carrier_tree.topLevelItem(0)
    assert item is not None
    viewport = dialog.label_carrier_tree.viewport()
    assert viewport is not None
    for column in (4, 5):
        selector = dialog.label_carrier_tree.itemWidget(item, column)
        assert isinstance(selector, ElidingComboBox)
        assert selector.parentWidget() is viewport
        assert viewport.rect().contains(selector.geometry())
        assert selector.toolTip() == selector.currentText()
        rendered_text = selector.elided_current_text()
        assert rendered_text
        assert rendered_text == selector.currentText() or "…" in rendered_text


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
    dialog.import_report_toggle.click()
    qtbot.wait(0)
    assert dialog.import_report_card.isVisibleTo(dialog)
    assert review_tree.topLevelItemCount() == 4
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


def test_import_review_refresh_detaches_previous_rows_before_rebuild(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={},
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    _show_step(dialog, "Review and Import")
    qtbot.wait(10)

    previous_rows = [
        widget
        for widget in dialog.findChildren(QLabel)
        if widget.objectName().startswith("DataImportReview")
        and widget.isVisibleTo(dialog)
    ]
    assert previous_rows

    dialog._refresh_review_import_summary()

    assert all(widget.parent() is None for widget in previous_rows)
    assert all(not widget.isVisibleTo(dialog) for widget in previous_rows)


def test_import_report_wraps_long_cells_and_uses_column_specific_tooltips(qtbot):
    issue = (
        "Label alignment is unresolved for the selected EEG and label files, so "
        "the imported labels cannot yet be assigned to the intended recordings."
    )
    impact = (
        "Training classes may be attached to the wrong trials and produce a "
        "misleading dataset if this mapping is imported without review."
    )
    next_action = (
        "Return to Match Labels and choose the label file that belongs to each EEG "
        "recording before applying the import recipe."
    )
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "action_items": [
                {
                    "target_step": "Review and Import",
                    "issue": issue,
                    "impact": impact,
                    "next_action": next_action,
                    "severity": "needs_confirmation",
                }
            ]
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    _show_step(dialog, "Review and Import")
    dialog.import_report_toggle.click()
    qtbot.wait(0)

    report = dialog.review_tree
    assert report.topLevelItemCount() == 1
    item = report.topLevelItem(0)
    assert item is not None
    assert [item.text(column) for column in range(4)] == [
        "Review and Import",
        issue,
        impact,
        next_action,
    ]
    assert [item.toolTip(column) for column in range(4)] == [
        "Review and Import",
        issue,
        impact,
        next_action,
    ]
    assert report.textElideMode() == Qt.TextElideMode.ElideNone
    assert report.wordWrap()
    assert not report.uniformRowHeights()
    assert report.sizeHintForRow(0) > report.fontMetrics().height() + 10


def test_review_and_import_describes_a_load_only_recipe(qtbot):
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
            "selected_eeg_files": ["/tmp/source/A01T.gdf"],
            "metadata_preview": [
                {
                    "file": "A01T.gdf",
                    "subject": {"value": "A01", "decision": "safe"},
                    "session": {"value": "T", "decision": "safe"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": "01", "decision": "safe"},
                },
            ],
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "A01T.mat",
                    "format": "MAT",
                    "label_candidates": ["classlabel"],
                    "anchor_candidates": ["768", "769"],
                    "selected_label_field": "classlabel",
                    "selected_anchor": "768",
                    "selected_target_event_codes": ["768"],
                    "time_model": "trial_order",
                    "granularity": "trial",
                    "placement_method": "eeg_event",
                    "role": "class cue labels",
                    "label_row_count": 288,
                },
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)
    _show_step(dialog, "Review and Import")
    qtbot.wait(0)

    review_text = _visible_step_text(dialog, "Review and Import")

    assert "Import review" in review_text
    assert "Import summary" not in review_text
    assert "EEG data" in review_text
    assert "1 EEG file" in review_text
    assert "A01T.gdf" in review_text
    assert "Label placement" in review_text
    assert "Classlabel" in review_text
    assert "target EEG events 768" in review_text
    assert "Recipe" in review_text
    assert "Not saved" in review_text
    assert "Save the current data import and label mapping settings" in review_text
    assert "Epoch setup" not in review_text
    assert dialog.save_recipe_check.text() == "Save recipe"
    assert dialog.save_recipe_check.isVisibleTo(dialog)
    assert dialog.import_report_toggle.text() == "View import report"
    assert not dialog.import_review_card.isAncestorOf(dialog.import_report_toggle)
    assert (
        dialog.import_report_toggle.geometry().top()
        >= dialog.import_review_card.geometry().bottom()
    )
    assert "Ready to import" not in review_text
    assert "No blocking review items" not in review_text
    assert "Epoch setup will use" not in review_text


def test_review_and_import_metadata_summary_uses_manual_edits(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "metadata_preview": [
                {
                    "file": "A01T.gdf",
                    "subject": {"value": "", "decision": "needs_confirmation"},
                    "session": {"value": "", "decision": "needs_confirmation"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": "01", "decision": "safe"},
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)
    _show_step(dialog, "Review Metadata")
    qtbot.wait(0)

    item = dialog.file_tree.topLevelItem(0)
    assert item is not None
    item.setText(1, "A01")
    item.setText(2, "T")

    _show_step(dialog, "Review and Import")
    qtbot.wait(0)
    review_text = _visible_step_text(dialog, "Review and Import")

    assert "Import review" in review_text
    assert "Metadata" in review_text
    assert "Ready" in review_text
    assert "Missing subject" not in review_text
    assert "Missing session" not in review_text


def test_save_recipe_and_import_do_not_require_optional_task_or_epoch_setup(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "metadata_preview": [
                {
                    "file": "A01T.gdf",
                    "subject": {"value": "", "decision": "needs_confirmation"},
                    "session": {"value": "", "decision": "needs_confirmation"},
                    "task": {"value": "", "decision": "needs_confirmation"},
                    "run": {"value": "", "decision": "needs_confirmation"},
                },
            ],
            "class_map": {"769": "left hand"},
            "event_roles": {"internal_events": "event role candidates"},
            "epoch_handoff": {
                "ready": False,
                "supervised_ready": False,
                "supervised_blockers": ["Epoch setup is incomplete."],
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    assert not dialog.apply_button.isEnabled()
    assert not dialog.save_recipe_check.isEnabled()
    assert not dialog.save_recipe_check.isChecked()

    item = dialog.file_tree.topLevelItem(0)
    assert item is not None
    item.setText(1, "A01")
    dialog._sync_apply_state()

    assert dialog.apply_button.isEnabled()
    assert dialog.save_recipe_check.isEnabled()
    assert not dialog.save_recipe_check.isChecked()
    review_rows = {row["item"]: row for row in dialog._review_import_status_rows()}
    assert review_rows["Metadata"]["status"] == "Ready with notes"
    assert review_rows["Recipe"]["status"] == "Not saved"
    assert "Epoch" not in review_rows["Recipe"]["summary"]

    dialog.save_recipe_check.click()
    assert dialog.save_recipe_check.isChecked()
    item.setText(2, "T")
    dialog._sync_apply_state()
    assert dialog.save_recipe_check.isChecked()


def test_bids_optional_task_and_run_do_not_block_import_or_recipe(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/bids",
            "source_kind": "bids",
            "bids": {"is_bids": True},
            "eeg_files": ["/tmp/bids/sub-01_eeg.edf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "selected_eeg_files": ["/tmp/bids/sub-01_eeg.edf"],
            "metadata_preview": [
                {
                    "file": "sub-01_eeg.edf",
                    "subject": {"value": "01", "decision": "safe"},
                    "session": {"value": "", "decision": "needs_confirmation"},
                    "task": {"value": "", "decision": "needs_confirmation"},
                    "run": {"value": "", "decision": "needs_confirmation"},
                }
            ],
            "class_map": {"1": "class 1"},
            "event_roles": {"internal_events": "event role candidates"},
            "epoch_handoff": {
                "ready": False,
                "supervised_ready": False,
                "supervised_blockers": ["Epoch setup is incomplete."],
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    rows = {row["item"]: row for row in dialog._review_import_status_rows()}
    assert dialog.apply_button.isEnabled()
    assert rows["Metadata"]["status"] == "Ready with notes"
    assert "task, run" in rows["Metadata"]["summary"]
    assert rows["Recipe"]["status"] == "Not saved"
    assert "Epoch" not in rows["Recipe"]["summary"]


def test_review_recipe_action_is_optional_and_reports_pending_selection(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "selected_eeg_files": ["/tmp/source/A01T.gdf"],
            "metadata_preview": [
                {
                    "file": "A01T.gdf",
                    "subject": {"value": "A01", "decision": "safe"},
                    "session": {"value": "", "decision": "needs_confirmation"},
                    "task": {"value": "", "decision": "needs_confirmation"},
                    "run": {"value": "", "decision": "needs_confirmation"},
                }
            ],
            "class_map": {"769": "left hand"},
            "event_roles": {"internal_events": "event role candidates"},
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    _show_step(dialog, "Review and Import")

    assert isinstance(dialog.save_recipe_check, QPushButton)
    assert dialog.save_recipe_check.isCheckable()
    assert dialog.save_recipe_check.text() == "Save recipe"
    assert dialog.apply_button.isEnabled()

    dialog.save_recipe_check.click()
    rows = {row["item"]: row for row in dialog._review_import_status_rows()}
    assert rows["Recipe"]["status"] == "Will save"
    assert rows["Recipe"]["summary"] == (
        "Recipe will be saved after this import succeeds."
    )
    assert rows["Recipe"]["action"] == "Cancel save"
    assert dialog.apply_button.isEnabled()


def test_import_report_includes_import_facts_and_issue_summary(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "selected_eeg_files": ["/tmp/source/A01T.gdf"],
            "metadata_preview": [
                {
                    "file": "A01T.gdf",
                    "subject": {"value": "A01", "decision": "safe"},
                    "session": {"value": "", "decision": "needs_confirmation"},
                    "task": {"value": "", "decision": "needs_confirmation"},
                    "run": {"value": "", "decision": "needs_confirmation"},
                }
            ],
            "class_map": {"769": "left hand"},
            "event_roles": {"internal_events": "event role candidates"},
            "resource_preflight": {
                "risk_level": "safe",
                "required_memory_bytes": 128 * 1024 * 1024,
                "available_memory_bytes": 8 * 1024 * 1024 * 1024,
            },
            "action_items": [
                {
                    "target_step": "Load Labels",
                    "issue": "Labels skipped for now.",
                    "impact": "Supervised workflows remain limited.",
                    "next_action": "Load labels later if needed.",
                    "severity": "limited",
                }
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    _show_step(dialog, "Review and Import")

    dialog.import_report_toggle.click()
    report = dialog.import_report_summary.text()

    assert dialog.import_report_card.isVisibleTo(dialog)
    for heading in (
        "EEG files:",
        "Label files:",
        "Metadata:",
        "Label alignment:",
        "Label placement:",
        "Resource check:",
        "Optional notes:",
        "Blocking issues:",
    ):
        assert heading in report
    assert "A01T.gdf" in report
    assert "Ready with notes" in report
    assert "Safe" in report
    assert "Optional notes:" in report
    assert "Labels skipped for now." in report.split("Blocking issues:", 1)[0]
    assert "Blocking issues: None" in report
    assert "Labels skipped for now" not in report.split("Blocking issues:", 1)[1]


def test_review_and_import_optional_task_uses_compact_note_row(qtbot):
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
            "metadata_preview": [
                {
                    "file": f"A0{index}T.gdf",
                    "subject": {"value": f"A0{index}", "decision": "safe"},
                    "session": {"value": "", "decision": "needs_confirmation"},
                    "task": {"value": "", "decision": "needs_confirmation"},
                    "run": {"value": "", "decision": "needs_confirmation"},
                }
                for index in range(1, 4)
            ],
            "action_items": [
                {
                    "target_step": "Review Metadata",
                    "issue": "Review metadata",
                    "impact": "Task metadata is missing.",
                    "next_action": "Review the metadata table.",
                },
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

    review_text = _visible_step_text(dialog, "Review and Import")
    action_text = "\n".join(
        label.text()
        for label in dialog.review_actions_panel.findChildren(QLabel)
        if label.text().strip()
    )

    assert "Import review" in review_text
    assert "Metadata" in review_text
    assert "Ready with notes" in review_text
    assert "Optional fields missing: session, task, run" in review_text
    assert "3 files affected" in review_text
    assert "Review before import" not in review_text
    assert "Review metadata" not in action_text
    assert any(
        button.text() == "Edit Metadata" for button in dialog.findChildren(QPushButton)
    )

    _click_button(dialog, "Edit Metadata")

    assert dialog._step_titles[dialog.step_stack.currentIndex()] == "Review Metadata"


def test_review_and_import_status_badges_share_geometry(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "metadata_preview": [
                {
                    "file": "A01T.gdf",
                    "subject": {"value": "A01", "decision": "safe"},
                    "session": {"value": "", "decision": "needs_confirmation"},
                    "task": {"value": "", "decision": "needs_confirmation"},
                    "run": {"value": "", "decision": "needs_confirmation"},
                }
            ],
            "class_map": {"769": "left hand"},
            "event_roles": {"internal_events": "event role candidates"},
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    _show_step(dialog, "Review and Import")
    qtbot.wait(0)

    badges = [
        label
        for label in dialog.findChildren(QLabel)
        if label.objectName().startswith("DataImportReviewStatus")
        and label.isVisibleTo(dialog)
    ]

    assert len(badges) == 6
    assert len({badge.height() for badge in badges}) == 1
    assert len({badge.width() for badge in badges}) == 1
    assert all(
        badge.alignment()
        == (Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        for badge in badges
    )
    assert all(badge.height() >= badge.fontMetrics().height() + 8 for badge in badges)


def test_review_and_import_drops_stale_metadata_action_after_manual_edits(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "metadata_preview": [
                {
                    "file": "A01T.gdf",
                    "subject": {"value": "", "decision": "needs_confirmation"},
                    "session": {"value": "", "decision": "needs_confirmation"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": "01", "decision": "safe"},
                },
            ],
            "action_items": [
                {
                    "target_step": "Review Metadata",
                    "issue": "Review metadata",
                    "impact": "Subject metadata is missing.",
                    "next_action": "Review the metadata table.",
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)
    _show_step(dialog, "Review Metadata")
    qtbot.wait(0)

    item = dialog.file_tree.topLevelItem(0)
    assert item is not None
    item.setText(1, "A01")
    item.setText(2, "T")

    _show_step(dialog, "Review and Import")
    qtbot.wait(0)
    review_text = _visible_step_text(dialog, "Review and Import")

    assert "Import review" in review_text
    assert "Metadata" in review_text
    assert "Ready" in review_text
    assert "Review metadata" not in review_text
    assert "Subject metadata is missing" not in review_text


def test_review_and_import_groups_repeated_file_action_items(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "summary": "Found 3 EEG file(s).",
            "action_items": [
                {
                    "target_step": "Review Metadata",
                    "issue": "Confirm subject metadata.",
                    "impact": f"Subject metadata is missing in A0{index}T.gdf.",
                    "next_action": "Confirm subject in Review Metadata.",
                }
                for index in range(1, 4)
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

    action_cards = dialog.review_actions_panel.findChildren(
        QFrame,
        "DataImportActionCard",
    )
    action_text = "\n".join(
        label.text()
        for label in dialog.review_actions_panel.findChildren(QLabel)
        if label.text().strip()
    )

    assert len(action_cards) == 0
    assert not dialog.review_actions_panel.isVisibleTo(dialog)
    assert "Review metadata" not in action_text
    assert dialog.review_tree.topLevelItemCount() == 1
    review_item = dialog.review_tree.topLevelItem(0)
    assert review_item is not None
    assert "3 files" in review_item.text(2)
    assert "A01T.gdf" in review_item.text(2)
    assert "A02T.gdf" in review_item.text(2)
    assert "A03T.gdf" in review_item.text(2)


def test_review_and_import_groups_file_scoped_issues_by_problem(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "summary": "Found 3 EEG file(s).",
            "action_items": [
                {
                    "target_step": "Review Metadata",
                    "issue": f"A0{index}T.gdf needs subject metadata review.",
                    "impact": "Subject metadata is missing.",
                    "next_action": "Confirm subject in Review Metadata.",
                }
                for index in range(1, 4)
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

    action_cards = dialog.review_actions_panel.findChildren(
        QFrame,
        "DataImportActionCard",
    )
    action_text = "\n".join(
        label.text()
        for label in dialog.review_actions_panel.findChildren(QLabel)
        if label.text().strip()
    )

    assert len(action_cards) == 0
    assert not dialog.review_actions_panel.isVisibleTo(dialog)
    assert action_text == ""
    assert dialog.review_tree.topLevelItemCount() == 1


def test_review_and_import_keeps_warning_items_in_report_not_primary_actions(qtbot):
    warning = "Saved recipe choices were reapplied."
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "summary": "Found 3 EEG file(s).",
            "action_items": [
                {
                    "target_step": "Review and Import",
                    "issue": warning,
                    "impact": "Import may still be usable.",
                    "next_action": "Open the report for details.",
                    "severity": "warning",
                },
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)
    _show_step(dialog, "Review and Import")
    qtbot.wait(0)

    assert not dialog.review_actions_panel.isVisibleTo(dialog)
    assert warning not in _visible_step_text(dialog, "Review and Import")
    assert dialog.import_report_toggle.text() == "View import report"
    assert warning in _tree_text(dialog.review_tree)

    dialog.import_report_toggle.click()
    qtbot.wait(0)

    assert dialog.import_report_card.isVisibleTo(dialog)
    assert dialog.import_report_toggle.text() == "Hide import report"
    assert dialog.apply_button.isVisibleTo(dialog)
    apply_bottom_right = dialog.apply_button.mapTo(
        dialog,
        dialog.apply_button.rect().bottomRight(),
    )
    assert dialog.rect().contains(apply_bottom_right)


def test_review_step_compacts_and_restores_the_wizard_height(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source/A01T.gdf",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "metadata_preview": [
                {
                    "file": "A01T.gdf",
                    "subject": {"value": "A01", "decision": "safe"},
                    "session": {"value": None, "decision": "safe"},
                    "task": {"value": None, "decision": "safe"},
                    "run": {"value": None, "decision": "safe"},
                },
            ],
            "class_map": {"769": "left", "770": "right"},
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(700, max(900, dialog.minimumSizeHint().height() + 160))
    dialog.show()
    qtbot.wait(0)
    working_height = dialog.height()
    working_center = dialog.geometry().center()

    _show_step(dialog, "Review and Import")
    assert dialog.height() < working_height
    review_center = dialog.geometry().center()
    assert abs(review_center.x() - working_center.x()) <= 2
    assert abs(review_center.y() - working_center.y()) <= 2
    compact_height = dialog.height()

    dialog.import_report_toggle.click()
    assert dialog.height() > compact_height
    assert dialog.height() <= working_height
    report_center = dialog.geometry().center()
    assert abs(report_center.x() - working_center.x()) <= 2
    assert abs(report_center.y() - working_center.y()) <= 2
    review_header = dialog.review_tree.header()
    review_viewport = dialog.review_tree.viewport()
    assert review_header is not None
    assert review_viewport is not None
    assert review_header.length() == review_viewport.width()

    _show_step(dialog, "Match Labels")
    assert dialog.height() == working_height
    restored_center = dialog.geometry().center()
    assert abs(restored_center.x() - working_center.x()) <= 2
    assert abs(restored_center.y() - working_center.y()) <= 2


def test_collapsed_review_geometry_is_stable_before_and_after_report_roundtrip(qtbot):
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
            "summary": "Found 3 EEG files.",
            "metadata_preview": [
                {
                    "file": f"A0{index}T.gdf",
                    "subject": {"value": f"A0{index}", "decision": "safe"},
                    "session": {"value": "", "decision": "safe"},
                    "task": {"value": "", "decision": "safe"},
                    "run": {"value": "", "decision": "safe"},
                }
                for index in range(1, 4)
            ],
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    qtbot.wait(0)
    _show_step(dialog, "Review and Import")
    qtbot.wait(0)

    initial_size = dialog.size()
    initial_rows = {
        label.text(): label.size()
        for label in dialog.findChildren(QLabel, "DataImportReviewSummary")
        if label.isVisibleTo(dialog)
    }

    dialog.import_report_toggle.click()
    qtbot.wait(0)
    dialog.import_report_toggle.click()
    qtbot.wait(0)

    assert dialog.size() == initial_size
    assert {
        label.text(): label.size()
        for label in dialog.findChildren(QLabel, "DataImportReviewSummary")
        if label.isVisibleTo(dialog)
    } == initial_rows


def test_collapsed_review_opened_before_show_removes_trailing_scroll_gutter(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source/A01T.gdf",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "summary": "Found 1 EEG file(s).",
            "metadata_preview": [
                {
                    "file": "A01T.gdf",
                    "subject": {"value": "A01", "decision": "safe"},
                    "session": {"value": None, "decision": "safe"},
                    "task": {"value": "mi", "decision": "safe"},
                    "run": {"value": None, "decision": "safe"},
                },
            ],
            "class_map": {"769": "left", "770": "right"},
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1100, 800)
    _show_step(dialog, "Review and Import")
    dialog.save_recipe_check.setChecked(True)

    dialog.show()
    qtbot.wait(0)

    separator = dialog.findChild(QFrame, "DataImportFooterSeparator")
    assert separator is not None
    report_action_bottom = dialog.import_report_toggle.mapTo(
        dialog,
        dialog.import_report_toggle.rect().bottomRight(),
    ).y()
    separator_top = separator.mapTo(dialog, separator.rect().topLeft()).y()
    scrollbar = dialog.scroll_area.verticalScrollBar()
    assert scrollbar is not None
    assert separator_top - report_action_bottom <= 96
    if scrollbar.maximum() == 0:
        assert (
            dialog.scroll_area.verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert not scrollbar.isVisibleTo(dialog)
    else:
        assert (
            dialog.scroll_area.verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
    assert dialog.apply_button.isVisibleTo(dialog)
    assert dialog.rect().contains(
        dialog.apply_button.mapTo(
            dialog,
            dialog.apply_button.rect().bottomRight(),
        )
    )

    dialog.import_report_toggle.click()
    qtbot.wait(0)

    assert dialog.import_report_card.isVisibleTo(dialog)
    assert dialog.apply_button.isVisibleTo(dialog)
    assert dialog.rect().contains(
        dialog.apply_button.mapTo(
            dialog,
            dialog.apply_button.rect().bottomRight(),
        )
    )


def test_review_and_import_primary_actions_exclude_report_only_warnings(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "summary": "Found 1 EEG file(s).",
            "action_items": [
                {
                    "target_step": "Load Labels",
                    "issue": "Label file is missing.",
                    "impact": "This import cannot be applied until labels are fixed.",
                    "next_action": "Load the missing label file.",
                    "severity": "blocked",
                },
                {
                    "target_step": "Match Labels",
                    "issue": "Confirm label placement.",
                    "impact": "This choice affects training readiness.",
                    "next_action": "Review Match Labels.",
                    "severity": "needs_confirmation",
                },
                {
                    "target_step": "Review and Import",
                    "issue": "Saved recipe choices were reapplied.",
                    "impact": "No action needed.",
                    "next_action": "Open the report for details.",
                    "severity": "warning",
                },
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

    action_cards = dialog.review_actions_panel.findChildren(
        QFrame,
        "DataImportActionCard",
    )
    action_text = "\n".join(
        label.text()
        for label in dialog.review_actions_panel.findChildren(QLabel)
        if label.text().strip()
    )

    assert len(action_cards) == 2
    assert "Cannot import yet" in action_text
    assert "Needs your decision" in action_text
    assert "Label source is incomplete" in action_text
    assert "Confirm label placement." not in action_text
    assert "Label placement is ambiguous" in action_text
    assert "Saved recipe choices were reapplied." not in action_text
    assert "Saved recipe choices were reapplied." in _tree_text(dialog.review_tree)
    action_bottom = dialog.review_actions_panel.mapTo(
        dialog,
        dialog.review_actions_panel.rect().bottomLeft(),
    ).y()
    review_top = dialog.import_review_card.mapTo(
        dialog,
        dialog.import_review_card.rect().topLeft(),
    ).y()
    assert action_bottom < review_top
    for summary_label in dialog.import_review_card.findChildren(
        QLabel,
        "DataImportReviewSummary",
    ):
        assert summary_label.height() >= summary_label.heightForWidth(
            max(1, summary_label.width())
        )
    assert not any(
        button.text() == "Fix Match Labels"
        for button in dialog.review_actions_panel.findChildren(QPushButton)
    )
    match_button = next(
        button
        for button in dialog.review_actions_panel.findChildren(QPushButton)
        if button.text() == "Go to Match Labels"
    )
    match_button.click()
    assert dialog._step_titles[dialog.step_stack.currentIndex()] == "Match Labels"
    review_rows = {row["item"]: row for row in dialog._review_import_status_rows()}
    assert review_rows["Label placement"]["status"] == "Needs review"
    assert review_rows["Label placement"]["action"] == "Go to Match Labels"


def test_blocked_import_only_promotes_true_blockers_to_first_layer(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "action_items": [
                {
                    "target_step": "Load Labels",
                    "issue": "Label source is missing.",
                    "impact": "Labels are required before import.",
                    "next_action": "Load labels.",
                    "severity": "blocked",
                },
                {
                    "target_step": "Match Labels",
                    "issue": "Confirm label placement.",
                    "impact": "Review the suggested placement.",
                    "next_action": "Review Match Labels.",
                    "severity": "needs_confirmation",
                },
            ]
        },
        validation_decision={"decision": "blocked"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 760)
    dialog.show()
    _show_step(dialog, "Review and Import")
    qtbot.wait(10)

    action_cards = dialog.review_actions_panel.findChildren(
        QFrame,
        "DataImportActionCard",
    )
    action_text = "\n".join(
        label.text()
        for label in dialog.review_actions_panel.findChildren(QLabel)
        if label.isVisibleTo(dialog) and label.text().strip()
    )

    assert len([card for card in action_cards if card.isVisibleTo(dialog)]) == 1
    assert "Label source is incomplete" in action_text
    assert "Label placement is ambiguous" not in action_text


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


def test_data_interpretation_preview_dialog_skip_labels_keeps_metadata_edits(qtbot):
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

    dialog.skip_labels_btn.click()

    result = dialog.get_result()

    assert result["choices"]["skip_labels"] is True
    assert result["choices"]["metadata_overrides"] == {
        "sub-01_task-mi.fif": {"session": "session-01"}
    }
    assert "class_map" not in result["choices"]
    assert "label_carrier" not in result["choices"]


def test_data_interpretation_preview_dialog_applies_smart_parse_task_and_run(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": "/tmp/source"},
        preview={
            "metadata_preview": [
                {
                    "file": "sub-01_task-mi_run-02_raw.fif",
                    "subject": {"value": None, "decision": "needs_confirmation"},
                    "session": {"value": None, "decision": "needs_confirmation"},
                    "task": {"value": None, "decision": "needs_confirmation"},
                    "run": {"value": None, "decision": "needs_confirmation"},
                },
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    dialog._apply_smart_parse_results(
        {
            "sub-01_task-mi_run-02_raw.fif": (
                "01",
                "-",
                "mi",
                "02",
            )
        }
    )

    result = dialog.get_result()

    assert result["choices"]["metadata_overrides"] == {
        "sub-01_task-mi_run-02_raw.fif": {
            "subject": "01",
            "task": "mi",
            "run": "02",
        }
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
        "Review these choices before applying."
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
            "action_items": [
                {
                    "target_step": "Match Labels",
                    "issue": (
                        "Label carrier pairing is incomplete: 0/2 selected EEG "
                        "files are paired."
                    ),
                    "impact": "Every selected EEG file needs a label carrier.",
                    "next_action": "Go to Label Alignment.",
                    "severity": "blocked",
                }
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

    _show_step(dialog, "Review and Import")
    review_text = _visible_step_text(dialog, "Review and Import")
    assert "Label placement" in review_text
    assert "Needs review" in review_text
    assert "1/2 EEG files paired" in review_text
    assert "1 need label" in review_text
    assert "0/2 selected EEG files are paired" not in review_text
    assert "0/2 EEG files paired" not in review_text
    assert not dialog.apply_button.isEnabled()

    dialog.import_report_toggle.click()
    qtbot.wait(0)
    report_text = _tree_text(dialog.review_tree)
    assert "0/2 selected EEG files are paired" not in report_text

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
    assert "Review any changed files" in details
    assert "Saved recipe choices were reapplied before validation" in details
    _show_step(dialog, "Review and Import")
    rows = {row["item"]: row for row in dialog._review_import_status_rows()}
    assert rows["Recipe"] == {
        "item": "Recipe",
        "status": "Loaded",
        "summary": (
            "A saved recipe was loaded. Save the current import settings "
            "again to keep any changes."
        ),
        "action": "Save recipe",
    }


def test_collapsed_review_keeps_wrapped_recipe_summary_fully_visible(qtbot):
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/A01T.gdf"],
        },
        preview={
            "selected_eeg_files": ["/tmp/source/A01T.gdf"],
            "recipe_reload_summary": {
                "message": (
                    "Saved recipe choices were reapplied before validation: "
                    "metadata overrides, event roles."
                ),
            },
        },
        validation_decision={"decision": "safe"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(700, 700)
    dialog.show()
    _show_step(dialog, "Review and Import")
    qtbot.wait(20)

    summary = dialog._review_summary_value_labels["Recipe"]
    required_height = summary.heightForWidth(summary.width())
    summary_bottom = summary.mapTo(
        dialog.import_review_card,
        summary.rect().bottomLeft(),
    ).y()

    assert required_height > 0
    assert summary.height() >= required_height
    assert summary_bottom <= dialog.import_review_card.contentsRect().bottom()


def test_data_interpretation_preview_dialog_keeps_recipe_trace_out_of_review_actions(
    qtbot,
):
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

    details = _tree_text(dialog.review_tree)

    assert "Source scan" not in details
    assert "Interpretation candidate" not in details
    assert "Metadata decision" not in details
    assert "Metadata override" not in details
    assert "Metadata choices" not in details
    assert "Event use choices" not in details
    assert "Label carrier choices" not in details
    assert "saved in the import recipe" not in details
    assert "scan:scan-1" not in details
    assert "candidate:candidate-1" not in details
    assert "metadata:subject" not in details
    assert "choices:metadata_overrides" not in details


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


def test_recipe_remap_selection_refreshes_every_visible_review_state(qtbot):
    old_eeg = "/tmp/source/old_raw.fif"
    old_events = "/tmp/source/old_events.tsv"
    first_eeg = "/tmp/source/sub-01_raw.fif"
    second_eeg = "/tmp/source/sub-02_raw.fif"
    new_events = "/tmp/source/sub-01_events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [first_eeg, second_eeg],
            "label_carriers": [new_events],
        },
        preview={
            "recipe_reload_summary": {
                "message": "Saved recipe choices require replacement files.",
                "eeg_file_remap_options": [
                    {
                        "saved": old_eeg,
                        "saved_name": "old_raw.fif",
                        "candidates": [
                            {"path": first_eeg, "name": "sub-01_raw.fif"},
                            {"path": second_eeg, "name": "sub-02_raw.fif"},
                        ],
                    }
                ],
                "label_carrier_remap_options": [
                    {
                        "saved": old_events,
                        "saved_name": "old_events.tsv",
                        "candidates": [
                            {"path": new_events, "name": "sub-01_events.tsv"}
                        ],
                    }
                ],
            },
        },
        validation_decision={
            "decision": "blocked",
            "blocked_reasons": [
                "Selected EEG file(s) were not found in the current scan: old_raw.fif.",
                "Saved label/event carrier(s) were not found in the current scan: old_events.tsv.",
            ],
        },
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 820)
    dialog.show()
    _show_step(dialog, "Review and Import")
    qtbot.wait(10)

    eeg_selector = dialog._eeg_file_remap_widgets[old_eeg]
    assert not dialog.apply_button.isEnabled()

    eeg_selector.setCurrentIndex(eeg_selector.findData(second_eeg))
    qtbot.wait(20)

    review_rows = {row["item"]: row for row in dialog._review_import_status_rows()}
    action_text = "\n".join(
        label.text()
        for label in dialog.review_actions_panel.findChildren(QLabel)
        if label.text().strip()
    )
    report_text = _tree_text(dialog.review_tree)

    assert dialog.apply_button.isEnabled()
    assert dialog.decision_label.text() == "Ready to apply remap."
    assert review_rows["Recipe"]["status"] == "Not saved"
    assert review_rows["Recipe"]["action"] == "Save recipe"
    assert "Resolve blocking items" not in review_rows["Recipe"]["summary"]
    assert "Cannot import yet" not in action_text
    assert not dialog.review_actions_panel.isVisibleTo(dialog)
    assert "Replacement selected" in report_text
    assert "were not found in the current scan" not in report_text
    assert "Blocking issues: None" in dialog._import_report_summary_text()
    assert "were not found in the current scan" not in (
        dialog._import_report_summary_text()
    )


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


def _visible_source_rows(dialog) -> list[QFrame]:
    panel = dialog.step_stack.widget(dialog._step_titles.index("Load Labels"))
    return [
        row
        for row in dialog.label_source_rows_widget.findChildren(
            QFrame,
            "DataImportSourceRow",
        )
        if row.isVisibleTo(panel)
    ]


def _visible_source_scope_rows(dialog) -> list[QFrame]:
    panel = dialog.step_stack.widget(dialog._step_titles.index("Load Labels"))
    return [
        row
        for row in dialog.label_source_rows_widget.findChildren(
            QFrame,
            "DataImportSourceScopeRow",
        )
        if row.isVisibleTo(panel)
    ]


def _source_row_button_texts(dialog) -> list[str]:
    result: list[str] = []
    for row in _visible_source_rows(dialog):
        buttons = row.findChildren(QPushButton)
        assert len(buttons) == 1
        result.append(buttons[0].text())
    return result


def _source_scope_button_texts(dialog) -> list[str]:
    result: list[str] = []
    for row in _visible_source_scope_rows(dialog):
        buttons = row.findChildren(QPushButton)
        assert len(buttons) == 1
        result.append(buttons[0].text())
    return result


def _source_row_titles(dialog) -> list[str]:
    result: list[str] = []
    for row in _visible_source_rows(dialog):
        labels = [label.text() for label in row.findChildren(QLabel)]
        assert labels
        result.append(labels[0])
    return result


def _source_scope_texts(dialog) -> list[str]:
    result: list[str] = []
    for row in _visible_source_scope_rows(dialog):
        labels = [label.text() for label in row.findChildren(QLabel)]
        assert labels
        result.append(labels[0])
    return result


def _click_source_row_button(dialog, title: str, button_text: str) -> None:
    for row in _visible_source_rows(dialog):
        labels = [label.text() for label in row.findChildren(QLabel)]
        if title not in labels:
            continue
        for button in row.findChildren(QPushButton):
            if button.text() == button_text:
                button.click()
                return
    raise AssertionError(f"No {button_text!r} button found for source row {title!r}")


def _click_source_scope_button(dialog, text: str) -> None:
    for row in _visible_source_scope_rows(dialog):
        labels = [label.text() for label in row.findChildren(QLabel)]
        if text not in labels:
            continue
        buttons = row.findChildren(QPushButton)
        assert len(buttons) == 1
        buttons[0].click()
        return
    raise AssertionError(f"No source scope button found for {text!r}")


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
