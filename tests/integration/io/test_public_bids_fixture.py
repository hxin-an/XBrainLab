"""Local-only downloaded public BIDS fixture validation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.dev.fetch_public_eeg_fixtures import resolve_public_fixture_dir
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CommandName,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    build_capability_policy,
)

PUBLIC_DATA_DIR = resolve_public_fixture_dir()
MNE_BIDS_ROOT = PUBLIC_DATA_DIR / "mne-bids-tiny-eeg"
MNE_BIDS_EEG_DIR = MNE_BIDS_ROOT / "sub-01" / "ses-eeg" / "eeg"
MNE_BIDS_EEG = MNE_BIDS_EEG_DIR / "sub-01_ses-eeg_task-rest_eeg.vhdr"
MNE_BIDS_EVENTS = MNE_BIDS_EEG_DIR / "sub-01_ses-eeg_task-rest_events.tsv"
MNE_BIDS_CHANNELS = MNE_BIDS_EEG_DIR / "sub-01_ses-eeg_task-rest_channels.tsv"
OPENNEURO_P300_ROOT = PUBLIC_DATA_DIR / "openneuro-ds003061-p300"
OPENNEURO_P300_EEG_DIR = OPENNEURO_P300_ROOT / "sub-001" / "eeg"

pytestmark = pytest.mark.optional_public_fixture


def test_public_mne_bids_numeric_trial_type_applies_and_publishes(
    tmp_path: Path,
) -> None:
    """Preview and Apply must share one identity for numeric-looking labels."""
    if not MNE_BIDS_EEG.exists():
        pytest.skip(
            "MNE-BIDS tiny fixture not downloaded; run "
            "scripts/dev/fetch_public_eeg_fixtures.py first."
        )

    bids_root = tmp_path / "numeric-label-bids"
    shutil.copytree(MNE_BIDS_ROOT, bids_root)
    eeg_dir = bids_root / "sub-01" / "ses-eeg" / "eeg"
    eeg_path = eeg_dir / MNE_BIDS_EEG.name
    events_path = eeg_dir / MNE_BIDS_EVENTS.name
    events_json = eeg_dir / "sub-01_ses-eeg_task-rest_events.json"
    events_path.write_text(
        "onset\tduration\ttrial_type\tvalue\tsample\n"
        "0.0\t0.0\t0.0\t1\t0\n"
        "0.2\t0.0\t1.0\t2\t1000\n",
        encoding="utf-8",
    )
    events_json.write_text(
        json.dumps(
            {
                "trial_type": {
                    "Description": "Numeric-looking categorical trial label.",
                    "Levels": {"0.0": "Rest", "1.0": "Target"},
                }
            }
        ),
        encoding="utf-8",
    )
    choices = {
        "selected_eeg_files": [str(eeg_path.resolve())],
        "label_carrier_choices": {
            str(events_path.resolve()): {
                "label_field": "trial_type",
                "anchor": "onset",
                "duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
                "value_decisions": {
                    "0.0": {
                        "role": "stimulus",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": "Rest",
                    },
                    "1.0": {
                        "role": "stimulus",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": "Target",
                    },
                },
            }
        },
    }

    service = ApplicationService()
    try:
        scan = service.execute(
            ScanSourceCommand(source_path=str(bids_root), source_hint="bids")
        )
        preview = service.execute(PreviewInterpretationCommand(choices=choices))
        validation = service.execute(ValidateInterpretationCommand())
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert scan.ok, scan.message
        assert preview.ok, preview.message
        assert validation.ok, validation.message
        assert applied.ok, applied.message
        assert applied.state.raw.count == 1
        assert applied.state.interpretation.class_map == {
            "0.0": "Rest",
            "1.0": "Target",
        }
        assert applied.state.interpretation.epoch_handoff["default_epoch_events"] == [
            "Rest",
            "Target",
        ]
        summary = service.execute(QueryStateCommand(query="data_summary"))
        assert summary.ok, summary.message
        assert summary.diagnostics["count"] == 1
        assert summary.diagnostics["files"] == [eeg_path.name]
        assert applied.diagnostics["label_apply"]["status"] == "applied"
        assert (
            build_capability_policy(applied.state).get(CommandName.PREPROCESS).enabled
            is True
        )
        preprocessed = service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE,
                method="z-score",
            )
        )
        assert preprocessed.ok, preprocessed.message
    finally:
        service.close()


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
    assert validation_decision["action_items"] == [
        {
            "issue": (
                "sub-01_ses-eeg_task-rest_events.tsv events.json does not define "
                "Levels for trial_type; class names need confirmation."
            ),
            "impact": (
                "Import may still be usable, but downstream labels or metadata may "
                "need review."
            ),
            "next_action": (
                "Open the target step and resolve or confirm this item before import."
            ),
            "target_step": "Match Labels",
            "severity": "warning",
        }
    ]
    assert apply_result.ok is True
    assert apply_result.diagnostics["montage_preparation"]["state"] == "pending"
    assert service.bids_montage_preparation.wait_for_idle(timeout=5.0)
    montage_snapshot = service.bids_montage_preparation.snapshot()
    assert montage_snapshot.state == "ready"
    assert montage_snapshot.aggregate.compatible is True
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
    assert epoch_result.state.visualization.montage_source == "bids"
    assert epoch_result.state.visualization.channel_positions_available is True
    assert epoch_result.state.visualization.montage_channels
    assert len(epoch_result.state.visualization.montage_channels) < (
        epoch_result.state.visualization.channel_count
    )
    assert set(epoch_result.state.epoch.event_ids) == {
        "show_stimulus",
        "start_experiment",
    }
    reload_service.close()
    service.close()


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


def test_openneuro_p300_preview_recommends_value_across_all_selected_runs() -> None:
    eeg_files = sorted(OPENNEURO_P300_EEG_DIR.glob("*_eeg.set"))
    if len(eeg_files) != 3:
        pytest.skip(
            "OpenNeuro P300 fixture not downloaded; run "
            "scripts/dev/fetch_public_eeg_fixtures.py first."
        )

    service = ApplicationService()
    scan = service.execute(
        ScanSourceCommand(source_path=str(OPENNEURO_P300_ROOT), source_hint="bids")
    )
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(path.resolve()) for path in eeg_files],
            }
        )
    )

    assert scan.ok is True
    assert preview.ok is True
    carriers = preview.diagnostics["preview"]["label_carrier_preview"]
    assert len(carriers) == 3
    assert {carrier["selected_label_field"] for carrier in carriers} == {"value"}
    assert all(carrier["events_json_sidecar_present"] is True for carrier in carriers)
    assert all(
        carrier["label_field_recommendation"]["field"] == "value"
        for carrier in carriers
    )
    recommendation = carriers[0]["label_field_recommendation"]
    assert recommendation["reason_code"] == "value_has_described_classes"
    assert recommendation["facts"]["selected_run_count"] == 3
    assert "reason" not in recommendation
    details = carriers[0]["label_field_recommendation_details"]
    assert details["evidence"]["value_refines_trial_type"] is True
    assert {Path(carrier["selected_target_file"]).name for carrier in carriers} == {
        path.name for path in eeg_files
    }
