from pathlib import Path

import pytest

from tests.unit.backend.path_assertions import (
    assert_filesystem_path_lists_equal,
    assert_filesystem_paths_equal,
)
from XBrainLab.backend.application import data_interpretation_internal_events
from XBrainLab.backend.application.data_interpretation_candidate import (
    InterpretationCandidate,
    build_interpretation_candidate,
    resolve_interpretation_resource_scope,
)
from XBrainLab.backend.application.data_interpretation_metadata import (
    FileMetadataResolution,
    MetadataFieldResolution,
)
from XBrainLab.backend.application.data_interpretation_resource_reader import (
    AdmittedResourceReader,
)
from XBrainLab.backend.application.data_interpretation_review import (
    build_interpretation_preview,
    validate_interpretation_candidate,
)
from XBrainLab.backend.application.data_interpretation_scan import ScanResult
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.resource_guard import (
    ResourceChecker,
    check_import_resource_preflight,
)


def _field(name: str, value: str | None = None) -> MetadataFieldResolution:
    return MetadataFieldResolution(
        field=name,
        value=value,
        source="test",
        decision="safe" if value else "needs_confirmation",
        reason="test",
    )


def _class_value_decision(class_name: str) -> dict[str, object]:
    return {
        "role": "stimulus",
        "keep_event": True,
        "use_as_class": True,
        "class_name": class_name,
    }


def _scan(**overrides) -> ScanResult:
    data = {
        "scan_id": "scan-1",
        "source_path": "/data",
        "source_kind": "bids",
        "eeg_files": ["/data/sub-01_task-mi_raw.fif"],
        "label_carriers": ["/data/sub-01_task-mi_events.tsv"],
        "label_sources": [],
        "label_carrier_sources": {"/data/sub-01_task-mi_events.tsv": "auto"},
        "metadata": [
            FileMetadataResolution(
                file="/data/sub-01_task-mi_raw.fif",
                subject=_field("subject"),
                session=_field("session", "01"),
                task=_field("task", "mi"),
                run=_field("run", "1"),
            )
        ],
        "bids": {"is_bids": True, "events_files": ["/data/sub-01_task-mi_events.tsv"]},
        "format_capabilities": [{"format": "MNE FIF", "status": "supported"}],
        "warnings": ["Review external labels."],
        "blocked_reasons": [],
    }
    data.update(overrides)
    return ScanResult(**data)


def _admitted_reader(paths: list[str], monkeypatch) -> AdmittedResourceReader:
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 10**12,
                "used_bytes": 0,
            }
        ),
    )
    return AdmittedResourceReader.from_resource_preflight(
        paths,
        check_import_resource_preflight(paths),
    )


def test_candidate_rejects_label_carrier_changed_after_resource_admission(
    tmp_path,
    monkeypatch,
) -> None:
    eeg_path = tmp_path / "signal.npy"
    label_path = tmp_path / "labels.csv"
    eeg_path.write_bytes(b"eeg")
    label_path.write_text("label\nleft\n", encoding="utf-8")
    paths = [str(eeg_path), str(label_path)]
    reader = _admitted_reader(paths, monkeypatch)
    label_path.write_text("label\nchanged\n", encoding="utf-8")

    with pytest.raises(PreconditionError) as raised:
        build_interpretation_candidate(
            candidate_id="candidate-admission-label",
            scan=_scan(
                source_kind="folder",
                eeg_files=[str(eeg_path)],
                label_carriers=[str(label_path)],
                label_carrier_sources={str(label_path): "auto"},
                bids={"is_bids": False},
                metadata=[],
            ),
            resource_reader=reader,
        )

    assert raised.value.diagnostics["purpose"] == "label carrier preview"


def test_bids_review_rejects_eeg_changed_after_resource_admission(
    tmp_path,
    monkeypatch,
) -> None:
    eeg_path = tmp_path / "sub-01_task-mi_eeg.fif"
    events_path = tmp_path / "sub-01_task-mi_events.tsv"
    eeg_path.write_bytes(b"not-yet-materialized")
    events_path.write_text(
        "onset\tduration\ttrial_type\n0\t1\tleft\n",
        encoding="utf-8",
    )
    paths = [str(eeg_path), str(events_path)]
    reader = _admitted_reader(paths, monkeypatch)
    eeg_path.write_bytes(b"changed-after-admission")

    with pytest.raises(PreconditionError) as raised:
        build_interpretation_candidate(
            candidate_id="candidate-admission-bids",
            scan=_scan(
                source_path=str(tmp_path),
                eeg_files=[str(eeg_path)],
                label_carriers=[str(events_path)],
                label_carrier_sources={str(events_path): "auto"},
                metadata=[],
                bids={
                    "is_bids": True,
                    "events_files": [str(events_path)],
                    "layout": [
                        {
                            "file": str(eeg_path),
                            "subject": "01",
                            "task": "mi",
                            "run": "",
                            "datatype": "eeg",
                            "events_file": str(events_path),
                            "channels_file": "",
                        }
                    ],
                },
            ),
            choices={
                "label_carrier_choices": {
                    str(events_path): {"label_field": "trial_type"}
                }
            },
            resource_reader=reader,
        )

    assert raised.value.diagnostics["purpose"] == "BIDS run review"


def test_internal_event_preview_rejects_eeg_changed_after_resource_admission(
    tmp_path,
    monkeypatch,
) -> None:
    eeg_path = tmp_path / "embedded-events.gdf"
    eeg_path.write_bytes(b"original-header")
    reader = _admitted_reader([str(eeg_path)], monkeypatch)
    eeg_path.write_bytes(b"changed-header!")

    with pytest.raises(PreconditionError) as raised:
        build_interpretation_candidate(
            candidate_id="candidate-admission-embedded",
            scan=_scan(
                source_kind="folder",
                eeg_files=[str(eeg_path)],
                label_carriers=[],
                label_carrier_sources={},
                bids={"is_bids": False},
                metadata=[],
            ),
            choices={"label_carrier": "embedded_events"},
            resource_reader=reader,
        )

    assert raised.value.diagnostics["purpose"] == "embedded EEG event preview"


def test_build_interpretation_candidate_applies_user_choices_and_recipe_trace(
    tmp_path,
):
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[str(events)],
            label_carrier_sources={str(events): "auto"},
            bids={"is_bids": True, "events_files": [str(events)]},
        ),
        choices={
            "metadata_overrides": {
                "sub-01_task-mi_raw.fif": {"subject": "S01"},
            },
            "event_roles": {"trial_type": "class cue"},
            "label_carrier_choices": {
                str(events): {
                    "label_field": "trial_type",
                    "value_decisions": {
                        "left": _class_value_decision("0"),
                    },
                },
            },
        },
    )

    assert isinstance(candidate, InterpretationCandidate)
    assert candidate.metadata[0].subject.value == "S01"
    assert candidate.metadata[0].subject.source == "user_override"
    assert candidate.event_roles["trial_type"] == "class cue"
    assert candidate.class_map == {"left": "0"}
    assert candidate.class_map_source == "value_decisions"
    assert "choices:metadata_overrides" in candidate.recipe_trace
    assert "choices:class_map" not in candidate.recipe_trace
    assert "choices:event_roles" in candidate.recipe_trace
    assert "choices:label_carriers" in candidate.recipe_trace


def test_build_interpretation_candidate_recomputes_bids_scope_for_selected_files(
    tmp_path,
):
    selected_file = str(tmp_path / "sub-01_task-mi_run-1_raw.fif")
    skipped_file = str(tmp_path / "sub-01_task-mi_run-2_raw.fif")
    selected_events = str(tmp_path / "sub-01_task-mi_run-1_events.tsv")
    skipped_events = str(tmp_path / "sub-01_task-mi_run-2_events.tsv")
    Path(selected_events).write_text(
        "onset\tduration\ttrial_type\n0\t0\tleft\n",
        encoding="utf-8",
    )
    Path(skipped_events).write_text(
        "onset\tduration\ttrial_type\n0\t0\tright\n",
        encoding="utf-8",
    )
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=[selected_file, skipped_file],
            label_carriers=[selected_events, skipped_events],
            label_carrier_sources={
                selected_events: "auto",
                skipped_events: "auto",
            },
            bids={
                "is_bids": True,
                "events_files": [selected_events, skipped_events],
                "layout": [
                    {
                        "file": selected_file,
                        "subject": "01",
                        "task": "mi",
                        "run": "1",
                        "datatype": "eeg",
                        "events_file": selected_events,
                        "channels_file": "/data/sub-01_task-mi_run-1_channels.tsv",
                    },
                    {
                        "file": skipped_file,
                        "subject": "01",
                        "task": "mi",
                        "run": "2",
                        "datatype": "eeg",
                        "events_file": skipped_events,
                        "channels_file": "/data/sub-01_task-mi_run-2_channels.tsv",
                    },
                ],
                "selected_scope": {
                    "eeg_files": [selected_file, skipped_file],
                    "events_files": [selected_events, skipped_events],
                },
            },
        ),
        choices={
            "selected_eeg_files": [selected_file],
            "label_carrier_choices": {
                selected_events: {"label_field": "trial_type", "anchor": "onset"}
            },
        },
    )

    assert candidate.selected_eeg_files == [selected_file]
    assert candidate.bids["selected_scope"]["eeg_files"] == [selected_file]
    assert candidate.bids["selected_scope"]["events_files"] == [selected_events]
    assert candidate.bids["selected_scope"]["runs"] == ["1"]
    assert candidate.label_carriers == [selected_events]
    assert [row["path"] for row in candidate.label_carrier_plan] == [selected_events]


def test_bids_candidate_blocks_selected_scope_without_events_tsv():
    selected_file = "/data/sub-01_task-mi_run-1_raw.fif"

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            source_kind="bids",
            eeg_files=[selected_file],
            label_carriers=[],
            label_carrier_sources={},
            bids={
                "is_bids": True,
                "events_files": [],
                "layout": [
                    {
                        "file": selected_file,
                        "subject": "01",
                        "task": "mi",
                        "run": "1",
                        "datatype": "eeg",
                        "events_file": "",
                        "channels_file": "",
                    }
                ],
            },
            warnings=[],
        ),
        choices={"selected_eeg_files": [selected_file]},
    )

    assert candidate.label_carriers == []
    assert candidate.bids["selected_scope"]["events_files"] == []
    assert (
        "BIDS events.tsv was not found for the selected EEG file(s). "
        "Choose a BIDS run with events.tsv, or use Import folder for non-BIDS labels."
        in candidate.blocked_reasons
    )


def test_candidate_blocks_partial_manual_label_pairing(tmp_path):
    eeg_1 = tmp_path / "sub-01_task-mi_run-1_raw.fif"
    eeg_2 = tmp_path / "sub-01_task-mi_run-2_raw.fif"
    labels = tmp_path / "events.tsv"
    labels.write_text("onset\ttrial_type\n0.5\tleft\n", encoding="utf-8")
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            source_kind="folder",
            eeg_files=[str(eeg_1), str(eeg_2)],
            label_carriers=[str(labels)],
            label_carrier_sources={str(labels): "auto"},
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "label_carrier_choices": {
                str(labels): {
                    "target_file": eeg_2.name,
                    "label_field": "trial_type",
                    "anchor": "onset",
                }
            }
        },
    )

    assert any(
        "Label carrier pairing is incomplete" in reason
        and "sub-01_task-mi_run-1_raw.fif" in reason
        for reason in candidate.blocked_reasons
    )
    preview = build_interpretation_preview(
        preview_id="preview-1",
        candidate=candidate,
    )
    decision = validate_interpretation_candidate(candidate)
    assert decision.decision == "blocked"
    assert any(
        item["target_step"] == "Match Labels"
        and "pairing is incomplete" in item["issue"]
        for item in preview.action_items
    )


def test_bids_candidate_blocks_when_one_selected_run_has_no_events_tsv(tmp_path):
    eeg_1 = tmp_path / "sub-01_task-mi_run-1_raw.fif"
    eeg_2 = tmp_path / "sub-01_task-mi_run-2_raw.fif"
    events_1 = tmp_path / "sub-01_task-mi_run-1_events.tsv"
    events_1.write_text("onset\ttrial_type\n0.5\tleft\n", encoding="utf-8")
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            source_kind="bids",
            eeg_files=[str(eeg_1), str(eeg_2)],
            label_carriers=[str(events_1)],
            label_carrier_sources={str(events_1): "auto"},
            bids={
                "is_bids": True,
                "events_files": [str(events_1)],
                "layout": [
                    {"file": str(eeg_1), "events_file": str(events_1)},
                    {"file": str(eeg_2), "events_file": ""},
                ],
            },
        ),
    )

    assert any(
        "Label carrier pairing is incomplete" in reason and eeg_2.name in reason
        for reason in candidate.blocked_reasons
    )


def test_bids_candidate_accepts_unique_events_tsv_for_each_selected_run(tmp_path):
    eeg_1 = tmp_path / "sub-01_task-mi_run-1_raw.fif"
    eeg_2 = tmp_path / "sub-01_task-mi_run-2_raw.fif"
    events_1 = tmp_path / "sub-01_task-mi_run-1_events.tsv"
    events_2 = tmp_path / "sub-01_task-mi_run-2_events.tsv"
    for events in (events_1, events_2):
        events.write_text("onset\ttrial_type\n0.5\tleft\n", encoding="utf-8")
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            source_kind="bids",
            eeg_files=[str(eeg_1), str(eeg_2)],
            label_carriers=[str(events_1), str(events_2)],
            label_carrier_sources={
                str(events_1): "auto",
                str(events_2): "auto",
            },
            bids={
                "is_bids": True,
                "events_files": [str(events_1), str(events_2)],
                "layout": [
                    {"file": str(eeg_1), "events_file": str(events_1)},
                    {"file": str(eeg_2), "events_file": str(events_2)},
                ],
            },
        ),
    )

    assert not any(
        "Label carrier pairing is incomplete" in reason
        for reason in candidate.blocked_reasons
    )


def test_build_interpretation_candidate_blocks_unresolved_bids_label_values(tmp_path):
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\n"
        "0.0\t1.0\tleft\n"
        "1.0\t1.0\tright\n"
        "2.0\t1.0\tleft\n",
        encoding="utf-8",
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[str(events)],
            bids={"is_bids": True, "events_files": [str(events)]},
        ),
    )

    assert candidate.label_carrier_plan[0]["selected_label_field"] == "trial_type"
    assert candidate.class_map == {}
    assert candidate.class_map_source == ""
    assert candidate.label_carrier_plan[0]["unresolved_values"] == [
        "left",
        "right",
    ]
    assert any("left, right" in reason for reason in candidate.blocked_reasons)
    assert "choices:class_map" not in candidate.recipe_trace


def test_build_interpretation_candidate_uses_inside_eeg_labels_instead_of_carrier(
    tmp_path,
    monkeypatch,
):
    events = tmp_path / "A01T.mat"
    events.write_text("not parsed when embedded events are selected", encoding="utf-8")
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "768": {"count": 36, "description": "768"},
                "769": {"count": 18, "description": "769"},
                "770": {"count": 18, "description": "770"},
                "1023": {"count": 6, "description": "1023"},
            }
        },
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=["/data/A01T.gdf"],
            label_carriers=[str(events)],
            label_carrier_sources={str(events): "auto"},
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "label_carrier": "embedded_events",
            "label_carrier_choices": {
                str(events): {
                    "label_field": "classlabel",
                    "anchor": "trial order",
                    "time_model": "trial_order",
                }
            },
            "required_label_carriers": [str(tmp_path / "missing.mat")],
        },
    )

    assert candidate.label_carriers == []
    assert candidate.label_carrier_plan == []
    assert candidate.class_map == {}
    assert candidate.event_roles["internal_events"] == "event role candidates"
    assert [
        row["event_code"]
        for row in candidate.internal_event_preview["candidate_label_events"]
    ] == ["769", "770"]
    assert candidate.internal_event_preview["candidate_label_events"][0][
        "evidence"
    ].startswith("Repeated count")
    assert candidate.internal_event_selection["label_event_counts"] == {
        "769": 18,
        "770": 18,
    }
    assert [
        row["event_code"] for row in candidate.internal_event_preview["not_used_events"]
    ] == ["768", "1023"]
    assert all(
        "label carrier alignment" not in item for item in candidate.confirmation_items
    )
    assert candidate.blocked_reasons == []
    assert "choices:label_carrier" in candidate.recipe_trace
    assert "choices:label_carriers" not in candidate.recipe_trace


def test_build_interpretation_candidate_excludes_removed_label_carrier(tmp_path):
    removed = tmp_path / "A01T.mat"
    kept = tmp_path / "A02T.mat"
    removed.write_text("removed", encoding="utf-8")
    kept.write_text("kept", encoding="utf-8")

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[str(removed), str(kept)],
            label_carrier_sources={
                str(removed): "auto",
                str(kept): "auto",
            },
            bids={"is_bids": False, "events_files": []},
        ),
        choices={"excluded_label_carriers": [str(removed)]},
    )

    assert candidate.label_carriers == [str(kept)]
    assert [item["path"] for item in candidate.label_carrier_plan] == [str(kept)]
    assert "choices:excluded_label_carriers" in candidate.recipe_trace


def test_excluded_label_carrier_full_path_does_not_remove_duplicate_basename(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first" / "events.tsv"
    second = tmp_path / "second" / "events.tsv"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("label\nleft\n", encoding="utf-8")
    second.write_text("label\nright\n", encoding="utf-8")
    scan = _scan(
        label_carriers=[str(first), str(second)],
        label_carrier_sources={str(first): "auto", str(second): "auto"},
        bids={"is_bids": False, "events_files": []},
    )

    exact = build_interpretation_candidate(
        candidate_id="candidate-exact",
        scan=scan,
        choices={"excluded_label_carriers": [str(first)]},
    )
    ambiguous_legacy = build_interpretation_candidate(
        candidate_id="candidate-legacy",
        scan=scan,
        choices={"excluded_label_carriers": [first.name]},
    )

    assert exact.label_carriers == [str(second)]
    assert ambiguous_legacy.label_carriers == [str(first), str(second)]


def test_build_interpretation_candidate_uses_bids_levels_as_suggestions_only(tmp_path):
    events = tmp_path / "sub-01_task-mi_events.tsv"
    sidecar = tmp_path / "sub-01_task-mi_events.json"
    events.write_text(
        "onset\tduration\ttrial_type\n0.0\t1.0\tleft\n1.0\t1.0\tright\n",
        encoding="utf-8",
    )
    sidecar.write_text(
        '{"trial_type":{"Levels":{"left":"Left hand","right":"Right hand"}}}',
        encoding="utf-8",
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[str(events)],
            bids={"is_bids": True, "events_files": [str(events)]},
        ),
    )

    assert candidate.class_map == {}
    decisions = candidate.label_carrier_plan[0]["value_decisions"]
    assert decisions["left"]["suggested_name"] == "Left hand"
    assert decisions["right"]["suggested_name"] == "Right hand"
    assert decisions["left"]["decision"] == "unresolved"
    assert "choices:class_map" not in candidate.recipe_trace


def test_build_interpretation_candidate_surfaces_bids_events_review_items(tmp_path):
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\ttrial_type\tresponse_time\tHED\tchannel\n"
        "0.0\tleft\t0.4\tMotor imagery\tC3\n"
        "1.0\tright\t0.5\tMotor imagery\tC4\n",
        encoding="utf-8",
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[str(events)],
            bids={"is_bids": True, "events_files": [str(events)]},
        ),
    )

    plan = candidate.label_carrier_plan[0]
    assert plan["bids_event_columns"] == [
        "onset",
        "trial_type",
        "response_time",
        "HED",
        "channel",
    ]
    assert any("events.json sidecar is missing" in item for item in candidate.warnings)
    assert any("duration column is missing" in item for item in candidate.warnings)


