"""Abstract base tool definitions for UI control operations.

Defines the interface for tools that switch the main application
window between different panels and sub-views.
"""

from typing import Any

from ..base import BaseTool
from ..result_contract import ToolExecutionResult


class BaseSwitchPanelTool(BaseTool):
    """Switch the main window view to a specific panel.

    Panels include dataset, preprocess, training, visualization, and
    evaluation. An optional *view_mode* selects a supported visualization.
    """

    @property
    def name(self) -> str:
        return "switch_panel"

    @property
    def description(self) -> str:
        return (
            "Switch the main window view to a specific panel (e.g., to show results or "
            "training status)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "panel_name": {
                    "type": "string",
                    "enum": [
                        "dataset",
                        "preprocess",
                        "training",
                        "visualization",
                        "evaluation",
                    ],
                    "description": "The name of the panel to switch to.",
                },
                "view_mode": {
                    "type": "string",
                    "description": (
                        "Optional sub-view to display. "
                        "For 'visualization': ['saliency_map', 'spectrogram', "
                        "'topographic_map', '3d_plot']."
                    ),
                },
            },
            "required": ["panel_name"],
        }

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError
