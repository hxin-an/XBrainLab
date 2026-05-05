"""Service for coordinating AggregateInfoPanel updates across the application."""

import weakref
from unittest.mock import Mock

from PyQt6.QtCore import QObject

from XBrainLab.backend.application import QueryStateCommand
from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.observer_bridge import QtObserverBridge


class InfoPanelService(QObject):
    """Service to manage AggregateInfoPanel updates across the application.

    Centralizes data fetching from dataset and preprocess controllers,
    and ensures all registered panels show consistent state via
    ``QtObserverBridge`` subscriptions.

    Attributes:
        study: The application ``Study`` instance.

    """

    def __init__(self, study: "Study"):
        """Initialize the service and connect to backend controllers.

        Args:
            study: The application ``Study`` instance.

        """
        super().__init__()
        self.study = study
        self._listeners: weakref.WeakSet = weakref.WeakSet()
        self._setup_bridges()

    def _setup_bridges(self):
        """Connect observer bridges to dataset and preprocess controllers."""
        self.dataset_bridge = QtObserverBridge(
            self.study.get_controller("dataset"),
            "data_changed",
            self,
        )
        self.dataset_bridge.connect_to(self.notify_all)

        self.preprocess_bridge = QtObserverBridge(
            self.study.get_controller("preprocess"),
            "preprocess_changed",
            self,
        )
        self.preprocess_bridge.connect_to(self.notify_all)

    def register(self, panel):
        """Register an info panel to receive automatic updates.

        Adds the panel to the weak listener set and triggers an
        immediate update with current data.

        Args:
            panel: An ``AggregateInfoPanel`` instance.

        """
        self._listeners.add(panel)
        # Robustness: Remove if explicitly destroyed (though WeakSet handles GC)
        if hasattr(panel, "destroyed"):
            panel.destroyed.connect(lambda: self.unregister(panel))
        self.update_single(panel)  # Initial update

    def unregister(self, panel):
        """Remove a panel from the listener set.

        Args:
            panel: The panel to unregister.

        """
        self._listeners.discard(panel)

    def notify_all(self, *args, **kwargs):
        """Fetch current data and update all registered panels."""
        loaded, preprocessed = self._query_data_lists()

        # Notify listeners
        for panel in self._listeners:
            self._safe_update_panel(panel, loaded, preprocessed)

    def _safe_update_panel(self, panel, loaded, preprocessed):
        """Update a single panel, catching runtime errors gracefully.

        Args:
            panel: The info panel to update.
            loaded: List of loaded data objects.
            preprocessed: List of preprocessed data objects.

        """
        try:
            panel.update_info(
                loaded_data_list=loaded,
                preprocessed_data_list=preprocessed,
            )
        except RuntimeError:
            # Handle deleted C++ objects in weak set if any
            pass
        except Exception as e:
            # Log other unexpected errors
            logger.error("Error updating info panel: %s", e)

    def update_single(self, panel):
        """Manually update a single panel with current data.

        Args:
            panel: The info panel to update.

        """
        loaded, preprocessed = self._query_data_lists()

        panel.update_info(loaded_data_list=loaded, preprocessed_data_list=preprocessed)

    def _query_data_lists(self):
        """Return raw/preprocessed lists through ApplicationService when possible."""
        if isinstance(self.study, Study) and not isinstance(self.study, Mock):
            result = BackendFacade(self.study).service.execute(
                QueryStateCommand(query="data_lists", include_objects=True),
            )
            if result.ok:
                return (
                    list(result.diagnostics.get("loaded_data_list", [])),
                    list(result.diagnostics.get("preprocessed_data_list", [])),
                )
            logger.debug("Info panel state query failed: %s", result.message)

        loaded = []
        if self.study.get_controller("dataset"):
            loaded = self.study.get_controller("dataset").get_loaded_data_list()

        preprocessed = []
        if self.study.get_controller("preprocess"):
            preprocessed = self.study.get_controller(
                "preprocess",
            ).get_preprocessed_data_list()

        return loaded, preprocessed
