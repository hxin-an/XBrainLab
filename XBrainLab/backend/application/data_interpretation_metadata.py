"""Metadata resolution helpers for Data Interpretation sources."""

from __future__ import annotations

import csv
import json
import os
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any, cast

SAFE = "safe"
NEEDS_CONFIRMATION = "needs_confirmation"
BIDS_METADATA_READ_BUDGET_BYTES = 1_048_576
DATASET_DESCRIPTION_MAX_BYTES = BIDS_METADATA_READ_BUDGET_BYTES


@dataclass
class BidsMetadataReadBudget:
    """Bound aggregate dataset-description reads after resource admission."""

    limit_bytes: int = BIDS_METADATA_READ_BUDGET_BYTES
    bytes_read: int = 0
    exhausted: bool = False

    @property
    def remaining_bytes(self) -> int:
        return max(self.limit_bytes - self.bytes_read, 0)

    def read(self, path: Path) -> tuple[bytes | None, str]:
        """Read one admitted file without exceeding the aggregate byte cap."""
        try:
            with path.open("rb") as handle:
                file_bytes = max(int(os.fstat(handle.fileno()).st_size), 0)
                if file_bytes > self.remaining_bytes:
                    self.exhausted = True
                    return None, (
                        f"{path.name} exceeds the bounded discovery limit of "
                        f"{self.limit_bytes} bytes (the shared BIDS metadata byte "
                        "budget)."
                    )
                encoded = handle.read(file_bytes)
        except OSError:
            return None, f"{path.name} could not be read."
        self.bytes_read += len(encoded)
        if len(encoded) != file_bytes:
            return None, f"{path.name} could not be read completely."
        return encoded, ""

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "budget_bytes": self.limit_bytes,
            "bytes_read": self.bytes_read,
            "budget_exhausted": self.exhausted,
        }


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
    *,
    materialize: bool = True,
    layout: list[dict[str, Any]] | None = None,
    discovered_files: Iterable[str | Path] | None = None,
    admitted_metadata_files: Iterable[str] | None = None,
    metadata_read_budget: BidsMetadataReadBudget | None = None,
) -> dict[str, Any]:
    """Summarize BIDS entities discovered during source scan."""
    discovered_values = None if discovered_files is None else list(discovered_files)
    discovered = _canonical_path_keys(discovered_values)
    admitted = _canonical_path_keys(admitted_metadata_files)
    available_metadata = _intersect_path_scopes(discovered, admitted)
    containment_root = scan_root.expanduser().resolve(strict=False)
    if containment_root.is_file():
        containment_root = containment_root.parent
    bids_root = resolve_bids_root(
        scan_root,
        admitted_files=available_metadata,
        containment_root=containment_root,
    )
    events_files = [
        item for item in label_carriers if item.endswith(("_events.tsv", "events.tsv"))
    ]
    dataset_description_candidate = bids_root / "dataset_description.json"
    dataset_description = _available_regular_file(
        dataset_description_candidate,
        available_metadata,
        containment_root=containment_root,
    )
    layout = (
        [dict(row) for row in layout]
        if layout is not None
        else bids_eeg_layout(
            bids_root=bids_root,
            eeg_files=eeg_files,
            events_files=events_files,
            admitted_files=discovered_values,
            containment_root=containment_root,
        )
    )
    layout = _restrict_bids_layout_to_admitted_files(
        layout,
        events_files=events_files,
        admitted_metadata=available_metadata,
        containment_root=containment_root,
    )
    participants_file = _available_regular_file(
        bids_root / "participants.tsv",
        available_metadata,
        containment_root=containment_root,
    )
    channels_files = _unique_paths(
        row.get("channels_file") for row in layout if row.get("channels_file")
    )

    def _is_admitted(path: Path) -> bool:
        return admitted is None or _canonical_path_key(path) in admitted

    participants = (
        _read_tsv_rows(participants_file)
        if materialize
        and participants_file is not None
        and _is_admitted(participants_file)
        else []
    )
    admitted_channels = [item for item in channels_files if _is_admitted(Path(item))]
    read_budget = metadata_read_budget or BidsMetadataReadBudget()
    if (
        materialize
        and dataset_description is not None
        and _is_admitted(dataset_description)
    ):
        dataset, root_validation_issue = _read_bids_dataset_description(
            dataset_description,
            read_budget,
        )
    elif materialize:
        dataset = {}
        root_validation_issue = (
            "dataset_description.json is missing from the selected BIDS root."
        )
    else:
        dataset = {}
        root_validation_issue = ""
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
        "participants_file": str(participants_file) if participants_file else None,
        "participant_count": len(participants),
        "participants": participants,
        "metadata_materialized": materialize,
        "channel_status_summary": (
            _channel_status_summary(admitted_channels)
            if materialize
            else {"total": 0, "good": 0, "bad": 0, "other": 0}
        ),
        "layout": layout,
        "selected_scope": bids_scope_summary(eeg_files, layout),
        "dataset_description": (
            str(dataset_description) if dataset_description is not None else None
        ),
        "dataset": dataset,
        "root_validation_issue": root_validation_issue,
        "metadata_read_budget": read_budget.to_diagnostics(),
    }


