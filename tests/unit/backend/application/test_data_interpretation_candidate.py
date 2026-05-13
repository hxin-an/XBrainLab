from pathlib import Path

from XBrainLab.backend.application import data_interpretation_internal_events
from XBrainLab.backend.application.data_interpretation_candidate import (
    InterpretationCandidate,
    build_interpretation_candidate,
)
from XBrainLab.backend.application.data_interpretation_metadata import (
    FileMetadataResolution,
    MetadataFieldResolution,
)
from XBrainLab.backend.application.data_interpretation_scan import ScanResult


def _field(name: str, value: str | None = None) -> MetadataFieldResolution:
    return MetadataFieldResolution(
        field=name,
        value=value,
        source="test",
        decision="safe" if value else "needs_confirmation",
        reason="test",
    )


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


def test_build_interpretation_candidate_applies_user_choices_and_recipe_trace():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(),
        choices={
            "metadata_overrides": {
                "sub-01_task-mi_raw.fif": {"subject": "S01"},
            },
            "class_map": {"left": "0"},
            "event_roles": {"trial_type": "class cue"},
            "label_carrier_choices": {
                "sub-01_task-mi_events.tsv": {"label_field": "trial_type"},
            },
        },
    )

    assert isinstance(candidate, InterpretationCandidate)
    assert candidate.metadata[0].subject.value == "S01"
    assert candidate.metadata[0].subject.source == "user_override"
    assert candidate.event_roles["trial_type"] == "class cue"
    assert candidate.class_map == {"left": "0"}
    assert candidate.class_map_source == "user_choices"
    assert "choices:metadata_overrides" in candidate.recipe_trace
    assert "choices:class_map" in candidate.recipe_trace
    assert "choices:event_roles" in candidate.recipe_trace
    assert "choices:label_carriers" in candidate.recipe_trace


def test_build_interpretation_candidate_previews_tabular_label_class_values(tmp_path):
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
    assert candidate.class_map == {"left": "left", "right": "right"}
    assert candidate.class_map_source == "label_carriers"
    assert (
        "Confirm label carrier alignment, anchor event, and class map before applying."
        in candidate.confirmation_items
    )
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


def test_build_interpretation_candidate_previews_bids_level_labels(tmp_path):
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

    assert candidate.class_map == {
        "left": "Left hand",
        "right": "Right hand",
    }
    assert "choices:class_map" not in candidate.recipe_trace


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
                    "granularity": "trial",
                }
            },
        },
    )

    assert candidate.label_carrier_plan[0]["format"] == "MAT"
    assert candidate.label_carrier_plan[0]["selected_label_field"] == "classlabel"
    assert candidate.class_map == {"1": "1", "2": "2"}
    assert candidate.class_map_source == "label_carriers"
    assert (
        "Confirm label carrier alignment, anchor event, and class map before applying."
        in candidate.confirmation_items
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
        scan=_scan(eeg_files=[]),
        choices={"selected_eeg_files": []},
    )

    assert candidate.selected_eeg_files == []
    assert "No EEG files were selected for interpretation." in candidate.blocked_reasons


def test_build_interpretation_candidate_blocks_selected_files_missing_from_scan():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(eeg_files=["/data/sub-01_task-mi_raw.fif"]),
        choices={
            "recipe_id": "recipe-1",
            "selected_eeg_files": [
                "/data/sub-01_task-mi_raw.fif",
                "/data/missing_raw.fif",
            ],
        },
    )

    assert "missing_raw.fif" in candidate.blocked_reasons[0]
    assert "not found in the current scan" in candidate.blocked_reasons[0]


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


def test_build_interpretation_candidate_blocks_required_label_carriers_missing_from_scan():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(label_carriers=["/data/sub-01_task-mi_events.tsv"]),
        choices={
            "recipe_id": "recipe-1",
            "required_label_carriers": [
                "/data/sub-01_task-mi_events.tsv",
                "/data/missing_events.tsv",
            ],
        },
    )

    assert "missing_events.tsv" in candidate.blocked_reasons[0]
    assert "label/event carrier" in candidate.blocked_reasons[0]
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
    assert "label_carrier" not in candidate.event_roles
    assert candidate.confirmation_items == []
    assert "choices:skip_labels" in candidate.recipe_trace


def test_build_interpretation_candidate_remaps_saved_label_carrier_choices():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(label_carriers=["/data/renamed_events.tsv"]),
        choices={
            "recipe_id": "recipe-1",
            "required_label_carriers": ["/data/original_events.tsv"],
            "label_carrier_remap": {
                "/data/original_events.tsv": "/data/renamed_events.tsv",
            },
            "label_carrier_choices": {
                "/data/original_events.tsv": {
                    "label_field": "trial_type",
                    "anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "trial",
                    "role": "class cue labels",
                }
            },
        },
    )

    assert candidate.blocked_reasons == []
    assert candidate.label_carrier_plan[0]["path"] == "/data/renamed_events.tsv"
    assert candidate.label_carrier_plan[0]["selected_label_field"] == "trial_type"
    assert candidate.label_carrier_plan[0]["selected_anchor"] == "onset"
    assert candidate.label_carrier_plan[0]["role"] == "class cue labels"
    assert "choices:label_carrier_remap" in candidate.recipe_trace


def test_build_interpretation_candidate_preserves_user_added_label_sources():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[
                "/data/sub-01_task-mi_events.tsv",
                "/external/sub-01_task-mi_labels.tsv",
            ],
            label_sources=["/external"],
            label_carrier_sources={
                "/data/sub-01_task-mi_events.tsv": "auto",
                "/external/sub-01_task-mi_labels.tsv": "/external",
            },
        ),
    )

    plans = {item["path"]: item for item in candidate.label_carrier_plan}

    assert candidate.label_sources == ["/external"]
    assert plans["/data/sub-01_task-mi_events.tsv"]["source_kind"] == (
        "auto_discovered"
    )
    assert plans["/external/sub-01_task-mi_labels.tsv"]["source_kind"] == ("user_added")
    assert plans["/external/sub-01_task-mi_labels.tsv"]["source_location"] == (
        "/external"
    )


def test_build_interpretation_candidate_uses_real_internal_event_evidence(
    monkeypatch,
):
    def fake_read(path: str):
        name = Path(path).name
        counts_by_file = {
            "A01T.gdf": {"768": 108, "769": 36, "770": 36, "772": 36, "1023": 2},
            "A02T.gdf": {"768": 108, "769": 36, "770": 36, "772": 36, "1023": 2},
            "A03T.gdf": {"768": 72, "769": 36, "770": 36, "1023": 2},
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
    assert other_by_code["1023"]["reason"] == "Event role needs review"
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


def test_build_interpretation_candidate_reviews_event_code_placement(
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

    assert review["method"] == "event_code"
    assert review["status"] == "ready"
    assert review["matched_codes"] == ["11", "12"]
    assert review["missing_codes"] == []
    assert review["summary"] == "All 2 label event codes match EEG events."


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
    assert review["status"] == "ready"
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
