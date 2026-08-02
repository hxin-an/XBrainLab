"""Non-mocked external event-value workflow through ApplicationService."""

from __future__ import annotations

import json
from pathlib import Path

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)


def test_save_reload_apply_epoch_preserves_event_value_truth(tmp_path: Path) -> None:
    bids_root, eeg, events = _bids_fixture(tmp_path)
    recipe_path = tmp_path / "mixed-events-recipe.json"
    choices = {
        "selected_eeg_files": [str(eeg)],
        "label_carrier_choices": {
            str(events): {
                "label_field": "trial_type",
                "anchor": "onset",
                "duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
                "granularity": "event",
                "value_decisions": {
                    "left": _value_choice("stimulus", True, "Left hand"),
                    "right": _value_choice("stimulus", True, "Right hand"),
                    "button_press": _value_choice("response", False),
                    "bad_segment": _value_choice("artifact", False, keep_event=False),
                    "boundary": _value_choice("boundary", False),
                },
            }
        },
    }

    writer = ApplicationService()
    assert writer.execute(
        ScanSourceCommand(source_path=str(bids_root), source_hint="bids")
    ).ok
    preview = writer.execute(PreviewInterpretationCommand(choices=choices))
    assert preview.ok
    validated = writer.execute(ValidateInterpretationCommand())
    assert validated.ok
    assert validated.diagnostics["validation_decision"]["decision"] == "safe"
    action_items = validated.diagnostics["validation_decision"]["action_items"]
    assert all(item["severity"] != "blocking" for item in action_items)
    applied = writer.execute(ApplyInterpretationCommand(confirmed=True))
    assert applied.ok
    assert applied.diagnostics["channels_apply"][0]["bad_channels"] == ["C4"]
    writer_raw = writer.study.loaded_data_list[0]
    assert writer_raw.get_mne().info["bads"] == ["C4"]
    assert set(writer_raw.get_mne().annotations.description) == {
        "Left hand",
        "Right hand",
        "response/button_press",
        "BAD_boundary/boundary",
    }
    saved = writer.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    assert saved.ok
    saved_decisions = saved.diagnostics["recipe"]["label_carrier_plan"][0][
        "value_decisions"
    ]
    assert saved_decisions["boundary"]["role"] == "boundary"
    assert (
        saved_decisions
        == preview.diagnostics["candidate"]["label_carrier_plan"][0]["value_decisions"]
    )

    reader = ApplicationService()
    reloaded = reader.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    assert reloaded.ok
    reloaded_plan = reloaded.diagnostics["candidate"]["label_carrier_plan"][0]
    assert reloaded_plan["value_decisions"] == saved_decisions
    assert reloaded_plan["value_decisions"]["boundary"]["role"] == "boundary"
    reapplied = reader.execute(ApplyInterpretationCommand(confirmed=True))
    assert reapplied.ok
    reader_raw = reader.study.loaded_data_list[0]
    assert reader_raw.get_mne().info["bads"] == ["C4"]
    assert "BAD_boundary/boundary" in set(reader_raw.get_mne().annotations.description)

    preprocessed = reader.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        )
    )
    assert preprocessed.ok
    epoch = reader.execute(CreateEpochCommand(t_min=0.0, t_max=0.2))
    assert epoch.ok
    assert set(epoch.state.epoch.event_ids or {}) == {"Left hand", "Right hand"}
    handoff = epoch.state.interpretation.epoch_handoff
    assert handoff["default_epoch_events"] == ["Left hand", "Right hand"]
    assert {row["raw_value"] for row in handoff["class_targets"]} == {
        "left",
        "right",
    }
    assert {
        row["raw_value"]
        for row in handoff["event_catalog"]
        if row["keep_event"] is True and row["use_as_class"] is False
    } == {"button_press", "boundary"}

    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "0.5\t0\tleft\t1\n"
        "1.5\t0\tnew_value\t2\n"
        "2.5\t0\tbutton_press\t3\n"
        "3.5\t0.2\tbad_segment\t4\n"
        "4.5\t0\tboundary\t5\n",
        encoding="utf-8",
    )
    changed = ApplicationService().execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    assert changed.ok
    changed_candidate = changed.diagnostics["candidate"]
    assert changed.diagnostics["validation_decision"]["decision"] == "blocked"
    assert changed_candidate["label_carrier_plan"][0]["unresolved_values"] == [
        "new_value"
    ]
    assert any("right" in warning for warning in changed_candidate["warnings"])


