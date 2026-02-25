"""Abstract base tool definitions for UI control operations.

Defines the interface for tools that switch the main application
window between different panels and sub-views.
"""

from typing import Any

from ..base import BaseTool


class BaseSwitchPanelTool(BaseTool):
    """Switch the main window view to a specific panel.

    Panels include dashboard, dataset, preprocess, training,
    visualization, and evaluation.  An optional *view_mode* selects
    a sub-view within the chosen panel.
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
                        "dashboard",
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
                        "'topographic_map', '3d_plot']. "
                        "For 'training': ['metrics']. "
                        "For 'evaluation': ['metrics' (includes confusion_matrix, "
                        "auc), 'model_summary']. "
                        "For 'preprocess': ['time_domain', 'frequency_domain']."
                    ),
                },
            },
            "required": ["panel_name"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError
