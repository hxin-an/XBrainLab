"""Candidate building boundary for Data Interpretation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from pathlib import Path, PureWindowsPath
from typing import Any

from . import data_interpretation_internal_events as _internal_events
from .bids_dataset_index import current_bids_dataset_index_for_path
from .data_interpretation_bids import review_strict_bids_event_runs
from .data_interpretation_bids_channels import review_bids_channel_sidecars
from .data_interpretation_bids_resources import (
    BidsEventsJsonReader,
    bids_events_json_resource_paths,
)
from .data_interpretation_content_identity import build_review_content_identity
from .data_interpretation_event_values import derive_class_views
from .data_interpretation_label_carriers import (
    build_label_carrier_plan as _build_label_carrier_plan,
)
from .data_interpretation_label_carriers import (
    normalize_label_carrier_choices as _normalize_label_carrier_choices,
)
from .data_interpretation_metadata import (
    FileMetadataResolution,
    MetadataFieldResolution,
    bids_scope_summary,
)
from .data_interpretation_pairing import resolve_label_file_pairing
from .data_interpretation_path_identity import (
    normalized_path_identity,
    resolve_scan_path,
    unresolved_scan_path_descriptions,
)
from .data_interpretation_placement import (
    annotate_label_carrier_placements as _annotate_label_carrier_placements,
)
from .data_interpretation_placement import (
    placement_blocked_reasons as _blocked_placement_reasons,
)
from .data_interpretation_placement import (
    placement_confirmation_items as _placement_confirmation_items,
)
from .data_interpretation_public_projection import (
    project_interpretation_candidate,
)
from .data_interpretation_resource_reader import AdmittedResourceReader
from .data_interpretation_scan import ScanResult
from .eeglab_set_preflight import eeglab_external_data_dependency
from .errors import PreconditionError

BRAINVISION_HEADER_MAX_BYTES = 1_048_576


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
    bids: dict[str, Any] = dc_field(default_factory=dict)
    label_carrier_plan: list[dict[str, Any]] = dc_field(default_factory=list)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)
    class_map_source: str = ""
    internal_event_preview: dict[str, Any] = dc_field(default_factory=dict)
    internal_event_selection: dict[str, Any] = dc_field(default_factory=dict)
    run_event_mappings: dict[str, dict[str, str]] = dc_field(default_factory=dict)
    time_model: str = "unknown"
    granularity: str = "unknown"
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    confirmation_items: list[str] = dc_field(default_factory=list)
    blocked_reasons: list[str] = dc_field(default_factory=list)
    choices: dict[str, Any] = dc_field(default_factory=dict)
    content_identity: dict[str, Any] = dc_field(default_factory=dict)
    recipe_trace: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)

    def to_public_dict(self) -> dict[str, Any]:
        """Return a bounded projection for UI, agent, and diagnostics clients."""
        return project_interpretation_candidate(_serialize(self))


@dataclass(frozen=True)
class InterpretationResourceScope:
    """EEG and external label paths that one preview may materialize."""

    selected_eeg_files: list[str] = dc_field(default_factory=list)
    materializable_eeg_files: list[str] = dc_field(default_factory=list)
    eeg_dependency_files: list[str] = dc_field(default_factory=list)
    eeg_dependencies_by_file: dict[str, list[str]] = dc_field(default_factory=dict)
    label_carriers: list[str] = dc_field(default_factory=list)
    bids_events_json_files: list[str] = dc_field(default_factory=list)
    bids_channels_files: list[str] = dc_field(default_factory=list)
    bids_events_json_by_carrier: dict[str, tuple[str, ...]] = dc_field(
        default_factory=dict
    )
    bids: dict[str, Any] = dc_field(default_factory=dict)

    @property
    def paths(self) -> list[str]:
        result: list[str] = []
        for path in [
            *self.materializable_eeg_files,
            *self.eeg_dependency_files,
            *self.label_carriers,
            *self.bids_events_json_files,
            *self.bids_channels_files,
        ]:
            if path not in result:
                result.append(path)
        return result


def resolve_interpretation_resource_scope(
    scan: ScanResult,
    choices: dict[str, Any] | None = None,
    *,
    bids_events_json_by_carrier: dict[str, tuple[str, ...]] | None = None,
) -> InterpretationResourceScope:
    """Resolve preview paths without reading EEG or label payloads."""
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
    materializable_files = [
        file_path for file_path in selected_files if file_path in set(scan.eeg_files)
    ]
    eeg_dependencies_by_file = _eeg_dependencies_by_file(materializable_files)
    eeg_dependency_files = [
        dependency
        for dependencies in eeg_dependencies_by_file.values()
        for dependency in dependencies
    ]
    skip_labels = bool(choices.get("skip_labels"))
    use_external_label_carriers = (
        _label_carrier_source_choice(choices) != "embedded_events" and not skip_labels
    )
    excluded_label_carriers = (
        [] if skip_labels else _string_list(choices.get("excluded_label_carriers"))
    )
    active_label_carriers = (
        _exclude_paths(scan.label_carriers, excluded_label_carriers)
        if use_external_label_carriers
        else []
    )
    bids = _bids_for_selected_scope(scan.bids, selected_files)
    active_label_carriers = _filter_bids_label_carriers_for_selected_scope(
        active_label_carriers,
        scan.bids,
        bids,
    )
    sidecars_by_carrier = _bids_events_json_catalog_for_scope(
        active_label_carriers,
        bids_events_json_by_carrier,
    )
    return InterpretationResourceScope(
        selected_eeg_files=selected_files,
        materializable_eeg_files=materializable_files,
        eeg_dependency_files=eeg_dependency_files,
        eeg_dependencies_by_file=eeg_dependencies_by_file,
        label_carriers=active_label_carriers,
        bids_events_json_files=list(
            dict.fromkeys(
                path for paths in sidecars_by_carrier.values() for path in paths
            )
        ),
        bids_channels_files=_selected_bids_channels_files(bids),
        bids_events_json_by_carrier=sidecars_by_carrier,
        bids=bids,
    )


def _bids_events_json_catalog_for_scope(
    label_carriers: list[str],
    catalog: dict[str, tuple[str, ...]] | None,
) -> dict[str, tuple[str, ...]]:
    available = dict(catalog or {})
    available_by_identity = {
        normalized_path_identity(carrier): tuple(paths)
        for carrier, paths in available.items()
    }
    result: dict[str, tuple[str, ...]] = {}
    missing: list[str] = []
    for carrier in label_carriers:
        paths = available_by_identity.get(normalized_path_identity(carrier))
        if paths is None:
            missing.append(carrier)
        else:
            result[carrier] = paths
    for carrier in missing:
        result[carrier] = tuple(bids_events_json_resource_paths([carrier]))
    return result


def build_interpretation_candidate(
    *,
    candidate_id: str,
    scan: ScanResult,
    choices: dict[str, Any] | None = None,
    bids_events_json_reader: BidsEventsJsonReader | None = None,
    resource_reader: AdmittedResourceReader | None = None,
    resource_scope: InterpretationResourceScope | None = None,
    admitted_content_identities: dict[str, dict[str, Any]] | None = None,
) -> InterpretationCandidate:
    """Build a candidate interpretation from a scan result and user choices."""
    choices = dict(choices or {})
    resource_scope = resource_scope or resolve_interpretation_resource_scope(
        scan,
        choices,
    )
    if resource_reader is not None:
        resource_reader = resource_reader.with_dependent_files(
            resource_scope.eeg_dependencies_by_file,
        )
    sidecar_reader = bids_events_json_reader or BidsEventsJsonReader.from_paths(
        resource_scope.bids_events_json_files,
    )
    eeg_file_remap = _string_mapping(choices.get("eeg_file_remap"))
    raw_selected_files = [
        str(item)
        for item in choices.get("eeg_files", choices.get("selected_eeg_files", []))
    ]
    selected_files = list(resource_scope.selected_eeg_files)
    materializable_files = list(resource_scope.materializable_eeg_files)
    blocked_reasons = list(scan.blocked_reasons)
    warnings = list(scan.warnings)
    confirmation_items: list[str] = []
    event_roles: dict[str, str] = {}
    skip_labels = bool(choices.get("skip_labels"))
    legacy_class_map = {} if skip_labels else _string_mapping(choices.get("class_map"))
    class_map: dict[str, str] = {}
    run_event_mappings = (
        {} if skip_labels else _nested_string_mapping(choices.get("run_event_mappings"))
    )
    class_map_source = ""
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
    if label_carrier_source == "embedded_events" and legacy_class_map:
        class_map = legacy_class_map
        class_map_source = "user_choices"
    use_external_label_carriers = (
        label_carrier_source != "embedded_events" and not skip_labels
    )
    active_label_carriers = list(resource_scope.label_carriers)
    bids = dict(resource_scope.bids)
    if (
        scan.source_kind == "bids"
        and scan.bids.get("is_bids")
        and selected_files
        and not _bids_selected_scope_has_events(bids)
    ):
        blocked_reasons.append(
            "BIDS events.tsv was not found for the selected EEG file(s). "
            "Choose a BIDS run with events.tsv, or use Import folder for non-BIDS "
            "labels."
        )
    label_carrier_choices = (
        {}
        if skip_labels
        else _remapped_label_carrier_choices(
            choices.get("label_carrier_choices"),
            choices.get("label_carrier_remap"),
        )
    )
    label_carrier_plan = _build_label_carrier_plan(
        active_label_carriers,
        label_carrier_choices,
        carrier_sources=scan.label_carrier_sources,
        sidecar_reader=sidecar_reader,
        resource_reader=resource_reader,
        recommend_bids_label_field=(
            scan.source_kind == "bids" and bool(bids.get("is_bids"))
        ),
    )
    warnings.extend(_label_carrier_plan_warnings(label_carrier_plan))
    if use_external_label_carriers:
        class_map, _run_class_maps = derive_class_views(label_carrier_plan)
        if any(
            isinstance(plan.get("run_class_map"), dict)
            and bool(plan.get("run_class_map"))
            for plan in label_carrier_plan
        ):
            class_map_source = "value_decisions"
        for plan in label_carrier_plan:
            unresolved = [
                str(value)
                for value in plan.get("unresolved_values", [])
                if str(value).strip()
            ]
            if not unresolved:
                continue
            blocked_reasons.append(
                "Observed event values require complete role/keep/class decisions "
                f"for {Path(str(plan.get('path') or '')).name}: "
                + ", ".join(unresolved)
                + "."
            )

    if active_label_carriers:
        event_roles["label_carrier"] = "external label or event source"
    internal_event_preview: dict[str, Any] = {}
    if skip_labels:
        internal_event_selection: dict[str, Any] = {}
    elif scan.bids.get("is_bids"):
        event_roles.update(
            {
                "onset": "time anchor",
                "duration": "event duration",
                "trial_type": "class label candidate",
            },
        )
        event_roles.update(_string_mapping(choices.get("event_roles")))
        explicit_internal_event_selection = isinstance(
            choices.get("internal_event_selection"),
            dict,
        ) and bool(choices.get("internal_event_selection"))
        internal_event_selection = (
            _internal_event_selection(
                internal_event_preview,
                choices.get("internal_event_selection"),
                event_roles,
            )
            if label_carrier_source == "embedded_events"
            or explicit_internal_event_selection
            else {}
        )
    else:
        extensions = {Path(item).suffix.lower() for item in materializable_files}
        internal_event_preview = _internal_events.build_internal_event_preview(
            materializable_files,
            resource_reader=resource_reader,
        )
        internal_event_warnings = internal_event_preview.get("scan_warnings", [])
        if isinstance(internal_event_warnings, list):
            warnings.extend(str(item) for item in internal_event_warnings)
        if internal_event_preview.get("run_dependent_semantics"):
            event_roles["run_dependent_events"] = "run/task mapping needs confirmation"
            run_mapping_review = _internal_events.review_run_dependent_event_mappings(
                internal_event_preview,
                materializable_files,
                run_event_mappings,
            )
            internal_event_preview["run_event_mapping_review"] = run_mapping_review
            if run_mapping_review["status"] == "needs_confirmation":
                affected = [
                    (f"{row['file']} missing {', '.join(row['missing_event_codes'])}")
                    for row in run_mapping_review["files"]
                    if row["missing_event_codes"]
                ]
                confirmation_items.append(
                    "Confirm run-dependent T1/T2 event mapping before supervised "
                    "training: " + "; ".join(affected) + ".",
                )
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
        event_roles.update(_string_mapping(choices.get("event_roles")))
        explicit_internal_event_selection = isinstance(
            choices.get("internal_event_selection"),
            dict,
        ) and bool(choices.get("internal_event_selection"))
        internal_event_selection = (
            _internal_event_selection(
                internal_event_preview,
                choices.get("internal_event_selection"),
                event_roles,
            )
            if label_carrier_source == "embedded_events"
            or explicit_internal_event_selection
            else {}
        )
    if label_carrier_source == "embedded_events" and not class_map:
        selection_class_map = _string_mapping(internal_event_selection.get("class_map"))
        if selection_class_map:
            class_map = selection_class_map
            class_map_source = "internal_events"

    label_carrier_plan = _annotate_label_carrier_placements(
        label_carrier_plan,
        internal_event_preview,
    )
    if (
        scan.source_kind == "bids"
        and bids.get("is_bids")
        and use_external_label_carriers
    ):
        bids_review = review_strict_bids_event_runs(
            bids=bids,
            selected_eeg_files=selected_files,
            label_carrier_plan=label_carrier_plan,
            resource_reader=resource_reader,
        )
        label_carrier_plan = bids_review.label_carrier_plan
        if bids_review.evidence:
            bids["event_validation"] = bids_review.evidence
        blocked_reasons.extend(bids_review.blocked_reasons)
        confirmation_items.extend(bids_review.confirmation_items)
        warnings.extend(bids_review.warnings)
    if scan.source_kind == "bids" and bids.get("is_bids"):
        channel_review = review_bids_channel_sidecars(
            bids=bids,
            selected_eeg_files=selected_files,
            resource_reader=resource_reader,
        )
        bids["channel_review"] = channel_review.to_dict()
        blocked_reasons.extend(channel_review.blocked_reasons)
        warnings.extend(channel_review.warnings)
    blocked_reasons.extend(_blocked_placement_reasons(label_carrier_plan))
    confirmation_items.extend(_placement_confirmation_items(label_carrier_plan))

    for item in metadata:
        # Subject is the only metadata field required by the generic import
        # contract. Strict BIDS structure is validated by the BIDS reviewer
        # above; task/session/run remain optional review notes here.
        fields = (item.subject,)
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
    if (
        not missing_selected_files
        and use_external_label_carriers
        and label_carrier_plan
        and selected_files
    ):
        pairing = resolve_label_file_pairing(label_carrier_plan, selected_files)
        if not pairing.complete:
            blocked_reasons.append(pairing.blocking_reason())

    identity_eeg_files = [
        path for path in resource_scope.materializable_eeg_files if Path(path).is_file()
    ]
    content_identity = build_review_content_identity(
        label_carrier_plan=label_carrier_plan,
        selected_eeg_files=identity_eeg_files,
        eeg_parser_dependencies=resource_scope.eeg_dependencies_by_file,
        bids_events_json_files=resource_scope.bids_events_json_files,
        bids_channels_files=resource_scope.bids_channels_files,
        admitted_file_identities={
            **dict(admitted_content_identities or {}),
            **sidecar_reader.content_identities(
                resource_scope.bids_events_json_files,
            ),
        },
        class_map=class_map,
        event_roles=event_roles,
        run_event_mappings=run_event_mappings,
        resource_reader=resource_reader,
    )
    content_trace = (
        [f"content:{content_identity['scope_sha256']}"]
        if content_identity.get("files")
        else []
    )

    return InterpretationCandidate(
        candidate_id=candidate_id,
        scan_id=scan.scan_id,
        source_path=scan.source_path,
        source_kind=scan.source_kind,
        selected_eeg_files=selected_files,
        label_sources=list(scan.label_sources),
        label_carriers=active_label_carriers,
        bids=bids,
        label_carrier_plan=label_carrier_plan,
        event_roles=event_roles,
        class_map=class_map,
        class_map_source=class_map_source,
        internal_event_preview=internal_event_preview,
        internal_event_selection=internal_event_selection,
        run_event_mappings=run_event_mappings,
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
        content_identity=content_identity,
        recipe_trace=[
            f"scan:{scan.scan_id}",
            f"candidate:{candidate_id}",
            *_choice_recipe_trace(choices),
            *content_trace,
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


def _bids_for_selected_scope(
    bids: dict[str, Any],
    selected_files: list[str],
) -> dict[str, Any]:
    """Return BIDS summary scoped to the candidate's selected EEG files."""
    result = dict(bids)
    layout = result.get("layout")
    if isinstance(layout, list):
        rows = [dict(item) for item in layout if isinstance(item, dict)]
        result["selected_scope"] = bids_scope_summary(selected_files, rows)
    return result


