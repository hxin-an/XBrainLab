from XBrainLab.backend.application.data_interpretation_label_carriers import (
    build_label_carrier_plan,
    infer_class_map_from_label_carrier_plan,
    normalize_label_carrier_choices,
)


def test_label_carrier_plan_uses_user_choices_for_bids_events(tmp_path):
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text("onset\tduration\ttrial_type\n0\t1\tleft\n", encoding="utf-8")

    plan = build_label_carrier_plan(
        [str(events)],
        {
            events.name: {
                "label_field": "trial_type",
                "anchor": "onset",
                "time_model": "seconds",
                "granularity": "trial",
                "role": "class cue labels",
                "target_file": "sub-01_raw.fif",
            }
        },
    )

    assert plan == [
        {
            "path": str(events),
            "name": events.name,
            "format": "BIDS events",
            "source_kind": "auto_discovered",
            "source_location": "",
            "label_candidates": ["trial_type"],
            "anchor_candidates": ["onset"],
            "duration_candidates": ["duration"],
            "selected_label_field": "trial_type",
            "selected_anchor": "onset",
            "selected_duration_field": "duration",
            "label_row_count": 1,
            "label_value_counts": {"left": 1},
            "time_model": "seconds",
            "granularity": "trial",
            "placement_method": "interval",
            "role": "class cue labels",
            "selected_target_file": "sub-01_raw.fif",
            "decision": "needs_confirmation",
            "reason": (
                "BIDS events carrier has candidate label fields and anchors; "
                "review the selected alignment before applying."
            ),
        }
    ]


def test_normalize_label_carrier_choices_accepts_path_or_name_keys(tmp_path):
    carrier = tmp_path / "labels.csv"
    choices = normalize_label_carrier_choices(
        {
            str(carrier): {
                "label_field": "label",
                "anchor": "sample",
                "placement_method": "time_field",
                "duration_field": "duration",
            },
            carrier.name: {"role": "artifact markers"},
        }
    )

    assert choices[str(carrier)]["label_field"] == "label"
    assert choices[str(carrier)]["placement_method"] == "time_field"
    assert choices[str(carrier)]["duration_field"] == "duration"
    assert choices[carrier.name]["role"] == "artifact markers"


def test_normalize_label_carrier_choices_accepts_event_code_placement(tmp_path):
    carrier = tmp_path / "labels.csv"
    choices = normalize_label_carrier_choices(
        {
            carrier.name: {
                "label_field": "condition",
                "anchor": "marker_code",
                "placement_method": "event_code",
            }
        }
    )

    assert choices[carrier.name]["placement_method"] == "event_code"


def test_label_carrier_plan_counts_label_rows_and_values(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "sample,label\n128,left\n256,right\n384,\n512,left\n",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(labels)],
        {labels.name: {"label_field": "label", "anchor": "sample"}},
    )

    assert plan[0]["label_row_count"] == 3
    assert plan[0]["label_value_counts"] == {"left": 2, "right": 1}


def test_infer_class_map_from_tabular_label_carrier_plan(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "sample,label\n128,left\n256,right\n384,n/a\n512,left\n",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(labels)],
        {labels.name: {"label_field": "label", "anchor": "sample"}},
    )

    assert infer_class_map_from_label_carrier_plan(plan) == {
        "left": "left",
        "right": "right",
    }


def test_infer_class_map_uses_bids_events_json_levels(tmp_path):
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

    plan = build_label_carrier_plan(
        [str(events)],
        {events.name: {"label_field": "trial_type", "anchor": "onset"}},
    )

    assert infer_class_map_from_label_carrier_plan(plan) == {
        "left": "Left hand",
        "right": "Right hand",
    }


def test_infer_class_map_uses_inherited_bids_events_json_levels(tmp_path):
    bids_root = tmp_path / "bids"
    eeg_dir = bids_root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    events = eeg_dir / "sub-01_task-mi_run-1_events.tsv"
    inherited_sidecar = bids_root / "task-mi_events.json"
    events.write_text(
        "onset\tduration\ttrial_type\n0.0\t1.0\tleft\n1.0\t1.0\tright\n",
        encoding="utf-8",
    )
    inherited_sidecar.write_text(
        '{"trial_type":{"Levels":{"left":"Left hand","right":"Right hand"}}}',
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(events)],
        {events.name: {"label_field": "trial_type", "anchor": "onset"}},
    )

    assert infer_class_map_from_label_carrier_plan(plan) == {
        "left": "Left hand",
        "right": "Right hand",
    }


def test_infer_class_map_from_mat_label_carrier_plan(tmp_path):
    import numpy as np
    from scipy.io import savemat

    labels = tmp_path / "A01T.mat"
    savemat(
        labels,
        {
            "classlabel": np.array([1.0, 2.0, np.nan, 2.0]),
            "cue_onset": np.array([100, 250, 400, 550]),
        },
    )

    plan = build_label_carrier_plan(
        [str(labels)],
        {labels.name: {"label_field": "classlabel", "anchor": "cue_onset"}},
    )

    assert infer_class_map_from_label_carrier_plan(plan) == {
        "1": "1",
        "2": "2",
    }
