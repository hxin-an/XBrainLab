"""Real implementations of dataset tools.

These tools interact with the ``BackendFacade`` to perform actual
dataset operations (file listing, loading, label attachment, etc.).
"""

import os
from typing import Any

from XBrainLab.backend.facade import BackendFacade

from ..definitions.dataset_def import (
    BaseAttachLabelsTool,
    BaseClearDatasetTool,
    BaseGenerateDatasetTool,
    BaseGetDatasetInfoTool,
    BaseListFilesTool,
    BaseLoadDataTool,
)


class RealListFilesTool(BaseListFilesTool):
    """Real implementation of :class:`BaseListFilesTool`.

    Lists files in a directory using ``os.listdir`` with optional
    extension-based filtering.
    """

    def execute(
        self,
        study: Any,
        directory: str | None = None,
        pattern: str | None = None,
        **kwargs,
    ) -> str:
        """List files in the specified directory.

        Args:
            study: The global ``Study`` instance (unused directly).
            directory: Absolute path to the target directory.
            pattern: Glob-style pattern for filtering (e.g., ``'*.gdf'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A string representation of the matched file list, or an
            error message on failure.

        """
        if not directory:
            return "Error: directory is required"

        # Resolve to absolute path and guard against directory traversal
        directory = os.path.realpath(directory)
        if not os.path.isabs(directory):
            return f"Error: Access denied — '{directory}' is not an absolute path."

        if not os.path.isdir(directory):
            return f"Error: Directory '{directory}' does not exist."

        try:
            files = []
            for f in os.listdir(directory):
                # Simple pattern logic (extension based)
                if pattern and pattern.startswith("*") and not f.endswith(pattern[1:]):
                    continue
                files.append(f)
            return str(files)
        except Exception as e:
            return f"Error listing files: {e!s}"


class RealLoadDataTool(BaseLoadDataTool):
    """Real implementation of :class:`BaseLoadDataTool`.

    Loads EEG data files via :class:`BackendFacade`, automatically
    expanding directory paths to individual files.
    """

    def execute(self, study: Any, paths: list[str] | None = None, **kwargs) -> str:
        """Load EEG data from the given file or directory paths.

        Directories are auto-expanded to include all contained files.

        Args:
            study: The global ``Study`` instance.
            paths: List of absolute file or directory paths.
            **kwargs: Additional keyword arguments.

        Returns:
            A success message with the count of loaded files, or an
            error message on failure.

        """
        if not paths:
            return "Error: paths list cannot be empty."

        # Auto-expand directories
        expanded_paths = []
        for p in paths:
            if os.path.isdir(p):
                # If directory, list all files
                try:
                    for f in os.listdir(p):
                        full_path = os.path.join(p, f)
                        if os.path.isfile(full_path):
                            expanded_paths.append(full_path)
                except Exception as e:
                    return f"Error scanning directory {p}: {e}"
            else:
                expanded_paths.append(p)

        if not expanded_paths:
            return "Error: No valid files found in provided paths."

        paths = expanded_paths

        # Use Facade to handle standard loading logic
        facade = BackendFacade(study)
        count, errors = facade.load_data(paths)

        if count > 0:
            if errors:
                return f"Successfully loaded {count} files. Errors: {errors}"
            return f"Successfully loaded {count} files."
        return f"Failed to load any data. Errors: {errors}"


class RealAttachLabelsTool(BaseAttachLabelsTool):
    """Real implementation of :class:`BaseAttachLabelsTool`.

    Attaches label files to loaded data via :class:`BackendFacade`.
    """

    def execute(
        self,
        study: Any,
        mapping: dict | None = None,
        label_format: str | None = None,
        **kwargs,
    ) -> str:
        """Attach label files to loaded data files.

        Args:
            study: The global ``Study`` instance.
            mapping: Dictionary mapping data filenames to label file paths.
            label_format: Optional label file format hint.
            **kwargs: Additional keyword arguments.

        Returns:
            A message indicating how many files received labels.

        """
        if mapping is None:
            return "Error: mapping is required"

        facade = BackendFacade(study)
        success_count = facade.attach_labels(mapping)

        if success_count > 0:
            return f"Attached labels to {success_count} files."
        return "No labels attached. Check file name mapping."


class RealClearDatasetTool(BaseClearDatasetTool):
    """Real implementation of :class:`BaseClearDatasetTool`."""

    def execute(self, study: Any, **kwargs) -> str:
        """Clear all loaded data and reset Study state.

        Args:
            study: The global ``Study`` instance.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation message.

        """
        facade = BackendFacade(study)
        facade.clear_data()
        return "Dataset cleared."


class RealGetDatasetInfoTool(BaseGetDatasetInfoTool):
    """Real implementation of :class:`BaseGetDatasetInfoTool`."""

    def execute(self, study: Any, **kwargs) -> str:
        """Retrieve summary information about the loaded dataset.

        Args:
            study: The global ``Study`` instance.
            **kwargs: Additional keyword arguments.

        Returns:
            A newline-separated summary string.

        """
        facade = BackendFacade(study)
        summary = facade.get_data_summary()

        if summary["count"] == 0:
            return "No data loaded."

        info = [f"Loaded {summary['count']} files:"]
        info.extend(summary["files"])

        # Facade returns basic dict. If we need MNE info,
        # get_data_summary currently returns dataset_controller.get_event_info()
        # which is {"total", "unique_count", "unique_labels"}

        if "total" in summary:
            info.append(
                f"Events: {summary['total']} (Unique: {summary['unique_count']})",
            )

        return "\n".join(info)


class RealGenerateDatasetTool(BaseGenerateDatasetTool):
    """Real implementation of :class:`BaseGenerateDatasetTool`.

    Generates train/validation/test splits from epoched EEG data.
    """

    def execute(
        self,
        study: Any,
        test_ratio: float = 0.2,
        val_ratio: float = 0.2,
        split_strategy: str = "trial",
        training_mode: str = "individual",
        **kwargs,
    ) -> str:
        """Generate a training dataset from epoched data.

        Args:
            study: The global ``Study`` instance.
            test_ratio: Fraction of data reserved for testing.
            val_ratio: Fraction of data reserved for validation.
            split_strategy: How to split data (``'trial'``, ``'session'``,
                or ``'subject'``).
            training_mode: Training paradigm (``'individual'`` or
                ``'group'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A success message with dataset count or an error message.

        """
        facade = BackendFacade(study)

        try:
            facade.generate_dataset(
                test_ratio=test_ratio,
                val_ratio=val_ratio,
                split_strategy=split_strategy,
                training_mode=training_mode,
            )
            # Fetch count from study.datasets explicitly if needed
            count = 0
            if study.datasets:
                count = len(study.datasets)

        except Exception as e:
            return f"Dataset generation failed: {e!s}"
        else:
            return (
                f"Dataset successfully generated. Count: {count} "
                f"(Test: {test_ratio}, Val: {val_ratio})."
            )
