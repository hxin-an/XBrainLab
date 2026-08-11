import json
from contextlib import contextmanager
from pathlib import Path

import XBrainLab.backend.application.data_interpretation_label_carriers as label_carriers
from XBrainLab.backend.application.data_interpretation_bids_resources import (
    BidsEventsJsonReader,
)
from XBrainLab.backend.application.data_interpretation_label_carriers import (
    _bids_label_field_profile,
    _bids_label_field_recommendation,
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
    assert row["bids_event_columns"] == ["onset", "duration", "trial_type"]
    assert row["placement_method"] == "interval"
    assert row["selected_target_file"] == "sub-01_raw.fif"


def test_label_carrier_plan_accepts_bids_events_with_utf8_bom(tmp_path):
    events = tmp_path / "sub-01_task-rest_events.tsv"
    events.write_text(
        "\ufeffonset\tduration\ttrial_type\tvalue\tsample\n"
        "0.0\t0.0\tstart\t1\t0\n"
        "0.2\t0.0\tstimulus\t2\t1000\n",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(events)],
        {
            events.name: {
                "label_field": "trial_type",
                "anchor": "onset",
                "duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
            }
        },
    )

    row = plan[0]
    assert row["bids_event_columns"] == [
        "onset",
        "duration",
        "trial_type",
        "value",
        "sample",
    ]
    assert row["selected_anchor_stats"]["numeric_count"] == 2
    assert row["label_value_counts"] == {"start": 1, "stimulus": 1}
    assert row["time_label_preview"] == [
        {"time": "0.0", "label": "start"},
        {"time": "0.2", "label": "stimulus"},
    ]


def test_label_carrier_plan_flags_bids_events_missing_sidecar_and_duration(tmp_path):
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\ttrial_type\tresponse_time\tHED\tchannel\n0\tleft\t0.5\tMotor\tC3\n",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan([str(events)], {})

    row = plan[0]
    assert row["format"] == "BIDS events"
    assert row["bids_event_columns"] == [
        "onset",
        "trial_type",
        "response_time",
        "HED",
        "channel",
    ]
    assert any("events.json sidecar is missing" in item for item in row["warnings"])
    assert any("duration column is missing" in item for item in row["warnings"])
    assert row["events_json_sidecar_present"] is False


def test_label_carrier_plan_blocks_bids_events_without_onset(tmp_path):
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text("trial_type\tvalue\nleft\t1\n", encoding="utf-8")

    plan = build_label_carrier_plan([str(events)], {})

    row = plan[0]
    assert any("onset column is missing" in item for item in row["warnings"])
    assert row["placement_method"] == "event_code"


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
        {
            labels.name: {
                "label_field": "label",
                "anchor": "sample",
                "role": "class labels",
            }
        },
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


def test_label_carrier_plan_does_not_treat_trial_column_as_eeg_event(tmp_path):
    labels = tmp_path / "labels.tsv"
    labels.write_text("trial\tclass\n1\tleft\n2\tright\n", encoding="utf-8")

    plan = build_label_carrier_plan([str(labels)], {})

    row = plan[0]
    assert row["selected_label_field"] == "class"
    assert row["anchor_candidates"] == ["trial"]
    assert row["placement_method"] == "eeg_event"
    assert row["selected_anchor"] == "trial order"
    assert row["selected_target_event_codes"] == []


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
        {
            labels.name: {
                "label_field": "label",
                "anchor": "sample",
                "role": "class labels",
            }
        },
    )

    assert infer_class_map_from_label_carrier_plan(plan) == {
        "left": "left",
        "right": "right",
    }


def test_bids_events_json_levels_are_suggestions_not_classes(tmp_path):
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

    assert infer_class_map_from_label_carrier_plan(plan) == {}
    assert plan[0]["events_json_sidecar_present"] is True
    assert plan[0]["value_decisions"]["left"]["suggested_name"] == "Left hand"
    assert plan[0]["value_decisions"]["right"]["suggested_name"] == "Right hand"


