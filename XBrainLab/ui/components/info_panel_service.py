"""Service for coordinating AggregateInfoPanel updates across the application."""

from __future__ import annotations

import weakref
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QObject

from XBrainLab.backend.application import ApplicationViewPublication
from XBrainLab.backend.utils.logger import logger


class InfoPanelService(QObject):
    """Render publication-owned Aggregate Information rows across the desktop."""

    def __init__(self, study: Any):
        super().__init__()
        self.study = study
        self._listeners: weakref.WeakSet = weakref.WeakSet()
        self._latest_publication: ApplicationViewPublication | None = None
        self._observes_controller_events = False

    def register(self, panel):
        """Register an info panel to receive automatic updates.

        Adds the panel to the weak listener set and replays the latest
        publication, or an empty fail-closed state before the first publication.

        Args:
            panel: An ``AggregateInfoPanel`` instance.

        """
        self._listeners.add(panel)
        self.update_single(panel)  # Initial update

    def unregister(self, panel):
        """Remove a panel from the listener set.

        Args:
            panel: The panel to unregister.

        """
        self._listeners.discard(panel)

    def notify_all(self, *args, **kwargs):
        """Replay the latest publication, failing closed when none exists."""
        publication = self._latest_publication
        if publication is not None:
            loaded, preprocessed = self._rows_from_publication(publication)
        else:
            loaded, preprocessed = [], []

        for panel in list(self._listeners):
            self._safe_update_panel(panel, loaded, preprocessed)

    def render_publication(self, publication: ApplicationViewPublication) -> bool:
        """Render one committed revision into every aggregate summary panel."""
        if not isinstance(publication, ApplicationViewPublication):
            return False
        self._latest_publication = publication
        loaded, preprocessed = self._rows_from_publication(publication)
        rendered = True
        for panel in list(self._listeners):
            rendered = self._safe_update_panel(panel, loaded, preprocessed) and rendered
        return rendered

    def _safe_update_panel(self, panel, loaded, preprocessed) -> bool:
        """Update a single panel, catching runtime errors gracefully.

        Args:
            panel: The info panel to update.
            loaded: List of loaded data objects.
            preprocessed: List of preprocessed data objects.

        """
        if self._is_deleted_qobject(panel):
            self.unregister(panel)
            return True
        try:
            panel.update_info(
                loaded_data_list=loaded,
                preprocessed_data_list=preprocessed,
            )
        except RuntimeError:
            if self._is_deleted_qobject(panel):
                self.unregister(panel)
                return True
            logger.exception("Aggregate Information render failed")
            return False
        except Exception:
            logger.exception("Aggregate Information render failed")
            return False
        return True

    @staticmethod
    def _is_deleted_qobject(panel: Any) -> bool:
        if not isinstance(panel, QObject):
            return False
        try:
            return bool(sip.isdeleted(panel))
        except (RuntimeError, TypeError):
            return False

    def update_single(self, panel):
        """Manually update a single panel with current data.

        Args:
            panel: The info panel to update.

        """
        publication = self._latest_publication
        if publication is not None:
            loaded, preprocessed = self._rows_from_publication(publication)
        else:
            loaded, preprocessed = [], []

        self._safe_update_panel(panel, loaded, preprocessed)

    def _rows_from_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> tuple[list[Any], list[Any]]:
        """Return the exact detached rows committed with one view revision."""
        if not publication.usable:
            return [], []
        rows = publication.data_summary_rows
        if rows is None:
            return [], []
        return list(rows), []
