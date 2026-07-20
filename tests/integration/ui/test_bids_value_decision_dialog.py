"""Low-mock BIDS value decisions from Qt dialog through ApplicationService."""

from __future__ import annotations

from pathlib import Path

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ReviewInterpretationCommand,
)
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)


def test_public_bids_value_decisions_recheck_and_apply(qtbot) -> None:
    root = Path("tests/fixtures/data/public/mne-bids-tiny-eeg").resolve()
    service = ApplicationService()
    initial = service.execute(
        ReviewInterpretationCommand(
            source_path=str(root),
            source_hint="bids",
        )
    )
    diagnostics = initial.diagnostics
    dialog = DataInterpretationPreviewDialog(
        scan_result=diagnostics["scan_result"],
        preview=diagnostics["preview"],
        validation_decision=diagnostics["validation_decision"],
        initial_step="Match Labels",
    )
    qtbot.addWidget(dialog)

    assert diagnostics["validation_decision"]["decision"] == "blocked"
    assert dialog.event_value_editor is not None
    assert dialog.event_value_editor.unresolved_values() == [
        "show_stimulus",
        "start_experiment",
    ]

    dialog.event_value_editor.set_value_decision(
        "show_stimulus",
        role="stimulus",
        use="class",
        class_name="Stimulus",
    )
    dialog.event_value_editor.set_value_decision(
        "start_experiment",
        role="system",
        use="event",
    )
    review_rows = {row["item"]: row for row in dialog._review_import_status_rows()}

    assert dialog.apply_button.isEnabled()
    assert dialog.decision_label.text() == "Ready to recheck and import."
    assert not dialog.review_actions_panel.isVisible()
    assert review_rows["Recipe"]["status"] == "Not saved"
    assert (
        review_rows["Recipe"]["summary"]
        == "Save current import and label mapping settings."
    )
    result = dialog.get_result()

    assert result["confirmed"] is True
    reviewed = service.execute(
        ReviewInterpretationCommand(
            source_path=str(root),
            source_hint="bids",
            choices=result["choices"],
        )
    )
    assert reviewed.ok
    assert reviewed.diagnostics["validation_decision"]["decision"] == "safe"
    assert reviewed.diagnostics["validation_decision"]["action_items"] == []

    applied = service.execute(ApplyInterpretationCommand(confirmed=result["confirmed"]))
    assert applied.ok
    assert applied.state.raw.loaded
    loaded = service.study.loaded_data_list[0]
    descriptions = set(loaded.get_mne().annotations.description)
    events, event_id = loaded.get_event_list()

    assert {"Stimulus", "system/start_experiment"}.issubset(descriptions)
    assert "Comment/ControlBox is not connected via USB" in descriptions
    assert set(event_id) == {"Stimulus"}
    assert len(events) == 1
