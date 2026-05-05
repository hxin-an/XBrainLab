from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from scripts.dev.capture_data_interpretation_replay import (
    apply_replay_review_choices,
    dataset_sidebar_state,
    table_state,
    tree_rows,
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
        if item is not None and item.text(0) == "trial_type":
            role_item = item
            break
    assert role_item is not None
    role_selector = dialog.event_tree.itemWidget(role_item, 2)
    assert isinstance(role_selector, QComboBox)
    assert role_selector.currentData() == "class label candidate"

    apply_replay_review_choices(dialog)

    assert role_selector.currentData() == "class cue"
    assert ["trial_type", "event role", "Class cue"] in tree_rows(dialog.event_tree)
    assert dialog.get_result()["choices"]["event_roles"] == {"trial_type": "class cue"}


def test_dataset_sidebar_state_records_button_tooltips(qtbot) -> None:
    class SidebarStub:
        pass

    sidebar = SidebarStub()
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

    sidebar.smart_parse_btn.setEnabled(False)
    sidebar.smart_parse_btn.setToolTip("Load raw data before applying smart parse.")

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


def table_item(text: str) -> QTableWidgetItem:
    return QTableWidgetItem(text)
