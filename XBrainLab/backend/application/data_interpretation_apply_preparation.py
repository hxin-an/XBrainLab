"""Immutable admission and prepared payloads for two-phase interpretation apply."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from XBrainLab.backend.services.dataset_state_service import PreparedDatasetImport
from XBrainLab.backend.training_state_contract import TrainingPipelineMutationBoundary

from .commands import ApplyInterpretationCommand
from .data_interpretation import InterpretationCandidate, ValidationDecision
from .data_interpretation_state import (
    InterpretationApplyCheckpoint,
    InterpretationSessionIdentity,
)
from .errors import PreconditionError
from .label_resource_admission import AdmittedLabelResourceSession
from .pipeline_transaction import PipelineStateIdentity, PipelineStateSnapshot
from .resource_guard import ResourcePreflightResult
from .state import ApplicationStateSnapshot


@dataclass(frozen=True, slots=True)
class ApplicationApplyBoundary:
    """Last verified application generation consumed by one prepare phase."""

    publication_generation: int
    publication_revision: int
    state: ApplicationStateSnapshot

    def __post_init__(self) -> None:
        for field_name in ("publication_generation", "publication_revision"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class SourceFileBoundary:
    """Exact digest plus cheap final token for one verified source file."""

    path: str
    role: str
    sha256: str
    device: int
    inode: int
    file_bytes: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def capture(
        cls,
        raw_path: str,
        *,
        role: str,
        sha256: str,
        file_bytes: int,
    ) -> SourceFileBoundary:
        path = Path(raw_path).expanduser().resolve(strict=True)
        stat = path.stat()
        normalized_digest = str(sha256 or "").strip().lower()
        if len(normalized_digest) != 64 or any(
            character not in "0123456789abcdef" for character in normalized_digest
        ):
            raise ValueError("Verified source SHA-256 identity is invalid.")
        if type(file_bytes) is not int or file_bytes < 0:
            raise ValueError("Verified source byte count is invalid.")
        if int(stat.st_size) != file_bytes:
            raise OSError("Verified source size changed before admission.")
        return cls(
            path=str(path),
            role=str(role),
            sha256=normalized_digest,
            device=int(stat.st_dev),
            inode=int(stat.st_ino),
            file_bytes=file_bytes,
            modified_ns=int(stat.st_mtime_ns),
            changed_ns=int(stat.st_ctime_ns),
        )


@dataclass(frozen=True, slots=True)
class InterpretationApplyPlan:
    """Immutable identities captured under the short initial command admission."""

    command: ApplyInterpretationCommand
    candidate: InterpretationCandidate
    decision: ValidationDecision
    content_scope_sha256: str
    application: ApplicationApplyBoundary
    training: TrainingPipelineMutationBoundary
    training_startup_snapshot: Any
    pipeline_snapshot: PipelineStateSnapshot
    pipeline_identity: PipelineStateIdentity
    interpretation_identity: InterpretationSessionIdentity


@dataclass(frozen=True, slots=True)
class PreparedInterpretationApply:
    """Detached Raw and interpretation state ready for one guarded commit."""

    plan: InterpretationApplyPlan
    dataset: PreparedDatasetImport
    interpretation_state_after: InterpretationApplyCheckpoint
    resource_preflight: ResourcePreflightResult
    resource_preflight_receipt_reused: bool
    label_resources: AdmittedLabelResourceSession | None
    source_files: tuple[SourceFileBoundary, ...]
    source_identity_apply: tuple[dict[str, Any], ...]
    channels_apply: tuple[dict[str, Any], ...]
    metadata_apply: tuple[dict[str, str], ...]
    label_apply: dict[str, Any]
    internal_epoch_hints: tuple[dict[str, Any], ...]


def capture_source_file_boundaries(
    content_identity: Mapping[str, Any],
) -> tuple[SourceFileBoundary, ...]:
    """Capture exact verified digests and a cheap post-hash stat token."""
    files = content_identity.get("files")
    if not isinstance(files, list):
        return ()
    rows = sorted(
        (
            item
            for item in files
            if isinstance(item, Mapping) and str(item.get("path") or "").strip()
        ),
        key=lambda item: str(item.get("path") or ""),
    )
    try:
        return tuple(_capture_source_identity_row(item) for item in rows)
    except (OSError, TypeError, ValueError) as exc:
        raise PreconditionError(
            "A reviewed import resource became unavailable before apply commit.",
            diagnostics={
                "code": "interpretation_apply_resource_unavailable",
                "state_preserved": True,
            },
        ) from exc


def _capture_source_identity_row(
    item: Mapping[str, Any],
) -> SourceFileBoundary:
    file_bytes = item.get("file_bytes")
    if type(file_bytes) is not int:
        raise ValueError("Verified source byte count is invalid.")
    return SourceFileBoundary.capture(
        str(item.get("path") or ""),
        role=str(item.get("role") or ""),
        sha256=str(item.get("sha256") or ""),
        file_bytes=file_bytes,
    )


def assert_source_file_boundaries_current(
    expected: tuple[SourceFileBoundary, ...],
) -> None:
    """Reject any ordinary post-hash change before the short commit section."""
    try:
        observed = tuple(
            SourceFileBoundary.capture(
                item.path,
                role=item.role,
                sha256=item.sha256,
                file_bytes=item.file_bytes,
            )
            for item in expected
        )
    except (OSError, TypeError, ValueError) as exc:
        raise PreconditionError(
            "A reviewed import resource changed before apply commit. Review again.",
            diagnostics={
                "code": "interpretation_apply_resource_changed",
                "state_preserved": True,
            },
        ) from exc
    if observed != expected:
        raise PreconditionError(
            "A reviewed import resource changed before apply commit. Review again.",
            diagnostics={
                "code": "interpretation_apply_resource_changed",
                "state_preserved": True,
            },
        )


def assert_source_content_boundaries_match(
    expected_identity: Mapping[str, Any],
    observed: tuple[SourceFileBoundary, ...],
) -> None:
    """Reject a prepared payload not bound to every reviewed SHA-256 digest."""
    files = expected_identity.get("files")
    expected = (
        sorted(
            (
                str(item.get("path") or ""),
                str(item.get("role") or ""),
                str(item.get("sha256") or "").strip().lower(),
                item.get("file_bytes"),
            )
            for item in files
            if isinstance(item, Mapping) and str(item.get("path") or "").strip()
        )
        if isinstance(files, list)
        else []
    )
    actual = sorted(
        (item.path, item.role, item.sha256, item.file_bytes) for item in observed
    )
    if actual != expected:
        raise PreconditionError(
            "Prepared import content identity is incomplete. Review again.",
            diagnostics={
                "code": "interpretation_apply_content_identity_incomplete",
                "state_preserved": True,
            },
        )
