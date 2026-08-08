"""Low-mock BIDS value decisions from Qt dialog through ApplicationService."""

from __future__ import annotations

import json
from pathlib import Path

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ReviewInterpretationCommand,
)
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)


def _write_value_decision_bids_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "bids-value-decisions"
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "value-decisions", "BIDSVersion": "1.11.1"}),
        encoding="utf-8",
    )
    stem = "sub-01_task-oddball_run-01"
    raw = mne.io.RawArray(
        np.zeros((2, 400)),
        mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
        verbose="ERROR",
    )
    raw.save(eeg_dir / f"{stem}_eeg.fif", overwrite=True, verbose="ERROR")
    (eeg_dir / f"{stem}_events.tsv").write_text(
        "onset\tduration\ttrial_type\n"
        "1.0\t0.0\tshow_stimulus\n"
        "2.0\t0.0\tstart_experiment\n",
        encoding="utf-8",
    )
    (eeg_dir / f"{stem}_events.json").write_text(
        json.dumps(
            {
                "trial_type": {
                    "Description": "Event category",
                    "Levels": {
                        "show_stimulus": "Stimulus presentation",
                        "start_experiment": "Experiment start marker",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return root.resolve()


def test_bids_value_decisions_recheck_and_apply(qtbot, tmp_path: Path) -> None:
    root = _write_value_decision_bids_fixture(tmp_path)
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
    assert dialog.next_button.isEnabled()
    assert dialog.next_button.text() == "Next: Review and Import"

    dialog.next_button.click()
    qtbot.wait(0)
    review_rows = {row["item"]: row for row in dialog._review_import_status_rows()}

    assert dialog.apply_button.isEnabled()
    assert dialog.apply_button.isVisibleTo(dialog)
    assert dialog.decision_label.text() == "Ready to recheck and import."
    assert not dialog.review_actions_panel.isVisible()
    assert review_rows["Recipe"]["status"] == "Not saved"
    assert (
        review_rows["Recipe"]["summary"]
        == "Save the current data import and label mapping settings for reuse."
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
    assert set(event_id) == {"Stimulus"}
    assert len(events) == 1
