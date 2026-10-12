"""Application boundary: interpretation labels behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import mne
import numpy as np

from tests.unit.backend.application.application_test_support import (
    _class_value_decisions,
    _raw_mock,
    _use_test_raw_factory,
)
from tests.unit.backend.application.preprocess_test_support import (
    _minimal_raw,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CommandName,
    ErrorType,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    ReviewInterpretationCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    data_interpretation_internal_events,
)
from XBrainLab.backend.application.workflow_projection import build_workflow_projection
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.study import Study


def _raw_with_event_codes(filepath: Path, event_codes: list[int]) -> Raw:
    """Build a real Raw wrapper with deterministic reviewed EEG triggers."""
    raw = _minimal_raw(filepath)
    events = np.asarray(
        [[index * 100, 0, code] for index, code in enumerate(event_codes)],
        dtype=int,
    )
    raw.set_event(
        events,
        {str(code): code for code in dict.fromkeys(event_codes)},
    )
    return raw


def test_data_interpretation_unresolved_sequence_target_cannot_be_confirmed(tmp_path):
    source_dir = tmp_path / "gdf_with_external_labels"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_bytes(b"not loaded during scan")
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)

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
    confirmation_text = " ".join(
        preview.diagnostics["preview"]["confirmation_items"]
    ).lower()
    assert "label placement" in confirmation_text
    assert "explicit target eeg event" in confirmation_text
    assert "trial anchors" not in confirmation_text
    assert validation.ok is True
    [carrier] = preview.diagnostics["candidate"]["label_carrier_plan"]
    assert carrier["placement_review"]["status"] == "blocked"
    assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
    assert validation.state.interpretation.validation_decision == "blocked"

    assert unconfirmed_apply.failed is True
    assert unconfirmed_apply.error_type == ErrorType.PRECONDITION
    assert confirmed_apply.failed is True
    assert confirmed_apply.error_type == ErrorType.PRECONDITION
    assert "explicit target EEG event" in confirmed_apply.message
    load.assert_not_called()
    assert confirmed_apply.state.interpretation.has_applied_interpretation is False


def test_data_interpretation_review_command_scans_previews_and_validates(tmp_path):
    source_dir = tmp_path / "review_command"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during review")
    label_path.write_bytes(b"not loaded during review")
    service = ApplicationService(Study())

    review = service.execute(
        ReviewInterpretationCommand(source_path=str(source_dir)),
    )

    assert review.ok is True
    assert review.command_name == CommandName.REVIEW_INTERPRETATION.value
    assert review.changed_state.interpretation_changed is True
    assert review.state.raw.loaded is False
    assert review.diagnostics["payload_type"] == "interpretation_review"
    assert review.diagnostics["scan_result"]["eeg_files"] == [str(eeg_path)]
    assert review.diagnostics["preview"]["label_carrier_count"] == 1
    assert review.diagnostics["candidate"]["candidate_id"]
    assert review.diagnostics["validation_decision"]["decision"] in {
        "safe",
        "needs_confirmation",
        "blocked",
    }


def test_data_interpretation_choices_flow_into_recipe(tmp_path):
    source_dir = tmp_path / "reviewed_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    recipe_path = tmp_path / "reviewed_recipe.json"
    service = ApplicationService(Study())
    _use_test_raw_factory(service)

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
                "label_carrier": "embedded_events",
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


def test_safe_data_interpretation_cannot_be_applied_twice(tmp_path):
    source_dir = tmp_path / "safe_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    service = ApplicationService(Study())
    load_raw = _use_test_raw_factory(service)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    eeg_path.name: {
                        "subject": "subject01",
                        "session": "session-01",
                        "task": "rest",
                        "run": "1",
                    }
                }
            }
        )
    )
    validation = service.execute(ValidateInterpretationCommand())
    first_apply = service.execute(ApplyInterpretationCommand(confirmed=True))
    apply_capability = service.get_capabilities().get(CommandName.APPLY_INTERPRETATION)
    second_apply = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert validation.ok is True
    assert validation.state.interpretation.validation_decision == "safe"
    assert first_apply.ok is True
    assert first_apply.state.interpretation.has_applied_interpretation is True
    assert apply_capability.available is False
    assert "Interpretation has already been applied." in apply_capability.reasons
    assert second_apply.failed is True
    assert second_apply.error_type == ErrorType.PRECONDITION
    assert load_raw.call_count == 1


def test_safe_recipe_reload_replaces_the_applied_candidate_in_same_service(tmp_path):
    source_dir = tmp_path / "safe_reload_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    recipe_path = tmp_path / "safe_reload_recipe.json"
    service = ApplicationService(Study())
    load_raw = _use_test_raw_factory(service)

    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    assert service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    eeg_path.name: {
                        "subject": "subject01",
                        "session": "session-01",
                        "task": "rest",
                        "run": "1",
                    }
                }
            }
        )
    ).ok
    assert service.execute(ValidateInterpretationCommand()).ok
    first_apply = service.execute(ApplyInterpretationCommand(confirmed=True))
    assert first_apply.ok
    assert service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path))
    ).ok

    reload_result = service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )
    reloaded_state = reload_result.state
    reloaded_capabilities = service.get_capabilities()
    reloaded_projection = build_workflow_projection(
        reloaded_state,
        reloaded_capabilities,
    )
    retry_without_confirmation = service.execute(ApplyInterpretationCommand())
    replacement_apply = service.execute(ApplyInterpretationCommand(confirmed=True))
    duplicate_apply = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert reload_result.ok
    assert reloaded_state.interpretation.validation_decision == "safe"
    assert reloaded_state.interpretation.has_applied_interpretation is True
    assert reloaded_state.interpretation.has_pending_candidate is True
    assert reloaded_capabilities.get(CommandName.APPLY_INTERPRETATION).available is True
    assert (
        reloaded_capabilities.get(
            CommandName.APPLY_INTERPRETATION
        ).confirmation_required
        is True
    )
    assert reloaded_projection.recommended_command == CommandName.APPLY_INTERPRETATION
    assert retry_without_confirmation.failed
    assert retry_without_confirmation.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert replacement_apply.ok
    assert replacement_apply.state.interpretation.has_pending_candidate is False
    assert duplicate_apply.failed
    assert duplicate_apply.error_type is ErrorType.PRECONDITION
    assert load_raw.call_count == 2


def test_data_interpretation_preview_exposes_internal_event_evidence(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    eeg_path.write_bytes(b"not loaded during scan")
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "768": {"count": 288, "description": "768"},
                "769": {"count": 72, "description": "769"},
                "770": {"count": 72, "description": "770"},
                "1023": {"count": 15, "description": "1023"},
            }
        },
    )
    service = ApplicationService(Study())

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    result = service.execute(
        PreviewInterpretationCommand(
            choices={"label_carrier": "embedded_events"},
        )
    )

    preview_payload = result.diagnostics["preview"]["internal_event_preview"]
    candidate_payload = result.diagnostics["candidate"]["internal_event_preview"]

    assert preview_payload == candidate_payload
    assert preview_payload["source"] == "mne_internal_events"
    assert [row["event_code"] for row in preview_payload["candidate_label_events"]] == [
        "769",
        "770",
    ]
    assert preview_payload["candidate_label_events"][0]["event_count"] == 72
    assert [row["event_code"] for row in preview_payload["not_used_events"]] == [
        "768",
        "1023",
    ]


def test_data_interpretation_apply_updates_loaded_metadata(tmp_path):
    source_dir = tmp_path / "reviewed_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    service = ApplicationService(Study())

    loaded = _minimal_raw(eeg_path)
    _use_test_raw_factory(service, loaded)

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

    committed = service.study.data_manager.loaded_data_list[0]
    assert committed.get_subject_name() == "S01"
    assert committed.get_session_name() == "session-01"
    assert committed.get_runtime_detail("data_interpretation_metadata") == {
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
    raw = Raw(
        str(eeg_path),
        mne.io.RawArray(
            np.zeros((1, 500)),
            mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    _use_test_raw_factory(service, raw)

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
                        "sample_index_base": "zero_based",
                        "sample_index_origin": "recording_relative",
                        "granularity": "trial",
                        "role": "class cue labels",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    }
                },
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
    _use_test_raw_factory(service)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "anchor": "cue_onset",
                        "time_model": "sample_index",
                        "sample_index_base": "zero_based",
                        "sample_index_origin": "recording_relative",
                        "granularity": "trial",
                        "role": "class labels",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    },
                },
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
        "brainvision.vhdr": b"vhdr placeholder",
        "brainvision.vmrk": b"vmrk placeholder",
        "labels.mat": b"mat placeholder",
        "events.tsv": b"onset\ttrial_type\n0.0\tleft\n",
        "lsl_recording.xdf": b"xdf placeholder",
    }
    for name, content in files.items():
        (source_dir / name).write_bytes(content)
    from scipy.io import savemat

    savemat(
        source_dir / "eeglab.set",
        {
            "EEG": {
                "data": np.zeros((2, 16), dtype=np.float32),
                "nbchan": 2.0,
                "pnts": 16.0,
                "trials": 1.0,
                "srate": 128.0,
            }
        },
        do_compression=True,
    )
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
    assert capabilities["brainvision.vmrk"]["format"] == "BrainVision markers"
    assert capabilities["brainvision.vmrk"]["role"] == "sidecar"
    assert capabilities["labels.mat"]["format"] == "MAT labels"
    assert capabilities["events.tsv"]["format"] == "BIDS events"
    assert capabilities["lsl_recording.xdf"]["status"] == "blocked"
    assert (
        "XDF / LSL stream selection is not available"
        in capabilities["lsl_recording.xdf"]["message"]
    )
    preview_capabilities = {
        item["name"]: item
        for item in preview.diagnostics["preview"]["format_capabilities"]
    }
    assert "brainvision.vmrk" not in preview_capabilities
    assert "lsl_recording.xdf" not in preview_capabilities
    assert set(preview_capabilities) == {
        "A01T.gdf",
        "brainvision.vhdr",
        "eeglab.set",
        "events.tsv",
        "labels.mat",
        "physionet.edf",
    }


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
    raw = _minimal_raw(eeg_path)
    _use_test_raw_factory(service, raw)

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
                        "value_decisions": _class_value_decisions(
                            {"left": "left hand", "right": "right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    events, event_id = raw.get_event_list()
    np.testing.assert_array_equal(
        events,
        np.array([[50, 0, 1], [150, 0, 2]]),
    )
    assert event_id == {"left hand": 1, "right hand": 2}
    mne_raw = raw.get_mne()
    assert mne_raw is not None
    annotations = mne_raw.annotations
    assert annotations is not None
    np.testing.assert_allclose(annotations.onset, [0.5, 1.5])
    np.testing.assert_allclose(annotations.duration, [0.1, 0.1])
    assert list(annotations.description) == ["left hand", "right hand"]
    assert raw.is_labels_imported() is True
    assert apply_result.state.interpretation.label_import_count == 1
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "timestamp"
    assert (
        "label_import:timestamp:1"
        in apply_result.diagnostics["applied_interpretation"]["recipe_trace"]
    )


def test_apply_interpretation_converts_sample_index_csv_labels_to_seconds(tmp_path):
    source_dir = tmp_path / "reviewed_csv_sample_index"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    labels_path = source_dir / "A01T_events.csv"
    eeg_path.write_bytes(b"not loaded during scan")
    labels_path.write_text(
        "sample,duration,label\n128,64,left\n256,64,right\n",
        encoding="utf-8",
    )
    service = ApplicationService(Study())
    raw = _minimal_raw(eeg_path, sfreq=128.0)
    _use_test_raw_factory(service, raw)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(labels_path): {
                        "label_field": "label",
                        "anchor": "sample",
                        "duration_field": "duration",
                        "placement_method": "time_field",
                        "time_model": "sample_index",
                        "sample_index_base": "zero_based",
                        "sample_index_origin": "recording_relative",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"left": "left hand", "right": "right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    events, event_id = raw.get_event_list()
    np.testing.assert_array_equal(
        events,
        np.array([[128, 0, 1], [256, 0, 2]]),
    )
    assert event_id == {"left hand": 1, "right hand": 2}
    mne_raw = raw.get_mne()
    assert mne_raw is not None
    annotations = mne_raw.annotations
    assert annotations is not None
    np.testing.assert_allclose(annotations.onset, [1.0, 2.0])
    np.testing.assert_allclose(annotations.duration, [0.5, 0.5])
    assert list(annotations.description) == ["left hand", "right hand"]
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "timestamp"


def test_apply_interpretation_applies_reviewed_csv_tsv_event_order_labels(
    tmp_path,
    monkeypatch,
):
    for suffix, delimiter in (("csv", ","), ("tsv", "\t")):
        source_dir = tmp_path / f"reviewed_{suffix}_event_order"
        source_dir.mkdir()
        eeg_path = source_dir / "A01T.gdf"
        labels_path = source_dir / f"A01T_events.{suffix}"
        eeg_path.write_bytes(b"not loaded during scan")
        labels_path.write_text(
            delimiter.join(["onset", "duration", "classlabel"])
            + "\n"
            + delimiter.join(["0.5", "0.1", "1"])
            + "\n"
            + delimiter.join(["1.5", "0.1", "2"])
            + "\n",
            encoding="utf-8",
        )
        _patch_internal_events(
            monkeypatch,
            {"A01T.gdf": {"768": {"count": 2, "description": "trial start"}}},
        )
        service = ApplicationService(Study())
        raw = _raw_with_event_codes(eeg_path, [768, 768])
        _use_test_raw_factory(service, raw)

        service.execute(ScanSourceCommand(source_path=str(source_dir)))
        service.execute(
            PreviewInterpretationCommand(
                choices={
                    "label_carrier_choices": {
                        str(labels_path): {
                            "label_field": "classlabel",
                            "target_event_codes": ["768"],
                            "placement_method": "eeg_event",
                            "time_model": "trial_order",
                            "granularity": "trial",
                            "value_decisions": _class_value_decisions(
                                {"1": "left hand", "2": "right hand"}
                            ),
                        },
                    },
                },
            ),
        )
        service.execute(ValidateInterpretationCommand())
        apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert apply_result.ok is True
        assert apply_result.diagnostics["label_apply"]["mode"] == "sequence"
        assert apply_result.state.interpretation.label_imports[0][
            "selected_event_names"
        ] == ["768"]


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
    raw_1 = _minimal_raw(eeg_1)
    raw_2 = _minimal_raw(eeg_2)
    _use_test_raw_factory(
        service,
        {str(eeg_1): raw_1, str(eeg_2): raw_2},
    )

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
                        "value_decisions": _class_value_decisions(
                            {"left": "left hand"}
                        ),
                    },
                    str(events_2): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"right": "right hand"}
                        ),
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["success_count"] == 2
    first_events, first_event_id = raw_1.get_event_list()
    second_events, second_event_id = raw_2.get_event_list()
    np.testing.assert_array_equal(first_events, np.array([[50, 0, 1]]))
    np.testing.assert_array_equal(second_events, np.array([[150, 0, 1]]))
    assert first_event_id == {"left hand": 1}
    assert second_event_id == {"right hand": 1}
    assert raw_1.is_labels_imported() is True
    assert raw_2.is_labels_imported() is True
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
    load = _use_test_raw_factory(service)

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

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.PRECONDITION
    assert "Label carrier pairing is incomplete" in apply_result.message
    load.assert_not_called()
    assert apply_result.state.interpretation.has_applied_interpretation is False


def test_apply_interpretation_blocks_partial_manual_timestamp_label_mapping(
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
    load = _use_test_raw_factory(service)

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

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.PRECONDITION
    assert "Label carrier pairing is incomplete" in apply_result.message
    assert "task-mi_run-1_raw.fif" in apply_result.message
    assert "sub-01" not in apply_result.message
    assert "[SUBJECT_REF:" in apply_result.message
    load.assert_not_called()
    assert apply_result.state.interpretation.has_applied_interpretation is False


def test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "reviewed_mat_sequence"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(label_path, {"classlabel": np.array([1, 2, 1, 2])})
    _patch_internal_events(
        monkeypatch,
        {"A01T.gdf": {"768": {"count": 4, "description": "768"}}},
    )
    service = ApplicationService(Study())
    raw = _raw_with_event_codes(eeg_path, [768, 768, 768, 768])
    _use_test_raw_factory(service, raw)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["mode"] == "sequence"
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "sequence"
    assert (
        "label_import:sequence:1"
        in apply_result.diagnostics["applied_interpretation"]["recipe_trace"]
    )


def test_apply_interpretation_blocks_mixed_label_placement_modes(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "mixed_label_placement"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    second_eeg_path = source_dir / "B01T.gdf"
    sequence_labels = source_dir / "A01T.mat"
    timed_labels = source_dir / "B01T_events.tsv"
    eeg_path.write_bytes(b"not loaded during scan")
    second_eeg_path.write_bytes(b"not loaded during scan")
    savemat(sequence_labels, {"classlabel": np.array([1, 2])})
    timed_labels.write_text(
        "onset\ttrial_type\n0.5\tleft\n1.5\tright\n",
        encoding="utf-8",
    )
    sentinel_path = tmp_path / "existing_interpretation.fif"
    sentinel_path.write_bytes(b"existing reviewed EEG identity")
    _patch_internal_events(
        monkeypatch,
        {"A01T.gdf": {"768": {"count": 2, "description": "768"}}},
    )
    service = ApplicationService(Study())
    sentinel_raw = _minimal_raw(sentinel_path)
    raw = _raw_with_event_codes(eeg_path, [768, 768])
    second_raw = _minimal_raw(second_eeg_path)
    load_raw = _use_test_raw_factory(
        service,
        {
            str(sentinel_path): sentinel_raw,
            str(eeg_path): raw,
            str(second_eeg_path): second_raw,
        },
    )

    baseline_review = service.execute(
        ReviewInterpretationCommand(
            source_path=str(sentinel_path),
            choices={
                "selected_eeg_files": [str(sentinel_path)],
                "skip_labels": True,
            },
        )
    )
    baseline_candidate_id = baseline_review.diagnostics["candidate"]["candidate_id"]
    assert service.execute(
        ValidateInterpretationCommand(candidate_id=baseline_candidate_id)
    ).ok
    baseline_apply = service.execute(
        ApplyInterpretationCommand(
            candidate_id=baseline_candidate_id,
            confirmed=True,
        )
    )
    assert baseline_apply.ok
    source_identity_before = dict(
        sentinel_raw.runtime_details["source_content_identity"]
    )

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(sequence_labels): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "Left hand", "2": "Right hand"}
                        ),
                    },
                    str(timed_labels): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "placement_method": "time_field",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"left": "Left hand", "right": "Right hand"}
                        ),
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    state_before = service.get_state()
    loaded_before = service.study.data_manager.loaded_data_list
    applied_before = service.interpretation.state.resolve_applied_interpretation()
    assert loaded_before == [sentinel_raw]
    assert state_before.interpretation.has_applied_interpretation is True
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    state_after = service.get_state()
    loaded_after = service.study.data_manager.loaded_data_list
    applied_after = service.interpretation.state.resolve_applied_interpretation()

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.VALIDATION
    assert apply_result.diagnostics["label_apply"]["status"] == "failed"
    assert apply_result.diagnostics["state_preserved"] is True
    assert "mixed placement modes" in apply_result.diagnostics["label_apply"]["reason"]
    assert apply_result.state.raw == state_before.raw
    assert apply_result.state.interpretation == state_before.interpretation
    assert state_after.raw == state_before.raw
    assert state_after.interpretation == state_before.interpretation
    assert loaded_after is loaded_before
    assert loaded_after == [sentinel_raw]
    assert loaded_after[0] is sentinel_raw
    assert applied_after is applied_before
    assert sentinel_raw.runtime_details["source_content_identity"] == (
        source_identity_before
    )
    assert load_raw.call_count == 3


def test_apply_interpretation_blocks_sequence_label_apply_count_mismatch(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "sequence_apply_count_mismatch"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(label_path, {"classlabel": np.array([1, 2])})
    _patch_internal_events(
        monkeypatch,
        {"A01T.gdf": {"768": {"count": 2, "description": "768"}}},
    )
    service = ApplicationService(Study())
    raw = _raw_with_event_codes(eeg_path, [768, 768])
    _use_test_raw_factory(service, raw)
    label_service = MagicMock()
    label_service.apply_labels_batch_checked.return_value = 0
    service.dataset._label_service_provider = lambda: lambda: label_service

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                    }
                },
                "class_map": {"1": "Left hand", "2": "Right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.VALIDATION
    assert apply_result.diagnostics["label_apply"]["status"] == "failed"
    assert apply_result.diagnostics["state_preserved"] is True
    assert "Applied labels to 0/1" in apply_result.diagnostics["label_apply"]["reason"]
    assert apply_result.state.interpretation.has_applied_interpretation is False


def test_apply_interpretation_filters_sequence_labels_to_selected_event_codes(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "reviewed_mat_sequence_target_event"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(label_path, {"classlabel": np.array([1, 2])})
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "768": {"count": 2, "description": "768"},
                "769": {"count": 1, "description": "769"},
                "770": {"count": 1, "description": "770"},
            }
        },
    )
    service = ApplicationService(Study())
    raw = _raw_with_event_codes(eeg_path, [768, 768, 769, 770])
    _use_test_raw_factory(service, raw)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.state.interpretation.label_imports[0][
        "selected_event_names"
    ] == ["768"]


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
            "cue_duration": np.array([50, 75, 25]),
        },
    )
    service = ApplicationService(Study())
    raw = _minimal_raw(eeg_path)
    _use_test_raw_factory(service, raw)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "anchor": "cue_onset",
                        "duration_field": "cue_duration",
                        "time_model": "sample_index",
                        "sample_index_base": "zero_based",
                        "sample_index_origin": "recording_relative",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["mode"] == "anchored"
    events, event_id = raw.get_event_list()
    np.testing.assert_array_equal(
        events,
        np.array([[100, 0, 1], [250, 0, 2], [400, 0, 1]]),
    )
    assert event_id == {"left hand": 1, "right hand": 2}
    mne_raw = raw.get_mne()
    assert mne_raw is not None
    annotations = mne_raw.annotations
    assert annotations is not None
    np.testing.assert_allclose(annotations.onset, [1.0, 2.5, 4.0])
    np.testing.assert_allclose(annotations.duration, [0.5, 0.75, 0.25])
    assert list(annotations.description) == [
        "left hand",
        "right hand",
        "left hand",
    ]
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "anchored"
    assert (
        "label_import:anchored:1"
        in apply_result.diagnostics["applied_interpretation"]["recipe_trace"]
    )


def test_apply_interpretation_applies_reviewed_event_code_label_carrier(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "reviewed_event_code_labels"
    source_dir.mkdir()
    eeg_path = source_dir / "session.edf"
    label_path = source_dir / "events.tsv"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_text(
        "event_code\tcondition\n11\tleft\n12\tright\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "11": {"count": 2, "description": "11"},
                "12": {"count": 1, "description": "12"},
            }
        },
    )
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_filepath.return_value = str(eeg_path)
    raw.get_filename.return_value = eeg_path.name
    raw.get_event_list.return_value = (
        np.array([[100, 0, 11], [200, 0, 12], [300, 0, 11]], dtype=np.int32),
        {"11": 11, "12": 12},
    )
    _use_test_raw_factory(service, cast(Raw, raw))

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "condition",
                        "anchor": "event_code",
                        "placement_method": "event_code",
                        # Event-code placement must not fall into the timestamp path
                        # when a label table also carries timing-style metadata.
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"left": "Left hand", "right": "Right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["mode"] == "event_code"
    events, event_id = raw.set_event.call_args.args
    np.testing.assert_array_equal(
        events,
        np.array([[100, 0, 1], [200, 0, 2], [300, 0, 1]], dtype=np.int32),
    )
    assert event_id == {"Left hand": 1, "Right hand": 2}
    raw.set_labels_imported.assert_called_once_with(True)
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "event_code"


def test_apply_interpretation_honors_interval_end_field(
    tmp_path,
):
    source_dir = tmp_path / "reviewed_interval_end"
    source_dir.mkdir()
    eeg_path = source_dir / "session.fif"
    label_path = source_dir / "events.tsv"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_text(
        "onset\tend\tlabel\n0.1\t0.6\tleft\n1.0\t1.4\tright\n",
        encoding="utf-8",
    )
    service = ApplicationService(Study())
    raw = _minimal_raw(eeg_path)
    _use_test_raw_factory(service, raw)

    scan_result = service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "label",
                        "anchor": "onset",
                        "duration_field": "end",
                        "placement_method": "interval",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"left": "Left hand", "right": "Right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan_result.diagnostics["scan_result"]["source_kind"] == "folder"
    assert apply_result.ok is True
    events, event_id = raw.get_event_list()
    np.testing.assert_array_equal(
        events,
        np.array([[10, 0, 1], [100, 0, 2]]),
    )
    assert event_id == {"Left hand": 1, "Right hand": 2}
    mne_raw = raw.get_mne()
    assert mne_raw is not None
    annotations = mne_raw.annotations
    assert annotations is not None
    np.testing.assert_allclose(annotations.onset, [0.1, 1.0])
    np.testing.assert_allclose(annotations.duration, [0.5, 0.4])
    assert list(annotations.description) == ["Left hand", "Right hand"]
    epoch_hint = raw.get_runtime_detail("data_interpretation_epoch_hint")
    assert isinstance(epoch_hint, dict)
    assert epoch_hint["source"] == "Loaded label file"
    assert epoch_hint["placement_method"] == "interval"
    assert epoch_hint["label_field"] == "label"
    assert epoch_hint["time_field"] == "onset"
    assert epoch_hint["duration_field"] == "end"
    assert epoch_hint["time_model"] == "seconds"
    assert epoch_hint["class_map"] == {"left": "Left hand", "right": "Right hand"}
    assert epoch_hint["recommended_events"] == ["Left hand", "Right hand"]
    assert epoch_hint["duration_stats"] == {
        "max": 0.5,
        "min": 0.4,
        "numeric_count": 2,
        "row_count": 2,
        "value_counts": {"0.4": 1, "0.5": 1},
    }


def test_apply_interpretation_records_internal_event_epoch_hint(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "internal_event_epoch_hint"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    eeg_path.write_bytes(b"not loaded during scan")
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "769": {"count": 72, "description": "769"},
                "770": {"count": 72, "description": "770"},
                "768": {"count": 288, "description": "768"},
            }
        },
    )
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_filepath.return_value = str(eeg_path)
    raw.get_filename.return_value = eeg_path.name
    _use_test_raw_factory(service, cast(Raw, raw))

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier": "embedded_events",
                "class_map": {"769": "Left hand", "770": "Right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    epoch_hint = next(
        call.args[1]
        for call in raw.set_runtime_detail.call_args_list
        if call.args[0] == "data_interpretation_epoch_hint"
    )
    assert epoch_hint["source"] == "Labels inside EEG files"
    assert epoch_hint["placement_method"] == "internal_events"
    assert epoch_hint["class_map"] == {"769": "Left hand", "770": "Right hand"}
    assert epoch_hint["recommended_events"] == ["769", "770"]
    assert epoch_hint["event_label_aliases"] == {
        "769": "Left hand",
        "770": "Right hand",
    }


def test_apply_interpretation_applies_reviewed_sequence_label_carriers_by_stem(
    tmp_path,
    monkeypatch,
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
    _patch_internal_events(
        monkeypatch,
        {
            "A01T.gdf": {"768": {"count": 2, "description": "768"}},
            "B01T.gdf": {"768": {"count": 2, "description": "768"}},
        },
    )
    service = ApplicationService(Study())
    raw_1 = _raw_with_event_codes(eeg_1, [768, 768])
    raw_2 = _raw_with_event_codes(eeg_2, [768, 768])
    _use_test_raw_factory(
        service,
        {str(eeg_1): raw_1, str(eeg_2): raw_2},
    )

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_1): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    },
                    str(label_2): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["success_count"] == 2
    assert apply_result.state.interpretation.label_imports[0]["file_mapping"] == {
        str(eeg_1): str(label_1),
        str(eeg_2): str(label_2),
    }


def test_apply_interpretation_blocks_ambiguous_multi_file_sequence_labels(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "ambiguous_sequence_multi"
    source_dir.mkdir()
    eeg_1 = source_dir / "A01T.gdf"
    eeg_2 = source_dir / "B01T.gdf"
    labels = source_dir / "labels.mat"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    savemat(labels, {"classlabel": np.array([1, 2, 1, 2])})
    _patch_internal_events(
        monkeypatch,
        {
            "A01T.gdf": {"768": {"count": 2, "description": "768"}},
            "B01T.gdf": {"768": {"count": 2, "description": "768"}},
        },
    )
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(labels): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.PRECONDITION
    assert "Label carrier pairing is incomplete" in apply_result.message
    load.assert_not_called()
    assert apply_result.state.interpretation.has_applied_interpretation is False


def test_apply_interpretation_blocks_partial_manual_sequence_label_mapping(
    tmp_path,
    monkeypatch,
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
    _patch_internal_events(
        monkeypatch,
        {
            "A01T.gdf": {"768": {"count": 2, "description": "768"}},
            "B01T.gdf": {"768": {"count": 2, "description": "768"}},
        },
    )
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(labels): {
                        "target_file": str(eeg_1),
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.PRECONDITION
    assert "Label carrier pairing is incomplete" in apply_result.message
    assert eeg_2.name in apply_result.message
    load.assert_not_called()
    assert apply_result.state.interpretation.has_applied_interpretation is False


def test_data_interpretation_blocks_sources_without_eeg_files(tmp_path):
    source_dir = tmp_path / "labels_only"
    source_dir.mkdir()
    (source_dir / "labels.csv").write_text("label\n1\n2\n", encoding="utf-8")
    service = ApplicationService(Study())
    load_raw = _use_test_raw_factory(service)

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
    load_raw.assert_not_called()


def test_data_interpretation_recipe_save_and_reload_rescans_without_apply(tmp_path):
    source_dir = tmp_path / "simple_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    recipe_path = tmp_path / "recipe.json"
    service = ApplicationService(Study())
    _use_test_raw_factory(service)

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
    fresh_load = _use_test_raw_factory(fresh_service)
    reload_result = fresh_service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert reload_result.ok is True
    assert reload_result.diagnostics["recipe"]["source_path"] == str(source_dir)
    assert reload_result.diagnostics["scan_result"]["eeg_files"] == [str(eeg_path)]
    assert reload_result.state.interpretation.has_recipe is True
    assert reload_result.state.interpretation.has_applied_interpretation is False
    fresh_load.assert_not_called()


def test_apply_interpretation_blocks_after_preprocessing_operations(tmp_path):
    service = ApplicationService(Study())
    source = tmp_path / "new_file.fif"
    source.write_bytes(b"not loaded during scan")
    assert service.execute(ScanSourceCommand(source_path=str(source))).ok
    assert service.execute(PreviewInterpretationCommand()).ok
    assert service.execute(ValidateInterpretationCommand()).ok
    raw = _raw_mock()
    raw.get_preprocess_history.return_value = ["bandpass"]
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    load = _use_test_raw_factory(service)
    service.get_state()

    policy = service.get_capabilities()
    result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert policy.get(CommandName.APPLY_INTERPRETATION).available is False
    assert "Reset preprocessing" in " ".join(
        policy.get(CommandName.APPLY_INTERPRETATION).reasons
    )
    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    load.assert_not_called()


def _patch_internal_events(
    monkeypatch: Any,
    events_by_file: dict[str, dict[str, dict[str, Any]]],
) -> None:
    def read_events(path: str) -> dict[str, Any]:
        name = Path(str(path)).name
        return {"events": events_by_file.get(name, events_by_file.get("*", {}))}

    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        read_events,
    )
