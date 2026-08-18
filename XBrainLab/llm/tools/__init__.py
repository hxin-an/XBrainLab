"""LLM tools package for the XBrainLab agent framework.

Provides mock and real tool implementations for dataset management,
preprocessing, training, and UI control. Use ``get_all_tools`` to
obtain the appropriate tool set based on the execution mode.

Real-tool imports are deferred to ``get_all_tools(mode="real")`` to
avoid pulling in heavy backend dependencies at package import time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS

from .base import BaseTool
from .definitions.ui_control_def import ApplicationCommandTool, WorkflowHandoffTool
from .mock.preprocess_mock import (
    MockBandPassFilterTool,
    MockNormalizeTool,
    MockNotchFilterTool,
    MockRereferenceTool,
    MockResampleTool,
)
from .mock.state import MockWorkflowState
from .mock.training_mock import (
    MockStartTrainingTool,
    MockStopTrainingTool,
)
from .mock.ui_control_mock import MockSwitchPanelTool
from .result_contract import (
    ToolResult,
    recover_authoritative_failure_state,
    runtime_tool_failure,
)

logger = logging.getLogger(__name__)


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


if TYPE_CHECKING:
    from .application_surface import ApplicationToolRuntime


@dataclass(frozen=True, slots=True)
class _RealToolExecutionContext:
    """Per-call host/runtime pair understood by canonical real-tool helpers."""

    study: Any
    application_runtime: ApplicationToolRuntime


def bind_real_tool_execution_context(
    study: Any,
    application_runtime: ApplicationToolRuntime | None,
) -> Any:
    """Carry an explicit runtime through a direct real-tool adapter call."""
    if application_runtime is None:
        return study
    return _RealToolExecutionContext(study, application_runtime)


def execute_real_application_tool(
    study: Any,
    tool_name: str,
    params: dict[str, Any],
) -> ToolResult:
    """Adapt one canonical application-surface result to the BaseTool contract."""
    from .application_surface import (
        application_tool_runtime,
        execute_application_tool_command,
        get_application_context,
    )

    application_runtime = None
    if isinstance(study, _RealToolExecutionContext):
        application_runtime = study.application_runtime
        study = study.study
    if application_runtime is None:
        application_runtime = application_tool_runtime(study)
    runtime_options: dict[str, Any] = (
        {} if application_runtime is None else {"runtime": application_runtime}
    )
    context = None

    try:
        context = get_application_context(
            study,
            tool_name,
            **runtime_options,
        )
        result = execute_application_tool_command(
            study,
            tool_name,
            params,
            availability=context.availability if context is not None else None,
            state=context.state if context is not None else None,
            **runtime_options,
        )
    except Exception as exc:
        mapped_command = AGENT_ACTION_CONTRACTS.contract_for(tool_name)
        capability_command = (
            mapped_command.capability_command if mapped_command is not None else None
        )
        recovery = recover_authoritative_failure_state(
            application_runtime,
            logger,
            operation=tool_name,
            boundary="real_tool_adapter_state_recovery",
        )
        return runtime_tool_failure(
            f"Failed to execute {tool_name}",
            exc,
            command_name=(
                capability_command.value if capability_command is not None else None
            ),
            capability=None,
            state=recovery.state,
            changed_state=recovery.changed_state,
            diagnostics=recovery.diagnostics,
        )

    if result is None:
        return ToolResult(
            False,
            f"Tool '{tool_name}' is not an ApplicationService command.",
            error_type="contract",
            recoverable=False,
        )
    return ToolResult(
        result.ok,
        result.message,
        payload=(
            dict(result.raw_result)
            if isinstance(result.raw_result, dict)
            and {
                "status",
                "command_name",
                "state",
                "changed_state",
            }.issubset(result.raw_result)
            else None
        ),
        error_type=result.error_type or ("none" if result.ok else "runtime"),
        recoverable=result.recoverable,
        command_name=result.command_name,
        error_code=result.error_code,
        recovery_action=result.recovery_action,
        state=result.state,
        capability=result.capability,
        diagnostics=dict(result.diagnostics),
        changed_state=dict(result.changed_state),
    )


def _build_real_tools() -> list[BaseTool]:
    """Lazily import and instantiate real tool classes."""
    from .real.preprocess_real import (
        RealBandPassFilterTool,
        RealNormalizeTool,
        RealNotchFilterTool,
        RealRereferenceTool,
        RealResampleTool,
    )
    from .real.training_real import (
        RealStartTrainingTool,
        RealStopTrainingTool,
    )
    from .real.ui_control_real import RealSwitchPanelTool

    return [
        *_target_gui_handoff_tools(),
        RealBandPassFilterTool(),
        RealNotchFilterTool(),
        RealResampleTool(),
        RealRereferenceTool(),
        RealNormalizeTool(),
        RealStartTrainingTool(),
        RealStopTrainingTool(),
        *_target_lifecycle_tools(),
        RealSwitchPanelTool(),
    ]


def get_all_tools(mode: str = "mock") -> list[BaseTool]:
    """Create and return all tool instances for the given execution mode.

    Args:
        mode: Execution mode — ``'mock'`` for simulated tools or
            ``'real'`` for backend-integrated tools.

    Returns:
        A list of ``BaseTool`` instances appropriate for the
        requested mode.

    Raises:
        ValueError: If *mode* is not ``'mock'`` or ``'real'``.

    """
    if mode == "mock":
        workflow_state = MockWorkflowState()
        tools = [
            *_target_gui_handoff_tools(),
            MockBandPassFilterTool(workflow_state),
            MockNotchFilterTool(workflow_state),
            MockResampleTool(workflow_state),
            MockRereferenceTool(workflow_state),
            MockNormalizeTool(workflow_state),
            MockStartTrainingTool(workflow_state),
            MockStopTrainingTool(workflow_state),
            *_target_lifecycle_tools(),
            MockSwitchPanelTool(),
        ]
    elif mode == "real":
        tools = _build_real_tools()
    else:
        raise ValueError(f"Unknown tool mode: {mode}")

    AGENT_ACTION_CONTRACTS.validate_registered_tool_names([tool.name for tool in tools])
    return tools


# Lazy module-level attribute — real tools are only imported on first access.
_AVAILABLE_TOOLS: list[BaseTool] | None = None


def __getattr__(name: str):
    """Module-level __getattr__ for lazy AVAILABLE_TOOLS."""
    if name == "AVAILABLE_TOOLS":
        global _AVAILABLE_TOOLS
        if _AVAILABLE_TOOLS is None:
            _AVAILABLE_TOOLS = get_all_tools(mode="real")
        return _AVAILABLE_TOOLS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
