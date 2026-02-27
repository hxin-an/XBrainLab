"""Lightweight Observer pattern implementation for backend event notification."""

from collections.abc import Callable
from contextlib import contextmanager

from XBrainLab.backend.utils.logger import logger


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
        self._batch_depth: int = 0
        self._pending_events: dict[str, tuple[tuple, dict]] = {}

    def subscribe(self, event_name: str, callback: Callable) -> None:
        """Subscribe a callback function to an event.

        Args:
            event_name: The name of the event to subscribe to.
            callback: The function to call when the event is notified.

        """
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
        if event_name in self._observers and callback in self._observers[event_name]:
            self._observers[event_name].remove(callback)

    def notify(self, event_name: str, *args, **kwargs):
        """Notify all subscribers of an event, passing along any arguments.

        When called inside a :meth:`batch_notifications` context, the
        notification is deferred and only emitted once after the outermost
        context exits.

        Args:
            event_name: The name of the event to notify.
            *args: Positional arguments to pass to each callback.
            **kwargs: Keyword arguments to pass to each callback.

        """
        if self._batch_depth > 0:
            # Defer — keep last args/kwargs per event
            self._pending_events[event_name] = (args, kwargs)
            return

        if event_name in self._observers:
            for callback in list(self._observers[event_name]):
                self._safe_call(event_name, callback, *args, **kwargs)

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
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                pending = dict(self._pending_events)
                self._pending_events.clear()
                for evt_name, (evt_args, evt_kwargs) in pending.items():
                    if evt_name in self._observers:
                        for callback in list(self._observers[evt_name]):
                            self._safe_call(
                                evt_name,
                                callback,
                                *evt_args,
                                **evt_kwargs,
                            )

    def _safe_call(self, event_name: str, callback: Callable, *args, **kwargs):
        """Invoke a callback safely, logging errors without propagating them.

        Args:
            event_name: The event name (for error logging context).
            callback: The subscriber function to call.
            *args: Positional arguments to pass to the callback.
            **kwargs: Keyword arguments to pass to the callback.

        """
        try:
            callback(*args, **kwargs)
        except Exception as e:
            # Prevent one subscriber's error from breaking others

            logger.error("Error in subscriber for %s: %s", event_name, e, exc_info=True)
