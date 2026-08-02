"""Application shutdown admission and terminal-publication reconciliation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any, Protocol

from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyStatus,
)
from XBrainLab.backend.utils.logger import logger

from .application_publication_lifecycle import ApplicationPublicationLifecycle
from .state import ApplicationStateSnapshot
from .training_runtime import TrainingRuntimePort
from .view_publication import ApplicationViewPublication

_TRAINING_CLOSE_WAIT_SECONDS = 2.0


class _TrainingTerminalWaitCancellationPort(Protocol):
    def cancel_terminal_notification_waits(self, reason: str) -> None: ...


class _DatasetPreviewCancellationPort(Protocol):
    def cancel_all(self) -> int: ...


class _PostTrainingSaliencyCancellationPort(Protocol):
    def cancel(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ApplicationShutdownSnapshot:
    """One atomic read of application command-admission lifecycle state."""

    closing: bool
    closed: bool
    fenced: bool
    fence_generation: int


class ApplicationShutdownLifecycleCoordinator:
    """Own close/fence state and reconcile retained terminal publications."""

    def __init__(
        self,
        *,
        command_admission_lock: Any,
        command_lock: Any,
        synchronous_training_lifecycle_lock: Any,
        training: _TrainingTerminalWaitCancellationPort,
        training_runtime: TrainingRuntimePort,
        dataset_split_preview: _DatasetPreviewCancellationPort,
        post_training_saliency: _PostTrainingSaliencyCancellationPort,
        publication_lifecycle: ApplicationPublicationLifecycle,
        refresh_training_publication: Callable[[], ApplicationStateSnapshot],
        committed_view_publication: Callable[[], ApplicationViewPublication],
        wait_for_synchronous_training_quiescence: Callable[[float], bool],
    ) -> None:
        self._command_admission_lock = command_admission_lock
        self._command_lock = command_lock
        self._synchronous_training_lifecycle_lock = synchronous_training_lifecycle_lock
        self._training = training
        self._training_runtime = training_runtime
        self._dataset_split_preview = dataset_split_preview
        self._post_training_saliency = post_training_saliency
        self._publication_lifecycle = publication_lifecycle
        self._refresh_training_publication = refresh_training_publication
        self._committed_view_publication = committed_view_publication
        self._wait_for_synchronous_training_quiescence = (
            wait_for_synchronous_training_quiescence
        )
        self._closing = False
        self._closed = False
        self._shutdown_fenced = False
        self._shutdown_fence_generation = 0

    @property
    def is_closing(self) -> bool:
        """Return whether permanent close has started but not committed."""
        return self._closing

    @property
    def is_closed(self) -> bool:
        """Return whether this service instance permanently released ownership."""
        return self._closed

    @property
    def is_shutdown_fenced(self) -> bool:
        """Return whether mutating command admission is temporarily fenced."""
        return self._shutdown_fenced

    @property
    def fence_generation(self) -> int:
        """Return the identity of the current or most recent shutdown fence."""
        return self._shutdown_fence_generation

    def snapshot(self) -> ApplicationShutdownSnapshot:
        """Read all admission flags under their owning lock."""
        with self._command_admission_lock:
            return ApplicationShutdownSnapshot(
                closing=self._closing,
                closed=self._closed,
                fenced=self._shutdown_fenced,
                fence_generation=self._shutdown_fence_generation,
            )

    def begin_close(self) -> bool:
        """Commit permanent close only after owned training work is quiescent."""
        with self._command_admission_lock:
            if self._closed or self._closing:
                return False
            self._closing = True
            self._shutdown_fenced = True
            self._shutdown_fence_generation += 1
        try:
            self._training.cancel_terminal_notification_waits(
                "Application service is closing."
            )
        except Exception:
            logger.debug(
                "Could not cancel training terminal handoff waits during close",
                exc_info=True,
            )
        close_deadline = monotonic() + _TRAINING_CLOSE_WAIT_SECONDS
        with self._synchronous_training_lifecycle_lock:
            try:
                trainer_present = self._training_runtime.has_trainer()
                stopped = self._training_runtime.stop_training(
                    wait_timeout=max(0.0, close_deadline - monotonic()),
                )
                worker_active = self._training_runtime.is_training()
            except Exception:
                logger.exception("Could not stop active training during close")
                self._abort_close()
                return False
            if worker_active or (trainer_present and not stopped):
                logger.warning(
                    "Training did not stop within %.1f seconds during close; "
                    "the cooperative stop request remains active.",
                    _TRAINING_CLOSE_WAIT_SECONDS,
                )
                self._abort_close()
                return False
            try:
                completion_timeout = max(0.0, close_deadline - monotonic())
                completion_quiescent = self._wait_for_synchronous_training_quiescence(
                    completion_timeout
                )
                worker_resumed = self._training_runtime.is_training()
            except Exception:
                logger.exception(
                    "Could not verify synchronous training quiescence during close"
                )
                self._abort_close()
                return False
            if not completion_quiescent:
                logger.warning(
                    "Synchronous training completion did not quiesce within %.1f "
                    "seconds during close.",
                    _TRAINING_CLOSE_WAIT_SECONDS,
                )
                self._abort_close()
                return False
            if worker_resumed:
                logger.warning("Training resumed before close could commit.")
                self._abort_close()
                return False
            self._dataset_split_preview.cancel_all()
            with self._command_lock, self._command_admission_lock:
                if self._closed:
                    return False
                self._closed = True
                self._closing = False
                return True

    def _abort_close(self) -> None:
        """Allow an explicit retry without reopening the shutdown fence."""
        with self._command_admission_lock:
            if not self._closed:
                self._closing = False

    def cancel_close_automation(self) -> None:
        """Stop nonessential post-training automation after close commits."""
        try:
            self._post_training_saliency.cancel()
        except Exception:
            logger.debug(
                "Could not cancel post-training saliency automation during close",
                exc_info=True,
            )

    def request_fence(self) -> None:
        """Reject new mutations and stop background work without waiting."""
        publications = self._publication_lifecycle.coordinator
        with (
            publications.capture_saliency_notifications(),
            self._training_runtime.defer_saliency_terminal(),
        ):
            with self._command_admission_lock:
                self._shutdown_fenced = True
                self._shutdown_fence_generation += 1
            self._dataset_split_preview.cancel_all()
            try:
                self._post_training_saliency.cancel()
                self._training_runtime.cancel_saliency_job()
            except Exception:
                logger.exception("Could not cancel background saliency during shutdown")

    def release_fence(self) -> bool:
        """Reopen admission only after hidden terminal state is publicly committed."""
        publication_changed = False
        terminal_status: PostTrainingSaliencyStatus | None = None
        release_generation = -1
        try:
            with self._command_lock, self._command_admission_lock:
                if self._closed or self._closing:
                    return False
                if not self._shutdown_fenced:
                    return True
                release_generation = self._shutdown_fence_generation
                before = self._committed_view_publication()
                refreshed_state = self._refresh_training_publication()
                after = self._committed_view_publication()
                if (
                    not refreshed_state.state_reliable
                    or not after.usable
                    or after.refresh_error is not None
                    or after.state != refreshed_state
                ):
                    return False
                before_visualization = before.state.visualization
                after_visualization = after.state.visualization
                publication_changed = (
                    before_visualization.post_training_saliency
                    != after_visualization.post_training_saliency
                    or before_visualization.saliency_coverage
                    != after_visualization.saliency_coverage
                )
                if publication_changed:
                    status = after.state.visualization.post_training_saliency
                    if status.phase.terminal:
                        terminal_status = status
        except Exception:
            logger.exception(
                "Could not reconcile application state after shutdown was cancelled"
            )
            terminal_status = self._terminal_saliency_release_obligation()
            if terminal_status is not None:
                self._publication_lifecycle.remember_pending_saliency_terminal(
                    terminal_status
                )
            return False

        terminal_status = (
            self._terminal_saliency_release_obligation() or terminal_status
        )
        try:
            with (
                self._publication_lifecycle.coordinator.capture_saliency_notifications()
            ):
                if terminal_status is not None:
                    self._publication_lifecycle.remember_pending_saliency_terminal(
                        terminal_status
                    )
                self._publication_lifecycle.reconcile_pending_saliency_terminal(
                    allow_shutdown_fenced=True,
                )
        except Exception:
            logger.exception(
                "Could not queue terminal saliency while releasing shutdown fence"
            )
            return False
        if self._publication_lifecycle.pending_saliency_terminal() is not None:
            return False
        if (
            publication_changed
            and terminal_status is None
            and not self._publication_lifecycle.notify_saliency_publication_changed()
        ):
            return False
        publication = self._committed_view_publication()
        if (
            not publication.usable
            or publication.refresh_error is not None
            or not self._runtime_saliency_terminal_delivery_committed()
        ):
            return False
        return self._complete_fence_release(release_generation)

    def _terminal_saliency_release_obligation(
        self,
    ) -> PostTrainingSaliencyStatus | None:
        status = self._training_runtime.saliency_status()
        if not status.phase.terminal:
            return None
        visualization_state = self._committed_view_publication().state.visualization
        publication_status = visualization_state.post_training_saliency
        if publication_status.generation > status.generation:
            return None
        if self._publication_lifecycle.coordinator.has_delivered_saliency_generation(
            status.generation
        ):
            return None
        return status

    def _runtime_saliency_terminal_delivery_committed(self) -> bool:
        delivery = self._training_runtime.saliency_delivery_state()
        if (
            delivery.pending_generations
            and delivery.active_generation is None
            and not delivery.retry_owner_active
        ):
            self._training_runtime.retry_saliency_delivery()
            delivery = self._training_runtime.saliency_delivery_state()
        if delivery.pending_generations or delivery.active_generation is not None:
            return False
        status = self._training_runtime.saliency_status()
        if not status.phase.terminal:
            return True
        if delivery.delivered_generation < status.generation:
            return False
        return (
            self._publication_lifecycle.coordinator.has_delivered_saliency_generation(
                status.generation
            )
        )

    def _complete_fence_release(self, expected_generation: int) -> bool:
        with self._command_admission_lock:
            if self._closed or self._closing:
                return False
            if not self._shutdown_fenced:
                return True
            if self._shutdown_fence_generation != expected_generation:
                return False
            self._shutdown_fenced = False
            return True
