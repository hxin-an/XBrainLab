"""Base panel class providing a standardized interface for all application panels."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.core.observer_bridge import QtObserverBridge

if TYPE_CHECKING:
    from collections.abc import Callable


class BasePanel(QWidget):
    """Abstract base class for all application panels.

    Enforces a consistent interface for initialization, update, and
    cleanup. Subclasses must call ``init_ui()`` and optionally
    ``_setup_bridges()`` explicitly after their own setup.

    Attributes:
        controller: The backend controller bound to this panel.
        main_window: Reference to the parent ``MainWindow``, or ``None``.

    """

    def __init__(self, parent=None, controller=None):
        """Initialize the base panel.

        Args:
            parent: Optional parent widget (typically ``MainWindow``).
            controller: Optional backend controller for data access.

        """
        super().__init__(parent)
        self.controller = controller
        # Attempt to resolve main_window from parent
        self.main_window = parent if getattr(parent, "study", None) else None

        # Registry for bridges created via _create_bridge
        self._bridges: list[QtObserverBridge] = []

        # Note: We do NOT call _setup_bridges() or init_ui() here to allow
        # subclasses to perform necessary setup (like creating actions/helpers)
        # before UI initialization. Subclasses must call these methods explicitly.

    def init_ui(self) -> None:
        """Initialize UI components.

        Must be implemented by subclasses.

        Raises:
            NotImplementedError: Always, unless overridden.

        """
        raise NotImplementedError

    def update_panel(self, *args, **kwargs) -> None:
        """Refresh panel content when backend state changes.

        Called by observers or the navigation system. Override in
        subclasses to implement refresh logic.

        Args:
            *args: Variable positional arguments from observers.
            **kwargs: Variable keyword arguments from observers.

        """

    def _setup_bridges(self) -> None:
        """Set up observer bridges connecting controller events to UI.

        Optional override for subclasses that need reactive updates.
        """

    def _create_bridge(
        self,
        controller: Observable,
        event: str,
        handler: Callable,
    ) -> QtObserverBridge:
        """Create and register a ``QtObserverBridge``.

        Convenience helper that reduces boilerplate in
        ``_setup_bridges`` overrides.  All created bridges are stored in
        ``self._bridges`` so they remain referenced for the lifetime of
        the panel.

        Args:
            controller: The backend controller to observe.
            event: The event name to subscribe to.
            handler: Callback invoked when the event fires.

        Returns:
            The created ``QtObserverBridge`` instance.

        """
        bridge = QtObserverBridge(controller, event, self)
        bridge.connect_to(handler)
        self._bridges.append(bridge)
        return bridge

    def set_busy(self, busy: bool):
        """Set the panel's busy state, updating cursor and interactivity.

        Args:
            busy: If ``True``, shows a wait cursor and disables the widget.

        """
        if busy:
            self.setCursor(Qt.CursorShape.WaitCursor)
            self.setEnabled(False)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setEnabled(True)

    def cleanup(self) -> None:
        """Clean up resources, bridges, or threads on close.

        Optional override for subclasses with disposable resources.
        """
