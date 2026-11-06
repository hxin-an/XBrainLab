"""Inherited TSVs must preserve actual signal, labels and replay semantics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests.integration.io.test_bids_timestamp_label_field import (
    _choices,
    _write_brainvision_bids_with_generic_flash_codes,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.epoch_context import EPOCH_HINT_KEY


def _inherited_dataset(tmp_path: Path, *, multiple: bool = False):
    root, eeg, events = _write_brainvision_bids_with_generic_flash_codes(tmp_path)
    waveform = np.arange(2_000, dtype="<f4").reshape(1_000, 2) / 100
    eeg.with_suffix(".eeg").write_bytes(waveform.tobytes())
    recordings = [eeg]
    if multiple:
        second = eeg.with_name("sub-01_task-cvep_run-2_eeg.vhdr")
        for suffix in (".vhdr", ".vmrk"):
            second.with_suffix(suffix).write_text(
                eeg.with_suffix(suffix)
                .read_text(encoding="utf-8")
                .replace(eeg.stem, second.stem),
                encoding="utf-8",
            )
        second.with_suffix(".eeg").write_bytes(waveform.tobytes())
        recordings.append(second)
    inherited_events = root / "task-cvep_events.tsv"
    events.rename(inherited_events)
    events.with_suffix(".json").rename(inherited_events.with_suffix(".json"))
    eeg.with_name("sub-01_task-cvep_channels.tsv").unlink()
    channels = root / "task-cvep_channels.tsv"
    channels.write_text(
        "name\ttype\tunits\tstatus\nC3\tEEG\tuV\tgood\nC4\tEOG\tuV\tbad\n",
        encoding="utf-8",
    )
    choices = _choices(eeg, inherited_events)
    choices["selected_eeg_files"] = [str(path) for path in recordings]
    return root, recordings, choices, waveform.T * 1e-6, channels


@pytest.mark.parametrize("multiple", [False, True])
def test_inherited_tsv_apply_and_fresh_recipe_preserve_signal_and_events(
    tmp_path: Path, multiple: bool
) -> None:
    root, recordings, choices, waveform, _channels = _inherited_dataset(
        tmp_path, multiple=multiple
    )
    recipe = tmp_path / "recipe.json"
    for replay in (False, True):
        service = ApplicationService()
        try:
            if replay:
                result = service.execute(ReloadInterpretationRecipeCommand(str(recipe)))
            else:
                result = service.execute(
                    ScanSourceCommand(str(root), source_hint="bids")
                )
                assert result.ok, result.message
                result = service.execute(PreviewInterpretationCommand(choices=choices))
            assert result.ok, result.message
            validated = service.execute(ValidateInterpretationCommand())
            assert validated.ok, validated.message
            assert not validated.state.interpretation.blocked_reasons
            applied = service.execute(ApplyInterpretationCommand(confirmed=True))
            assert applied.ok, applied.message
            assert len(service.study.loaded_data_list) == len(recordings)
            placement = applied.diagnostics["label_apply"]["bids_placement"]
            assert {row["eeg_file"] for row in placement} == {
                str(path) for path in recordings
            }
            assert all(
                (
                    row["source_event_count"],
                    row["usable_event_count"],
                    row["excluded_event_count"],
                )
                == (4, 2, 2)
                for row in placement
            )
            for loaded in service.study.loaded_data_list:
                raw = loaded.get_mne()
                assert raw.get_channel_types() == ["eeg", "eog"]
                assert raw.info["bads"] == ["C4"]
                np.testing.assert_allclose(raw.get_data(), waveform, rtol=1e-7, atol=0)
                events, classes = loaded.get_event_list()
                assert events[:, 0].tolist() == [100, 300]
                assert classes == {"Target 0": 1, "Target 1": 2}
                hint = loaded.get_runtime_detail(EPOCH_HINT_KEY)
                assert hint["placement_event_count"] == 2
                assert hint["excluded_event_count"] == 2
            if not replay:
                saved = service.execute(SaveInterpretationRecipeCommand(str(recipe)))
                assert saved.ok, saved.message
        finally:
            service.close()


@pytest.mark.parametrize("change", ["modify", "add_override"])
def test_inherited_channel_change_after_validation_cannot_publish(
    tmp_path: Path, change: str
) -> None:
    root, recordings, choices, _waveform, channels = _inherited_dataset(tmp_path)
    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        assert service.execute(PreviewInterpretationCommand(choices=choices)).ok
        validated = service.execute(ValidateInterpretationCommand())
        assert not validated.state.interpretation.blocked_reasons
        if change == "add_override":
            channels = recordings[0].with_name("sub-01_task-cvep_channels.tsv")
        channels.write_text(
            "name\ttype\tunits\tstatus\nC3\tEEG\tuV\tgood\nC4\tEEG\tuV\tgood\n",
            encoding="utf-8",
        )
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))
        assert not applied.ok
        assert not service.study.loaded_data_list
    finally:
        service.close()


def test_ambiguous_channels_are_blocked_before_apply(tmp_path: Path) -> None:
    root, _recordings, choices, _waveform, channels = _inherited_dataset(tmp_path)
    (root / "channels.tsv").write_bytes(channels.read_bytes())
    service = ApplicationService()
    try:
        catalog = service.execute(
            ScanSourceCommand(str(root), source_hint="auto", catalog_only=True)
        )
        assert catalog.ok, catalog.message
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        preview = service.execute(PreviewInterpretationCommand(choices=choices))
        assert preview.ok, preview.message
        validated = service.execute(ValidateInterpretationCommand())
        assert any(
            "ambiguous" in reason
            for reason in validated.state.interpretation.blocked_reasons
        )
        assert not service.execute(ApplyInterpretationCommand(confirmed=True)).ok
        assert not service.study.loaded_data_list
    finally:
        service.close()
