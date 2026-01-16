from typing import Any

from ..definitions.ui_control_def import BaseSwitchPanelTool


class RealSwitchPanelTool(BaseSwitchPanelTool):
    def execute(self, study: Any, panel_name: str, view_mode: str | None = None) -> str:
        # Since tools cannot directly control UI here (running in worker thread),
        # we return a special formatted string that the Controller parses to trigger
        # UI signals.
        # This is the architectural contract described in agent_architecture.md

        msg = f"Request: Switch UI to '{panel_name}'"
        if view_mode:
            msg += f" (View: {view_mode})"
        return msg