def bids_metadata_resource_paths(summary: dict[str, Any]) -> list[str]:
    """Return files that ``bids_summary`` may fully materialize."""
    return _unique_paths(
        [
            summary.get("dataset_description"),
            summary.get("participants_file"),
            *(summary.get("channels_files") or []),
        ],
    )


def resolve_bids_root(
    scan_root: Path,
    *,
    admitted_files: set[str] | None = None,
    containment_root: Path | None = None,
) -> Path:
    """Return the nearest ancestor that owns ``dataset_description.json``."""
    root = scan_root.resolve()
    if root.is_file():
        root = root.parent
    for candidate in [root, *root.parents]:
        if (
            _available_regular_file(
                candidate / "dataset_description.json",
                admitted_files,
                containment_root=containment_root,
            )
            is not None
        ):
            return candidate
    return root


def bids_eeg_layout(
    *,
    bids_root: Path,
    eeg_files: list[str],
    events_files: list[str],
    admitted_files: Iterable[str | Path] | None = None,
    containment_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Return per-raw-file BIDS EEG layout rows with effective local sidecars."""
    admitted = _canonical_path_keys(admitted_files)
    events_by_name = {
        Path(item).name: str(Path(item).resolve())
        for item in events_files
        if admitted is None or _canonical_path_key(Path(item)) in admitted
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
            admitted_candidate = _available_regular_file(
                candidate,
                admitted,
                containment_root=containment_root,
            )
            events_file = (
                str(admitted_candidate) if admitted_candidate is not None else ""
            )
        channels_file = _available_regular_file(
            path.with_name(f"{stem}_channels.tsv"),
            admitted,
            containment_root=containment_root,
        )
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
                "channels_file": (
                    str(channels_file) if channels_file is not None else ""
                ),
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
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            return [
                {str(key): str(value or "") for key, value in row.items() if key}
                for row in reader
            ]
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def _read_bids_dataset_description(
    path: Path,
    budget: BidsMetadataReadBudget,
) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "dataset_description.json is missing from the selected BIDS root."
    encoded, read_issue = budget.read(path)
    if encoded is None:
        return {}, read_issue
    try:
        payload = json.loads(encoded.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}, "dataset_description.json is not valid JSON."
    if not isinstance(payload, dict):
        return {}, "dataset_description.json must contain a JSON object."
    missing_fields = [
        field_name
        for field_name in ("Name", "BIDSVersion")
        if not str(payload.get(field_name) or "").strip()
    ]
    if missing_fields:
        return (
            payload,
            "dataset_description.json is missing required field(s): "
            + ", ".join(missing_fields)
            + ".",
        )
    return payload, ""


def _read_json_object(path: Path) -> dict[str, Any]:
    """Compatibility wrapper for one bounded dataset-description read."""
    payload, _issue = _read_bids_dataset_description(
        path,
        BidsMetadataReadBudget(),
    )
    return payload


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


def _canonical_path_key(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _canonical_path_keys(
    values: Iterable[str | Path] | None,
) -> set[str] | None:
    if values is None:
        return None
    return {_canonical_path_key(Path(value)) for value in values}


def _intersect_path_scopes(*scopes: set[str] | None) -> set[str] | None:
    active = [scope for scope in scopes if scope is not None]
    if not active:
        return None
    result = set(active[0])
    for scope in active[1:]:
        result.intersection_update(scope)
    return result


def _available_regular_file(
    path: Path,
    admitted: set[str] | None,
    *,
    containment_root: Path | None = None,
) -> Path | None:
    if containment_root is not None:
        try:
            path.relative_to(containment_root)
        except ValueError:
            return None
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if containment_root is not None:
        try:
            resolved.relative_to(containment_root)
        except ValueError:
            return None
    if admitted is not None and _canonical_path_key(resolved) not in admitted:
        return None
    return resolved if resolved.is_file() else None


def _restrict_bids_layout_to_admitted_files(
    layout: list[dict[str, Any]],
    *,
    events_files: list[str],
    admitted_metadata: set[str] | None,
    containment_root: Path,
) -> list[dict[str, Any]]:
    admitted_events = _canonical_path_keys(events_files) or set()
    result: list[dict[str, Any]] = []
    for source_row in layout:
        row = dict(source_row)
        events_file = str(row.get("events_file") or "")
        if admitted_metadata is not None and (
            events_file
            and _canonical_path_key(Path(events_file)) not in admitted_events
        ):
            row["events_file"] = ""
        channels_file = str(row.get("channels_file") or "")
        if channels_file:
            admitted_channel = _available_regular_file(
                Path(channels_file),
                admitted_metadata,
                containment_root=containment_root,
            )
            row["channels_file"] = (
                str(admitted_channel) if admitted_channel is not None else ""
            )
        result.append(row)
    return result


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