def test_build_interpretation_candidate_previews_mat_label_class_values(tmp_path):
    from scipy.io import savemat

    label_path = tmp_path / "A01T.mat"
    savemat(
        label_path,
        {
            "classlabel": [1, 2, 1, 2],
            "cue_onset": [100, 250, 400, 550],
        },
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[str(label_path)],
            bids={"is_bids": False, "events_files": []},
        ),
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
                }
            },
        },
    )

    assert candidate.label_carrier_plan[0]["format"] == "MAT"
    assert candidate.label_carrier_plan[0]["selected_label_field"] == "classlabel"
    assert candidate.class_map == {"1": "1", "2": "2"}
    assert candidate.class_map_source == "value_decisions"
    assert not any(
        "Confirm label carrier alignment" in item
        for item in candidate.confirmation_items
    )
    assert "choices:class_map" not in candidate.recipe_trace


def test_build_interpretation_candidate_reviews_bids_interval_placement(tmp_path):
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\n0.0\t1.0\tleft\n2.0\t1.0\tright\n",
        encoding="utf-8",
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[str(events)],
            bids={"is_bids": True, "events_files": [str(events)]},
        ),
        choices={
            "label_carrier_choices": {
                str(events): {
                    "label_field": "trial_type",
                    "anchor": "onset",
                    "duration_field": "duration",
                    "placement_method": "interval",
                }
            }
        },
    )

    review = candidate.label_carrier_plan[0]["placement_review"]

    assert review["method"] == "interval"
    assert review["status"] == "ready"
    assert review["label_rows"] == 2
    assert review["numeric_rows"] == 2
    assert review["duration_numeric_rows"] == 2
    assert review["summary"] == "2 interval rows using onset and duration."


def test_build_interpretation_candidate_blocks_empty_selection():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=[],
            label_carriers=[],
            label_carrier_sources={},
            bids={"is_bids": True, "events_files": []},
        ),
        choices={"selected_eeg_files": []},
    )

    assert candidate.selected_eeg_files == []
    assert "No EEG files were selected for interpretation." in candidate.blocked_reasons


def test_build_interpretation_candidate_blocks_selected_files_missing_from_scan():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=["/data/sub-01_task-mi_raw.fif"],
            label_carriers=[],
            label_carrier_sources={},
            bids={"is_bids": True, "events_files": []},
        ),
        choices={
            "recipe_id": "recipe-1",
            "selected_eeg_files": [
                "/data/sub-01_task-mi_raw.fif",
                "/data/missing_raw.fif",
            ],
        },
    )

    assert any(
        "missing_raw.fif" in reason and "not found in the current scan" in reason
        for reason in candidate.blocked_reasons
    )


def test_resource_scope_keeps_missing_selection_but_only_materializes_scanned_files():
    scanned = "/data/sub-01_task-mi_raw.fif"
    missing = "/data/missing_raw.fif"

    scope = resolve_interpretation_resource_scope(
        _scan(eeg_files=[scanned], label_carriers=[]),
        {"selected_eeg_files": [scanned, missing]},
    )

    assert scope.selected_eeg_files == [scanned, missing]
    assert scope.materializable_eeg_files == [scanned]
    assert scope.paths == [scanned]


def test_duplicate_basename_recipe_selection_is_ambiguous_and_blocks_import():
    saved = "/recipe/old/run_raw.fif"
    scanned = ["/scan/site-a/run_raw.fif", "/scan/site-b/run_raw.fif"]
    scan = _scan(
        source_kind="folder",
        eeg_files=scanned,
        label_carriers=[],
        label_carrier_sources={},
        bids={"is_bids": False},
        metadata=[],
    )

    scope = resolve_interpretation_resource_scope(
        scan,
        {"recipe_id": "recipe-1", "selected_eeg_files": [saved]},
    )
    candidate = build_interpretation_candidate(
        candidate_id="candidate-ambiguous",
        scan=scan,
        choices={"recipe_id": "recipe-1", "selected_eeg_files": [saved]},
    )
    preview = build_interpretation_preview(
        preview_id="preview-ambiguous",
        candidate=candidate,
        scan=scan,
    )

    assert scope.selected_eeg_files == [saved]
    assert scope.materializable_eeg_files == []
    assert any(
        "ambiguous" in reason.lower()
        and "/scan/site-a/run_raw.fif" in reason
        and "/scan/site-b/run_raw.fif" in reason
        for reason in candidate.blocked_reasons
    )
    assert any(
        item["severity"] == "blocked" and item["target_step"] == "Choose EEG Data"
        for item in preview.action_items
    )


def test_duplicate_basename_required_label_carrier_requires_explicit_remap(
    tmp_path: Path,
):
    saved = "/recipe/old/events.tsv"
    first = tmp_path / "site-a" / "events.tsv"
    second = tmp_path / "site-b" / "events.tsv"
    first.parent.mkdir()
    second.parent.mkdir()
    for path in (first, second):
        path.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    scan = _scan(
        source_kind="folder",
        label_carriers=[str(first), str(second)],
        label_carrier_sources={str(first): "auto", str(second): "auto"},
        bids={"is_bids": False},
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-label-ambiguous",
        scan=scan,
        choices={
            "recipe_id": "recipe-1",
            "required_label_carriers": [saved],
        },
    )

    assert any(
        "ambiguous" in reason.lower() and str(first) in reason and str(second) in reason
        for reason in candidate.blocked_reasons
    )


def test_resource_scope_includes_referenced_eeglab_external_data(tmp_path: Path):
    from scipy.io import savemat

    set_path = tmp_path / "subject.set"
    fdt_path = tmp_path / "Signal-Case.FDT"
    fdt_path.write_bytes(b"\0" * (2 * 20 * 4))
    savemat(
        set_path,
        {
            "EEG": {
                "data": fdt_path.name,
                "nbchan": 2.0,
                "pnts": 20.0,
                "trials": 1.0,
            }
        },
        do_compression=True,
    )

    scope = resolve_interpretation_resource_scope(
        _scan(eeg_files=[str(set_path)], label_carriers=[]),
    )

    assert scope.materializable_eeg_files == [str(set_path)]
    assert scope.eeg_dependency_files == [str(fdt_path)]
    assert scope.paths == [str(set_path), str(fdt_path)]


