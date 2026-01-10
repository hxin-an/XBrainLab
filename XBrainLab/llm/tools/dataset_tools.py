
from typing import Any, Dict
from .base import BaseTool
from XBrainLab.backend.utils.logger import logger

class ClearDatasetTool(BaseTool):
    """Tool for clearing the dataset."""

    @property
    def name(self) -> str:
        return "clear_dataset"

    @property
    def description(self) -> str:
        return "Clear all loaded data and reset the study state. Use this if you need to start over or if loading data fails due to locked state."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    def execute(self, study: Any) -> str:
        try:
            study.clean_raw_data(force_update=True)
            return "Successfully cleared the dataset."
        except Exception as e:
            logger.error(f"ClearDatasetTool error: {e}", exc_info=True)
            return f"Error clearing dataset: {str(e)}"
