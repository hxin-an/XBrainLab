"""Mock implementations of dataset tools.

Return deterministic results without interacting with the backend,
enabling offline agent testing and development.
"""

from typing import Any

from XBrainLab.backend.training.input_contract import (
    TrainingInputContractError,
    normalize_strict_boolean,
)

from ..definitions.dataset_def import (
    BaseApplyInterpretationTool,
    BaseAttachLabelsTool,
    BaseClearDatasetTool,
    BaseConfigureDatasetSplitTool,
    BaseGetDatasetInfoTool,
    BaseListFilesTool,
    BaseLoadDataTool,
    BasePreviewInterpretationTool,
    BaseQueryStateTool,
    BaseReloadInterpretationRecipeTool,
    BaseSaveInterpretationRecipeTool,
    BaseScanSourceTool,
    BaseValidateInterpretationTool,
)
from ..result_contract import ToolResult
from .state import MockWorkflowState


class MockListFilesTool(BaseListFilesTool):
    """Mock implementation of :class:`BaseListFilesTool`."""

    def execute(
        self,
        study: Any,
        directory: str | None = None,
        pattern: str = "*",
        **kwargs,
    ) -> ToolResult:
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
            return ToolResult(False, "A folder path is required.", error_type="input")
        files = ["A01T.gdf", "A02T.gdf"]
        return ToolResult(
            True,
            f"Found {len(files)} file(s) matching {pattern}.",
            payload=files,
        )


class MockLoadDataTool(BaseLoadDataTool):
    """Mock implementation of :class:`BaseLoadDataTool`."""

    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def execute(
        self,
        study: Any,
        paths: list[str] | None = None,
        **kwargs,
    ) -> ToolResult:
        """Return a simulated data-load result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            paths: List of file or directory paths to load.
            **kwargs: Additional keyword arguments.

        Returns:
            A success message indicating how many paths were loaded.

        """
        if not paths:
            return ToolResult(
                ok=False,
                message="Error: paths list is required",
                error_type="input",
            )
        self._state.mark_data_loaded()
        return ToolResult(
            ok=True,
            message=f"Successfully loaded data from {len(paths)} sources: {paths}",
        )


class MockScanSourceTool(BaseScanSourceTool):
    """Mock implementation of :class:`BaseScanSourceTool`."""

    def execute(
        self,
        study: Any,
        source_path: str | None = None,
        source_hint: str = "auto",
        label_sources: list[str] | None = None,
        **kwargs,
    ) -> ToolResult:
        if not source_path:
            return ToolResult(
                ok=False,
                message="Error: source_path is required",
                error_type="input",
            )
        label_count = len(label_sources or [])
        suffix = f" Attached {label_count} label source(s)." if label_count else ""
        return ToolResult(
            ok=True,
            message=(
                f"Scanned {source_path} as {source_hint}; found 1 EEG file.{suffix}"
            ),
        )


class MockPreviewInterpretationTool(BasePreviewInterpretationTool):
    """Mock implementation of :class:`BasePreviewInterpretationTool`."""

    def execute(
        self,
        study: Any,
        scan_id: str | None = None,
        choices: dict[str, Any] | None = None,
        **kwargs,
    ) -> ToolResult:
        target = scan_id or "latest scan"
        return ToolResult(
            ok=True,
            message=f"Interpretation preview ready for {target}.",
        )


class MockValidateInterpretationTool(BaseValidateInterpretationTool):
    """Mock implementation of :class:`BaseValidateInterpretationTool`."""

    def execute(
        self,
        study: Any,
        candidate_id: str | None = None,
        **kwargs,
    ) -> ToolResult:
        target = candidate_id or "latest candidate"
        return ToolResult(
            ok=True,
            message=f"Interpretation validation for {target}: safe.",
        )


class MockApplyInterpretationTool(BaseApplyInterpretationTool):
    """Mock implementation of :class:`BaseApplyInterpretationTool`."""

    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def execute(
        self,
        study: Any,
        candidate_id: str | None = None,
        confirmed: bool = False,
        **kwargs,
    ) -> ToolResult:
        target = candidate_id or "latest candidate"
        marker = " with confirmation" if confirmed else ""
        self._state.mark_data_loaded()
        return ToolResult(
            ok=True,
            message=f"Applied interpretation for {target}{marker}.",
        )


class MockSaveInterpretationRecipeTool(BaseSaveInterpretationRecipeTool):
    """Mock implementation of :class:`BaseSaveInterpretationRecipeTool`."""

    def execute(
        self,
        study: Any,
        recipe_path: str | None = None,
        **kwargs,
    ) -> ToolResult:
        target = recipe_path or "default recipe path"
        return ToolResult(
            ok=True,
            message=f"Interpretation recipe saved to {target}.",
        )


