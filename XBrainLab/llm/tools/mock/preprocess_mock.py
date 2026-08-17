"""Deterministic mocks for the five direct preprocessing actions."""

from typing import Any

from ..definitions.preprocess_def import (
    BaseBandPassFilterTool,
    BaseNormalizeTool,
    BaseNotchFilterTool,
    BaseRereferenceTool,
    BaseResampleTool,
)
from ..result_contract import ToolResult
from .state import MockWorkflowState


class _RequiresLoadedData:
    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def _loaded_data_precondition(self) -> ToolResult | None:
        if self._state.data_loaded:
            return None
        return ToolResult(
            ok=False,
            message="Load EEG data before preprocessing.",
            error_type="precondition",
        )


class MockBandPassFilterTool(_RequiresLoadedData, BaseBandPassFilterTool):
    def execute(
        self,
        study: Any,
        low_freq: float | None = None,
        high_freq: float | None = None,
        **kwargs,
    ) -> ToolResult:
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if low_freq is None or high_freq is None:
            return ToolResult(
                False, "Error: frequencies are required", error_type="input"
            )
        return ToolResult(True, f"Applied bandpass filter ({low_freq}-{high_freq} Hz).")


class MockNotchFilterTool(_RequiresLoadedData, BaseNotchFilterTool):
    def execute(
        self,
        study: Any,
        freq: float | None = None,
        **kwargs,
    ) -> ToolResult:
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if freq is None:
            return ToolResult(False, "Error: frequency is required", error_type="input")
        return ToolResult(True, f"Applied notch filter at {freq} Hz.")


class MockResampleTool(_RequiresLoadedData, BaseResampleTool):
    def execute(
        self,
        study: Any,
        rate: int | None = None,
        **kwargs,
    ) -> ToolResult:
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if rate is None:
            return ToolResult(False, "Error: rate is required", error_type="input")
        return ToolResult(True, f"Resampled data to {rate} Hz.")


class MockNormalizeTool(_RequiresLoadedData, BaseNormalizeTool):
    def execute(
        self,
        study: Any,
        method: str | None = None,
        **kwargs,
    ) -> ToolResult:
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if method is None:
            return ToolResult(False, "Error: method is required", error_type="input")
        return ToolResult(True, f"Normalized data using {method} method.")


class MockRereferenceTool(_RequiresLoadedData, BaseRereferenceTool):
    def execute(
        self,
        study: Any,
        method: str | None = None,
        **kwargs,
    ) -> ToolResult:
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if method is None:
            return ToolResult(False, "Error: method is required", error_type="input")
        return ToolResult(True, f"Re-referenced data to {method}.")
