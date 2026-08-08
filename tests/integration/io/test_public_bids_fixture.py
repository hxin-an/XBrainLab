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
OPENNEURO_P300_ROOT = PUBLIC_DATA_DIR / "openneuro-ds003061-p300"
OPENNEURO_P300_EEG_DIR = OPENNEURO_P300_ROOT / "sub-001" / "eeg"

pytestmark = pytest.mark.optional_public_fixture


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
                        "value_decisions": {
                            "show_stimulus": {
                                "role": "stimulus",
                                "keep_event": True,
                                "use_as_class": True,
                                "class_name": "show_stimulus",
                            },
                            "start_experiment": {
                                "role": "system",
                                "keep_event": True,
                                "use_as_class": True,
                                "class_name": "start_experiment",
                            },
                        },
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
    assert scan_result.state.interpretation.bids["metadata_materialized"] is False
    assert scan_result.state.interpretation.bids["dataset"] == {}
    assert scan_result.state.interpretation.bids["participants"] == []
    assert scan_result.state.interpretation.label_carriers == [
        str(MNE_BIDS_EVENTS.resolve())
    ]
    assert scan_result.state.interpretation.bids["channels_files"] == [
        str(MNE_BIDS_CHANNELS.resolve())
    ]
    assert preview_result.ok is True
    preview = preview_result.diagnostics["preview"]
    assert preview["bids"]["metadata_materialized"] is True
    assert preview["bids"]["dataset"]["Name"] == "tiny_bids"
    assert preview["bids"]["participants"] == [
        {
            "participant_id": "sub-01",
            "age": "29",
            "sex": "F",
            "hand": "A",
            "weight": "n/a",
            "height": "n/a",
        }
    ]
    assert preview["bids"]["selected_scope"]["eeg_files"] == [
        str(MNE_BIDS_EEG.resolve())
    ]
    assert preview["bids"]["selected_scope"]["sessions"] == ["eeg"]
    assert preview["bids"]["selected_scope"]["tasks"] == ["rest"]
    assert preview["class_map"] == {
        "show_stimulus": "show_stimulus",
        "start_experiment": "start_experiment",
    }
    event_validation = preview["bids"]["event_validation"]
    assert event_validation["status"] == "safe"
    assert event_validation["file_mapping"] == {
        str(MNE_BIDS_EEG.resolve()): str(MNE_BIDS_EVENTS.resolve())
    }
    assert event_validation["pairing_issues"] == []
    assert event_validation["mapping_conflicts"] == []
    assert event_validation["runs"][0]["eeg_file"] == str(MNE_BIDS_EEG.resolve())
    assert event_validation["runs"][0]["events_file"] == str(MNE_BIDS_EVENTS.resolve())
    assert event_validation["runs"][0]["sampling_frequency_hz"] > 0
    assert event_validation["runs"][0]["sample_count"] > 0
    assert event_validation["runs"][0]["recording_duration_seconds"] > 0
    assert event_validation["runs"][0]["bids_schema"]["status"] == "valid"
    assert event_validation["runs"][0]["placement"]["status"] == "ready"
    assert event_validation["runs"][0]["placement"]["usable_event_count"] == 2
    assert event_validation["runs"][0]["placement"]["excluded_event_count"] == 0
    assert event_validation["runs"][0]["issues"] == []
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
    validation_decision = validation_result.diagnostics["validation_decision"]
    assert validation_decision["decision"] == "safe"
    assert validation_decision["blocked_reasons"] == []
    assert validation_decision["required_confirmations"] == []
    assert validation_decision["action_items"] == []
    assert apply_result.ok is True
    assert apply_result.diagnostics["channels_apply"][0]["bad_channels"] == ["PO10"]
    assert service.study.loaded_data_list[0].get_mne().info["bads"] == ["PO10"]
    assert apply_result.diagnostics["label_apply"]["bids_placement"] == [
        {
            "eeg_file": str(MNE_BIDS_EEG.resolve()),
            "events_file": str(MNE_BIDS_EVENTS.resolve()),
            "source_event_count": 2,
            "usable_event_count": 2,
            "excluded_event_count": 0,
            "excluded_reasons": {},
            "unknown_duration_count": 0,
            "unknown_duration_rows": [],
        }
    ]
    assert apply_result.state.raw.files == [MNE_BIDS_EEG.name]
    handoff = apply_result.state.interpretation.epoch_handoff
    assert handoff["label_source"] == "bids_events"
    assert handoff["default_epoch_events"] == [
        "show_stimulus",
        "start_experiment",
    ]
    handoff_plan = handoff["label_carrier_plan"][0]
    assert handoff_plan["path"] == str(MNE_BIDS_EVENTS.resolve())
    assert handoff_plan["selected_target_file"] == str(MNE_BIDS_EEG.resolve())
    assert handoff_plan["selected_label_field"] == "trial_type"
    assert handoff_plan["selected_anchor"] == "onset"
    assert handoff_plan["selected_duration_field"] == "duration"
    assert handoff_plan["time_model"] == "seconds"
    assert handoff_plan["placement_method"] == "interval"
    assert handoff_plan["run_class_map"] == {
        "show_stimulus": "show_stimulus",
        "start_experiment": "start_experiment",
    }
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


def test_openneuro_p300_trial_type_excludes_missing_rows_and_imports() -> None:
    """A valid BIDS label column may contain sparse canonical n/a values."""
    eeg_files = sorted(OPENNEURO_P300_EEG_DIR.glob("*_eeg.set"))
    events_files = sorted(OPENNEURO_P300_EEG_DIR.glob("*_events.tsv"))
    if len(eeg_files) != 3 or len(events_files) != 3:
        pytest.skip(
            "OpenNeuro P300 fixture not downloaded; run "
            "scripts/dev/fetch_public_eeg_fixtures.py first."
        )

    decisions = {
        "stimulus": {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": "stimulus",
        },
        "response": {
            "role": "response",
            "keep_event": True,
            "use_as_class": False,
        },
    }
    service = ApplicationService()
    scan = service.execute(
        ScanSourceCommand(source_path=str(OPENNEURO_P300_ROOT), source_hint="bids")
    )
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(path.resolve()) for path in eeg_files],
                "label_carrier_choices": {
                    str(path.resolve()): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "time_field",
                        "value_decisions": decisions,
                    }
                    for path in events_files
                },
            }
        )
    )
    validation = service.execute(ValidateInterpretationCommand())
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan.ok is True
    assert preview.ok is True
    runs = preview.diagnostics["preview"]["bids"]["event_validation"]["runs"]
    assert [run["placement"]["status"] for run in runs] == [
        "ready_with_exclusions",
        "ready",
        "ready_with_exclusions",
    ]
    assert [run["placement"]["usable_event_count"] for run in runs] == [
        860,
        862,
        858,
    ]
    assert [run["placement"]["excluded_event_count"] for run in runs] == [3, 0, 2]
    assert validation.diagnostics["validation_decision"]["blocked_reasons"] == []
    assert applied.ok is True
    assert applied.state.raw.count == 3
    assert applied.state.interpretation.class_map == {"stimulus": "stimulus"}
    assert applied.state.interpretation.epoch_handoff["default_epoch_events"] == [
        "stimulus"
    ]
    assert [
        row["excluded_reasons"]
        for row in applied.diagnostics["label_apply"]["bids_placement"]
    ] == [
        {"selected_label_missing": 3},
        {},
        {"selected_label_missing": 2},
    ]
