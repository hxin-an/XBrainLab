"""Regression coverage for reviewed BIDS timestamp labels.

The BIDS ``value`` column remains provenance here: it deliberately contains
generic flash codes reused by more than one reviewed ``trial_id`` class.
"""

from __future__ import annotations

import json
from pathlib import Path

import mne
import numpy as np
import pytest

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


@pytest.mark.parametrize(
    ("base", "origin", "samples"),
    [
        ("zero_based", "absolute", (100, 300)),
        ("one_based", "recording_relative", (101, 301)),
    ],
)
def test_bids_sample_index_choices_survive_fresh_recipe_replay(
    tmp_path: Path, base: str, origin: str, samples: tuple[int, int]
) -> None:
    root, eeg, events = _write_brainvision_bids_with_generic_flash_codes(tmp_path)
    events.write_text(
        "onset\tduration\ttrial_id\tsample\n"
        f"1\t0\t0\t{samples[0]}\n3\t0\t1\t{samples[1]}\n",
        encoding="utf-8",
    )
    choices = _choices(eeg, events)
    choices["label_carrier_choices"][str(events)].update(
        anchor="sample",
        time_model="sample_index",
        sample_index_base=base,
        sample_index_origin=origin,
    )
    recipe = tmp_path / "sample-index-recipe.json"
    writer = ApplicationService()
    try:
        assert writer.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        assert writer.execute(PreviewInterpretationCommand(choices=choices)).ok
        assert writer.execute(ValidateInterpretationCommand()).ok
        applied = writer.execute(ApplyInterpretationCommand(confirmed=True))
        assert applied.ok, applied.message
        assert _class_event_samples(writer) == {"Target 0": [100], "Target 1": [300]}
        assert writer.execute(SaveInterpretationRecipeCommand(str(recipe))).ok
    finally:
        writer.close()

    replay = ApplicationService()
    try:
        reloaded = replay.execute(ReloadInterpretationRecipeCommand(str(recipe)))
        assert reloaded.ok, reloaded.message
        assert replay.execute(ValidateInterpretationCommand()).ok
        reapplied = replay.execute(ApplyInterpretationCommand(confirmed=True))
        assert reapplied.ok, reapplied.message
        assert _class_event_samples(replay) == {"Target 0": [100], "Target 1": [300]}
    finally:
        replay.close()


def test_shared_bids_sample_indexes_are_converted_for_each_recording(
    tmp_path: Path,
) -> None:
    from tests.integration.io.test_bids_inherited_sidecars import (
        _inherited_dataset,
    )

    root, recordings, choices, waveform, _channels = _inherited_dataset(
        tmp_path, multiple=True
    )
    second = recordings[1]
    second.write_text(
        second.read_text(encoding="utf-8").replace(
            "SamplingInterval=10000", "SamplingInterval=5000"
        ),
        encoding="utf-8",
    )
    events = root / "task-cvep_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_id\tsample\n1\t0\t0\t100\n3\t0\t1\t300\n",
        encoding="utf-8",
    )
    choices["label_carrier_choices"][str(events)].update(
        anchor="sample",
        time_model="sample_index",
        sample_index_base="zero_based",
        sample_index_origin="recording_relative",
    )
    recipe = tmp_path / "shared-sample-recipe.json"
    for replay in (False, True):
        service = ApplicationService()
        try:
            if replay:
                result = service.execute(ReloadInterpretationRecipeCommand(str(recipe)))
            else:
                assert service.execute(
                    ScanSourceCommand(str(root), source_hint="bids")
                ).ok
                result = service.execute(PreviewInterpretationCommand(choices=choices))
            assert result.ok, result.message
            assert service.execute(ValidateInterpretationCommand()).ok
            applied = service.execute(ApplyInterpretationCommand(confirmed=True))
            assert applied.ok, applied.message
            assert len(service.study.loaded_data_list) == 2
            for loaded, expected_sfreq in zip(
                service.study.loaded_data_list, (100.0, 200.0), strict=True
            ):
                raw = loaded.get_mne()
                assert raw.info["sfreq"] == expected_sfreq
                np.testing.assert_allclose(raw.get_data(), waveform, rtol=1e-7, atol=0)
                samples, classes = loaded.get_event_list()
                assert {
                    name: samples[samples[:, 2] == code, 0].tolist()
                    for name, code in classes.items()
                } == {"Target 0": [100], "Target 1": [300]}
            if not replay:
                assert service.execute(SaveInterpretationRecipeCommand(str(recipe))).ok
        finally:
            service.close()


@pytest.mark.parametrize("sample", ["1000", "100.5"])
def test_bids_selected_sample_anchor_is_checked_before_apply(
    tmp_path: Path, sample: str
) -> None:
    root, eeg, events = _write_brainvision_bids_with_generic_flash_codes(tmp_path)
    events.write_text(
        f"onset\tduration\ttrial_id\tsample\n1\t0\t0\t100\n3\t0\t1\t{sample}\n",
        encoding="utf-8",
    )
    choices = _choices(eeg, events)
    choices["label_carrier_choices"][str(events)].update(
        anchor="sample",
        time_model="sample_index",
        sample_index_base="zero_based",
        sample_index_origin="recording_relative",
    )
    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        assert service.execute(PreviewInterpretationCommand(choices=choices)).ok
        validation = service.execute(ValidateInterpretationCommand())
        assert validation.ok, validation.message
        assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
        assert service.study.loaded_data_list == []
    finally:
        service.close()


