import os
from typing import Any

from XBrainLab.backend.exceptions import FileCorruptedError, UnsupportedFormatError
from XBrainLab.backend.load_data.raw_data_loader import load_raw_data
from XBrainLab.backend.utils.logger import logger

from .base import BaseTool


class LoadDataTool(BaseTool):
    """Tool for loading EEG data files."""

    @property
    def name(self) -> str:
        return "load_data"

    @property
    def description(self) -> str:
        return "Load an EEG data file (e.g., .gdf, .set) into the study."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "The absolute path to the data file.",
                }
            },
            "required": ["filepath"],
        }

    def execute(self, study: Any, filepath: str) -> str:
        if not os.path.exists(filepath):
            return f"Error: File not found at {filepath}"

        try:
            # Use the unified loader factory from backend
            try:
                raw = load_raw_data(filepath)
            except UnsupportedFormatError:
                return f"Error: Unsupported file format for {filepath}"
            except FileCorruptedError as e:
                return f"Error: File is corrupted or cannot be loaded: {e}"
            except Exception as e:
                return f"Error: Failed to load {filepath}: {e}"

            if raw:
                # Append to current study data
                current_data = study.loaded_data_list
                current_data.append(raw)
                try:
                    study.set_loaded_data_list(current_data)
                except ValueError as e:
                    return (
                        f"Error: {e}. Please use the 'clear_dataset' tool first to "
                        f"reset the study."
                    )

                return (
                    f"Successfully loaded {filepath}. Total files: {len(current_data)}"
                )
            else:
                return f"Error: Failed to load {filepath} (Unknown error)"

        except Exception as e:
            logger.error(f"LoadDataTool error: {e}", exc_info=True)
            return f"Error loading data: {e!s}"
