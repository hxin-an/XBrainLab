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

    row = plan[0]
    assert row["path"] == str(events)
    assert row["format"] == "BIDS events"
    assert row["label_candidates"] == ["trial_type"]
    assert row["anchor_candidates"] == ["onset"]
    assert row["time_field_candidates"] == ["onset"]
    assert row["interval_start_candidates"] == ["onset"]
    assert row["duration_candidates"] == ["duration"]
    assert row["selected_label_field"] == "trial_type"
    assert row["selected_anchor"] == "onset"
    assert row["selected_duration_field"] == "duration"
    assert row["label_row_count"] == 1
    assert row["label_value_counts"] == {"left": 1}
    assert row["selected_anchor_stats"]["numeric_count"] == 1
    assert row["selected_duration_stats"]["numeric_count"] == 1
    assert row["placement_method"] == "interval"
    assert row["selected_target_file"] == "sub-01_raw.fif"


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


def test_normalize_label_carrier_choices_accepts_event_order_targets(tmp_path):
    carrier = tmp_path / "labels.mat"
    choices = normalize_label_carrier_choices(
        {
            carrier.name: {
                "label_field": "classlabel",
                "target_event_codes": ["769", "770", "", "770"],
                "placement_method": "eeg_event",
            }
        }
    )

    assert choices[carrier.name]["target_event_codes"] == ["769", "770"]


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


def test_label_carrier_plan_exposes_time_label_preview(tmp_path):
    labels = tmp_path / "events.tsv"
    labels.write_text(
        "onset\ttrial_type\n0\tleft\n2.5\tright\n5\tleft\n",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(labels)],
        {labels.name: {"label_field": "trial_type", "anchor": "onset"}},
    )

    assert plan[0]["time_label_preview"] == [
        {"time": "0", "label": "left"},
        {"time": "2.5", "label": "right"},
        {"time": "5", "label": "left"},
    ]


def test_label_carrier_plan_exposes_event_code_candidates_and_stats(tmp_path):
    labels = tmp_path / "labels.tsv"
    labels.write_text(
        "event_code\tcondition\n11\tleft\n12\tright\n11\tleft\n",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(labels)],
        {
            labels.name: {
                "label_field": "condition",
                "anchor": "event_code",
                "placement_method": "event_code",
            }
        },
    )

    assert plan[0]["event_code_candidates"] == ["event_code"]
    assert plan[0]["selected_anchor_stats"]["value_counts"] == {
        "11": 2,
        "12": 1,
    }
    assert plan[0]["selected_anchor_stats"]["numeric_count"] == 3


def test_label_carrier_plan_defaults_marker_table_to_event_code_placement(tmp_path):
    labels = tmp_path / "markers.csv"
    labels.write_text(
        "event_code,label\n31,target\n32,nontarget\n31,target\n",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan([str(labels)], {})

    row = plan[0]
    assert row["selected_label_field"] == "label"
    assert row["event_code_candidates"] == ["event_code"]
    assert row["selected_anchor"] == "event_code"
    assert row["placement_method"] == "event_code"
    assert row["selected_anchor_stats"]["value_counts"] == {
        "31": 2,
        "32": 1,
    }


def test_label_carrier_plan_exposes_mat_interval_fields(tmp_path):
    import numpy as np
    from scipy.io import savemat

    labels = tmp_path / "segments.mat"
    savemat(
        labels,
        {
            "classlabel": np.array([1, 2, 1]),
            "onset": np.array([0.0, 2.0, 4.0]),
            "duration": np.array([1.0, 1.5, 1.0]),
        },
    )

    plan = build_label_carrier_plan([str(labels)], {})

    row = plan[0]
    assert "onset" in row["time_field_candidates"]
    assert row["duration_candidates"] == ["duration"]
    assert row["selected_duration_field"] == "duration"
    assert row["placement_method"] == "interval"
    assert row["selected_duration_stats"]["numeric_count"] == 3


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
