"""Import recipe serialization for Data Interpretation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from enum import Enum
from pathlib import Path
from typing import Any, cast

from .data_interpretation_metadata import (
    FileMetadataResolution,
    file_metadata_from_dict,
)

IMPORT_RECIPE_MAX_BYTES = 1_048_576


class ImportRecipeTooLargeError(ValueError):
    """Raised when the authoritative recipe reader reaches its byte cap."""

    def __init__(self, *, path: Path, file_bytes_at_least: int) -> None:
        self.path = path
        self.file_bytes_at_least = file_bytes_at_least
        super().__init__(
            "Import recipe exceeds the bounded "
            f"{IMPORT_RECIPE_MAX_BYTES}-byte input limit: {path}.",
        )


@dataclass(frozen=True)
class ImportRecipe:
    """Serializable recipe for replaying a data interpretation."""

    recipe_id: str
    interpretation_id: str
    source_path: str
    source_kind: str
    selected_eeg_files: list[str] = dc_field(default_factory=list)
    label_sources: list[str] = dc_field(default_factory=list)
    label_carriers: list[str] = dc_field(default_factory=list)
    bids: dict[str, Any] = dc_field(default_factory=dict)
    label_carrier_plan: list[dict[str, Any]] = dc_field(default_factory=list)
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
    skip_labels: bool = False
    label_carrier: str = ""
    excluded_label_carriers: list[str] = dc_field(default_factory=list)
    validation_decision: str = "safe"
    confirmations: list[str] = dc_field(default_factory=list)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)
    internal_event_selection: dict[str, Any] = dc_field(default_factory=dict)
    run_event_mappings: dict[str, dict[str, str]] = dc_field(default_factory=dict)
    label_imports: list[dict[str, Any]] = dc_field(default_factory=list)
    content_identity: dict[str, Any] = dc_field(default_factory=dict)
    warnings: list[str] = dc_field(default_factory=list)
    recipe_trace: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)

    def write_json(self, path: str) -> None:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def load_import_recipe(path: str) -> ImportRecipe:
    """Load one recipe through a single bounded binary read."""
    target = Path(path).expanduser()
    with target.open("rb") as handle:
        encoded = handle.read(IMPORT_RECIPE_MAX_BYTES + 1)
    if len(encoded) > IMPORT_RECIPE_MAX_BYTES:
        raise ImportRecipeTooLargeError(
            path=target,
            file_bytes_at_least=len(encoded),
        )
    payload = json.loads(encoded.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Import recipe JSON must contain an object.")
    return import_recipe_from_dict(payload)


def import_recipe_from_dict(payload: dict[str, Any]) -> ImportRecipe:
    """Build an import recipe from a serialized payload."""
    metadata = [
        file_metadata_from_dict(item)
        for item in cast(list[dict[str, Any]], payload.get("metadata", []))
    ]
    skip_labels = bool(payload.get("skip_labels", False))
    return ImportRecipe(
        recipe_id=str(payload.get("recipe_id", "recipe-reloaded")),
        interpretation_id=str(payload.get("interpretation_id", "")),
        source_path=str(payload.get("source_path", "")),
        source_kind=str(payload.get("source_kind", "unknown")),
        selected_eeg_files=[
            str(item) for item in payload.get("selected_eeg_files", [])
        ],
        label_sources=[]
        if skip_labels
        else [str(item) for item in payload.get("label_sources", [])],
        label_carriers=[]
        if skip_labels
        else [str(item) for item in payload.get("label_carriers", [])],
        bids=dict(payload.get("bids") or {})
        if isinstance(payload.get("bids"), dict)
        else {},
        label_carrier_plan=[]
        if skip_labels
        else [
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
        skip_labels=skip_labels,
        label_carrier="" if skip_labels else str(payload.get("label_carrier", "")),
        excluded_label_carriers=[]
        if skip_labels
        else [str(item) for item in payload.get("excluded_label_carriers", [])],
        validation_decision=str(payload.get("validation_decision", "safe")),
        confirmations=[str(item) for item in payload.get("confirmations", [])],
        event_roles={} if skip_labels else _string_mapping(payload.get("event_roles")),
        class_map={} if skip_labels else _string_mapping(payload.get("class_map")),
        internal_event_selection={}
        if skip_labels
        else dict(payload.get("internal_event_selection") or {})
        if isinstance(payload.get("internal_event_selection"), dict)
        else {},
        run_event_mappings={}
        if skip_labels
        else _nested_string_mapping(payload.get("run_event_mappings")),
        label_imports=[]
        if skip_labels
        else [
            dict(item)
            for item in payload.get("label_imports", [])
            if isinstance(item, dict)
        ],
        content_identity={}
        if skip_labels
        else dict(payload.get("content_identity") or {})
        if isinstance(payload.get("content_identity"), dict)
        else {},
        warnings=[str(item) for item in payload.get("warnings", [])],
        recipe_trace=[str(item) for item in payload.get("recipe_trace", [])],
    )


def build_import_recipe(
    *,
    recipe_id: str,
    applied: Any,
    warnings: list[str],
    content_identity: dict[str, Any] | None = None,
) -> ImportRecipe:
    """Build a recipe from an applied interpretation-like object."""
    skip_labels = bool(getattr(applied, "skip_labels", False))
    return ImportRecipe(
        recipe_id=recipe_id,
        interpretation_id=str(applied.interpretation_id),
        source_path=str(applied.source_path),
        source_kind=str(applied.source_kind),
        selected_eeg_files=list(applied.loaded_files),
        label_sources=[]
        if skip_labels
        else list(getattr(applied, "label_sources", [])),
        label_carriers=[] if skip_labels else list(applied.label_carriers),
        bids=dict(getattr(applied, "bids", {}) or {}),
        label_carrier_plan=[]
        if skip_labels
        else [dict(item) for item in applied.label_carrier_plan],
        metadata=list(applied.metadata),
        format_capabilities=[dict(item) for item in applied.format_capabilities],
        skip_labels=skip_labels,
        label_carrier="" if skip_labels else str(getattr(applied, "label_carrier", "")),
        excluded_label_carriers=[
            str(item) for item in getattr(applied, "excluded_label_carriers", [])
        ]
        if not skip_labels
        else [],
        validation_decision=str(applied.validation_decision),
        confirmations=list(applied.confirmations),
        event_roles={} if skip_labels else dict(applied.event_roles),
        class_map={} if skip_labels else dict(applied.class_map),
        internal_event_selection={}
        if skip_labels
        else dict(getattr(applied, "internal_event_selection", {}) or {}),
        run_event_mappings={}
        if skip_labels
        else {
            str(key): dict(value)
            for key, value in getattr(applied, "run_event_mappings", {}).items()
        },
        label_imports=[]
        if skip_labels
        else [dict(item) for item in applied.label_imports],
        content_identity={} if skip_labels else dict(content_identity or {}),
        warnings=list(warnings),
        recipe_trace=[*applied.recipe_trace, f"recipe:{recipe_id}"],
    )


def choices_from_import_recipe(recipe: ImportRecipe) -> dict[str, Any]:
    """Rebuild candidate choices from a saved import recipe."""
    choices: dict[str, Any] = {"recipe_id": recipe.recipe_id}
    if recipe.selected_eeg_files:
        choices["selected_eeg_files"] = list(recipe.selected_eeg_files)
    include_label_choices = not recipe.skip_labels
    if include_label_choices and recipe.label_sources:
        choices["label_sources"] = list(recipe.label_sources)
    if recipe.skip_labels:
        choices["skip_labels"] = True
    if include_label_choices and recipe.label_carrier:
        choices["label_carrier"] = recipe.label_carrier
    if include_label_choices and recipe.excluded_label_carriers:
        choices["excluded_label_carriers"] = list(recipe.excluded_label_carriers)
    required_label_carriers = (
        _required_label_carriers_from_recipe(recipe) if include_label_choices else []
    )
    if required_label_carriers:
        choices["required_label_carriers"] = required_label_carriers
    metadata_overrides = _metadata_overrides_from_recipe(recipe.metadata)
    if metadata_overrides:
        choices["metadata_overrides"] = metadata_overrides
    label_carrier_choices = _label_carrier_choices_from_recipe(
        recipe.label_carrier_plan if include_label_choices else [],
        legacy_class_map=recipe.class_map,
        label_imports=recipe.label_imports if include_label_choices else [],
    )
    if label_carrier_choices:
        choices["label_carrier_choices"] = label_carrier_choices
    if include_label_choices and recipe.event_roles:
        choices["event_roles"] = dict(recipe.event_roles)
    internal_event_recipe = bool(recipe.internal_event_selection) or (
        recipe.label_carrier == "embedded_events"
    )
    if include_label_choices and recipe.class_map and internal_event_recipe:
        choices["class_map"] = dict(recipe.class_map)
    if include_label_choices and recipe.internal_event_selection:
        choices["internal_event_selection"] = dict(recipe.internal_event_selection)
    if include_label_choices and recipe.run_event_mappings:
        choices["run_event_mappings"] = {
            str(key): dict(value) for key, value in recipe.run_event_mappings.items()
        }
    return choices


def _required_label_carriers_from_recipe(recipe: ImportRecipe) -> list[str]:
    carriers: list[str] = []
    for value in recipe.label_carriers:
        text = str(value).strip()
        if text and text not in carriers:
            carriers.append(text)
    for item in recipe.label_carrier_plan:
        if not isinstance(item, dict):
            continue
        text = str(item.get("path") or "").strip()
        if text and text not in carriers:
            carriers.append(text)
    return carriers


def _metadata_overrides_from_recipe(
    metadata: list[FileMetadataResolution],
) -> dict[str, dict[str, str]]:
    overrides: dict[str, dict[str, str]] = {}
    for item in metadata:
        file_key = Path(item.file).name or item.file
        fields: dict[str, str] = {}
        for field_name in ("subject", "session", "task", "run"):
            field_value = getattr(item, field_name)
            value = field_value.override
            if value is None and field_value.source == "user_override":
                value = field_value.value
            if value not in (None, ""):
                fields[field_name] = str(value)
        if fields:
            overrides[file_key] = fields
    return overrides


def _label_carrier_choices_from_recipe(
    label_carrier_plan: list[dict[str, Any]],
    *,
    legacy_class_map: dict[str, str] | None = None,
    label_imports: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    choices: dict[str, dict[str, Any]] = {}
    field_map = {
        "selected_target_file": "target_file",
        "selected_label_field": "label_field",
        "selected_anchor": "anchor",
        "selected_duration_field": "duration_field",
        "time_model": "time_model",
        "placement_method": "placement_method",
        "granularity": "granularity",
        "role": "role",
    }
    for carrier in label_carrier_plan:
        path = str(carrier.get("path") or "").strip()
        if not path:
            continue
        carrier_choices: dict[str, Any] = {
            choice_key: str(carrier.get(recipe_key) or "").strip()
            for recipe_key, choice_key in field_map.items()
            if str(carrier.get(recipe_key) or "").strip()
        }
        target_files = [
            str(item).strip()
            for item in carrier.get("selected_target_files", [])
            if str(item).strip()
        ]
        if target_files:
            carrier_choices["target_files"] = list(dict.fromkeys(target_files))
        target_event_codes = [
            str(item).strip()
            for item in carrier.get("selected_target_event_codes", [])
            if str(item).strip()
        ]
        if target_event_codes:
            carrier_choices["target_event_codes"] = target_event_codes
        raw_value_decisions = carrier.get("value_decisions")
        value_decisions = (
            {
                str(raw_value): dict(decision)
                for raw_value, decision in raw_value_decisions.items()
                if isinstance(decision, dict)
            }
            if isinstance(raw_value_decisions, dict)
            else {}
        )
        if value_decisions:
            carrier_choices["value_decisions"] = value_decisions
        elif legacy_class_map:
            carrier_choices["value_decisions"] = {
                str(raw_value): {
                    "suggested_name": str(class_name),
                    "decision_source": "legacy_recipe_class_map_suggestion",
                    "provenance": "legacy_recipe:class_map",
                }
                for raw_value, class_name in legacy_class_map.items()
                if str(raw_value).strip() and str(class_name).strip()
            }
        if carrier_choices:
            choices[path] = carrier_choices
    _merge_label_import_audit_choices(choices, label_imports or [])
    return choices


def _merge_label_import_audit_choices(
    choices: dict[str, dict[str, Any]],
    label_imports: list[dict[str, Any]],
) -> None:
    """Replay complete legacy label-import choices retained in recipe audit rows."""
    for record in label_imports:
        if not isinstance(record, dict):
            continue
        raw_file_mapping = record.get("file_mapping")
        file_mapping = (
            {
                str(target).strip(): str(carrier).strip()
                for target, carrier in raw_file_mapping.items()
                if str(target).strip() and str(carrier).strip()
            }
            if isinstance(raw_file_mapping, dict)
            else {}
        )
        raw_configs = record.get("label_configs")
        label_configs = (
            {
                str(carrier).strip(): config
                for carrier, config in raw_configs.items()
                if str(carrier).strip() and isinstance(config, dict)
            }
            if isinstance(raw_configs, dict)
            else {}
        )
        carriers = list(
            dict.fromkeys(
                [
                    str(item).strip()
                    for item in record.get("label_carriers", [])
                    if str(item).strip()
                ]
                + list(file_mapping.values())
                + list(label_configs)
            )
        )
        selected_events = sorted(
            {
                str(item).strip()
                for item in record.get("selected_event_names", [])
                if str(item).strip()
            }
        )
        raw_class_map = record.get("class_map")
        class_map = (
            {
                str(raw_value): str(class_name)
                for raw_value, class_name in raw_class_map.items()
                if str(raw_value).strip() and str(class_name).strip()
            }
            if isinstance(raw_class_map, dict)
            else {}
        )
        for carrier in carriers:
            carrier_choices = choices.setdefault(carrier, {})
            config = label_configs.get(carrier, {})
            for source_key, choice_key in (
                ("label_field", "label_field"),
                ("anchor", "anchor"),
                ("duration_field", "duration_field"),
            ):
                value = str(config.get(source_key) or "").strip()
                if value:
                    carrier_choices[choice_key] = value
            targets = sorted(
                target
                for target, mapped_carrier in file_mapping.items()
                if mapped_carrier == carrier
            )
            if targets:
                carrier_choices["target_files"] = targets
                if len(targets) == 1:
                    carrier_choices["target_file"] = targets[0]
                else:
                    carrier_choices.pop("target_file", None)
            if "selected_event_names" in record:
                if selected_events:
                    carrier_choices["target_event_codes"] = selected_events
                else:
                    carrier_choices.pop("target_event_codes", None)
            if class_map:
                audit_decisions = {
                    raw_value: {
                        "role": "stimulus",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": class_name,
                        "suggested_name": class_name,
                        "decision": "resolved",
                        "decision_source": "external_label_mapping",
                        "provenance": "label_import",
                    }
                    for raw_value, class_name in class_map.items()
                }
                reviewed_decisions = carrier_choices.get("value_decisions")
                carrier_choices["value_decisions"] = {
                    **audit_decisions,
                    **(
                        reviewed_decisions
                        if isinstance(reviewed_decisions, dict)
                        else {}
                    ),
                }


def _string_mapping(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value).strip()
        for key, value in payload.items()
        if str(value).strip()
    }


def _nested_string_mapping(payload: Any) -> dict[str, dict[str, str]]:
    if not isinstance(payload, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for outer_key, inner_payload in payload.items():
        inner = _string_mapping(inner_payload)
        if inner:
            result[str(outer_key)] = inner
    return result


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: _serialize(v) for k, v in asdict(cast(Any, value)).items()}
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _serialize(value.to_dict())
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return {k: _serialize(v) for k, v in vars(value).items()}
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value
