from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


class BasePanel(QWidget):
    """
    Abstract base class for all application panels (Dataset, Preprocess, etc.).
    Enforces a consistent interface for initialization and updates.
    """

    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        self.controller = controller
        # Attempt to resolve main_window from parent
        self.main_window = parent if getattr(parent, "study", None) else None

        # Note: We do NOT call _setup_bridges() or init_ui() here to allow
        # subclasses to perform necessary setup (like creating actions/helpers)
        # before UI initialization. Subclasses must call these methods explicitly.

    def init_ui(self) -> None:
        """
        Initialize UI components.
        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def update_panel(self, *args, **kwargs) -> None:
        """
        Refresh panel content.
        Called by observers when backend state changes.
        """

    def _setup_bridges(self) -> None:
        """
        Set up observer bridges to connect Controller events to UI updates.
        Optional override.
        """

    def set_busy(self, busy: bool):
        """
        Set the panel's busy state, updating the cursor and interactivity.
        """
        if busy:
            self.setCursor(Qt.CursorShape.WaitCursor)
            self.setEnabled(False)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setEnabled(True)

    def cleanup(self) -> None:
        """
        Cleanup resources, bridges, or threads on close.
        Optional override.
        """
