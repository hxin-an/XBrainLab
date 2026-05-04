"""Metadata resolution helpers for Data Interpretation sources."""

from __future__ import annotations

import re
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
    events_files = [
        item for item in label_carriers if item.endswith(("_events.tsv", "events.tsv"))
    ]
    dataset_description = scan_root / "dataset_description.json"
    return {
        "is_bids": source_kind == "bids",
        "subjects": bids_entity_values(eeg_files, scan_root, "sub"),
        "sessions": bids_entity_values(eeg_files, scan_root, "ses"),
        "tasks": bids_entity_values(eeg_files, scan_root, "task"),
        "runs": bids_entity_values(eeg_files, scan_root, "run"),
        "events_files": events_files,
        "dataset_description": str(dataset_description)
        if dataset_description.exists()
        else None,
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
