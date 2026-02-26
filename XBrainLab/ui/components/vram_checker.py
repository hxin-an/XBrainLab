"""VRAM conflict checker for local LLM vs 3D visualization co-existence.

Extracted from :class:`AgentManager` to reduce responsibility count
and enable independent testing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMessageBox

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
        agent_controller_ref: Callable returning the current
            :class:`LLMController`, or ``None``.

    """

    def __init__(
        self,
        main_window: Any,
        agent_controller_ref: Any,
    ) -> None:
        self.main_window = main_window
        self._get_controller = agent_controller_ref

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
            QMessageBox.warning(
                self.main_window,
                "VRAM Warning",
                "This requires significant VRAM (Video Memory). "
                "If you experience crashes or lag, please close the 3D view "
                "or switch to Gemini mode.",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_local_mode(self, switching_to_local: bool) -> bool:
        if switching_to_local:
            return True
        controller = self._get_controller()
        if controller and controller.worker:
            try:
                if controller.worker.engine:
                    return controller.worker.engine.config.active_mode == "local"
            except Exception:
                logger.debug(
                    "Engine not yet initialized, skipping local mode check",
                    exc_info=True,
                )
        return False

    def _is_3d_active(self, switching_to_3d: bool) -> bool:
        viz_panel = self.main_window.visualization_panel
        return switching_to_3d or (
            viz_panel.tabs.currentIndex() == VIZ_TAB_3D_PLOT
            and not viz_panel.isHidden()
            and self.main_window.stack.currentIndex() == PANEL_VISUALIZATION
        )