def test_resource_scope_includes_all_brainvision_parser_dependencies_without_opening_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vhdr_path = tmp_path / "subject.vhdr"
    eeg_path = tmp_path / "subject-data.eeg"
    vmrk_path = tmp_path / "subject-markers.vmrk"
    eeg_path.write_bytes(b"eeg payload must not be opened for dependency discovery")
    vmrk_path.write_text(
        "Brain Vision Data Exchange Marker File, Version 1.0\n",
        encoding="utf-8",
    )
    vhdr_path.write_text(
        "\n".join(
            (
                "Brain Vision Data Exchange Header File Version 1.0",
                "[Common Infos]",
                "Codepage=UTF-8",
                f"DataFile={eeg_path.name}",
                f"MarkerFile={vmrk_path.name}",
            )
        ),
        encoding="utf-8",
    )
    real_open = Path.open
    opened_paths: list[Path] = []

    def _observed_open(path: Path, *args, **kwargs):
        resolved = path.resolve(strict=False)
        opened_paths.append(resolved)
        if resolved in {eeg_path.resolve(), vmrk_path.resolve()}:
            raise AssertionError("dependency discovery must not open EEG payloads")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _observed_open)

    scope = resolve_interpretation_resource_scope(
        _scan(eeg_files=[str(vhdr_path)], label_carriers=[]),
    )

    assert scope.eeg_dependency_files == [str(eeg_path), str(vmrk_path)]
    assert scope.eeg_dependencies_by_file == {
        str(vhdr_path): [str(eeg_path), str(vmrk_path)]
    }
    assert scope.paths == [str(vhdr_path), str(eeg_path), str(vmrk_path)]
    assert opened_paths == [vhdr_path.resolve()]


def test_candidate_rebinds_changed_brainvision_reference_to_admitted_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = (
        Path(__file__).resolve().parents[4]
        / "tests"
        / "fixtures"
        / "data"
        / "multiformat"
    )
    stem = "A01T-mini-real"
    copied_paths: list[str] = []
    for suffix in (".vhdr", ".eeg", ".vmrk"):
        source = fixture_root / f"{stem}{suffix}"
        target = tmp_path / source.name
        target.write_bytes(source.read_bytes())
        copied_paths.append(str(target))
    vhdr_path = tmp_path / f"{stem}.vhdr"
    changed_eeg_path = tmp_path / "changed.eeg"
    changed_eeg_path.write_bytes((tmp_path / f"{stem}.eeg").read_bytes())
    reader = _admitted_reader(copied_paths, monkeypatch)
    vhdr_path.write_text(
        vhdr_path.read_text(encoding="utf-8").replace(
            f"DataFile={stem}.eeg",
            f"DataFile={changed_eeg_path.name}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(PreconditionError) as raised:
        build_interpretation_candidate(
            candidate_id="candidate-brainvision-reference-change",
            scan=_scan(
                source_kind="folder",
                eeg_files=[str(vhdr_path)],
                label_carriers=[],
                label_carrier_sources={},
                bids={"is_bids": False},
                metadata=[],
            ),
            choices={"label_carrier": "embedded_events"},
            resource_reader=reader,
        )

    assert raised.value.diagnostics["code"] == "interpretation_resource_not_admitted"
    assert_filesystem_paths_equal(raised.value.diagnostics["owner_path"], vhdr_path)
    assert_filesystem_path_lists_equal(
        raised.value.diagnostics["missing_paths"],
        [changed_eeg_path],
    )


def test_build_interpretation_candidate_filters_metadata_to_selected_files():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=[
                "/data/sub-01_task-mi_raw.fif",
                "/data/sub-02_task-mi_raw.fif",
                "/data/sub-03_task-mi_raw.fif",
            ],
            metadata=[
                FileMetadataResolution(
                    file="/data/sub-01_task-mi_raw.fif",
                    subject=_field("subject", "01"),
                    session=_field("session", "01"),
                    task=_field("task", "mi"),
                    run=_field("run", "1"),
                ),
                FileMetadataResolution(
                    file="/data/sub-02_task-mi_raw.fif",
                    subject=_field("subject", "02"),
                    session=_field("session", "01"),
                    task=_field("task", "mi"),
                    run=_field("run", "1"),
                ),
                FileMetadataResolution(
                    file="/data/sub-03_task-mi_raw.fif",
                    subject=_field("subject", "03"),
                    session=_field("session", "01"),
                    task=_field("task", "mi"),
                    run=_field("run", "1"),
                ),
            ],
            label_carriers=[],
            label_carrier_sources={},
            bids={"is_bids": False},
        ),
        choices={
            "selected_eeg_files": [
                "/data/sub-01_task-mi_raw.fif",
                "/data/sub-03_task-mi_raw.fif",
            ],
        },
    )

    assert candidate.selected_eeg_files == [
        "/data/sub-01_task-mi_raw.fif",
        "/data/sub-03_task-mi_raw.fif",
    ]
    assert [Path(item.file).name for item in candidate.metadata] == [
        "sub-01_task-mi_raw.fif",
        "sub-03_task-mi_raw.fif",
    ]


def test_candidate_only_requires_subject_metadata_confirmation():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-optional-metadata",
        scan=_scan(
            source_kind="folder",
            eeg_files=["/data/signal.fif"],
            label_carriers=[],
            label_carrier_sources={},
            bids={"is_bids": False, "events_files": []},
            metadata=[
                FileMetadataResolution(
                    file="/data/signal.fif",
                    subject=_field("subject"),
                    session=_field("session"),
                    task=_field("task"),
                    run=_field("run"),
                )
            ],
        ),
        choices={"skip_labels": True},
    )

    assert candidate.confirmation_items == [
        "Confirm subject metadata for signal.fif.",
    ]


def test_build_interpretation_candidate_resolves_relative_selected_file_to_scan_path(
    tmp_path,
):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    selected_eeg = source_dir / "selected.fif"
    sibling_eeg = source_dir / "sibling.fif"
    selected_eeg.write_bytes(b"selected")
    sibling_eeg.write_bytes(b"sibling")

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            source_path=str(source_dir),
            source_kind="folder",
            eeg_files=[str(selected_eeg), str(sibling_eeg)],
            label_carriers=[],
            label_carrier_sources={},
            bids={"is_bids": False, "events_files": []},
            metadata=[
                FileMetadataResolution(
                    file=str(selected_eeg),
                    subject=_field("subject", "01"),
                    session=_field("session", "01"),
                    task=_field("task", "mi"),
                    run=_field("run", "1"),
                ),
                FileMetadataResolution(
                    file=str(sibling_eeg),
                    subject=_field("subject", "02"),
                    session=_field("session", "01"),
                    task=_field("task", "mi"),
                    run=_field("run", "1"),
                ),
            ],
        ),
        choices={"selected_eeg_files": ["selected.fif"]},
    )

    assert candidate.blocked_reasons == []
    assert candidate.selected_eeg_files == [str(selected_eeg)]
    assert [Path(item.file).name for item in candidate.metadata] == ["selected.fif"]


