"""Abstract base tool definitions for dataset operations.

Each class defines the tool's name, description, and JSON-schema
parameters.  Concrete (mock or real) implementations must override
:meth:`execute`.
"""

from typing import Any

from ..base import BaseTool


class BaseListFilesTool(BaseTool):
    """List files in a directory to explore dataset structure.

    Allows the agent to discover available data files before loading.
    """

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return "List all files in a directory to explore structure."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Absolute path to the directory.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '*.gdf').",
                },
            },
            "required": ["directory"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseLoadDataTool(BaseTool):
    """Load raw EEG/GDF data files into the Study.

    Accepts absolute file paths or directory paths. Directories are
    expanded to include all contained files.
    """

    @property
    def name(self) -> str:
        return "load_data"

    @property
    def description(self) -> str:
        return "Load raw EEG/GDF data from files or directories into the Study."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of absolute file paths or directory paths to load."
                    ),
                },
            },
            "required": ["paths"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseAttachLabelsTool(BaseTool):
    """Attach label files to previously loaded data files.

    Maps each data filename to its corresponding label file path.
    """

    @property
    def name(self) -> str:
        return "attach_labels"

    @property
    def description(self) -> str:
        return "Attach label files to loaded data files."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mapping": {
                    "type": "object",
                    "description": "Dictionary mapping filename to label file path.",
                },
                "label_format": {
                    "type": "string",
                    "description": "Format of label file (optional).",
                },
            },
            "required": ["mapping"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseClearDatasetTool(BaseTool):
    """Clear all loaded data and reset the Study state."""

    @property
    def name(self) -> str:
        return "clear_dataset"

    @property
    def description(self) -> str:
        return "Clear all loaded data and reset Study state."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    @property
    def requires_confirmation(self) -> bool:
        """Clearing data is destructive and requires user confirmation."""
        return True

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseGetDatasetInfoTool(BaseTool):
    """Retrieve summary information about the currently loaded dataset."""

    @property
    def name(self) -> str:
        return "get_dataset_info"

    @property
    def description(self) -> str:
        return "Get summary info of loaded dataset."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseGenerateDatasetTool(BaseTool):
    """Generate a training/validation/test dataset from epoched data.

    Supports multiple split strategies (trial, session, subject) and
    training modes (individual, group).
    """

    @property
    def name(self) -> str:
        return "generate_dataset"

    @property
    def description(self) -> str:
        return "Generate training dataset from epochs."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "test_ratio": {"type": "number", "default": 0.2},
                "val_ratio": {"type": "number", "default": 0.2},
                "split_strategy": {
                    "type": "string",
                    "enum": ["trial", "session", "subject"],
                },
                "training_mode": {"type": "string", "enum": ["individual", "group"]},
            },
            "required": ["split_strategy", "training_mode"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError
