"""Data interpretation lifecycle objects for the application command layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from enum import Enum
from typing import Any, cast

from . import data_interpretation_candidate as _candidate
from . import data_interpretation_metadata as _metadata
from . import data_interpretation_recipe as _recipe
from . import data_interpretation_review as _review
from . import data_interpretation_scan as _scan
from .data_interpretation_metadata import (
    FileMetadataResolution,
)

ImportRecipe = _recipe.ImportRecipe
InterpretationCandidate = _candidate.InterpretationCandidate
InterpretationPreview = _review.InterpretationPreview
MetadataFieldResolution = _metadata.MetadataFieldResolution
ScanResult = _scan.ScanResult
ValidationDecision = _review.ValidationDecision
build_interpretation_candidate = _candidate.build_interpretation_candidate
build_import_recipe = _recipe.build_import_recipe
choices_from_import_recipe = _recipe.choices_from_import_recipe
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
class AppliedInterpretation:
    """Applied data interpretation that becomes downstream workflow truth."""

    interpretation_id: str
    candidate_id: str
    source_path: str
    source_kind: str
    loaded_files: list[str] = dc_field(default_factory=list)
    label_sources: list[str] = dc_field(default_factory=list)
    label_carriers: list[str] = dc_field(default_factory=list)
    label_carrier_plan: list[dict[str, Any]] = dc_field(default_factory=list)
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
    skip_labels: bool = False
    label_carrier: str = ""
    excluded_label_carriers: list[str] = dc_field(default_factory=list)
    validation_decision: str = InterpretationDecision.SAFE.value
    confirmations: list[str] = dc_field(default_factory=list)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)
    run_event_mappings: dict[str, dict[str, str]] = dc_field(default_factory=dict)
    label_imports: list[dict[str, Any]] = dc_field(default_factory=list)
    recipe_trace: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


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