def test_build_interpretation_candidate_remaps_saved_selected_eeg_file_choices():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=["/data/renamed_raw.fif"],
            label_carriers=[],
            label_carrier_sources={},
            bids={"is_bids": False, "events_files": []},
            metadata=[
                FileMetadataResolution(
                    file="/data/renamed_raw.fif",
                    subject=_field("subject"),
                    session=_field("session", "01"),
                    task=_field("task", "mi"),
                    run=_field("run", "1"),
                )
            ],
        ),
        choices={
            "recipe_id": "recipe-1",
            "selected_eeg_files": ["/data/original_raw.fif"],
            "eeg_file_remap": {
                "/data/original_raw.fif": "/data/renamed_raw.fif",
            },
            "metadata_overrides": {
                "/data/original_raw.fif": {"subject": "S01"},
            },
        },
    )

    assert candidate.blocked_reasons == []
    assert candidate.selected_eeg_files == ["/data/renamed_raw.fif"]
    assert candidate.metadata[0].subject.value == "S01"
    assert candidate.metadata[0].subject.source == "user_override"
    assert "choices:eeg_file_remap" in candidate.recipe_trace


def test_build_interpretation_candidate_blocks_required_label_carriers_missing_from_scan(
    tmp_path,
):
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[str(events)],
            label_carrier_sources={str(events): "auto"},
            bids={"is_bids": True, "events_files": [str(events)]},
        ),
        choices={
            "recipe_id": "recipe-1",
            "required_label_carriers": [
                str(events),
                "/data/missing_events.tsv",
            ],
        },
    )

    missing_reason = next(
        reason for reason in candidate.blocked_reasons if "missing_events.tsv" in reason
    )
    assert "label/event carrier" in missing_reason
    assert "choices:label_carriers" in candidate.recipe_trace


def test_build_interpretation_candidate_skip_labels_suppresses_external_carriers():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=["/data/sub-01_task-mi_events.tsv"],
            metadata=[
                FileMetadataResolution(
                    file="/data/sub-01_task-mi_raw.fif",
                    subject=_field("subject", "01"),
                    session=_field("session", "01"),
                    task=_field("task", "mi"),
                    run=_field("run", "1"),
                )
            ],
        ),
        choices={
            "skip_labels": True,
            "label_carrier": "embedded_events",
            "event_roles": {"internal_events": "event role candidates"},
            "class_map": {"769": "left hand"},
            "run_event_mappings": {
                "S001R04.edf": {"T1": "left fist", "T2": "right fist"},
            },
            "required_label_carriers": ["/data/missing_events.tsv"],
            "label_carrier_choices": {
                "/data/missing_events.tsv": {
                    "label_field": "trial_type",
                    "anchor": "onset",
                }
            },
        },
    )

    assert candidate.blocked_reasons == []
    assert candidate.label_carriers == []
    assert candidate.label_carrier_plan == []
    assert candidate.event_roles == {}
    assert candidate.class_map == {}
    assert candidate.internal_event_preview == {}
    assert candidate.internal_event_selection == {}
    assert candidate.run_event_mappings == {}
    assert candidate.confirmation_items == []
    assert "choices:skip_labels" in candidate.recipe_trace
    assert "choices:label_carrier" not in candidate.recipe_trace
    assert "choices:class_map" not in candidate.recipe_trace
    assert "choices:event_roles" not in candidate.recipe_trace
    assert "choices:label_carriers" not in candidate.recipe_trace


def test_build_interpretation_candidate_remaps_saved_label_carrier_choices(tmp_path):
    original = tmp_path / "original_events.tsv"
    renamed = tmp_path / "renamed_events.tsv"
    renamed.write_text(
        "onset\ttrial_type\n0.0\tleft\n1.0\tright\n",
        encoding="utf-8",
    )
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[str(renamed)],
            label_carrier_sources={str(renamed): "auto"},
            bids={"is_bids": True, "events_files": [str(renamed)]},
        ),
        choices={
            "recipe_id": "recipe-1",
            "required_label_carriers": [str(original)],
            "label_carrier_remap": {
                str(original): str(renamed),
            },
            "label_carrier_choices": {
                str(original): {
                    "label_field": "trial_type",
                    "anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "trial",
                    "role": "class cue labels",
                    "value_decisions": {
                        "left": _class_value_decision("left"),
                        "right": _class_value_decision("right"),
                    },
                }
            },
        },
    )

    assert candidate.blocked_reasons == []
    assert candidate.label_carrier_plan[0]["path"] == str(renamed)
    assert candidate.label_carrier_plan[0]["selected_label_field"] == "trial_type"
    assert candidate.label_carrier_plan[0]["selected_anchor"] == "onset"
    assert candidate.label_carrier_plan[0]["role"] == "class cue labels"
    assert "choices:label_carrier_remap" in candidate.recipe_trace


def test_build_interpretation_candidate_preserves_user_added_label_sources(tmp_path):
    auto_events = tmp_path / "sub-01_task-mi_events.tsv"
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    external_labels = external_dir / "sub-01_task-mi_labels.tsv"
    auto_events.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    external_labels.write_text("onset\tlabel\n0\tleft\n", encoding="utf-8")
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[
                str(auto_events),
                str(external_labels),
            ],
            label_sources=[str(external_dir)],
            label_carrier_sources={
                str(auto_events): "auto",
                str(external_labels): str(external_dir),
            },
            bids={
                "is_bids": True,
                "events_files": [str(auto_events), str(external_labels)],
            },
        ),
    )

    plans = {item["path"]: item for item in candidate.label_carrier_plan}

    assert candidate.label_sources == [str(external_dir)]
    assert plans[str(auto_events)]["source_kind"] == ("auto_discovered")
    assert plans[str(external_labels)]["source_kind"] == "user_added"
    assert plans[str(external_labels)]["source_location"] == str(external_dir)


