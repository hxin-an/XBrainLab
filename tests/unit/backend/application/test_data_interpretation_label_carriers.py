from XBrainLab.backend.application.data_interpretation_label_carriers import (
    build_label_carrier_plan,
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
            "label_candidates": ["trial_type"],
            "anchor_candidates": ["onset"],
            "selected_label_field": "trial_type",
            "selected_anchor": "onset",
            "time_model": "seconds",
            "granularity": "trial",
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
            str(carrier): {"label_field": "label", "anchor": "sample"},
            carrier.name: {"role": "artifact markers"},
        }
    )

    assert choices[str(carrier)]["label_field"] == "label"
    assert choices[carrier.name]["role"] == "artifact markers"
