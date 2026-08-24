"""VRAM conflict checker for local LLM vs 3D visualization co-existence.

Extracted from :class:`AgentManager` to reduce responsibility count
and enable independent testing.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from XBrainLab.llm.agent.runtime_state import AssistantRuntimeSnapshot
from XBrainLab.ui.components.modal_presentation import AlertSeverity, show_alert

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)

# Panel / tab indices must stay in sync with agent_manager constants
VIZ_TAB_3D_PLOT = 3
PANEL_VISUALIZATION = 4


class VRAMConflictChecker:
    """Detect and warn about simultaneous local-LLM + 3D-viz VRAM usage.

    Attributes:
        main_window: The application main window (used to query viz state).
        runtime_snapshot_ref: Callable returning the latest immutable UI-side
            assistant runtime snapshot.

    """

    def __init__(
        self,
        main_window: Any,
        runtime_snapshot_ref: Callable[[], AssistantRuntimeSnapshot],
    ) -> None:
        self.main_window = main_window
        self._get_runtime_snapshot = runtime_snapshot_ref

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_viz_tab_changed(self, index: int) -> None:
        """React to a visualization tab switch.

        Args:
            index: Newly selected tab index.

        """
        if index == VIZ_TAB_3D_PLOT:
            self.check(switching_to_3d=True)

    def check(
        self,
        *,
        switching_to_local: bool = False,
        switching_to_3d: bool = False,
    ) -> None:
        """Warn the user if local LLM and 3D plot compete for VRAM.

        Args:
            switching_to_local: The user is switching *to* local mode.
            switching_to_3d: The user is switching *to* the 3D tab.

        """
        is_local = self._is_local_mode(switching_to_local)
        if not is_local:
            return

        is_3d_active = self._is_3d_active(switching_to_3d)
        if is_local and is_3d_active:
            show_alert(
                self.main_window,
                severity=AlertSeverity.WARNING,
                title="VRAM Warning",
                message=(
                    "This requires significant VRAM (Video Memory). "
                    "If you experience crashes or lag, please close the 3D view "
                    "before using the assistant."
                ),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_local_mode(self, switching_to_local: bool) -> bool:
        if switching_to_local:
            return True
        try:
            snapshot = self._get_runtime_snapshot()
        except Exception:
            logger.debug(
                "Assistant runtime state unavailable, skipping local mode check",
                exc_info=True,
            )
            return False
        return snapshot.initialized and snapshot.backend_mode == "local"

    def _is_3d_active(self, switching_to_3d: bool) -> bool:
        viz_panel = getattr(self.main_window, "visualization_panel", None)
        stack = getattr(self.main_window, "stack", None)
        if viz_panel is None or stack is None:
            return switching_to_3d
        tabs = getattr(viz_panel, "tabs", None)
        current_tab = getattr(tabs, "currentIndex", None)
        is_hidden = getattr(viz_panel, "isHidden", None)
        current_panel = getattr(stack, "currentIndex", None)
        if (
            not callable(current_tab)
            or not callable(is_hidden)
            or not callable(current_panel)
        ):
            return switching_to_3d
        return switching_to_3d or (
            current_tab() == VIZ_TAB_3D_PLOT
            and not is_hidden()
            and current_panel() == PANEL_VISUALIZATION
        )
