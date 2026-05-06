"""Label-carrier planning for Data Interpretation sources."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from scipy.io import loadmat

NEEDS_CONFIRMATION = "needs_confirmation"


def build_label_carrier_plan(
    label_carriers: list[str],
    choices_payload: Any,
) -> list[dict[str, Any]]:
    """Build reviewable label-carrier rows for interpretation preview."""
    choices = normalize_label_carrier_choices(choices_payload)
    return [
        _label_carrier_plan_for_path(Path(carrier), choices)
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
        for value in _observed_label_values(carrier, limit=remaining):
            if value not in class_map:
                class_map[value] = value
    return class_map


def normalize_label_carrier_choices(payload: Any) -> dict[str, dict[str, str]]:
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
    }
    for carrier_key, carrier_choices in payload.items():
        if not isinstance(carrier_choices, dict):
            continue
        cleaned = {
            str(key): str(value).strip()
            for key, value in carrier_choices.items()
            if str(key) in allowed and str(value).strip()
        }
        if cleaned:
            result[str(carrier_key)] = cleaned
    return result


def _label_carrier_plan_for_path(
    path: Path,
    choices: dict[str, dict[str, str]],
) -> dict[str, Any]:
    carrier_choice = _choice_for_label_carrier(path, choices)
    label_candidates = _label_candidates_for_carrier(path)
    anchor_candidates = _anchor_candidates_for_carrier(path, label_candidates)
    selected_label = carrier_choice.get("label_field") or (
        label_candidates[0] if label_candidates else ""
    )
    selected_anchor = carrier_choice.get("anchor") or (
        anchor_candidates[0] if anchor_candidates else ""
    )
    return {
        "path": str(path),
        "name": path.name,
        "format": _label_carrier_format(path),
        "label_candidates": label_candidates,
        "anchor_candidates": anchor_candidates,
        "selected_label_field": selected_label,
        "selected_anchor": selected_anchor,
        "time_model": carrier_choice.get("time_model")
        or _default_time_model(path, anchor_candidates),
        "granularity": carrier_choice.get("granularity") or _default_granularity(path),
        "role": carrier_choice.get("role") or "external labels",
        "selected_target_file": carrier_choice.get("target_file", ""),
        "decision": NEEDS_CONFIRMATION,
        "reason": _label_carrier_reason(path, label_candidates, anchor_candidates),
    }


def _choice_for_label_carrier(
    path: Path,
    choices: dict[str, dict[str, str]],
) -> dict[str, str]:
    return choices.get(str(path), choices.get(path.name, {}))


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
    return []


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


def _clean_label_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"n/a", "na", "nan", "null"}:
        return ""
    return text


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
