"""Regression coverage for reviewed BIDS timestamp labels.

The BIDS ``value`` column remains provenance here: it deliberately contains
generic flash codes reused by more than one reviewed ``trial_id`` class.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)


def _write_brainvision_bids_with_generic_flash_codes(
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    root = tmp_path / "bids"
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps(
            {"Name": "timestamp label-field regression", "BIDSVersion": "1.10.0"}
        ),
        encoding="utf-8",
    )
    eeg = eeg_dir / "sub-01_task-cvep_eeg.vhdr"
    # A real tiny recording without a dependency on the optional pybv exporter.
    eeg.with_suffix(".eeg").write_bytes(np.zeros((1_000, 2), dtype="<f4").tobytes())
    eeg.write_text(
        "Brain Vision Data Exchange Header File Version 1.0\n"
        "[Common Infos]\nCodepage=UTF-8\n"
        f"DataFile={eeg.with_suffix('.eeg').name}\n"
        f"MarkerFile={eeg.with_suffix('.vmrk').name}\n"
        "DataFormat=BINARY\nDataOrientation=MULTIPLEXED\n"
        "NumberOfChannels=2\nSamplingInterval=10000\n"
        "[Binary Infos]\nBinaryFormat=IEEE_FLOAT_32\n"
        "[Channel Infos]\nCh1=C3,,1,µV\nCh2=C4,,1,µV\n",
        encoding="utf-8",
    )
    eeg.with_suffix(".vmrk").write_text(
        "Brain Vision Data Exchange Marker File, Version 1.0\n"
        "[Common Infos]\nCodepage=UTF-8\n"
        f"DataFile={eeg.with_suffix('.eeg').name}\n"
        "[Marker Infos]\n"
        "Mk1=Comment,0.0,101,1,0\nMk2=Comment,1.0,201,1,0\n"
        "Mk3=Comment,0.0,301,1,0\nMk4=Comment,1.0,401,1,0\n",
        encoding="utf-8",
    )
    events = eeg_dir / "sub-01_task-cvep_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\ttrial_id\n"
        "1.0\t0\t0.0\t1\t0\n"
        "2.0\t0\t1.0\t2\tn/a\n"
        "3.0\t0\t0.0\t1\t1\n"
        "4.0\t0\t1.0\t2\tn/a\n",
        encoding="utf-8",
    )
    events.with_suffix(".json").write_text(
        json.dumps(
            {
                "trial_id": {
                    "Description": "Source-owned target ID at a trial onset.",
                    "Levels": {"0": "Target 0", "1": "Target 1"},
                },
                "value": {"Description": "Generic binary flash code, not a class."},
            }
        ),
        encoding="utf-8",
    )
    (eeg_dir / "sub-01_task-cvep_channels.tsv").write_text(
        "name\ttype\tunits\tstatus\nC3\tEEG\tuV\tgood\nC4\tEEG\tuV\tgood\n",
        encoding="utf-8",
    )
    return root, eeg, events


def _choices(eeg: Path, events: Path) -> dict[str, object]:
    return {
        "selected_eeg_files": [str(eeg)],
        "label_carrier_choices": {
            str(events): {
                "label_field": "trial_id",
                "anchor": "onset",
                "duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "time_field",
                "granularity": "trial",
                "value_decisions": {
                    "0": {
                        "role": "stimulus",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": "Target 0",
                    },
                    "1": {
                        "role": "stimulus",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": "Target 1",
                    },
                },
            }
        },
    }


def _class_event_samples(service: ApplicationService) -> dict[str, list[int]]:
    events, event_id = service.study.loaded_data_list[0].get_event_list()
    return {
        name: events[events[:, 2] == code, 0].tolist()
        for name, code in event_id.items()
        if name in {"Target 0", "Target 1"}
    }


def test_bids_timestamp_label_field_allows_generic_value_codes_and_replays_recipe(
    tmp_path: Path,
) -> None:
    root, eeg, events = _write_brainvision_bids_with_generic_flash_codes(tmp_path)
    recipe = tmp_path / "trial-id-recipe.json"
    writer = ApplicationService()
    try:
        assert writer.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        preview = writer.execute(
            PreviewInterpretationCommand(choices=_choices(eeg, events))
        )
        assert preview.ok, preview.message
        reviewed = preview.diagnostics["candidate"]["bids"]["event_validation"]["runs"][
            0
        ]
        assert reviewed["event_code_class_map"] == {}
        assert writer.execute(ValidateInterpretationCommand()).ok
        applied = writer.execute(ApplyInterpretationCommand(confirmed=True))
        assert applied.ok, applied.message
        assert _class_event_samples(writer) == {"Target 0": [100], "Target 1": [300]}
        annotations = {
            str(description).removeprefix("Comment/")
            for description in writer.study.loaded_data_list[0]
            .get_mne()
            .annotations.description
        }
        assert annotations >= {
            "0.0",
            "1.0",
            "Target 0",
            "Target 1",
        }
        assert writer.execute(SaveInterpretationRecipeCommand(str(recipe))).ok
    finally:
        writer.close()

    replay = ApplicationService()
    try:
        assert replay.execute(ReloadInterpretationRecipeCommand(str(recipe))).ok
        assert replay.execute(ValidateInterpretationCommand()).ok
        reapplied = replay.execute(ApplyInterpretationCommand(confirmed=True))
        assert reapplied.ok, reapplied.message
        assert _class_event_samples(replay) == {"Target 0": [100], "Target 1": [300]}
    finally:
        replay.close()


def test_bids_event_code_placement_still_rejects_generic_value_code_collisions(
    tmp_path: Path,
) -> None:
    root, eeg, events = _write_brainvision_bids_with_generic_flash_codes(tmp_path)
    choices = _choices(eeg, events)
    carrier = choices["label_carrier_choices"][str(events)]
    carrier["placement_method"] = "event_code"
    carrier["anchor"] = "value"
    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        preview = service.execute(PreviewInterpretationCommand(choices=choices))
        assert preview.ok, preview.message
        reviewed = preview.diagnostics["candidate"]["bids"]["event_validation"]["runs"][
            0
        ]
        assert any(
            issue["code"] == "event_code_has_multiple_classes"
            for issue in reviewed["issues"]
        )
        validation = service.execute(ValidateInterpretationCommand())
        assert validation.ok
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))
        assert not applied.ok
        assert "multiple classes" in applied.message
    finally:
        service.close()
