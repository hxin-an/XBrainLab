"""Label-carrier planning for Data Interpretation sources."""

from __future__ import annotations

import contextlib
import csv
import io
import math
import re
from collections import Counter
from collections.abc import Iterable
from itertools import islice
from numbers import Real
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

from .data_interpretation_bids_resources import (
    BidsEventsJsonReader,
    bids_events_json_candidates,
    bids_events_json_resource_paths,
)
from .data_interpretation_event_values import (
    class_map_from_value_decisions,
    derive_class_views,
    review_event_values,
)
from .data_interpretation_parsed_cache import (
    ParsedContentTooLargeError,
    parsed_delimited_table,
)
from .data_interpretation_public_projection import (
    PUBLIC_BIDS_RECOMMENDATION_RUN_SAMPLE_LIMIT,
)
from .data_interpretation_resource_reader import AdmittedResourceReader

NEEDS_CONFIRMATION = "needs_confirmation"
BIDS_LABEL_RECOMMENDATION_ROW_LIMIT_PER_RUN = 2048
BIDS_LABEL_RECOMMENDATION_TOTAL_ROW_LIMIT = 8192
BIDS_LABEL_RECOMMENDATION_BYTE_LIMIT_PER_RUN = 1024 * 1024
BIDS_LABEL_RECOMMENDATION_TOTAL_BYTE_LIMIT = 4 * 1024 * 1024
BIDS_LABEL_RECOMMENDATION_MIN_REFINEMENT_ROW_COVERAGE = 1.0

_GENERIC_BIDS_EVENT_ROLES = {
    "event",
    "events",
    "feedback",
    "fixation",
    "instruction",
    "instructions",
    "response",
    "responses",
    "stimuli",
    "stimulus",
}
_IDENTIFIER_DESCRIPTION_PATTERN = re.compile(
    r"^(?:(?:stimulus|event|marker|trigger|condition|hardware)\s+)?"
    r"(?:identifier|id|code)(?:\s+\d+)?$",
    re.IGNORECASE,
)


def build_label_carrier_plan(
    label_carriers: list[str],
    choices_payload: Any,
    *,
    carrier_sources: dict[str, str] | None = None,
    sidecar_reader: BidsEventsJsonReader | None = None,
    resource_reader: AdmittedResourceReader | None = None,
    recommend_bids_label_field: bool = False,
) -> list[dict[str, Any]]:
    """Build reviewable label-carrier rows for interpretation preview."""
    choices = normalize_label_carrier_choices(choices_payload)
    carrier_sources = dict(carrier_sources or {})
    label_field_recommendation: dict[str, Any] = {}
    recommendation_carriers = [
        carrier
        for carrier in label_carriers
        if _is_bids_events_file(Path(carrier))
        and not str(
            _choice_for_label_carrier(
                Path(carrier),
                choices,
                str(carrier),
            ).get("label_field")
            or ""
        ).strip()
    ]
    if recommend_bids_label_field and recommendation_carriers:
        recommendation_guard = (
            resource_reader.guard(
                recommendation_carriers,
                purpose="BIDS label-field recommendation preview",
            )
            if resource_reader is not None
            else contextlib.nullcontext()
        )
        with recommendation_guard:
            label_field_recommendation = _bids_label_field_recommendation(
                recommendation_carriers,
                choices,
                sidecar_reader=sidecar_reader,
            )
    carrier_recommendation = _label_field_recommendation_summary(
        label_field_recommendation
    )
    rows: list[dict[str, Any]] = []
    for carrier in label_carriers:
        path = Path(carrier)
        guard = (
            resource_reader.guard([path], purpose="label carrier preview")
            if resource_reader is not None
            else contextlib.nullcontext()
        )
        with guard:
            rows.append(
                _label_carrier_plan_for_path(
                    path,
                    choices,
                    raw_path=str(carrier),
                    source_location=carrier_sources.get(str(carrier), ""),
                    sidecar_reader=sidecar_reader,
                    label_field_recommendation=carrier_recommendation,
                )
            )
    details = _label_field_recommendation_details(label_field_recommendation)
    if details:
        for row in rows:
            recommendation = row.get("label_field_recommendation")
            if (
                isinstance(recommendation, dict)
                and recommendation.get("source") == "bids_multi_run_evidence"
            ):
                row["label_field_recommendation_details"] = details
                break
    return rows


def infer_class_map_from_label_carrier_plan(
    label_carrier_plan: list[dict[str, Any]],
    *,
    limit: int = 20,
    sidecar_reader: BidsEventsJsonReader | None = None,
    resource_reader: AdmittedResourceReader | None = None,
) -> dict[str, str]:
    """Return the collision-safe class view selected by value decisions."""
    del sidecar_reader, resource_reader
    class_map, _run_maps = derive_class_views(label_carrier_plan)
    return dict(list(class_map.items())[: max(int(limit), 0)])


def observed_class_map_for_label_carrier(
    carrier: dict[str, Any],
    *,
    sidecar_reader: BidsEventsJsonReader | None = None,
) -> dict[str, str]:
    """Return the selected class view for one carrier."""
    del sidecar_reader
    decisions = carrier.get("value_decisions")
    return class_map_from_value_decisions(
        decisions if isinstance(decisions, dict) else {}
    )