def test_build_interpretation_candidate_uses_real_internal_event_evidence(
    monkeypatch,
):
    def fake_read(path: str):
        name = Path(path).name
        counts_by_file = {
            "A01T.gdf": {
                "768": 108,
                "769": 36,
                "770": 36,
                "772": 36,
                "1023": 2,
                "32766": 1,
            },
            "A02T.gdf": {
                "768": 108,
                "769": 36,
                "770": 36,
                "772": 36,
                "1023": 2,
                "32766": 1,
            },
            "A03T.gdf": {"768": 72, "769": 36, "770": 36, "1023": 2, "32766": 1},
        }
        return {
            "events": {
                code: {"count": count, "description": code}
                for code, count in counts_by_file[name].items()
            }
        }

    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        fake_read,
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            source_kind="folder",
            eeg_files=["/data/A01T.gdf", "/data/A02T.gdf", "/data/A03T.gdf"],
            label_carriers=[],
            label_carrier_sources={},
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "selected_eeg_files": [
                "/data/A01T.gdf",
                "/data/A02T.gdf",
                "/data/A03T.gdf",
            ],
            "label_carrier": "embedded_events",
        },
    )

    preview = candidate.internal_event_preview
    rows_by_code = {row["event_code"]: row for row in preview["candidate_label_events"]}
    other_by_code = {row["event_code"]: row for row in preview["not_used_events"]}

    assert preview["source"] == "mne_internal_events"
    assert preview["file_count"] == 3
    assert list(rows_by_code) == ["769", "770", "772"]
    assert rows_by_code["769"]["event_count"] == 108
    assert rows_by_code["769"]["coverage"] == "3/3 files"
    assert "same count/file" in rows_by_code["769"]["evidence"]
    assert rows_by_code["772"]["coverage"] == "2/3 files"
    assert rows_by_code["772"]["missing_files"] == ["A03T.gdf"]
    assert "missing A03T.gdf" in rows_by_code["772"]["evidence"]
    assert other_by_code["768"]["use_as"] == "Trial timing"
    assert other_by_code["1023"]["use_as"] == "Exclude bad trials"
    assert other_by_code["1023"]["reason"] == "Rejected / artifact trial"
    assert other_by_code["32766"]["use_as"] == "Ignore"
    assert other_by_code["32766"]["reason"] == "System / boundary marker"
    assert candidate.class_map == {}
    assert candidate.class_map_source == ""


def test_build_interpretation_candidate_reviews_external_event_order_placement(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    label_path = tmp_path / "A01T.mat"
    savemat(label_path, {"classlabel": [1, 2, 1, 2]})
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "768": {"count": 4, "description": "768"},
                "1023": {"count": 1, "description": "artifact"},
            }
        },
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=["/data/A01T.gdf"],
            label_carriers=[str(label_path)],
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "label_carrier_choices": {
                str(label_path): {
                    "label_field": "classlabel",
                    "anchor": "768",
                    "placement_method": "eeg_event",
                }
            }
        },
    )

    review = candidate.label_carrier_plan[0]["placement_review"]

    assert review["method"] == "eeg_event"
    assert review["status"] == "ready"
    assert review["label_rows"] == 4
    assert review["selected_eeg_events"] == 4
    assert review["matched"] == 4
    assert review["excluded_eeg_events"] == 1


def test_build_interpretation_candidate_reviews_multiple_event_order_targets(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    label_path = tmp_path / "A01T.mat"
    savemat(label_path, {"classlabel": [1, 2, 1, 2]})
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "768": {"count": 4, "description": "trial start"},
                "769": {"count": 2, "description": "769"},
                "770": {"count": 2, "description": "770"},
                "1023": {"count": 1, "description": "artifact"},
            }
        },
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=["/data/A01T.gdf"],
            label_carriers=[str(label_path)],
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "label_carrier_choices": {
                str(label_path): {
                    "label_field": "classlabel",
                    "target_event_codes": ["769", "770"],
                    "placement_method": "eeg_event",
                }
            }
        },
    )

    plan = candidate.label_carrier_plan[0]
    review = plan["placement_review"]

    assert plan["selected_target_event_codes"] == ["769", "770"]
    assert plan["selected_anchor"] == "769"
    assert review["method"] == "eeg_event"
    assert review["status"] == "ready"
    assert review["target_events"] == ["769", "770"]
    assert review["selected_eeg_events"] == 4
    assert review["matched"] == 4
    assert review["excluded_eeg_events"] == 1


def test_build_interpretation_candidate_explains_event_order_count_mismatch(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    label_path = tmp_path / "A01T.mat"
    savemat(label_path, {"classlabel": [1, 2, 1, 2]})
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "768": {"count": 5, "description": "trial start"},
                "769": {"count": 2, "description": "769"},
                "770": {"count": 2, "description": "770"},
            }
        },
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=["/data/A01T.gdf"],
            label_carriers=[str(label_path)],
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "label_carrier_choices": {
                str(label_path): {
                    "label_field": "classlabel",
                    "target_event_codes": ["768"],
                    "placement_method": "eeg_event",
                }
            }
        },
    )

    review = candidate.label_carrier_plan[0]["placement_review"]

    assert review["status"] == "needs_review"
    assert review["label_rows"] == 4
    assert review["selected_eeg_events"] == 5
    assert review["unlabeled_eeg_events"] == 1
    assert review["unmatched_label_rows"] == 0
    assert (
        review["summary"]
        == "1 selected EEG event has no label (4 label rows, 5 selected events)."
    )
    assert (
        review["next_action"]
        == "Uncheck extra target events or choose a label field with more rows."
    )


def test_build_interpretation_candidate_blocks_missing_event_order_target(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    label_path = tmp_path / "A01T.mat"
    savemat(label_path, {"classlabel": [1, 2]})
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "768": {"count": 2, "description": "trial start"},
            }
        },
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=["/data/A01T.gdf"],
            label_carriers=[str(label_path)],
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "label_carrier_choices": {
                str(label_path): {
                    "label_field": "classlabel",
                    "target_event_codes": ["769"],
                    "placement_method": "eeg_event",
                }
            }
        },
    )

    review = candidate.label_carrier_plan[0]["placement_review"]
    assert review["status"] == "blocked"
    assert any(
        "Target EEG event(s) were not found" in item
        for item in candidate.blocked_reasons
    )


def test_build_interpretation_candidate_reviews_event_code_placement(
    tmp_path,
    monkeypatch,
):
    labels = tmp_path / "labels.tsv"
    labels.write_text(
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

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=["/data/session.edf"],
            label_carriers=[str(labels)],
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "label_carrier_choices": {
                str(labels): {
                    "label_field": "condition",
                    "anchor": "event_code",
                    "placement_method": "event_code",
                }
            }
        },
    )

    review = candidate.label_carrier_plan[0]["placement_review"]

    assert review["method"] == "event_code"
    assert review["status"] == "ready"
    assert review["matched_codes"] == ["11", "12"]
    assert review["missing_codes"] == []
    assert review["code_mappings"] == [
        {
            "event_code": "11",
            "label_values": ["left"],
            "label_rows": 1,
            "eeg_event_count": 2,
            "status": "ready",
            "conflict": False,
            "duplicate_rows": False,
            "review": "Ready.",
        },
        {
            "event_code": "12",
            "label_values": ["right"],
            "label_rows": 1,
            "eeg_event_count": 1,
            "status": "ready",
            "conflict": False,
            "duplicate_rows": False,
            "review": "Ready.",
        },
    ]
    assert review["summary"] == "All 2 label event codes match EEG events."


