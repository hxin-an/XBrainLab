from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from scripts.dev.capture_data_interpretation_replay import (
    apply_replay_review_choices,
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
