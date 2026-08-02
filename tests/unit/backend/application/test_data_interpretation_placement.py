from pathlib import Path

import pytest

from XBrainLab.backend.application.data_interpretation_label_carriers import (
    build_label_carrier_plan,
)
from XBrainLab.backend.application.data_interpretation_placement import (
    annotate_label_carrier_placements,
)


def _sample_plan(
    tmp_path: Path,
    *,
    sample_index_base: str | None = None,
    sample_index_origin: str | None = None,
) -> dict[str, object]:
    labels = tmp_path / "samples.csv"
    labels.write_text(
        "sample,label\n1,left\n101,right\n",
        encoding="utf-8",
    )
    carrier_choice: dict[str, object] = {
        "label_field": "label",
        "anchor": "sample",
        "time_model": "sample_index",
        "placement_method": "time_field",
        "granularity": "event",
    }
    if sample_index_base is not None:
        carrier_choice["sample_index_base"] = sample_index_base
    if sample_index_origin is not None:
        carrier_choice["sample_index_origin"] = sample_index_origin
    return build_label_carrier_plan(
        [str(labels)],
        {str(labels): carrier_choice},
    )[0]


def test_sample_index_placement_blocks_without_explicit_base_and_origin(
    tmp_path: Path,
) -> None:
    plan = _sample_plan(tmp_path)

    reviewed = annotate_label_carrier_placements([plan], {})[0]

    assert reviewed["sample_index_base"] == ""
    assert reviewed["sample_index_origin"] == ""
    assert reviewed["placement_review"]["status"] == "blocked"
    assert reviewed["placement_review"]["decision_code"] == (
        "sample_index_contract_required"
    )
    assert "zero- or one-based" in reviewed["placement_review"]["summary"]
    assert "recording-relative or absolute" in reviewed["placement_review"]["summary"]


def test_sample_index_placement_preserves_explicit_contract(tmp_path: Path) -> None:
    plan = _sample_plan(
        tmp_path,
        sample_index_base="one_based",
        sample_index_origin="recording_relative",
    )

    reviewed = annotate_label_carrier_placements([plan], {})[0]

    assert reviewed["sample_index_base"] == "one_based"
    assert reviewed["sample_index_origin"] == "recording_relative"
    assert reviewed["placement_review"]["status"] == "ready"
    assert reviewed["placement_review"]["sample_index_contract"] == {
        "base": "one_based",
        "origin": "recording_relative",
    }


def test_timestamp_placement_blocks_mne_excluded_class_description(
    tmp_path: Path,
) -> None:
    labels = tmp_path / "events.csv"
    labels.write_text("onset,label\n1.0,left\n", encoding="utf-8")
    plan = build_label_carrier_plan(
        [str(labels)],
        {
            str(labels): {
                "label_field": "label",
                "anchor": "onset",
                "time_model": "seconds",
                "placement_method": "time_field",
                "granularity": "event",
                "value_decisions": {
                    "left": {
                        "role": "stimulus",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": "BadTrial",
                    }
                },
            }
        },
    )[0]

    reviewed = annotate_label_carrier_placements([plan], {})[0]

    assert reviewed["placement_review"]["status"] == "blocked"
    assert reviewed["placement_review"]["decision_code"] == (
        "mne_excluded_class_description"
    )
    assert "BadTrial" in reviewed["placement_review"]["summary"]


def test_trial_order_placement_blocks_without_resolved_target_events(
    tmp_path: Path,
) -> None:
    carrier = {
        "path": str((tmp_path / "labels.mat").resolve()),
        "format": "MAT labels",
        "selected_label_field": "classlabel",
        "selected_anchor": "trial order",
        "selected_target_event_codes": [],
        "label_row_count": 10,
        "placement_method": "eeg_event",
        "time_model": "trial_order",
        "granularity": "trial",
    }
    internal_events = {
        "candidate_label_events": [
            {"event_code": "768", "event_count": 10},
            {"event_code": "769", "event_count": 5},
            {"event_code": "770", "event_count": 5},
        ]
    }

    review = annotate_label_carrier_placements([carrier], internal_events)[0][
        "placement_review"
    ]

    assert review["status"] == "blocked"
    assert review["decision_code"] == "sequence_target_events_required"
    assert review["target_events"] == []
    assert "explicit target EEG event" in review["summary"]


