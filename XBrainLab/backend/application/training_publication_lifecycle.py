"""Delivery ownership for training and post-training terminal publications."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import Enum
from threading import Condition, Lock, Thread, current_thread
from time import monotonic

from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyStatus,
    TrainingLifecycleEvent,
)
from XBrainLab.backend.utils.logger import logger

from .post_training_saliency import (
    PostCommandSaliencyNotificationBoundary,
    SaliencyTerminalDeliveryState,
    SaliencyTerminalNotification,
)

_TrainingTerminalKey = tuple[int, str | None, int | None]
_TRAINING_TERMINAL_ATTEMPTS_PER_DRAIN = 2
_TRAINING_TERMINAL_RETRY_INITIAL_SECONDS = 0.05
_TRAINING_TERMINAL_RETRY_MAX_SECONDS = 0.4
_TRAINING_TERMINAL_MAX_AUTONOMOUS_DRAINS = 3


@dataclass(frozen=True, slots=True)
class TrainingTerminalDeliveryState:
    """Immutable summary of the training-terminal acknowledgement ledger."""

    active_count: int
    pending_count: int
    delivered_count: int
    retry_count: int
    latest_publication_generation: int
    retry_owner_active: bool
    retry_exhausted: bool
    closed: bool


class SaliencyTerminalDeliveryDisposition(str, Enum):
    """Decision returned by the application environment for one delivery."""

    DELIVER = "deliver"
    RETRY = "retry"
    DISCARD = "discard"


@dataclass(frozen=True, slots=True)
class SaliencyTerminalDeliveryPlan:
    """Validated environment decision for a retained saliency notification."""

    disposition: SaliencyTerminalDeliveryDisposition
    analysis_event: TrainingLifecycleEvent | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, SaliencyTerminalDeliveryDisposition):
            raise TypeError("saliency terminal delivery disposition is invalid")
        if self.disposition is SaliencyTerminalDeliveryDisposition.DELIVER:
            if not isinstance(self.analysis_event, TrainingLifecycleEvent):
                raise TypeError(
                    "deliver saliency terminal plan requires an analysis event"
                )
        elif self.analysis_event is not None:
            raise ValueError(
                "non-delivery saliency terminal plan cannot carry an analysis event"
            )


@dataclass(frozen=True, slots=True)
class _SaliencyTerminalDeliveryProgress:
    """Acknowledgements already committed for one exact terminal status."""

    status: PostTrainingSaliencyStatus
    analysis_delivered: bool = False
    visualization_delivered: bool = False


class TrainingPublicationLifecycleCoordinator:
    """Own terminal publication identities, retries, and acknowledgements.

    ApplicationService supplies environment operations such as reading the current
    publication and notifying adapters. This coordinator alone owns which terminal
    generations are active, acknowledged, pending, superseded, or discarded.
    """

    def __init__(
        self,
        *,
        publish_training_terminal: Callable[[TrainingLifecycleEvent], object],
        plan_saliency_delivery: Callable[
            [SaliencyTerminalNotification],
            SaliencyTerminalDeliveryPlan,
        ],
        publish_training_analysis: Callable[[TrainingLifecycleEvent], object],
        publish_saliency_changed: Callable[[SaliencyTerminalNotification], object],
    ) -> None:
        self._publish_training_terminal = publish_training_terminal
        self._plan_saliency_delivery = plan_saliency_delivery
        self._publish_training_analysis = publish_training_analysis
        self._publish_saliency_changed = publish_saliency_changed

        self._training_lock = Lock()
        self._training_condition = Condition(self._training_lock)
        self._training_active: set[_TrainingTerminalKey] = set()
        self._training_pending: dict[
            _TrainingTerminalKey,
            TrainingLifecycleEvent,
        ] = {}
        self._training_delivered: set[_TrainingTerminalKey] = set()
        self._training_draining = False
        self._training_drain_owner: Thread | None = None
        self._training_retry_owner: Thread | None = None
        self._training_retry_count = 0
        self._training_autonomous_retry_rounds = 0
        self._training_retry_exhausted = False
        self._latest_training_publication_generation = 0
        self._closed = False

        self._saliency_lock = Lock()
        self._pending_saliency_status: PostTrainingSaliencyStatus | None = None
        self._saliency_progress: dict[
            int,
            _SaliencyTerminalDeliveryProgress,
        ] = {}
        self._saliency_boundary = PostCommandSaliencyNotificationBoundary(
            self.deliver_saliency_terminal
        )

    @property
    def saliency_notification_boundary(
        self,
    ) -> PostCommandSaliencyNotificationBoundary:
        """Expose queue state for shutdown coordination and focused diagnostics."""
        return self._saliency_boundary

    def publish_training_terminal(
        self,
        event: TrainingLifecycleEvent,
    ) -> bool:
        """Retain and deliver one terminal identity after acknowledgement."""
        if not isinstance(event, TrainingLifecycleEvent):
            raise TypeError("training terminal publication is invalid")
        key = self._training_key(event)
        with self._training_lock:
            if self._closed:
                return False
            publication_generation = event.publication_generation
            if (
                publication_generation is not None
                and publication_generation
                < self._latest_training_publication_generation
            ):
                return True
            if publication_generation is not None:
                self._latest_training_publication_generation = max(
                    self._latest_training_publication_generation,
                    publication_generation,
                )
            if self._training_run_already_delivered_locked(event):
                return True
            if key in self._training_delivered:
                return True
            self._discard_superseded_pending_for_run_locked(event)
            self._training_pending.setdefault(key, event)
            self._reset_training_retry_budget_locked()
            if self._training_draining:
                return False
        self.retry_training_terminal_delivery()
        with self._training_lock:
            return not self._closed and (
                key in self._training_delivered or key not in self._training_pending
            )

    def retry_training_terminal_delivery(self) -> bool:
        """Drain retained terminal publications with one bounded retry."""
        with self._training_condition:
            if self._closed:
                return False
            self._reset_training_retry_budget_locked()
        return self._drain_training_terminal_delivery()

    def _drain_training_terminal_delivery(self) -> bool:
        """Attempt a bounded delivery pass without resetting retry policy."""
        with self._training_condition:
            if self._closed or self._training_draining:
                return False
            self._training_draining = True
            self._training_drain_owner = current_thread()
            self._training_condition.notify_all()

        attempts = 0
        try:
            while attempts < _TRAINING_TERMINAL_ATTEMPTS_PER_DRAIN:
                with self._training_condition:
                    if self._closed:
                        return False
                    pending = next(iter(self._training_pending.items()), None)
                    if pending is None:
                        return True
                    key, event = pending
                    self._training_active.add(key)

                delivered = False
                try:
                    delivered = self._publish_training_terminal(event) is not False
                except Exception:
                    logger.exception("Could not deliver terminal training publication")
                attempts += 1

                with self._training_condition:
                    self._training_active.discard(key)
                    if delivered and not self._closed:
                        self._training_delivered.add(key)
                        self._training_pending.pop(key, None)
                    elif not self._closed and key in self._training_pending:
                        self._training_retry_count += 1
                        event = self._training_pending.pop(key)
                        self._training_pending[key] = event
                    self._training_condition.notify_all()

            with self._training_lock:
                return not self._training_pending and not self._training_active
        finally:
            with self._training_condition:
                self._training_draining = False
                self._training_drain_owner = None
                self._ensure_training_retry_owner_locked()
                self._training_condition.notify_all()

    def wait_for_training_delivery(self, timeout: float | None = None) -> bool:
        """Wait for the bounded retry owner and any active drain to finish."""
        deadline = None if timeout is None else monotonic() + max(0.0, timeout)
        with self._training_condition:
            self._ensure_training_retry_owner_locked()
            while True:
                if (
                    not self._training_pending
                    and not self._training_active
                    and not self._training_draining
                    and self._training_retry_owner is None
                ):
                    return True
                if (
                    self._training_pending
                    and not self._training_draining
                    and self._training_retry_owner is None
                ):
                    return False
                remaining = (
                    None if deadline is None else max(0.0, deadline - monotonic())
                )
                if remaining == 0.0:
                    return False
                self._training_condition.wait(timeout=remaining)

    def _ensure_training_retry_owner_locked(self) -> None:
        """Start at most one delayed owner for retained training publications."""
        if (
            self._closed
            or not self._training_pending
            or self._training_retry_owner is not None
            or self._training_retry_exhausted
        ):
            return
        owner = Thread(
            target=self._run_training_retry_owner,
            name="xbrainlab-training-publication-retry",
            daemon=True,
        )
        self._training_retry_owner = owner
        try:
            owner.start()
        except Exception:
            self._training_retry_owner = None
            self._training_retry_exhausted = True
            self._training_condition.notify_all()
            logger.exception(
                "Could not start terminal training publication retry owner"
            )

    def _run_training_retry_owner(self) -> None:
        """Retry retained work with finite exponential backoff."""
        owner = current_thread()
        try:
            while True:
                with self._training_condition:
                    if self._closed or not self._training_pending:
                        self._release_training_retry_owner_locked(owner)
                        return
                    if (
                        self._training_autonomous_retry_rounds
                        >= _TRAINING_TERMINAL_MAX_AUTONOMOUS_DRAINS
                    ):
                        self._training_retry_exhausted = True
                        self._release_training_retry_owner_locked(owner)
                        return
                    delay = min(
                        _TRAINING_TERMINAL_RETRY_INITIAL_SECONDS
                        * (2**self._training_autonomous_retry_rounds),
                        _TRAINING_TERMINAL_RETRY_MAX_SECONDS,
                    )
                    retry_at = monotonic() + delay
                    while self._training_pending and not self._closed:
                        remaining = retry_at - monotonic()
                        if remaining <= 0.0:
                            break
                        self._training_condition.wait(timeout=remaining)
                    if self._closed or not self._training_pending:
                        self._release_training_retry_owner_locked(owner)
                        return
                    self._training_autonomous_retry_rounds += 1
                self._drain_training_terminal_delivery()
        finally:
            with self._training_condition:
                self._release_training_retry_owner_locked(owner)

    def _release_training_retry_owner_locked(self, owner: Thread) -> None:
        if self._training_retry_owner is owner:
            self._training_retry_owner = None
        self._training_condition.notify_all()

    def _reset_training_retry_budget_locked(self) -> None:
        self._training_autonomous_retry_rounds = 0
        self._training_retry_exhausted = False

    def training_delivery_state(self) -> TrainingTerminalDeliveryState:
        """Return an immutable ledger summary without exposing internal sets."""
        with self._training_lock:
            return TrainingTerminalDeliveryState(
                active_count=len(self._training_active),
                pending_count=len(self._training_pending),
                delivered_count=len(self._training_delivered),
                retry_count=self._training_retry_count,
                latest_publication_generation=(
                    self._latest_training_publication_generation
                ),
                retry_owner_active=self._training_retry_owner is not None,
                retry_exhausted=self._training_retry_exhausted,
                closed=self._closed,
            )

    @staticmethod
    def _training_key(event: TrainingLifecycleEvent) -> _TrainingTerminalKey:
        run = event.outcome.run
        return (
            event.token.generation,
            run.trainer_id if run is not None else None,
            run.run_id if run is not None else None,
        )

    def _discard_superseded_pending_for_run_locked(
        self,
        event: TrainingLifecycleEvent,
    ) -> None:
        """Retire older revisions once the same run has newer terminal truth."""
        run = event.outcome.run
        publication_generation = event.publication_generation
        if run is None or publication_generation is None:
            return
        superseded = [
            key
            for key, pending in self._training_pending.items()
            if pending.outcome.run is not None
            and pending.outcome.run.trainer_id == run.trainer_id
            and pending.outcome.run.run_id == run.run_id
            and pending.publication_generation is not None
            and pending.publication_generation < publication_generation
            and pending.token.generation <= event.token.generation
        ]
        for key in superseded:
            self._training_pending.pop(key, None)

    def _training_run_already_delivered_locked(
        self,
        event: TrainingLifecycleEvent,
    ) -> bool:
        run = event.outcome.run
        if run is None:
            return False
        return any(
            trainer_id == run.trainer_id and run_id == run.run_id
            for _generation, trainer_id, run_id in self._training_delivered
        )

    @contextmanager
    def capture_saliency_notifications(self) -> Iterator[None]:
        """Commit nested saliency notifications at the outer command boundary."""
        with self._saliency_boundary.capture():
            yield

    def publish_saliency_terminal(
        self,
        status: PostTrainingSaliencyStatus,
        *,
        reconcile: Callable[[], object],
    ) -> bool:
        """Retain terminal truth and reconcile it within one capture boundary."""
        with self.capture_saliency_notifications():
            self.commit_saliency_terminal(status, reconcile=reconcile)
        return self.has_delivered_saliency_generation(status.generation)

    def commit_saliency_terminal(
        self,
        status: PostTrainingSaliencyStatus,
        *,
        reconcile: Callable[[], object],
    ) -> bool:
        """Remember one terminal generation until public observers acknowledge it."""
        if (
            not isinstance(status, PostTrainingSaliencyStatus)
            or not status.phase.terminal
        ):
            return True
        if self.has_delivered_saliency_generation(status.generation):
            return True
        self.remember_saliency_terminal(status)
        return reconcile() is not False

    def remember_saliency_terminal(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> bool:
        """Keep only the newest terminal generation awaiting publication."""
        if (
            not isinstance(status, PostTrainingSaliencyStatus)
            or not status.phase.terminal
        ):
            return False
        with self._saliency_lock:
            pending = self._pending_saliency_status
            if pending is not None and pending.generation > status.generation:
                return False
            if pending is None or pending.generation < status.generation:
                stale_generations = [
                    generation
                    for generation in self._saliency_progress
                    if generation < status.generation
                ]
                for generation in stale_generations:
                    self._saliency_progress.pop(generation, None)
            self._pending_saliency_status = status
        return True

    def pending_saliency_terminal(self) -> PostTrainingSaliencyStatus | None:
        """Return the exact terminal identity still awaiting delivery."""
        with self._saliency_lock:
            return self._pending_saliency_status

    def discard_saliency_terminal(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> None:
        """Discard one exact identity without erasing a concurrent newer run."""
        with self._saliency_lock:
            if self._pending_saliency_status == status:
                self._pending_saliency_status = None
            self._saliency_progress.pop(status.generation, None)

    def stage_saliency_notification(
        self,
        notification: SaliencyTerminalNotification,
    ) -> bool:
        """Reserve and queue one notification without losing retry ownership."""
        if not self._saliency_boundary.reserve(notification):
            if self.has_delivered_saliency_generation(notification.status.generation):
                self.discard_saliency_terminal(notification.status)
                return True
            self._saliency_boundary.retry_pending()
            return False
        try:
            self._saliency_boundary.publish_reserved(notification)
        except Exception:
            self._saliency_boundary.release(notification)
            logger.exception("Could not queue terminal saliency notification")
            return False
        return self.has_delivered_saliency_generation(notification.status.generation)

    def deliver_saliency_terminal(
        self,
        notification: SaliencyTerminalNotification,
    ) -> bool:
        """Deliver both public events, retrying only unacknowledged work."""
        if not isinstance(notification, SaliencyTerminalNotification):
            raise TypeError("saliency terminal notification is invalid")
        plan = self._plan_saliency_delivery(notification)
        if not isinstance(plan, SaliencyTerminalDeliveryPlan):
            raise TypeError("saliency terminal delivery plan is invalid")
        if plan.disposition is SaliencyTerminalDeliveryDisposition.DISCARD:
            self.discard_saliency_terminal(notification.status)
            return True
        if plan.disposition is SaliencyTerminalDeliveryDisposition.RETRY:
            return False

        progress = self._saliency_delivery_progress(notification.status)
        if not progress.analysis_delivered:
            analysis_event = plan.analysis_event
            if not isinstance(analysis_event, TrainingLifecycleEvent):
                raise RuntimeError(
                    "deliver saliency terminal plan lost its analysis event"
                )
            if self._publish_training_analysis(analysis_event) is False:
                return False
            self._mark_saliency_progress(
                notification.status,
                analysis_delivered=True,
            )

        progress = self._saliency_delivery_progress(notification.status)
        if not progress.visualization_delivered:
            if self._publish_saliency_changed(notification) is False:
                return False
            self._mark_saliency_progress(
                notification.status,
                visualization_delivered=True,
            )

        self.discard_saliency_terminal(notification.status)
        return True

    def _saliency_delivery_progress(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> _SaliencyTerminalDeliveryProgress:
        with self._saliency_lock:
            progress = self._saliency_progress.get(status.generation)
            if progress is None or progress.status != status:
                progress = _SaliencyTerminalDeliveryProgress(status=status)
                self._saliency_progress[status.generation] = progress
            return progress

    def _mark_saliency_progress(
        self,
        status: PostTrainingSaliencyStatus,
        *,
        analysis_delivered: bool = False,
        visualization_delivered: bool = False,
    ) -> None:
        with self._saliency_lock:
            progress = self._saliency_progress.get(status.generation)
            if progress is None or progress.status != status:
                return
            self._saliency_progress[status.generation] = replace(
                progress,
                analysis_delivered=(progress.analysis_delivered or analysis_delivered),
                visualization_delivered=(
                    progress.visualization_delivered or visualization_delivered
                ),
            )

    def has_delivered_saliency_generation(self, generation: int) -> bool:
        """Return whether public callbacks acknowledged this generation."""
        return self._saliency_boundary.has_delivered_generation(generation)

    def saliency_delivery_state(self) -> SaliencyTerminalDeliveryState:
        """Return the notification queue state atomically."""
        return self._saliency_boundary.delivery_state()

    def wait_for_saliency_delivery(self, timeout: float | None = None) -> bool:
        """Wait until no committed saliency notification needs acknowledgement."""
        return self._saliency_boundary.wait_for_idle(timeout=timeout)

    def discard_pending(self) -> None:
        """Compatibility alias for permanent lifecycle close."""
        self.close()

    def close(self) -> None:
        """Fence new delivery without waiting on externally owned callbacks."""
        with self._training_condition:
            self._closed = True
            self._training_pending.clear()
            self._training_retry_exhausted = True
            self._training_retry_owner = None
            self._training_condition.notify_all()
        with self._saliency_lock:
            self._pending_saliency_status = None
            self._saliency_progress.clear()
        self._saliency_boundary.discard_pending()
