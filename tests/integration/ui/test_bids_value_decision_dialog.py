"""Low-mock BIDS value decisions from Qt dialog through ApplicationService."""

from __future__ import annotations

import json
from pathlib import Path

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ReviewInterpretationCommand,
    ValidateInterpretationCommand,
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


def test_bids_value_decisions_recheck_and_apply(
    qtbot,
    tmp_path: Path,
) -> None:
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
    dialog.show()
    qtbot.wait(0)

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
        use="ignore",
    )
    assert dialog.next_button.isEnabled()
    assert dialog.next_button.text() == "Next: Review and Import"

    dialog.next_button.click()
    qtbot.wait(0)
    assert dialog.result() == dialog.DialogCode.Accepted
    stale_result = dialog.get_result()
    assert stale_result["resume_step"] == "Review and Import"

    reviewed_preview = service.execute(
        PreviewInterpretationCommand(choices=stale_result["choices"])
    )
    assert reviewed_preview.ok, reviewed_preview.message
    reviewed_validation = service.execute(ValidateInterpretationCommand())
    assert reviewed_validation.ok, reviewed_validation.message
    assert reviewed_validation.diagnostics["validation_decision"]["decision"] == "safe"
    assert reviewed_validation.diagnostics["validation_decision"]["action_items"] == []

    fresh_dialog = DataInterpretationPreviewDialog(
        scan_result=diagnostics["scan_result"],
        preview=reviewed_preview.diagnostics["preview"],
        validation_decision=reviewed_validation.diagnostics["validation_decision"],
        initial_step="Review and Import",
        choices=stale_result["choices"],
    )
    qtbot.addWidget(fresh_dialog)
    fresh_dialog.show()
    qtbot.wait(0)
    assert fresh_dialog.step_stack.currentIndex() == 4
    assert fresh_dialog.decision == "safe"
    assert fresh_dialog.apply_button.isEnabled()
    before_confirm = service.get_view_publication().state
    assert before_confirm.raw.count == 0
    assert before_confirm.interpretation.has_applied_interpretation is False
    fresh_dialog.apply_button.click()
    qtbot.wait(0)
    assert fresh_dialog.result() == fresh_dialog.DialogCode.Accepted
    fresh_result = fresh_dialog.get_result()
    assert fresh_result["confirmed"] is True

    applied = service.execute(
        ApplyInterpretationCommand(confirmed=fresh_result["confirmed"])
    )
    assert applied.ok
    assert applied.state.raw.loaded
    assert applied.state.raw.count == 1
    assert applied.state.interpretation.has_applied_interpretation is True
    assert len(service.study.loaded_data_list) == 1
    assert applied.state.interpretation.class_map == {"show_stimulus": "Stimulus"}
    loaded = service.study.loaded_data_list[0]
    descriptions = set(loaded.get_mne().annotations.description)
    events, event_id = loaded.get_event_list()

    assert {"Stimulus", "system/start_experiment"}.issubset(descriptions)
    assert set(event_id) == {"Stimulus"}
    assert len(events) == 1
