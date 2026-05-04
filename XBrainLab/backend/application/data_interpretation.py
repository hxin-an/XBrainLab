"""Data interpretation lifecycle objects for the application command layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from enum import Enum
from pathlib import Path
from typing import Any, cast

from . import data_interpretation_recipe as _recipe
from . import data_interpretation_review as _review
from . import data_interpretation_scan as _scan
from .data_interpretation_label_carriers import (
    build_label_carrier_plan as _build_label_carrier_plan,
)
from .data_interpretation_label_carriers import (
    normalize_label_carrier_choices as _normalize_label_carrier_choices,
)
from .data_interpretation_metadata import (
    FileMetadataResolution,
    MetadataFieldResolution,
)

ImportRecipe = _recipe.ImportRecipe
InterpretationPreview = _review.InterpretationPreview
ScanResult = _scan.ScanResult
ValidationDecision = _review.ValidationDecision
build_import_recipe = _recipe.build_import_recipe
build_interpretation_preview = _review.build_interpretation_preview
import_recipe_from_dict = _recipe.import_recipe_from_dict
load_import_recipe = _recipe.load_import_recipe
scan_source_path = _scan.scan_source_path
validate_interpretation_candidate = _review.validate_interpretation_candidate


class InterpretationDecision(str, Enum):
    """Reviewable validation decisions for a data interpretation."""

    SAFE = "safe"
    NEEDS_CONFIRMATION = "needs_confirmation"
    BLOCKED = "blocked"


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


def build_interpretation_candidate(
    *,
    candidate_id: str,
    scan: _scan.ScanResult,
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
