"""Local-only public BIDS-like fixture validation."""

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
TINY_BIDS_ROOT = PUBLIC_DATA_DIR / "tiny-bids-eeg"
TINY_BIDS_EEG_DIR = TINY_BIDS_ROOT / "sub-01" / "ses-01" / "eeg"
TINY_BIDS_EEG = TINY_BIDS_EEG_DIR / "sub-01_ses-01_task-mi_run-1_eeg.vhdr"
TINY_BIDS_EVENTS = TINY_BIDS_EEG_DIR / "sub-01_ses-01_task-mi_run-1_events.tsv"
TINY_BIDS_CHANNELS = TINY_BIDS_EEG_DIR / "sub-01_ses-01_task-mi_run-1_channels.tsv"


def test_public_tiny_bids_import_apply_recipe_and_epoch(tmp_path: Path) -> None:
    """Downloaded/generated BIDS-like fixture should exercise folder-level import."""
    if not TINY_BIDS_EEG.exists():
        pytest.skip(
            "Tiny BIDS fixture not generated; run "
            "scripts/dev/fetch_public_eeg_fixtures.py first."
        )

    service = ApplicationService()
    scan_result = service.execute(
        ScanSourceCommand(source_path=str(TINY_BIDS_ROOT), source_hint="bids")
    )
    preview_result = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(TINY_BIDS_EEG)],
                "label_carrier_choices": {
                    str(TINY_BIDS_EVENTS): {
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
    recipe_path = tmp_path / "tiny-bids-recipe.json"
    recipe_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )

    assert scan_result.ok is True
    assert scan_result.state.interpretation.bids["is_bids"] is True
    assert scan_result.state.interpretation.label_carriers == [
        str(TINY_BIDS_EVENTS.resolve())
    ]
    assert scan_result.state.interpretation.bids["channels_files"] == [
        str(TINY_BIDS_CHANNELS.resolve())
    ]
    assert preview_result.ok is True
    preview = preview_result.diagnostics["preview"]
    assert preview["bids"]["selected_scope"]["eeg_files"] == [
        str(TINY_BIDS_EEG.resolve())
    ]
    assert preview["class_map"] == {
        "feet": "Feet motor imagery",
        "left_hand": "Left hand motor imagery",
        "right_hand": "Right hand motor imagery",
    }
    assert validation_result.ok is True
    assert apply_result.ok is True
    assert apply_result.state.raw.files == [TINY_BIDS_EEG.name]
    handoff = apply_result.state.interpretation.epoch_handoff
    assert handoff["label_source"] == "bids_events"
    assert handoff["default_epoch_events"] == [
        "Feet motor imagery",
        "Left hand motor imagery",
        "Right hand motor imagery",
    ]
    assert recipe_result.ok is True
    assert recipe_result.diagnostics["recipe"]["bids"]["root"] == str(
        TINY_BIDS_ROOT.resolve()
    )

    reload_service = ApplicationService()
    reload_result = reload_service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    assert reload_result.ok is True
    assert reload_result.diagnostics["candidate"]["bids"]["selected_scope"][
        "events_files"
    ] == [str(TINY_BIDS_EVENTS.resolve())]

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
    assert epoch_result.state.epoch.epoch_count == 3
    assert set(epoch_result.state.epoch.event_ids) == {
        "Feet motor imagery",
        "Left hand motor imagery",
        "Right hand motor imagery",
    }
