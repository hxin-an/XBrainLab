"""Mock implementations of dataset tools.

Return canned success/error strings without interacting with the
backend, enabling offline agent testing and development.
"""

from typing import Any

from ..definitions.dataset_def import (
    BaseApplyInterpretationTool,
    BaseAttachLabelsTool,
    BaseClearDatasetTool,
    BaseGenerateDatasetTool,
    BaseGetDatasetInfoTool,
    BaseListFilesTool,
    BaseLoadDataTool,
    BasePreviewInterpretationTool,
    BaseReloadInterpretationRecipeTool,
    BaseSaveInterpretationRecipeTool,
    BaseScanSourceTool,
    BaseValidateInterpretationTool,
)


class MockListFilesTool(BaseListFilesTool):
    """Mock implementation of :class:`BaseListFilesTool`."""

    def execute(
        self,
        study: Any,
        directory: str | None = None,
        pattern: str = "*",
        **kwargs,
    ) -> str:
        """Return a simulated file listing.

        Args:
            study: The global ``Study`` instance (unused in mock).
            directory: Absolute path to the directory.
            pattern: Glob pattern for filtering files.
            **kwargs: Additional keyword arguments.

        Returns:
            A string representation of matching files.

        """
        if directory is None:
            return "Error: directory is required"
        return f"['A01T.gdf', 'A02T.gdf'] found in {directory} matching {pattern}"


class MockLoadDataTool(BaseLoadDataTool):
    """Mock implementation of :class:`BaseLoadDataTool`."""

    def execute(self, study: Any, paths: list[str] | None = None, **kwargs) -> str:
        """Return a simulated data-load result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            paths: List of file or directory paths to load.
            **kwargs: Additional keyword arguments.

        Returns:
            A success message indicating how many paths were loaded.

        """
        if paths is None:
            return "Error: paths list is required"
        return f"Successfully loaded data from {len(paths)} sources: {paths}"


class MockScanSourceTool(BaseScanSourceTool):
    """Mock implementation of :class:`BaseScanSourceTool`."""

    def execute(
        self,
        study: Any,
        source_path: str | None = None,
        source_hint: str = "auto",
        **kwargs,
    ) -> str:
        if not source_path:
            return "Error: source_path is required"
        return f"Scanned {source_path} as {source_hint}; found 1 EEG file."


class MockPreviewInterpretationTool(BasePreviewInterpretationTool):
    """Mock implementation of :class:`BasePreviewInterpretationTool`."""

    def execute(
        self,
        study: Any,
        scan_id: str | None = None,
        choices: dict[str, Any] | None = None,
        **kwargs,
    ) -> str:
        target = scan_id or "latest scan"
        return f"Interpretation preview ready for {target}."


class MockValidateInterpretationTool(BaseValidateInterpretationTool):
    """Mock implementation of :class:`BaseValidateInterpretationTool`."""

    def execute(
        self,
        study: Any,
        candidate_id: str | None = None,
        **kwargs,
    ) -> str:
        target = candidate_id or "latest candidate"
        return f"Interpretation validation for {target}: safe."


class MockApplyInterpretationTool(BaseApplyInterpretationTool):
    """Mock implementation of :class:`BaseApplyInterpretationTool`."""

    def execute(
        self,
        study: Any,
        candidate_id: str | None = None,
        confirmed: bool = False,
        **kwargs,
    ) -> str:
        target = candidate_id or "latest candidate"
        marker = " with confirmation" if confirmed else ""
        return f"Applied interpretation for {target}{marker}."


class MockSaveInterpretationRecipeTool(BaseSaveInterpretationRecipeTool):
    """Mock implementation of :class:`BaseSaveInterpretationRecipeTool`."""

    def execute(
        self,
        study: Any,
        recipe_path: str | None = None,
        **kwargs,
    ) -> str:
        target = recipe_path or "default recipe path"
        return f"Interpretation recipe saved to {target}."


class MockReloadInterpretationRecipeTool(BaseReloadInterpretationRecipeTool):
    """Mock implementation of :class:`BaseReloadInterpretationRecipeTool`."""

    def execute(
        self,
        study: Any,
        recipe_path: str | None = None,
        **kwargs,
    ) -> str:
        if not recipe_path:
            return "Error: recipe_path is required"
        return f"Interpretation recipe reloaded from {recipe_path}."


class MockAttachLabelsTool(BaseAttachLabelsTool):
    """Mock implementation of :class:`BaseAttachLabelsTool`."""

    def execute(
        self,
        study: Any,
        mapping: dict[str, str] | None = None,
        label_format: str | None = None,
        **kwargs,
    ) -> str:
        """Return a simulated label-attach result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            mapping: Dictionary mapping filenames to label file paths.
            label_format: Optional label file format hint.
            **kwargs: Additional keyword arguments.

        Returns:
            A message summarising how many files received labels.

        """
        if mapping is None:
            return "Error: mapping is required"
        return f"Attached labels to {len(mapping)} files."


class MockClearDatasetTool(BaseClearDatasetTool):
    """Mock implementation of :class:`BaseClearDatasetTool`."""

    def execute(self, study: Any, **kwargs) -> str:
        """Return a simulated dataset-clear confirmation.

        Args:
            study: The global ``Study`` instance (unused in mock).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation message.

        """
        return "Dataset cleared."


class MockGetDatasetInfoTool(BaseGetDatasetInfoTool):
    """Mock implementation of :class:`BaseGetDatasetInfoTool`."""

    def execute(self, study: Any, **kwargs) -> str:
        """Return a simulated dataset summary.

        Args:
            study: The global ``Study`` instance (unused in mock).
            **kwargs: Additional keyword arguments.

        Returns:
            A canned dataset-info string.

        """
        return "Dataset Info: 2 files loaded, 250Hz, 22 channels."


class MockGenerateDatasetTool(BaseGenerateDatasetTool):
    """Mock implementation of :class:`BaseGenerateDatasetTool`."""

    def execute(
        self,
        study: Any,
        test_ratio: float = 0.2,
        val_ratio: float = 0.2,
        split_strategy: str = "trial",
        training_mode: str = "individual",
        **kwargs,
    ) -> str:
        """Return a simulated dataset-generation result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            test_ratio: Fraction of data reserved for testing.
            val_ratio: Fraction of data reserved for validation.
            split_strategy: How to split data (trial/session/subject).
            training_mode: Training paradigm (individual/group).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation message with the split strategy and mode.

        """
        return f"Generated dataset (Split: {split_strategy}, Mode: {training_mode})."
