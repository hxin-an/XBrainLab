from typing import Any

from ..definitions.ui_control_def import BaseSwitchPanelTool


class MockSwitchPanelTool(BaseSwitchPanelTool):
    def execute(
        self,
        study: Any,
        panel_name: str | None = None,
        view_mode: str | None = None,
        **kwargs,
    ) -> str:
        if panel_name is None:
            return "Error: panel_name is required"
        msg = f"Switched UI view to {panel_name} panel"
        if view_mode:
            msg += f" showing {view_mode}"
        return msg + "."
