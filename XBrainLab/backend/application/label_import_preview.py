"""Backend-owned materialization for legacy label preview and commit."""

from __future__ import annotations

import math
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .commands import LabelImportPlan
from .errors import PreconditionError
from .label_import_policy import (
    MAX_LABEL_MAPPING_CARDINALITY,
    MAX_LABEL_PREVIEW_FILES,
    MAX_LABEL_PREVIEW_PATH_LENGTH,
    MAX_LABEL_PREVIEW_TEXT_LENGTH,
    LabelMaterializationReview,
    enforce_label_file_count,
    enforce_public_label_mapping_cardinality,
    materialize_reviewed_label_map,
)
from .label_resource_admission import (
    AdmittedLabelResourceSession,
    LabelResourceAdmissionService,
    LabelResourceSpec,
    specs_from_paths,
)


@dataclass(frozen=True, slots=True)
class MaterializedLabelImport:
    """Private payload retained only inside the ApplicationService boundary."""

    label_map: dict[str, Any]
    specs: tuple[LabelResourceSpec, ...]
    resource_preflight: dict[str, Any]
    preview_id: str | None = None


@dataclass(frozen=True, slots=True, eq=False)
class LabelPreviewTargetIdentity:
    """Private binding to one exact dataset session and ordered raw generation."""

    dataset: object
    raw_targets: tuple[object, ...]
    raw_paths: tuple[str, ...]

    def matches(self, other: LabelPreviewTargetIdentity) -> bool:
        return (
            self.dataset is other.dataset
            and self.raw_paths == other.raw_paths
            and len(self.raw_targets) == len(other.raw_targets)
            and all(
                expected is current
                for expected, current in zip(
                    self.raw_targets,
                    other.raw_targets,
                    strict=True,
                )
            )
        )


@dataclass(frozen=True, slots=True)
class _CachedLabelPreview:
    preview_id: str
    session: AdmittedLabelResourceSession
    materialized: MaterializedLabelImport
    summary: dict[str, Any]
    target_identity: LabelPreviewTargetIdentity


