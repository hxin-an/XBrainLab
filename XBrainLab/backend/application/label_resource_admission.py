"""Receipt-bound resource admission for external label payloads."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterable, Mapping
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
from .label_resource_receipt import LabelResourceReceiptAuthority
from .owned_work import owned_work_checkpoint
from .resource_guard import check_import_resource_preflight
from .resource_label_estimation import SUPPORTED_EXTERNAL_LABEL_EXTENSIONS
from .resource_receipt import (
    fingerprint_resource_preflight,
    fingerprint_resource_scope,
)

LABEL_CONTENT_HASH_CHUNK_BYTES = 1024 * 1024
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
    _content_identities: tuple[dict[str, Any], ...]

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

    def assert_current(self, *, purpose: str) -> None:
        """Verify that every admitted file still has its preview identity."""
        _assert_content_identities_current(
            self._content_identities,
            purpose=purpose,
        )
        self.reader.assert_current(
            [spec.path for spec in self.specs],
            purpose=purpose,
        )


class LabelResourceAdmissionService:
    """Preflight, bind, authorize, and expose one bounded label reader."""

    def __init__(self, *, command_name: str) -> None:
        self.command_name = str(command_name)
        self._receipts = LabelResourceReceiptAuthority(command_name=command_name)

    def admit(
        self,
        specs: Iterable[LabelResourceSpec],
        *,
        confirmed: bool,
        token: str | None,
        configuration: Mapping[str, Any] | None = None,
    ) -> AdmittedLabelResourceSession:
        """Return a bounded parser session or fail before parser entry."""
        normalized_specs = _normalized_specs(specs)
        paths = [spec.path for spec in normalized_specs]
        _inspect_label_resource_paths(paths)
        preflight = check_import_resource_preflight(paths)
        self._receipts.enforce_blocking(token=token, preflight=preflight)
        resource_reader = AdmittedResourceReader.from_resource_preflight(
            paths,
            preflight,
        )
        admitted_reader = AdmittedLabelResourceReader(
            resource_reader,
            admitted_specs={
                _path_key(spec.path): spec.to_scope() for spec in normalized_specs
            },
        )
        content_identities = [
            _content_identity(path, reader=admitted_reader) for path in paths
        ]
        configuration_fingerprint = fingerprint_resource_scope(
            {
                "command": self.command_name,
                "configuration": dict(configuration or {}),
                "label_specs": [spec.to_scope() for spec in normalized_specs],
            }
        )
        preflight_fingerprint = fingerprint_resource_preflight(preflight)
        scope_fingerprint = fingerprint_resource_scope(
            {
                "command": self.command_name,
                "configuration_fingerprint": configuration_fingerprint,
                "content_identities": content_identities,
            }
        )
        receipt_reused = self._receipts.authorize(
            confirmed=confirmed,
            token=token,
            preflight=preflight,
            scope_fingerprint=scope_fingerprint,
            configuration_fingerprint=configuration_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
        )
        diagnostics = {
            **preflight.to_diagnostics(),
            "configuration_fingerprint": configuration_fingerprint,
            "preflight_fingerprint": preflight_fingerprint,
            "scope_fingerprint": scope_fingerprint,
            "confirmation_receipt_reused": receipt_reused,
            "parser_admission": admitted_reader.diagnostics(),
        }
        return AdmittedLabelResourceSession(
            reader=admitted_reader,
            specs=normalized_specs,
            resource_preflight=diagnostics,
            _content_identities=tuple(content_identities),
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
    content_identities: list[dict[str, Any]] = []
    for index, path in enumerate(paths):
        owned_work_checkpoint(
            f"Verifying reviewed label resource {index + 1} of {resource_count}",
            completed=index,
            total=resource_count,
        )
        content_identities.append(_content_identity(path, reader=admitted_reader))
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
        _content_identities=tuple(content_identities),
    )


def specs_from_paths(
    paths: Iterable[str],
    *,
    configs: Mapping[str, Mapping[str, Any]] | None = None,
    sequence_only: bool = False,
) -> tuple[LabelResourceSpec, ...]:
    """Build parser specs from public command paths and plain config maps."""
    normalized_configs = {
        _path_key(path): dict(value)
        for path, value in (configs or {}).items()
        if isinstance(value, Mapping)
    }
    result: list[LabelResourceSpec] = []
    for path in paths:
        key = _path_key(path)
        config = normalized_configs.get(key, {})
        result.append(
            LabelResourceSpec(
                path=_path_value(path),
                label_field=_optional_text(config.get("label_field")),
                anchor=_optional_text(config.get("anchor")),
                duration_field=_optional_text(config.get("duration_field")),
                sequence_only=bool(config.get("sequence_only", sequence_only)),
            )
        )
    return tuple(result)


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


def _content_identity(
    path: str,
    *,
    reader: AdmittedLabelResourceReader,
) -> dict[str, Any]:
    digest = hashlib.sha256()
    total = 0
    with reader.open_binary(path, purpose="label content identity") as handle:
        while chunk := handle.read(LABEL_CONTENT_HASH_CHUNK_BYTES):
            digest.update(chunk)
            total += len(chunk)
    return {
        "path": _path_value(path),
        "file_bytes": total,
        "sha256": digest.hexdigest(),
    }


def _assert_content_identities_current(
    expected_identities: Iterable[Mapping[str, Any]],
    *,
    purpose: str,
) -> None:
    for expected in expected_identities:
        path = _path_value(str(expected.get("path") or ""))
        expected_bytes = int(expected.get("file_bytes") or 0)
        observed = _current_content_identity(path, expected_bytes=expected_bytes)
        if observed["file_bytes"] == expected_bytes and observed[
            "sha256"
        ] == expected.get("sha256"):
            continue
        changed_fields = []
        if observed["file_bytes"] != expected_bytes:
            changed_fields.append("file_bytes")
        if observed["sha256"] != expected.get("sha256"):
            changed_fields.append("sha256")
        raise PreconditionError(
            f"A selected label file changed after resource admission: {path}.",
            diagnostics={
                "code": "interpretation_resource_changed_after_admission",
                "path": path,
                "purpose": purpose,
                "parse_started": False,
                "admitted_bytes": expected_bytes,
                "observed_bytes": observed["file_bytes"],
                "changed_fields": changed_fields,
            },
        )


def _current_content_identity(
    path: str,
    *,
    expected_bytes: int,
) -> dict[str, Any]:
    digest = hashlib.sha256()
    total = 0
    try:
        with open(path, "rb") as handle:
            file_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise PreconditionError(
                    f"A selected label path is not a regular file: {path}.",
                    diagnostics={
                        "code": "interpretation_resource_changed_after_admission",
                        "path": path,
                        "parse_started": False,
                    },
                )
            observed_bytes = max(int(file_stat.st_size), 0)
            read_limit = min(observed_bytes, max(expected_bytes, 0))
            while total < read_limit:
                chunk = handle.read(
                    min(LABEL_CONTENT_HASH_CHUNK_BYTES, read_limit - total)
                )
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
    except OSError as exc:
        raise PreconditionError(
            f"A selected label file is unavailable during commit: {path}.",
            diagnostics={
                "code": "interpretation_resource_changed_after_admission",
                "path": path,
                "parse_started": False,
            },
        ) from exc
    return {
        "path": _path_value(path),
        "file_bytes": observed_bytes,
        "sha256": digest.hexdigest() if total == observed_bytes else "",
    }


def _path_key(path: str | Path) -> str:
    return resolved_path_identity(path)


def _path_value(path: str | Path) -> str:
    return resolved_path_value(path)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
