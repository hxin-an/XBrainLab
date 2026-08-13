"""Immutable boundaries for two-phase source scan and interpretation review."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from json import dumps as json_dumps
from json import loads as json_loads
from typing import Any

from .commands import (
    PreviewInterpretationCommand,
    ReviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from .data_interpretation_state import InterpretationSessionCheckpoint
from .state import ApplicationStateSnapshot


@dataclass(frozen=True, slots=True)
class ApplicationDiscoveryBoundary:
    """Exact committed application view consumed before detached discovery."""

    publication_generation: int
    publication_revision: int
    state: ApplicationStateSnapshot

    def __post_init__(self) -> None:
        for field_name in ("publication_generation", "publication_revision"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class InterpretationDiscoveryPlan:
    """Session and cache inputs captured during short command admission."""

    command: (
        ScanSourceCommand
        | ReviewInterpretationCommand
        | PreviewInterpretationCommand
        | ValidateInterpretationCommand
    )
    application: ApplicationDiscoveryBoundary
    state_before: InterpretationSessionCheckpoint
    safe_preview_admissions: tuple[tuple[Any, Any], ...]
    bids_dataset_indexes: tuple[tuple[str, Any], ...]

    @classmethod
    def capture(
        cls,
        command: (
            ScanSourceCommand
            | ReviewInterpretationCommand
            | PreviewInterpretationCommand
            | ValidateInterpretationCommand
        ),
        *,
        application: ApplicationDiscoveryBoundary,
        state_before: InterpretationSessionCheckpoint,
        safe_preview_admissions: dict[Any, Any],
        bids_dataset_indexes: dict[str, Any],
    ) -> InterpretationDiscoveryPlan:
        if not isinstance(
            command,
            (
                ScanSourceCommand,
                ReviewInterpretationCommand,
                PreviewInterpretationCommand,
                ValidateInterpretationCommand,
            ),
        ):
            raise TypeError("command must be a Data Interpretation review command")
        return cls(
            command=deepcopy(command),
            application=application,
            state_before=deepcopy(state_before),
            safe_preview_admissions=tuple(safe_preview_admissions.items()),
            bids_dataset_indexes=tuple(bids_dataset_indexes.items()),
        )


@dataclass(frozen=True, slots=True)
class PreparedInterpretationDiscovery:
    """Detached review state and caches ready for one guarded publication."""

    plan: InterpretationDiscoveryPlan
    state_after: InterpretationSessionCheckpoint
    message: str
    diagnostics_json: str
    safe_preview_admissions: tuple[tuple[Any, Any], ...]
    bids_dataset_indexes: tuple[tuple[str, Any], ...]

    @classmethod
    def create(
        cls,
        *,
        plan: InterpretationDiscoveryPlan,
        state_after: InterpretationSessionCheckpoint,
        message: str,
        diagnostics: dict[str, Any],
        safe_preview_admissions: dict[Any, Any],
        bids_dataset_indexes: dict[str, Any],
    ) -> PreparedInterpretationDiscovery:
        normalized_message = str(message).strip()
        if not normalized_message:
            raise ValueError("prepared discovery message cannot be empty")
        return cls(
            plan=plan,
            state_after=deepcopy(state_after),
            message=normalized_message,
            diagnostics_json=json_dumps(
                deepcopy(diagnostics),
                sort_keys=True,
                separators=(",", ":"),
            ),
            safe_preview_admissions=tuple(safe_preview_admissions.items()),
            bids_dataset_indexes=tuple(bids_dataset_indexes.items()),
        )

    def handler_result(self) -> tuple[str, dict[str, Any]]:
        return self.message, json_loads(self.diagnostics_json)


__all__ = [
    "ApplicationDiscoveryBoundary",
    "InterpretationDiscoveryPlan",
    "PreparedInterpretationDiscovery",
]