@pytest.mark.parametrize(
    ("first_sample", "bids_duration"),
    [(1000, "2"), (1000, "n/a"), (-1000, "2")],
)
def test_bids_selected_absolute_sample_and_end_field_match_actual_placement(
    tmp_path: Path, first_sample: int, bids_duration: str
) -> None:
    """A controlled FIF exercises nonzero first_samp, not BIDS format coverage."""
    from XBrainLab.backend.application.epoch_context import EPOCH_HINT_KEY

    root, brainvision, events = _write_brainvision_bids_with_generic_flash_codes(
        tmp_path
    )
    eeg = brainvision.with_suffix(".fif")
    mne.io.RawArray(
        np.zeros((2, 1000)),
        mne.create_info(["C3", "C4"], 100.0, ch_types="eeg"),
        first_samp=first_sample,
        verbose="ERROR",
    ).save(eeg, overwrite=True, verbose="ERROR")
    events.write_text(
        "onset\tduration\ttrial_id\tsample\tend\n"
        f"1\t{bids_duration}\t0\t{first_sample + 100}\t{first_sample + 150}\n"
        f"3\t{bids_duration}\t1\t{first_sample + 300}\t{first_sample + 350}\n",
        encoding="utf-8",
    )
    choices = _choices(eeg, events)
    choices["label_carrier_choices"][str(events)].update(
        anchor="sample",
        duration_field="end",
        time_model="sample_index",
        sample_index_base="zero_based",
        sample_index_origin="absolute",
    )
    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        assert service.execute(PreviewInterpretationCommand(choices=choices)).ok
        validation = service.execute(ValidateInterpretationCommand())
        assert validation.ok, validation.message
        if first_sample < 0:
            # Preserve the existing BIDS apply policy rejecting raw negative samples.
            assert (
                validation.diagnostics["validation_decision"]["decision"] == "blocked"
            )
            assert service.study.loaded_data_list == []
            return
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))
        assert applied.ok, applied.message
        assert _class_event_samples(service) == {
            "Target 0": [first_sample + 100],
            "Target 1": [first_sample + 300],
        }
        loaded = service.study.loaded_data_list[0]
        class_durations = [
            duration
            for description, duration in zip(
                loaded.get_mne().annotations.description,
                loaded.get_mne().annotations.duration,
                strict=True,
            )
            if description in {"Target 0", "Target 1"}
        ]
        assert class_durations == [0.5, 0.5]
        assert loaded.get_runtime_detail(EPOCH_HINT_KEY)["duration_stats"]["max"] == 0.5
    finally:
        service.close()


@pytest.mark.parametrize(
    ("case", "expected_issue"),
    [
        ("bad_class", "mne_excluded_class_description"),
        ("missing_sample_base", "sample_index_contract_required"),
        ("missing_sample_origin", "sample_index_contract_required"),
        ("after_last_sample", "onset_after_last_stored_sample"),
    ],
)
def test_bids_rejects_unapplicable_timestamp_choices_during_review(
    tmp_path: Path, case: str, expected_issue: str
) -> None:
    root, eeg, events = _write_brainvision_bids_with_generic_flash_codes(tmp_path)
    choices = _choices(eeg, events)
    carrier = choices["label_carrier_choices"][str(events)]
    if case == "bad_class":
        carrier["value_decisions"]["0"]["class_name"] = "Badminton"
    elif case.startswith("missing_sample"):
        events.write_text(
            "onset\tduration\ttrial_id\tsample\n1\t0\t0\t100\n3\t0\t1\t300\n",
            encoding="utf-8",
        )
        carrier.update(
            anchor="sample",
            time_model="sample_index",
            sample_index_base="zero_based",
            sample_index_origin="recording_relative",
        )
        del carrier[
            "sample_index_base"
            if case == "missing_sample_base"
            else "sample_index_origin"
        ]
    else:
        events.write_text(
            "onset\tduration\ttrial_id\n1\t0\t0\n9.994\t0\t1\n",
            encoding="utf-8",
        )
    original_events = events.read_bytes()
    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        preview = service.execute(PreviewInterpretationCommand(choices=choices))
        assert preview.ok, preview.message
        reviewed = preview.diagnostics["candidate"]["bids"]["event_validation"]["runs"][
            0
        ]
        assert expected_issue in {issue["code"] for issue in reviewed["issues"]}
        validation = service.execute(ValidateInterpretationCommand())
        assert validation.ok, validation.message
        assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
        assert validation.state.interpretation.blocked_reasons
        assert service.study.loaded_data_list == []
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))
        assert not applied.ok
        assert service.study.loaded_data_list == []
        assert events.read_bytes() == original_events
    finally:
        service.close()


def test_bids_point_on_last_stored_sample_remains_applicable(tmp_path: Path) -> None:
    root, eeg, events = _write_brainvision_bids_with_generic_flash_codes(tmp_path)
    events.write_text(
        "onset\tduration\ttrial_id\n1\t0\t0\n9.99\t0\t1\n",
        encoding="utf-8",
    )
    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        assert service.execute(
            PreviewInterpretationCommand(choices=_choices(eeg, events))
        ).ok
        validation = service.execute(ValidateInterpretationCommand())
        assert validation.ok
        assert not validation.state.interpretation.blocked_reasons
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))
        assert applied.ok, applied.message
        assert _class_event_samples(service) == {"Target 0": [100], "Target 1": [999]}
    finally:
        service.close()
