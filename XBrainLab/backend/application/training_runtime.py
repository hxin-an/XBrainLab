"""Typed application boundary over Study-owned training runtime state."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from XBrainLab.backend.exceptions import StaleTrainingPipelineMutationError
from XBrainLab.backend.training_manager import (
    PostTrainingSaliencyScheduleOutcome,
    PostTrainingSaliencyTarget,
    PostTrainingSaliencyTerminalDeliveryState,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
    TrainingOutcomeState,
    TrainingPipelineMutationBoundary,
    TrainingReadBoundary,
    TrainingTerminalOutcome,
)

from .errors import PreconditionError

SaliencyTerminalCallback = Callable[[PostTrainingSaliencyStatus], object]


@dataclass(frozen=True, slots=True)
class TrainingRuntimeContext:
    """Immutable inputs used by one training resource preflight."""

    datasets: tuple[Any, ...]
    training_option: Any | None
    model_holder: Any | None

    def to_mapping(self) -> dict[str, Any]:
        """Return the compatibility mapping consumed by receipt fingerprinting."""
        return {
            "datasets": list(self.datasets),
            "training_option": self.training_option,
            "model_holder": self.model_holder,
        }


@dataclass(frozen=True, slots=True)
class TrainingConfigurationSnapshot:
    """One detached read of model, option, and saliency configuration."""

    model_holder: Any | None
    training_option: Any | None
    saliency_params: dict[str, Any] | None


class TrainingStateReadPort(Protocol):
    """Training truth required by one application state snapshot."""

    def configuration_snapshot(self) -> TrainingConfigurationSnapshot: ...

    def has_trainer(self) -> bool: ...

    def terminal_outcome(self) -> TrainingTerminalOutcome: ...

    def saliency_status(self) -> PostTrainingSaliencyStatus: ...

    def capture_read_boundary(self) -> TrainingReadBoundary: ...


class TrainingProjectionReadPort(Protocol):
    """Runtime reads used to project training history and readiness."""

    def resource_context(self) -> TrainingRuntimeContext: ...

    def is_training(self) -> bool: ...

    def training_plan_holders(self) -> tuple[Any, ...]: ...

    def current_training_plan_index(self) -> int | None: ...


class TrainingCommandRuntimePort(Protocol):
    """Runtime reads and control required by training command handlers."""

    def resource_context(self) -> TrainingRuntimeContext: ...

    def stop_training(self, *, wait_timeout: float | None = None) -> bool: ...

    def wait_for_training_completion(self, *, timeout: float | None = None) -> bool: ...

    def terminal_outcome(self) -> TrainingTerminalOutcome: ...


class TrainingConfigurationControlPort(Protocol):
    """Sole application mutation used by configuration reset."""

    def clear_configuration(self) -> None: ...


class TrainingPipelineMutationPort(Protocol):
    """Compare-and-commit boundary for raw and downstream data replacement."""

    def begin_raw_replacement(self) -> TrainingPipelineMutationBoundary: ...

    def begin_downstream_replacement(self) -> TrainingPipelineMutationBoundary: ...

    def commit_pipeline_invalidation(
        self,
        expected: TrainingPipelineMutationBoundary,
    ) -> bool: ...

    def commit_pipeline_replacement(
        self,
        expected: TrainingPipelineMutationBoundary,
        *,
        publish: Callable[[], None],
    ) -> bool: ...


class PostTrainingSaliencyRuntimePort(Protocol):
    """Post-training saliency lifecycle operations owned by the runtime."""

    def saliency_status(self) -> PostTrainingSaliencyStatus: ...

    def saliency_delivery_state(
        self,
    ) -> PostTrainingSaliencyTerminalDeliveryState: ...

    def subscribe_saliency_terminal(
        self,
        callback: SaliencyTerminalCallback,
    ) -> None: ...

    def unsubscribe_saliency_terminal(
        self,
        callback: SaliencyTerminalCallback,
    ) -> None: ...

    def defer_saliency_terminal(
        self,
        stage: SaliencyTerminalCallback | None = None,
    ) -> AbstractContextManager[None]: ...

    def publish_saliency_submission_failure(
        self,
        target: PostTrainingSaliencyTarget,
        error: BaseException,
    ) -> PostTrainingSaliencyScheduleOutcome: ...

    def wait_for_saliency_job(self, *, timeout: float | None = None) -> bool: ...

    def cancel_saliency_job(self) -> None: ...

    def wait_for_saliency_delivery(self, *, timeout: float | None = None) -> bool: ...

    def retry_saliency_delivery(self) -> None: ...


class TrainingRuntimePort(
    TrainingStateReadPort,
    TrainingProjectionReadPort,
    TrainingCommandRuntimePort,
    TrainingConfigurationControlPort,
    TrainingPipelineMutationPort,
    PostTrainingSaliencyRuntimePort,
    Protocol,
):
    """Composite application runtime; consumers should prefer a narrow port."""


class _TrainingManagerRuntimePort(Protocol):
    """Concrete manager surface consumed by the Study runtime adapter."""

    model_holder: Any | None
    training_option: Any | None
    saliency_params: dict[str, Any] | None

    def has_trainer(self) -> bool: ...

    def is_training(self) -> bool: ...

    def get_training_plan_holders_snapshot(self) -> tuple[Any, ...]: ...

    def get_current_training_plan_index(self) -> int | None: ...

    def capture_training_read_boundary(self) -> TrainingReadBoundary: ...

    def stop_training_if_present(
        self,
        wait_timeout: float | None = None,
    ) -> bool: ...

    def wait_for_training_completion(self, timeout: float | None = None) -> bool: ...

    def get_training_terminal_outcome(self) -> TrainingTerminalOutcome: ...

    def capture_pipeline_mutation_boundary(
        self,
    ) -> TrainingPipelineMutationBoundary: ...

    def retire_trainer_if_current(
        self,
        expected: TrainingPipelineMutationBoundary,
    ) -> bool: ...

    def commit_pipeline_replacement(
        self,
        expected: TrainingPipelineMutationBoundary,
        *,
        publish: Callable[[], None],
    ) -> bool: ...

    def get_post_training_saliency_status(self) -> PostTrainingSaliencyStatus: ...

    def get_post_training_saliency_terminal_delivery_state(
        self,
    ) -> PostTrainingSaliencyTerminalDeliveryState: ...

    def subscribe_post_training_saliency_terminal(
        self,
        callback: SaliencyTerminalCallback,
    ) -> None: ...

    def unsubscribe_post_training_saliency_terminal(
        self,
        callback: SaliencyTerminalCallback,
    ) -> None: ...

    def defer_post_training_saliency_terminal_notifications(
        self,
        stage: SaliencyTerminalCallback | None = None,
    ) -> AbstractContextManager[None]: ...

    def publish_post_training_saliency_submission_failure(
        self,
        target: PostTrainingSaliencyTarget,
        error: BaseException,
    ) -> PostTrainingSaliencyScheduleOutcome: ...

    def wait_for_saliency_job(self, timeout: float | None = None) -> bool: ...

    def cancel_saliency_job(self) -> None: ...

    def wait_for_saliency_terminal_delivery(
        self,
        timeout: float | None = None,
    ) -> bool: ...

    def retry_post_training_saliency_terminal_delivery(self) -> None: ...


class _TrainingRuntimeStudy(Protocol):
    """Read-only Study ownership required by the training runtime adapter."""

    @property
    def training_manager(self) -> _TrainingManagerRuntimePort: ...

    @property
    def datasets(self) -> Sequence[Any]: ...


class StudyTrainingRuntime:
    """Adapt the concrete Study/TrainingManager runtime to the application port."""

    def __init__(self, study: _TrainingRuntimeStudy) -> None:
        self._study = study

    @property
    def _manager(self) -> _TrainingManagerRuntimePort:
        return self._study.training_manager

    def resource_context(self) -> TrainingRuntimeContext:
        """Capture the current resource-estimation inputs without UI knowledge."""
        configuration = self.configuration_snapshot()
        return TrainingRuntimeContext(
            datasets=tuple(self._study.datasets),
            training_option=configuration.training_option,
            model_holder=configuration.model_holder,
        )

    def configuration_snapshot(self) -> TrainingConfigurationSnapshot:
        """Detach saliency settings while preserving configured object identity."""
        saliency_params = self._manager.saliency_params
        return TrainingConfigurationSnapshot(
            model_holder=self._manager.model_holder,
            training_option=self._manager.training_option,
            saliency_params=(
                deepcopy(saliency_params) if isinstance(saliency_params, dict) else None
            ),
        )

    def has_trainer(self) -> bool:
        return bool(self._manager.has_trainer())

    def is_training(self) -> bool:
        return bool(self._manager.is_training())

    def training_plan_holders(self) -> tuple[Any, ...]:
        return tuple(self._manager.get_training_plan_holders_snapshot())

    def current_training_plan_index(self) -> int | None:
        return self._manager.get_current_training_plan_index()

    def capture_read_boundary(self) -> TrainingReadBoundary:
        return self._manager.capture_training_read_boundary()

    def stop_training(self, *, wait_timeout: float | None = None) -> bool:
        """Stop the active trainer, returning False when no trainer exists."""
        return bool(
            self._manager.stop_training_if_present(wait_timeout=wait_timeout),
        )

    def wait_for_training_completion(self, *, timeout: float | None = None) -> bool:
        """Wait for one admitted run without retaining mutable trainer access."""
        return bool(self._manager.wait_for_training_completion(timeout=timeout))

    def terminal_outcome(self) -> TrainingTerminalOutcome:
        """Return typed terminal truth from the current trainer."""
        return self._manager.get_training_terminal_outcome()

    def clear_configuration(self) -> None:
        """Clear model, optimizer, and saliency choices at their runtime owner."""
        self._manager.model_holder = None
        self._manager.training_option = None
        self._manager.saliency_params = None

    def begin_raw_replacement(self) -> TrainingPipelineMutationBoundary:
        """Require an empty, stable training runtime before raw data changes."""
        boundary = self._manager.capture_pipeline_mutation_boundary()
        self._ensure_pipeline_mutation_safe(boundary)
        if boundary.read_boundary.trainer_identity is not None:
            raise PreconditionError(
                "Raw EEG data cannot be replaced while training history exists. "
                "Clear training results first.",
                diagnostics={
                    "code": "raw_replacement_training_history_present",
                    "state_preserved": True,
                },
            )
        return boundary

    def begin_downstream_replacement(self) -> TrainingPipelineMutationBoundary:
        """Capture stable training truth before replacing downstream data."""
        boundary = self._manager.capture_pipeline_mutation_boundary()
        self._ensure_pipeline_mutation_safe(boundary)
        return boundary

    def commit_pipeline_invalidation(
        self,
        expected: TrainingPipelineMutationBoundary,
    ) -> bool:
        """Retire only the trainer proven current at transaction start."""
        if not isinstance(expected, TrainingPipelineMutationBoundary):
            raise TypeError("expected must be a TrainingPipelineMutationBoundary")
        try:
            return bool(self._manager.retire_trainer_if_current(expected))
        except StaleTrainingPipelineMutationError as exc:
            raise PreconditionError(
                "Training or saliency state changed before the data update could "
                "commit. The previous training state was preserved; retry when "
                "background work is idle.",
                diagnostics={
                    "code": "training_pipeline_boundary_changed",
                    "state_preserved": True,
                    "retryable": True,
                },
            ) from exc

    def commit_pipeline_replacement(
        self,
        expected: TrainingPipelineMutationBoundary,
        *,
        publish: Callable[[], None],
    ) -> bool:
        """Publish downstream data while trainer retirement owns one lease."""
        if not isinstance(expected, TrainingPipelineMutationBoundary):
            raise TypeError("expected must be a TrainingPipelineMutationBoundary")
        if not callable(publish):
            raise TypeError("publish must be callable")
        try:
            return bool(
                self._manager.commit_pipeline_replacement(
                    expected,
                    publish=publish,
                )
            )
        except StaleTrainingPipelineMutationError as exc:
            raise PreconditionError(
                "Training or saliency state changed before the data update could "
                "commit. The previous training state was preserved; retry when "
                "background work is idle.",
                diagnostics={
                    "code": "training_pipeline_boundary_changed",
                    "state_preserved": True,
                    "retryable": True,
                },
            ) from exc

    @staticmethod
    def _ensure_pipeline_mutation_safe(
        boundary: TrainingPipelineMutationBoundary,
    ) -> None:
        if not boundary.read_boundary.stable:
            raise PreconditionError(
                "Training state is still changing. Wait for training to stop before "
                "changing the data pipeline.",
                diagnostics={
                    "code": "training_pipeline_state_unstable",
                    "state_preserved": True,
                },
            )
        if boundary.training_work_active:
            raise PreconditionError(
                "A training lifecycle operation is still in progress. Wait for it "
                "to finish before changing the data pipeline.",
                diagnostics={
                    "code": "training_pipeline_operation_active",
                    "state_preserved": True,
                },
            )
        if boundary.terminal_outcome.state in {
            TrainingOutcomeState.RUNNING,
            TrainingOutcomeState.STOP_REQUESTED,
        }:
            raise PreconditionError(
                "Training is running or still stopping. Wait for it to finish before "
                "changing the data pipeline.",
                diagnostics={
                    "code": "training_pipeline_active",
                    "state_preserved": True,
                },
            )
        if (
            boundary.read_boundary.trainer_identity is not None
            and boundary.terminal_outcome.state is TrainingOutcomeState.UNKNOWN
        ):
            raise PreconditionError(
                "Training state could not be verified. The data pipeline was not "
                "changed.",
                diagnostics={
                    "code": "training_pipeline_outcome_unverified",
                    "state_preserved": True,
                },
            )
        if boundary.saliency_work_active or boundary.saliency_status.phase in {
            PostTrainingSaliencyPhase.PENDING,
            PostTrainingSaliencyPhase.RUNNING,
        }:
            raise PreconditionError(
                "Automatic saliency is still running or cleaning up. Wait for it to "
                "finish before changing the data pipeline.",
                diagnostics={
                    "code": "training_pipeline_saliency_active",
                    "state_preserved": True,
                },
            )
        outcome_run = boundary.terminal_outcome.run
        trainer_identity = boundary.read_boundary.trainer_identity
        if (
            outcome_run is not None
            and trainer_identity is not None
            and outcome_run.trainer_id != trainer_identity
        ):
            raise PreconditionError(
                "Training history identity could not be verified. The data pipeline "
                "was not changed.",
                diagnostics={
                    "code": "training_pipeline_identity_mismatch",
                    "state_preserved": True,
                },
            )

    def saliency_status(self) -> PostTrainingSaliencyStatus:
        return self._manager.get_post_training_saliency_status()

    def saliency_delivery_state(
        self,
    ) -> PostTrainingSaliencyTerminalDeliveryState:
        return self._manager.get_post_training_saliency_terminal_delivery_state()

    def subscribe_saliency_terminal(
        self,
        callback: SaliencyTerminalCallback,
    ) -> None:
        self._manager.subscribe_post_training_saliency_terminal(callback)

    def unsubscribe_saliency_terminal(
        self,
        callback: SaliencyTerminalCallback,
    ) -> None:
        self._manager.unsubscribe_post_training_saliency_terminal(callback)

    def defer_saliency_terminal(
        self,
        stage: SaliencyTerminalCallback | None = None,
    ) -> AbstractContextManager[None]:
        return self._manager.defer_post_training_saliency_terminal_notifications(stage)

    def publish_saliency_submission_failure(
        self,
        target: PostTrainingSaliencyTarget,
        error: BaseException,
    ) -> PostTrainingSaliencyScheduleOutcome:
        return self._manager.publish_post_training_saliency_submission_failure(
            target,
            error,
        )

    def wait_for_saliency_job(self, *, timeout: float | None = None) -> bool:
        return bool(self._manager.wait_for_saliency_job(timeout=timeout))

    def cancel_saliency_job(self) -> None:
        self._manager.cancel_saliency_job()

    def wait_for_saliency_delivery(self, *, timeout: float | None = None) -> bool:
        return bool(
            self._manager.wait_for_saliency_terminal_delivery(timeout=timeout),
        )

    def retry_saliency_delivery(self) -> None:
        self._manager.retry_post_training_saliency_terminal_delivery()


__all__ = [
    "PostTrainingSaliencyRuntimePort",
    "SaliencyTerminalCallback",
    "StudyTrainingRuntime",
    "TrainingCommandRuntimePort",
    "TrainingConfigurationControlPort",
    "TrainingConfigurationSnapshot",
    "TrainingPipelineMutationPort",
    "TrainingProjectionReadPort",
    "TrainingRuntimeContext",
    "TrainingRuntimePort",
    "TrainingStateReadPort",
]