def test_bids_multi_run_recommendation_prefers_described_value_refinement(tmp_path):
    events_files = []
    for run in (1, 2):
        events = tmp_path / f"sub-01_task-P300_run-{run}_events.tsv"
        events.write_text(
            "onset\tduration\ttrial_type\tvalue\n"
            "0\t0\tstimulus\tstandard\n"
            "1\t0\tstimulus\toddball\n"
            "2\t0\tresponse\tresponse\n"
            "3\t0\tstimulus\tstandard\n",
            encoding="utf-8",
        )
        events.with_suffix(".json").write_text(
            "{"
            '"trial_type":{"Levels":{"stimulus":"Auditory stimulus",'
            '"response":"Behavioral response"}},'
            '"value":{"Levels":{"standard":"Standard tone",'
            '"oddball":"Oddball tone","response":"Button response"}}'
            "}",
            encoding="utf-8",
        )
        events_files.append(str(events))

    plan = build_label_carrier_plan(
        events_files,
        {},
        recommend_bids_label_field=True,
    )

    assert {row["selected_label_field"] for row in plan} == {"value"}
    recommendation = plan[0]["label_field_recommendation"]
    assert recommendation["field"] == "value"
    assert recommendation["source"] == "bids_multi_run_evidence"
    assert recommendation["reason_code"] == "value_has_described_classes"
    assert recommendation["facts"]["selected_run_count"] == 2
    assert "reason" not in recommendation
    assert "evidence" not in recommendation
    [details] = [
        row["label_field_recommendation_details"]
        for row in plan
        if "label_field_recommendation_details" in row
    ]
    assert details["evidence"]["value_refines_trial_type"] is True
    assert details["evidence"]["sidecar_level_run_coverage"]["value"] == 1.0


def test_bids_recommendation_requires_observed_rows_for_described_value(tmp_path):
    events = tmp_path / "sub-01_task-P300_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n0\t0\tstimulus\t\n1\t0\tresponse\t\n",
        encoding="utf-8",
    )
    events.with_suffix(".json").write_text(
        "{"
        '"trial_type":{"Levels":{"stimulus":"Auditory stimulus",'
        '"response":"Behavioral response"}},'
        '"value":{"Levels":{"1":"Target", "2":"Non-target"}}'
        "}",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(events)],
        {},
        recommend_bids_label_field=True,
    )

    assert plan[0]["selected_label_field"] != "value"
    recommendation = plan[0].get("label_field_recommendation", {})
    assert recommendation.get("field") != "value"


def test_bids_recommendation_accepts_numeric_codes_with_semantic_descriptions(
    tmp_path,
):
    events = tmp_path / "sub-01_task-P300_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "0\t0\tstimulus\t1\n"
        "1\t0\tstimulus\t2\n"
        "2\t0\tstimulus\t1\n"
        "3\t0\tstimulus\t2\n",
        encoding="utf-8",
    )
    events.with_suffix(".json").write_text(
        "{"
        '"trial_type":{"Levels":{"stimulus":"Stimulus"}},'
        '"value":{"Levels":{"1":"Left hand", "2":"Right hand"}}'
        "}",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(events)],
        {},
        recommend_bids_label_field=True,
    )

    assert plan[0]["selected_label_field"] == "value"
    assert plan[0]["label_field_recommendation"]["reason_code"] == (
        "value_has_described_classes"
    )


def test_bids_recommendation_keeps_complete_trial_type_over_sparse_value(tmp_path):
    events = tmp_path / "sub-01_task-condition_events.tsv"
    rows = [
        "onset\tduration\ttrial_type\tvalue",
        "0\t0\tstimulus\t1",
        "1\t0\tstimulus\t2",
    ]
    rows.extend(f"{index}\t0\tstimulus\t" for index in range(2, 10))
    events.write_text("\n".join(rows) + "\n", encoding="utf-8")
    events.with_suffix(".json").write_text(
        "{"
        '"trial_type":{"Levels":{"stimulus":"Stimulus"}},'
        '"value":{"Levels":{"1":"Condition A", "2":"Condition B"}}'
        "}",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(events)],
        {},
        recommend_bids_label_field=True,
    )

    assert plan[0]["selected_label_field"] == "trial_type"
    recommendation = plan[0]["label_field_recommendation"]
    assert recommendation["field"] == "trial_type"
    assert recommendation["reason_code"] == "trial_type_has_more_complete_rows"
    assert recommendation["facts"]["nonempty_row_coverage"] == {
        "trial_type": 1.0,
        "value": 0.2,
    }
    assert recommendation["facts"]["minimum_refinement_row_coverage"] == 1.0


