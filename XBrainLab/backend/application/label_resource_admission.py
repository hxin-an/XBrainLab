"""Receipt-bound resource admission for external label payloads."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .data_interpretation_path_identity import (
    resolved_path_identity,
    resolved_path_value,
)
from .data_interpretation_resource_reader import AdmittedResourceReader
from .errors import PreconditionError
from .label_resource_reader import AdmittedLabelResourceReader
from .owned_work import owned_work_checkpoint
from .resource_label_estimation import SUPPORTED_EXTERNAL_LABEL_EXTENSIONS

NPY_MAGIC = b"\x93NUMPY"
NPY_SUPPORTED_VERSIONS = frozenset({(1, 0), (2, 0), (3, 0)})


@dataclass(frozen=True, slots=True)
class LabelResourceSpec:
    """One external label path and its parser-affecting configuration."""

    path: str
    label_field: str | None = None
    anchor: str | None = None
    duration_field: str | None = None
    sequence_only: bool = False

    def normalized(self) -> LabelResourceSpec:
        return LabelResourceSpec(
            path=_path_value(self.path),
            label_field=_optional_text(self.label_field),
            anchor=_optional_text(self.anchor),
            duration_field=_optional_text(self.duration_field),
            sequence_only=bool(self.sequence_only),
        )

    def to_scope(self) -> dict[str, Any]:
        normalized = self.normalized()
        return {
            "path": normalized.path,
            "label_field": normalized.label_field,
            "anchor": normalized.anchor,
            "duration_field": normalized.duration_field,
            "sequence_only": normalized.sequence_only,
        }


@dataclass(frozen=True, slots=True)
class AdmittedLabelResourceSession:
    """Backend-only parser session minted after current resource admission."""

    reader: AdmittedLabelResourceReader
    specs: tuple[LabelResourceSpec, ...]
    resource_preflight: dict[str, Any]

    def load(self, path: str) -> Any:
        key = _path_key(path)
        for spec in self.specs:
            if _path_key(spec.path) == key:
                return self.reader.load(
                    spec.path,
                    label_field=spec.label_field,
                    anchor=spec.anchor,
                    duration_field=spec.duration_field,
                    sequence_only=spec.sequence_only,
                )
        raise PreconditionError(
            f"Label resource was not admitted for this command: {path}.",
            diagnostics={"code": "label_resource_not_admitted", "path": key},
        )


def session_from_resource_preflight(
    specs: Iterable[LabelResourceSpec],
    resource_preflight: Any,
) -> AdmittedLabelResourceSession:
    """Bind reviewed label specs to an already-authorized application preflight."""
    owned_work_checkpoint("Normalizing reviewed label resource scope")
    normalized_specs = _normalized_specs(specs)
    paths = [spec.path for spec in normalized_specs]
    resource_count = len(paths)
    for index, path in enumerate(paths):
        owned_work_checkpoint(
            f"Inspecting reviewed label resource {index + 1} of {resource_count}",
            completed=index,
            total=resource_count,
        )
        _inspect_label_resource_paths((path,))
    owned_work_checkpoint("Binding reviewed label resource reader")
    resource_reader = AdmittedResourceReader.from_resource_preflight(
        paths,
        resource_preflight,
    )
    admitted_reader = AdmittedLabelResourceReader(
        resource_reader,
        admitted_specs={
            _path_key(spec.path): spec.to_scope() for spec in normalized_specs
        },
    )
    for index, path in enumerate(paths):
        owned_work_checkpoint(
            f"Verifying reviewed label resource {index + 1} of {resource_count}",
            completed=index,
            total=resource_count,
        )
        # Keep the exact admission guard without reading a discarded payload hash.
        with admitted_reader.open_binary(path, purpose="label content identity"):
            pass
    owned_work_checkpoint(
        "Reviewed label resources admitted",
        completed=resource_count,
        total=resource_count,
    )
    return AdmittedLabelResourceSession(
        reader=admitted_reader,
        specs=normalized_specs,
        resource_preflight={
            **resource_preflight.to_diagnostics(),
            "parser_admission": admitted_reader.diagnostics(),
        },
    )


def _normalized_specs(
    specs: Iterable[LabelResourceSpec],
) -> tuple[LabelResourceSpec, ...]:
    result: list[LabelResourceSpec] = []
    by_path: dict[str, LabelResourceSpec] = {}
    for raw_spec in specs:
        if not isinstance(raw_spec, LabelResourceSpec):
            raise PreconditionError("Label resource specs must be path-based.")
        spec = raw_spec.normalized()
        path_identity = _path_key(spec.path)
        existing = by_path.get(path_identity)
        if existing is not None and existing != spec:
            raise PreconditionError(
                "One label path cannot use conflicting parser configurations.",
                diagnostics={
                    "code": "label_resource_configuration_conflict",
                    "path": spec.path,
                },
            )
        if existing is None:
            by_path[path_identity] = spec
            result.append(spec)
    if not result:
        raise PreconditionError("At least one label path is required.")
    return tuple(result)


def _inspect_label_resource_paths(paths: Iterable[str]) -> None:
    for raw_path in paths:
        path = Path(raw_path)
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTERNAL_LABEL_EXTENSIONS:
            raise PreconditionError(
                f"Label resource format cannot be inspected safely: {path}.",
                diagnostics={
                    "code": "label_resource_format_uninspectable",
                    "path": str(path),
                    "format": suffix,
                    "supported_formats": sorted(SUPPORTED_EXTERNAL_LABEL_EXTENSIONS),
                },
            )
        try:
            opened = path.open("rb")
        except OSError as exc:
            raise PreconditionError(
                f"Label resource is unavailable: {path}.",
                diagnostics={
                    "code": "label_resource_unavailable",
                    "path": str(path),
                },
            ) from exc
        with opened:
            file_stat = os.fstat(opened.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise PreconditionError(
                    f"Label resource is not a regular file: {path}.",
                    diagnostics={
                        "code": "label_resource_uninspectable",
                        "path": str(path),
                    },
                )
            if suffix == ".npy":
                header = opened.read(8)
                if (
                    len(header) != 8
                    or header[:6] != NPY_MAGIC
                    or tuple(header[6:8]) not in NPY_SUPPORTED_VERSIONS
                ):
                    raise PreconditionError(
                        f"NumPy label resource could not be inspected: {path}.",
                        diagnostics={
                            "code": "label_resource_uninspectable",
                            "path": str(path),
                            "format": ".npy",
                        },
                    )


def _path_key(path: str | Path) -> str:
    return resolved_path_identity(path)


def _path_value(path: str | Path) -> str:
    return resolved_path_value(path)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
