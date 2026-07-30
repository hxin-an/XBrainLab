"""Qt-compatible observer bridge for thread-safe backend-to-UI signalling."""

import contextlib
from collections.abc import Callable
from threading import Lock
from typing import Any
from weakref import finalize, ref

from PyQt6 import sip
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable, ObserverDeliveryStatus


class _ObserverSubscription:
    """Own one idempotent backend subscription outside QObject teardown."""

    def __init__(
        self,
        observable: Observable,
        event_name: str,
        callback: Callable[..., Any],
    ) -> None:
        self._lock = Lock()
        self._observable: Observable | None = observable
        self._event_name = event_name
        self._callback: Callable[..., Any] | None = callback

    def close(self, _destroyed: object = None) -> None:
        """Unsubscribe once without invoking weakref machinery from Qt."""
        with self._lock:
            observable = self._observable
            callback = self._callback
            if observable is None or callback is None:
                return
            self._observable = None
            self._callback = None
        observable.unsubscribe(self._event_name, callback)


class QtObserverBridge(QObject):
    """Bridge between backend Observer notifications and Qt Signals.

    Ensures thread-safety when backend events fire on background threads
    and UI slots must run on the main thread.

    Attributes:
        triggered: Signal emitted as ``(args_tuple, kwargs_dict)``.
        observable: The backend ``Observable`` being subscribed to.
        event_name: The event name subscribed on the observable.

    """

    triggered = pyqtSignal(tuple, dict)  # (args), {kwargs}

    def __init__(
        self,
        observable: Observable,
        event_name: str,
        parent=None,
        *,
        require_slot_acknowledgement: bool = False,
    ):
        """Initialize the bridge and subscribe to the backend event.

        Args:
            observable: The backend ``Observable`` instance.
            event_name: Name of the event to subscribe to.
            parent: Optional parent QObject.

        """
        super().__init__(parent)
        self.observable = observable
        self.event_name = event_name
        self._slot: Callable[..., Any] | None = None
        self._active = True
        self._require_slot_acknowledgement = bool(require_slot_acknowledgement)
        self._synchronous_dispatch_result: bool | None = None
        # Qt AutoConnection invokes same-thread events directly and queues
        # background-thread emissions onto this QObject's GUI thread.
        self.triggered.connect(self._dispatch)

        bridge_ref = ref(self)

        def observer_callback(
            *args: Any,
            **kwargs: Any,
        ) -> bool | ObserverDeliveryStatus | None:
            bridge = bridge_ref()
            if bridge is not None:
                delivered = bridge._on_event(*args, **kwargs)
                if bridge._require_slot_acknowledgement:
                    return delivered
            return None

        self._observer_callback: Callable[..., Any] | None = observer_callback
        self.observable.subscribe(self.event_name, observer_callback)
        self._observer_subscription = _ObserverSubscription(
            observable,
            str(event_name),
            observer_callback,
        )
        self._observer_finalizer = finalize(
            self,
            self._observer_subscription.close,
        )
        # Product owners call cleanup explicitly. The finalizer is a safety net
        # for Python wrapper collection, not an interpreter-shutdown callback.
        self._observer_finalizer.atexit = False
        self.destroyed.connect(self._observer_subscription.close)

    def _on_event(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> bool | ObserverDeliveryStatus:
        """Callback invoked by the backend on any thread.

        Wraps arguments and emits the ``triggered`` Qt signal for
        thread-safe delivery to the main thread.

        Args:
            *args: Positional arguments from the backend event.
            **kwargs: Keyword arguments from the backend event.

        """
        # Wrap args/kwargs to send via signal
        # Note: Qt signals need pickle-able types usually, but tuple/dict are fine.
        if not self._active or sip.isdeleted(self):
            return False
        synchronous = QThread.currentThread() is self.thread()
        if self._require_slot_acknowledgement and synchronous:
            self._synchronous_dispatch_result = None
        with contextlib.suppress(RuntimeError):
            self.triggered.emit(args, kwargs)
            if not self._require_slot_acknowledgement:
                return True
            if synchronous:
                return self._synchronous_dispatch_result is True
            # The GUI slot will explicitly acknowledge after queued delivery.
            return ObserverDeliveryStatus.DEFERRED
        return False

    def connect_to(self, slot: Callable[..., Any]) -> None:
        """Connect the bridge's triggered signal to a UI slot.

        The slot receives unpacked ``(*args, **kwargs)`` from the
        backend event.

        Args:
            slot: A callable to invoke when the event fires.

        """
        if not callable(slot):
            raise TypeError("Observer bridge slots must be callable.")
        self._slot = slot

    def _dispatch(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
        """Invoke the registered slot on this bridge's Qt thread."""
        if not self._active or sip.isdeleted(self):
            return False
        slot = self._slot
        if slot is not None:
            try:
                slot(*args, **kwargs)
            except Exception:
                self._synchronous_dispatch_result = False
                logger.exception(
                    "Qt observer slot failed for %s",
                    self.event_name,
                )
                return False
        self._synchronous_dispatch_result = True
        return True

    def cleanup(self):
        """Unsubscribe from the backend observable event and disconnect signals."""
        self._active = False
        self._observer_callback = None
        with contextlib.suppress(TypeError, RuntimeError):
            self._observer_subscription.close()
            self._observer_finalizer.detach()
        self._slot = None
        with contextlib.suppress(TypeError, RuntimeError):
            self.triggered.disconnect()