class LabelImportPreviewService:
    """Own one bounded preview payload and consume it into an exact import."""

    def __init__(self, *, command_name: str) -> None:
        self._admission = LabelResourceAdmissionService(command_name=command_name)
        self._latest: _CachedLabelPreview | None = None

    def preview(
        self,
        *,
        label_paths: list[str],
        label_configs: Mapping[str, Mapping[str, Any]] | None,
        confirmed: bool,
        token: str | None,
        target_identity: LabelPreviewTargetIdentity,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self._latest = None
        _validate_preview_request(label_paths, label_configs)
        specs = specs_from_paths(label_paths, configs=label_configs)
        _validate_preview_specs(specs)
        session = self._admission.admit(
            specs,
            confirmed=confirmed,
            token=token,
            configuration={
                "purpose": "label_import_preview",
                "label_specs": [spec.to_scope() for spec in specs],
            },
        )
        label_map, review = materialize_reviewed_label_map(
            (spec.path for spec in specs),
            load=session.load,
            error_code="label_preview_cardinality_exceeded",
            normalize_value=_python_scalar,
            validate_value=lambda value, path: _validate_public_label_value(
                value,
                path=path,
            ),
        )
        preview_id = f"label-preview-{secrets.token_urlsafe(24)}"
        summary = _preview_summary(
            preview_id=preview_id,
            specs=specs,
            review=review,
        )
        materialized = MaterializedLabelImport(
            label_map=label_map,
            specs=specs,
            resource_preflight=session.resource_preflight,
            preview_id=preview_id,
        )
        self._latest = _CachedLabelPreview(
            preview_id=preview_id,
            session=session,
            materialized=materialized,
            summary=summary,
            target_identity=target_identity,
        )
        return summary, session.resource_preflight

    def materialize(
        self,
        *,
        plan: LabelImportPlan,
        confirmed: bool,
        token: str | None,
        configuration: Mapping[str, Any],
        target_identity: LabelPreviewTargetIdentity,
    ) -> MaterializedLabelImport:
        if plan.preview_id:
            materialized = self._consume_preview(
                plan,
                target_identity=target_identity,
            )
            enforce_public_label_mapping_cardinality(plan.mapping)
            return materialized
        enforce_public_label_mapping_cardinality(plan.mapping)
        specs = specs_from_paths(
            plan.label_paths,
            configs=plan.label_configs,
            sequence_only=str(plan.mode or "").strip() == "sequence",
        )
        session = self._admission.admit(
            specs,
            confirmed=confirmed,
            token=token,
            configuration=configuration,
        )
        label_map, _review = materialize_reviewed_label_map(
            (spec.path for spec in specs),
            load=session.load,
            error_code="label_mapping_cardinality_exceeded",
            normalize_value=_python_scalar,
        )
        return MaterializedLabelImport(
            label_map=label_map,
            specs=specs,
            resource_preflight=session.resource_preflight,
        )

    def _consume_preview(
        self,
        plan: LabelImportPlan,
        *,
        target_identity: LabelPreviewTargetIdentity,
    ) -> MaterializedLabelImport:
        cached = self._latest
        if cached is None or cached.preview_id != plan.preview_id:
            raise PreconditionError(
                "The label preview is missing or has already been consumed.",
                diagnostics={"code": "label_preview_unavailable"},
            )
        self._latest = None
        if not cached.target_identity.matches(target_identity):
            raise PreconditionError(
                "The active EEG dataset changed after the label preview.",
                diagnostics={"code": "label_preview_unavailable"},
            )
        requested_specs = specs_from_paths(
            plan.label_paths,
            configs=plan.label_configs,
        )
        if requested_specs != cached.materialized.specs:
            raise PreconditionError(
                "The label import paths or parser configuration changed after preview.",
                diagnostics={"code": "label_preview_scope_mismatch"},
            )
        reviewed_mode = str(cached.summary.get("mode") or "").strip()
        requested_mode = str(plan.mode or "").strip()
        if requested_mode != reviewed_mode:
            raise PreconditionError(
                "The label import mode changed after preview.",
                diagnostics={
                    "code": "label_preview_scope_mismatch",
                    "reviewed_mode": reviewed_mode,
                    "requested_mode": requested_mode,
                },
            )
        cached.session.assert_current(purpose="label preview commit")
        return cached.materialized


def _preview_summary(
    *,
    preview_id: str,
    specs: tuple[LabelResourceSpec, ...],
    review: LabelMaterializationReview,
) -> dict[str, Any]:
    file_summaries = [
        {**file_summary, "name": Path(str(file_summary["path"])).name}
        for file_summary in review.files
    ]
    return {
        "preview_id": preview_id,
        "label_paths": [spec.path for spec in specs],
        "label_configs": {
            spec.path: {
                "label_field": spec.label_field,
                "anchor": spec.anchor,
                "duration_field": spec.duration_field,
                "sequence_only": spec.sequence_only,
            }
            for spec in specs
        },
        "files": file_summaries,
        "mode": review.mode,
        "target_count": review.target_count,
        "total_label_count": review.total_label_count,
        "mapping_cardinality_limit": MAX_LABEL_MAPPING_CARDINALITY,
        "file_count_limit": MAX_LABEL_PREVIEW_FILES,
        "text_length_limit": MAX_LABEL_PREVIEW_TEXT_LENGTH,
        "unique_labels": sorted(review.unique_labels, key=_label_sort_key),
    }


def _validate_preview_specs(specs: tuple[LabelResourceSpec, ...]) -> None:
    _enforce_preview_file_count(len(specs))
    for spec in specs:
        _validate_preview_text(
            spec.path,
            field="path",
            path=spec.path,
            limit=MAX_LABEL_PREVIEW_PATH_LENGTH,
        )
        for field, value in (
            ("label_field", spec.label_field),
            ("anchor", spec.anchor),
            ("duration_field", spec.duration_field),
        ):
            if value is not None:
                _validate_preview_text(value, field=field, path=spec.path)


def _validate_preview_request(
    label_paths: list[str],
    label_configs: Mapping[str, Mapping[str, Any]] | None,
) -> None:
    _enforce_preview_file_count(len(label_paths))
    for raw_path in [*label_paths, *(label_configs or {})]:
        _validate_preview_text(
            str(raw_path),
            field="path",
            path=None,
            limit=MAX_LABEL_PREVIEW_PATH_LENGTH,
        )


def _enforce_preview_file_count(observed_count: int) -> None:
    enforce_label_file_count(
        observed_count,
        code="label_preview_file_count_exceeded",
    )


def _validate_public_label_value(value: Any, *, path: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise PreconditionError(
            "The selected label field contains a non-finite class or event code. "
            "Select a clean label field or convert the source before retrying.",
            diagnostics={
                "code": "label_preview_value_unsupported",
                "path": path,
                "value_type": type(value).__name__,
            },
        )
    if value is not None and not isinstance(value, (bool, int, float, str)):
        raise PreconditionError(
            "The selected label field contains a value that cannot be mapped as a "
            "class or event code. Select a scalar label field and retry.",
            diagnostics={
                "code": "label_preview_value_unsupported",
                "path": path,
                "value_type": type(value).__name__,
            },
        )
    _validate_preview_text(str(value), field="unique_label", path=path)


def _validate_preview_text(
    value: str,
    *,
    field: str,
    path: str | None,
    limit: int = MAX_LABEL_PREVIEW_TEXT_LENGTH,
) -> None:
    observed_length = len(value)
    if observed_length <= limit:
        return
    suggestions = (
        [
            "select the label field that contains compact class or event codes",
            "convert verbose values to bounded class or event codes",
        ]
        if field == "unique_label"
        else ["use shorter label paths and parser field names"]
    )
    diagnostics: dict[str, Any] = {
        "code": "label_preview_text_too_long",
        "field": field,
        "observed_length": observed_length,
        "limit": limit,
        "suggestions": suggestions,
    }
    if path is not None:
        diagnostics["path"] = path
    raise PreconditionError(
        f"A {field.replace('_', ' ')} value is too long for the external label "
        f"mapping editor ({observed_length} characters; limit {limit}). Select a "
        "compact label field or convert the source before retrying.",
        diagnostics=diagnostics,
    )


def _python_scalar(value: Any) -> Any:
    return value.item() if isinstance(value, np.generic) else value


def _label_sort_key(value: Any) -> tuple[int, Any]:
    if isinstance(value, int) and not isinstance(value, bool):
        return (0, value)
    if isinstance(value, float) and value.is_integer():
        return (0, int(value))
    return (1, str(value))
