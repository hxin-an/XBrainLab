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
from .mock.analysis_mock import (
    MockEvaluateTool,
    MockSaliencyTool,
    MockVisualizeTool,
)

# Mock tools are lightweight — import eagerly for type checking
from .mock.dataset_mock import (
    MockApplyInterpretationTool,
    MockAttachLabelsTool,
    MockConfigureDatasetSplitTool,
    MockGetDatasetInfoTool,
    MockListFilesTool,
    MockLoadDataTool,
    MockPreviewInterpretationTool,
    MockQueryStateTool,
    MockReloadInterpretationRecipeTool,
    MockSaveInterpretationRecipeTool,
    MockScanSourceTool,
    MockValidateInterpretationTool,
)
from .mock.preprocess_mock import (
    MockBandPassFilterTool,
    MockChannelSelectionTool,
    MockEpochDataTool,
    MockNormalizeTool,
    MockNotchFilterTool,
    MockRereferenceTool,
    MockResampleTool,
    MockResetPreprocessTool,
    MockSetMontageTool,
    MockStandardPreprocessTool,
)
from .mock.state import MockWorkflowState
from .mock.training_mock import (
    MockConfigureTrainingTool,
    MockSetModelTool,
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
    from .real.analysis_real import (
        RealEvaluateTool,
        RealSaliencyTool,
        RealVisualizeTool,
    )
    from .real.dataset_real import (
        RealApplyInterpretationTool,
        RealAttachLabelsTool,
        RealConfigureDatasetSplitTool,
        RealGetDatasetInfoTool,
        RealListFilesTool,
        RealLoadDataTool,
        RealPreviewInterpretationTool,
        RealQueryStateTool,
        RealReloadInterpretationRecipeTool,
        RealSaveInterpretationRecipeTool,
        RealScanSourceTool,
        RealValidateInterpretationTool,
    )
    from .real.preprocess_real import (
        RealBandPassFilterTool,
        RealChannelSelectionTool,
        RealEpochDataTool,
        RealNormalizeTool,
        RealNotchFilterTool,
        RealRereferenceTool,
        RealResampleTool,
        RealResetPreprocessTool,
        RealSetMontageTool,
        RealStandardPreprocessTool,
    )
    from .real.training_real import (
        RealConfigureTrainingTool,
        RealSetModelTool,
        RealStartTrainingTool,
        RealStopTrainingTool,
    )
    from .real.ui_control_real import RealSwitchPanelTool

    return [
        # Dataset
        RealListFilesTool(),
        RealScanSourceTool(),
        RealPreviewInterpretationTool(),
        RealValidateInterpretationTool(),
        RealApplyInterpretationTool(),
        RealSaveInterpretationRecipeTool(),
        RealReloadInterpretationRecipeTool(),
        RealLoadDataTool(),
        RealAttachLabelsTool(),
        RealQueryStateTool(),
        RealGetDatasetInfoTool(),
        RealConfigureDatasetSplitTool(),
        # Analysis
        RealEvaluateTool(),
        RealVisualizeTool(),
        RealSaliencyTool(),
        # Preprocess
        RealStandardPreprocessTool(),
        RealResetPreprocessTool(),
        RealBandPassFilterTool(),
        RealNotchFilterTool(),
        RealResampleTool(),
        RealNormalizeTool(),
        RealRereferenceTool(),
        RealChannelSelectionTool(),
        RealSetMontageTool(),
        RealEpochDataTool(),
        # Training
        RealSetModelTool(),
        RealConfigureTrainingTool(),
        RealStartTrainingTool(),
        RealStopTrainingTool(),
        # UI Control
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
            # Dataset
            MockListFilesTool(),
            MockScanSourceTool(),
            MockPreviewInterpretationTool(),
            MockValidateInterpretationTool(),
            MockApplyInterpretationTool(workflow_state),
            MockSaveInterpretationRecipeTool(),
            MockReloadInterpretationRecipeTool(),
            MockLoadDataTool(workflow_state),
            MockAttachLabelsTool(),
            MockQueryStateTool(workflow_state),
            MockGetDatasetInfoTool(),
            MockConfigureDatasetSplitTool(workflow_state),
            # Analysis
            MockEvaluateTool(),
            MockVisualizeTool(),
            MockSaliencyTool(),
            # Preprocess
            MockStandardPreprocessTool(workflow_state),
            MockResetPreprocessTool(workflow_state),
            MockBandPassFilterTool(workflow_state),
            MockNotchFilterTool(workflow_state),
            MockResampleTool(workflow_state),
            MockNormalizeTool(workflow_state),
            MockRereferenceTool(workflow_state),
            MockChannelSelectionTool(workflow_state),
            MockSetMontageTool(workflow_state),
            MockEpochDataTool(workflow_state),
            # Training
            MockSetModelTool(workflow_state),
            MockConfigureTrainingTool(workflow_state),
            MockStartTrainingTool(workflow_state),
            MockStopTrainingTool(workflow_state),
            # UI Control
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
