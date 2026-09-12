"""Approved Assistant tools, lazily built from the single product registry.

Package import stays lightweight; tool definitions are imported on first use.
"""

from __future__ import annotations

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS

from .base import BaseTool
from .definitions.ui_control_def import (
    ApplicationCommandTool,
    BaseSwitchPanelTool,
    WorkflowHandoffTool,
)

_TARGET_GUI_HANDOFF_DESCRIPTIONS = {
    "import_eeg_data": "Open Import EEG Data for the user to review and apply.",
    "select_channels": "Open Channel Selection for the user to choose EEG channels.",
    "set_montage": "Open Montage Settings for the user to resolve channel positions.",
    "create_epochs": "Open EEG Epoch Settings for the user to create epochs.",
    "configure_dataset_split": "Open Dataset Splitting for the user to configure it.",
    "select_model": "Open Model Selection for the user to choose a model.",
    "configure_training": "Open Training Settings for the user to configure training.",
    "compute_saliency": (
        "Compute saliency for the currently selected completed run after confirmation."
    ),
}

_CONFIRMED_GUI_HANDOFF_TOOLS = frozenset({"compute_saliency"})

_TARGET_LIFECYCLE_DESCRIPTIONS = {
    "reset_preprocessing": (
        "Reset preprocessing and downstream derived state after confirmation."
    ),
    "clear_training_history": (
        "Clear training plans and run history after confirmation."
    ),
}


class _ConfirmedWorkflowHandoffTool(WorkflowHandoffTool):
    """Reuse the standard GUI handoff while requiring the existing card."""

    @property
    def requires_confirmation(self) -> bool:
        return True


def _target_gui_handoff_tools() -> list[BaseTool]:
    """Build the approved parameter-free product GUI handoff surface."""
    return [
        (
            _ConfirmedWorkflowHandoffTool(tool_name, description)
            if tool_name in _CONFIRMED_GUI_HANDOFF_TOOLS
            else WorkflowHandoffTool(tool_name, description)
        )
        for tool_name, description in _TARGET_GUI_HANDOFF_DESCRIPTIONS.items()
    ]


def _target_lifecycle_tools() -> list[BaseTool]:
    return [
        ApplicationCommandTool(tool_name, description)
        for tool_name, description in _TARGET_LIFECYCLE_DESCRIPTIONS.items()
    ]


def get_all_tools() -> list[BaseTool]:
    """Lazily instantiate and validate the approved product tool definitions."""
    from .definitions.preprocess_def import (
        BaseBandPassFilterTool,
        BaseNormalizeTool,
        BaseNotchFilterTool,
        BaseRereferenceTool,
        BaseResampleTool,
    )
    from .definitions.training_def import (
        BaseStartTrainingTool,
        BaseStopTrainingTool,
    )

    tools = [
        *_target_gui_handoff_tools(),
        BaseBandPassFilterTool(),
        BaseNotchFilterTool(),
        BaseResampleTool(),
        BaseRereferenceTool(),
        BaseNormalizeTool(),
        BaseStartTrainingTool(),
        BaseStopTrainingTool(),
        *_target_lifecycle_tools(),
        BaseSwitchPanelTool(),
    ]
    AGENT_ACTION_CONTRACTS.validate_registered_tool_names([tool.name for tool in tools])
    return tools


# Lazy module-level attribute — real tools are only imported on first access.
_AVAILABLE_TOOLS: list[BaseTool] | None = None


def __getattr__(name: str):
    """Module-level __getattr__ for lazy AVAILABLE_TOOLS."""
    if name == "AVAILABLE_TOOLS":
        global _AVAILABLE_TOOLS
        if _AVAILABLE_TOOLS is None:
            _AVAILABLE_TOOLS = get_all_tools()
        return _AVAILABLE_TOOLS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