def test_shared_carrier_scopes_duplicate_basenames_by_full_target_path(
    tmp_path: Path,
) -> None:
    target_a = (tmp_path / "subject-a" / "session.gdf").resolve()
    target_b = (tmp_path / "subject-b" / "session.gdf").resolve()
    carrier = {
        "path": str((tmp_path / "shared.mat").resolve()),
        "selected_label_field": "classlabel",
        "selected_target_files": [str(target_a), str(target_b)],
        "selected_target_event_codes": ["769", "770", "771", "772"],
        "label_row_count": 288,
        "placement_method": "eeg_event",
    }
    internal_events = {
        "candidate_label_events": [
            {
                "event_code": code,
                "event_count": 144,
                "file_counts": {
                    str(target_a): 72,
                    str(target_b): 72,
                },
            }
            for code in ("769", "770", "771", "772")
        ]
    }

    reviewed = annotate_label_carrier_placements([carrier], internal_events)[0]

    assert reviewed["placement_review"]["status"] == "ready"
    assert reviewed["placement_review"]["selected_eeg_events"] == 288
    assert reviewed["placement_review"]["selected_eeg_events_by_target"] == {
        str(target_a): 288,
        str(target_b): 288,
    }


def test_committed_event_order_placement_uses_applied_scope_when_preview_was_skipped(
    tmp_path: Path,
) -> None:
    target_a = (tmp_path / "subject-a" / "session.gdf").resolve()
    target_b = (tmp_path / "subject-b" / "session.gdf").resolve()
    carrier = {
        "path": str((tmp_path / "shared.mat").resolve()),
        "selected_label_field": "classlabel",
        "selected_target_files": [str(target_a), str(target_b)],
        "selected_target_event_codes": ["769", "770", "771", "772"],
        "label_row_count": 288,
        "applied_event_counts_by_target": {
            str(target_a): 288,
            str(target_b): 288,
        },
        "placement_method": "eeg_event",
    }

    reviewed = annotate_label_carrier_placements([carrier], {})[0]

    assert reviewed["placement_review"]["status"] == "ready"
    assert reviewed["placement_review"]["selected_eeg_events"] == 288
    assert reviewed["placement_review"]["selected_eeg_events_by_target"] == {
        str(target_a): 288,
        str(target_b): 288,
    }


def test_committed_event_order_placement_keeps_applied_count_mismatch_blocked(
    tmp_path: Path,
) -> None:
    target = (tmp_path / "subject-a" / "session.gdf").resolve()
    carrier = {
        "path": str((tmp_path / "shared.mat").resolve()),
        "selected_label_field": "classlabel",
        "selected_target_files": [str(target)],
        "selected_target_event_codes": ["769", "770", "771", "772"],
        "label_row_count": 288,
        "applied_event_counts_by_target": {str(target): 287},
        "placement_method": "eeg_event",
    }

    reviewed = annotate_label_carrier_placements([carrier], {})[0]

    assert reviewed["placement_review"]["status"] == "blocked"
    assert reviewed["placement_review"]["selected_eeg_events"] == 287
    assert reviewed["placement_review"]["unmatched_label_rows"] == 1


@pytest.mark.parametrize(
    ("committed_case", "expected_decision_code"),
    (
        ("missing_target", "post_commit_event_scope_target_mismatch"),
        ("mismatched_target", "post_commit_event_scope_target_mismatch"),
        ("aggregate_only", "post_commit_event_scope_not_per_target"),
    ),
    ids=("MISSING_TARGET", "MISMATCH_TARGET", "AGGREGATE_ONLY"),
)
def test_invalid_committed_event_scope_cannot_fall_back_to_ready_preview(
    tmp_path: Path,
    committed_case: str,
    expected_decision_code: str,
) -> None:
    target_a = (tmp_path / "subject-a" / "session.gdf").resolve()
    target_b = (tmp_path / "subject-b" / "session.gdf").resolve()
    mismatched_target = (tmp_path / "other" / "session.gdf").resolve()
    if committed_case == "missing_target":
        committed_counts: object = {str(target_a): 288}
    elif committed_case == "mismatched_target":
        committed_counts = {
            str(target_a): 288,
            str(mismatched_target): 288,
        }
    else:
        committed_counts = {}
    carrier = {
        "path": str((tmp_path / "shared.mat").resolve()),
        "selected_label_field": "classlabel",
        "selected_target_files": [str(target_a), str(target_b)],
        "selected_target_event_codes": ["769", "770", "771", "772"],
        "label_row_count": 288,
        "applied_event_counts_by_target": committed_counts,
        "placement_method": "eeg_event",
    }
    if committed_case == "aggregate_only":
        carrier["applied_event_count"] = 576
    preview = {
        "candidate_label_events": [
            {
                "event_code": code,
                "event_count": 144,
                "file_counts": {
                    str(target_a): 72,
                    str(target_b): 72,
                },
            }
            for code in ("769", "770", "771", "772")
        ]
    }

    reviewed = annotate_label_carrier_placements([carrier], preview)[0]

    assert reviewed["placement_review"]["status"] == "blocked"
    assert reviewed["placement_review"]["decision_code"] == expected_decision_code
    assert "committed" in reviewed["placement_review"]["summary"].lower()


