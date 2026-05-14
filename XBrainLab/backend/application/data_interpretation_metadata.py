"""Metadata resolution helpers for Data Interpretation sources."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any, cast

SAFE = "safe"
NEEDS_CONFIRMATION = "needs_confirmation"


@dataclass(frozen=True)
class MetadataFieldResolution:
    """Resolved value and provenance for one metadata field."""

    field: str
    value: str | None
    source: str
    decision: str
    reason: str
    override: str | None = None
    recipe_trace: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FileMetadataResolution:
    """Subject/session/task/run metadata preview for one source file."""

    file: str
    subject: MetadataFieldResolution
    session: MetadataFieldResolution
    task: MetadataFieldResolution
    run: MetadataFieldResolution

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def metadata_for_file(
    path: Path,
    scan_root: Path,
    source_kind: str,
) -> FileMetadataResolution:
    """Resolve subject/session/task/run metadata for one EEG source file."""
    rel_text = relative_text(path, scan_root)
    is_bids = source_kind == "bids" or "sub-" in rel_text
    return FileMetadataResolution(
        file=str(path),
        subject=field_resolution("subject", path, rel_text, is_bids),
        session=field_resolution("session", path, rel_text, is_bids),
        task=field_resolution("task", path, rel_text, is_bids),
        run=field_resolution("run", path, rel_text, is_bids),
    )


def field_resolution(
    field_name: str,
    path: Path,
    rel_text: str,
    is_bids: bool,
) -> MetadataFieldResolution:
    """Resolve one metadata field from BIDS entities or filename rules."""
    bids_key = {
        "subject": "sub",
        "session": "ses",
        "task": "task",
        "run": "run",
    }[field_name]
    value = extract_bids_entity(rel_text, bids_key)
    if value is not None:
        return MetadataFieldResolution(
            field=field_name,
            value=value,
            source="bids_entity",
            decision=SAFE,
            reason=f"{field_name} resolved from BIDS entity.",
            recipe_trace=[f"bids:{bids_key}"],
        )

    value = extract_filename_metadata(path.name, field_name)
    if value is not None:
        return MetadataFieldResolution(
            field=field_name,
            value=value,
            source="filename_rule",
            decision=NEEDS_CONFIRMATION,
            reason=f"{field_name} inferred from filename and should be confirmed.",
            recipe_trace=[f"filename:{field_name}"],
        )

    reason = (
        f"{field_name} was not inferred from source path."
        if not is_bids
        else f"{field_name} BIDS entity is not present for this file."
    )
    return MetadataFieldResolution(
        field=field_name,
        value=None,
        source="missing",
        decision=NEEDS_CONFIRMATION,
        reason=reason,
        recipe_trace=[],
    )


def bids_summary(
    scan_root: Path,
    source_kind: str,
    eeg_files: list[str],
    label_carriers: list[str],
) -> dict[str, Any]:
    """Summarize BIDS entities discovered during source scan."""
    bids_root = resolve_bids_root(scan_root)
    events_files = [
        item for item in label_carriers if item.endswith(("_events.tsv", "events.tsv"))
    ]
    dataset_description = bids_root / "dataset_description.json"
    layout = bids_eeg_layout(
        bids_root=bids_root,
        eeg_files=eeg_files,
        events_files=events_files,
    )
    participants_file = bids_root / "participants.tsv"
    participants = _read_tsv_rows(participants_file)
    channels_files = _unique_paths(
        row.get("channels_file") for row in layout if row.get("channels_file")
    )
    return {
        "is_bids": source_kind == "bids",
        "root": str(bids_root),
        "scan_location": str(scan_root),
        "subjects": bids_entity_values(eeg_files, bids_root, "sub"),
        "sessions": bids_entity_values(eeg_files, bids_root, "ses"),
        "tasks": bids_entity_values(eeg_files, bids_root, "task"),
        "runs": bids_entity_values(eeg_files, bids_root, "run"),
        "datatypes": _unique_strings(row.get("datatype") for row in layout),
        "eeg_file_count": len(eeg_files),
        "events_files": events_files,
        "channels_files": channels_files,
        "participants_file": (
            str(participants_file) if participants_file.exists() else None
        ),
        "participant_count": len(participants),
        "participants": participants,
        "channel_status_summary": _channel_status_summary(channels_files),
        "layout": layout,
        "selected_scope": bids_scope_summary(eeg_files, layout),
        "dataset_description": str(dataset_description)
        if dataset_description.exists()
        else None,
        "dataset": _read_json_object(dataset_description),
    }


def resolve_bids_root(scan_root: Path) -> Path:
    """Return the nearest ancestor that owns ``dataset_description.json``."""
    root = scan_root.resolve()
    if root.is_file():
        root = root.parent
    for candidate in [root, *root.parents]:
        if (candidate / "dataset_description.json").exists():
            return candidate
    return root


def bids_eeg_layout(
    *,
    bids_root: Path,
    eeg_files: list[str],
    events_files: list[str],
) -> list[dict[str, Any]]:
    """Return per-raw-file BIDS EEG layout rows with effective local sidecars."""
    events_by_name = {
        Path(item).name: str(Path(item).resolve()) for item in events_files
    }
    rows: list[dict[str, Any]] = []
    for file_path in sorted(eeg_files):
        path = Path(file_path).resolve()
        rel = relative_text(path, bids_root)
        datatype = _bids_datatype(rel)
        stem = _bids_raw_stem(path)
        events_file = events_by_name.get(f"{stem}_events.tsv")
        if events_file is None:
            candidate = path.with_name(f"{stem}_events.tsv")
            events_file = str(candidate) if candidate.exists() else ""
        channels_file = path.with_name(f"{stem}_channels.tsv")
        rows.append(
            {
                "file": str(path),
                "name": path.name,
                "relative_path": rel,
                "subject": extract_bids_entity(rel, "sub") or "",
                "session": extract_bids_entity(rel, "ses") or "",
                "task": extract_bids_entity(rel, "task") or "",
                "run": extract_bids_entity(rel, "run") or "",
                "datatype": datatype,
                "events_file": events_file,
                "channels_file": str(channels_file) if channels_file.exists() else "",
            }
        )
    return rows


def bids_scope_summary(
    selected_eeg_files: list[str],
    layout: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize BIDS entities and sidecars for the selected EEG scope."""
    selected = {str(Path(item).resolve()) for item in selected_eeg_files}
    rows = [row for row in layout if str(row.get("file")) in selected]
    return {
        "eeg_file_count": len(rows),
        "subjects": _unique_strings(row.get("subject") for row in rows),
        "sessions": _unique_strings(row.get("session") for row in rows),
        "tasks": _unique_strings(row.get("task") for row in rows),
        "runs": _unique_strings(row.get("run") for row in rows),
        "datatypes": _unique_strings(row.get("datatype") for row in rows),
        "eeg_files": [str(row.get("file")) for row in rows if row.get("file")],
        "events_files": _unique_paths(
            row.get("events_file") for row in rows if row.get("events_file")
        ),
        "channels_files": _unique_paths(
            row.get("channels_file") for row in rows if row.get("channels_file")
        ),
    }


