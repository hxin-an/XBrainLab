"""Immutable admission and payloads for two-phase preprocessing commands."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from XBrainLab.backend.services.dataset_state_service import PreparedChannelSelection
from XBrainLab.backend.services.preprocess_state_service import PreparedPreprocessData
from XBrainLab.backend.training_state_contract import TrainingPipelineMutationBoundary

from .commands import CreateEpochCommand, PreprocessCommand
from .pipeline_transaction import (
    PipelineStateIdentity,
    PipelineStateSnapshot,
)
from .state import ApplicationStateSnapshot


@dataclass(frozen=True, slots=True)
class ApplicationPreprocessBoundary:
    """Exact committed application view consumed before detached preparation."""

    publication_generation: int
    publication_revision: int
    state: ApplicationStateSnapshot

    def __post_init__(self) -> None:
        for field_name in ("publication_generation", "publication_revision"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class PreprocessMutationPlan:
    """Stable identities admitted under the short initial command lock."""

    command: PreprocessCommand | CreateEpochCommand
    application: ApplicationPreprocessBoundary
    training: TrainingPipelineMutationBoundary
    training_startup_snapshot: Any
    pipeline_snapshot: PipelineStateSnapshot
    pipeline_identity: PipelineStateIdentity

    @classmethod
    def capture(
        cls,
        command: PreprocessCommand | CreateEpochCommand,
        *,
        application: ApplicationPreprocessBoundary,
        training: TrainingPipelineMutationBoundary,
        training_startup_snapshot: Any,
        pipeline_snapshot: PipelineStateSnapshot,
    ) -> PreprocessMutationPlan:
        if not isinstance(command, (PreprocessCommand, CreateEpochCommand)):
            raise TypeError("command must be a preprocessing or epoch command")
        return cls(
            command=deepcopy(command),
            application=application,
            training=training,
            training_startup_snapshot=training_startup_snapshot,
            pipeline_snapshot=pipeline_snapshot,
            pipeline_identity=PipelineStateIdentity.from_snapshot(pipeline_snapshot),
        )


@dataclass(frozen=True, slots=True)
class PreparedPreprocessCommand:
    """Detached transformed EEG data plus its immutable public result details."""

    plan: PreprocessMutationPlan
    prepared_data: PreparedPreprocessData | PreparedChannelSelection
    message: str
    diagnostics_json: str

    @classmethod
    def create(
        cls,
        *,
        plan: PreprocessMutationPlan,
        prepared_data: PreparedPreprocessData | PreparedChannelSelection,
        message: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> PreparedPreprocessCommand:
        if not isinstance(plan, PreprocessMutationPlan):
            raise TypeError("plan must be PreprocessMutationPlan")
        if not isinstance(
            prepared_data,
            (PreparedPreprocessData, PreparedChannelSelection),
        ):
            raise TypeError("prepared_data has an invalid preprocessing type")
        normalized_message = str(message).strip()
        if not normalized_message:
            raise ValueError("prepared preprocessing message cannot be empty")
        return cls(
            plan=plan,
            prepared_data=prepared_data,
            message=normalized_message,
            diagnostics_json=json.dumps(
                deepcopy(diagnostics or {}),
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    def handler_result(self) -> str | tuple[str, dict[str, Any]]:
        diagnostics = json.loads(self.diagnostics_json)
        if not diagnostics:
            return self.message
        return self.message, diagnostics


__all__ = [
    "ApplicationPreprocessBoundary",
    "PreparedPreprocessCommand",
    "PreprocessMutationPlan",
]
