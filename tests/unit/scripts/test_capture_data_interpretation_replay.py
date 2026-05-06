from __future__ import annotations

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
    build_replay_geometry_review,
    build_visible_text_review,
    dataset_sidebar_state,
    source_event_field_matches,
    table_state,
    tree_rows,
    tree_state,
)
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)


def test_apply_replay_review_choices_updates_event_role_selector(qtbot) -> None:
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

    label_item = dialog.label_carrier_tree.topLevelItem(0)
    assert label_item is not None
    target_selector = dialog.label_carrier_tree.itemWidget(label_item, 1)
    assert isinstance(target_selector, QComboBox)
    assert target_selector.currentData() == "sub-01_task-mi_run-2_raw.fif"
    assert (
        dialog.get_result()["choices"]["label_carrier_choices"][
            "/tmp/source/events.tsv"
        ]["target_file"]
        == "sub-01_task-mi_run-2_raw.fif"
    )
    assert role_selector.currentData() == "class cue"
    assert ["Trial type", "event role", "Class cue"] in tree_rows(dialog.event_tree)
    assert dialog.get_result()["choices"]["event_roles"] == {"trial_type": "class cue"}


def test_dataset_sidebar_state_records_button_tooltips(qtbot) -> None:
    class SidebarStub:
        pass

    sidebar = SidebarStub()
    smart_parse_btn: QPushButton | None = None
    for name, text in {
        "import_btn": "Interpret EEG Source",
        "import_folder_btn": "Interpret Folder",
        "reload_recipe_btn": "Reload Import Recipe",
        "import_label_btn": "Add Labels to Loaded Data",
        "smart_parse_btn": "Smart Parse Metadata",
        "chan_select_btn": "Channel Selection",
        "clear_btn": "Clear Dataset",
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

    assert state["import_source"]["text"] == "Interpret EEG Source"
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
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)
    dialog.resize(760, 720)
    dialog.show()
    qtbot.wait(0)
    dialog._fit_all_tree_columns_to_viewport()

    state = tree_state(dialog.review_tree)

    assert state["headers"] == ["Item", "Status", "What it means"]
    assert state["rows"]
    assert state["resize_modes"] == ["Interactive", "Interactive", "Interactive"]
    assert state["stretch_last_section"] is False
    assert abs(state["header_length"] - state["viewport_width"]) <= 2
    assert state["horizontal_scrollbar_max"] == 0
    assert state["vertical_scrollbar_max"] >= 0
    assert state["partial_visible_rows"] == []
    assert state["text_elide_mode"] == "ElideRight"
    assert state["alternating_row_colors"] is True
    flat_rows = " ".join(" ".join(row) for row in state["rows"])
    assert "Source scan" in flat_rows
    assert "Interpretation candidate" in flat_rows
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
    dialog._fit_all_tree_columns_to_viewport()

    review = build_replay_geometry_review(
        {
            "dialog": {
                "tables": {
                    "metadata": tree_state(dialog.file_tree),
                    "label_carriers": tree_state(dialog.label_carrier_tree),
                    "events": tree_state(dialog.event_tree),
                    "review_summary": tree_state(dialog.review_tree),
                },
            },
        },
    )

    assert review["passed"] is True
    assert review["checked_widgets"] == 4
    assert {row["widget"] for row in review["rows"]} == {
        "dialog.tables.metadata",
        "dialog.tables.label_carriers",
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


def table_item(text: str) -> QTableWidgetItem:
    return QTableWidgetItem(text)
