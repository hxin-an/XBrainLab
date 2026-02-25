"""Mock implementation of UI control tools.

Returns simulated panel-switch messages without interacting with
the actual GUI, enabling offline agent testing.
"""

from typing import Any

from ..definitions.ui_control_def import BaseSwitchPanelTool


class MockSwitchPanelTool(BaseSwitchPanelTool):
    """Mock implementation of :class:`BaseSwitchPanelTool`."""

    def execute(
        self,
        study: Any,
        panel_name: str | None = None,
        view_mode: str | None = None,
        **kwargs,
    ) -> str:
        """Return a simulated panel-switch result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            panel_name: Target panel name.
            view_mode: Optional sub-view within the panel.
            **kwargs: Additional keyword arguments.

        Returns:
            A message confirming the simulated panel switch.
        """
        if panel_name is None:
            return "Error: panel_name is required"
        msg = f"Switched UI view to {panel_name} panel"
        if view_mode:
            msg += f" showing {view_mode}"
        return msg + "."
