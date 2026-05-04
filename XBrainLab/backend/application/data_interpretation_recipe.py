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
    label_carriers: list[str] = dc_field(default_factory=list)
    label_carrier_plan: list[dict[str, Any]] = dc_field(default_factory=list)
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
    validation_decision: str = "safe"
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
        validation_decision=str(payload.get("validation_decision", "safe")),
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
        label_carriers=list(applied.label_carriers),
        label_carrier_plan=[dict(item) for item in applied.label_carrier_plan],
        metadata=list(applied.metadata),
        format_capabilities=[dict(item) for item in applied.format_capabilities],
        validation_decision=str(applied.validation_decision),
        confirmations=list(applied.confirmations),
        event_roles=dict(applied.event_roles),
        class_map=dict(applied.class_map),
        label_imports=[dict(item) for item in applied.label_imports],
        warnings=list(warnings),
        recipe_trace=[*applied.recipe_trace, f"recipe:{recipe_id}"],
    )


def _string_mapping(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value).strip()
        for key, value in payload.items()
        if str(value).strip()
    }


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
