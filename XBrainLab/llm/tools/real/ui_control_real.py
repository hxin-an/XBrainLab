"""Real implementation of typed UI control requests."""

from typing import Any

from ..definitions.ui_control_def import BaseSwitchPanelTool
from ..result_contract import ToolResult, UiRequest, UiRequestKind


class RealSwitchPanelTool(BaseSwitchPanelTool):
    """Real implementation of :class:`BaseSwitchPanelTool`.

    Tools execute away from the GUI thread, so this returns a typed request
    that the controller validates before publishing to the UI host.
    """

    def execute(
        self,
        study: Any,
        panel_name: str | None = None,
        view_mode: str | None = None,
        **kwargs,
    ) -> ToolResult | UiRequest:
        """Request a UI panel switch.

        Args:
            study: The global ``Study`` instance (unused directly).
            panel_name: Target panel name.
            view_mode: Optional sub-view within the panel.
            **kwargs: Additional keyword arguments.

        Returns:
            A typed request for the controller to validate and publish.

        """
        if panel_name is None:
            return ToolResult(
                ok=False,
                message="A panel name is required.",
                error_type="input",
            )
        return UiRequest(
            kind=UiRequestKind.SWITCH_PANEL,
            params={"panel": panel_name, "view_mode": view_mode},
        )
