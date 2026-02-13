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
    """
    Executes tools requested by the Interactive Debug Mode.
    Maps string tool names to Real*Tool implementations.
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

    def __init__(self, study: Any):
        self.study = study

    def execute(self, tool_name: str, params: dict) -> str:
        """
        Execute a tool by name with provided parameters.
        Returns the result string.
        """
        tool_class = self.TOOL_MAP.get(tool_name)
        if not tool_class:
            msg = f"Error: Unknown tool '{tool_name}'"
            logger.error(msg)
            return msg

        try:
            logger.info(f"Executing debug tool: {tool_name} with params: {params}")
            tool = tool_class()
            # execute method signature: (study, **kwargs)
            result = tool.execute(self.study, **params)
        except Exception as e:
            msg = f"Error executing {tool_name}: {e}"
            logger.error(msg)
            return f"Error: {msg}"
        else:
            return result
