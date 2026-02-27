"""LLM tools package for the XBrainLab agent framework.

Provides mock and real tool implementations for dataset management,
preprocessing, training, and UI control. Use ``get_all_tools`` to
obtain the appropriate tool set based on the execution mode.

Real-tool imports are deferred to ``get_all_tools(mode="real")`` to
avoid pulling in heavy backend dependencies at package import time.
"""

from .base import BaseTool

# Mock tools are lightweight — import eagerly for type checking
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


def _build_real_tools() -> list[BaseTool]:
    """Lazily import and instantiate real tool classes."""
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

    return [
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
        # Training
        RealSetModelTool(),
        RealConfigureTrainingTool(),
        RealStartTrainingTool(),
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
    if mode == "real":
        return _build_real_tools()
    raise ValueError(f"Unknown tool mode: {mode}")


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
