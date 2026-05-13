"""Label-carrier planning for Data Interpretation sources."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from collections.abc import Iterable
from numbers import Real
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

NEEDS_CONFIRMATION = "needs_confirmation"


def build_label_carrier_plan(
    label_carriers: list[str],
    choices_payload: Any,
    *,
    carrier_sources: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Build reviewable label-carrier rows for interpretation preview."""
    choices = normalize_label_carrier_choices(choices_payload)
    carrier_sources = dict(carrier_sources or {})
    return [
        _label_carrier_plan_for_path(
            Path(carrier),
            choices,
            raw_path=str(carrier),
            source_location=carrier_sources.get(str(carrier), ""),
        )
        for carrier in label_carriers
    ]


def infer_class_map_from_label_carrier_plan(
    label_carrier_plan: list[dict[str, Any]],
    *,
    limit: int = 20,
) -> dict[str, str]:
    """Return observed tabular label values for human review in the wizard."""
    class_map: dict[str, str] = {}
    for carrier in label_carrier_plan:
        remaining = max(limit - len(class_map), 0)
        if remaining <= 0:
            break
        for value, label in _observed_class_map_entries(carrier, limit=remaining):
            if value not in class_map:
                class_map[value] = label
    return class_map


def normalize_label_carrier_choices(payload: Any) -> dict[str, dict[str, Any]]:
    """Return cleaned wizard choices keyed by carrier path or file name."""
    if not isinstance(payload, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    allowed = {
        "label_field",
        "anchor",
        "time_model",
        "granularity",
        "role",
        "target_file",
        "placement_method",
        "duration_field",
        "target_event_codes",
    }
    for carrier_key, carrier_choices in payload.items():
        if not isinstance(carrier_choices, dict):
            continue
        cleaned: dict[str, Any] = {}
        for key, value in carrier_choices.items():
            key_text = str(key)
            if key_text not in allowed:
                continue
            if key_text == "target_event_codes":
                values = _string_list(value)
                if values:
                    cleaned[key_text] = values
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
    selected_label = carrier_choice.get("label_field") or (
        label_candidates[0] if label_candidates else ""
    )
    time_model = carrier_choice.get("time_model") or _default_time_model(
        path, anchor_candidates
    )
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
    anchor_stats = _observed_field_stats(path, selected_anchor)
    duration_stats = _observed_field_stats(path, selected_duration)
    return {
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
        "selected_anchor_stats": anchor_stats,
        "selected_duration_stats": duration_stats,
        "time_model": time_model,
        "granularity": granularity,
        "placement_method": placement_method,
        "role": carrier_choice.get("role") or "external labels",
        "selected_target_file": carrier_choice.get("target_file", ""),
        "decision": NEEDS_CONFIRMATION,
        "reason": _label_carrier_reason(path, label_candidates, anchor_candidates),
    }


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
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            header = next(reader, [])
    except (OSError, UnicodeDecodeError, csv.Error, StopIteration):
        return []
    return [str(column).strip() for column in header if str(column).strip()]


def _observed_label_values(carrier: dict[str, Any], *, limit: int) -> list[str]:
    if limit <= 0:
        return []
    path = Path(str(carrier.get("path") or ""))
    label_field = str(carrier.get("selected_label_field") or "").strip()
    if not label_field:
        return []
    if path.suffix.lower() in {".csv", ".tsv"} or _is_bids_events_file(path):
        return _tabular_label_values(path, label_field, limit=limit)
    if path.suffix.lower() == ".mat":
        return _mat_label_values(path, label_field, limit=limit)
    if path.suffix.lower() == ".txt":
        return _text_label_values(path, limit=limit)
    return []


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
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames or field_name not in reader.fieldnames:
                return _empty_field_stats()
            values = [row.get(field_name) for row in reader]
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
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames or label_field not in reader.fieldnames:
                return {"row_count": 0, "value_counts": {}}
            for row in reader:
                value = _clean_label_value(row.get(label_field))
                if value:
                    counts[value] += 1
    except (OSError, UnicodeDecodeError, csv.Error):
        return {"row_count": 0, "value_counts": {}}
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
        with path.open("r", encoding="utf-8") as handle:
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


def _observed_class_map_entries(
    carrier: dict[str, Any],
    *,
    limit: int,
) -> list[tuple[str, str]]:
    values = _observed_label_values(carrier, limit=limit)
    if not values:
        return []
    path = Path(str(carrier.get("path") or ""))
    label_field = str(carrier.get("selected_label_field") or "").strip()
    level_labels = (
        _bids_event_level_labels(path, label_field)
        if _is_bids_events_file(path)
        else {}
    )
    return [(value, level_labels.get(value, value)) for value in values]


def _tabular_label_values(path: Path, label_field: str, *, limit: int) -> list[str]:
    delimiter = (
        "\t" if path.suffix.lower() == ".tsv" or _is_bids_events_file(path) else ","
    )
    values: list[str] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames or label_field not in reader.fieldnames:
                return []
            for row in reader:
                value = _clean_label_value(row.get(label_field))
                if not value or value in values:
                    continue
                values.append(value)
                if len(values) >= limit:
                    break
    except (OSError, UnicodeDecodeError, csv.Error):
        return []
    return values


def _text_label_values(path: Path, *, limit: int) -> list[str]:
    values: list[str] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                value = _clean_label_value(line)
                if not value or value in values:
                    continue
                values.append(value)
                if len(values) >= limit:
                    break
    except (OSError, UnicodeDecodeError):
        return []
    return values


def _bids_event_level_labels(path: Path, label_field: str) -> dict[str, str]:
    if not label_field:
        return {}
    for sidecar in _bids_events_json_candidates(path):
        payload = _json_object(sidecar)
        levels = _levels_for_field(payload, label_field)
        if levels:
            return levels
    return {}


def _bids_events_json_candidates(path: Path) -> list[Path]:
    names = _bids_event_sidecar_names(path)
    candidates: list[Path] = []
    for directory in [path.parent, *path.parents[1:8]]:
        for name in names:
            candidate = directory / name
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _bids_event_sidecar_names(path: Path) -> list[str]:
    names: list[str] = []
    if path.name.endswith(".tsv"):
        stem = path.name[: -len(".tsv")]
        names.append(f"{stem}.json")
    prefix = path.name.removesuffix(".tsv").removesuffix("_events")
    parts = [part for part in prefix.split("_") if part]
    semantic_parts = [
        part for part in parts if not part.startswith(("sub-", "ses-", "run-"))
    ]
    if semantic_parts:
        names.append("_".join([*semantic_parts, "events"]) + ".json")
    names.append("events.json")
    result: list[str] = []
    for name in names:
        if name not in result:
            result.append(name)
    return result


def _json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _mat_label_values(path: Path, label_field: str, *, limit: int) -> list[str]:
    try:
        payload = loadmat(str(path), squeeze_me=True, struct_as_record=False)
    except Exception:
        return []
    value = _mat_variable(payload, label_field)
    if value is None:
        return []
    array = np.asarray(value)
    if array.dtype.names is not None or array.dtype == object:
        return []
    values: list[str] = []
    for item in array.reshape(-1):
        label = _clean_label_value(item.item() if hasattr(item, "item") else item)
        if not label or label in values:
            continue
        values.append(label)
        if len(values) >= limit:
            break
    return values


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
    if granularity == "segment" or duration_field:
        return "interval"
    if time_model in {"seconds", "relative_time", "sample_index"}:
        return "time_field"
    if event_code_candidates and not time_field_candidates:
        return "event_code"
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