def test_build_interpretation_candidate_flags_repeated_event_code_rows(
    tmp_path,
    monkeypatch,
):
    labels = tmp_path / "labels.tsv"
    labels.write_text(
        "event_code\tcondition\n11\tleft\n12\tright\n11\tleft\n",
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

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=["/data/session.edf"],
            label_carriers=[str(labels)],
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "label_carrier_choices": {
                str(labels): {
                    "label_field": "condition",
                    "anchor": "event_code",
                    "placement_method": "event_code",
                }
            }
        },
    )

    review = candidate.label_carrier_plan[0]["placement_review"]

    assert review["status"] == "needs_review"
    assert review["duplicate_codes"] == ["11"]
    assert review["code_mappings"][0]["duplicate_rows"] is True
    assert review["code_mappings"][0]["review"] == (
        "Repeated rows; event-code placement expects one row per code."
    )


def test_build_interpretation_candidate_flags_conflicting_event_code_labels(
    tmp_path,
    monkeypatch,
):
    labels = tmp_path / "labels.tsv"
    labels.write_text(
        "event_code\tcondition\n11\tleft\n11\tright\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {"events": {"11": {"count": 2, "description": "11"}}},
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=["/data/session.edf"],
            label_carriers=[str(labels)],
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "label_carrier_choices": {
                str(labels): {
                    "label_field": "condition",
                    "anchor": "event_code",
                    "placement_method": "event_code",
                }
            }
        },
    )

    review = candidate.label_carrier_plan[0]["placement_review"]

    assert review["status"] == "needs_review"
    assert review["conflict_codes"] == ["11"]
    assert review["duplicate_codes"] == []
    assert review["code_mappings"][0]["label_values"] == ["left", "right"]
    assert review["code_mappings"][0]["review"] == (
        "Same code maps to multiple label values."
    )


def test_build_interpretation_candidate_defaults_marker_table_to_event_code_placement(
    tmp_path,
    monkeypatch,
):
    labels = tmp_path / "markers.csv"
    labels.write_text(
        "event_code,label\n31,target\n32,nontarget\n31,target\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "31": {"count": 2, "description": "target marker"},
                "32": {"count": 1, "description": "nontarget marker"},
            }
        },
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            source_kind="folder",
            eeg_files=["/data/sub-01.gdf"],
            label_carriers=[str(labels)],
            label_carrier_sources={str(labels): "user_added"},
            bids={"is_bids": False, "events_files": []},
        ),
    )

    plan = candidate.label_carrier_plan[0]
    review = plan["placement_review"]

    assert plan["selected_label_field"] == "label"
    assert plan["placement_method"] == "event_code"
    assert plan["selected_anchor"] == "event_code"
    assert review["method"] == "event_code"
    assert review["status"] == "needs_review"
    assert review["duplicate_codes"] == ["31"]
    assert review["matched_codes"] == ["31", "32"]


def test_build_interpretation_candidate_uses_format_neutral_event_pattern(
    monkeypatch,
):
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "1": {"count": 40, "description": "1"},
                "11": {"count": 20, "description": "11"},
                "12": {"count": 20, "description": "12"},
            }
        },
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            source_kind="folder",
            eeg_files=["/data/session.edf"],
            label_carriers=[],
            label_carrier_sources={},
            bids={"is_bids": False, "events_files": []},
        ),
        choices={"label_carrier": "embedded_events"},
    )

    preview = candidate.internal_event_preview
    candidate_codes = [row["event_code"] for row in preview["candidate_label_events"]]
    other_by_code = {row["event_code"]: row for row in preview["not_used_events"]}

    assert candidate_codes == ["11", "12"]
    assert preview["candidate_label_events"][0]["evidence"].startswith("Repeated count")
    assert other_by_code["1"]["use_as"] == "Trial timing"


def test_build_interpretation_candidate_warns_on_run_dependent_t1_t2_events(
    monkeypatch,
):
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "T0": {"count": 15, "description": "T0"},
                "T1": {"count": 15, "description": "T1"},
                "T2": {"count": 15, "description": "T2"},
            }
        },
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            source_kind="folder",
            eeg_files=["/data/S001R04.edf", "/data/S001R08.edf"],
            label_carriers=[],
            label_carrier_sources={},
            bids={"is_bids": False, "events_files": []},
        ),
        choices={"label_carrier": "embedded_events"},
    )

    assert candidate.internal_event_preview["run_dependent_semantics"] is True
    assert candidate.internal_event_preview["run_dependent_mapping"]["status"] == (
        "needs_confirmation"
    )
    assert candidate.internal_event_preview["run_dependent_mapping"]["files"] == [
        {
            "file": "S001R04.edf",
            "run": "04",
            "events": {"T1": "", "T2": ""},
        },
        {
            "file": "S001R08.edf",
            "run": "08",
            "events": {"T1": "", "T2": ""},
        },
    ]
    assert any(
        "Confirm run-dependent T1/T2 event mapping" in item
        for item in candidate.confirmation_items
    )
    assert any("T1/T2" in item and "run" in item for item in candidate.warnings)


def test_build_interpretation_candidate_preserves_run_dependent_event_mapping(
    monkeypatch,
):
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "T1": {"count": 15, "description": "T1"},
                "T2": {"count": 15, "description": "T2"},
            }
        },
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            source_kind="folder",
            eeg_files=["/data/S001R04.edf"],
            label_carriers=[],
            label_carrier_sources={},
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "label_carrier": "embedded_events",
            "run_event_mappings": {
                "S001R04.edf": {"T1": "left fist", "T2": "right fist"},
            },
        },
    )

    assert candidate.run_event_mappings == {
        "S001R04.edf": {"T1": "left fist", "T2": "right fist"},
    }
    assert not any(
        "Confirm run-dependent T1/T2 event mapping" in item
        for item in candidate.confirmation_items
    )


def test_build_interpretation_candidate_keeps_response_and_comment_events_out_of_labels(
    monkeypatch,
):
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "Stimulus/S 1": {"count": 20, "description": "Stimulus/S 1"},
                "Response/R 1": {"count": 20, "description": "Response/R 1"},
                "Comment": {"count": 1, "description": "Comment"},
                "New Segment/": {"count": 1, "description": "New Segment/"},
            }
        },
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            source_kind="folder",
            eeg_files=["/data/sub-01.vhdr"],
            label_carriers=[],
            label_carrier_sources={},
            bids={"is_bids": False, "events_files": []},
        ),
        choices={"label_carrier": "embedded_events"},
    )

    not_used = {
        row["event_code"]: row
        for row in candidate.internal_event_preview["not_used_events"]
    }
    assert not_used["Response/R 1"]["use_as"] == "Response"
    assert not_used["Comment"]["use_as"] == "Ignore"
    assert not_used["New Segment/"]["use_as"] == "Ignore"
