"""Tool executor for the Interactive Debug Mode.

Maps human-readable tool name strings to their concrete ``Real*Tool``
implementations and dispatches execution against a :class:`Study` instance.
"""

from typing import Any, ClassVar

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.tools.base import BaseTool
from XBrainLab.llm.tools.real.dataset_real import (
    RealAttachLabelsTool,
    RealClearDatasetTool,
    RealGenerateDatasetTool,
    RealGetDatasetInfoTool,
    RealListFilesTool,
    RealLoadDataTool,
)
from XBrainLab.llm.tools.real.preprocess_real import (
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
from XBrainLab.llm.tools.real.training_real import (
    RealConfigureTrainingTool,
    RealSetModelTool,
    RealStartTrainingTool,
)
from XBrainLab.llm.tools.real.ui_control_real import RealSwitchPanelTool


class ToolExecutor:
    """Executes tools requested by the Interactive Debug Mode.

    Maintains a class-level registry (``TOOL_MAP``) that maps short string
    names to concrete ``Real*Tool`` classes covering dataset, preprocessing,
    training, and UI-control operations.

    Attributes:
        TOOL_MAP: Class-variable mapping tool name strings to their
            corresponding ``BaseTool`` subclass types.
        study: The active :class:`Study` instance against which tools are
            executed.
    """

    TOOL_MAP: ClassVar[dict[str, type[BaseTool]]] = {
        # Dataset
        "list_files": RealListFilesTool,
        "load_data": RealLoadDataTool,
        "attach_labels": RealAttachLabelsTool,
        "clear_dataset": RealClearDatasetTool,
        "get_dataset_info": RealGetDatasetInfoTool,
        "generate_dataset": RealGenerateDatasetTool,
        # Preprocess
        "apply_standard_preprocess": RealStandardPreprocessTool,
        "apply_bandpass_filter": RealBandPassFilterTool,
        "apply_notch_filter": RealNotchFilterTool,
        "resample_data": RealResampleTool,
        "normalize_data": RealNormalizeTool,
        "set_reference": RealRereferenceTool,
        "select_channels": RealChannelSelectionTool,
        "set_montage": RealSetMontageTool,
        "epoch_data": RealEpochDataTool,
        # Training
        "configure_training": RealConfigureTrainingTool,
        "set_model": RealSetModelTool,
        "start_training": RealStartTrainingTool,
        # UI
        "switch_panel": RealSwitchPanelTool,
    }

    def __init__(self, study: Any) -> None:
        """Initialise the executor with a study context.

        Args:
            study: The backend :class:`Study` instance that each tool
                receives as its first positional argument.
        """
        self.study = study

    def execute(self, tool_name: str, params: dict) -> str:
        """Execute a tool by name with the provided parameters.

        Looks up ``tool_name`` in ``TOOL_MAP``, instantiates the tool, and
        calls its ``execute`` method with ``self.study`` and ``**params``.

        Args:
            tool_name: Key into ``TOOL_MAP`` identifying the tool to run.
            params: Keyword arguments forwarded to the tool's ``execute``
                method.

        Returns:
            The string result produced by the tool, or an error message
            prefixed with ``"Error:"`` if the tool is not found or raises
            an exception.
        """
        tool_class = self.TOOL_MAP.get(tool_name)
        if not tool_class:
            msg = f"Error: Unknown tool '{tool_name}'"
            logger.error(msg)
            return msg

        try:
            logger.info("Executing debug tool: %s with params: %s", tool_name, params)
            tool = tool_class()
            # execute method signature: (study, **kwargs)
            result = tool.execute(self.study, **params)
        except Exception as e:
            msg = f"Error executing {tool_name}: {e}"
            logger.error(msg)
            return f"Error: {msg}"
        else:
            return result