def test_committed_zero_label_and_event_scope_is_blocked(tmp_path: Path) -> None:
    target_a = (tmp_path / "subject-a" / "session.gdf").resolve()
    target_b = (tmp_path / "subject-b" / "session.gdf").resolve()
    carrier = {
        "path": str((tmp_path / "shared.mat").resolve()),
        "selected_target_files": [str(target_a), str(target_b)],
        "selected_target_event_codes": ["769"],
        "label_row_count": 0,
        "applied_event_counts_by_target": {
            str(target_a): 0,
            str(target_b): 0,
        },
        "placement_method": "eeg_event",
    }

    review = annotate_label_carrier_placements([carrier], {})[0]["placement_review"]

    assert review["status"] == "blocked"
    assert review["decision_code"] == "post_commit_event_scope_empty"
    assert "at least one applied EEG event" in review["summary"]


def test_pre_import_zero_count_preview_keeps_empty_preview_semantics(
    tmp_path: Path,
) -> None:
    carrier = {
        "path": str((tmp_path / "shared.mat").resolve()),
        "selected_target_event_codes": ["769"],
        "label_row_count": 0,
        "placement_method": "eeg_event",
    }
    preview = {
        "candidate_label_events": [
            {
                "event_code": "769",
                "event_count": 0,
            }
        ]
    }

    review = annotate_label_carrier_placements([carrier], preview)[0][
        "placement_review"
    ]

    assert review["status"] == "ready"
    assert review["matched"] == 0
    assert "0 label rows match 0 selected EEG events" in review["summary"]


def test_committed_zero_label_count_with_positive_event_scope_is_blocked(
    tmp_path: Path,
) -> None:
    target = (tmp_path / "subject-a" / "session.gdf").resolve()
    carrier = {
        "path": str((tmp_path / "shared.mat").resolve()),
        "selected_target_files": [str(target)],
        "selected_target_event_codes": ["769"],
        "label_row_count": 0,
        "applied_event_counts_by_target": {str(target): 1},
        "placement_method": "eeg_event",
    }

    review = annotate_label_carrier_placements([carrier], {})[0]["placement_review"]

    assert review["status"] == "blocked"
    assert review["decision_code"] == "post_commit_label_scope_empty"
    assert "at least one label row" in review["summary"]


def test_committed_mixed_multi_target_zero_event_scope_is_blocked(
    tmp_path: Path,
) -> None:
    target_a = (tmp_path / "subject-a" / "session.gdf").resolve()
    target_b = (tmp_path / "subject-b" / "session.gdf").resolve()
    carrier = {
        "path": str((tmp_path / "shared.mat").resolve()),
        "selected_target_files": [str(target_a), str(target_b)],
        "selected_target_event_codes": ["769"],
        "label_row_count": 288,
        "applied_event_counts_by_target": {
            str(target_a): 288,
            str(target_b): 0,
        },
        "placement_method": "eeg_event",
    }

    review = annotate_label_carrier_placements([carrier], {})[0]["placement_review"]

    assert review["status"] == "blocked"
    assert review["decision_code"] == "post_commit_event_scope_empty"
    assert "at least one applied EEG event" in review["summary"]


@pytest.mark.parametrize(
    "label_row_count",
    (-1, True, "288", None),
    ids=("NEGATIVE", "BOOLEAN", "NUMERIC_STRING", "MISSING"),
)
def test_committed_invalid_label_count_is_blocked(
    tmp_path: Path,
    label_row_count: object,
) -> None:
    target = (tmp_path / "subject-a" / "session.gdf").resolve()
    carrier = {
        "path": str((tmp_path / "shared.mat").resolve()),
        "selected_target_files": [str(target)],
        "selected_target_event_codes": ["769"],
        "label_row_count": label_row_count,
        "applied_event_counts_by_target": {str(target): 288},
        "placement_method": "eeg_event",
    }

    review = annotate_label_carrier_placements([carrier], {})[0]["placement_review"]

    assert review["status"] == "blocked"
    assert review["decision_code"] == "post_commit_label_count_invalid"
    assert "positive integer" in review["summary"]


@pytest.mark.parametrize(
    "event_count",
    (-1, True, "288", None),
    ids=("NEGATIVE", "BOOLEAN", "NUMERIC_STRING", "MISSING"),
)
def test_committed_invalid_target_event_count_is_blocked(
    tmp_path: Path,
    event_count: object,
) -> None:
    target = (tmp_path / "subject-a" / "session.gdf").resolve()
    carrier = {
        "path": str((tmp_path / "shared.mat").resolve()),
        "selected_target_files": [str(target)],
        "selected_target_event_codes": ["769"],
        "label_row_count": 288,
        "applied_event_counts_by_target": {str(target): event_count},
        "placement_method": "eeg_event",
    }

    review = annotate_label_carrier_placements([carrier], {})[0]["placement_review"]

    assert review["status"] == "blocked"
    assert review["decision_code"] == "post_commit_event_scope_invalid"
    assert "positive integer" in review["summary"]