def test_bids_recommendation_rejects_sidecar_levels_that_do_not_match_rows(tmp_path):
    events = tmp_path / "sub-01_task-P300_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n0\t0\tstimulus\t3\n1\t0\tstimulus\t4\n",
        encoding="utf-8",
    )
    events.with_suffix(".json").write_text(
        "{"
        '"trial_type":{"Levels":{"stimulus":"Stimulus"}},'
        '"value":{"Levels":{"1":"Left hand", "2":"Right hand"}}'
        "}",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(events)],
        {},
        recommend_bids_label_field=True,
    )

    assert plan[0]["selected_label_field"] != "value"
    recommendation = plan[0].get("label_field_recommendation", {})
    assert recommendation.get("field") != "value"


def test_bids_multi_run_recommendation_keeps_meaningful_trial_type(tmp_path):
    events_files = []
    for run in (1, 2):
        events = tmp_path / f"sub-01_task-mi_run-{run}_events.tsv"
        events.write_text(
            "onset\tduration\ttrial_type\tvalue\n"
            "0\t0\tleft_hand\t769\n"
            "1\t0\tright_hand\t770\n"
            "2\t0\tleft_hand\t769\n"
            "3\t0\tright_hand\t770\n",
            encoding="utf-8",
        )
        events.with_suffix(".json").write_text(
            "{"
            '"trial_type":{"Levels":{"left_hand":"Left hand",'
            '"right_hand":"Right hand"}},'
            '"value":{"Description":"Hardware trigger code"}'
            "}",
            encoding="utf-8",
        )
        events_files.append(str(events))

    plan = build_label_carrier_plan(
        events_files,
        {},
        recommend_bids_label_field=True,
    )

    assert {row["selected_label_field"] for row in plan} == {"trial_type"}
    recommendation = plan[0]["label_field_recommendation"]
    assert recommendation["field"] == "trial_type"
    assert recommendation["reason_code"] == "trial_type_over_numeric_value"
    assert recommendation["facts"]["selected_run_count"] == 2
    [details] = [
        row["label_field_recommendation_details"]
        for row in plan
        if "label_field_recommendation_details" in row
    ]
    assert details["evidence"]["numeric_only"]["value"] is True


def test_bids_explicit_label_field_precedes_multi_run_recommendation(tmp_path):
    events_files = []
    choices = {}
    for run in (1, 2):
        events = tmp_path / f"sub-01_task-P300_run-{run}_events.tsv"
        events.write_text(
            "onset\tduration\ttrial_type\tvalue\n"
            "0\t0\tstimulus\tstandard\n"
            "1\t0\tstimulus\toddball\n"
            "2\t0\tresponse\tresponse\n",
            encoding="utf-8",
        )
        events.with_suffix(".json").write_text(
            "{"
            '"trial_type":{"Levels":{"stimulus":"Stimulus",'
            '"response":"Response"}},'
            '"value":{"Levels":{"standard":"Standard",'
            '"oddball":"Oddball","response":"Response"}}'
            "}",
            encoding="utf-8",
        )
        events_files.append(str(events))
        choices[events.name] = {"label_field": "trial_type"}

    plan = build_label_carrier_plan(
        events_files,
        choices,
        recommend_bids_label_field=True,
    )

    assert {row["selected_label_field"] for row in plan} == {"trial_type"}
    recommendation = plan[0]["label_field_recommendation"]
    assert recommendation["field"] == "trial_type"
    assert recommendation["source"] == "explicit_selection"
    assert recommendation["reason_code"] == "explicit_selection"


