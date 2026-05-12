"""Application service contract tests."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ApplyMontageCommand,
    ApplySmartParseCommand,
    AttachLabelsCommand,
    ClearDatasetsCommand,
    ClearTrainingHistoryCommand,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    ErrorType,
    EvaluateCommand,
    GenerateDatasetCommand,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
    NewSessionCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    RemoveFilesCommand,
    ResetPreprocessCommand,
    ResetSessionCommand,
    SaliencyCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    StopTrainingCommand,
    TrainCommand,
    UpdateMetadataCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
)
from XBrainLab.backend.dataset import SplitByType
from XBrainLab.backend.study import Study


def test_empty_state_snapshot_and_policy():
    service = ApplicationService(Study())

    state = service.get_state()
    policy = service.get_capabilities()

    assert state.pipeline_stage == "empty"
    assert state.raw.loaded is False
    assert state.preprocessed.available is False
    assert state.epoch.available is False
    assert state.dataset.available is False
    assert state.training.has_trainer is False
    assert state.interpretation.has_scan_result is False
    assert state.interpretation.has_applied_interpretation is False
    assert policy.get(CommandName.LOAD_DATA).available is True
    assert policy.get(CommandName.SCAN_SOURCE).available is True
    assert policy.get(CommandName.PREVIEW_INTERPRETATION).available is False
    assert policy.get(CommandName.PREPROCESS).available is False
    assert policy.get(CommandName.TRAIN).available is False
    assert policy.get(CommandName.TRAIN).requires_confirmation is True
    assert policy.get(CommandName.TRAIN).can_auto_execute is False
    assert policy.get(CommandName.RESET_SESSION).confirmation_required is False


def test_capability_policy_covers_all_declared_commands():
    service = ApplicationService(Study())
    policy = service.get_capabilities()

    assert set(policy.capabilities) == {name.value for name in CommandName}
    assert policy.get(CommandName.EVALUATE).available is False
    assert policy.get(CommandName.VISUALIZE).available is False
    assert policy.get(CommandName.SALIENCY).available is False
    assert policy.get(CommandName.RESET_PREPROCESS).available is False
    assert policy.get(CommandName.CLEAR_DATASETS).available is False
    assert policy.get(CommandName.CLEAR_TRAINING_HISTORY).available is False
    assert policy.get(CommandName.SCAN_SOURCE).available is True
    assert policy.get(CommandName.PREVIEW_INTERPRETATION).available is False
    assert policy.get(CommandName.VALIDATE_INTERPRETATION).available is False
    assert policy.get(CommandName.APPLY_INTERPRETATION).available is False
    assert policy.get(CommandName.SAVE_INTERPRETATION_RECIPE).available is False
    assert policy.get(CommandName.RELOAD_INTERPRETATION_RECIPE).available is True
    assert policy.get(CommandName.QUERY_STATE).available is True
    assert policy.get(CommandName.NEW_SESSION).available is True


def test_data_interpretation_scan_preview_validate_requires_confirmation(tmp_path):
    source_dir = tmp_path / "gdf_with_external_labels"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_bytes(b"not loaded during scan")
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    scan = service.execute(ScanSourceCommand(source_path=str(source_dir)))
    preview = service.execute(PreviewInterpretationCommand())
    validation = service.execute(ValidateInterpretationCommand())
    unconfirmed_apply = service.execute(ApplyInterpretationCommand())
    confirmed_apply = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan.ok is True
    assert scan.command_name == CommandName.SCAN_SOURCE.value
    assert scan.changed_state.interpretation_changed is True
    assert scan.state.raw.loaded is False
    assert scan.diagnostics["scan_result"]["source_kind"] == "folder"
    assert scan.diagnostics["scan_result"]["eeg_files"] == [str(eeg_path)]
    assert scan.diagnostics["scan_result"]["label_carriers"] == [str(label_path)]

    assert preview.ok is True
    assert preview.diagnostics["preview"]["label_carrier_count"] == 1
    assert "class map" in " ".join(preview.diagnostics["preview"]["confirmation_items"])
    assert validation.ok is True
    assert validation.diagnostics["validation_decision"]["decision"] == (
        "needs_confirmation"
    )
    assert validation.state.interpretation.validation_decision == "needs_confirmation"

    assert unconfirmed_apply.failed is True
    assert unconfirmed_apply.error_type == ErrorType.CONFIRMATION_REQUIRED
    assert service.dataset.import_files.call_count == 1
    assert confirmed_apply.ok is True
    assert confirmed_apply.diagnostics["applied_interpretation"]["loaded_files"] == [
        str(eeg_path),
    ]
    assert confirmed_apply.state.interpretation.has_applied_interpretation is True


def test_data_interpretation_choices_flow_into_recipe(tmp_path):
    source_dir = tmp_path / "reviewed_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    recipe_path = tmp_path / "reviewed_recipe.json"
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    "subject01_run1.fif": {
                        "session": "session-01",
                        "task": "motor-imagery",
                    }
                },
                "class_map": {"1": "left hand", "2": "right hand"},
            }
        )
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    save_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    metadata_preview = preview.diagnostics["preview"]["metadata_preview"][0]
    assert metadata_preview["session"]["value"] == "session-01"
    assert metadata_preview["session"]["source"] == "user_override"
    assert metadata_preview["task"]["value"] == "motor-imagery"
    assert preview.diagnostics["preview"]["class_map"] == {
        "1": "left hand",
        "2": "right hand",
    }
    applied = apply_result.diagnostics["applied_interpretation"]
    assert applied["class_map"] == {"1": "left hand", "2": "right hand"}
    recipe = save_result.diagnostics["recipe"]
    assert recipe["metadata"][0]["session"]["override"] == "session-01"
    assert recipe["metadata"][0]["task"]["override"] == "motor-imagery"
    assert recipe["class_map"] == {"1": "left hand", "2": "right hand"}
    assert "choices:metadata_overrides" in recipe["recipe_trace"]
    assert "choices:class_map" in recipe["recipe_trace"]


def test_data_interpretation_apply_updates_loaded_metadata(tmp_path):
    source_dir = tmp_path / "reviewed_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    service = ApplicationService(Study())

    class LoadedData:
        def __init__(self, filepath: str) -> None:
            self.filepath = filepath
            self.subject = "0"
            self.session = "0"
            self.runtime_details: dict[str, dict[str, str]] = {}

        def get_filepath(self) -> str:
            return self.filepath

        def set_subject_name(self, subject: str) -> None:
            self.subject = subject

        def set_session_name(self, session: str) -> None:
            self.session = session

        def set_runtime_detail(self, name: str, detail: dict[str, str]) -> None:
            self.runtime_details[name] = detail

    loaded = LoadedData(str(eeg_path))

    def import_files(_filepaths: object) -> tuple[int, list[str]]:
        cast(Any, service.study).loaded_data_list = [loaded]
        return 1, []

    service.dataset.import_files = MagicMock(side_effect=import_files)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    "subject01_run1.fif": {
                        "subject": "S01",
                        "session": "session-01",
                        "task": "motor-imagery",
                        "run": "1",
                    }
                }
            }
        )
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert loaded.subject == "S01"
    assert loaded.session == "session-01"
    assert loaded.runtime_details["data_interpretation_metadata"] == {
        "subject": "S01",
        "session": "session-01",
        "task": "motor-imagery",
        "run": "1",
    }
    assert apply_result.diagnostics["metadata_apply"] == [
        {
            "file": "subject01_run1.fif",
            "subject": "S01",
            "session": "session-01",
            "task": "motor-imagery",
            "run": "1",
        }
    ]


def test_data_interpretation_label_carrier_choices_flow_into_recipe(tmp_path):
    from scipy.io import savemat

    source_dir = tmp_path / "gdf_with_mat_labels"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(
        label_path,
        {
            "classlabel": [1, 2, 1, 2],
            "cue_onset": [100, 200, 300, 400],
            "artifact_flag": [0, 0, 1, 0],
        },
    )
    recipe_path = tmp_path / "mat_label_recipe.json"
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    initial_preview = service.execute(PreviewInterpretationCommand())
    reviewed_preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "anchor": "cue_onset",
                        "time_model": "sample_index",
                        "granularity": "trial",
                        "role": "class cue labels",
                    }
                },
                "class_map": {"1": "left hand", "2": "right hand"},
                "event_roles": {"cue_onset": "trial anchor"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    save_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    initial_carriers = initial_preview.diagnostics["preview"]["label_carrier_preview"]
    assert initial_carriers[0]["format"] == "MAT"
    assert "classlabel" in initial_carriers[0]["label_candidates"]
    assert "cue_onset" in initial_carriers[0]["anchor_candidates"]

    reviewed_carrier = reviewed_preview.diagnostics["preview"]["label_carrier_preview"][
        0
    ]
    assert reviewed_carrier["selected_label_field"] == "classlabel"
    assert reviewed_carrier["selected_anchor"] == "cue_onset"
    assert reviewed_carrier["time_model"] == "sample_index"
    assert reviewed_carrier["granularity"] == "trial"
    assert reviewed_carrier["role"] == "class cue labels"

    applied = apply_result.diagnostics["applied_interpretation"]
    assert applied["label_carrier_plan"][0]["selected_label_field"] == "classlabel"
    assert applied["label_carrier_plan"][0]["selected_anchor"] == "cue_onset"
    assert applied["label_carrier_plan"][0]["role"] == "class cue labels"
    assert applied["event_roles"]["cue_onset"] == "trial anchor"
    recipe = save_result.diagnostics["recipe"]
    assert recipe["label_carrier_plan"][0]["path"] == str(label_path)
    assert recipe["label_carrier_plan"][0]["selected_label_field"] == "classlabel"
    assert recipe["label_carrier_plan"][0]["selected_anchor"] == "cue_onset"
    assert recipe["label_carrier_plan"][0]["role"] == "class cue labels"
    assert recipe["event_roles"]["cue_onset"] == "trial anchor"
    assert "choices:label_carriers" in recipe["recipe_trace"]
    assert "choices:event_roles" in recipe["recipe_trace"]


def test_data_interpretation_state_snapshot_preserves_import_review_truth(tmp_path):
    from scipy.io import savemat

    source_dir = tmp_path / "reviewed_state_truth"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(label_path, {"classlabel": [1, 2], "cue_onset": [100, 200]})
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "anchor": "cue_onset",
                        "time_model": "sample_index",
                        "granularity": "trial",
                    },
                },
                "class_map": {"1": "left hand", "2": "right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    query_result = service.execute(QueryStateCommand(query="state"))

    interpretation = apply_result.state.interpretation
    assert interpretation.label_carrier_plan[0]["path"] == str(label_path)
    assert interpretation.label_carrier_plan[0]["selected_label_field"] == "classlabel"
    assert interpretation.label_carrier_plan[0]["selected_anchor"] == "cue_onset"
    assert interpretation.class_map == {"1": "left hand", "2": "right hand"}
    assert (
        interpretation.event_roles["label_carrier"] == "external label or event source"
    )
    capabilities = {item["name"]: item for item in interpretation.format_capabilities}
    assert capabilities["A01T.gdf"]["status"] == "needs_review"
    assert capabilities["A01T.mat"]["format"] == "MAT labels"

    state_payload = query_result.diagnostics["state"]["interpretation"]
    assert state_payload["label_carrier_plan"] == interpretation.label_carrier_plan
    assert state_payload["format_capabilities"] == interpretation.format_capabilities
    assert state_payload["class_map"] == interpretation.class_map
    assert state_payload["event_roles"] == interpretation.event_roles


def test_data_interpretation_scan_reports_format_capability_boundaries(tmp_path):
    source_dir = tmp_path / "mixed_format_source"
    source_dir.mkdir()
    files = {
        "A01T.gdf": b"gdf placeholder",
        "physionet.edf": b"edf placeholder",
        "eeglab.set": b"set placeholder",
        "brainvision.vhdr": b"vhdr placeholder",
        "brainvision.vmrk": b"vmrk placeholder",
        "labels.mat": b"mat placeholder",
        "events.tsv": b"onset\ttrial_type\n0.0\tleft\n",
        "lsl_recording.xdf": b"xdf placeholder",
    }
    for name, content in files.items():
        (source_dir / name).write_bytes(content)
    service = ApplicationService(Study())

    scan = service.execute(ScanSourceCommand(source_path=str(source_dir)))
    preview = service.execute(PreviewInterpretationCommand())

    capabilities = {
        item["name"]: item
        for item in scan.diagnostics["scan_result"]["format_capabilities"]
    }

    assert capabilities["A01T.gdf"]["format"] == "GDF"
    assert capabilities["A01T.gdf"]["status"] == "needs_review"
    assert "trial anchor" in capabilities["A01T.gdf"]["message"]
    assert capabilities["physionet.edf"]["format"] == "EDF"
    assert "annotations" in capabilities["physionet.edf"]["message"]
    assert capabilities["eeglab.set"]["format"] == "EEGLAB"
    assert "boundary" in capabilities["eeglab.set"]["message"]
    assert capabilities["brainvision.vhdr"]["format"] == "BrainVision"
    assert "stimulus" in capabilities["brainvision.vhdr"]["message"]
    assert capabilities["labels.mat"]["format"] == "MAT labels"
    assert capabilities["events.tsv"]["format"] == "BIDS events"
    assert capabilities["lsl_recording.xdf"]["status"] == "blocked"
    assert (
        "XDF / LSL stream selection is not available"
        in capabilities["lsl_recording.xdf"]["message"]
    )
    assert (
        preview.diagnostics["preview"]["format_capabilities"]
        == scan.diagnostics["scan_result"]["format_capabilities"]
    )


def test_apply_interpretation_applies_reviewed_timestamp_label_carrier(tmp_path):
    source_dir = tmp_path / "reviewed_bids_events"
    source_dir.mkdir()
    eeg_path = source_dir / "sub-01_task-mi_raw.fif"
    events_path = source_dir / "events.tsv"
    eeg_path.write_bytes(b"not loaded during scan")
    events_path.write_text(
        "onset\tduration\ttrial_type\n0.5\t0.1\tleft\n1.5\t0.1\tright\n",
        encoding="utf-8",
    )
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_filepath.return_value = str(eeg_path)
    raw.get_filename.return_value = eeg_path.name
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
    service.dataset.apply_labels_batch = MagicMock(return_value=1)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                    }
                },
                "class_map": {"left": "left hand", "right": "right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    label_map = service.dataset.apply_labels_batch.call_args.args[1]
    assert list(label_map) == [str(events_path)]
    assert label_map[str(events_path)] == [
        {"onset": 0.5, "label": "left", "duration": 0.1},
        {"onset": 1.5, "label": "right", "duration": 0.1},
    ]
    assert service.dataset.apply_labels_batch.call_args.args[2] == {
        str(eeg_path): str(events_path)
    }
    assert service.dataset.apply_labels_batch.call_args.args[3] == {
        "left": "left hand",
        "right": "right hand",
    }
    assert apply_result.state.interpretation.label_import_count == 1
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "timestamp"
    assert (
        "label_import:timestamp:1"
        in apply_result.diagnostics["applied_interpretation"]["recipe_trace"]
    )


def test_apply_interpretation_applies_reviewed_timestamp_label_carriers_by_stem(
    tmp_path,
):
    source_dir = tmp_path / "reviewed_bids_multi_events"
    source_dir.mkdir()
    eeg_1 = source_dir / "sub-01_task-mi_run-1_raw.fif"
    eeg_2 = source_dir / "sub-01_task-mi_run-2_raw.fif"
    events_1 = source_dir / "sub-01_task-mi_run-1_events.tsv"
    events_2 = source_dir / "sub-01_task-mi_run-2_events.tsv"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    events_1.write_text(
        "onset\tduration\ttrial_type\n0.5\t0.1\tleft\n",
        encoding="utf-8",
    )
    events_2.write_text(
        "onset\tduration\ttrial_type\n1.5\t0.1\tright\n",
        encoding="utf-8",
    )
    service = ApplicationService(Study())
    raw_1 = _raw_mock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_1.get_filename.return_value = eeg_1.name
    raw_2 = _raw_mock()
    raw_2.get_filepath.return_value = str(eeg_2)
    raw_2.get_filename.return_value = eeg_2.name
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])
    service.dataset.apply_labels_batch = MagicMock(return_value=2)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(events_1): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                    },
                    str(events_2): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                    },
                },
                "class_map": {"left": "left hand", "right": "right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["success_count"] == 2
    args = service.dataset.apply_labels_batch.call_args.args
    assert args[0] == [raw_1, raw_2]
    assert set(args[1]) == {str(events_1), str(events_2)}
    assert args[1][str(events_1)] == [
        {"onset": 0.5, "label": "left", "duration": 0.1},
    ]
    assert args[1][str(events_2)] == [
        {"onset": 1.5, "label": "right", "duration": 0.1},
    ]
    assert args[2] == {str(eeg_1): str(events_1), str(eeg_2): str(events_2)}
    assert apply_result.state.interpretation.label_import_count == 1
    assert apply_result.state.interpretation.label_imports[0]["file_mapping"] == {
        str(eeg_1): str(events_1),
        str(eeg_2): str(events_2),
    }


def test_apply_interpretation_skips_ambiguous_multi_file_timestamp_labels(tmp_path):
    source_dir = tmp_path / "ambiguous_multi_events"
    source_dir.mkdir()
    eeg_1 = source_dir / "sub-01_task-mi_run-1_raw.fif"
    eeg_2 = source_dir / "sub-01_task-mi_run-2_raw.fif"
    events = source_dir / "events.tsv"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    events.write_text("onset\ttrial_type\n0.5\tleft\n", encoding="utf-8")
    service = ApplicationService(Study())
    raw_1 = _raw_mock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_2 = _raw_mock()
    raw_2.get_filepath.return_value = str(eeg_2)
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])
    service.dataset.apply_labels_batch = MagicMock(return_value=2)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(events): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                    },
                },
                "class_map": {"left": "left hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "skipped"
    assert (
        "No reviewed label carrier uniquely matches"
        in apply_result.diagnostics["label_apply"]["reason"]
    )
    service.dataset.apply_labels_batch.assert_not_called()


def test_apply_interpretation_applies_manually_mapped_generic_timestamp_label(
    tmp_path,
):
    source_dir = tmp_path / "manual_timestamp_mapping"
    source_dir.mkdir()
    eeg_1 = source_dir / "sub-01_task-mi_run-1_raw.fif"
    eeg_2 = source_dir / "sub-01_task-mi_run-2_raw.fif"
    events = source_dir / "events.tsv"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    events.write_text("onset\ttrial_type\n0.5\tleft\n", encoding="utf-8")
    service = ApplicationService(Study())
    raw_1 = _raw_mock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_1.get_filename.return_value = eeg_1.name
    raw_2 = _raw_mock()
    raw_2.get_filepath.return_value = str(eeg_2)
    raw_2.get_filename.return_value = eeg_2.name
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])
    service.dataset.apply_labels_batch = MagicMock(return_value=1)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(events): {
                        "target_file": eeg_2.name,
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                    },
                },
                "class_map": {"left": "left hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["success_count"] == 1
    args = service.dataset.apply_labels_batch.call_args.args
    assert args[0] == [raw_2]
    assert args[2] == {str(eeg_2): str(events)}
    assert apply_result.state.interpretation.label_imports[0]["target_files"] == [
        str(eeg_2)
    ]


def test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier(tmp_path):
    from scipy.io import savemat

    source_dir = tmp_path / "reviewed_mat_sequence"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(label_path, {"classlabel": np.array([1, 2, 1, 2])})
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_filepath.return_value = str(eeg_path)
    raw.get_filename.return_value = eeg_path.name
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
    service.dataset.apply_labels_legacy = MagicMock(return_value=1)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "anchor": "trial order",
                        "time_model": "trial_order",
                        "granularity": "trial",
                    }
                },
                "class_map": {"1": "left hand", "2": "right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["mode"] == "legacy"
    args = service.dataset.apply_labels_legacy.call_args.args
    assert args[0] == [raw]
    np.testing.assert_array_equal(args[1], np.array([1, 2, 1, 2]))
    assert args[2] == {1: "left hand", 2: "right hand"}
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "legacy"
    assert (
        "label_import:legacy:1"
        in apply_result.diagnostics["applied_interpretation"]["recipe_trace"]
    )


def test_apply_interpretation_applies_reviewed_mat_sample_anchor_label_carrier(
    tmp_path,
):
    from scipy.io import savemat

    source_dir = tmp_path / "reviewed_mat_sample_anchor"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(
        label_path,
        {
            "classlabel": np.array([1, 2, 1]),
            "cue_onset": np.array([100, 250, 400]),
        },
    )
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_filepath.return_value = str(eeg_path)
    raw.get_filename.return_value = eeg_path.name
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
    service.dataset.apply_labels_batch = MagicMock(return_value=1)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "anchor": "cue_onset",
                        "time_model": "sample_index",
                        "granularity": "trial",
                    }
                },
                "class_map": {"1": "left hand", "2": "right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["mode"] == "anchored"
    args = service.dataset.apply_labels_batch.call_args.args
    assert args[0] == [raw]
    np.testing.assert_array_equal(
        args[1][str(label_path)],
        np.array([[100, 0, 1], [250, 0, 2], [400, 0, 1]], dtype=np.int32),
    )
    assert args[2] == {str(eeg_path): str(label_path)}
    assert args[3] == {1: "left hand", 2: "right hand"}
    assert args[4] is None
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "anchored"
    assert (
        "label_import:anchored:1"
        in apply_result.diagnostics["applied_interpretation"]["recipe_trace"]
    )


def test_apply_interpretation_applies_reviewed_sequence_label_carriers_by_stem(
    tmp_path,
):
    from scipy.io import savemat

    source_dir = tmp_path / "reviewed_mat_sequence_multi"
    source_dir.mkdir()
    eeg_1 = source_dir / "A01T.gdf"
    eeg_2 = source_dir / "B01T.gdf"
    label_1 = source_dir / "A01T.mat"
    label_2 = source_dir / "B01T.mat"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    savemat(label_1, {"classlabel": np.array([1, 2])})
    savemat(label_2, {"classlabel": np.array([2, 1])})
    service = ApplicationService(Study())
    raw_1 = _raw_mock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_1.get_filename.return_value = eeg_1.name
    raw_2 = _raw_mock()
    raw_2.get_filepath.return_value = str(eeg_2)
    raw_2.get_filename.return_value = eeg_2.name
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])
    service.dataset.apply_labels_legacy = MagicMock(side_effect=[1, 1])

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_1): {
                        "label_field": "classlabel",
                        "anchor": "trial order",
                        "time_model": "trial_order",
                        "granularity": "trial",
                    },
                    str(label_2): {
                        "label_field": "classlabel",
                        "anchor": "trial order",
                        "time_model": "trial_order",
                        "granularity": "trial",
                    },
                },
                "class_map": {"1": "left hand", "2": "right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["success_count"] == 2
    calls = service.dataset.apply_labels_legacy.call_args_list
    assert len(calls) == 2
    assert calls[0].args[0] == [raw_1]
    np.testing.assert_array_equal(calls[0].args[1], np.array([1, 2]))
    assert calls[1].args[0] == [raw_2]
    np.testing.assert_array_equal(calls[1].args[1], np.array([2, 1]))
    assert apply_result.state.interpretation.label_imports[0]["file_mapping"] == {
        str(eeg_1): str(label_1),
        str(eeg_2): str(label_2),
    }


def test_apply_interpretation_skips_ambiguous_multi_file_sequence_labels(tmp_path):
    from scipy.io import savemat

    source_dir = tmp_path / "ambiguous_sequence_multi"
    source_dir.mkdir()
    eeg_1 = source_dir / "A01T.gdf"
    eeg_2 = source_dir / "B01T.gdf"
    labels = source_dir / "labels.mat"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    savemat(labels, {"classlabel": np.array([1, 2, 1, 2])})
    service = ApplicationService(Study())
    raw_1 = _raw_mock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_2 = _raw_mock()
    raw_2.get_filepath.return_value = str(eeg_2)
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])
    service.dataset.apply_labels_legacy = MagicMock(return_value=2)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(labels): {
                        "label_field": "classlabel",
                        "anchor": "trial order",
                        "time_model": "trial_order",
                        "granularity": "trial",
                    },
                },
                "class_map": {"1": "left hand", "2": "right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "skipped"
    assert (
        "No reviewed label carrier uniquely matches"
        in apply_result.diagnostics["label_apply"]["reason"]
    )
    service.dataset.apply_labels_legacy.assert_not_called()


def test_apply_interpretation_applies_manually_mapped_generic_sequence_label(
    tmp_path,
):
    from scipy.io import savemat

    source_dir = tmp_path / "manual_sequence_mapping"
    source_dir.mkdir()
    eeg_1 = source_dir / "A01T.gdf"
    eeg_2 = source_dir / "B01T.gdf"
    labels = source_dir / "labels.mat"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    savemat(labels, {"classlabel": np.array([1, 2])})
    service = ApplicationService(Study())
    raw_1 = _raw_mock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_1.get_filename.return_value = eeg_1.name
    raw_2 = _raw_mock()
    raw_2.get_filepath.return_value = str(eeg_2)
    raw_2.get_filename.return_value = eeg_2.name
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])
    service.dataset.apply_labels_legacy = MagicMock(return_value=1)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(labels): {
                        "target_file": str(eeg_1),
                        "label_field": "classlabel",
                        "anchor": "trial order",
                        "time_model": "trial_order",
                        "granularity": "trial",
                    },
                },
                "class_map": {"1": "left hand", "2": "right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["success_count"] == 1
    call = service.dataset.apply_labels_legacy.call_args
    assert call.args[0] == [raw_1]
    assert apply_result.state.interpretation.label_imports[0]["file_mapping"] == {
        str(eeg_1): str(labels)
    }


def test_data_interpretation_blocks_sources_without_eeg_files(tmp_path):
    source_dir = tmp_path / "labels_only"
    source_dir.mkdir()
    (source_dir / "labels.csv").write_text("label\n1\n2\n", encoding="utf-8")
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    scan = service.execute(ScanSourceCommand(source_path=str(source_dir)))
    preview = service.execute(PreviewInterpretationCommand())
    validation = service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan.ok is True
    assert preview.ok is True
    assert validation.ok is True
    assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.PRECONDITION
    assert "blocked" in apply_result.message.lower()
    service.dataset.import_files.assert_not_called()


def test_data_interpretation_recipe_save_and_reload_rescans_without_apply(tmp_path):
    source_dir = tmp_path / "simple_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    recipe_path = tmp_path / "recipe.json"
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(PreviewInterpretationCommand())
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    save_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert apply_result.ok is True
    assert save_result.ok is True
    assert recipe_path.exists()
    assert save_result.state.interpretation.has_recipe is True

    fresh_service = ApplicationService(Study())
    fresh_service.dataset.import_files = MagicMock(return_value=(1, []))
    reload_result = fresh_service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert reload_result.ok is True
    assert reload_result.diagnostics["recipe"]["source_path"] == str(source_dir)
    assert reload_result.diagnostics["scan_result"]["eeg_files"] == [str(eeg_path)]
    assert reload_result.state.interpretation.has_recipe is True
    assert reload_result.state.interpretation.has_applied_interpretation is False
    fresh_service.dataset.import_files.assert_not_called()


def test_preprocess_capability_requires_raw_data_not_existing_preprocessed_copy():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = []

    policy = service.get_capabilities()

    assert policy.get(CommandName.PREPROCESS).available is True
    assert policy.get(CommandName.CREATE_EPOCH).available is False
    assert (
        "Preprocess data before creating epochs"
        in (policy.get(CommandName.CREATE_EPOCH).reasons[0])
    )


def test_evaluate_command_returns_typed_service_backed_summary():
    service = ApplicationService(Study())
    run = MagicMock()
    run.is_finished.return_value = False
    plan = MagicMock()
    plan.get_name.return_value = "Plan A"
    plan.get_plans.return_value = [run]
    service.study.training_manager.trainer = MagicMock()
    service.evaluation.get_plans = MagicMock(return_value=[plan])

    result = service.execute(EvaluateCommand())

    assert result.ok is True
    assert result.command_name == "evaluate"
    assert result.diagnostics["payload_type"] == "evaluation_summary"
    assert result.diagnostics["available"] is False
    assert result.diagnostics["plan_count"] == 1
    assert result.state.last_error is None


def test_visualize_and_saliency_commands_return_typed_query_payloads():
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = MagicMock()
    service.study.training_manager.model_holder = MagicMock()
    service.study.training_manager.training_option = MagicMock()

    visualize = service.execute(VisualizeCommand(view="summary"))
    saliency = service.execute(SaliencyCommand())

    assert visualize.ok is True
    assert visualize.command_name == "visualize"
    assert visualize.diagnostics["payload_type"] == "visualization_summary"
    assert visualize.diagnostics["available"] is True
    assert "available_views" in visualize.diagnostics
    assert saliency.ok is True
    assert saliency.command_name == "saliency"
    assert saliency.diagnostics["payload_type"] == "saliency_summary"
    assert saliency.diagnostics["action"] == "query"
    assert saliency.diagnostics["saliency_configured"] is False


def test_saliency_command_can_configure_params():
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = MagicMock()
    service.study.training_manager.training_option = MagicMock()

    result = service.execute(SaliencyCommand(params={"method": "Gradient"}))

    assert result.ok is True
    assert result.changed_state.visualization_changed is True
    assert result.diagnostics["action"] == "configure"
    assert result.diagnostics["saliency_configured"] is True
    assert result.diagnostics["saliency_available"] is False
    assert set(result.diagnostics["params"]) == {
        "SmoothGrad",
        "SmoothGrad_Squared",
        "VarGrad",
    }


def test_saliency_command_normalizes_flat_method_params():
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = MagicMock()
    service.study.training_manager.training_option = MagicMock()

    result = service.execute(
        SaliencyCommand(
            method="Gradient",
            params={
                "nt_samples": 2,
                "nt_samples_batch_size": 1,
                "stdevs": 1.0,
            },
        ),
    )

    assert result.ok is True
    assert result.diagnostics["requested_method"] == "Gradient"
    params = result.diagnostics["params"]
    for method in ("SmoothGrad", "SmoothGrad_Squared", "VarGrad"):
        assert params[method]["nt_samples"] == 2
        assert params[method]["nt_samples_batch_size"] == 1
        assert params[method]["stdevs"] == 1.0


def test_command_result_classifies_unsupported_load(tmp_path):
    service = ApplicationService(Study())
    unsupported_path = tmp_path / "sample.unsupported"
    unsupported_path.write_text("not eeg", encoding="utf-8")

    result = service.execute(LoadDataCommand(paths=[str(unsupported_path)]))

    assert result.failed is True
    assert result.ok is False
    assert result.command_name == "load_data"
    assert result.error_type == ErrorType.UNSUPPORTED_FORMAT
    assert result.recoverable is True
    assert result.state.last_error is not None
    assert result.state.last_error.error_type == "unsupported_format"
    assert result.changed_state.error_changed is True


def test_execute_returns_failure_result_for_unsupported_command_object():
    service = ApplicationService(Study())

    result = service.execute(cast(Any, object()))

    assert result.failed is True
    assert result.command_name == "unsupported_command"
    assert result.error_type == ErrorType.UNSUPPORTED_COMMAND
    assert "Unsupported command object" in result.message
    assert result.state.last_error is not None
    assert result.state.last_error.error_type == "unsupported_command"
    assert result.changed_state.error_changed is True


def test_successful_command_clears_previous_last_error():
    service = ApplicationService(Study())

    failed_result = service.execute(TrainCommand())
    assert failed_result.failed is True
    assert failed_result.state.last_error is not None

    reset_result = service.execute(ResetSessionCommand())

    assert reset_result.ok is True
    assert reset_result.state.last_error is None
    assert reset_result.changed_state.error_changed is True


def test_read_only_query_does_not_clear_previous_last_error():
    service = ApplicationService(Study())

    failed_result = service.execute(TrainCommand())
    assert failed_result.failed is True
    assert failed_result.state.last_error is not None

    query_result = service.execute(QueryStateCommand(query="state"))

    assert query_result.ok is True
    assert query_result.state.last_error == failed_result.state.last_error
    assert query_result.changed_state.error_changed is False


def test_train_command_blocked_until_backend_ready():
    service = ApplicationService(Study())

    result = service.execute(TrainCommand())

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Generate datasets before training" in result.message
    assert result.state.training.has_trainer is False


def test_train_command_requires_confirmation_before_long_running_start():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.loaded_data_list = [raw]
    cast(Any, service.study).datasets = [object()]
    cast(Any, service.study).model_holder = object()
    cast(Any, service.study).training_option = object()
    service.training.start_training = MagicMock()

    result = service.execute(TrainCommand())
    confirmed = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.CONFIRMATION_REQUIRED
    assert confirmed.ok is True
    service.training.start_training.assert_called_once_with(
        append=True,
        interactive=True,
    )


def test_every_declared_command_returns_result_envelope():
    service = ApplicationService(Study())
    commands = [
        LoadDataCommand(paths=[]),
        AttachLabelsCommand(mapping={}),
        ImportLabelsCommand(plan=LabelImportPlan(label_map={"labels": [1]})),
        UpdateMetadataCommand(index=0, subject="S01"),
        ApplySmartParseCommand(results={"/tmp/sample.fif": ("S01", "001")}),
        RemoveFilesCommand(indices=[0]),
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=1,
            high_freq=40,
        ),
        CreateEpochCommand(t_min=0, t_max=1),
        GenerateDatasetCommand(),
        ClearDatasetsCommand(),
        ConfigureTrainingCommand(model_name="EEGNet"),
        TrainCommand(),
        EvaluateCommand(),
        VisualizeCommand(),
        SaliencyCommand(),
        StopTrainingCommand(),
        ClearTrainingHistoryCommand(),
        ScanSourceCommand(source_path=""),
        PreviewInterpretationCommand(),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(),
        SaveInterpretationRecipeCommand(recipe_path=""),
        ReloadInterpretationRecipeCommand(recipe_path=""),
        ApplyMontageCommand(channels=["Cz"], positions=[(0.0, 0.0, 0.0)]),
        QueryStateCommand(),
        ResetPreprocessCommand(),
        ResetSessionCommand(),
        NewSessionCommand(),
    ]

    seen = set()
    for command in commands:
        result = service.execute(command)
        seen.add(result.command_name)
        assert result.command_name
        assert result.status.value in {"ok", "failed"}
        assert result.state is not None
        assert result.changed_state is not None

    assert seen == {name.value for name in CommandName}


def test_raw_mutation_commands_block_after_epoch_without_side_effects():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.dataset.remove_files = MagicMock()

    result = service.execute(RemoveFilesCommand(indices=[0]))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Reset the session" in result.message
    service.dataset.remove_files.assert_not_called()


def test_apply_interpretation_blocks_after_epoch_without_import_side_effect(
    tmp_path,
):
    source_dir = tmp_path / "new_source"
    source_dir.mkdir()
    eeg_path = source_dir / "sub-02_task-mi_raw.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(PreviewInterpretationCommand())
    validation = service.execute(ValidateInterpretationCommand())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    policy = service.get_capabilities()

    result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert validation.ok is True
    assert policy.get(CommandName.APPLY_INTERPRETATION).available is False
    assert "Reset the session" in " ".join(
        policy.get(CommandName.APPLY_INTERPRETATION).reasons,
    )
    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Reset the session" in result.message
    service.dataset.import_files.assert_not_called()


def test_generate_dataset_blocks_when_dataset_already_exists():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.study.data_manager.datasets = [MagicMock()]

    result = service.execute(GenerateDatasetCommand())

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "new session" in result.message


def test_generate_dataset_blocks_while_training_is_running():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.training.is_training = MagicMock(return_value=True)

    result = service.execute(GenerateDatasetCommand())

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Stop training before changing data splitting." in result.message


def test_clear_datasets_blocks_while_training_is_running():
    service = ApplicationService(Study())
    service.study.data_manager.datasets = [MagicMock()]
    service.training.is_training = MagicMock(return_value=True)
    service.training.clean_datasets = MagicMock()

    result = service.execute(ClearDatasetsCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Stop training before clearing generated datasets." in result.message
    service.training.clean_datasets.assert_not_called()


def test_generate_dataset_fails_when_split_audit_has_empty_or_leaking_splits():
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = MagicMock()
    leaking = MagicMock()
    leaking.get_name.return_value = "bad_split"
    leaking.train_mask = np.array([True, True, False])
    leaking.val_mask = np.array([False, True, False])
    leaking.test_mask = np.array([False, False, False])
    service.training.apply_data_splitting = MagicMock(
        side_effect=lambda _generator: setattr(
            service.study.data_manager,
            "datasets",
            [leaking],
        ),
    )

    result = service.execute(
        GenerateDatasetCommand(generator=MagicMock(), split_strategy="trial"),
    )

    assert result.failed is True
    assert result.error_type == ErrorType.DATA_MISMATCH
    assert "split audit" in result.message
    assert result.state.dataset.available is False
    assert result.state.dataset.generator_exists is False
    assert result.state.training.has_trainer is False
    assert result.diagnostics["rolled_back"] is True
    assert result.diagnostics["split_audit"]["ok"] is False
    assert any(
        "split is empty" in issue["message"]
        for issue in result.diagnostics["split_audit"]["issues"]
    )
    train = service.execute(TrainCommand())
    assert train.failed is True
    assert "Generate datasets before training" in train.message


def test_generate_dataset_rolls_back_partial_apply_failure():
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = MagicMock()
    partial_dataset = MagicMock()
    partial_generator = MagicMock()
    partial_trainer = MagicMock()

    def fail_after_partial_mutation(_generator):
        service.study.data_manager.datasets = [partial_dataset]
        service.study.data_manager.dataset_generator = partial_generator
        service.study.training_manager.trainer = partial_trainer
        raise RuntimeError("split worker crashed")

    service.training.apply_data_splitting = MagicMock(
        side_effect=fail_after_partial_mutation,
    )

    result = service.execute(GenerateDatasetCommand(generator=MagicMock()))

    assert result.failed is True
    assert result.state.dataset.available is False
    assert result.state.dataset.generator_exists is False
    assert result.state.training.has_trainer is False
    assert result.changed_state.datasets_changed is False
    assert result.changed_state.training_changed is False
    assert result.changed_state.error_changed is True


def test_generate_dataset_audits_custom_trial_generator_as_trial_protocol():
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = MagicMock()
    dataset = MagicMock()
    dataset.get_name.return_value = "trial_split"
    dataset.train_mask = np.array([True, False, False])
    dataset.val_mask = np.array([False, True, False])
    dataset.test_mask = np.array([False, False, True])
    service.training.apply_data_splitting = MagicMock(
        side_effect=lambda _generator: setattr(
            service.study.data_manager,
            "datasets",
            [dataset],
        ),
    )
    splitter = MagicMock()
    splitter.split_type = SplitByType.TRIAL
    generator = MagicMock()
    generator.test_splitter_list = [splitter]

    result = service.execute(GenerateDatasetCommand(generator=generator))

    assert result.ok is True
    assert result.diagnostics["protocol"] == "trial-wise"
    assert result.state.dataset.available is True


def test_reset_preprocess_command_clears_downstream_training_plan():
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_preprocess_history.return_value = ["filter"]
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.study.data_manager.datasets = [MagicMock()]
    service.study.training_manager.trainer = MagicMock()
    service.study.reset_preprocess = MagicMock(
        side_effect=lambda force_update: setattr(
            service.study.data_manager,
            "epoch_data",
            None,
        ),
    )
    service.training.clean_datasets = MagicMock(
        side_effect=lambda force_update: (
            setattr(service.study.data_manager, "datasets", []),
            setattr(service.study.training_manager, "trainer", None),
        ),
    )

    unconfirmed = service.execute(ResetPreprocessCommand())
    assert unconfirmed.failed is True
    assert unconfirmed.error_type == ErrorType.CONFIRMATION_REQUIRED

    result = service.execute(ResetPreprocessCommand(confirmed=True))

    assert result.ok is True
    assert result.state.epoch.available is False
    assert result.state.dataset.available is False
    assert result.state.training.has_trainer is False
    assert result.diagnostics["trainer_cleared"] is True


def test_clear_datasets_and_training_history_commands_route_cleanup():
    service = ApplicationService(Study())
    service.study.data_manager.datasets = [MagicMock()]
    service.training.clean_datasets = MagicMock()

    clear_datasets = service.execute(ClearDatasetsCommand(confirmed=True))

    assert clear_datasets.ok is True
    service.training.clean_datasets.assert_called_once_with(force_update=True)

    trainer = MagicMock()
    trainer.is_running.return_value = False
    plan = MagicMock()
    service.evaluation.get_plans = MagicMock(return_value=[plan])
    service.study.training_manager.trainer = trainer
    service.training.clear_history = MagicMock()

    clear_history = service.execute(ClearTrainingHistoryCommand(confirmed=True))

    assert clear_history.ok is True
    service.training.clear_history.assert_called_once_with()


def test_evaluate_and_clear_history_block_when_trainer_has_no_plan_history():
    service = ApplicationService(Study())
    trainer = MagicMock()
    trainer.is_running.return_value = False
    trainer.get_training_plan_holders.return_value = []
    service.study.training_manager.trainer = trainer

    policy = service.get_capabilities()
    evaluate = service.execute(EvaluateCommand())
    clear_history = service.execute(ClearTrainingHistoryCommand(confirmed=True))

    assert policy.get(CommandName.EVALUATE).available is False
    assert policy.get(CommandName.CLEAR_TRAINING_HISTORY).available is False
    assert evaluate.failed is True
    assert evaluate.error_type == ErrorType.PRECONDITION
    assert clear_history.failed is True
    assert clear_history.error_type == ErrorType.PRECONDITION


def test_blocked_query_and_lifecycle_commands_still_return_result_envelopes():
    service = ApplicationService(Study())

    for command in (
        EvaluateCommand(),
        VisualizeCommand(),
        SaliencyCommand(),
        ClearDatasetsCommand(),
        ClearTrainingHistoryCommand(),
        ResetPreprocessCommand(),
    ):
        result = service.execute(command)

        assert result.failed is True
        assert result.command_name == command.name.value
        assert result.error_type == ErrorType.PRECONDITION
        assert result.state is not None
        assert result.changed_state is not None


def test_metadata_update_command_routes_through_service():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.dataset.update_metadata = MagicMock()

    result = service.execute(UpdateMetadataCommand(index=0, subject="S01"))

    assert result.ok is True
    assert result.command_name == CommandName.UPDATE_METADATA.value
    assert result.diagnostics["success_count"] == 1
    service.dataset.update_metadata.assert_called_once_with(
        0,
        subject="S01",
        session=None,
    )


def test_import_labels_plan_routes_batch_import():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.dataset.apply_labels_batch = MagicMock(return_value=1)

    result = service.execute(
        ImportLabelsCommand(
            plan=LabelImportPlan(
                target_indices=[0],
                label_map={"labels.txt": [1, 2]},
                file_mapping={"/tmp/sample.fif": "labels.txt"},
                mapping={1: "left", 2: "right"},
                mode="batch",
            ),
        ),
    )

    assert result.ok is True
    assert result.diagnostics["success_count"] == 1
    service.dataset.apply_labels_batch.assert_called_once()


def test_import_labels_updates_applied_interpretation_recipe_trace(tmp_path):
    source_dir = tmp_path / "interpreted_with_external_labels"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    recipe_path = tmp_path / "recipe_with_labels.json"
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
    service.dataset.apply_labels_batch = MagicMock(return_value=1)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(PreviewInterpretationCommand())
    service.execute(ValidateInterpretationCommand())
    service.execute(ApplyInterpretationCommand(confirmed=True))
    service.study.data_manager.loaded_data_list = [raw]
    import_result = service.execute(
        ImportLabelsCommand(
            plan=LabelImportPlan(
                target_indices=[0],
                label_map={"labels.tsv": [1, 2]},
                file_mapping={"/tmp/sample.fif": "labels.tsv"},
                mapping={1: "left", 2: "right"},
                mode="batch",
                selected_event_names=["cue"],
            ),
        ),
    )
    save_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert import_result.ok is True
    assert import_result.diagnostics["recipe_updated"] is True
    label_import = import_result.diagnostics["label_import"]
    assert label_import["mode"] == "batch"
    assert label_import["label_carriers"] == ["labels.tsv"]
    assert label_import["selected_event_names"] == ["cue"]
    assert import_result.state.interpretation.label_carriers == ["labels.tsv"]
    assert import_result.state.interpretation.label_import_count == 1
    assert save_result.ok is True
    recipe = save_result.diagnostics["recipe"]
    assert recipe["label_carriers"] == ["labels.tsv"]
    assert recipe["label_imports"][0]["class_map"] == {"1": "left", "2": "right"}
    assert "label_import:batch:1" in recipe["recipe_trace"]


def test_apply_montage_command_routes_confirmed_positions():
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = MagicMock()
    service.preprocess.apply_montage = MagicMock()

    result = service.execute(
        ApplyMontageCommand(
            channels=["Cz"],
            positions=[(0.0, 0.0, 0.0)],
            montage_name="standard_1020",
        ),
    )

    assert result.ok is True
    assert result.command_name == CommandName.APPLY_MONTAGE.value
    service.preprocess.apply_montage.assert_called_once_with(
        ["Cz"],
        [(0.0, 0.0, 0.0)],
    )


def test_query_state_returns_typed_dataset_summary():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]

    result = service.execute(QueryStateCommand(query="data_summary"))

    assert result.ok is True
    assert result.diagnostics["count"] == 1
    assert result.diagnostics["metadata"][0]["subject"] == "S01"


def test_new_session_requires_confirmation_and_clears_single_backend_session():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]

    unconfirmed = service.execute(NewSessionCommand())

    assert unconfirmed.failed is True
    assert unconfirmed.error_type == ErrorType.CONFIRMATION_REQUIRED

    confirmed = service.execute(NewSessionCommand(confirmed=True))

    assert confirmed.ok is True
    assert confirmed.command_name == "new_session"
    assert confirmed.state.raw.loaded is False


def test_set_montage_preprocess_operation_requires_ui_confirmation():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.SET_MONTAGE,
            montage_name="standard_1020",
        ),
    )

    assert result.failed is True
    assert result.error_type == ErrorType.CONFIRMATION_REQUIRED
    assert "app confirmation path" in result.message


def _raw_mock():
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    raw.get_subject_name.return_value = "S01"
    raw.get_session_name.return_value = "001"
    raw.is_raw.return_value = True
    mne_raw = MagicMock()
    mne_raw.ch_names = ["C3", "C4"]
    mne_raw.annotations = []
    raw.get_mne.return_value = mne_raw
    return raw
