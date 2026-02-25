"""Application-wide central event bus for decoupled component messaging."""

from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    """Central event bus for application-wide messaging.

    Implements the Singleton pattern. Use ``get_instance()`` to obtain
    the shared instance.

    Attributes:
        status_message: Signal emitted with ``(message, duration_ms)``.
        error_occurred: Signal emitted with ``(error_message,)``.
        data_refreshed: Signal emitted when data state changes globally.
        model_updated: Signal emitted with ``(model_name,)`` on model changes.
    """

    _instance = None

    # --- Common Application Events ---
    # Global status update: (message, duration_ms)
    status_message = pyqtSignal(str, int)

    # Global error reporting: (error_message)
    error_occurred = pyqtSignal(str)

    # Model/Data State Changes that cross panel boundaries
    data_refreshed = pyqtSignal()
    model_updated = pyqtSignal(str)  # model_name

    @classmethod
    def get_instance(cls):
        """Get the singleton instance of the EventBus.

        Returns:
            The shared ``EventBus`` instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize the EventBus.

        Raises:
            RuntimeError: If an instance already exists.
        """
        super().__init__()
        if EventBus._instance is not None:
            raise RuntimeError("EventBus is a singleton! Use get_instance() instead.")