class MockReloadInterpretationRecipeTool(BaseReloadInterpretationRecipeTool):
    """Mock implementation of :class:`BaseReloadInterpretationRecipeTool`."""

    def execute(
        self,
        study: Any,
        recipe_path: str | None = None,
        **kwargs,
    ) -> ToolResult:
        if not recipe_path:
            return ToolResult(
                ok=False,
                message="Error: recipe_path is required",
                error_type="input",
            )
        return ToolResult(
            ok=True,
            message=f"Interpretation recipe reloaded from {recipe_path}.",
        )


class MockAttachLabelsTool(BaseAttachLabelsTool):
    """Mock implementation of :class:`BaseAttachLabelsTool`."""

    def execute(
        self,
        study: Any,
        mapping: dict[str, str] | None = None,
        label_format: str | None = None,
        **kwargs,
    ) -> ToolResult:
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
            return ToolResult(
                ok=False,
                message="Error: mapping is required",
                error_type="input",
            )
        return ToolResult(
            ok=True,
            message=f"Attached labels to {len(mapping)} files.",
        )


class MockClearDatasetTool(BaseClearDatasetTool):
    """Mock implementation of :class:`BaseClearDatasetTool`."""

    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def execute(self, study: Any, **kwargs) -> ToolResult:
        """Return a simulated dataset-clear confirmation.

        Args:
            study: The global ``Study`` instance (unused in mock).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation message.

        """
        try:
            confirmed = normalize_strict_boolean(
                "confirmed",
                kwargs.get("confirmed", False),
            )
        except TrainingInputContractError as exc:
            return ToolResult(False, str(exc), error_type="input")
        if not confirmed:
            return ToolResult(
                ok=False,
                message="Dataset reset requires confirmation.",
                error_type="confirmation_required",
            )
        self._state.clear_dataset()
        return ToolResult(ok=True, message="Dataset cleared.")


class MockGetDatasetInfoTool(BaseGetDatasetInfoTool):
    """Mock implementation of :class:`BaseGetDatasetInfoTool`."""

    def execute(self, study: Any, **kwargs) -> ToolResult:
        """Return a simulated dataset summary.

        Args:
            study: The global ``Study`` instance (unused in mock).
            **kwargs: Additional keyword arguments.

        Returns:
            A canned dataset-info string.

        """
        return ToolResult(
            True,
            "Dataset Info: 2 files loaded, 250Hz, 22 channels.",
            payload={"count": 2, "sampling_rate": 250, "channels": 22},
        )


class MockQueryStateTool(BaseQueryStateTool):
    """Mock implementation of :class:`BaseQueryStateTool`."""

    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def execute(self, study: Any, **kwargs) -> ToolResult:
        from XBrainLab.backend.application.pipeline_stage import (  # noqa: PLC0415
            PipelineStage,
            pipeline_stage_readiness_message,
        )

        if self._state.split_spec_saved:
            stage = PipelineStage.DATASET_READY
        elif self._state.epochs_ready:
            stage = PipelineStage.EPOCH_READY
        elif self._state.data_loaded:
            stage = PipelineStage.DATA_LOADED
        else:
            stage = PipelineStage.EMPTY
        return ToolResult(
            ok=True,
            message=pipeline_stage_readiness_message(
                stage,
                raw_count=1 if self._state.data_loaded else 0,
            ),
        )


class MockConfigureDatasetSplitTool(BaseConfigureDatasetSplitTool):
    """Mock implementation of :class:`BaseConfigureDatasetSplitTool`."""

    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def execute(
        self,
        study: Any,
        test_ratio: float = 0.2,
        val_ratio: float = 0.2,
        split_strategy: str = "trial",
        training_mode: str = "individual",
        **kwargs,
    ) -> ToolResult:
        """Return a simulated split-configuration result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            test_ratio: Fraction of data reserved for testing.
            val_ratio: Fraction of data reserved for validation.
            split_strategy: How to split data (trial/session/subject).
            training_mode: Training paradigm (individual/group).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation message with the saved split strategy and mode.

        """
        if not self._state.epochs_ready:
            return ToolResult(
                ok=False,
                message="Create EEG epochs before saving data splitting settings.",
                error_type="precondition",
            )
        self._state.split_spec_saved = True
        return ToolResult(
            ok=True,
            message=(
                f"Saved data splitting settings (Split: {split_strategy}, "
                f"Mode: {training_mode})."
            ),
        )
