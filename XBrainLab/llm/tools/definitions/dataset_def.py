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


class BaseScanSourceTool(BaseTool):
    """Scan a data source before importing it into the active session."""

    @property
    def name(self) -> str:
        return "scan_source"

    @property
    def description(self) -> str:
        return "Scan an EEG file, folder, BIDS root, or import recipe."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source_path": {
                    "type": "string",
                    "description": "Absolute path to the EEG source or recipe.",
                },
                "source_hint": {
                    "type": "string",
                    "enum": [
                        "auto",
                        "file",
                        "folder",
                        "bids",
                        "device_export",
                        "recipe",
                    ],
                    "default": "auto",
                    "description": "Optional source type hint.",
                },
            },
            "required": ["source_path"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BasePreviewInterpretationTool(BaseTool):
    """Preview a candidate interpretation from the latest source scan."""

    @property
    def name(self) -> str:
        return "preview_interpretation"

    @property
    def description(self) -> str:
        return "Preview file, label/event, and metadata choices before import."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scan_id": {
                    "type": "string",
                    "description": "Optional scan id. Defaults to the latest scan.",
                },
                "choices": {
                    "type": "object",
                    "description": (
                        "Optional overrides such as selected_eeg_files, event roles, "
                        "class map, recipe id, or metadata choices like subject, "
                        "session, task, and run."
                    ),
                },
            },
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseValidateInterpretationTool(BaseTool):
    """Validate a candidate interpretation before apply."""

    @property
    def name(self) -> str:
        return "validate_interpretation"

    @property
    def description(self) -> str:
        return "Validate whether an interpretation is safe, blocked, or needs review."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "candidate_id": {
                    "type": "string",
                    "description": (
                        "Optional candidate id. Defaults to the latest candidate."
                    ),
                },
            },
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseApplyInterpretationTool(BaseTool):
    """Apply a validated interpretation to the active backend session."""

    @property
    def name(self) -> str:
        return "apply_interpretation"

    @property
    def description(self) -> str:
        return "Apply a validated data interpretation and load selected EEG files."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "candidate_id": {
                    "type": "string",
                    "description": (
                        "Optional candidate id. Defaults to the latest candidate."
                    ),
                },
                "confirmed": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "True only after the user confirms reviewable semantics."
                    ),
                },
            },
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseSaveInterpretationRecipeTool(BaseTool):
    """Save the applied interpretation as a replayable import recipe."""

    @property
    def name(self) -> str:
        return "save_interpretation_recipe"

    @property
    def description(self) -> str:
        return "Save the current applied interpretation as an import recipe."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "recipe_path": {
                    "type": "string",
                    "description": "Optional absolute path for the recipe JSON file.",
                },
            },
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseReloadInterpretationRecipeTool(BaseTool):
    """Reload an import recipe for preview and validation without auto-apply."""

    @property
    def name(self) -> str:
        return "reload_interpretation_recipe"

    @property
    def description(self) -> str:
        return "Reload an import recipe and preview the replayed interpretation."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "recipe_path": {
                    "type": "string",
                    "description": "Absolute path to a saved import recipe JSON file.",
                },
            },
            "required": ["recipe_path"],
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


class BaseQueryStateTool(BaseTool):
    """Query the typed ApplicationService state snapshot."""

    @property
    def name(self) -> str:
        return "query_state"

    @property
    def description(self) -> str:
        return (
            "Get the current typed workflow state, capabilities, or data summary "
            "through ApplicationService."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "enum": [
                        "state",
                        "data_lists",
                        "data_summary",
                        "preprocess_diagnostics",
                        "smart_filter_suggestions",
                    ],
                    "default": "state",
                }
            },
        }

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
                    "description": (
                        "How to split examples: trial, session, or subject. "
                        "Do not use individual or group here."
                    ),
                },
                "training_mode": {
                    "type": "string",
                    "enum": ["individual", "group"],
                    "description": "Training mode: individual or group.",
                },
            },
            "required": ["split_strategy", "training_mode"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError
