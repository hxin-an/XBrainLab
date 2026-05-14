"""Internal EEG event evidence for Data Interpretation previews."""

from __future__ import annotations

import importlib
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

INTERNAL_EVENT_EXTENSIONS = (
    ".gdf",
    ".edf",
    ".bdf",
    ".set",
    ".vhdr",
    ".fif",
    ".fif.gz",
    ".cnt",
)

_PATTERN_MIN_COUNT_PER_FILE = 5
_PATTERN_MIN_LABEL_CODES = 2
_PATTERN_MAX_LABEL_CODES = 12
_CLASS_LIKE_TOKENS = {
    "left",
    "right",
    "hand",
    "foot",
    "feet",
    "tongue",
    "target",
    "non-target",
    "nontarget",
    "standard",
    "deviant",
    "rest",
}
_NUMBER_RE = re.compile(r"\b\d+\b")


def build_internal_event_preview(selected_files: list[str]) -> dict[str, Any]:
    """Build UI/agent-readable evidence from events embedded in EEG files."""
    event_files = [
        str(item) for item in selected_files if _has_internal_event_extension(str(item))
    ]
    if not event_files:
        return {}

    file_names = [Path(item).name or str(item) for item in event_files]
    aggregates: dict[str, dict[str, Any]] = {}
    scan_warnings: list[str] = []
    for file_path, file_name in zip(event_files, file_names, strict=True):
        try:
            payload = _read_internal_events_for_file(file_path)
        except Exception as exc:  # pragma: no cover - covered through caller payload
            scan_warnings.append(_scan_warning(file_path, exc))
            continue

        if isinstance(payload, dict) and payload.get("read_error"):
            scan_warnings.append(str(payload["read_error"]))
        for row in _normalize_file_event_rows(payload):
            code = row["code"]
            stats = aggregates.setdefault(
                code,
                {
                    "code": code,
                    "total_count": 0,
                    "file_counts": {},
                    "descriptions": set(),
                    "suffixes": set(),
                },
            )
            count = int(row["count"])
            stats["total_count"] += count
            stats["file_counts"][file_name] = (
                int(stats["file_counts"].get(file_name, 0)) + count
            )
            description = str(row.get("description") or "").strip()
            if description:
                stats["descriptions"].add(description)
            stats["suffixes"].add(_file_suffix(file_path))

    candidate_rows: list[dict[str, Any]] = []
    not_used_rows: list[dict[str, Any]] = []
    semantics_by_code = {
        str(stats["code"]): _semantic_for_event(stats) for stats in aggregates.values()
    }
    _apply_count_pattern_evidence(aggregates, semantics_by_code, file_names)
    for stats in sorted(aggregates.values(), key=_event_sort_key):
        semantic = semantics_by_code[str(stats["code"])]
        row = _preview_row(stats, semantic, file_names)
        if semantic["bucket"] == "candidate":
            candidate_rows.append(row)
        else:
            not_used_rows.append(row)

    result: dict[str, Any] = {
        "source": "mne_internal_events",
        "file_count": len(event_files),
        "scanned_files": file_names,
        "event_count": sum(int(item["total_count"]) for item in aggregates.values()),
        "candidate_label_events": candidate_rows,
        "not_used_events": not_used_rows,
        "names_reliable": _names_reliable(candidate_rows),
        "pattern_status": _pattern_status(candidate_rows, not_used_rows),
    }
    if _has_run_dependent_t_markers(aggregates):
        result["run_dependent_semantics"] = True
        result["run_dependent_event_codes"] = sorted(
            [code for code in aggregates if str(code).upper() in {"T0", "T1", "T2"}],
            key=str.casefold,
        )
        result["run_dependent_mapping"] = _run_dependent_mapping(
            event_files,
            file_names,
            result["run_dependent_event_codes"],
        )
        scan_warnings.append(
            "PhysioNet-style T1/T2 event labels can change meaning by run; "
            "confirm run/task mapping before supervised training."
        )
    if scan_warnings:
        result["scan_warnings"] = scan_warnings
    return result


def _read_internal_events_for_file(path: str) -> dict[str, Any]:
    """Read embedded events from one EEG file using MNE without preloading data."""
    mne = importlib.import_module("mne")

    raw = _read_mne_object(path, mne)
    return {"events": _events_from_mne_object(raw, mne)}


def _read_mne_object(path: str, mne: Any) -> Any:
    lower = str(path).lower()
    suffix = Path(lower).suffix
    if lower.endswith((".fif", ".fif.gz")):
        return mne.io.read_raw_fif(path, preload=False, verbose="ERROR")
    if suffix == ".gdf":
        return mne.io.read_raw_gdf(path, preload=False, verbose="ERROR")
    if suffix == ".edf":
        return mne.io.read_raw_edf(path, preload=False, verbose="ERROR")
    if suffix == ".bdf":
        return mne.io.read_raw_bdf(path, preload=False, verbose="ERROR")
    if suffix == ".vhdr":
        return mne.io.read_raw_brainvision(path, preload=False, verbose="ERROR")
    if suffix == ".cnt":
        return mne.io.read_raw_cnt(path, preload=False, verbose="ERROR")
    if suffix == ".set":
        try:
            return mne.io.read_raw_eeglab(
                path,
                uint16_codec="latin1",
                preload=False,
                verbose="ERROR",
            )
        except Exception:
            return mne.io.read_epochs_eeglab(
                path,
                uint16_codec="latin1",
                verbose="ERROR",
            )
    raise ValueError(f"Unsupported internal event source: {path}")


def _events_from_mne_object(mne_object: Any, mne: Any) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    _add_annotation_events(rows, mne_object, mne)
    if not rows:
        _add_epoch_events(rows, mne_object)
    if not rows:
        _add_stim_channel_events(rows, mne_object, mne)
    return rows


def _add_annotation_events(rows: dict[str, dict[str, Any]], mne_object: Any, mne: Any):
    annotations = getattr(mne_object, "annotations", None)
    if annotations is None or len(annotations) == 0:
        return
    try:
        events, event_id = mne.events_from_annotations(
            mne_object,
            verbose="ERROR",
        )
    except Exception:
        return
    id_to_description = {int(value): str(key) for key, value in event_id.items()}
    for event_value in events[:, 2].tolist():
        description = id_to_description.get(int(event_value), str(event_value))
        code = _event_code_from_description(description, fallback=str(event_value))
        _increment_event_row(rows, code, description)


def _add_epoch_events(rows: dict[str, dict[str, Any]], mne_object: Any) -> None:
    events = getattr(mne_object, "events", None)
    if events is None:
        return
    event_id = getattr(mne_object, "event_id", {}) or {}
    id_to_description = {int(value): str(key) for key, value in event_id.items()}
    try:
        values = events[:, 2].tolist()
    except Exception:
        return
    for event_value in values:
        description = id_to_description.get(int(event_value), str(event_value))
        code = _event_code_from_description(description, fallback=str(event_value))
        _increment_event_row(rows, code, description)


def _add_stim_channel_events(
    rows: dict[str, dict[str, Any]],
    mne_object: Any,
    mne: Any,
) -> None:
    try:
        events = mne.find_events(mne_object, shortest_event=1, verbose="ERROR")
    except Exception:
        return
    for event_value in events[:, 2].tolist():
        text = str(int(event_value))
        _increment_event_row(rows, text, text)


def _increment_event_row(
    rows: dict[str, dict[str, Any]],
    code: str,
    description: str,
) -> None:
    if not code:
        return
    row = rows.setdefault(
        code,
        {"count": 0, "description": description or code},
    )
    row["count"] = int(row.get("count", 0)) + 1
    if description and not str(row.get("description") or "").strip():
        row["description"] = description


def _normalize_file_event_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    source = payload.get("events", payload)
    if isinstance(source, dict):
        return _normalize_event_mapping(source)
    if isinstance(source, list):
        return _normalize_event_list(source)
    return []


def _normalize_event_mapping(source: dict[Any, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in source.items():
        if str(key) in {"read_error", "warnings", "scan_warnings"}:
            continue
        if isinstance(value, dict):
            count = _positive_int(
                value.get("count")
                or value.get("event_count")
                or value.get("occurrences")
            )
            description = str(value.get("description") or value.get("name") or key)
        else:
            count = _positive_int(value)
            description = str(key)
        code = _event_code_from_description(str(key), fallback=description)
        if not count or not code:
            continue
        rows.append({"code": code, "count": count, "description": description})
    return rows


def _normalize_event_list(source: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in source:
        if not isinstance(item, dict):
            continue
        count = _positive_int(
            item.get("count") or item.get("event_count") or item.get("occurrences")
        )
        code = _event_code_from_description(
            str(
                item.get("event_code")
                or item.get("code")
                or item.get("label")
                or item.get("description")
                or ""
            ),
            fallback=str(item.get("description") or ""),
        )
        if not count or not code:
            continue
        rows.append(
            {
                "code": code,
                "count": count,
                "description": str(item.get("description") or code),
            }
        )
    return rows


def _event_code_from_description(description: str, *, fallback: str = "") -> str:
    text = " ".join(str(description or "").strip().split())
    if text.isdigit():
        return str(int(text))
    if _looks_like_prefixed_marker(text):
        return text
    fallback_text = " ".join(str(fallback or "").strip().split())
    if text:
        return text
    return fallback_text


def _looks_like_coded_marker(text: str) -> bool:
    return bool(_NUMBER_RE.fullmatch(str(text or "").strip()))


def _looks_like_prefixed_marker(text: str) -> bool:
    normalized = text.casefold()
    prefixes = (
        "stimulus/s",
        "response/r",
        "event/e",
        "annotation/",
        "trigger/",
    )
    return normalized.startswith(prefixes)


def _semantic_for_event(stats: dict[str, Any]) -> dict[str, str]:
    descriptions = [str(item) for item in stats.get("descriptions", set())]
    if _description_has_any(descriptions, ("artifact", "artefact", "reject", "bad")):
        return {
            "bucket": "not_used",
            "use_as": "Exclude bad trials",
            "reason": "Rejected / artifact trial",
            "evidence": "Artifact text",
        }
    if _description_has_any(
        descriptions,
        ("boundary", "edge", "new segment", "sync", "system"),
    ):
        return {
            "bucket": "not_used",
            "use_as": "Ignore",
            "reason": "System / boundary marker",
            "evidence": "Boundary/system text",
        }
    if _description_has_any(descriptions, ("response", "button", "keypress")):
        return {
            "bucket": "not_used",
            "use_as": "Response",
            "reason": "Response marker",
            "evidence": "Response text",
        }
    if _description_has_any(descriptions, ("comment", "note")):
        return {
            "bucket": "not_used",
            "use_as": "Ignore",
            "reason": "Comment marker",
            "evidence": "Comment text",
        }
    if _description_has_any(descriptions, ("trial start", "starttrial", "start trial")):
        return {
            "bucket": "not_used",
            "use_as": "Trial timing",
            "reason": "Trial start marker",
            "evidence": "Trial-start text",
        }
    class_name = _class_like_description(descriptions)
    if class_name:
        return {
            "bucket": "candidate",
            "use_as": "Class label",
            "evidence": "Class-like text",
            "class_name": class_name,
        }
    return {
        "bucket": "not_used",
        "use_as": "Review",
        "reason": "Event role needs review",
        "evidence": "Needs review",
    }


def _apply_count_pattern_evidence(
    aggregates: dict[str, dict[str, Any]],
    semantics_by_code: dict[str, dict[str, str]],
    file_names: list[str],
) -> None:
    pattern = _repeated_event_group_pattern(
        aggregates,
        semantics_by_code,
        file_names,
    )
    if not pattern:
        return

    evidence = "Repeated count"
    if pattern.get("timing_code"):
        evidence += " + timing"
    for code in pattern["candidate_codes"]:
        semantic = semantics_by_code.get(code)
        if not semantic or semantic.get("bucket") == "candidate":
            continue
        semantic.pop("reason", None)
        semantic.update(
            {
                "bucket": "candidate",
                "use_as": "Class label",
                "evidence": evidence,
            }
        )

    timing_code = str(pattern.get("timing_code") or "").strip()
    semantic = semantics_by_code.get(timing_code)
    if semantic and semantic.get("use_as") == "Review":
        semantic.update(
            {
                "bucket": "not_used",
                "use_as": "Trial timing",
                "reason": "Count matches candidate label group",
                "evidence": "Matches class total",
            }
        )


def _repeated_event_group_pattern(
    aggregates: dict[str, dict[str, Any]],
    semantics_by_code: dict[str, dict[str, str]],
    file_names: list[str],
) -> dict[str, Any]:
    total_files = len(file_names)
    if total_files <= 0:
        return {}

    groups: dict[int, list[str]] = {}
    for code, stats in aggregates.items():
        semantic = semantics_by_code.get(code, {})
        if not _eligible_for_count_pattern(stats, semantic, total_files):
            continue
        nonzero_count = _stable_nonzero_count(stats)
        if nonzero_count:
            groups.setdefault(nonzero_count, []).append(code)

    candidates = [
        (count, sorted(codes, key=_event_code_sort_value))
        for count, codes in groups.items()
        if _PATTERN_MIN_LABEL_CODES <= len(codes) <= _PATTERN_MAX_LABEL_CODES
    ]
    if not candidates:
        return {}

    candidate_count, candidate_codes = max(
        candidates,
        key=lambda item: (len(item[1]), item[0]),
    )
    timing_code = _timing_code_for_candidate_group(
        aggregates,
        candidate_codes,
        file_names,
    )
    return {
        "candidate_codes": candidate_codes,
        "candidate_count": candidate_count,
        "timing_code": timing_code,
    }


def _eligible_for_count_pattern(
    stats: dict[str, Any],
    semantic: dict[str, str],
    total_files: int,
) -> bool:
    if semantic.get("bucket") == "candidate":
        return False
    if semantic.get("use_as") != "Review":
        return False
    stable_count = _stable_nonzero_count(stats)
    if stable_count < _PATTERN_MIN_COUNT_PER_FILE:
        return False
    present_files = len(stats.get("file_counts", {}) or {})
    return present_files >= max(total_files - 1, 1)


def _stable_nonzero_count(stats: dict[str, Any]) -> int:
    counts = [
        int(value)
        for value in (stats.get("file_counts", {}) or {}).values()
        if isinstance(value, int) and value > 0
    ]
    if not counts or len(set(counts)) != 1:
        return 0
    return counts[0]


def _timing_code_for_candidate_group(
    aggregates: dict[str, dict[str, Any]],
    candidate_codes: list[str],
    file_names: list[str],
) -> str:
    expected_counts = {
        file_name: sum(
            int(
                (aggregates.get(code, {}).get("file_counts", {}) or {}).get(
                    file_name,
                    0,
                )
            )
            for code in candidate_codes
        )
        for file_name in file_names
    }
    if not any(expected_counts.values()):
        return ""
    for code, stats in sorted(
        aggregates.items(),
        key=lambda item: _event_sort_key(item[1]),
    ):
        if code in candidate_codes:
            continue
        file_counts = stats.get("file_counts", {}) or {}
        if all(
            int(file_counts.get(file_name, 0)) == expected
            for file_name, expected in expected_counts.items()
        ):
            return code
    return ""


def _preview_row(
    stats: dict[str, Any],
    semantic: dict[str, str],
    file_names: list[str],
) -> dict[str, Any]:
    file_counts = {
        str(key): int(value)
        for key, value in sorted(
            stats["file_counts"].items(),
            key=lambda item: item[0].casefold(),
        )
    }
    present_files = len(file_counts)
    total_files = len(file_names)
    missing_files = [name for name in file_names if name not in file_counts]
    row: dict[str, Any] = {
        "event_code": str(stats["code"]),
        "code": str(stats["code"]),
        "use_as": semantic["use_as"],
        "event_count": int(stats["total_count"]),
        "coverage": f"{present_files}/{total_files} files",
        "present_files": present_files,
        "total_files": total_files,
        "missing_files": missing_files,
        "file_counts": file_counts,
        "evidence": _evidence_text(semantic["evidence"], file_counts, missing_files),
    }
    if semantic.get("reason"):
        row["reason"] = semantic["reason"]
    if semantic.get("class_name"):
        row["class_name"] = semantic["class_name"]
    return row


def _evidence_text(
    base: str,
    file_counts: dict[str, int],
    missing_files: list[str],
) -> str:
    details: list[str] = []
    counts = list(file_counts.values())
    if len(counts) > 1 and len(set(counts)) == 1:
        details.append("same count/file")
    elif len(counts) > 1:
        details.append("count varies/file")
    if missing_files:
        details.append("missing " + ", ".join(missing_files))
    return "; ".join([base, *details])


def _names_reliable(candidate_rows: list[dict[str, Any]]) -> bool:
    if not candidate_rows:
        return False
    return all(str(row.get("class_name") or "").strip() for row in candidate_rows)


def _pattern_status(
    candidate_rows: list[dict[str, Any]],
    not_used_rows: list[dict[str, Any]],
) -> str:
    if candidate_rows:
        return "Suggested label events found"
    if not_used_rows:
        return "Internal events found; choose labels"
    return "No internal events detected"


def _has_run_dependent_t_markers(aggregates: dict[str, dict[str, Any]]) -> bool:
    codes = {str(code).upper() for code in aggregates}
    return {"T1", "T2"}.issubset(codes)


def _run_dependent_mapping(
    event_files: list[str],
    file_names: list[str],
    event_codes: list[str],
) -> dict[str, Any]:
    t_codes = [code for code in event_codes if str(code).upper() in {"T1", "T2"}]
    return {
        "status": "needs_confirmation",
        "files": [
            {
                "file": file_name,
                "run": _run_token_for_file(file_path),
                "events": dict.fromkeys(t_codes, ""),
            }
            for file_path, file_name in zip(event_files, file_names, strict=True)
        ],
    }


def _run_token_for_file(path: str) -> str:
    stem = Path(path).stem
    match = re.search(r"R(\d+)(?:[_-]|$)", stem, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"(?:^|[_-])run-?(\d+)(?:[_-]|$)", stem, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def _class_like_description(descriptions: Iterable[str]) -> str:
    for description in sorted(descriptions, key=str.casefold):
        text = " ".join(str(description).strip().split())
        if not text or text.isdigit() or _looks_like_coded_marker(text):
            continue
        normalized = text.casefold()
        if any(token in normalized for token in _CLASS_LIKE_TOKENS):
            return text
    return ""


def _description_has_any(descriptions: Iterable[str], tokens: Iterable[str]) -> bool:
    token_tuple = tuple(token.casefold() for token in tokens)
    return any(
        any(token in str(description).casefold() for token in token_tuple)
        for description in descriptions
    )


def _positive_int(value: Any) -> int:
    if isinstance(value, int):
        return value if value > 0 else 0
    text = str(value or "").strip()
    if text.isdigit():
        parsed = int(text)
        return parsed if parsed > 0 else 0
    return 0


def _has_internal_event_extension(path: str) -> bool:
    lower = str(path).lower()
    return any(lower.endswith(extension) for extension in INTERNAL_EVENT_EXTENSIONS)


def _file_suffix(path: str) -> str:
    lower = str(path).lower()
    if lower.endswith(".fif.gz"):
        return ".fif.gz"
    return Path(lower).suffix


def _event_sort_key(item: dict[str, Any]) -> tuple[int, int | str]:
    code = str(item.get("code") or item.get("event_code") or "").strip()
    return _event_code_sort_value(code)


def _event_code_sort_value(code: str) -> tuple[int, int | str]:
    code = str(code).strip()
    return (0, int(code)) if code.isdigit() else (1, code.casefold())


def _scan_warning(file_path: str, exc: Exception) -> str:
    return (
        "Could not inspect internal EEG events for "
        f"{Path(file_path).name}: {type(exc).__name__}: {exc}"
    )
