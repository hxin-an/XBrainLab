"""Real implementation of UI control tools.

Returns specially formatted request strings that the agent controller
parses to trigger UI panel switches via Qt signals.
"""

from typing import Any

from ..definitions.ui_control_def import BaseSwitchPanelTool


class RealSwitchPanelTool(BaseSwitchPanelTool):
    """Real implementation of :class:`BaseSwitchPanelTool`.

    Since tools execute in a worker thread and cannot manipulate the
    GUI directly, this tool returns a formatted request string that
    the ``AgentController`` parses to emit the appropriate UI signal.
    """

    def execute(
        self,
        study: Any,
        panel_name: str | None = None,
        view_mode: str | None = None,
        **kwargs,
    ) -> str:
        """Request a UI panel switch.

        Args:
            study: The global ``Study`` instance (unused directly).
            panel_name: Target panel name.
            view_mode: Optional sub-view within the panel.
            **kwargs: Additional keyword arguments.

        Returns:
            A formatted request string for the controller to parse.

        """
        if panel_name is None:
            return "Error: panel_name is required"
        # Since tools cannot directly control UI here (running in worker thread),
        # we return a special formatted string that the Controller parses to trigger
        # UI signals.
        # This is the architectural contract described in agent_architecture.md

        msg = f"Request: Switch UI to '{panel_name}'"
        if view_mode:
            msg += f" (View: {view_mode})"
        return msg
