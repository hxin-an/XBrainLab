from PyQt6.QtCore import QObject, pyqtSignal

from XBrainLab.backend.utils.observer import Observable


class QtObserverBridge(QObject):
    """
    Bridges backend Observer notifications to Qt Signals.
    Ensures thread-safety when backend runs on a background thread
    and UI needs to update on the main thread.
    """

    triggered = pyqtSignal(tuple, dict)  # (args), {kwargs}

    def __init__(self, observable: Observable, event_name: str, parent=None):
        super().__init__(parent)
        self.observable = observable
        self.event_name = event_name

        # Subscribe to the backend event
        self.observable.subscribe(self.event_name, self._on_event)

    def _on_event(self, *args, **kwargs):
        """Called by backend (any thread). Emits proper Qt signal."""
        # Wrap args/kwargs to send via signal
        # Note: Qt signals need pickle-able types usually, but tuple/dict are fine.
        self.triggered.emit(args, kwargs)

    def connect_to(self, slot):
        """Helper to connect the key signal to a UI slot."""
        self.triggered.connect(lambda args, kwargs: slot(*args, **kwargs))

    def cleanup(self):
        """Unsubscribe when destroyed."""
        self.observable.unsubscribe(self.event_name, self._on_event)
