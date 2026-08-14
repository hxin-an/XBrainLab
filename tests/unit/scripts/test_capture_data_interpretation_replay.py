from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from scripts.dev.capture_data_interpretation_replay import (
    apply_replay_review_choices,
    artifact_file_manifest,
    build_replay_geometry_review,
    build_visible_text_review,
    dataset_sidebar_state,
    ensure_confirmed_apply_succeeded,
    pairing_rows,
    pairing_rows_state_for_step,
    request_window_close,
    source_event_field_matches,
    source_file_manifest,
    source_fingerprint,
    table_state,
    tree_rows,
    tree_state,
)
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)


def test_replay_fingerprint_covers_current_data_import_presentation_source() -> None:
    source_files = source_file_manifest()
    paths = {record["path"] for record in source_files}

    assert "scripts/dev/capture_data_interpretation_replay.py" in paths
    assert "XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py" in paths
    assert "XBrainLab/ui/dialogs/dataset/event_value_decision_editor.py" in paths
    assert "XBrainLab/ui/dialogs/dataset/review_import_step.py" in paths
    assert "XBrainLab/ui/components/info_panel.py" in paths
    assert "XBrainLab/ui/components/info_panel_service.py" in paths
    assert all(record["sha256"] for record in source_files)
    assert source_fingerprint(source_files) != source_fingerprint(
        [{"path": "different.py", "sha256": "0" * 64}]
    )


def test_artifact_file_manifest_hashes_every_replay_screenshot(tmp_path: Path) -> None:
    screenshots = {
        "preview": tmp_path / "preview.png",
        "remap": tmp_path / "remap.png",
        "applied": tmp_path / "applied.png",
    }
    for name, path in screenshots.items():
        path.write_bytes(f"{name}-content".encode())

    manifest = artifact_file_manifest(screenshots, artifact_root=tmp_path)

    assert set(manifest) == set(screenshots)
    assert all(record["relative_path"].endswith(".png") for record in manifest.values())
    assert all(len(record["sha256"]) == 64 for record in manifest.values())
    assert all(record["byte_size"] > 0 for record in manifest.values())


def test_apply_replay_review_choices_only_changes_visible_matching_controls(
    qtbot,
) -> None:
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
            "selected_eeg_files": [
                "/tmp/source/sub-01_task-mi_run-2_raw.fif",
            ],
            "event_roles": {"trial_type": "class label candidate"},
        },
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    role_item = None
    for index in range(dialog.event_tree.topLevelItemCount()):
        item = dialog.event_tree.topLevelItem(index)
        if item is not None and source_event_field_matches(item, "trial_type"):
            role_item = item
            break
    assert role_item is not None
    assert role_item.text(0) == "Trial type"
    role_selector = dialog.event_tree.itemWidget(role_item, 2)
    assert isinstance(role_selector, QComboBox)
    assert role_selector.currentData() == "class label candidate"

    apply_replay_review_choices(dialog)

    visible_selector = dialog._eeg_label_widgets["sub-01_task-mi_run-2_raw.fif"]
    assert isinstance(visible_selector, QComboBox)
    assert visible_selector.currentData() == "/tmp/source/events.tsv"
    assert pairing_rows(dialog) == [
        ["sub-01_task-mi_run-2_raw.fif", "events.tsv", "Needs setup"],
    ]
    label_choice = dialog.get_result()["choices"]["label_carrier_choices"][
        "/tmp/source/events.tsv"
    ]
    assert "target_file" not in label_choice
    assert dialog.get_result()["choices"].get("selected_eeg_files") is None
    replay_choices = apply_replay_review_choices(dialog)
    assert replay_choices["selected_eeg_files"] == [
        "/tmp/source/sub-01_task-mi_run-2_raw.fif"
    ]
    assert role_selector.currentData() == "class label candidate"
    assert ["Trial type", "event use", "Class label candidate"] in tree_rows(
        dialog.event_tree
    )
    assert dialog.get_result()["choices"].get("event_roles", {}) == {}


def test_apply_replay_review_choices_completes_observed_label_values(qtbot) -> None:
    decisions = {
        value: {
            "role": "unknown",
            "keep_event": None,
            "use_as_class": None,
            "suggested_name": name,
            "decision": "unresolved",
            "count": 3,
        }
        for value, name in (("left", "Left hand"), ("right", "Right hand"))
    }
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_run-2_raw.fif"],
            "label_carriers": ["/tmp/source/events.tsv"],
        },
        preview={
            "selected_eeg_files": ["/tmp/source/sub-01_task-mi_run-2_raw.fif"],
            "label_carrier_preview": [
                {
                    "path": "/tmp/source/events.tsv",
                    "name": "events.tsv",
                    "format": "TSV",
                    "selected_label_field": "trial_type",
                    "role": "class cue labels",
                    "value_decisions": decisions,
                    "unresolved_values": ["left", "right"],
                }
            ],
        },
        validation_decision={"decision": "blocked"},
    )
    qtbot.addWidget(dialog)

    replay_choices = apply_replay_review_choices(dialog)

    value_decisions = replay_choices["label_carrier_choices"]["/tmp/source/events.tsv"][
        "value_decisions"
    ]
    assert {
        value: {
            "role": payload["role"],
            "keep_event": payload["keep_event"],
            "use_as_class": payload["use_as_class"],
            "class_name": payload["class_name"],
        }
        for value, payload in value_decisions.items()
    } == {
        "left": {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": "Left hand",
        },
        "right": {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": "Right hand",
        },
    }


