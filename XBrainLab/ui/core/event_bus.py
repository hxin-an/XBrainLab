from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    """
    Central event bus for application-wide messaging and decoupling components.
    follows Singleton pattern.
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
        """Get the singleton instance of the EventBus."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        if EventBus._instance is not None:
            raise RuntimeError("EventBus is a singleton! Use get_instance() instead.")
