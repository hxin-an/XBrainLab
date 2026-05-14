"""Candidate building boundary for Data Interpretation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any

from . import data_interpretation_internal_events as _internal_events
from .data_interpretation_label_carriers import (
    build_label_carrier_plan as _build_label_carrier_plan,
)
from .data_interpretation_label_carriers import (
    infer_class_map_from_label_carrier_plan as _infer_class_map_from_label_carrier_plan,
)
from .data_interpretation_label_carriers import (
    normalize_label_carrier_choices as _normalize_label_carrier_choices,
)
from .data_interpretation_metadata import (
    FileMetadataResolution,
    MetadataFieldResolution,
)
from .data_interpretation_placement import (
    annotate_label_carrier_placements as _annotate_label_carrier_placements,
)
from .data_interpretation_placement import (
    placement_confirmation_items as _placement_confirmation_items,
)
from .data_interpretation_scan import ScanResult


@dataclass(frozen=True)
class InterpretationCandidate:
    """Candidate data interpretation built from a scan result."""

    candidate_id: str
    scan_id: str
    source_path: str
    source_kind: str
    selected_eeg_files: list[str] = dc_field(default_factory=list)
    label_sources: list[str] = dc_field(default_factory=list)
    label_carriers: list[str] = dc_field(default_factory=list)
    label_carrier_plan: list[dict[str, Any]] = dc_field(default_factory=list)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)
    class_map_source: str = ""
    internal_event_preview: dict[str, Any] = dc_field(default_factory=dict)
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


def build_interpretation_candidate(
    *,
    candidate_id: str,
    scan: ScanResult,
    choices: dict[str, Any] | None = None,
) -> InterpretationCandidate:
    """Build a candidate interpretation from a scan result and user choices."""
    choices = dict(choices or {})
    eeg_file_remap = _string_mapping(choices.get("eeg_file_remap"))
    raw_selected_files = [
        str(item)
        for item in choices.get("eeg_files", choices.get("selected_eeg_files", []))
    ]
    selected_files = (
        _remapped_selected_files(raw_selected_files, eeg_file_remap)
        if raw_selected_files
        else list(scan.eeg_files)
    )
    selected_files = _resolve_selected_files_to_scan(selected_files, scan.eeg_files)
    blocked_reasons = list(scan.blocked_reasons)
    warnings = list(scan.warnings)
    confirmation_items: list[str] = []
    event_roles: dict[str, str] = {}
    class_map: dict[str, str] = _string_mapping(choices.get("class_map"))
    class_map_source = "user_choices" if class_map else ""
    metadata = _metadata_for_selected_files(
        scan.metadata,
        selected_files,
        restrict=bool(raw_selected_files),
    )
    metadata = _apply_metadata_overrides(
        metadata,
        _remapped_metadata_overrides(
            choices.get("metadata_overrides"),
            eeg_file_remap,
        ),
    )
    label_carrier_source = _label_carrier_source_choice(choices)
    skip_labels = bool(choices.get("skip_labels"))
    use_external_label_carriers = (
        label_carrier_source != "embedded_events" and not skip_labels
    )
    excluded_label_carriers = _string_list(choices.get("excluded_label_carriers"))
    active_label_carriers = (
        _exclude_paths(scan.label_carriers, excluded_label_carriers)
        if use_external_label_carriers
        else []
    )
    label_carrier_choices = _remapped_label_carrier_choices(
        choices.get("label_carrier_choices"),
        choices.get("label_carrier_remap"),
    )
    label_carrier_plan = _build_label_carrier_plan(
        active_label_carriers,
        label_carrier_choices,
        carrier_sources=scan.label_carrier_sources,
    )
    warnings.extend(_label_carrier_plan_warnings(label_carrier_plan))
    if not class_map and use_external_label_carriers:
        class_map = _infer_class_map_from_label_carrier_plan(label_carrier_plan)
        if class_map:
            class_map_source = "label_carriers"

    if active_label_carriers:
        event_roles["label_carrier"] = "external label or event source"
        confirmation_items.append(
            "Confirm label carrier alignment, anchor event, and class map "
            "before applying.",
        )
    internal_event_preview: dict[str, Any] = {}
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
        internal_event_preview = _internal_events.build_internal_event_preview(
            selected_files
        )
        internal_event_warnings = internal_event_preview.get("scan_warnings", [])
        if isinstance(internal_event_warnings, list):
            warnings.extend(str(item) for item in internal_event_warnings)
        has_internal_event_rows = bool(
            internal_event_preview.get("candidate_label_events")
            or internal_event_preview.get("not_used_events")
        )
        if extensions & {".gdf", ".edf", ".bdf", ".set", ".vhdr"} or (
            has_internal_event_rows
        ):
            event_roles["internal_events"] = "event role candidates"
            confirmation_items.append(
                "Confirm which events are trial anchors, class cues, responses, "
                "artifacts, or boundaries.",
            )

    label_carrier_plan = _annotate_label_carrier_placements(
        label_carrier_plan,
        internal_event_preview,
    )
    blocked_reasons.extend(_blocked_placement_reasons(label_carrier_plan))
    confirmation_items.extend(_placement_confirmation_items(label_carrier_plan))

    event_roles.update(_string_mapping(choices.get("event_roles")))

    for item in metadata:
        fields = (item.subject, item.session, item.task, item.run)
        confirmation_items.extend(
            f"Confirm {field_value.field} metadata for {Path(item.file).name}."
            for field_value in fields
            if field_value.decision == "needs_confirmation"
        )

    confirmation_items = sorted(set(confirmation_items))
    if not selected_files:
        blocked_reasons.append("No EEG files were selected for interpretation.")
    missing_selected_files = _selected_files_missing_from_scan(
        selected_files,
        scan.eeg_files,
    )
    if missing_selected_files:
        blocked_reasons.append(
            "Selected EEG file(s) were not found in the current scan: "
            + ", ".join(missing_selected_files)
            + "."
        )
    missing_label_carriers = _required_label_carriers_missing_from_scan(
        choices,
        active_label_carriers,
    )
    if missing_label_carriers:
        blocked_reasons.append(
            "Saved label/event carrier(s) were not found in the current scan: "
            + ", ".join(missing_label_carriers)
            + "."
        )

    return InterpretationCandidate(
        candidate_id=candidate_id,
        scan_id=scan.scan_id,
        source_path=scan.source_path,
        source_kind=scan.source_kind,
        selected_eeg_files=selected_files,
        label_sources=list(scan.label_sources),
        label_carriers=active_label_carriers,
        label_carrier_plan=label_carrier_plan,
        event_roles=event_roles,
        class_map=class_map,
        class_map_source=class_map_source,
        internal_event_preview=internal_event_preview,
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


def _label_carrier_plan_warnings(
    label_carrier_plan: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    for carrier in label_carrier_plan:
        for item in carrier.get("warnings", []) or []:
            text = str(item).strip()
            if text and text not in warnings:
                warnings.append(text)
    return warnings


def _blocked_placement_reasons(
    label_carrier_plan: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    for carrier in label_carrier_plan:
        review = carrier.get("placement_review")
        if not isinstance(review, dict):
            continue
        if str(review.get("status") or "").strip() != "blocked":
            continue
        carrier_name = str(
            carrier.get("name") or Path(str(carrier.get("path") or "")).name
        ).strip()
        summary = str(review.get("summary") or "Label placement is blocked.").strip()
        reason = f"{carrier_name}: {summary}" if carrier_name else summary
        if reason not in reasons:
            reasons.append(reason)
    return reasons


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
        decision="safe",
        reason="User confirmed this value in the Data Interpretation wizard.",
        override=value,
        recipe_trace=trace,
    )


def _metadata_for_selected_files(
    metadata: list[FileMetadataResolution],
    selected_files: list[str],
    *,
    restrict: bool,
) -> list[FileMetadataResolution]:
    """Return metadata rows relevant to the candidate EEG file selection."""
    if not restrict:
        return list(metadata)
    selected_keys = {_path_key(path) for path in selected_files}
    selected_names = {Path(path).name for path in selected_files}
    return [
        item
        for item in metadata
        if (
            _path_key(item.file) in selected_keys
            or Path(item.file).name in selected_names
        )
    ]


def _string_mapping(payload: Any) -> dict[str, str]:
    """Return a cleaned string mapping from a user-choice payload."""
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value).strip()
        for key, value in payload.items()
        if str(value).strip()
    }


def _path_key(path: str) -> str:
    return str(Path(path).expanduser())


def _selected_files_missing_from_scan(
    selected_files: list[str],
    scanned_files: list[str],
) -> list[str]:
    return _paths_missing_from_scan(selected_files, scanned_files)


def _resolve_selected_files_to_scan(
    selected_files: list[str],
    scanned_files: list[str],
) -> list[str]:
    """Map selected relative filenames to their scanned absolute file paths."""
    scanned_exact = {str(item): str(item) for item in scanned_files}
    scanned_by_name: dict[str, list[str]] = {}
    for item in scanned_files:
        text = str(item)
        name = Path(text).name or text
        scanned_by_name.setdefault(name, []).append(text)

    result: list[str] = []
    for selected in selected_files:
        text = str(selected)
        mapped = scanned_exact.get(text)
        if mapped is None:
            matches = scanned_by_name.get(Path(text).name or text, [])
            mapped = matches[0] if len(matches) == 1 else text
        if mapped not in result:
            result.append(mapped)
    return result


def _remapped_selected_files(
    selected_files: list[str],
    remap: dict[str, str],
) -> list[str]:
    result: list[str] = []
    for file_path in selected_files:
        mapped = _mapped_path(file_path, remap)
        if mapped and mapped not in result:
            result.append(mapped)
    return result


def _remapped_metadata_overrides(
    payload: Any,
    remap: dict[str, str],
) -> Any:
    if not isinstance(payload, dict) or not remap:
        return payload
    result: dict[str, Any] = {}
    for file_key, fields in payload.items():
        mapped = _mapped_path(str(file_key), remap)
        if mapped:
            result[mapped] = fields
    return result


def _required_label_carriers_missing_from_scan(
    choices: dict[str, Any],
    scanned_carriers: list[str],
) -> list[str]:
    if _label_carrier_source_choice(choices) == "embedded_events" or bool(
        choices.get("skip_labels")
    ):
        return []
    remap = _string_mapping(choices.get("label_carrier_remap"))
    required = _remapped_required_label_carriers(
        _string_list(choices.get("required_label_carriers")),
        remap,
    )
    label_carrier_choices = choices.get("label_carrier_choices")
    if isinstance(label_carrier_choices, dict):
        required.extend(
            remap.get(str(key).strip(), str(key).strip())
            for key in label_carrier_choices
            if str(key).strip()
        )
    return _paths_missing_from_scan(required, scanned_carriers)


def _label_carrier_source_choice(choices: dict[str, Any]) -> str:
    return str(choices.get("label_carrier") or "").strip()


def _exclude_paths(paths: list[str], excluded: list[str]) -> list[str]:
    if not excluded:
        return list(paths)
    excluded_exact = {str(item) for item in excluded}
    excluded_names = {Path(str(item)).name or str(item) for item in excluded}
    result: list[str] = []
    for path in paths:
        text = str(path)
        name = Path(text).name or text
        if text in excluded_exact or name in excluded_names:
            continue
        result.append(text)
    return result


def _remapped_required_label_carriers(
    required: list[str],
    remap: dict[str, str],
) -> list[str]:
    result: list[str] = []
    for carrier in required:
        mapped = _mapped_path(carrier, remap)
        if mapped and mapped not in result:
            result.append(mapped)
    return result


def _remapped_label_carrier_choices(
    payload: Any,
    remap_payload: Any,
) -> dict[str, dict[str, str]]:
    choices = _normalize_label_carrier_choices(payload)
    remap = _string_mapping(remap_payload)
    if not choices or not remap:
        return choices
    result: dict[str, dict[str, str]] = {}
    for carrier, carrier_choices in choices.items():
        mapped = _mapped_path(carrier, remap)
        if mapped:
            result[mapped] = dict(carrier_choices)
    return result


def _mapped_path(path: str, remap: dict[str, str]) -> str:
    text = str(path).strip()
    if not text:
        return ""
    if text in remap:
        return remap[text]
    name = Path(text).name or text
    for source, target in remap.items():
        if Path(str(source)).name == name:
            return str(target)
    return text


def _string_list(payload: Any) -> list[str]:
    if not isinstance(payload, list):
        return []
    result: list[str] = []
    for item in payload:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _paths_missing_from_scan(required: list[str], scanned: list[str]) -> list[str]:
    scanned_exact = {str(item) for item in scanned}
    scanned_names = {Path(str(item)).name or str(item) for item in scanned}
    missing: list[str] = []
    for item in required:
        text = str(item)
        name = Path(text).name or text
        if text in scanned_exact or name in scanned_names:
            continue
        if name not in missing:
            missing.append(name)
    return missing


def _choice_recipe_trace(choices: dict[str, Any]) -> list[str]:
    traces: list[str] = []
    metadata_overrides = choices.get("metadata_overrides")
    if isinstance(metadata_overrides, dict) and metadata_overrides:
        traces.append("choices:metadata_overrides")
    if _string_mapping(choices.get("class_map")):
        traces.append("choices:class_map")
    if _string_mapping(choices.get("event_roles")):
        traces.append("choices:event_roles")
    use_external_label_carriers = (
        _label_carrier_source_choice(choices) != "embedded_events"
    )
    if use_external_label_carriers and (
        _normalize_label_carrier_choices(choices.get("label_carrier_choices"))
        or _string_list(choices.get("required_label_carriers"))
    ):
        traces.append("choices:label_carriers")
    if _label_carrier_source_choice(choices):
        traces.append("choices:label_carrier")
    if _string_list(choices.get("label_sources")):
        traces.append("choices:label_sources")
    if _string_list(choices.get("excluded_label_carriers")):
        traces.append("choices:excluded_label_carriers")
    if bool(choices.get("skip_labels")):
        traces.append("choices:skip_labels")
    if _string_mapping(choices.get("eeg_file_remap")):
        traces.append("choices:eeg_file_remap")
    if _string_mapping(choices.get("label_carrier_remap")):
        traces.append("choices:label_carrier_remap")
    return traces


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value
