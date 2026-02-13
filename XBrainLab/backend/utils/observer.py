from collections.abc import Callable

from XBrainLab.backend.utils.logger import logger


class Observable:
    """
    A lightweight, pure Python implementation of the Observer pattern.
    Replaces PyQt specific signals for backend components.
    """

    def __init__(self):
        self._observers: dict[str, list[Callable]] = {}

    def subscribe(self, event_name: str, callback: Callable) -> None:
        """
        Subscribe a callback function to an event.

        Args:
            event_name: The name of the event to subscribe to.
            callback: The function to call when the event is notified.
        """
        if event_name not in self._observers:
            self._observers[event_name] = []
        if callback not in self._observers[event_name]:
            self._observers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable) -> None:
        """
        Unsubscribe a callback function from an event.

        Args:
            event_name: The name of the event.
            callback: The function to remove.
        """
        if event_name in self._observers and callback in self._observers[event_name]:
            self._observers[event_name].remove(callback)

    def notify(self, event_name: str, *args, **kwargs):
        """Notify all subscribers of an event."""
        if event_name in self._observers:
            for callback in self._observers[event_name]:
                self._safe_call(event_name, callback, *args, **kwargs)

    def _safe_call(self, event_name: str, callback: Callable, *args, **kwargs):
        try:
            callback(*args, **kwargs)
        except Exception as e:
            # Prevent one subscriber's error from breaking others

            logger.error(f"Error in subscriber for {event_name}: {e}", exc_info=True)
