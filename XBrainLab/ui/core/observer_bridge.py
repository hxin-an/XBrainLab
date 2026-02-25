"""Qt-compatible observer bridge for thread-safe backend-to-UI signalling."""

import contextlib

from PyQt6.QtCore import QObject, pyqtSignal

from XBrainLab.backend.utils.observer import Observable


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

    def __init__(self, observable: Observable, event_name: str, parent=None):
        """Initialize the bridge and subscribe to the backend event.

        Args:
            observable: The backend ``Observable`` instance.
            event_name: Name of the event to subscribe to.
            parent: Optional parent QObject.

        """
        super().__init__(parent)
        self.observable = observable
        self.event_name = event_name

        # Subscribe to the backend event
        self.observable.subscribe(self.event_name, self._on_event)

    def _on_event(self, *args, **kwargs):
        """Callback invoked by the backend on any thread.

        Wraps arguments and emits the ``triggered`` Qt signal for
        thread-safe delivery to the main thread.

        Args:
            *args: Positional arguments from the backend event.
            **kwargs: Keyword arguments from the backend event.

        """
        # Wrap args/kwargs to send via signal
        # Note: Qt signals need pickle-able types usually, but tuple/dict are fine.
        self.triggered.emit(args, kwargs)

    def connect_to(self, slot):
        """Connect the bridge's triggered signal to a UI slot.

        The slot receives unpacked ``(*args, **kwargs)`` from the
        backend event.

        Args:
            slot: A callable to invoke when the event fires.

        """
        self._wrapper = lambda args, kwargs: slot(*args, **kwargs)
        self.triggered.connect(self._wrapper)

    def cleanup(self):
        """Unsubscribe from the backend observable event and disconnect signals."""
        self.observable.unsubscribe(self.event_name, self._on_event)
        with contextlib.suppress(TypeError):
            self.triggered.disconnect()