def bids_entity_values(
    eeg_files: list[str],
    scan_root: Path,
    entity: str,
) -> list[str]:
    """Return sorted unique values for one BIDS entity in scanned EEG files."""
    values = {
        value
        for file_path in eeg_files
        if (
            value := extract_bids_entity(
                relative_text(Path(file_path), scan_root),
                entity,
            )
        )
    }
    return sorted(values)


def _bids_datatype(rel_text: str) -> str:
    parts = [part for part in rel_text.split("/") if part]
    for part in parts:
        if part in {"eeg", "ieeg", "meg"}:
            return part
    return ""


def _bids_raw_stem(path: Path) -> str:
    name = path.name
    stem = name[: -len(".fif.gz")] if name.lower().endswith(".fif.gz") else path.stem
    for suffix in ("_eeg", "_raw"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _read_tsv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            return [
                {str(key): str(value or "") for key, value in row.items() if key}
                for row in reader
            ]
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _channel_status_summary(channels_files: list[str]) -> dict[str, int]:
    summary = {"total": 0, "good": 0, "bad": 0, "other": 0}
    for file_path in channels_files:
        for row in _read_tsv_rows(Path(file_path)):
            summary["total"] += 1
            status = str(row.get("status") or "").strip().lower()
            if status == "good":
                summary["good"] += 1
            elif status == "bad":
                summary["bad"] += 1
            else:
                summary["other"] += 1
    return summary


def _unique_paths(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        normalized = str(Path(text).resolve())
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _unique_strings(values: Iterable[Any]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def extract_bids_entity(text: str, entity: str) -> str | None:
    """Extract a BIDS entity value from a relative path string."""
    match = re.search(rf"(?:^|[/_]){entity}-([A-Za-z0-9]+)", text)
    return match.group(1) if match else None


def extract_filename_metadata(filename: str, field_name: str) -> str | None:
    """Infer metadata from conservative non-BIDS filename patterns."""
    patterns = {
        "subject": [
            r"(?:^|[_-])sub(?:ject)?[_-]?([A-Za-z0-9]+)",
            r"(?:^|[_-])s([0-9]{1,3})(?:[_-]|$)",
        ],
        "session": [
            r"(?:^|[_-])ses(?:sion)?[_-]?([A-Za-z0-9]+)",
        ],
        "task": [
            r"(?:^|[_-])task[_-]?([A-Za-z0-9]+)",
        ],
        "run": [
            r"(?:^|[_-])run[_-]?([A-Za-z0-9]+)",
            r"(?:^|[_-])r([0-9]{1,3})(?:[_-]|$)",
        ],
    }
    normalized = Path(filename).stem
    for pattern in patterns[field_name]:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def relative_text(path: Path, root: Path) -> str:
    """Return POSIX-style path text relative to scan root when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def file_metadata_from_dict(payload: dict[str, Any]) -> FileMetadataResolution:
    """Build file metadata resolution from serialized recipe payload."""
    return FileMetadataResolution(
        file=str(payload.get("file", "")),
        subject=field_from_dict(
            cast(dict[str, Any], payload.get("subject", {})),
            "subject",
        ),
        session=field_from_dict(
            cast(dict[str, Any], payload.get("session", {})),
            "session",
        ),
        task=field_from_dict(cast(dict[str, Any], payload.get("task", {})), "task"),
        run=field_from_dict(cast(dict[str, Any], payload.get("run", {})), "run"),
    )


def field_from_dict(
    payload: dict[str, Any],
    field_name: str,
) -> MetadataFieldResolution:
    """Build one metadata-field resolution from serialized recipe payload."""
    return MetadataFieldResolution(
        field=str(payload.get("field", field_name)),
        value=payload.get("value"),
        source=str(payload.get("source", "unknown")),
        decision=str(payload.get("decision", NEEDS_CONFIRMATION)),
        reason=str(payload.get("reason", "")),
        override=payload.get("override"),
        recipe_trace=[str(item) for item in payload.get("recipe_trace", [])],
    )
