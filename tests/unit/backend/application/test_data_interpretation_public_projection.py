"""Bounded public projections for Data Interpretation review payloads."""

from __future__ import annotations

from XBrainLab.backend.application.data_interpretation_public_projection import (
    PUBLIC_EVIDENCE_PREVIEW_LIMIT,
    project_bids_review,
    project_label_carrier_plan,
)


def _rows(count: int) -> list[dict[str, object]]:
    return [{"row": index, "value": f"value-{index}"} for index in range(count)]


def test_label_carrier_projection_bounds_row_level_evidence() -> None:
    count = PUBLIC_EVIDENCE_PREVIEW_LIMIT + 20
    [projected] = project_label_carrier_plan(
        [
            {
                "path": "/data/events.tsv",
                "selected_label_field": "value",
                "selected_anchor_stats": {
                    "row_count": count,
                    "numeric_count": count,
                    "min": 0.0,
                    "max": float(count - 1),
                    "value_counts": {str(index): 1 for index in range(count)},
                },
                "event_code_label_counts": {
                    str(index): {"class": 1} for index in range(count)
                },
                "placement_reviews": {
                    "event_code": {
                        "method": "event_code",
                        "missing_codes": [str(index) for index in range(count)],
                        "code_mappings": _rows(count),
                    }
                },
                "bids_event_review": {
                    "row_evidence": _rows(count),
                    "placement": {
                        "unknown_duration_rows": _rows(count),
                        "excluded_rows": _rows(count),
                    },
                },
            }
        ]
    )

    assert "value_counts" not in projected["selected_anchor_stats"]
    assert "event_code_label_counts" not in projected
    assert "row_evidence" not in projected["bids_event_review"]
    assert projected["bids_event_review"]["row_evidence_count"] == count
    placement = projected["bids_event_review"]["placement"]
    assert "unknown_duration_rows" not in placement
    assert placement["unknown_duration_row_count"] == count
    assert "excluded_rows" not in placement
    assert placement["excluded_row_count"] == count
    event_code = projected["placement_reviews"]["event_code"]
    assert event_code["missing_code_count"] == count
    assert len(event_code["missing_codes"]) == PUBLIC_EVIDENCE_PREVIEW_LIMIT
    assert event_code["code_mapping_count"] == count
    assert len(event_code["code_mappings"]) == PUBLIC_EVIDENCE_PREVIEW_LIMIT


def test_bids_projection_keeps_aggregate_counts_without_full_rows() -> None:
    count = PUBLIC_EVIDENCE_PREVIEW_LIMIT + 5
    projected = project_bids_review(
        {
            "is_bids": True,
            "event_validation": {
                "runs": [
                    {
                        "file": "/data/sub-01_eeg.set",
                        "row_evidence": _rows(count),
                        "placement": {
                            "usable_event_count": count,
                            "unknown_duration_rows": _rows(count),
                            "excluded_rows": _rows(2),
                        },
                    }
                ]
            },
        }
    )

    [run] = projected["event_validation"]["runs"]
    assert run["file"] == "/data/sub-01_eeg.set"
    assert "row_evidence" not in run
    assert run["row_evidence_count"] == count
    assert run["placement"]["usable_event_count"] == count
    assert run["placement"]["unknown_duration_row_count"] == count
    assert run["placement"]["excluded_row_count"] == 2