def test_bids_partial_explicit_label_field_does_not_leak_to_other_runs(tmp_path):
    events_files = []
    for run in (1, 2):
        events = tmp_path / f"sub-01_task-P300_run-{run}_events.tsv"
        events.write_text(
            "onset\tduration\ttrial_type\tvalue\n"
            "0\t0\tstimulus\tstandard\n"
            "1\t0\tstimulus\toddball\n"
            "2\t0\tresponse\tresponse\n",
            encoding="utf-8",
        )
        events.with_suffix(".json").write_text(
            "{"
            '"trial_type":{"Levels":{"stimulus":"Auditory stimulus",'
            '"response":"Behavioral response"}},'
            '"value":{"Levels":{"standard":"Standard tone",'
            '"oddball":"Oddball tone","response":"Button response"}}'
            "}",
            encoding="utf-8",
        )
        events_files.append(str(events))

    plan = build_label_carrier_plan(
        events_files,
        {Path(events_files[0]).name: {"label_field": "trial_type"}},
        recommend_bids_label_field=True,
    )

    assert [row["selected_label_field"] for row in plan] == ["trial_type", "value"]
    assert plan[0]["label_field_recommendation"]["source"] == "explicit_selection"
    assert plan[1]["label_field_recommendation"]["source"] == (
        "bids_multi_run_evidence"
    )


def test_bids_explicit_heterogeneous_run_is_excluded_from_automatic_evidence(
    tmp_path,
):
    explicit_events = tmp_path / "sub-01_task-oddball_run-1_events.tsv"
    explicit_events.write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "0\t0\ttarget\tstimulus_01\n"
        "1\t0\tnontarget\tstimulus_02\n",
        encoding="utf-8",
    )
    explicit_events.with_suffix(".json").write_text(
        "{"
        '"trial_type":{"Levels":{"target":"Target trial",'
        '"nontarget":"Non-target trial"}},'
        '"value":{"Levels":{"stimulus_01":"Stimulus identifier 1",'
        '"stimulus_02":"Stimulus identifier 2"}}'
        "}",
        encoding="utf-8",
    )
    automatic_events = tmp_path / "sub-01_task-P300_run-2_events.tsv"
    automatic_events.write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "0\t0\tstimulus\tstandard\n"
        "1\t0\tstimulus\toddball\n"
        "2\t0\tresponse\tresponse\n",
        encoding="utf-8",
    )
    automatic_events.with_suffix(".json").write_text(
        "{"
        '"trial_type":{"Levels":{"stimulus":"Auditory stimulus",'
        '"response":"Behavioral response"}},'
        '"value":{"Levels":{"standard":"Standard tone",'
        '"oddball":"Oddball tone","response":"Button response"}}'
        "}",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(explicit_events), str(automatic_events)],
        {explicit_events.name: {"label_field": "trial_type"}},
        recommend_bids_label_field=True,
    )

    assert [row["selected_label_field"] for row in plan] == ["trial_type", "value"]
    assert plan[0]["label_field_recommendation"]["source"] == "explicit_selection"
    automatic_recommendation = plan[1]["label_field_recommendation"]
    assert automatic_recommendation["field"] == "value"
    assert automatic_recommendation["facts"]["selected_run_count"] == 1


def test_bids_recommendation_keeps_target_nontarget_trial_type_over_stimulus_ids(
    tmp_path,
):
    events = tmp_path / "sub-01_task-oddball_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "0\t0\ttarget\tstimulus_01\n"
        "1\t0\tnontarget\tstimulus_02\n"
        "2\t0\ttarget\tstimulus_03\n",
        encoding="utf-8",
    )
    events.with_suffix(".json").write_text(
        "{"
        '"trial_type":{"Levels":{"target":"Target trial",'
        '"nontarget":"Non-target trial"}},'
        '"value":{"Levels":{"stimulus_01":"Stimulus identifier 1",'
        '"stimulus_02":"Stimulus identifier 2",'
        '"stimulus_03":"Stimulus identifier 3"}}'
        "}",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(events)],
        {},
        recommend_bids_label_field=True,
    )

    assert plan[0]["selected_label_field"] == "trial_type"
    recommendation = plan[0]["label_field_recommendation"]
    assert recommendation["field"] == "trial_type"
    assert recommendation["reason_code"] == "trial_type_has_task_labels"


