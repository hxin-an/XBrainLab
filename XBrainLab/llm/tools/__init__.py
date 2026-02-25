"""LLM tools package for the XBrainLab agent framework.

Provides mock and real tool implementations for dataset management,
preprocessing, training, and UI control. Use ``get_all_tools`` to
obtain the appropriate tool set based on the execution mode.
"""

from .base import BaseTool

# Import Mock Tools
from .mock.dataset_mock import (
    MockAttachLabelsTool,
    MockClearDatasetTool,
    MockGenerateDatasetTool,
    MockGetDatasetInfoTool,
    MockListFilesTool,
    MockLoadDataTool,
)
from .mock.preprocess_mock import (
    MockBandPassFilterTool,
    MockChannelSelectionTool,
    MockEpochDataTool,
    MockNormalizeTool,
    MockNotchFilterTool,
    MockRereferenceTool,
    MockResampleTool,
    MockSetMontageTool,
    MockStandardPreprocessTool,
)
from .mock.training_mock import (
    MockConfigureTrainingTool,
    MockSetModelTool,
    MockStartTrainingTool,
)
from .mock.ui_control_mock import MockSwitchPanelTool
from .real.dataset_real import (
    RealAttachLabelsTool,
    RealClearDatasetTool,
    RealGenerateDatasetTool,
    RealGetDatasetInfoTool,
    RealListFilesTool,
    RealLoadDataTool,
)
from .real.preprocess_real import (
    RealBandPassFilterTool,
    RealChannelSelectionTool,
    RealEpochDataTool,
    RealNormalizeTool,
    RealNotchFilterTool,
    RealRereferenceTool,
    RealResampleTool,
    RealSetMontageTool,
    RealStandardPreprocessTool,
)
from .real.training_real import (
    RealConfigureTrainingTool,
    RealSetModelTool,
    RealStartTrainingTool,
)
from .real.ui_control_real import RealSwitchPanelTool

# ... (Previous imports)


def get_tool_by_name(name: str) -> BaseTool | None:
    """Look up a registered tool by its canonical name.

    Args:
        name: The canonical name of the tool (e.g., ``'load_data'``).

    Returns:
        The matching ``BaseTool`` instance, or ``None`` if no tool
        with the given name exists in ``AVAILABLE_TOOLS``.
    """
    for tool in AVAILABLE_TOOLS:
        if tool.name == name:
            return tool
    return None


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
        return [
            # Dataset
            MockListFilesTool(),
            MockLoadDataTool(),
            MockAttachLabelsTool(),
            MockClearDatasetTool(),
            MockGetDatasetInfoTool(),
            MockGenerateDatasetTool(),
            # Preprocess
            MockStandardPreprocessTool(),
            MockBandPassFilterTool(),
            MockNotchFilterTool(),
            MockResampleTool(),
            MockNormalizeTool(),
            MockRereferenceTool(),
            MockChannelSelectionTool(),
            MockSetMontageTool(),
            MockEpochDataTool(),
            # Training
            MockSetModelTool(),
            MockConfigureTrainingTool(),
            MockStartTrainingTool(),
            # UI Control
            MockSwitchPanelTool(),
        ]
    elif mode == "real":
        return [
            # Dataset (Reusing Mock for now if Real not ready, or Todo)
            # For now we only implemented Real Training Tools as requested
            # Dataset
            RealListFilesTool(),
            RealLoadDataTool(),
            RealAttachLabelsTool(),
            RealClearDatasetTool(),
            RealGetDatasetInfoTool(),
            RealGenerateDatasetTool(),
            # Preprocess
            RealStandardPreprocessTool(),
            RealBandPassFilterTool(),
            RealNotchFilterTool(),
            RealResampleTool(),
            RealNormalizeTool(),
            RealRereferenceTool(),
            RealChannelSelectionTool(),
            RealSetMontageTool(),
            RealEpochDataTool(),
            # Training - REAL
            RealSetModelTool(),
            RealConfigureTrainingTool(),
            RealStartTrainingTool(),
            # UI Control
            RealSwitchPanelTool(),
        ]
    else:
        raise ValueError(f"Unknown tool mode: {mode}")


# Default to mock for now, or read from env
# In the future, this can be dynamic.
AVAILABLE_TOOLS = get_all_tools(mode="real")
