"""Lightweight Observer pattern implementation for backend event notification."""

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any

from XBrainLab.backend.utils.logger import logger

_MAX_RETAINED_BATCH_DELIVERIES = 2048


class ObserverDeliveryStatus(str, Enum):
    """Typed result for consumers that distinguish queued from rendered work."""

    DELIVERED = "delivered"
    DEFERRED = "deferred"
    FAILED = "failed"


@dataclass(slots=True)
class _NotificationBatchState:
    """Context-owned deferred events for one outer notification batch."""

    generation: int
    depth: int = 1
    pending_events: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = field(
        default_factory=dict
    )


class Observable:
    """A pure Python implementation of the Observer pattern.

    Manages event subscriptions and notifications, decoupling publishers
    from subscribers without depending on UI frameworks.

    Attributes:
        _observers: Mapping of event names to lists of callback functions.
        _batch_depth: Nesting depth of ``batch_notifications`` contexts.
        _pending_events: Events deferred during a batch that will be
            emitted once all nested batches are exited.

    """

    def __init__(self):
        """Initialize the observable with an empty subscriber registry."""
        self._observers: dict[str, list[Callable]] = {}
        self._observer_lock = Lock()
        self._batch_state: ContextVar[_NotificationBatchState | None] = ContextVar(
            f"xbrainlab_observer_batch_{id(self)}",
            default=None,
        )
        self._batch_ledger_lock = Lock()
        self._batch_sequence: int = 0
        self._active_batch_generations: set[int] = set()
        self._batch_delivery_results: dict[tuple[int, str], bool] = {}

    @property
    def _batch_depth(self) -> int:
        """Compatibility view of the current execution context's nesting depth."""
        state = self._batch_state.get()
        return state.depth if state is not None else 0

    @property
    def _pending_events(
        self,
    ) -> dict[str, tuple[tuple[Any, ...], dict[str, Any]]]:
        """Compatibility view of events deferred by the current context."""
        state = self._batch_state.get()
        return state.pending_events if state is not None else {}

    @property
    def notifications_deferred(self) -> bool:
        """Return whether callbacks are currently held by an outer batch."""
        return self._batch_state.get() is not None

    @property
    def notification_batch_generation(self) -> int | None:
        """Return the exact outer batch currently holding notifications."""
        state = self._batch_state.get()
        return state.generation if state is not None else None

    def consume_batched_delivery(
        self,
        event_name: str,
        generation: int,
    ) -> bool | None:
        """Consume one exact batch callback result, if that event was emitted."""
        with self._batch_ledger_lock:
            return self._batch_delivery_results.pop((generation, event_name), None)

    def is_notification_batch_active(self, generation: int) -> bool:
        """Return whether one exact outer batch still owns deferred delivery."""
        with self._batch_ledger_lock:
            return generation in self._active_batch_generations

    def subscribe(self, event_name: str, callback: Callable) -> None:
        """Subscribe a callback function to an event.

        Args:
            event_name: The name of the event to subscribe to.
            callback: The function to call when the event is notified.

        """
        with self._observer_lock:
            if event_name not in self._observers:
                self._observers[event_name] = []
            if callback not in self._observers[event_name]:
                self._observers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable) -> None:
        """Unsubscribe a callback function from an event.

        Args:
            event_name: The name of the event.
            callback: The function to remove.

        """
        with self._observer_lock:
            if (
                event_name in self._observers
                and callback in self._observers[event_name]
            ):
                self._observers[event_name].remove(callback)

    def notify(self, event_name: str, *args, **kwargs) -> bool:
        """Notify all subscribers of an event, passing along any arguments.

        When called inside a :meth:`batch_notifications` context, the
        notification is deferred and only emitted once after the outermost
        context exits. The return value reports whether every immediate
        subscriber completed successfully; exceptions remain isolated.

        Args:
            event_name: The name of the event to notify.
            *args: Positional arguments to pass to each callback.
            **kwargs: Keyword arguments to pass to each callback.

        """
        batch = self._batch_state.get()
        if batch is not None:
            # Defer — keep last args/kwargs per event
            batch.pending_events[event_name] = (args, kwargs)
            return True

        delivered = True
        for callback in self._observer_snapshot(event_name):
            delivered = (
                self._safe_call(event_name, callback, *args, **kwargs) and delivered
            )
        return delivered

    def notify_delivery(
        self,
        event_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> ObserverDeliveryStatus:
        """Notify subscribers while preserving deferred UI delivery semantics."""
        batch = self._batch_state.get()
        if batch is not None:
            batch.pending_events[event_name] = (args, kwargs)
            return ObserverDeliveryStatus.DEFERRED

        status = ObserverDeliveryStatus.DELIVERED
        for callback in self._observer_snapshot(event_name):
            try:
                result = callback(*args, **kwargs)
            except Exception as exc:
                logger.error(
                    "Error in subscriber for %s: %s",
                    event_name,
                    exc,
                    exc_info=True,
                )
                return ObserverDeliveryStatus.FAILED
            if result is False or result is ObserverDeliveryStatus.FAILED:
                return ObserverDeliveryStatus.FAILED
            if result is ObserverDeliveryStatus.DEFERRED:
                status = ObserverDeliveryStatus.DEFERRED
        return status

    @contextmanager
    def batch_notifications(self):
        """Suppress duplicate notifications during a batch of operations.

        All :meth:`notify` calls made inside this context are collected
        and de-duplicated.  Each unique event name is emitted exactly
        once when the outermost ``batch_notifications`` context exits.

        Supports nesting — only the outermost exit triggers emission.

        Example::

            with controller.batch_notifications():
                controller.apply_filter(4, 40)
                controller.apply_notch_filter(50)
            # ``preprocess_changed`` is emitted only once here.

        """
        active = self._batch_state.get()
        if active is not None:
            active.depth += 1
            try:
                yield
            finally:
                active.depth -= 1
            return

        with self._batch_ledger_lock:
            self._batch_sequence += 1
            generation = self._batch_sequence
            self._active_batch_generations.add(generation)
        batch = _NotificationBatchState(generation=generation)
        token = self._batch_state.set(batch)
        try:
            yield
        finally:
            self._batch_state.reset(token)
            try:
                pending = dict(batch.pending_events)
                batch.pending_events.clear()
                for evt_name, (evt_args, evt_kwargs) in pending.items():
                    delivered = True
                    for callback in self._observer_snapshot(evt_name):
                        delivered = (
                            self._safe_call(
                                evt_name,
                                callback,
                                *evt_args,
                                **evt_kwargs,
                            )
                            and delivered
                        )
                    self._remember_batched_delivery(
                        generation,
                        evt_name,
                        delivered,
                    )
            finally:
                with self._batch_ledger_lock:
                    self._active_batch_generations.discard(generation)

    def _observer_snapshot(self, event_name: str) -> tuple[Callable, ...]:
        """Copy subscribers without holding the registry lock during callbacks."""
        with self._observer_lock:
            return tuple(self._observers.get(event_name, ()))

    def _remember_batched_delivery(
        self,
        generation: int,
        event_name: str,
        delivered: bool,
    ) -> None:
        """Retain exact callback acknowledgement without cross-command clearing."""
        with self._batch_ledger_lock:
            self._batch_delivery_results[(generation, event_name)] = delivered
            while len(self._batch_delivery_results) > _MAX_RETAINED_BATCH_DELIVERIES:
                oldest = next(iter(self._batch_delivery_results))
                self._batch_delivery_results.pop(oldest, None)

    def _safe_call(
        self,
        event_name: str,
        callback: Callable,
        *args,
        **kwargs,
    ) -> bool:
        """Invoke a callback safely, logging errors without propagating them.

        Args:
            event_name: The event name (for error logging context).
            callback: The subscriber function to call.
            *args: Positional arguments to pass to the callback.
            **kwargs: Keyword arguments to pass to the callback.

        """
        try:
            result = callback(*args, **kwargs)
        except Exception as e:
            # Prevent one subscriber's error from breaking others

            logger.error("Error in subscriber for %s: %s", event_name, e, exc_info=True)
            return False
        else:
            return result is not False