def test_bids_recommendation_requires_review_when_row_sample_is_truncated(tmp_path):
    plans = []
    for order in ("late_refinement", "early_refinement"):
        events = tmp_path / f"sub-01_task-P300_{order}_events.tsv"
        repeated = [f"{index}\t0\tstimulus\tstandard" for index in range(2048)]
        refinements = [
            "2048\t0\tstimulus\toddball",
            "2049\t0\tresponse\tresponse",
        ]
        body = (
            [*repeated, *refinements]
            if order == "late_refinement"
            else [*refinements, *repeated]
        )
        events.write_text(
            "onset\tduration\ttrial_type\tvalue\n" + "\n".join(body) + "\n",
            encoding="utf-8",
        )
        events.with_suffix(".json").write_text(
            "{"
            '"trial_type":{"Levels":{"stimulus":"Auditory stimulus",'
            '"response":"Behavioral response"}},'
            '"value":{"Levels":{"standard":"Standard tone",'
            '"oddball":"Oddball tone","response":"Button response"}}'
            "}",
            encoding="utf-8",
        )
        plan = build_label_carrier_plan(
            [str(events)],
            {},
            recommend_bids_label_field=True,
        )
        plans.append(plan[0])

    assert [row["selected_label_field"] for row in plans] == [
        "trial_type",
        "trial_type",
    ]
    assert all("label_field_recommendation" not in row for row in plans)


def test_bids_selected_field_levels_are_distinct_from_sidecar_presence(tmp_path):
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\n0\t0\tleft\n1\t0\tright\n",
        encoding="utf-8",
    )
    events.with_suffix(".json").write_text(
        '{"trial_type":{"Description":"Movement class"}}',
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(events)],
        {events.name: {"label_field": "trial_type"}},
    )

    assert plan[0]["events_json_sidecar_present"] is True
    assert plan[0]["selected_label_field_levels_available"] is False
    assert any(
        "does not define Levels for trial_type" in warning
        for warning in plan[0]["warnings"]
    )


def test_bids_label_field_profile_bounds_rows_per_selected_run(tmp_path):
    events = tmp_path / "sub-01_task-P300_run-1_events.tsv"
    rows = ["onset\tduration\ttrial_type\tvalue"]
    rows.extend(
        f"{index}\t0\tstimulus\t{'standard' if index % 2 else 'oddball'}"
        for index in range(2048)
    )
    rows.append("2048\t0\tlate_event\tlate_value")
    events.write_text("\n".join(rows) + "\n", encoding="utf-8")

    profile = _bids_label_field_profile(
        events,
        sidecar_reader=BidsEventsJsonReader.from_paths([]),
    )

    assert profile["sampled_row_count"] == 2048
    assert profile["row_truncated"] is True


def test_bids_label_field_profile_bounds_bytes_for_wide_rows(tmp_path):
    events = tmp_path / "sub-01_task-P300_events.tsv"
    events.write_bytes(
        b"onset\tduration\ttrial_type\tvalue\n"
        + b"0\t0\tstimulus\t"
        + (b"x" * 4096)
        + b"\n"
    )

    profile = _bids_label_field_profile(
        events,
        sidecar_reader=BidsEventsJsonReader.from_paths([]),
        row_limit=2048,
        byte_limit=256,
    )

    assert profile["sampled_byte_count"] <= 256
    assert profile["byte_truncated"] is True
    assert profile["sampled_row_count"] == 0
    assert "late_event" not in profile["counts"]["trial_type"]
    assert "late_value" not in profile["counts"]["value"]


def test_bids_multi_run_recommendation_is_computed_once_per_preview(
    tmp_path,
    monkeypatch,
):
    events_files = []
    for run in (1, 2, 3):
        events = tmp_path / f"sub-01_task-mi_run-{run}_events.tsv"
        events.write_text(
            "onset\tduration\ttrial_type\n0\t0\tleft\n1\t0\tright\n",
            encoding="utf-8",
        )
        events_files.append(str(events))

    calls = []

    def recommend_once(paths, choices, *, sidecar_reader):
        calls.append((tuple(paths), choices, sidecar_reader))
        return {
            "field": "trial_type",
            "source": "bids_multi_run_evidence",
            "reason": "test recommendation",
        }

    monkeypatch.setattr(
        label_carriers,
        "_bids_label_field_recommendation",
        recommend_once,
    )

    plan = build_label_carrier_plan(
        events_files,
        {},
        recommend_bids_label_field=True,
    )

    assert len(calls) == 1
    assert calls[0][0] == tuple(events_files)
    assert {row["selected_label_field"] for row in plan} == {"trial_type"}


