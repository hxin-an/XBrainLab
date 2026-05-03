"""Data interpretation lifecycle objects for the application command layer."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from enum import Enum
from pathlib import Path
from typing import Any, cast

SUPPORTED_EEG_EXTENSIONS = (
    ".set",
    ".gdf",
    ".fif",
    ".fif.gz",
    ".edf",
    ".bdf",
    ".cnt",
    ".vhdr",
)
LABEL_CARRIER_EXTENSIONS = (".mat", ".txt", ".csv", ".tsv")


class InterpretationDecision(str, Enum):
    """Reviewable validation decisions for a data interpretation."""

    SAFE = "safe"
    NEEDS_CONFIRMATION = "needs_confirmation"
    BLOCKED = "blocked"


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
        return _serialize(self)


@dataclass(frozen=True)
class FileMetadataResolution:
    """Subject/session/task/run metadata preview for one source file."""

    file: str
    subject: MetadataFieldResolution
    session: MetadataFieldResolution
    task: MetadataFieldResolution
    run: MetadataFieldResolution


@dataclass(frozen=True)
class ScanResult:
    """Files, label carriers, and metadata discovered from a source path."""

    scan_id: str
    source_path: str
    source_hint: str = "auto"
    source_kind: str = "unknown"
    eeg_files: list[str] = dc_field(default_factory=list)
    label_carriers: list[str] = dc_field(default_factory=list)
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    bids: dict[str, Any] = dc_field(default_factory=dict)
    warnings: list[str] = dc_field(default_factory=list)
    blocked_reasons: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(frozen=True)
class InterpretationCandidate:
    """Candidate data interpretation built from a scan result."""

    candidate_id: str
    scan_id: str
    source_path: str
    source_kind: str
    selected_eeg_files: list[str] = dc_field(default_factory=list)
    label_carriers: list[str] = dc_field(default_factory=list)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)
    time_model: str = "unknown"
    granularity: str = "unknown"
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    confirmation_items: list[str] = dc_field(default_factory=list)
    blocked_reasons: list[str] = dc_field(default_factory=list)
    choices: dict[str, Any] = dc_field(default_factory=dict)
    recipe_trace: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(frozen=True)
class InterpretationPreview:
    """Human- and agent-readable preview of an interpretation candidate."""

    preview_id: str
    candidate_id: str
    summary: str
    file_count: int
    label_carrier_count: int
    metadata_preview: list[dict[str, Any]] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    confirmation_items: list[str] = dc_field(default_factory=list)
    blocked_reasons: list[str] = dc_field(default_factory=list)
    downstream_impacts: list[str] = dc_field(default_factory=list)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(frozen=True)
class ValidationDecision:
    """Validation result for an interpretation candidate."""

    candidate_id: str
    decision: str
    reasons: list[str] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    required_confirmations: list[str] = dc_field(default_factory=list)
    blocked_reasons: list[str] = dc_field(default_factory=list)
    downstream_impacts: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(frozen=True)
class AppliedInterpretation:
    """Applied data interpretation that becomes downstream workflow truth."""

    interpretation_id: str
    candidate_id: str
    source_path: str
    source_kind: str
    loaded_files: list[str] = dc_field(default_factory=list)
    label_carriers: list[str] = dc_field(default_factory=list)
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    validation_decision: str = InterpretationDecision.SAFE.value
    confirmations: list[str] = dc_field(default_factory=list)
    recipe_trace: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(frozen=True)
class ImportRecipe:
    """Serializable recipe for replaying a data interpretation."""

    recipe_id: str
    interpretation_id: str
    source_path: str
    source_kind: str
    selected_eeg_files: list[str] = dc_field(default_factory=list)
    label_carriers: list[str] = dc_field(default_factory=list)
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    validation_decision: str = InterpretationDecision.SAFE.value
    confirmations: list[str] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    recipe_trace: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)

    def write_json(self, path: str) -> None:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )


def load_import_recipe(path: str) -> ImportRecipe:
    """Load an import recipe from a JSON file."""
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    return import_recipe_from_dict(payload)


def import_recipe_from_dict(payload: dict[str, Any]) -> ImportRecipe:
    """Build an :class:`ImportRecipe` from a serialized payload."""
    metadata = [
        _file_metadata_from_dict(item)
        for item in cast(list[dict[str, Any]], payload.get("metadata", []))
    ]
    return ImportRecipe(
        recipe_id=str(payload.get("recipe_id", "recipe-reloaded")),
        interpretation_id=str(payload.get("interpretation_id", "")),
        source_path=str(payload.get("source_path", "")),
        source_kind=str(payload.get("source_kind", "unknown")),
        selected_eeg_files=[
            str(item) for item in payload.get("selected_eeg_files", [])
        ],
        label_carriers=[str(item) for item in payload.get("label_carriers", [])],
        metadata=metadata,
        validation_decision=str(
            payload.get("validation_decision", InterpretationDecision.SAFE.value),
        ),
        confirmations=[str(item) for item in payload.get("confirmations", [])],
        warnings=[str(item) for item in payload.get("warnings", [])],
        recipe_trace=[str(item) for item in payload.get("recipe_trace", [])],
    )


def scan_source_path(
    *,
    scan_id: str,
    source_path: str,
    source_hint: str = "auto",
) -> ScanResult:
    """Scan a file, folder, BIDS root, device export, or recipe path."""
    if not str(source_path).strip():
        raise ValueError("source_path is required.")

    path = Path(source_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Source path does not exist: {source_path}")
    resolved = path.resolve()
    source_kind = _source_kind(resolved, source_hint)
    scan_root = resolved.parent if resolved.is_file() else resolved
    files = _candidate_files(resolved)
    eeg_files = sorted(
        str(item)
        for item in files
        if _has_supported_suffix(item, SUPPORTED_EEG_EXTENSIONS)
    )
    label_carriers = sorted(
        str(item)
        for item in files
        if _is_label_carrier(item) or _is_bids_events_file(item)
    )
    metadata = [
        _metadata_for_file(Path(file_path), scan_root, source_kind)
        for file_path in eeg_files
    ]
    bids = _bids_summary(scan_root, source_kind, eeg_files, label_carriers)
    warnings = _scan_warnings(source_kind, eeg_files, label_carriers, bids)
    blocked_reasons = [] if eeg_files else ["No supported EEG data files were found."]

    return ScanResult(
        scan_id=scan_id,
        source_path=str(resolved),
        source_hint=source_hint,
        source_kind=source_kind,
        eeg_files=eeg_files,
        label_carriers=label_carriers,
        metadata=metadata,
        bids=bids,
        warnings=warnings,
        blocked_reasons=blocked_reasons,
    )


def build_interpretation_candidate(
    *,
    candidate_id: str,
    scan: ScanResult,
    choices: dict[str, Any] | None = None,
) -> InterpretationCandidate:
    """Build a candidate interpretation from a scan result and user choices."""
    choices = dict(choices or {})
    selected_files = [
        str(item)
        for item in choices.get("eeg_files", choices.get("selected_eeg_files", []))
    ] or list(scan.eeg_files)
    blocked_reasons = list(scan.blocked_reasons)
    warnings = list(scan.warnings)
    confirmation_items: list[str] = []
    event_roles: dict[str, str] = {}
    class_map: dict[str, str] = {}

    if scan.label_carriers:
        event_roles["label_carrier"] = "external label or event source"
        confirmation_items.append(
            "Confirm label carrier alignment, anchor event, and class map "
            "before applying.",
        )
    if scan.bids.get("is_bids"):
        event_roles.update(
            {
                "onset": "time anchor",
                "duration": "event duration",
                "trial_type": "class label candidate",
            },
        )
        if not scan.bids.get("events_files"):
            warnings.append("BIDS-like source has no events.tsv file.")
    else:
        extensions = {Path(item).suffix.lower() for item in selected_files}
        if extensions & {".gdf", ".edf", ".bdf", ".set", ".vhdr"}:
            event_roles["internal_events"] = "event role candidates"
            confirmation_items.append(
                "Confirm which events are trial anchors, class cues, responses, "
                "artifacts, or boundaries.",
            )

    for item in scan.metadata:
        fields = (item.subject, item.session, item.task, item.run)
        confirmation_items.extend(
            f"Confirm {field_value.field} metadata for {Path(item.file).name}."
            for field_value in fields
            if field_value.decision == InterpretationDecision.NEEDS_CONFIRMATION.value
        )

    confirmation_items = sorted(set(confirmation_items))
    if not selected_files:
        blocked_reasons.append("No EEG files were selected for interpretation.")

    return InterpretationCandidate(
        candidate_id=candidate_id,
        scan_id=scan.scan_id,
        source_path=scan.source_path,
        source_kind=scan.source_kind,
        selected_eeg_files=selected_files,
        label_carriers=list(scan.label_carriers),
        event_roles=event_roles,
        class_map=class_map,
        time_model="sample_index_or_annotation_time"
        if event_roles
        else "file_native_time",
        granularity="trial_or_event" if event_roles else "recording",
        metadata=list(scan.metadata),
        warnings=warnings,
        confirmation_items=confirmation_items,
        blocked_reasons=sorted(set(blocked_reasons)),
        choices=choices,
        recipe_trace=[
            f"scan:{scan.scan_id}",
            f"candidate:{candidate_id}",
        ],
    )


def build_interpretation_preview(
    *,
    preview_id: str,
    candidate: InterpretationCandidate,
) -> InterpretationPreview:
    """Create a UI/agent-friendly preview for a candidate interpretation."""
    file_count = len(candidate.selected_eeg_files)
    label_count = len(candidate.label_carriers)
    summary = (
        f"Found {file_count} EEG file(s) and {label_count} label/event carrier(s)."
    )
    metadata_preview = [
        {
            "file": Path(item.file).name,
            "subject": item.subject.to_dict()
            if hasattr(item.subject, "to_dict")
            else _serialize(item.subject),
            "session": _serialize(item.session),
            "task": _serialize(item.task),
            "run": _serialize(item.run),
        }
        for item in candidate.metadata
    ]
    return InterpretationPreview(
        preview_id=preview_id,
        candidate_id=candidate.candidate_id,
        summary=summary,
        file_count=file_count,
        label_carrier_count=label_count,
        metadata_preview=metadata_preview,
        warnings=list(candidate.warnings),
        confirmation_items=list(candidate.confirmation_items),
        blocked_reasons=list(candidate.blocked_reasons),
        downstream_impacts=[
            "Applying this interpretation will replace active raw data and "
            "invalidate downstream preprocessing, epochs, datasets, training, "
            "and saliency for the current session.",
        ],
        event_roles=dict(candidate.event_roles),
        class_map=dict(candidate.class_map),
    )


def validate_interpretation_candidate(
    candidate: InterpretationCandidate,
) -> ValidationDecision:
    """Validate a candidate using reviewable safe/confirm/blocked decisions."""
    if candidate.blocked_reasons:
        return ValidationDecision(
            candidate_id=candidate.candidate_id,
            decision=InterpretationDecision.BLOCKED.value,
            reasons=["Interpretation cannot be applied until blockers are resolved."],
            warnings=list(candidate.warnings),
            blocked_reasons=list(candidate.blocked_reasons),
            downstream_impacts=[
                "Preprocess, epoch, dataset, and training remain blocked.",
            ],
        )
    if candidate.confirmation_items:
        return ValidationDecision(
            candidate_id=candidate.candidate_id,
            decision=InterpretationDecision.NEEDS_CONFIRMATION.value,
            reasons=["Candidate has reviewable semantic choices."],
            warnings=list(candidate.warnings),
            required_confirmations=list(candidate.confirmation_items),
            downstream_impacts=[
                "Downstream workflow remains blocked until the interpretation "
                "is confirmed and applied.",
            ],
        )
    return ValidationDecision(
        candidate_id=candidate.candidate_id,
        decision=InterpretationDecision.SAFE.value,
        reasons=["Source files and required metadata are sufficient for apply."],
        warnings=list(candidate.warnings),
        downstream_impacts=[
            "Applied interpretation becomes the source truth for preprocessing, "
            "epoching, dataset generation, training, and saliency.",
        ],
    )


def build_import_recipe(
    *,
    recipe_id: str,
    applied: AppliedInterpretation,
    warnings: list[str],
) -> ImportRecipe:
    """Build a recipe from an applied interpretation."""
    return ImportRecipe(
        recipe_id=recipe_id,
        interpretation_id=applied.interpretation_id,
        source_path=applied.source_path,
        source_kind=applied.source_kind,
        selected_eeg_files=list(applied.loaded_files),
        label_carriers=list(applied.label_carriers),
        metadata=list(applied.metadata),
        validation_decision=applied.validation_decision,
        confirmations=list(applied.confirmations),
        warnings=list(warnings),
        recipe_trace=[*applied.recipe_trace, f"recipe:{recipe_id}"],
    )


def _source_kind(path: Path, source_hint: str) -> str:
    hint = str(source_hint or "auto").strip().lower()
    if hint in {"file", "folder", "bids", "device_export", "recipe"}:
        return hint
    if path.is_file() and path.suffix.lower() == ".json":
        return "recipe"
    if path.is_file():
        return "file"
    if _looks_like_bids(path):
        return "bids"
    return "folder"


def _candidate_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return [item for item in path.rglob("*") if item.is_file()]


def _has_supported_suffix(path: Path, suffixes: tuple[str, ...]) -> bool:
    normalized = str(path).lower()
    return any(normalized.endswith(suffix) for suffix in suffixes)


def _is_label_carrier(path: Path) -> bool:
    return _has_supported_suffix(path, LABEL_CARRIER_EXTENSIONS)


def _is_bids_events_file(path: Path) -> bool:
    return path.name.endswith("_events.tsv") or path.name == "events.tsv"


def _looks_like_bids(path: Path) -> bool:
    if not path.is_dir():
        return False
    if (path / "dataset_description.json").exists():
        return True
    return any(item.name.startswith("sub-") for item in path.iterdir())


def _metadata_for_file(
    path: Path,
    scan_root: Path,
    source_kind: str,
) -> FileMetadataResolution:
    rel_text = _relative_text(path, scan_root)
    is_bids = source_kind == "bids" or "sub-" in rel_text
    return FileMetadataResolution(
        file=str(path),
        subject=_field_resolution("subject", path, rel_text, is_bids),
        session=_field_resolution("session", path, rel_text, is_bids),
        task=_field_resolution("task", path, rel_text, is_bids),
        run=_field_resolution("run", path, rel_text, is_bids),
    )


def _field_resolution(
    field_name: str,
    path: Path,
    rel_text: str,
    is_bids: bool,
) -> MetadataFieldResolution:
    bids_key = {
        "subject": "sub",
        "session": "ses",
        "task": "task",
        "run": "run",
    }[field_name]
    value = _extract_bids_entity(rel_text, bids_key)
    if value is not None:
        return MetadataFieldResolution(
            field=field_name,
            value=value,
            source="bids_entity",
            decision=InterpretationDecision.SAFE.value,
            reason=f"{field_name} resolved from BIDS entity.",
            recipe_trace=[f"bids:{bids_key}"],
        )

    value = _extract_filename_metadata(path.name, field_name)
    if value is not None:
        return MetadataFieldResolution(
            field=field_name,
            value=value,
            source="filename_rule",
            decision=InterpretationDecision.NEEDS_CONFIRMATION.value,
            reason=f"{field_name} inferred from filename and should be confirmed.",
            recipe_trace=[f"filename:{field_name}"],
        )

    decision = (
        InterpretationDecision.NEEDS_CONFIRMATION.value
        if field_name in {"subject", "session", "task", "run"}
        else InterpretationDecision.SAFE.value
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
        decision=decision,
        reason=reason,
        recipe_trace=[],
    )


def _extract_bids_entity(text: str, entity: str) -> str | None:
    match = re.search(rf"(?:^|[/_]){entity}-([A-Za-z0-9]+)", text)
    return match.group(1) if match else None


def _extract_filename_metadata(filename: str, field_name: str) -> str | None:
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


def _bids_summary(
    scan_root: Path,
    source_kind: str,
    eeg_files: list[str],
    label_carriers: list[str],
) -> dict[str, Any]:
    is_bids = source_kind == "bids"
    subjects = _bids_entity_values(eeg_files, scan_root, "sub")
    sessions = _bids_entity_values(eeg_files, scan_root, "ses")
    tasks = _bids_entity_values(eeg_files, scan_root, "task")
    runs = _bids_entity_values(eeg_files, scan_root, "run")
    events_files = [
        item for item in label_carriers if item.endswith(("_events.tsv", "events.tsv"))
    ]
    return {
        "is_bids": is_bids,
        "subjects": subjects,
        "sessions": sessions,
        "tasks": tasks,
        "runs": runs,
        "events_files": events_files,
        "dataset_description": str(scan_root / "dataset_description.json")
        if (scan_root / "dataset_description.json").exists()
        else None,
    }


def _bids_entity_values(
    eeg_files: list[str],
    scan_root: Path,
    entity: str,
) -> list[str]:
    values = {
        value
        for file_path in eeg_files
        if (
            value := _extract_bids_entity(
                _relative_text(Path(file_path), scan_root),
                entity,
            )
        )
    }
    return sorted(values)


def _scan_warnings(
    source_kind: str,
    eeg_files: list[str],
    label_carriers: list[str],
    bids: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if len(eeg_files) > 1:
        warnings.append(
            "Multiple EEG files were discovered; subject/session/run mapping "
            "should be reviewed.",
        )
    if label_carriers:
        warnings.append("External label/event carriers require preview before apply.")
    if source_kind == "bids" and not bids.get("events_files"):
        warnings.append(
            "BIDS-like source has no events.tsv carrier; supervised labels "
            "may be limited.",
        )
    return warnings


def _relative_text(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _file_metadata_from_dict(payload: dict[str, Any]) -> FileMetadataResolution:
    return FileMetadataResolution(
        file=str(payload.get("file", "")),
        subject=_field_from_dict(
            cast(dict[str, Any], payload.get("subject", {})),
            "subject",
        ),
        session=_field_from_dict(
            cast(dict[str, Any], payload.get("session", {})),
            "session",
        ),
        task=_field_from_dict(cast(dict[str, Any], payload.get("task", {})), "task"),
        run=_field_from_dict(cast(dict[str, Any], payload.get("run", {})), "run"),
    )


def _field_from_dict(
    payload: dict[str, Any],
    field_name: str,
) -> MetadataFieldResolution:
    return MetadataFieldResolution(
        field=str(payload.get("field", field_name)),
        value=payload.get("value"),
        source=str(payload.get("source", "unknown")),
        decision=str(
            payload.get(
                "decision",
                InterpretationDecision.NEEDS_CONFIRMATION.value,
            ),
        ),
        reason=str(payload.get("reason", "")),
        override=payload.get("override"),
        recipe_trace=[str(item) for item in payload.get("recipe_trace", [])],
    )


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: _serialize(v) for k, v in asdict(cast(Any, value)).items()}
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value
