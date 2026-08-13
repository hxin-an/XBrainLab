"""Application-owned single-flight coordination for training draft estimates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from secrets import token_urlsafe
from threading import Condition, Event, RLock, Thread, current_thread
from time import monotonic
from typing import Any

from .errors import PreconditionError
from .owned_work import (
    OwnedOperationCancelledError,
    OwnedWorkKind,
    OwnedWorkRegistry,
    owned_work_checkpoint,
    owned_work_commit_boundary,
)
from .resource_guard import (
    TrainingResourcePreviewContext,
    TrainingResourcePreviewReceipt,
    TrainingResourcePreviewRequest,
    TrainingResourcePreviewResult,
    TrainingResourceRefinement,
)

_CLOSING_MESSAGE = (
    "Training resource preview is unavailable while XBrainLab is closing."
)
_SUPERSEDED_MESSAGE = "A newer training resource preview replaced this pending request."
_STALE_CONTEXT_MESSAGE = "Training context changed. Review the settings again."
_CANCELLED_MESSAGE = "The training resource preview was cancelled."
_COMMAND_IDENTITY = "training_resource_preview"


@dataclass(slots=True)
class _PreviewJob:
    sequence: int
    request: TrainingResourcePreviewRequest
    context: TrainingResourcePreviewContext
    completed: Event = field(default_factory=Event)
    result: TrainingResourcePreviewResult | None = None
    error: BaseException | None = None
    cancellation_message: str | None = None
    operation_id: str = ""

    def matches(
        self,
        request: TrainingResourcePreviewRequest,
        context: TrainingResourcePreviewContext,
    ) -> bool:
        return self.request == request and self.context == context


class TrainingResourcePreviewTicket:
    """One client claim on an application-owned preview job."""

    def __init__(self, job: _PreviewJob) -> None:
        self._job = job

    def result(self, timeout: float | None = None) -> TrainingResourcePreviewResult:
        """Wait for this exact request without taking worker ownership."""
        wait_timeout = None if timeout is None else max(0.0, float(timeout))
        if not self._job.completed.wait(timeout=wait_timeout):
            raise TimeoutError("Training resource preview did not finish in time.")
        if self._job.error is not None:
            raise self._job.error
        result = self._job.result
        if not isinstance(result, TrainingResourcePreviewResult):
            raise RuntimeError("Training resource preview completed without a result.")
        return result

    @property
    def done(self) -> bool:
        """Return terminal readiness without blocking the caller."""
        return self._job.completed.is_set()

    @property
    def operation_id(self) -> str:
        """Return the backend-owned identity for this exact shared job."""
        return self._job.operation_id


class TrainingResourcePreviewCoordinator:
    """Serialize native model estimates and retain only the newest queued draft."""

    def __init__(
        self,
        *,
        estimate: Callable[
            [TrainingResourcePreviewRequest, TrainingResourcePreviewContext],
            TrainingResourcePreviewResult,
        ],
        generation_is_current: Callable[[int], bool],
        registry: OwnedWorkRegistry,
    ) -> None:
        if not isinstance(registry, OwnedWorkRegistry):
            raise TypeError("registry must be an OwnedWorkRegistry")
        self._estimate = estimate
        self._generation_is_current = generation_is_current
        self._registry = registry
        self._lock = RLock()
        self._idle = Condition(self._lock)
        self._pending: _PreviewJob | None = None
        self._active: _PreviewJob | None = None
        self._worker: Thread | None = None
        self._closing = False
        self._sequence = 0
        self._last_completed: (
            tuple[int, TrainingResourcePreviewRequest, TrainingResourcePreviewResult]
            | None
        ) = None

    def submit(
        self,
        request: TrainingResourcePreviewRequest,
        context: TrainingResourcePreviewContext,
    ) -> TrainingResourcePreviewTicket:
        """Admit a draft, sharing identical work and replacing older pending work."""
        if not isinstance(request, TrainingResourcePreviewRequest):
            raise TypeError("request must be a TrainingResourcePreviewRequest")
        if not isinstance(context, TrainingResourcePreviewContext):
            raise TypeError("context must be a TrainingResourcePreviewContext")
        with self._idle:
            if self._closing:
                raise PreconditionError(_CLOSING_MESSAGE)
            for job in (self._active, self._pending):
                if job is not None and job.matches(request, context):
                    return TrainingResourcePreviewTicket(job)
            self._sequence += 1
            operation = self._registry.begin(
                OwnedWorkKind.TRAINING_RESOURCE_PREVIEW,
                cancellable=True,
                stage="Queued training resource preview",
                command_identity=_COMMAND_IDENTITY,
            )
            job = _PreviewJob(
                self._sequence,
                request,
                context,
                operation_id=operation.operation_id,
            )
            obsolete = self._pending
            self._pending = job
            if obsolete is not None:
                self._cancel_pending_job_locked(obsolete, _SUPERSEDED_MESSAGE)
            try:
                self._ensure_worker_locked()
            except BaseException:
                if self._pending is job:
                    self._pending = None
                self._registry.fail(
                    job.operation_id,
                    message="Training resource preview worker could not start.",
                )
                self._fail_job(
                    job,
                    RuntimeError("Training resource preview worker could not start."),
                )
                self._idle.notify_all()
                raise
            self._idle.notify_all()
            return TrainingResourcePreviewTicket(job)

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        """Wait for active and pending estimates at an explicit lifecycle boundary."""
        deadline = None if timeout is None else monotonic() + max(0.0, timeout)
        with self._idle:
            while (
                self._active is not None
                or self._pending is not None
                or self._worker is not None
            ):
                remaining = (
                    None if deadline is None else max(0.0, deadline - monotonic())
                )
                if remaining == 0.0:
                    return False
                self._idle.wait(timeout=remaining)
            return True

    def begin_close(self) -> None:
        """Fence submissions and cancel active and pending preview ownership."""
        with self._idle:
            if self._closing:
                return
            self._closing = True
            self._last_completed = None
            pending = self._pending
            self._pending = None
            if pending is not None:
                self._cancel_pending_job_locked(pending, _CLOSING_MESSAGE)
            active = self._active
            if active is not None:
                self._request_job_cancellation(active, _CLOSING_MESSAGE)
            self._idle.notify_all()

    def cancel_close(self) -> bool:
        """Reopen preview admission after a temporary desktop close fence."""
        with self._idle:
            self._closing = False
            self._idle.notify_all()
            return True

    def close(self, timeout: float | None = 2.0) -> bool:
        """Fence and join the owned non-daemon worker within a bounded wait."""
        self.begin_close()
        deadline = None if timeout is None else monotonic() + max(0.0, timeout)
        with self._idle:
            worker = self._worker
        if worker is not None and worker is not current_thread():
            remaining = None if deadline is None else max(0.0, deadline - monotonic())
            worker.join(timeout=remaining)
        with self._idle:
            worker = self._worker
            if worker is not None and not worker.is_alive():
                self._worker = None
                worker = None
            return worker is None and self._active is None and self._pending is None

    @property
    def worker_thread(self) -> Thread | None:
        """Expose detached worker identity for lifecycle validation."""
        with self._idle:
            return self._worker

    def background_work_snapshot(self) -> dict[str, int | bool]:
        """Return exact non-blocking ownership for close diagnostics."""
        with self._idle:
            worker = self._worker
            active_jobs = int(self._active is not None)
            pending_jobs = int(self._pending is not None)
            alive_workers = int(worker is not None and worker.is_alive())
            remaining_workers = int(worker is not None)
            return {
                "idle": (
                    remaining_workers == 0 and active_jobs == 0 and pending_jobs == 0
                ),
                "remaining_workers": remaining_workers,
                "alive_workers": alive_workers,
                "active_jobs": active_jobs,
                "pending_jobs": pending_jobs,
            }

    def refinements_for_configuration(
        self,
        command: Any,
    ) -> tuple[TrainingResourceRefinement, ...]:
        """Consume the latest matching refinement when a draft is saved."""
        with self._idle:
            completed = self._last_completed
        if completed is None:
            return ()
        _sequence, request, result = completed
        from .training_submission import (  # noqa: PLC0415
            training_submission_resource_preview_receipt,
        )

        submitted_receipt = training_submission_resource_preview_receipt(command)
        if result.receipt is None or submitted_receipt != result.receipt:
            return ()
        with self._idle:
            if self._last_completed == completed:
                self._last_completed = None
        refinement = result.refinement
        if refinement is None or not self._is_generation_current(request):
            return ()
        if getattr(command, "batch_size", None) != refinement.refined_value:
            return ()
        if _normalized(getattr(command, "device", None)) != request.device:
            return ()
        if _normalized(getattr(command, "optimizer", None)) != _normalized(
            request.optimizer
        ):
            return ()
        command_model = getattr(command, "model_name", None)
        if request.model_name is not None and _normalized(command_model) != _normalized(
            request.model_name
        ):
            return ()
        command_params = dict(getattr(command, "model_params", {}) or {})
        if request.model_name is not None and command_params != dict(
            request.model_params
        ):
            return ()
        return (refinement,)

    def _ensure_worker_locked(self) -> None:
        worker = self._worker
        if worker is not None and worker.is_alive():
            return
        worker = Thread(
            target=self._worker_loop,
            name="xbrainlab-training-resource-preview",
            daemon=False,
        )
        self._worker = worker
        try:
            worker.start()
        except BaseException:
            self._worker = None
            raise

    def _worker_loop(self) -> None:
        while True:
            with self._idle:
                if self._pending is None:
                    self._worker = None
                    self._idle.notify_all()
                    return
                job = self._pending
                self._pending = None
                self._active = job
            if job is None:
                continue
            self._run_active_job(job)

    def _run_active_job(self, job: _PreviewJob) -> None:
        try:
            self._registry.claim_start(
                job.operation_id,
                kind=OwnedWorkKind.TRAINING_RESOURCE_PREVIEW,
                command_identity=_COMMAND_IDENTITY,
            )
            with self._registry.bind(job.operation_id):
                owned_work_checkpoint("Preparing training resource preview")
                result = self._estimate_current_job(job)
                owned_work_checkpoint("Verifying training resource preview")
                with self._idle:
                    newer_pending = (
                        self._pending is not None
                        and self._pending.sequence > job.sequence
                    )
                    if self._closing:
                        self._request_job_cancellation(job, _CLOSING_MESSAGE)
                    owned_work_checkpoint("Admitting training resource preview")
                    owned_work_commit_boundary("Publishing training resource preview")
                    if not newer_pending:
                        self._last_completed = (job.sequence, job.request, result)
                    job.error = None
                    job.result = result
                    if self._active is job:
                        self._active = None
                    self._registry.complete(job.operation_id)
                    job.completed.set()
                    self._idle.notify_all()
        except OwnedOperationCancelledError:
            self._finish_active_job(
                job,
                error=PreconditionError(job.cancellation_message or _CANCELLED_MESSAGE),
                cancelled=True,
            )
        except BaseException as exc:
            self._finish_active_job(job, error=exc, cancelled=False)

    def _finish_active_job(
        self,
        job: _PreviewJob,
        *,
        error: BaseException,
        cancelled: bool,
    ) -> None:
        snapshot = self._registry.snapshot(job.operation_id)
        if not snapshot.phase.terminal:
            if cancelled:
                self._registry.finish_cancelled(job.operation_id)
            else:
                self._registry.fail(
                    job.operation_id,
                    message="Training resource preview failed.",
                )
        with self._idle:
            job.error = error
            job.result = None
            job.completed.set()
            if self._active is job:
                self._active = None
            self._idle.notify_all()

    def _estimate_current_job(
        self,
        job: _PreviewJob,
    ) -> TrainingResourcePreviewResult:
        owned_work_checkpoint("Estimating training resource requirements")
        result = self._estimate(job.request, job.context)
        owned_work_checkpoint("Resource estimate ready")
        if not isinstance(result, TrainingResourcePreviewResult):
            raise TypeError("Training resource preview returned an invalid contract.")
        if not self._is_generation_current(job.request):
            raise PreconditionError(_STALE_CONTEXT_MESSAGE)
        return replace(
            result,
            receipt=TrainingResourcePreviewReceipt(
                token=token_urlsafe(24),
                request_generation=result.request_generation,
                publication_generation=result.publication_generation,
                requested_batch_size=result.requested_batch_size,
                suggested_batch_size=result.suggested_batch_size,
            ),
        )

    def _is_generation_current(
        self,
        request: TrainingResourcePreviewRequest,
    ) -> bool:
        try:
            return bool(self._generation_is_current(request.publication_generation))
        except Exception:
            return False

    def _request_job_cancellation(self, job: _PreviewJob, message: str) -> bool:
        cancelled = self._registry.cancel(job.operation_id)
        if cancelled:
            job.cancellation_message = message
        return cancelled

    def _cancel_pending_job_locked(self, job: _PreviewJob, message: str) -> None:
        self._request_job_cancellation(job, message)
        snapshot = self._registry.snapshot(job.operation_id)
        if not snapshot.phase.terminal:
            self._registry.finish_cancelled(job.operation_id)
        self._fail_job(job, PreconditionError(message))

    @staticmethod
    def _fail_job(job: _PreviewJob, error: BaseException) -> None:
        job.error = error
        job.result = None
        job.completed.set()


def _normalized(value: Any) -> str:
    return str(value or "").strip().casefold()


__all__ = [
    "TrainingResourcePreviewCoordinator",
    "TrainingResourcePreviewTicket",
]