def test_bids_recommendation_tsv_reads_enter_admitted_resource_guard(tmp_path):
    events_files = []
    for run in (1, 2):
        events = tmp_path / f"sub-01_task-mi_run-{run}_events.tsv"
        events.write_text(
            "onset\tduration\ttrial_type\n0\t0\tleft\n1\t0\tright\n",
            encoding="utf-8",
        )
        events_files.append(str(events))

    class RecordingResourceReader:
        def __init__(self):
            self.calls = []

        @contextmanager
        def guard(self, paths, *, purpose):
            self.calls.append((tuple(Path(path) for path in paths), purpose))
            yield

    reader = RecordingResourceReader()

    build_label_carrier_plan(
        events_files,
        {},
        resource_reader=reader,
        recommend_bids_label_field=True,
    )

    assert reader.calls[0] == (
        tuple(Path(path) for path in events_files),
        "BIDS label-field recommendation preview",
    )


def test_bids_recommendation_declines_truncated_total_sample(tmp_path):
    events_files = []
    for run in range(5):
        events = tmp_path / f"sub-01_task-mi_run-{run}_events.tsv"
        rows = ["onset\tduration\ttrial_type\tvalue"]
        rows.extend(
            f"{index}\t0\tstimulus\t{'standard' if index % 2 else 'oddball'}"
            for index in range(2100)
        )
        events.write_text("\n".join(rows) + "\n", encoding="utf-8")
        events_files.append(str(events))

    recommendation = _bids_label_field_recommendation(
        events_files,
        {},
        sidecar_reader=BidsEventsJsonReader.from_paths([]),
    )

    assert recommendation == {}


def test_bids_recommendation_publication_is_linear_and_run_samples_are_bounded(
    tmp_path,
):
    events_files = []
    run_count = 40
    for run in range(run_count):
        events = tmp_path / f"sub-01_task-P300_run-{run:02d}_events.tsv"
        events.write_text(
            "onset\tduration\ttrial_type\tvalue\n"
            "0\t0\tstimulus\tstandard\n"
            "1\t0\tstimulus\toddball\n",
            encoding="utf-8",
        )
        events.with_suffix(".json").write_text(
            "{"
            '"trial_type":{"Levels":{"stimulus":"Auditory stimulus"}},'
            '"value":{"Levels":{"standard":"Standard tone",'
            '"oddball":"Oddball tone"}}'
            "}",
            encoding="utf-8",
        )
        events_files.append(str(events))

    plan = build_label_carrier_plan(
        events_files,
        {},
        recommend_bids_label_field=True,
    )
    serialized = json.dumps(plan, sort_keys=True)

    recommendations = [row["label_field_recommendation"] for row in plan]
    assert {item["reason_code"] for item in recommendations} == {
        "value_has_described_classes"
    }
    assert all(
        "evidence" not in item and "reason" not in item for item in recommendations
    )
    details_rows = [row for row in plan if "label_field_recommendation_details" in row]
    assert len(details_rows) == 1
    evidence = details_rows[0]["label_field_recommendation_details"]["evidence"]
    assert evidence["sampled_row_counts_sample_limit"] == 12
    assert evidence["sampled_row_counts_total"] == run_count
    assert evidence["sampled_row_counts_truncated"] == run_count - 12
    assert len(evidence["sampled_row_counts"]) == 12
    assert serialized.count('"label_field_recommendation_details"') == 1
    assert len(serialized.encode("utf-8")) < 200_000


def test_inherited_bids_levels_are_suggestions_not_classes(tmp_path):
    bids_root = tmp_path / "bids"
    bids_root.mkdir()
    (bids_root / "dataset_description.json").write_text(
        '{"Name":"label-carrier-test","BIDSVersion":"1.11.1"}',
        encoding="utf-8",
    )
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

    assert infer_class_map_from_label_carrier_plan(plan) == {}
    assert plan[0]["value_decisions"]["left"]["suggested_name"] == "Left hand"
    assert plan[0]["value_decisions"]["right"]["suggested_name"] == "Right hand"


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
