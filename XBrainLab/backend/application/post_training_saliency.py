"""Application-owned terminal notification delivery for saliency commands."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Event, Lock, Thread, Timer, current_thread

from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyStatus,
    TrainingLifecycleEvent,
)
from XBrainLab.backend.utils.logger import logger

_SALIENCY_NOTIFICATION_RETRY_SECONDS = 0.05


@dataclass(frozen=True, slots=True)
class SaliencyTerminalNotification:
    """One committed terminal publication delivered after command locks."""

    status: PostTrainingSaliencyStatus
    analysis_event: TrainingLifecycleEvent
    visualization_batch_generation: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status, PostTrainingSaliencyStatus)
            or not self.status.phase.terminal
        ):
            raise TypeError("saliency terminal notification status is invalid")
        if not isinstance(self.analysis_event, TrainingLifecycleEvent):
            raise TypeError("saliency terminal analysis event is invalid")
        if self.visualization_batch_generation is not None and (
            isinstance(self.visualization_batch_generation, bool)
            or not isinstance(self.visualization_batch_generation, int)
            or self.visualization_batch_generation < 1
        ):
            raise TypeError("saliency visualization batch generation is invalid")


@dataclass(frozen=True, slots=True)
class SaliencyTerminalDeliveryState:
    """Immutable truth for one post-command terminal delivery boundary."""

    pending_generations: tuple[int, ...]
    active_generation: int | None
    delivered_generation: int
    retry_owner_active: bool
    retry_unavailable: bool


@dataclass(slots=True)
class _SaliencyNotificationReservation:
    notification: SaliencyTerminalNotification
    staged: bool = False


class PostCommandSaliencyNotificationBoundary:
    """Commit typed saliency delivery atomically at the outer command exit."""

    def __init__(
        self,
        deliver: Callable[[SaliencyTerminalNotification], object],
    ) -> None:
        self._deliver = deliver
        self._delivery_lock = Lock()
        self._committed_generation = -1
        self._delivered_generation = -1
        self._reservations: dict[int, _SaliencyNotificationReservation] = {}
        self._delivery_queue: deque[SaliencyTerminalNotification] = deque()
        self._delivering = False
        self._retry_timer: Timer | None = None
        self._retry_fallback_thread: Thread | None = None
        self._retry_unavailable = False
        self._delivery_idle = Event()
        self._delivery_idle.set()
        self._pending: ContextVar[list[SaliencyTerminalNotification] | None] = (
            ContextVar(
                f"xbrainlab_saliency_notifications_{id(self)}",
                default=None,
            )
        )

    @contextmanager
    def capture(self) -> Iterator[None]:
        """Stage nested notifications and commit one failure-atomic queue batch."""
        pending = self._pending.get()
        if pending is not None:
            yield
            return

        pending = []
        token = self._pending.set(pending)
        try:
            yield
        finally:
            self._pending.reset(token)
            try:
                self._enqueue_deliveries(pending)
            except BaseException:
                self._rollback_staged_deliveries(pending)
                raise

    def reserve(self, notification: SaliencyTerminalNotification) -> bool:
        """Acquire temporary ownership without committing delivery."""
        if not isinstance(notification, SaliencyTerminalNotification):
            raise TypeError("saliency terminal notification is invalid")
        generation = notification.status.generation
        with self._delivery_lock:
            if generation <= self._committed_generation:
                return False
            if self._reservations and generation <= max(self._reservations):
                return False
            self._reservations[generation] = _SaliencyNotificationReservation(
                notification
            )
        return True

    def release(self, notification: SaliencyTerminalNotification) -> bool:
        """Roll back one exact uncommitted reservation so it can be retried."""
        if not isinstance(notification, SaliencyTerminalNotification):
            raise TypeError("saliency terminal notification is invalid")
        generation = notification.status.generation
        with self._delivery_lock:
            reservation = self._reservations.get(generation)
            if reservation is None or reservation.notification != notification:
                return False
            self._reservations.pop(generation)
        return True

    def publish_reserved(self, notification: SaliencyTerminalNotification) -> bool:
        """Stage a reservation, committing only after a durable queue handoff."""
        if not isinstance(notification, SaliencyTerminalNotification):
            raise TypeError("saliency terminal notification is invalid")
        generation = notification.status.generation
        pending = self._pending.get()
        if pending is not None:
            with self._delivery_lock:
                reservation = self._reservations.get(generation)
                if reservation is None or reservation.notification != notification:
                    raise RuntimeError(
                        "saliency terminal notification was not reserved"
                    )
                if generation <= self._committed_generation:
                    self._reservations.pop(generation)
                    return False
                if reservation.staged:
                    raise RuntimeError(
                        "saliency terminal notification is already staged"
                    )
                reservation.staged = True
                try:
                    pending.append(notification)
                except BaseException:
                    reservation.staged = False
                    raise
            return True

        committed = self._enqueue_deliveries((notification,))
        return generation in committed

    def defer(self, notification: SaliencyTerminalNotification) -> bool:
        """Reserve and publish one terminal generation exactly once."""
        if not self.reserve(notification):
            return False
        try:
            return self.publish_reserved(notification)
        except BaseException:
            self.release(notification)
            raise

    def _enqueue_deliveries(
        self,
        notifications: Iterable[SaliencyTerminalNotification],
    ) -> frozenset[int]:
        """Commit a complete queue handoff before advancing the ledger."""
        batch = tuple(notifications)
        if not batch:
            return frozenset()

        should_drain = False
        with self._delivery_lock:
            accepted: list[SaliencyTerminalNotification] = []
            committed_generation = self._committed_generation
            for notification in batch:
                generation = notification.status.generation
                reservation = self._reservations.get(generation)
                if reservation is None or reservation.notification != notification:
                    raise RuntimeError(
                        "saliency terminal notification was not reserved"
                    )
                if generation <= committed_generation:
                    continue
                accepted.append(notification)
                committed_generation = generation

            accepted_generations = frozenset(
                item.status.generation for item in accepted
            )
            if accepted:
                replacement_queue = self._delivery_queue.copy()
                replacement_queue.extend(accepted)
                self._delivery_queue = replacement_queue
                self._delivery_idle.clear()

            for notification in batch:
                self._reservations.pop(notification.status.generation)
            self._committed_generation = committed_generation
            if self._delivery_queue and not self._delivering:
                self._delivering = True
                self._retry_unavailable = False
                should_drain = True

        if should_drain:
            self._drain_delivery_queue()
        return accepted_generations

    def _rollback_staged_deliveries(
        self,
        notifications: Iterable[SaliencyTerminalNotification],
    ) -> None:
        """Release an uncommitted capture batch after queue handoff failure."""
        with self._delivery_lock:
            for notification in notifications:
                generation = notification.status.generation
                reservation = self._reservations.get(generation)
                if (
                    reservation is not None
                    and reservation.notification == notification
                    and reservation.staged
                ):
                    self._reservations.pop(generation)

    def _drain_delivery_queue(self) -> None:
        """Invoke callbacks outside the ledger lock and commit after acknowledgement."""
        while True:
            with self._delivery_lock:
                if not self._delivery_queue:
                    self._delivering = False
                    self._retry_unavailable = False
                    self._delivery_idle.set()
                    return
                notification = self._delivery_queue[0]
                generation = notification.status.generation
                if generation <= self._delivered_generation:
                    self._delivery_queue.popleft()
                    continue
            try:
                delivered = self._deliver(notification) is not False
            except Exception:
                logger.exception("Could not deliver terminal saliency notification")
                delivered = False
            if not delivered:
                with self._delivery_lock:
                    self._delivering = False
                self._schedule_delivery_retry()
                return
            with self._delivery_lock:
                if self._delivery_queue and self._delivery_queue[0] == notification:
                    self._delivery_queue.popleft()
                self._delivered_generation = max(
                    self._delivered_generation,
                    generation,
                )
                self._retry_unavailable = False

    def _schedule_delivery_retry(self) -> None:
        """Schedule one delayed retry without blocking or recursively draining."""
        try:
            with self._delivery_lock:
                if not self._delivery_queue:
                    self._retry_unavailable = False
                    self._delivery_idle.set()
                    return
                if (
                    self._retry_timer is not None
                    or self._retry_fallback_thread is not None
                ):
                    return
                timer = Timer(
                    _SALIENCY_NOTIFICATION_RETRY_SECONDS,
                    self._retry_delivery_queue,
                )
                timer.daemon = True
                self._retry_timer = timer
        except Exception:
            logger.exception("Could not construct saliency notification retry")
            self._schedule_delivery_retry_fallback()
            return
        try:
            timer.start()
        except Exception:
            with self._delivery_lock:
                if self._retry_timer is timer:
                    self._retry_timer = None
            logger.exception("Could not schedule saliency notification retry")
            self._schedule_delivery_retry_fallback()

    def _schedule_delivery_retry_fallback(self) -> None:
        """Use one sleeping daemon worker when Timer.start itself is unavailable."""
        try:
            with self._delivery_lock:
                if not self._delivery_queue:
                    self._retry_unavailable = False
                    self._delivery_idle.set()
                    return
                if self._retry_fallback_thread is not None:
                    return
                thread = Thread(
                    target=self._run_delivery_retry_fallback,
                    name="xbrainlab-saliency-notification-retry",
                    daemon=True,
                )
                self._retry_fallback_thread = thread
        except Exception:
            self._mark_delivery_retry_unavailable()
            logger.exception("Could not construct saliency notification retry fallback")
            return
        try:
            thread.start()
        except Exception:
            with self._delivery_lock:
                if self._retry_fallback_thread is thread:
                    self._retry_fallback_thread = None
            self._mark_delivery_retry_unavailable()
            logger.exception("Could not start saliency notification retry fallback")

    def _run_delivery_retry_fallback(self) -> None:
        self._delivery_idle.wait(_SALIENCY_NOTIFICATION_RETRY_SECONDS)
        with self._delivery_lock:
            if self._retry_fallback_thread is current_thread():
                self._retry_fallback_thread = None
        self._retry_delivery_queue()

    def _mark_delivery_retry_unavailable(self) -> None:
        """Retain non-idle truth when no retry primitive can own the queue."""
        with self._delivery_lock:
            if self._delivery_queue:
                self._retry_unavailable = True
                self._delivery_idle.clear()

    def _retry_delivery_queue(self) -> None:
        """Resume the retained queue once, preserving bounded retry spacing."""
        with self._delivery_lock:
            if self._retry_timer is current_thread():
                self._retry_timer = None
            if self._delivering:
                return
            if not self._delivery_queue:
                self._retry_unavailable = False
                self._delivery_idle.set()
                return
            self._delivering = True
            self._retry_unavailable = False
        self._drain_delivery_queue()

    def retry_pending(self) -> None:
        """Prompt a retained queue without waiting for another public state read."""
        self._retry_delivery_queue()

    def has_delivered_generation(self, generation: int) -> bool:
        """Return whether callbacks acknowledged this generation or a newer one."""
        with self._delivery_lock:
            return generation <= self._delivered_generation

    def delivery_state(self) -> SaliencyTerminalDeliveryState:
        """Return queue, acknowledgement, and retry-owner truth atomically."""
        with self._delivery_lock:
            pending_generations = tuple(
                item.status.generation for item in self._delivery_queue
            )
            active_generation = (
                pending_generations[0]
                if self._delivering and pending_generations
                else None
            )
            return SaliencyTerminalDeliveryState(
                pending_generations=pending_generations,
                active_generation=active_generation,
                delivered_generation=self._delivered_generation,
                retry_owner_active=(
                    self._retry_timer is not None
                    or self._retry_fallback_thread is not None
                ),
                retry_unavailable=self._retry_unavailable,
            )

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        """Wait until no committed notification still needs acknowledgement."""
        return self._delivery_idle.wait(timeout=timeout)

    def discard_pending(self) -> None:
        """Abandon all undelivered work during permanent application close."""
        with self._delivery_lock:
            timer = self._retry_timer
            self._retry_timer = None
            self._retry_fallback_thread = None
            self._delivery_queue.clear()
            self._reservations.clear()
            self._delivering = False
            self._retry_unavailable = False
            self._delivery_idle.set()
        if timer is not None:
            timer.cancel()