def test_confirmed_apply_cannot_override_unresolved_bids_values(
    tmp_path: Path,
) -> None:
    bids_root, eeg, events = _bids_fixture(tmp_path)
    service = ApplicationService()
    assert service.execute(
        ScanSourceCommand(source_path=str(bids_root), source_hint="bids")
    ).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg)],
                "class_map": {
                    "left": "Left hand",
                    "right": "Right hand",
                    "button_press": "Button",
                    "bad_segment": "Bad",
                    "boundary": "Boundary",
                },
                "label_carrier_choices": {
                    str(events): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                    }
                },
            }
        )
    )
    validation = service.execute(ValidateInterpretationCommand())
    apply = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert preview.ok
    assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
    assert apply.ok is False
    assert "selected event values have no complete semantic decision" in str(
        apply.error_message
    )
    assert apply.state.raw.loaded is False


def test_channels_name_mismatch_fails_apply_and_rolls_back(tmp_path: Path) -> None:
    bids_root, eeg, events = _bids_fixture(tmp_path)
    events.with_name("sub-01_task-mi_channels.tsv").write_text(
        "name\tstatus\nC3\tgood\nPO10\tbad\n",
        encoding="utf-8",
    )
    service = ApplicationService()
    assert service.execute(
        ScanSourceCommand(source_path=str(bids_root), source_hint="bids")
    ).ok
    assert service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg)],
                "label_carrier_choices": {
                    str(events): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": {
                            "left": _value_choice("stimulus", True, "Left hand"),
                            "right": _value_choice("stimulus", True, "Right hand"),
                            "button_press": _value_choice("response", False),
                            "bad_segment": _value_choice(
                                "artifact", False, keep_event=False
                            ),
                            "boundary": _value_choice("boundary", False),
                        },
                    }
                },
            }
        )
    ).ok
    assert service.execute(ValidateInterpretationCommand()).ok

    apply = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply.ok is False
    assert "do not match" in str(apply.error_message)
    assert apply.state.raw.loaded is False


def _bids_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "bids"
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "mixed", "BIDSVersion": "1.9.0"}),
        encoding="utf-8",
    )
    eeg = eeg_dir / "sub-01_task-mi_eeg.fif"
    raw = mne.io.RawArray(
        np.zeros((2, 1000)),
        mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
        verbose=False,
    )
    raw.save(eeg, overwrite=True, verbose=False)
    events = eeg_dir / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "0.5\t0\tleft\t1\n"
        "1.5\t0\tright\t2\n"
        "2.5\t0\tbutton_press\t3\n"
        "3.5\t0.2\tbad_segment\t4\n"
        "4.5\t0\tboundary\t5\n",
        encoding="utf-8",
    )
    (eeg_dir / "sub-01_task-mi_events.json").write_text(
        json.dumps(
            {
                "trial_type": {
                    "Levels": {
                        "left": "Left hand",
                        "right": "Right hand",
                        "button_press": "Button press",
                        "bad_segment": "Bad segment",
                        "boundary": "Boundary",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (eeg_dir / "sub-01_task-mi_channels.tsv").write_text(
        "name\tstatus\nC3\tgood\nC4\tbad\n",
        encoding="utf-8",
    )
    return root, eeg.resolve(), events.resolve()


def _value_choice(
    role: str,
    use_as_class: bool,
    class_name: str = "",
    *,
    keep_event: bool = True,
) -> dict[str, object]:
    value: dict[str, object] = {
        "role": role,
        "keep_event": keep_event,
        "use_as_class": use_as_class,
    }
    if class_name:
        value["class_name"] = class_name
    return value
