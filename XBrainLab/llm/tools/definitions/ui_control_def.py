"""Abstract base tool definitions for UI control operations.

Defines the interface for tools that switch the main application
window between different panels and sub-views.
"""

from typing import Any

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.llm.action_contracts import (
    AGENT_ACTION_CONTRACTS,
    AgentExecutionKind,
)

from ..base import BaseTool
from ..result_contract import ToolExecutionResult, ToolResult, UiRequest, UiRequestKind


class WorkflowHandoffTool(BaseTool):
    """Zero-parameter request for one existing product-owned GUI decision."""

    def __init__(self, tool_name: str, description: str) -> None:
        contract = AGENT_ACTION_CONTRACTS.contract_for(tool_name)
        if (
            contract is None
            or contract.execution_kind is not AgentExecutionKind.UI_REQUEST
            or not isinstance(contract.action, CommandName)
        ):
            raise ValueError(
                f"Workflow handoff tool is not registered as a UI request: {tool_name}"
            )
        self._name = tool_name
        self._description = description
        self._command = contract.action
        self._decision_fields = contract.ui_decision_fields

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, study: Any, **kwargs: Any) -> UiRequest:
        del study, kwargs
        return UiRequest(
            kind=UiRequestKind.WORKFLOW_HANDOFF,
            params={
                "tool_name": self.name,
                "command": self._command.value,
                "decision_fields": self._decision_fields,
            },
        )


class ApplicationCommandTool(BaseTool):
    """Zero-parameter adapter for one existing ApplicationService command."""

    def __init__(self, tool_name: str, description: str) -> None:
        contract = AGENT_ACTION_CONTRACTS.contract_for(tool_name)
        if (
            contract is None
            or contract.execution_kind is not AgentExecutionKind.APPLICATION_COMMAND
            or not isinstance(contract.action, CommandName)
        ):
            raise ValueError(f"Mapped application tool is not registered: {tool_name}")
        self._name = tool_name
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, study: Any, **kwargs: Any) -> ToolExecutionResult:
        del study, kwargs
        return ToolResult(
            False,
            f"{self.name} must execute through ApplicationService.",
            error_type="contract",
            recoverable=False,
        )


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
                    "enum": [
                        "saliency_map",
                        "spectrogram",
                        "topographic_map",
                        "3d_plot",
                    ],
                    "description": (
                        "Optional sub-view to display. "
                        "For 'visualization': ['saliency_map', 'spectrogram', "
                        "'topographic_map', '3d_plot']."
                    ),
                },
            },
            "required": ["panel_name"],
            "additionalProperties": False,
        }

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError
