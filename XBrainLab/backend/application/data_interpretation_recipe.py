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
    """Load an import recipe from a JSON file."""
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    return import_recipe_from_dict(payload)


def import_recipe_from_dict(payload: dict[str, Any]) -> ImportRecipe:
    """Build an import recipe from a serialized payload."""
    metadata = [
        file_metadata_from_dict(item)
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
        label_sources=[str(item) for item in payload.get("label_sources", [])],
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
        skip_labels=bool(payload.get("skip_labels", False)),
        label_carrier=str(payload.get("label_carrier", "")),
        excluded_label_carriers=[
            str(item) for item in payload.get("excluded_label_carriers", [])
        ],
        validation_decision=str(payload.get("validation_decision", "safe")),
        confirmations=[str(item) for item in payload.get("confirmations", [])],
        event_roles=_string_mapping(payload.get("event_roles")),
        class_map=_string_mapping(payload.get("class_map")),
        internal_event_selection=dict(payload.get("internal_event_selection") or {})
        if isinstance(payload.get("internal_event_selection"), dict)
        else {},
        run_event_mappings=_nested_string_mapping(payload.get("run_event_mappings")),
        label_imports=[
            dict(item)
            for item in payload.get("label_imports", [])
            if isinstance(item, dict)
        ],
        warnings=[str(item) for item in payload.get("warnings", [])],
        recipe_trace=[str(item) for item in payload.get("recipe_trace", [])],
    )


def build_import_recipe(
    *,
    recipe_id: str,
    applied: Any,
    warnings: list[str],
) -> ImportRecipe:
    """Build a recipe from an applied interpretation-like object."""
    return ImportRecipe(
        recipe_id=recipe_id,
        interpretation_id=str(applied.interpretation_id),
        source_path=str(applied.source_path),
        source_kind=str(applied.source_kind),
        selected_eeg_files=list(applied.loaded_files),
        label_sources=list(getattr(applied, "label_sources", [])),
        label_carriers=list(applied.label_carriers),
        label_carrier_plan=[dict(item) for item in applied.label_carrier_plan],
        metadata=list(applied.metadata),
        format_capabilities=[dict(item) for item in applied.format_capabilities],
        skip_labels=bool(getattr(applied, "skip_labels", False)),
        label_carrier=str(getattr(applied, "label_carrier", "")),
        excluded_label_carriers=[
            str(item) for item in getattr(applied, "excluded_label_carriers", [])
        ],
        validation_decision=str(applied.validation_decision),
        confirmations=list(applied.confirmations),
        event_roles=dict(applied.event_roles),
        class_map=dict(applied.class_map),
        internal_event_selection=dict(
            getattr(applied, "internal_event_selection", {}) or {}
        ),
        run_event_mappings={
            str(key): dict(value)
            for key, value in getattr(applied, "run_event_mappings", {}).items()
        },
        label_imports=[dict(item) for item in applied.label_imports],
        warnings=list(warnings),
        recipe_trace=[*applied.recipe_trace, f"recipe:{recipe_id}"],
    )


def choices_from_import_recipe(recipe: ImportRecipe) -> dict[str, Any]:
    """Rebuild candidate choices from a saved import recipe."""
    choices: dict[str, Any] = {"recipe_id": recipe.recipe_id}
    if recipe.selected_eeg_files:
        choices["selected_eeg_files"] = list(recipe.selected_eeg_files)
    if recipe.label_sources:
        choices["label_sources"] = list(recipe.label_sources)
    if recipe.skip_labels:
        choices["skip_labels"] = True
    if recipe.label_carrier:
        choices["label_carrier"] = recipe.label_carrier
    if recipe.excluded_label_carriers:
        choices["excluded_label_carriers"] = list(recipe.excluded_label_carriers)
    required_label_carriers = _required_label_carriers_from_recipe(recipe)
    if required_label_carriers:
        choices["required_label_carriers"] = required_label_carriers
    metadata_overrides = _metadata_overrides_from_recipe(recipe.metadata)
    if metadata_overrides:
        choices["metadata_overrides"] = metadata_overrides
    label_carrier_choices = _label_carrier_choices_from_recipe(
        recipe.label_carrier_plan,
    )
    if label_carrier_choices:
        choices["label_carrier_choices"] = label_carrier_choices
    if recipe.event_roles:
        choices["event_roles"] = dict(recipe.event_roles)
    if recipe.class_map:
        choices["class_map"] = dict(recipe.class_map)
    if recipe.internal_event_selection:
        choices["internal_event_selection"] = dict(recipe.internal_event_selection)
    if recipe.run_event_mappings:
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
        target_event_codes = [
            str(item).strip()
            for item in carrier.get("selected_target_event_codes", [])
            if str(item).strip()
        ]
        if target_event_codes:
            carrier_choices["target_event_codes"] = target_event_codes
        if carrier_choices:
            choices[path] = carrier_choices
    return choices


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
