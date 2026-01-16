
from typing import Any, Dict

from ..base import BaseTool


class BaseListFilesTool(BaseTool):
    @property
    def name(self) -> str: return "list_files"
    @property
    def description(self) -> str: return "List all files in a directory to explore structure."
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Absolute path to the directory."},
                "pattern": {"type": "string", "description": "Glob pattern (e.g., '*.gdf')."}
            },
            "required": ["directory"]
        }
    def execute(self, study: Any, **kwargs) -> str: raise NotImplementedError

class BaseLoadDataTool(BaseTool):
    @property
    def name(self) -> str: return "load_data"
    @property
    def description(self) -> str: return "Load raw EEG/GDF data from files or directories into the Study."
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of absolute file paths or directory paths to load."
                }
            },
            "required": ["paths"]
        }
    def execute(self, study: Any, **kwargs) -> str: raise NotImplementedError

class BaseAttachLabelsTool(BaseTool):
    @property
    def name(self) -> str: return "attach_labels"
    @property
    def description(self) -> str: return "Attach label files to loaded data files."
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mapping": {"type": "object", "description": "Dictionary mapping filename to label file path."},
                "label_format": {"type": "string", "description": "Format of label file (optional)."}
            },
            "required": ["mapping"]
        }
    def execute(self, study: Any, **kwargs) -> str: raise NotImplementedError

class BaseClearDatasetTool(BaseTool):
    @property
    def name(self) -> str: return "clear_dataset"
    @property
    def description(self) -> str: return "Clear all loaded data and reset Study state."
    @property
    def parameters(self) -> Dict[str, Any]: return {"type": "object", "properties": {}}
    def execute(self, study: Any, **kwargs) -> str: raise NotImplementedError

class BaseGetDatasetInfoTool(BaseTool):
    @property
    def name(self) -> str: return "get_dataset_info"
    @property
    def description(self) -> str: return "Get summary info of loaded dataset."
    @property
    def parameters(self) -> Dict[str, Any]: return {"type": "object", "properties": {}}
    def execute(self, study: Any, **kwargs) -> str: raise NotImplementedError

class BaseGenerateDatasetTool(BaseTool):
    @property
    def name(self) -> str: return "generate_dataset"
    @property
    def description(self) -> str: return "Generate training dataset from epochs."
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "test_ratio": {"type": "number", "default": 0.2},
                "val_ratio": {"type": "number", "default": 0.2},
                "split_strategy": {"type": "string", "enum": ["trial", "session", "subject"]},
                "training_mode": {"type": "string", "enum": ["individual", "group"]}
            },
            "required": ["split_strategy", "training_mode"]
        }
    def execute(self, study: Any, **kwargs) -> str: raise NotImplementedError