def normalize_label_carrier_choices(payload: Any) -> dict[str, dict[str, Any]]:
    """Return cleaned wizard choices keyed by carrier path or file name."""
    if not isinstance(payload, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    allowed = {
        "label_field",
        "anchor",
        "time_model",
        "sample_index_base",
        "sample_index_origin",
        "granularity",
        "role",
        "target_file",
        "target_files",
        "placement_method",
        "duration_field",
        "target_event_codes",
        "value_decisions",
    }
    for carrier_key, carrier_choices in payload.items():
        if not isinstance(carrier_choices, dict):
            continue
        cleaned: dict[str, Any] = {}
        for key, value in carrier_choices.items():
            key_text = str(key)
            if key_text not in allowed:
                continue
            if key_text in {"target_event_codes", "target_files"}:
                values = _string_list(value)
                if values:
                    cleaned[key_text] = values
                continue
            if key_text == "value_decisions":
                decisions = _normalize_value_decision_choices(value)
                if decisions:
                    cleaned[key_text] = decisions
                continue
            value_text = str(value).strip()
            if value_text:
                cleaned[key_text] = value_text
        if cleaned:
            result[str(carrier_key)] = cleaned
    return result


def _label_carrier_plan_for_path(
    path: Path,
    choices: dict[str, dict[str, Any]],
    *,
    raw_path: str | None = None,
    source_location: str = "",
    sidecar_reader: BidsEventsJsonReader | None = None,
    label_field_recommendation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_path = raw_path or str(path)
    carrier_choice = _choice_for_label_carrier(path, choices, source_path)
    label_candidates = _label_candidates_for_carrier(path)
    anchor_candidates = _anchor_candidates_for_carrier(path, label_candidates)
    time_field_candidates = _time_field_candidates_for_carrier(path, label_candidates)
    interval_start_candidates = list(time_field_candidates)
    event_code_candidates = _event_code_candidates_for_carrier(
        path,
        label_candidates,
    )
    duration_candidates = _duration_candidates_for_carrier(path)
    recommendation = dict(label_field_recommendation or {})
    explicit_label = str(carrier_choice.get("label_field") or "").strip()
    if explicit_label:
        recommendation = _explicit_label_field_recommendation(explicit_label)
    recommended_label = str(recommendation.get("field") or "").strip()
    selected_label = carrier_choice.get("label_field") or (
        recommended_label
        if recommended_label in label_candidates
        else label_candidates[0]
        if label_candidates
        else ""
    )
    time_model = carrier_choice.get("time_model") or _default_time_model(
        path, anchor_candidates
    )
    sample_index_base = str(carrier_choice.get("sample_index_base") or "").strip()
    sample_index_origin = str(carrier_choice.get("sample_index_origin") or "").strip()
    granularity = carrier_choice.get("granularity") or _default_granularity(path)
    selected_duration = carrier_choice.get("duration_field") or _default_duration_field(
        duration_candidates
    )
    placement_method = carrier_choice.get(
        "placement_method"
    ) or _default_placement_method(
        time_model=time_model,
        granularity=granularity,
        duration_field=selected_duration,
        time_field_candidates=time_field_candidates,
        event_code_candidates=event_code_candidates,
    )
    selected_anchor = carrier_choice.get("anchor") or _default_anchor_for_placement(
        placement_method=placement_method,
        anchor_candidates=anchor_candidates,
        time_field_candidates=time_field_candidates,
        interval_start_candidates=interval_start_candidates,
        event_code_candidates=event_code_candidates,
    )
    selected_target_event_codes = _target_event_codes_for_choice(
        carrier_choice,
        selected_anchor,
        placement_method,
    )
    if selected_target_event_codes and selected_anchor in {"", "trial order"}:
        selected_anchor = selected_target_event_codes[0]
    label_stats = _observed_label_stats(path, selected_label)
    level_suggestions = (
        _bids_event_level_labels(
            path,
            selected_label,
            sidecar_reader=sidecar_reader,
        )
        if _is_bids_events_file(path)
        else {}
    )
    selected_label_field_levels_available = bool(level_suggestions)
    value_review = review_event_values(
        value_counts=label_stats["value_counts"],
        selected_field=selected_label,
        carrier_format=_label_carrier_format(path),
        carrier_role=str(carrier_choice.get("role") or "external labels"),
        suggested_names=level_suggestions,
        choices=carrier_choice.get("value_decisions")
        if isinstance(carrier_choice.get("value_decisions"), dict)
        else {},
    )
    run_class_map = class_map_from_value_decisions(value_review.decisions)
    anchor_stats = _observed_field_stats(path, selected_anchor)
    duration_stats = _observed_field_stats(path, selected_duration)
    event_code_label_counts = _event_code_label_counts(
        path,
        selected_anchor,
        selected_label,
    )
    time_label_preview = _time_label_preview(
        path,
        selected_anchor,
        selected_label,
        limit=3,
    )
    bids_event_columns = _bids_event_columns(path)
    events_json_sidecar_present = bool(
        _existing_bids_events_json_candidates(path, sidecar_reader=sidecar_reader)
    )
    warnings = _label_carrier_warnings(
        path,
        bids_event_columns=bids_event_columns,
        time_field_candidates=time_field_candidates,
        duration_candidates=duration_candidates,
        sidecar_reader=sidecar_reader,
        events_json_sidecar_present=events_json_sidecar_present,
        selected_label_field=selected_label,
        selected_label_field_levels_available=(selected_label_field_levels_available),
    )
    warnings.extend(value_review.warnings)
    plan = {
        "path": source_path,
        "name": path.name,
        "format": _label_carrier_format(path),
        "source_kind": "auto_discovered"
        if source_location in {"", "auto"}
        else "user_added",
        "source_location": "" if source_location == "auto" else source_location,
        "label_candidates": label_candidates,
        "anchor_candidates": anchor_candidates,
        "time_field_candidates": time_field_candidates,
        "interval_start_candidates": interval_start_candidates,
        "event_code_candidates": event_code_candidates,
        "duration_candidates": duration_candidates,
        "selected_label_field": selected_label,
        "selected_anchor": selected_anchor,
        "selected_target_event_codes": selected_target_event_codes,
        "selected_duration_field": selected_duration,
        "label_row_count": label_stats["row_count"],
        "label_value_counts": label_stats["value_counts"],
        "value_decisions": value_review.decisions,
        "unresolved_values": value_review.unresolved_values,
        "missing_value_decisions": value_review.missing_values,
        "selected_anchor_stats": anchor_stats,
        "selected_duration_stats": duration_stats,
        "event_code_label_counts": event_code_label_counts,
        "time_label_preview": time_label_preview,
        "bids_event_columns": bids_event_columns,
        "events_json_sidecar_present": events_json_sidecar_present,
        "selected_label_field_levels_available": (
            selected_label_field_levels_available
        ),
        "warnings": warnings,
        "time_model": time_model,
        "sample_index_base": sample_index_base,
        "sample_index_origin": sample_index_origin,
        "granularity": granularity,
        "placement_method": placement_method,
        "role": carrier_choice.get("role") or "external labels",
        "selected_target_file": carrier_choice.get("target_file", ""),
        "selected_target_files": carrier_choice.get("target_files", []),
        "decision": NEEDS_CONFIRMATION,
        "reason": _label_carrier_reason(path, label_candidates, anchor_candidates),
    }
    if recommendation and _is_bids_events_file(path):
        plan["label_field_recommendation"] = recommendation
    if run_class_map:
        plan["run_class_map"] = run_class_map
    return plan


def _choice_for_label_carrier(
    path: Path,
    choices: dict[str, dict[str, Any]],
    raw_path: str,
) -> dict[str, Any]:
    return choices.get(
        raw_path,
        choices.get(
            path.as_posix(), choices.get(str(path), choices.get(path.name, {}))
        ),
    )


def _bids_label_field_recommendation(
    label_carriers: list[str],
    choices: dict[str, dict[str, Any]],
    *,
    sidecar_reader: BidsEventsJsonReader | None,
) -> dict[str, Any]:
    paths = [Path(carrier) for carrier in label_carriers]
    paths = [path for path in paths if _is_bids_events_file(path)]
    if not paths:
        return {}

    automatic_paths = [
        path
        for path in paths
        if not str(
            _choice_for_label_carrier(path, choices, str(path)).get("label_field") or ""
        ).strip()
    ]
    if not automatic_paths:
        return {}

    reader = sidecar_reader or BidsEventsJsonReader.from_paths(
        bids_events_json_resource_paths(str(path) for path in automatic_paths),
    )
    row_limit = min(
        BIDS_LABEL_RECOMMENDATION_ROW_LIMIT_PER_RUN,
        BIDS_LABEL_RECOMMENDATION_TOTAL_ROW_LIMIT // len(automatic_paths),
    )
    byte_limit = min(
        BIDS_LABEL_RECOMMENDATION_BYTE_LIMIT_PER_RUN,
        BIDS_LABEL_RECOMMENDATION_TOTAL_BYTE_LIMIT // len(automatic_paths),
    )
    profiles = [
        _bids_label_field_profile(
            path,
            sidecar_reader=reader,
            row_limit=row_limit,
            byte_limit=byte_limit,
        )
        for path in automatic_paths
    ]
    evidence = _aggregate_bids_label_field_evidence(profiles)
    if evidence["row_truncated_run_count"] or evidence["byte_truncated_run_count"]:
        return {}
    trial_column_coverage = evidence["field_column_run_coverage"]["trial_type"]
    value_column_coverage = evidence["field_column_run_coverage"]["value"]
    trial_row_coverage = evidence["nonempty_row_coverage"]["trial_type"]
    value_row_coverage = evidence["nonempty_row_coverage"]["value"]
    value_is_strong_refinement = bool(
        evidence["value_refines_trial_type"]
        and evidence["nonempty_run_coverage"]["value"] == 1.0
        and value_row_coverage >= BIDS_LABEL_RECOMMENDATION_MIN_REFINEMENT_ROW_COVERAGE
        and value_row_coverage >= trial_row_coverage
        and evidence["multi_value_run_coverage"]["value"] == 1.0
        and evidence["generic_trial_role_run_coverage"] == 1.0
        and evidence["meaningful_value_refinement_run_coverage"] == 1.0
        and evidence["sidecar_level_run_coverage"]["trial_type"] == 1.0
        and evidence["sidecar_level_run_coverage"]["value"] == 1.0
        and evidence["sidecar_level_cross_run_consistency"]["value"] == 1.0
        and evidence["sidecar_observed_value_run_coverage"]["value"] == 1.0
    )
    if value_is_strong_refinement:
        return {
            "field": "value",
            "source": "bids_multi_run_evidence",
            "reason_code": "value_has_described_classes",
            "facts": _label_field_recommendation_facts(evidence),
            "evidence": evidence,
        }

    if (
        trial_column_coverage > 0
        and value_column_coverage > 0
        and trial_row_coverage >= BIDS_LABEL_RECOMMENDATION_MIN_REFINEMENT_ROW_COVERAGE
        and value_row_coverage < trial_row_coverage
    ):
        return {
            "field": "trial_type",
            "source": "bids_multi_run_evidence",
            "reason_code": "trial_type_has_more_complete_rows",
            "facts": _label_field_recommendation_facts(evidence),
            "evidence": evidence,
        }

    if (
        trial_column_coverage > 0
        and evidence["nonempty_run_coverage"]["trial_type"] == 1.0
        and evidence["generic_trial_role_run_coverage"] < 1.0
    ):
        if evidence["numeric_only"]["value"] and value_column_coverage > 0:
            reason_code = "trial_type_over_numeric_value"
        elif evidence["generic_trial_role_run_coverage"] < 1.0:
            reason_code = "trial_type_has_task_labels"
        else:
            reason_code = "trial_type_is_consistent"
        return {
            "field": "trial_type",
            "source": "bids_multi_run_evidence",
            "reason_code": reason_code,
            "facts": _label_field_recommendation_facts(evidence),
            "evidence": evidence,
        }

    if (
        value_column_coverage > 0
        and evidence["nonempty_run_coverage"]["value"] == 1.0
        and (
            trial_column_coverage == 0
            or evidence["nonempty_run_coverage"]["trial_type"] < 1.0
        )
    ):
        return {
            "field": "value",
            "source": "bids_multi_run_evidence",
            "reason_code": "value_is_only_supported_field",
            "facts": _label_field_recommendation_facts(evidence),
            "evidence": evidence,
        }
    return {}


def _explicit_label_field_recommendation(field: str) -> dict[str, Any]:
    return {
        "field": str(field).strip(),
        "source": "explicit_selection",
        "reason_code": "explicit_selection",
        "facts": {},
    }


def _label_field_recommendation_summary(
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    if not recommendation:
        return {}
    source = str(recommendation.get("source") or "").strip()
    reason_code = str(recommendation.get("reason_code") or "").strip()
    if not reason_code:
        reason_code = (
            "explicit_selection"
            if source == "explicit_selection"
            else "bids_label_field_recommendation"
        )
    facts = recommendation.get("facts")
    return {
        "field": str(recommendation.get("field") or "").strip(),
        "source": source,
        "reason_code": reason_code,
        "facts": dict(facts) if isinstance(facts, dict) else {},
    }


def _label_field_recommendation_details(
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    evidence = recommendation.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        return {}
    summary = _label_field_recommendation_summary(recommendation)
    return {
        "reason_code": summary["reason_code"],
        "facts": summary["facts"],
        "evidence": dict(evidence),
    }


def _label_field_recommendation_facts(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    coverage = evidence.get("nonempty_row_coverage")
    row_coverage = coverage if isinstance(coverage, dict) else {}
    return {
        "selected_run_count": int(evidence.get("selected_run_count") or 0),
        "total_sampled_row_count": int(evidence.get("total_sampled_row_count") or 0),
        "row_sample_limit_per_run": int(evidence.get("row_sample_limit_per_run") or 0),
        "total_row_sample_limit": int(evidence.get("total_row_sample_limit") or 0),
        "nonempty_row_coverage": {
            "trial_type": float(row_coverage.get("trial_type") or 0.0),
            "value": float(row_coverage.get("value") or 0.0),
        },
        "minimum_refinement_row_coverage": (
            BIDS_LABEL_RECOMMENDATION_MIN_REFINEMENT_ROW_COVERAGE
        ),
    }


def _bids_label_field_profile(
    path: Path,
    *,
    sidecar_reader: BidsEventsJsonReader,
    row_limit: int = BIDS_LABEL_RECOMMENDATION_ROW_LIMIT_PER_RUN,
    byte_limit: int = BIDS_LABEL_RECOMMENDATION_BYTE_LIMIT_PER_RUN,
) -> dict[str, Any]:
    counts = {"trial_type": Counter(), "value": Counter()}
    pairings: dict[str, set[str]] = {}
    sampled_row_count = 0
    sampled_byte_count = 0
    byte_truncated = False
    row_truncated = False
    try:
        file_bytes = max(int(path.stat().st_size), 0)
        if file_bytes <= max(int(byte_limit), 0):
            table = parsed_delimited_table(path, delimiter="\t")
            sampled_byte_count = table.file_bytes
            columns = {str(column).strip() for column in table.fieldnames}
            rows = table.dict_rows()
            sampled_rows = rows[: max(int(row_limit), 0)]
            byte_truncated = False
            row_truncated = len(rows) > len(sampled_rows)
        else:
            text, sampled_byte_count, byte_truncated = _bounded_tsv_text(
                path,
                byte_limit=max(int(byte_limit), 0),
            )
            with io.StringIO(text, newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                columns = {str(column).strip() for column in reader.fieldnames or []}
                sampled_rows = list(islice(reader, max(int(row_limit), 0)))
                row_truncated = next(reader, None) is not None
        for row in sampled_rows:
            sampled_row_count += 1
            trial_type = _clean_label_value(row.get("trial_type"))
            value = _clean_label_value(row.get("value"))
            if trial_type:
                counts["trial_type"][trial_type] += 1
            if value:
                counts["value"][value] += 1
            if trial_type and value:
                pairings.setdefault(trial_type, set()).add(value)
    except ParsedContentTooLargeError:
        try:
            text, sampled_byte_count, byte_truncated = _bounded_tsv_text(
                path,
                byte_limit=max(int(byte_limit), 0),
            )
            with io.StringIO(text, newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                columns = {str(column).strip() for column in reader.fieldnames or []}
                sampled_rows = list(islice(reader, max(int(row_limit), 0)))
                row_truncated = next(reader, None) is not None
            for row in sampled_rows:
                sampled_row_count += 1
                trial_type = _clean_label_value(row.get("trial_type"))
                value = _clean_label_value(row.get("value"))
                if trial_type:
                    counts["trial_type"][trial_type] += 1
                if value:
                    counts["value"][value] += 1
                if trial_type and value:
                    pairings.setdefault(trial_type, set()).add(value)
        except (OSError, UnicodeDecodeError, csv.Error):
            columns = set()
    except (OSError, UnicodeDecodeError, csv.Error):
        columns = set()
    return {
        "columns": columns,
        "sampled_row_count": sampled_row_count,
        "row_sample_limit": max(int(row_limit), 0),
        "sampled_byte_count": sampled_byte_count,
        "byte_sample_limit": max(int(byte_limit), 0),
        "byte_truncated": byte_truncated,
        "row_truncated": row_truncated,
        "counts": counts,
        "pairings": pairings,
        "levels": {
            field: _bids_event_level_labels(
                path,
                field,
                sidecar_reader=sidecar_reader,
            )
            for field in ("trial_type", "value")
        },
    }


def _aggregate_bids_label_field_evidence(
    profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    fields = ("trial_type", "value")
    run_count = len(profiles)
    nonempty_run_coverage: dict[str, float] = {}
    nonempty_row_coverage: dict[str, float] = {}
    categorical_run_coverage: dict[str, float] = {}
    multi_value_run_coverage: dict[str, float] = {}
    cross_run_consistency: dict[str, float] = {}
    sidecar_level_run_coverage: dict[str, float] = {}
    numeric_only: dict[str, bool] = {}
    field_column_run_coverage: dict[str, float] = {}
    sidecar_level_cross_run_consistency: dict[str, float] = {}
    sidecar_observed_value_run_coverage: dict[str, float] = {}

    for field in fields:
        field_counts = [profile["counts"][field] for profile in profiles]
        populated = [counts for counts in field_counts if counts]
        field_column_run_coverage[field] = _ratio(
            sum(field in profile["columns"] for profile in profiles),
            run_count,
        )
        nonempty_run_coverage[field] = _ratio(len(populated), run_count)
        sampled_rows = sum(int(profile["sampled_row_count"]) for profile in profiles)
        nonempty_rows = sum(sum(counts.values()) for counts in field_counts)
        nonempty_row_coverage[field] = _ratio(nonempty_rows, sampled_rows)
        categorical_run_coverage[field] = _ratio(
            sum(_is_repeated_categorical(counts) for counts in field_counts),
            run_count,
        )
        multi_value_run_coverage[field] = _ratio(
            sum(len(counts) >= 2 for counts in field_counts),
            run_count,
        )
        cross_run_consistency[field] = _cross_run_category_consistency(populated)
        sidecar_level_run_coverage[field] = _ratio(
            sum(bool(profile["levels"][field]) for profile in profiles),
            run_count,
        )
        sidecar_level_cross_run_consistency[field] = _cross_run_set_consistency(
            [
                set(profile["levels"][field])
                for profile in profiles
                if profile["levels"][field]
            ]
        )
        sidecar_observed_value_run_coverage[field] = _ratio(
            sum(_sidecar_levels_cover_observed(profile, field) for profile in profiles),
            run_count,
        )
        observed_values = [value for counts in populated for value in counts]
        numeric_only[field] = bool(observed_values) and all(
            _numeric_value(value) is not None for value in observed_values
        )

    generic_trial_role_run_coverage = _ratio(
        sum(
            _is_generic_event_role_taxonomy(profile["levels"]["trial_type"])
            for profile in profiles
        ),
        run_count,
    )
    meaningful_value_refinement_run_coverage = _ratio(
        sum(
            _has_meaningful_value_refinement(
                profile["levels"]["trial_type"],
                profile["levels"]["value"],
            )
            for profile in profiles
        ),
        run_count,
    )
    value_refines_trial_type = bool(
        generic_trial_role_run_coverage == 1.0
        and meaningful_value_refinement_run_coverage == 1.0
    )
    sampled_row_counts = [int(profile["sampled_row_count"]) for profile in profiles]
    sampled_byte_counts = [int(profile["sampled_byte_count"]) for profile in profiles]
    sampled_row_count_sample = sampled_row_counts[
        :PUBLIC_BIDS_RECOMMENDATION_RUN_SAMPLE_LIMIT
    ]
    return {
        "selected_run_count": run_count,
        "row_sample_limit_per_run": max(
            (int(profile["row_sample_limit"]) for profile in profiles),
            default=0,
        ),
        "total_row_sample_limit": BIDS_LABEL_RECOMMENDATION_TOTAL_ROW_LIMIT,
        "byte_sample_limit_per_run": max(
            (int(profile["byte_sample_limit"]) for profile in profiles),
            default=0,
        ),
        "total_byte_sample_limit": BIDS_LABEL_RECOMMENDATION_TOTAL_BYTE_LIMIT,
        "total_sampled_byte_count": sum(sampled_byte_counts),
        "byte_truncated_run_count": sum(
            bool(profile["byte_truncated"]) for profile in profiles
        ),
        "row_truncated_run_count": sum(
            bool(profile["row_truncated"]) for profile in profiles
        ),
        "sampled_row_counts": sampled_row_count_sample,
        "sampled_row_counts_sample_limit": (
            PUBLIC_BIDS_RECOMMENDATION_RUN_SAMPLE_LIMIT
        ),
        "sampled_row_counts_total": len(sampled_row_counts),
        "sampled_row_counts_truncated": (
            len(sampled_row_counts) - len(sampled_row_count_sample)
        ),
        "total_sampled_row_count": sum(sampled_row_counts),
        "nonempty_run_coverage": nonempty_run_coverage,
        "nonempty_row_coverage": nonempty_row_coverage,
        "field_column_run_coverage": field_column_run_coverage,
        "categorical_run_coverage": categorical_run_coverage,
        "multi_value_run_coverage": multi_value_run_coverage,
        "cross_run_consistency": cross_run_consistency,
        "sidecar_level_run_coverage": sidecar_level_run_coverage,
        "sidecar_level_cross_run_consistency": (sidecar_level_cross_run_consistency),
        "sidecar_observed_value_run_coverage": (sidecar_observed_value_run_coverage),
        "numeric_only": numeric_only,
        "generic_trial_role_run_coverage": generic_trial_role_run_coverage,
        "meaningful_value_refinement_run_coverage": (
            meaningful_value_refinement_run_coverage
        ),
        "value_refines_trial_type": value_refines_trial_type,
    }


def _is_generic_event_role_taxonomy(levels: dict[str, str]) -> bool:
    if not levels:
        return False
    normalized = {
        re.sub(r"[\s_-]+", " ", str(value).strip().casefold()) for value in levels
    }
    return normalized <= _GENERIC_BIDS_EVENT_ROLES


def _has_meaningful_value_refinement(
    trial_levels: dict[str, str],
    value_levels: dict[str, str],
) -> bool:
    if not _is_generic_event_role_taxonomy(trial_levels):
        return False
    if len(value_levels) <= len(trial_levels):
        return False
    meaningful_count = sum(
        _is_meaningful_class_level(code, description)
        for code, description in value_levels.items()
    )
    return meaningful_count >= 2 and meaningful_count / len(value_levels) >= 0.75


def _is_meaningful_class_level(code: str, description: str) -> bool:
    code_text = str(code).strip()
    description_text = str(description).strip()
    if not code_text or not description_text:
        return False
    normalized_code = re.sub(r"[\s_-]+", " ", code_text.casefold())
    normalized_description = re.sub(r"[\s_-]+", " ", description_text.casefold())
    if normalized_description == normalized_code:
        return False
    if normalized_description in _GENERIC_BIDS_EVENT_ROLES:
        return False
    if _IDENTIFIER_DESCRIPTION_PATTERN.fullmatch(normalized_description):
        return False
    return any(character.isalpha() for character in description_text)


def _sidecar_levels_cover_observed(
    profile: dict[str, Any],
    field: str,
) -> bool:
    observed = {str(value).strip() for value in profile["counts"][field]}
    levels = {str(value).strip() for value in profile["levels"][field]}
    return bool(observed and levels and observed <= levels)


def _bounded_tsv_text(path: Path, *, byte_limit: int) -> tuple[str, int, bool]:
    """Read complete TSV lines within a fixed byte budget."""
    if byte_limit <= 0:
        return "", 0, True
    with path.open("rb") as handle:
        payload = handle.read(byte_limit + 1)
    truncated = len(payload) > byte_limit
    payload = payload[:byte_limit]
    if truncated:
        line_end = max(payload.rfind(b"\n"), payload.rfind(b"\r"))
        payload = payload[: line_end + 1] if line_end >= 0 else b""
    return payload.decode("utf-8-sig"), len(payload), truncated


def _cross_run_set_consistency(sets: list[set[str]]) -> float:
    if not sets:
        return 0.0
    if len(sets) == 1:
        return 1.0
    union = set().union(*sets)
    return _ratio(len(set.intersection(*sets)), len(union))


def _is_repeated_categorical(counts: Counter[str]) -> bool:
    nonempty_count = sum(counts.values())
    cardinality = len(counts)
    if nonempty_count < 2 or cardinality < 2:
        return False
    reasonable_cardinality = cardinality <= min(
        32,
        max(4, int(math.sqrt(nonempty_count)) * 4),
    )
    repeated_count = sum(count for count in counts.values() if count > 1)
    return reasonable_cardinality and repeated_count / nonempty_count >= 0.5


def _cross_run_category_consistency(counts_by_run: list[Counter[str]]) -> float:
    if not counts_by_run:
        return 0.0
    if len(counts_by_run) == 1:
        return 1.0
    sets = [set(counts) for counts in counts_by_run]
    union = set().union(*sets)
    return _ratio(len(set.intersection(*sets)), len(union))


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _label_carrier_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if _is_bids_events_file(path):
        return "BIDS events"
    if suffix == ".mat":
        return "MAT"
    if suffix == ".csv":
        return "CSV"
    if suffix == ".tsv":
        return "TSV"
    if suffix == ".txt":
        return "TXT"
    return suffix.lstrip(".").upper() or "Unknown"


def _label_candidates_for_carrier(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".mat":
        return _mat_variables(path)
    if suffix in {".csv", ".tsv"} or _is_bids_events_file(path):
        columns = _tabular_columns(path)
        anchor_like = {
            "onset",
            "duration",
            "sample",
            "time",
            "timestamp",
            "latency",
            "trial",
            "trial_index",
            "index",
        }
        label_like = [
            column
            for column in columns
            if column.lower()
            in {
                "trial_type",
                "value",
                "label",
                "labels",
                "class",
                "classlabel",
                "classlabels",
                "class_label",
                "class_labels",
                "target",
                "condition",
                "event",
                "marker",
                "code",
                "stimulus",
                "hed",
            }
        ]
        remaining = [
            column
            for column in columns
            if column not in label_like and column.lower() not in anchor_like
        ]
        return [*label_like, *remaining]
    if suffix == ".txt":
        return ["line label sequence"]
    return []


def _normalize_value_decision_choices(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    allowed = {
        "role",
        "keep_event",
        "use_as_class",
        "class_name",
        "suggested_name",
        "decision",
        "decision_source",
        "provenance",
        "count",
    }
    result: dict[str, dict[str, Any]] = {}
    for raw_value, raw_decision in payload.items():
        value = str(raw_value).strip()
        if not value or not isinstance(raw_decision, dict):
            continue
        decision: dict[str, Any] = {}
        for raw_key, raw_item in raw_decision.items():
            key = str(raw_key)
            if key not in allowed:
                continue
            if key in {"keep_event", "use_as_class"}:
                if isinstance(raw_item, bool):
                    decision[key] = raw_item
                continue
            if key == "count":
                if isinstance(raw_item, int) and not isinstance(raw_item, bool):
                    decision[key] = max(raw_item, 0)
                continue
            item = str(raw_item).strip()
            if item:
                decision[key] = item
        if decision:
            result[value] = decision
    return result


def _anchor_candidates_for_carrier(
    path: Path,
    label_candidates: list[str],
) -> list[str]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"} or _is_bids_events_file(path):
        return [
            column
            for column in _tabular_columns(path)
            if column.lower()
            in {
                "onset",
                "sample",
                "time",
                "timestamp",
                "latency",
                "trial",
                "trial_index",
                "index",
            }
        ]
    if suffix == ".mat":
        return [
            name
            for name in label_candidates
            if any(
                token in name.lower()
                for token in ("onset", "cue", "trial", "sample", "event", "time")
            )
        ]
    if suffix == ".txt":
        return ["trial order"]
    return []


def _time_field_candidates_for_carrier(
    path: Path,
    label_candidates: list[str],
) -> list[str]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"} or _is_bids_events_file(path):
        return [
            column
            for column in _tabular_columns(path)
            if column.lower()
            in {
                "onset",
                "sample",
                "sample_index",
                "time",
                "timestamp",
                "latency",
                "trial",
                "trial_index",
                "index",
            }
        ]
    if suffix == ".mat":
        return [
            name
            for name in label_candidates
            if any(
                token in name.lower()
                for token in (
                    "onset",
                    "cue",
                    "trial",
                    "sample",
                    "time",
                    "latency",
                )
            )
        ]
    return []


def _event_code_candidates_for_carrier(
    path: Path,
    label_candidates: list[str],
) -> list[str]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"} or _is_bids_events_file(path):
        return [
            column
            for column in _tabular_columns(path)
            if column.lower()
            in {
                "event_code",
                "event",
                "code",
                "value",
                "marker",
                "marker_code",
                "trigger",
                "trigger_code",
                "stimulus",
                "stimulus_code",
            }
        ]
    if suffix == ".mat":
        return [
            name
            for name in label_candidates
            if any(
                token in name.lower()
                for token in ("event", "code", "marker", "trigger", "stim")
            )
        ]
    return []


def _duration_candidates_for_carrier(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"} or _is_bids_events_file(path):
        return [
            column
            for column in _tabular_columns(path)
            if column.lower()
            in {
                "duration",
                "dur",
                "end",
                "end_time",
                "offset",
                "stop",
                "stop_time",
            }
        ]
    if suffix == ".mat":
        return [
            name
            for name in _mat_variables(path)
            if any(
                token in name.lower()
                for token in ("duration", "dur", "end", "offset", "stop")
            )
        ]
    return []


def _tabular_columns(path: Path) -> list[str]:
    delimiter = (
        "\t" if path.suffix.lower() == ".tsv" or _is_bids_events_file(path) else ","
    )
    try:
        table = parsed_delimited_table(path, delimiter=delimiter)
        header = table.fieldnames
    except ParsedContentTooLargeError:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                header = next(reader, [])
        except (OSError, UnicodeDecodeError, csv.Error, StopIteration):
            return []
    except (OSError, UnicodeDecodeError, csv.Error, StopIteration):
        return []
    return [str(column).strip() for column in header if str(column).strip()]


def _observed_label_stats(path: Path, label_field: str) -> dict[str, Any]:
    if not label_field:
        return {"row_count": 0, "value_counts": {}}
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"} or _is_bids_events_file(path):
        return _tabular_label_stats(path, label_field)
    if suffix == ".mat":
        return _mat_label_stats(path, label_field)
    if suffix == ".txt":
        return _text_label_stats(path)
    return {"row_count": 0, "value_counts": {}}


def _observed_field_stats(path: Path, field_name: str) -> dict[str, Any]:
    if not field_name or field_name == "trial order":
        return _empty_field_stats()
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"} or _is_bids_events_file(path):
        return _tabular_field_stats(path, field_name)
    if suffix == ".mat":
        return _mat_field_stats(path, field_name)
    return _empty_field_stats()


def _time_label_preview(
    path: Path,
    time_field: str,
    label_field: str,
    *,
    limit: int,
) -> list[dict[str, str]]:
    time_field = str(time_field or "").strip()
    label_field = str(label_field or "").strip()
    if not time_field or not label_field or time_field == "trial order" or limit <= 0:
        return []
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"} or _is_bids_events_file(path):
        return _tabular_time_label_preview(
            path,
            time_field,
            label_field,
            limit=limit,
        )
    if suffix == ".mat":
        return _mat_time_label_preview(
            path,
            time_field,
            label_field,
            limit=limit,
        )
    return []


def _event_code_label_counts(
    path: Path,
    event_code_field: str,
    label_field: str,
) -> dict[str, dict[str, int]]:
    event_code_field = str(event_code_field or "").strip()
    label_field = str(label_field or "").strip()
    if not event_code_field or not label_field or event_code_field == "trial order":
        return {}
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"} or _is_bids_events_file(path):
        return _tabular_event_code_label_counts(path, event_code_field, label_field)
    if suffix == ".mat":
        return _mat_event_code_label_counts(path, event_code_field, label_field)
    return {}


def _tabular_event_code_label_counts(
    path: Path,
    event_code_field: str,
    label_field: str,
) -> dict[str, dict[str, int]]:
    delimiter = (
        "\t" if path.suffix.lower() == ".tsv" or _is_bids_events_file(path) else ","
    )
    counts: dict[str, Counter[str]] = {}
    try:
        table = parsed_delimited_table(path, delimiter=delimiter)
        if (
            not table.fieldnames
            or event_code_field not in table.fieldnames
            or label_field not in table.fieldnames
        ):
            return {}
        rows = table.dict_rows()
    except ParsedContentTooLargeError:
        return _legacy_tabular_event_code_label_counts(
            path,
            event_code_field,
            label_field,
            delimiter=delimiter,
        )
    except (OSError, UnicodeDecodeError, csv.Error):
        return {}
    for row in rows:
        code = _clean_label_value(row.get(event_code_field))
        label = _clean_label_value(row.get(label_field))
        if not code or not label:
            continue
        counts.setdefault(code, Counter())[label] += 1
    return _nested_counter_dict(counts)


def _legacy_tabular_event_code_label_counts(
    path: Path,
    event_code_field: str,
    label_field: str,
    *,
    delimiter: str,
) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if (
                not reader.fieldnames
                or event_code_field not in reader.fieldnames
                or label_field not in reader.fieldnames
            ):
                return {}
            for row in reader:
                code = _clean_label_value(row.get(event_code_field))
                label = _clean_label_value(row.get(label_field))
                if not code or not label:
                    continue
                counts.setdefault(code, Counter())[label] += 1
    except (OSError, UnicodeDecodeError, csv.Error):
        return {}
    return _nested_counter_dict(counts)


def _mat_event_code_label_counts(
    path: Path,
    event_code_field: str,
    label_field: str,
) -> dict[str, dict[str, int]]:
    try:
        payload = loadmat(str(path), squeeze_me=True, struct_as_record=False)
    except Exception:
        return {}
    code_value = _mat_variable(payload, event_code_field)
    label_value = _mat_variable(payload, label_field)
    if code_value is None or label_value is None:
        return {}
    code_array = np.asarray(code_value)
    label_array = np.asarray(label_value)
    if (
        code_array.dtype.names is not None
        or label_array.dtype.names is not None
        or object in (code_array.dtype, label_array.dtype)
    ):
        return {}
    counts: dict[str, Counter[str]] = {}
    for code_item, label_item in zip(
        code_array.reshape(-1),
        label_array.reshape(-1),
        strict=False,
    ):
        code = _clean_label_value(
            code_item.item() if hasattr(code_item, "item") else code_item
        )
        label = _clean_label_value(
            label_item.item() if hasattr(label_item, "item") else label_item
        )
        if not code or not label:
            continue
        counts.setdefault(code, Counter())[label] += 1
    return _nested_counter_dict(counts)


def _nested_counter_dict(counts: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {
        code: {
            label: values[label]
            for label in sorted(values, key=lambda item: (item.casefold(), item))
        }
        for code, values in sorted(counts.items(), key=lambda item: (item[0], item[0]))
    }


def _tabular_time_label_preview(
    path: Path,
    time_field: str,
    label_field: str,
    *,
    limit: int,
) -> list[dict[str, str]]:
    delimiter = (
        "\t" if path.suffix.lower() == ".tsv" or _is_bids_events_file(path) else ","
    )
    rows: list[dict[str, str]] = []
    try:
        table = parsed_delimited_table(path, delimiter=delimiter)
        if (
            not table.fieldnames
            or time_field not in table.fieldnames
            or label_field not in table.fieldnames
        ):
            return []
        source_rows = table.dict_rows()
    except ParsedContentTooLargeError:
        return _legacy_tabular_time_label_preview(
            path,
            time_field,
            label_field,
            limit=limit,
            delimiter=delimiter,
        )
    except (OSError, UnicodeDecodeError, csv.Error):
        return []
    for row in source_rows:
        time_value = _clean_label_value(row.get(time_field))
        label_value = _clean_label_value(row.get(label_field))
        if not time_value or not label_value:
            continue
        rows.append({"time": time_value, "label": label_value})
        if len(rows) >= limit:
            break
    return rows


def _legacy_tabular_time_label_preview(
    path: Path,
    time_field: str,
    label_field: str,
    *,
    limit: int,
    delimiter: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if (
                not reader.fieldnames
                or time_field not in reader.fieldnames
                or label_field not in reader.fieldnames
            ):
                return []
            for row in reader:
                time_value = _clean_label_value(row.get(time_field))
                label_value = _clean_label_value(row.get(label_field))
                if not time_value or not label_value:
                    continue
                rows.append({"time": time_value, "label": label_value})
                if len(rows) >= limit:
                    break
    except (OSError, UnicodeDecodeError, csv.Error):
        return []
    return rows


def _mat_time_label_preview(
    path: Path,
    time_field: str,
    label_field: str,
    *,
    limit: int,
) -> list[dict[str, str]]:
    try:
        payload = loadmat(str(path), squeeze_me=True, struct_as_record=False)
    except Exception:
        return []
    time_value = _mat_variable(payload, time_field)
    label_value = _mat_variable(payload, label_field)
    if time_value is None or label_value is None:
        return []
    time_array = np.asarray(time_value)
    label_array = np.asarray(label_value)
    if (
        time_array.dtype.names is not None
        or label_array.dtype.names is not None
        or object in (time_array.dtype, label_array.dtype)
    ):
        return []
    rows: list[dict[str, str]] = []
    time_values = time_array.reshape(-1)
    label_values = label_array.reshape(-1)
    for time_item, label_item in zip(time_values, label_values, strict=False):
        time_text = _clean_label_value(
            time_item.item() if hasattr(time_item, "item") else time_item
        )
        label_text = _clean_label_value(
            label_item.item() if hasattr(label_item, "item") else label_item
        )
        if not time_text or not label_text:
            continue
        rows.append({"time": time_text, "label": label_text})
        if len(rows) >= limit:
            break
    return rows


def _empty_field_stats() -> dict[str, Any]:
    return {
        "row_count": 0,
        "value_counts": {},
        "numeric_count": 0,
        "min": None,
        "max": None,
    }


def _tabular_field_stats(path: Path, field_name: str) -> dict[str, Any]:
    delimiter = (
        "\t" if path.suffix.lower() == ".tsv" or _is_bids_events_file(path) else ","
    )
    values: list[Any] = []
    try:
        table = parsed_delimited_table(path, delimiter=delimiter)
        if not table.fieldnames or field_name not in table.fieldnames:
            return _empty_field_stats()
        values = [row.get(field_name) for row in table.dict_rows()]
    except ParsedContentTooLargeError:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                if not reader.fieldnames or field_name not in reader.fieldnames:
                    return _empty_field_stats()
                values = [row.get(field_name) for row in reader]
        except (OSError, UnicodeDecodeError, csv.Error):
            return _empty_field_stats()
    except (OSError, UnicodeDecodeError, csv.Error):
        return _empty_field_stats()
    return _field_stats_from_values(values)


def _mat_field_stats(path: Path, field_name: str) -> dict[str, Any]:
    try:
        payload = loadmat(str(path), squeeze_me=True, struct_as_record=False)
    except Exception:
        return _empty_field_stats()
    value = _mat_variable(payload, field_name)
    if value is None:
        return _empty_field_stats()
    array = np.asarray(value)
    if array.dtype.names is not None or array.dtype == object:
        return _empty_field_stats()
    return _field_stats_from_values(
        item.item() if hasattr(item, "item") else item for item in array.reshape(-1)
    )


def _field_stats_from_values(values: Iterable[Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    numeric_values: list[float] = []
    for value in values:
        text = _clean_label_value(value)
        if not text:
            continue
        counts[text] += 1
        numeric = _numeric_value(text)
        if numeric is not None:
            numeric_values.append(numeric)
    stats = _empty_field_stats()
    stats["row_count"] = sum(counts.values())
    stats["value_counts"] = {
        value: counts[value]
        for value in sorted(counts, key=lambda item: (item.casefold(), item))
    }
    stats["numeric_count"] = len(numeric_values)
    if numeric_values:
        stats["min"] = min(numeric_values)
        stats["max"] = max(numeric_values)
    return stats


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, Real):
        numeric = float(value)
    else:
        try:
            numeric = float(str(value).strip())
        except ValueError:
            return None
    return numeric if math.isfinite(numeric) else None


def _tabular_label_stats(path: Path, label_field: str) -> dict[str, Any]:
    delimiter = (
        "\t" if path.suffix.lower() == ".tsv" or _is_bids_events_file(path) else ","
    )
    counts: Counter[str] = Counter()
    try:
        table = parsed_delimited_table(path, delimiter=delimiter)
        if not table.fieldnames or label_field not in table.fieldnames:
            return {"row_count": 0, "value_counts": {}}
        rows = table.dict_rows()
    except ParsedContentTooLargeError:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                if not reader.fieldnames or label_field not in reader.fieldnames:
                    return {"row_count": 0, "value_counts": {}}
                rows = list(reader)
        except (OSError, UnicodeDecodeError, csv.Error):
            return {"row_count": 0, "value_counts": {}}
    except (OSError, UnicodeDecodeError, csv.Error):
        return {"row_count": 0, "value_counts": {}}
    for row in rows:
        value = _clean_label_value(row.get(label_field))
        if value:
            counts[value] += 1
    return _label_stats_from_counts(counts)


def _mat_label_stats(path: Path, label_field: str) -> dict[str, Any]:
    try:
        payload = loadmat(str(path), squeeze_me=True, struct_as_record=False)
    except Exception:
        return {"row_count": 0, "value_counts": {}}
    value = _mat_variable(payload, label_field)
    if value is None:
        return {"row_count": 0, "value_counts": {}}
    array = np.asarray(value)
    if array.dtype.names is not None or array.dtype == object:
        return {"row_count": 0, "value_counts": {}}
    counts: Counter[str] = Counter()
    for item in array.reshape(-1):
        label = _clean_label_value(item.item() if hasattr(item, "item") else item)
        if label:
            counts[label] += 1
    return _label_stats_from_counts(counts)


def _text_label_stats(path: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                value = _clean_label_value(line)
                if value:
                    counts[value] += 1
    except (OSError, UnicodeDecodeError):
        return {"row_count": 0, "value_counts": {}}
    return _label_stats_from_counts(counts)


def _label_stats_from_counts(counts: Counter[str]) -> dict[str, Any]:
    ordered = {
        value: counts[value]
        for value in sorted(counts, key=lambda item: (item.casefold(), item))
    }
    return {"row_count": sum(ordered.values()), "value_counts": ordered}


def _bids_event_level_labels(
    path: Path,
    label_field: str,
    *,
    sidecar_reader: BidsEventsJsonReader | None = None,
) -> dict[str, str]:
    if not label_field:
        return {}
    reader = sidecar_reader or BidsEventsJsonReader.from_paths(
        bids_events_json_resource_paths([str(path)]),
    )
    sidecars = (
        sidecar_reader.candidate_paths_for(path)
        if sidecar_reader is not None
        else bids_events_json_candidates(path)
    )
    for sidecar in sidecars:
        payload = reader.read_object(sidecar)
        levels = _levels_for_field(payload, label_field)
        if levels:
            return levels
    return {}


def _levels_for_field(payload: dict[str, Any], label_field: str) -> dict[str, str]:
    field_payload = _case_insensitive_mapping_value(payload, label_field)
    if not isinstance(field_payload, dict):
        return {}
    levels = _case_insensitive_mapping_value(field_payload, "Levels")
    if not isinstance(levels, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in levels.items():
        code = _clean_label_value(key)
        label = _clean_level_label(value)
        if code and label:
            result[code] = label
    return result


def _case_insensitive_mapping_value(
    payload: dict[str, Any],
    key: str,
) -> Any | None:
    if key in payload:
        return payload[key]
    normalized = key.lower()
    for item_key, value in payload.items():
        if str(item_key).lower() == normalized:
            return value
    return None


def _clean_level_label(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("LongName", "Description", "description", "name"):
            text = _clean_label_value(value.get(key))
            if text:
                return text
        return ""
    return _clean_label_value(value)


def _clean_label_value(value: Any) -> str:
    if isinstance(value, Real):
        numeric = float(value)
        if not math.isfinite(numeric):
            return ""
        if numeric.is_integer():
            return str(int(numeric))
        return str(value).strip()
    text = str(value or "").strip()
    if not text or text.lower() in {"n/a", "na", "nan", "null"}:
        return ""
    return text


def _mat_variable(payload: dict[str, Any], label_field: str) -> Any | None:
    requested = str(label_field).strip()
    if not requested:
        return None
    for key, value in payload.items():
        if str(key).startswith("__"):
            continue
        if key == requested:
            return value
    normalized = requested.lower()
    for key, value in payload.items():
        if str(key).startswith("__"):
            continue
        if str(key).lower() == normalized:
            return value
    return None


def _mat_variables(path: Path) -> list[str]:
    try:
        payload = loadmat(str(path), squeeze_me=True, struct_as_record=False)
    except Exception:
        return []
    variables: list[str] = []
    for key, value in payload.items():
        if str(key).startswith("__"):
            continue
        size = getattr(value, "size", 1)
        if isinstance(size, int | float) and size <= 0:
            continue
        variables.append(str(key))
    return sorted(variables)


def _default_time_model(path: Path, anchor_candidates: list[str]) -> str:
    if _is_bids_events_file(path):
        return "seconds"
    if any("sample" in candidate.lower() for candidate in anchor_candidates):
        return "sample_index"
    if any(
        token in candidate.lower()
        for candidate in anchor_candidates
        for token in ("time", "onset", "timestamp")
    ):
        return "relative_time"
    return "trial_order"


def _default_granularity(path: Path) -> str:
    if _is_bids_events_file(path):
        return "event"
    if path.suffix.lower() in {".csv", ".tsv", ".mat", ".txt"}:
        return "trial"
    return "unknown"


def _default_duration_field(duration_candidates: list[str]) -> str:
    for candidate in duration_candidates:
        if candidate.lower() == "duration":
            return candidate
    return duration_candidates[0] if duration_candidates else ""


def _default_placement_method(
    *,
    time_model: str,
    granularity: str,
    duration_field: str,
    time_field_candidates: list[str],
    event_code_candidates: list[str],
) -> str:
    if (granularity == "segment" or duration_field) and time_field_candidates:
        return "interval"
    if event_code_candidates and not time_field_candidates:
        return "event_code"
    if time_model in {"seconds", "relative_time", "sample_index"}:
        return "time_field"
    return "eeg_event"


def _default_anchor_for_placement(
    *,
    placement_method: str,
    anchor_candidates: list[str],
    time_field_candidates: list[str],
    interval_start_candidates: list[str],
    event_code_candidates: list[str],
) -> str:
    if placement_method == "event_code" and event_code_candidates:
        return event_code_candidates[0]
    if placement_method == "interval" and interval_start_candidates:
        return interval_start_candidates[0]
    if placement_method == "time_field" and time_field_candidates:
        return time_field_candidates[0]
    if placement_method == "eeg_event":
        return "trial order"
    return anchor_candidates[0] if anchor_candidates else ""


def _target_event_codes_for_choice(
    carrier_choice: dict[str, Any],
    selected_anchor: str,
    placement_method: str,
) -> list[str]:
    if placement_method != "eeg_event":
        return []
    values = _string_list(carrier_choice.get("target_event_codes"))
    if values:
        return values
    anchor = str(selected_anchor or "").strip()
    if anchor and anchor != "trial order":
        return [anchor]
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values: Iterable[Any] = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        return []
    result: list[str] = []
    for item in raw_values:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _label_carrier_reason(
    path: Path,
    label_candidates: list[str],
    anchor_candidates: list[str],
) -> str:
    carrier_format = _label_carrier_format(path)
    if label_candidates and anchor_candidates:
        return (
            f"{carrier_format} carrier has candidate label fields and anchors; "
            "review the selected alignment before applying."
        )
    if label_candidates:
        return (
            f"{carrier_format} carrier has candidate label fields; choose the "
            "trial anchor or confirm trial-order alignment."
        )
    return (
        f"{carrier_format} carrier was detected, but its label field could not "
        "be inferred automatically."
    )


def _is_bids_events_file(path: Path) -> bool:
    return path.name.endswith("_events.tsv") or path.name == "events.tsv"


def _bids_event_columns(path: Path) -> list[str]:
    return _tabular_columns(path) if _is_bids_events_file(path) else []


def _label_carrier_warnings(
    path: Path,
    *,
    bids_event_columns: list[str],
    time_field_candidates: list[str],
    duration_candidates: list[str],
    sidecar_reader: BidsEventsJsonReader | None = None,
    events_json_sidecar_present: bool | None = None,
    selected_label_field: str = "",
    selected_label_field_levels_available: bool | None = None,
) -> list[str]:
    if not _is_bids_events_file(path):
        return []
    warnings: list[str] = []
    sidecar_present = (
        bool(events_json_sidecar_present)
        if events_json_sidecar_present is not None
        else bool(
            _existing_bids_events_json_candidates(
                path,
                sidecar_reader=sidecar_reader,
            )
        )
    )
    if not sidecar_present:
        warnings.append(
            f"{path.name} events.json sidecar is missing; class names and event "
            "semantics need confirmation."
        )
    elif selected_label_field and selected_label_field_levels_available is False:
        warnings.append(
            f"{path.name} events.json does not define Levels for "
            f"{selected_label_field}; class names need confirmation."
        )
    normalized_columns = {column.lower() for column in bids_event_columns}
    if "onset" not in normalized_columns and not time_field_candidates:
        warnings.append(
            f"{path.name} onset column is missing; event timing cannot be "
            "confirmed from BIDS-style event time."
        )
    if "duration" not in normalized_columns and not duration_candidates:
        warnings.append(
            f"{path.name} duration column is missing; EEG epoch windows will need "
            "manual review after import."
        )
    return warnings


def _existing_bids_events_json_candidates(
    path: Path,
    *,
    sidecar_reader: BidsEventsJsonReader | None = None,
) -> list[Path]:
    if sidecar_reader is not None:
        return (
            list(sidecar_reader.candidate_paths_for(path))
            if sidecar_reader.has_candidate_for(path)
            else []
        )
    return [
        candidate
        for candidate in bids_events_json_candidates(path)
        if candidate.exists()
    ]


def _sidecar_reader_for_plan(
    label_carrier_plan: list[dict[str, Any]],
) -> BidsEventsJsonReader:
    return BidsEventsJsonReader.from_paths(
        bids_events_json_resource_paths(
            str(carrier.get("path") or "") for carrier in label_carrier_plan
        ),
    )
