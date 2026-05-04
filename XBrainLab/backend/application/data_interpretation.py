"""Data interpretation lifecycle objects for the application command layer."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from enum import Enum
from pathlib import Path
from typing import Any, cast

from scipy.io import loadmat

from .data_interpretation_formats import (
    LABEL_CARRIER_EXTENSIONS,
    SUPPORTED_EEG_EXTENSIONS,
)
from .data_interpretation_formats import (
    format_capabilities as _format_capabilities,
)
from .data_interpretation_metadata import (
    FileMetadataResolution,
    MetadataFieldResolution,
)
from .data_interpretation_metadata import (
    bids_summary as _bids_summary,
)
from .data_interpretation_metadata import (
    file_metadata_from_dict as _file_metadata_from_dict,
)
from .data_interpretation_metadata import (
    metadata_for_file as _metadata_for_file,
)


class InterpretationDecision(str, Enum):
    """Reviewable validation decisions for a data interpretation."""

    SAFE = "safe"
    NEEDS_CONFIRMATION = "needs_confirmation"
    BLOCKED = "blocked"


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
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
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
    label_carrier_plan: list[dict[str, Any]] = dc_field(default_factory=list)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)
    time_model: str = "unknown"
    granularity: str = "unknown"
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
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
    label_carrier_preview: list[dict[str, Any]] = dc_field(default_factory=list)
    metadata_preview: list[dict[str, Any]] = dc_field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
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
    label_carrier_plan: list[dict[str, Any]] = dc_field(default_factory=list)
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
    validation_decision: str = InterpretationDecision.SAFE.value
    confirmations: list[str] = dc_field(default_factory=list)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)
    label_imports: list[dict[str, Any]] = dc_field(default_factory=list)
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
    label_carrier_plan: list[dict[str, Any]] = dc_field(default_factory=list)
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
    validation_decision: str = InterpretationDecision.SAFE.value
    confirmations: list[str] = dc_field(default_factory=list)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)
    label_imports: list[dict[str, Any]] = dc_field(default_factory=list)
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
        label_carrier_plan=[
            dict(item)
            for item in payload.get("label_carrier_plan", [])
            if isinstance(item, dict)
        ],
        metadata=metadata,
        format_capabilities=[
            dict(item)
            for item in payload.get("format_capabilities", [])
            if isinstance(item, dict)
        ],
        validation_decision=str(
            payload.get("validation_decision", InterpretationDecision.SAFE.value),
        ),
        confirmations=[str(item) for item in payload.get("confirmations", [])],
        event_roles=_string_mapping(payload.get("event_roles")),
        class_map=_string_mapping(payload.get("class_map")),
        label_imports=[
            dict(item)
            for item in payload.get("label_imports", [])
            if isinstance(item, dict)
        ],
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
    format_capabilities = _format_capabilities(files)
    warnings = _scan_warnings(
        source_kind,
        eeg_files,
        label_carriers,
        bids,
        format_capabilities,
    )
    blocked_reasons = _scan_blocked_reasons(eeg_files, format_capabilities)

    return ScanResult(
        scan_id=scan_id,
        source_path=str(resolved),
        source_hint=source_hint,
        source_kind=source_kind,
        eeg_files=eeg_files,
        label_carriers=label_carriers,
        metadata=metadata,
        bids=bids,
        format_capabilities=format_capabilities,
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
    class_map: dict[str, str] = _string_mapping(choices.get("class_map"))
    metadata = _apply_metadata_overrides(
        scan.metadata,
        choices.get("metadata_overrides"),
    )
    label_carrier_plan = _build_label_carrier_plan(
        scan.label_carriers,
        choices.get("label_carrier_choices"),
    )

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

    event_roles.update(_string_mapping(choices.get("event_roles")))

    for item in metadata:
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
        label_carrier_plan=label_carrier_plan,
        event_roles=event_roles,
        class_map=class_map,
        time_model="sample_index_or_annotation_time"
        if event_roles
        else "file_native_time",
        granularity="trial_or_event" if event_roles else "recording",
        metadata=metadata,
        format_capabilities=[dict(item) for item in scan.format_capabilities],
        warnings=warnings,
        confirmation_items=confirmation_items,
        blocked_reasons=sorted(set(blocked_reasons)),
        choices=choices,
        recipe_trace=[
            f"scan:{scan.scan_id}",
            f"candidate:{candidate_id}",
            *_choice_recipe_trace(choices),
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
        label_carrier_preview=[dict(item) for item in candidate.label_carrier_plan],
        metadata_preview=metadata_preview,
        format_capabilities=[dict(item) for item in candidate.format_capabilities],
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
        label_carrier_plan=[dict(item) for item in applied.label_carrier_plan],
        metadata=list(applied.metadata),
        format_capabilities=[dict(item) for item in applied.format_capabilities],
        validation_decision=applied.validation_decision,
        confirmations=list(applied.confirmations),
        event_roles=dict(applied.event_roles),
        class_map=dict(applied.class_map),
        label_imports=[dict(item) for item in applied.label_imports],
        warnings=list(warnings),
        recipe_trace=[*applied.recipe_trace, f"recipe:{recipe_id}"],
    )


def _apply_metadata_overrides(
    metadata: list[FileMetadataResolution],
    overrides_payload: Any,
) -> list[FileMetadataResolution]:
    """Return metadata with user-confirmed wizard overrides applied."""
    if not isinstance(overrides_payload, dict) or not overrides_payload:
        return list(metadata)

    normalized_overrides: dict[str, dict[str, str]] = {}
    for key, fields in overrides_payload.items():
        if not isinstance(fields, dict):
            continue
        cleaned_fields = {
            str(field): str(value).strip()
            for field, value in fields.items()
            if str(value).strip()
        }
        if cleaned_fields:
            normalized_overrides[str(key)] = cleaned_fields

    if not normalized_overrides:
        return list(metadata)

    result: list[FileMetadataResolution] = []
    for item in metadata:
        file_path = Path(item.file)
        field_overrides = normalized_overrides.get(item.file)
        if field_overrides is None:
            field_overrides = normalized_overrides.get(file_path.name, {})
        if not field_overrides:
            result.append(item)
            continue
        result.append(
            FileMetadataResolution(
                file=item.file,
                subject=_override_field(item.subject, field_overrides),
                session=_override_field(item.session, field_overrides),
                task=_override_field(item.task, field_overrides),
                run=_override_field(item.run, field_overrides),
            )
        )
    return result


def _override_field(
    field: MetadataFieldResolution,
    overrides: dict[str, str],
) -> MetadataFieldResolution:
    value = overrides.get(field.field)
    if value is None:
        return field
    trace = [*field.recipe_trace, f"metadata_override:{field.field}"]
    return MetadataFieldResolution(
        field=field.field,
        value=value,
        source="user_override",
        decision=InterpretationDecision.SAFE.value,
        reason="User confirmed this value in the Data Interpretation wizard.",
        override=value,
        recipe_trace=trace,
    )


def _build_label_carrier_plan(
    label_carriers: list[str],
    choices_payload: Any,
) -> list[dict[str, Any]]:
    choices = _normalize_label_carrier_choices(choices_payload)
    return [
        _label_carrier_plan_for_path(Path(carrier), choices)
        for carrier in label_carriers
    ]


def _normalize_label_carrier_choices(payload: Any) -> dict[str, dict[str, str]]:
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
        "decision": InterpretationDecision.NEEDS_CONFIRMATION.value,
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


def _string_mapping(payload: Any) -> dict[str, str]:
    """Return a cleaned string mapping from a user-choice payload."""
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value).strip()
        for key, value in payload.items()
        if str(value).strip()
    }


def _choice_recipe_trace(choices: dict[str, Any]) -> list[str]:
    traces: list[str] = []
    metadata_overrides = choices.get("metadata_overrides")
    if isinstance(metadata_overrides, dict) and metadata_overrides:
        traces.append("choices:metadata_overrides")
    if _string_mapping(choices.get("class_map")):
        traces.append("choices:class_map")
    if _string_mapping(choices.get("event_roles")):
        traces.append("choices:event_roles")
    if _normalize_label_carrier_choices(choices.get("label_carrier_choices")):
        traces.append("choices:label_carriers")
    return traces


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


def _scan_warnings(
    source_kind: str,
    eeg_files: list[str],
    label_carriers: list[str],
    bids: dict[str, Any],
    format_capabilities: list[dict[str, Any]],
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
    blocked_formats = [
        str(item.get("format"))
        for item in format_capabilities
        if item.get("status") == "blocked"
    ]
    if blocked_formats and eeg_files:
        warnings.append(
            "Some discovered sources are not applied by this wizard yet: "
            + ", ".join(blocked_formats)
            + ".",
        )
    return warnings


def _scan_blocked_reasons(
    eeg_files: list[str],
    format_capabilities: list[dict[str, Any]],
) -> list[str]:
    if eeg_files:
        return []
    blocked = [
        str(item.get("message"))
        for item in format_capabilities
        if item.get("status") == "blocked" and item.get("message")
    ]
    if blocked:
        return sorted(set(blocked))
    return ["No supported EEG data files were found."]


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
