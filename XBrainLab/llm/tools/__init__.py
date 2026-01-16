
from typing import List

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
from .real.training_real import (
    RealConfigureTrainingTool,
    RealSetModelTool,
    RealStartTrainingTool,
)

# ... (Previous imports)

def get_tool_by_name(name: str) -> BaseTool:
    """
    Returns the tool instance with the given name.
    """
    for tool in AVAILABLE_TOOLS:
        if tool.name == name:
            return tool
    return None

def get_all_tools(mode: str = 'mock') -> List[BaseTool]:
    """
    Factory function to get all tools based on the mode.
    """
    if mode == 'mock':
        return [
            # Dataset
            MockListFilesTool(), MockLoadDataTool(),
            MockAttachLabelsTool(), MockClearDatasetTool(), MockGetDatasetInfoTool(),
            MockGenerateDatasetTool(),

            # Preprocess
            MockStandardPreprocessTool(), MockBandPassFilterTool(), MockNotchFilterTool(),
            MockResampleTool(), MockNormalizeTool(), MockRereferenceTool(),
            MockChannelSelectionTool(), MockSetMontageTool(), MockEpochDataTool(),

            # Training
            MockSetModelTool(), MockConfigureTrainingTool(), MockStartTrainingTool(),

            # UI Control
            MockSwitchPanelTool()
        ]
    elif mode == 'real':
        return [
            # Dataset (Reusing Mock for now if Real not ready, or Todo)
            # For now we only implemented Real Training Tools as requested
            MockListFilesTool(), MockLoadDataTool(),
            MockAttachLabelsTool(), MockClearDatasetTool(), MockGetDatasetInfoTool(),
            MockGenerateDatasetTool(),

            # Preprocess
            MockStandardPreprocessTool(), MockBandPassFilterTool(), MockNotchFilterTool(),
            MockResampleTool(), MockNormalizeTool(), MockRereferenceTool(),
            MockChannelSelectionTool(), MockSetMontageTool(), MockEpochDataTool(),

            # Training - REAL
            RealSetModelTool(), RealConfigureTrainingTool(), RealStartTrainingTool(),

            # UI Control
            MockSwitchPanelTool()
        ]
    else:
        raise ValueError(f"Unknown tool mode: {mode}")

# Default to mock for now, or read from env
# In the future, this can be dynamic.
AVAILABLE_TOOLS = get_all_tools(mode='mock')