def _selected_bids_channels_files(bids: dict[str, Any]) -> list[str]:
    selected_scope = bids.get("selected_scope")
    if not isinstance(selected_scope, dict):
        return []
    return [
        str(path)
        for path in selected_scope.get("channels_files", [])
        if str(path).strip() and Path(str(path)).is_file()
    ]


def _eeg_dependencies_by_file(eeg_files: list[str]) -> dict[str, list[str]]:
    dependencies_by_file: dict[str, list[str]] = {}
    for eeg_file in eeg_files:
        eeg_path = Path(eeg_file)
        if not eeg_path.is_file():
            continue
        suffix = eeg_path.suffix.casefold()
        if suffix == ".set":
            dependency = eeglab_external_data_dependency(eeg_file)
            dependencies = [dependency] if dependency else []
        elif suffix == ".vhdr":
            dependencies = _brainvision_parser_dependencies(eeg_file)
        else:
            dependencies = []
        if dependencies:
            dependencies_by_file[str(Path(eeg_file).resolve(strict=False))] = list(
                dict.fromkeys(dependencies)
            )
    return dependencies_by_file


def _brainvision_parser_dependencies(vhdr_file: str) -> list[str]:
    """Resolve BrainVision data/marker references from one bounded text header."""
    path = Path(vhdr_file).expanduser()
    try:
        with path.open("rb") as handle:
            payload = handle.read(BRAINVISION_HEADER_MAX_BYTES + 1)
    except OSError as exc:
        raise PreconditionError(
            f"BrainVision header dependencies could not be inspected: {path}.",
            diagnostics={
                "code": "brainvision_dependency_header_unavailable",
                "path": str(path.resolve(strict=False)),
                "os_error": str(exc),
            },
        ) from exc
    if len(payload) > BRAINVISION_HEADER_MAX_BYTES:
        raise PreconditionError(
            f"BrainVision header exceeds the bounded dependency read limit: {path}.",
            diagnostics={
                "code": "brainvision_dependency_header_too_large",
                "path": str(path.resolve(strict=False)),
                "max_bytes": BRAINVISION_HEADER_MAX_BYTES,
            },
        )
    text = _decode_brainvision_header(payload)
    references = _brainvision_common_info_references(text)
    dependencies: list[str] = []
    for key, expected_suffix in (("datafile", ".eeg"), ("markerfile", ".vmrk")):
        reference = references.get(key)
        if not reference:
            continue
        dependency = _resolve_brainvision_reference(
            header_path=path,
            reference=reference,
            expected_suffix=expected_suffix,
        )
        dependencies.append(str(dependency))
    return dependencies


def _decode_brainvision_header(payload: bytes) -> str:
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return payload.decode("cp1252", errors="replace")


def _brainvision_common_info_references(text: str) -> dict[str, str]:
    section = ""
    references: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().casefold()
            continue
        if section != "common infos" or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip().casefold()
        if normalized_key in {"datafile", "markerfile"}:
            references[normalized_key] = value.strip()
    return references


def _resolve_brainvision_reference(
    *,
    header_path: Path,
    reference: str,
    expected_suffix: str,
) -> Path:
    normalized = reference.strip().strip('"').strip("\x00").replace("\\", "/")
    relative = Path(normalized)
    windows_path = PureWindowsPath(normalized)
    if (
        not normalized
        or windows_path.drive
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise _brainvision_dependency_error(
            header_path,
            reference,
            "The dependency reference must be a safe relative path.",
        )
    if relative.suffix.casefold() != expected_suffix:
        raise _brainvision_dependency_error(
            header_path,
            reference,
            f"The dependency reference must name a {expected_suffix} file.",
        )

    root = header_path.parent.resolve()
    bids_index = current_bids_dataset_index_for_path(header_path)
    if bids_index is not None and bids_index.contains_recording(header_path):
        indexed = bids_index.indexed_file_in_recording_directory(
            header_path,
            relative,
        )
        if indexed is None:
            raise _brainvision_dependency_error(
                header_path,
                reference,
                "The dependency was not listed in the BIDS dataset index.",
            )
        resolved = Path(indexed)
        if resolved.suffix.casefold() != expected_suffix:
            raise _brainvision_dependency_error(
                header_path,
                reference,
                f"The dependency reference must name a {expected_suffix} file.",
            )
        return resolved
    current = root
    for part in relative.parts:
        exact = current / part
        if exact.exists():
            current = exact
            continue
        try:
            matches = [
                child
                for child in current.iterdir()
                if child.name.casefold() == part.casefold()
            ]
        except OSError as exc:
            raise _brainvision_dependency_error(
                header_path,
                reference,
                "The dependency directory could not be inspected.",
            ) from exc
        if len(matches) != 1:
            raise _brainvision_dependency_error(
                header_path,
                reference,
                "The dependency file was not found uniquely.",
            )
        current = matches[0]
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise _brainvision_dependency_error(
            header_path,
            reference,
            "The dependency escapes the BrainVision header folder.",
        ) from exc
    if not resolved.is_file():
        raise _brainvision_dependency_error(
            header_path,
            reference,
            "The dependency is not a regular file.",
        )
    return resolved


def _brainvision_dependency_error(
    header_path: Path,
    reference: str,
    reason: str,
) -> PreconditionError:
    return PreconditionError(
        f"BrainVision parser dependency could not be admitted for {header_path.name}: "
        f"{reason}",
        diagnostics={
            "code": "brainvision_dependency_unavailable",
            "path": str(header_path.resolve(strict=False)),
            "reference": reference,
            "reason": reason,
        },
    )


def _filter_bids_label_carriers_for_selected_scope(
    label_carriers: list[str],
    scan_bids: dict[str, Any],
    candidate_bids: dict[str, Any],
) -> list[str]:
    if not scan_bids.get("is_bids"):
        return list(label_carriers)
    all_bids_events = {str(item) for item in scan_bids.get("events_files", []) or []}
    selected_scope = candidate_bids.get("selected_scope")
    if not all_bids_events or not isinstance(selected_scope, dict):
        return list(label_carriers)
    selected_bids_events = {
        str(item) for item in selected_scope.get("events_files", []) or []
    }
    return [
        carrier
        for carrier in label_carriers
        if carrier not in all_bids_events or carrier in selected_bids_events
    ]


def _bids_selected_scope_has_events(bids: dict[str, Any]) -> bool:
    selected_scope = bids.get("selected_scope")
    if not isinstance(selected_scope, dict):
        return bool(bids.get("events_files"))
    return bool(selected_scope.get("events_files"))


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


def _nested_string_mapping(payload: Any) -> dict[str, dict[str, str]]:
    """Return cleaned nested string mappings from review choices."""
    if not isinstance(payload, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for outer_key, inner_payload in payload.items():
        inner = _string_mapping(inner_payload)
        if inner:
            result[str(outer_key)] = inner
    return result


def _internal_event_selection(
    internal_event_preview: dict[str, Any],
    payload: Any,
    event_roles: dict[str, str],
) -> dict[str, Any]:
    """Build a replayable internal-event selection from preview evidence."""
    if not internal_event_preview:
        return {}
    explicit = payload if isinstance(payload, dict) else {}
    has_explicit_selected = "label_event_codes" in explicit
    has_explicit_not_label = "not_label_event_codes" in explicit
    has_explicit_class_map = "class_map" in explicit
    selected = _string_list(explicit.get("label_event_codes"))
    not_label = _string_list(explicit.get("not_label_event_codes"))
    class_map = _string_mapping(explicit.get("class_map"))
    if not selected and not has_explicit_selected:
        selected = _internal_event_codes(
            internal_event_preview.get("candidate_label_events")
            or internal_event_preview.get("candidate_events")
        )
    if not not_label and not has_explicit_not_label:
        not_label = _internal_not_label_event_codes(
            internal_event_preview.get("not_used_events")
            or internal_event_preview.get("non_label_events")
            or internal_event_preview.get("excluded_events")
        )
    for code, role in event_roles.items():
        normalized_role = str(role).strip().lower()
        code_text = str(code).strip()
        if not code_text:
            continue
        if normalized_role == "class label":
            if code_text not in selected:
                selected.append(code_text)
            not_label = [item for item in not_label if item != code_text]
        elif normalized_role == "not a label":
            if code_text not in not_label:
                not_label.append(code_text)
            selected = [item for item in selected if item != code_text]
    if not class_map and not has_explicit_class_map:
        class_map = _class_map_from_internal_event_rows(
            internal_event_preview.get("candidate_label_events")
            or internal_event_preview.get("candidate_events")
        )
    selected = _sorted_event_codes(selected)
    not_label = [item for item in not_label if item not in selected]
    event_counts = _internal_event_counts(internal_event_preview)
    result: dict[str, Any] = {
        "label_event_codes": selected,
        "label_event_counts": {code: event_counts.get(code, 0) for code in selected},
        "not_label_event_codes": not_label,
    }
    if class_map:
        result["class_map"] = {
            key: class_map[key] for key in _sorted_event_codes(class_map)
        }
    return result


def _internal_event_counts(internal_event_preview: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row_key in (
        "candidate_label_events",
        "candidate_events",
        "not_used_events",
        "non_label_events",
        "excluded_events",
    ):
        rows = internal_event_preview.get(row_key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = _internal_event_code_from_row(row)
            if not code:
                continue
            raw_count: Any = row.get(
                "event_count",
                row.get("total_count", row.get("count")),
            )
            try:
                count = max(int(raw_count), 0)
            except (TypeError, ValueError, OverflowError):
                count = 0
            counts[code] = max(counts.get(code, 0), count)
    return counts


def _internal_event_codes(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    codes: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = _internal_event_code_from_row(row)
        if code and code not in codes:
            codes.append(code)
    return codes


def _internal_not_label_event_codes(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    typed_rows = [row for row in rows if isinstance(row, dict)]
    typed_rows.sort(key=_not_label_event_sort_key)
    return _internal_event_codes(typed_rows)


def _not_label_event_sort_key(row: dict[str, Any]) -> tuple[int, tuple[int, int | str]]:
    text = " ".join(
        str(row.get(key) or "").lower() for key in ("use_as", "reason", "evidence")
    )
    if any(token in text for token in ("artifact", "artefact", "exclude", "bad")):
        rank = 0
    elif any(token in text for token in ("boundary", "system", "ignore")):
        rank = 1
    elif any(token in text for token in ("trial", "start", "anchor", "timing")):
        rank = 2
    else:
        rank = 3
    return (rank, _event_code_sort_key(_internal_event_code_from_row(row)))


def _class_map_from_internal_event_rows(rows: Any) -> dict[str, str]:
    if not isinstance(rows, list):
        return {}
    result: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = _internal_event_code_from_row(row)
        label = str(row.get("class_name") or row.get("name") or "").strip()
        if code and label:
            result[code] = label
    return result


def _internal_event_code_from_row(row: dict[str, Any]) -> str:
    for key in (
        "event_code",
        "original_event_code",
        "original_code",
        "original_label",
        "value",
        "raw_value",
        "code",
        "label",
        "event_label",
    ):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _sorted_event_codes(values: Any) -> list[str]:
    raw_values = values.keys() if isinstance(values, dict) else values
    return sorted(
        {str(item).strip() for item in raw_values if str(item).strip()},
        key=_event_code_sort_key,
    )


def _event_code_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if str(value).isdigit() else (1, str(value).casefold())


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
    result: list[str] = []
    for selected in selected_files:
        text = str(selected)
        match = resolve_scan_path(text, scanned_files)
        mapped = match.resolved if match.accepted else text
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
    basename_counts: dict[str, int] = {}
    for path in paths:
        name = Path(str(path)).name or str(path)
        basename_counts[name] = basename_counts.get(name, 0) + 1
    compatible_unique_names = {
        text
        for item in excluded
        if (text := str(item)) == (Path(text).name or text)
        and basename_counts.get(text) == 1
    }
    result: list[str] = []
    for path in paths:
        text = str(path)
        name = Path(text).name or text
        if text in excluded_exact or name in compatible_unique_names:
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
    match = resolve_scan_path(text, list(remap))
    if match.accepted and match.resolved:
        return str(remap[match.resolved])
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
    return unresolved_scan_path_descriptions(required, scanned)


def _choice_recipe_trace(choices: dict[str, Any]) -> list[str]:
    traces: list[str] = []
    skip_labels = bool(choices.get("skip_labels"))
    metadata_overrides = choices.get("metadata_overrides")
    if isinstance(metadata_overrides, dict) and metadata_overrides:
        traces.append("choices:metadata_overrides")
    if not skip_labels and _string_mapping(choices.get("class_map")):
        traces.append("choices:class_map")
    if not skip_labels and _string_mapping(choices.get("event_roles")):
        traces.append("choices:event_roles")
    use_external_label_carriers = (
        _label_carrier_source_choice(choices) != "embedded_events" and not skip_labels
    )
    if use_external_label_carriers and (
        _normalize_label_carrier_choices(choices.get("label_carrier_choices"))
        or _string_list(choices.get("required_label_carriers"))
    ):
        traces.append("choices:label_carriers")
    if not skip_labels and _label_carrier_source_choice(choices):
        traces.append("choices:label_carrier")
    if not skip_labels and _string_list(choices.get("label_sources")):
        traces.append("choices:label_sources")
    if not skip_labels and _string_list(choices.get("excluded_label_carriers")):
        traces.append("choices:excluded_label_carriers")
    if skip_labels:
        traces.append("choices:skip_labels")
    if _string_mapping(choices.get("eeg_file_remap")):
        traces.append("choices:eeg_file_remap")
    if not skip_labels and _string_mapping(choices.get("label_carrier_remap")):
        traces.append("choices:label_carrier_remap")
    if not skip_labels and _nested_string_mapping(choices.get("run_event_mappings")):
        traces.append("choices:run_event_mappings")
    if not skip_labels and isinstance(choices.get("internal_event_selection"), dict):
        traces.append("choices:internal_event_selection")
    return traces


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value