def test_confirmed_apply_failure_fails_the_replay_validator() -> None:
    try:
        ensure_confirmed_apply_succeeded(
            {
                "ok": False,
                "message": "Label carrier pairing is incomplete.",
                "error": {"code": "validation_failed"},
            }
        )
    except RuntimeError as exc:
        assert "Confirmed apply failed" in str(exc)
        assert "Label carrier pairing is incomplete" in str(exc)
    else:
        raise AssertionError("A failed confirmed apply must fail the replay.")


def test_confirmed_apply_success_passes_the_replay_validator() -> None:
    ensure_confirmed_apply_succeeded(
        {
            "ok": True,
            "message": "Interpretation applied.",
        }
    )
    ensure_confirmed_apply_succeeded(
        {
            "status": "ok",
            "message": "Interpretation applied.",
        }
    )


def test_dataset_sidebar_state_records_button_tooltips(qtbot) -> None:
    class SidebarStub:
        pass

    sidebar = SidebarStub()
    smart_parse_btn: QPushButton | None = None
    for name, text in {
        "import_btn": "Import file",
        "import_folder_btn": "Import folder",
        "import_bids_btn": "Import BIDS folder",
        "reload_recipe_btn": "Reload Import Recipe",
        "import_label_btn": "Add labels",
        "smart_parse_btn": "Smart Parse Metadata",
        "chan_select_btn": "Channel Selection",
    }.items():
        button = QPushButton(text)
        qtbot.addWidget(button)
        setattr(sidebar, name, button)
        if name == "smart_parse_btn":
            smart_parse_btn = button

    assert smart_parse_btn is not None
    smart_parse_btn.setEnabled(False)
    smart_parse_btn.setToolTip("Load raw data before applying smart parse.")

    state = dataset_sidebar_state(sidebar)

    assert state["import_source"]["text"] == "Import file"
    assert state["import_bids"]["text"] == "Import BIDS folder"
    assert state["smart_parse"] == {
        "text": "Smart Parse Metadata",
        "enabled": False,
        "tooltip": "Load raw data before applying smart parse.",
    }


def test_table_state_records_rows_and_resize_modes(qtbot) -> None:
    table = QTableWidget(2, 3)
    qtbot.addWidget(table)
    table.setHorizontalHeaderLabels(["File", "Subject", "Events"])
    header = table.horizontalHeader()
    assert header is not None
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    table.setItem(0, 0, table_item("sub-01.fif"))
    table.setItem(0, 1, table_item("S01"))
    table.setItem(0, 2, table_item("Events (6)"))
    table.setItem(1, 0, table_item("sub-02.fif"))
    table.setItem(1, 1, table_item("S02"))
    table.setItem(1, 2, table_item("Labels (4)"))

    state = table_state(table)

    assert state["headers"] == ["File", "Subject", "Events"]
    assert state["rows"] == [
        ["sub-01.fif", "S01", "Events (6)"],
        ["sub-02.fif", "S02", "Labels (4)"],
    ]
    assert state["resize_modes"] == [
        "Stretch",
        "ResizeToContents",
        "ResizeToContents",
    ]
    assert state["stretch_last_section"] is False
    assert state["header_length"] > 0
    assert state["viewport_width"] > 0


def test_table_state_records_main_panel_fill_gap(qtbot) -> None:
    panel = QWidget()
    qtbot.addWidget(panel)
    layout = QHBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    table = QTableWidget(1, 2, panel)
    sidebar = QWidget(panel)
    sidebar.setFixedWidth(160)
    layout.addWidget(table, stretch=1)
    layout.addWidget(sidebar, stretch=0)
    panel.resize(760, 360)
    panel.show()
    qtbot.wait(0)

    state = table_state(table, panel=panel, right_boundary=sidebar)

    assert state["panel_width"] == panel.width()
    assert state["right_boundary_x"] == sidebar.x()
    assert abs(state["right_gap_to_boundary"]) <= 2
    assert state["widget_width"] > state["viewport_width"]


def test_tree_state_records_rows_and_fit_geometry(qtbot) -> None:
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
        validation_decision={
            "decision": "needs_confirmation",
            "action_items": [
                {
                    "target_step": "Review and Import",
                    "issue": "Import assumptions need review",
                    "impact": "Review the complete import report before applying.",
                    "next_action": "Review the report.",
                    "severity": "needs_confirmation",
                }
            ],
        },
    )
    qtbot.addWidget(dialog)
    dialog.resize(760, 720)
    dialog.show()
    qtbot.wait(0)
    _show_dialog_step(dialog, "Review and Import", qtbot)
    dialog._fit_all_tree_columns_to_viewport()

    state = tree_state(dialog.review_tree)

    assert state["headers"] == ["Target step", "Issue", "Impact", "Next action"]
    assert state["rows"]
    assert state["resize_modes"] == [
        "Interactive",
        "Interactive",
        "Interactive",
        "Interactive",
    ]
    assert state["stretch_last_section"] is False
    assert abs(state["header_length"] - state["viewport_width"]) <= 2
    assert state["horizontal_scrollbar_max"] == 0
    assert state["vertical_scrollbar_max"] >= 0
    assert state["partial_visible_rows"] == []
    assert state["text_elide_mode"] == "ElideNone"
    assert state["alternating_row_colors"] is True
    flat_rows = " ".join(" ".join(row) for row in state["rows"])
    assert "Source scan" not in flat_rows
    assert "Interpretation candidate" not in flat_rows
    assert "scan:scan-1" not in flat_rows
    assert "candidate:candidate-1" not in flat_rows


