"""Local-only downloaded public BIDS fixture validation."""

from __future__ import annotations

from pathlib import Path

import pytest

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

PUBLIC_DATA_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "data" / "public"
MNE_BIDS_ROOT = PUBLIC_DATA_DIR / "mne-bids-tiny-eeg"
MNE_BIDS_EEG_DIR = MNE_BIDS_ROOT / "sub-01" / "ses-eeg" / "eeg"
MNE_BIDS_EEG = MNE_BIDS_EEG_DIR / "sub-01_ses-eeg_task-rest_eeg.vhdr"
MNE_BIDS_EVENTS = MNE_BIDS_EEG_DIR / "sub-01_ses-eeg_task-rest_events.tsv"
MNE_BIDS_CHANNELS = MNE_BIDS_EEG_DIR / "sub-01_ses-eeg_task-rest_channels.tsv"


def test_public_mne_bids_import_apply_recipe_and_epoch(tmp_path: Path) -> None:
    """Downloaded MNE-BIDS fixture should exercise folder-level import."""
    if not MNE_BIDS_EEG.exists():
        pytest.skip(
            "MNE-BIDS tiny fixture not downloaded; run "
            "scripts/dev/fetch_public_eeg_fixtures.py first."
        )

    service = ApplicationService()
    scan_result = service.execute(
        ScanSourceCommand(source_path=str(MNE_BIDS_ROOT), source_hint="bids")
    )
    preview_result = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(MNE_BIDS_EEG)],
                "label_carrier_choices": {
                    str(MNE_BIDS_EVENTS): {
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
    validation_result = service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    recipe_path = tmp_path / "mne-bids-tiny-recipe.json"
    recipe_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )

    assert scan_result.ok is True
    assert scan_result.state.interpretation.bids["is_bids"] is True
    assert scan_result.state.interpretation.bids["dataset"]["Name"] == "tiny_bids"
    assert scan_result.state.interpretation.bids["participants"] == [
        {
            "participant_id": "sub-01",
            "age": "29",
            "sex": "F",
            "hand": "A",
            "weight": "n/a",
            "height": "n/a",
        }
    ]
    assert scan_result.state.interpretation.label_carriers == [
        str(MNE_BIDS_EVENTS.resolve())
    ]
    assert scan_result.state.interpretation.bids["channels_files"] == [
        str(MNE_BIDS_CHANNELS.resolve())
    ]
    assert preview_result.ok is True
    preview = preview_result.diagnostics["preview"]
    assert preview["bids"]["selected_scope"]["eeg_files"] == [
        str(MNE_BIDS_EEG.resolve())
    ]
    assert preview["bids"]["selected_scope"]["sessions"] == ["eeg"]
    assert preview["bids"]["selected_scope"]["tasks"] == ["rest"]
    assert preview["class_map"] == {
        "show_stimulus": "show_stimulus",
        "start_experiment": "start_experiment",
    }
    label_preview = preview["label_carrier_preview"][0]
    assert label_preview["bids_event_columns"] == [
        "onset",
        "duration",
        "trial_type",
        "value",
        "sample",
    ]
    assert label_preview["selected_anchor_stats"]["numeric_count"] == 2
    assert label_preview["time_label_preview"] == [
        {"time": "0.0", "label": "start_experiment"},
        {"time": "0.2", "label": "show_stimulus"},
    ]
    assert validation_result.ok is True
    assert validation_result.diagnostics["validation_decision"]["decision"] == (
        "needs_confirmation"
    )
    assert validation_result.diagnostics["validation_decision"]["blocked_reasons"] == []
    assert apply_result.ok is True
    assert apply_result.state.raw.files == [MNE_BIDS_EEG.name]
    handoff = apply_result.state.interpretation.epoch_handoff
    assert handoff["label_source"] == "bids_events"
    assert handoff["default_epoch_events"] == [
        "show_stimulus",
        "start_experiment",
    ]
    assert handoff["label_carrier_plan"] == [
        {
            "path": str(MNE_BIDS_EVENTS.resolve()),
            "selected_label_field": "trial_type",
            "selected_anchor": "onset",
            "selected_duration_field": "duration",
            "time_model": "seconds",
            "placement_method": "interval",
        }
    ]
    assert recipe_result.ok is True
    assert recipe_result.diagnostics["recipe"]["bids"]["root"] == str(
        MNE_BIDS_ROOT.resolve()
    )

    reload_service = ApplicationService()
    reload_result = reload_service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    assert reload_result.ok is True
    assert reload_result.diagnostics["candidate"]["bids"]["selected_scope"][
        "events_files"
    ] == [str(MNE_BIDS_EVENTS.resolve())]

    preprocess_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        )
    )
    epoch_result = service.execute(CreateEpochCommand(t_min=0.0, t_max=0.3))

    assert preprocess_result.ok is True
    assert epoch_result.ok is True
    assert epoch_result.state.epoch.available is True
    assert epoch_result.state.epoch.epoch_count == 2
    assert set(epoch_result.state.epoch.event_ids) == {
        "show_stimulus",
        "start_experiment",
    }
