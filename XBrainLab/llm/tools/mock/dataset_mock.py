from typing import Any

from ..definitions.dataset_def import (
    BaseAttachLabelsTool,
    BaseClearDatasetTool,
    BaseGenerateDatasetTool,
    BaseGetDatasetInfoTool,
    BaseListFilesTool,
    BaseLoadDataTool,
)


class MockListFilesTool(BaseListFilesTool):
    def execute(
        self, study: Any, directory: str | None = None, pattern: str = "*", **kwargs
    ) -> str:
        if directory is None:
            return "Error: directory is required"
        return f"['A01T.gdf', 'A02T.gdf'] found in {directory} matching {pattern}"


class MockLoadDataTool(BaseLoadDataTool):
    def execute(self, study: Any, paths: list[str] | None = None, **kwargs) -> str:
        if paths is None:
            return "Error: paths list is required"
        return f"Successfully loaded data from {len(paths)} sources: {paths}"


class MockAttachLabelsTool(BaseAttachLabelsTool):
    def execute(
        self,
        study: Any,
        mapping: dict[str, str] | None = None,
        label_format: str | None = None,
        **kwargs,
    ) -> str:
        if mapping is None:
            return "Error: mapping is required"
        return f"Attached labels to {len(mapping)} files."


class MockClearDatasetTool(BaseClearDatasetTool):
    def execute(self, study: Any, **kwargs) -> str:
        return "Dataset cleared."


class MockGetDatasetInfoTool(BaseGetDatasetInfoTool):
    def execute(self, study: Any, **kwargs) -> str:
        return "Dataset Info: 2 files loaded, 250Hz, 22 channels."


class MockGenerateDatasetTool(BaseGenerateDatasetTool):
    def execute(
        self,
        study: Any,
        test_ratio: float = 0.2,
        val_ratio: float = 0.2,
        split_strategy: str = "trial",
        training_mode: str = "individual",
        **kwargs,
    ) -> str:
        return f"Generated dataset (Split: {split_strategy}, Mode: {training_mode})."
