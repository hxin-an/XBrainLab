import weakref
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject

from XBrainLab.ui.core.observer_bridge import QtObserverBridge

if TYPE_CHECKING:
    from XBrainLab.backend.study import Study


class InfoPanelService(QObject):
    """
    Service to manage AggregateInfoPanel updates across the application.
    Centralizes data fetching and ensures all registered panels show consistent state.
    """

    def __init__(self, study: "Study"):
        super().__init__()
        self.study = study
        self._listeners: weakref.WeakSet = weakref.WeakSet()
        self._setup_bridges()

    def _setup_bridges(self):
        """Connect to backend controllers."""
        self.dataset_bridge = QtObserverBridge(
            self.study.get_controller("dataset"), "data_changed", self
        )
        self.dataset_bridge.connect_to(self.notify_all)

        self.preprocess_bridge = QtObserverBridge(
            self.study.get_controller("preprocess"), "preprocess_changed", self
        )
        self.preprocess_bridge.connect_to(self.notify_all)

        # also listen to import finished
        self.import_bridge = QtObserverBridge(
            self.study.get_controller("dataset"), "import_finished", self
        )
        self.import_bridge.connect_to(self.notify_all)

    def register(self, panel):
        """Register an InfoPanel to receive updates."""
        self._listeners.add(panel)
        # Robustness: Remove if explicitly destroyed (though WeakSet handles GC)
        if hasattr(panel, "destroyed"):
            panel.destroyed.connect(lambda: self.unregister(panel))
        self.update_single(panel)  # Initial update

    def unregister(self, panel):
        """Explicitly remove a panel from listeners."""
        self._listeners.discard(panel)

    def notify_all(self, *args, **kwargs):
        """Update all registered panels with latest data."""
        # Fetch current state
        loaded = []
        if self.study.get_controller("dataset"):
            loaded = self.study.get_controller("dataset").get_loaded_data_list()

        preprocessed = []
        if self.study.get_controller("preprocess"):
            preprocessed = self.study.get_controller(
                "preprocess"
            ).get_preprocessed_data_list()

        # Notify listeners
        # Notify listeners
        for panel in self._listeners:
            self._safe_update_panel(panel, loaded, preprocessed)

    def _safe_update_panel(self, panel, loaded, preprocessed):
        try:
            panel.update_info(
                loaded_data_list=loaded, preprocessed_data_list=preprocessed
            )
        except RuntimeError:
            # Handle deleted C++ objects in weak set if any
            pass
        except Exception as e:
            # Log other unexpected errors
            print(f"Error updating info panel: {e}")

    def update_single(self, panel):
        """Manually update a single panel."""
        loaded = []
        if self.study.get_controller("dataset"):
            loaded = self.study.get_controller("dataset").get_loaded_data_list()

        preprocessed = []
        if self.study.get_controller("preprocess"):
            preprocessed = self.study.get_controller(
                "preprocess"
            ).get_preprocessed_data_list()

        panel.update_info(loaded_data_list=loaded, preprocessed_data_list=preprocessed)