def test_visible_text_review_flags_raw_recipe_trace_tokens() -> None:
    review = build_visible_text_review(
        {
            "dialog": {
                "review_summary_rows": [
                    ["Recipe trace", "Saved", "scan:scan-1"],
                    ["Recipe trace", "Saved", "choices:metadata_overrides"],
                ],
            },
        },
    )

    assert review["passed"] is False
    assert review["findings"]
    assert review["findings"][0]["trace_tokens"] == ["scan:scan-1"]


def test_visible_text_review_allows_humanized_recipe_trace_rows() -> None:
    review = build_visible_text_review(
        {
            "dialog": {
                "review_summary_rows": [
                    ["Source scan", "Recorded", "Source scan is saved in the recipe."],
                    ["Metadata choices", "Recorded", "Metadata choices were recorded."],
                ],
            },
        },
    )

    assert review["passed"] is True


def test_replay_geometry_review_checks_all_wizard_tables(qtbot) -> None:
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
    dialog.resize(900, 740)
    dialog.show()
    qtbot.wait(0)

    review = build_replay_geometry_review(
        {
            "dialog": {
                "tables": {
                    "metadata": _tree_state_for_step(
                        dialog,
                        "Review Metadata",
                        dialog.file_tree,
                        qtbot,
                    ),
                    "file_pairing": pairing_rows_state_for_step(
                        dialog,
                        "Match Labels",
                        qtbot,
                    ),
                    "events": _tree_state_for_step(
                        dialog,
                        "Match Labels",
                        dialog.event_tree,
                        qtbot,
                    ),
                    "review_summary": _tree_state_for_step(
                        dialog,
                        "Review and Import",
                        dialog.review_tree,
                        qtbot,
                    ),
                },
            },
        },
    )

    assert review["passed"] is True
    assert review["checked_widgets"] == 4
    assert {row["widget"] for row in review["rows"]} == {
        "dialog.tables.metadata",
        "dialog.tables.file_pairing",
        "dialog.tables.events",
        "dialog.tables.review_summary",
    }


def test_replay_geometry_review_flags_underfilled_tree() -> None:
    review = build_replay_geometry_review(
        {
            "dialog": {
                "tables": {
                    "label_carriers": {
                        "headers": ["File", "Role"],
                        "rows": [["events.tsv", "Class cue"]],
                        "header_length": 500,
                        "viewport_width": 760,
                        "horizontal_scrollbar_max": 0,
                        "partial_visible_rows": [],
                    },
                },
            },
        },
    )

    assert review["passed"] is False
    assert review["findings"][0]["widget"] == "dialog.tables.label_carriers"
    assert review["findings"][0]["fills_viewport"] is False


def test_capture_scripts_never_use_hidden_label_tree_as_ui_evidence() -> None:
    root = Path(__file__).resolve().parents[3]
    for relative_path in (
        "scripts/dev/capture_data_interpretation_replay.py",
        "scripts/dev/capture_human_like_product_walkthrough.py",
    ):
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "label_carrier_tree" not in source, relative_path


def test_request_window_close_waits_for_deferred_product_shutdown(qtbot) -> None:
    class DeferredCloseWidget(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.close_attempts = 0

        def closeEvent(self, event) -> None:
            self.close_attempts += 1
            if self.close_attempts == 1:
                event.ignore()
                QTimer.singleShot(10, self.close)
                return
            super().closeEvent(event)

    widget = DeferredCloseWidget()
    qtbot.addWidget(widget)
    widget.show()
    closed: list[bool] = []
    timed_out: list[bool] = []

    request_window_close(
        widget,
        on_closed=lambda: closed.append(True),
        on_timeout=lambda: timed_out.append(True),
        timeout_ms=500,
    )
    qtbot.waitUntil(lambda: bool(closed), timeout=1_000)

    assert widget.close_attempts == 2
    assert timed_out == []


def table_item(text: str) -> QTableWidgetItem:
    return QTableWidgetItem(text)


def _tree_state_for_step(dialog, step_title: str, tree, qtbot) -> dict:
    _show_dialog_step(dialog, step_title, qtbot)
    dialog._fit_all_tree_columns_to_viewport()
    return tree_state(tree)


def _show_dialog_step(dialog, step_title: str, qtbot) -> None:
    dialog._go_to_step(dialog._step_titles.index(step_title))
    qtbot.wait(0)
