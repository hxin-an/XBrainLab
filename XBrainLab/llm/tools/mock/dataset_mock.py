
from typing import Any, Dict, List
from ..definitions.dataset_def import (
    BaseListFilesTool, BaseLoadDataTool, 
    BaseAttachLabelsTool, BaseClearDatasetTool, BaseGetDatasetInfoTool, 
    BaseGenerateDatasetTool
)

class MockListFilesTool(BaseListFilesTool):
    def execute(self, study: Any, directory: str, pattern: str = "*") -> str:
        return f"['A01T.gdf', 'A02T.gdf'] found in {directory} matching {pattern}"

class MockLoadDataTool(BaseLoadDataTool):
    def execute(self, study: Any, paths: List[str]) -> str:
        return f"Successfully loaded data from {len(paths)} sources: {paths}"

class MockAttachLabelsTool(BaseAttachLabelsTool):
    def execute(self, study: Any, mapping: Dict[str, str], label_format: str = None) -> str:
        return f"Attached labels to {len(mapping)} files."

class MockClearDatasetTool(BaseClearDatasetTool):
    def execute(self, study: Any) -> str:
        return "Dataset cleared."

class MockGetDatasetInfoTool(BaseGetDatasetInfoTool):
    def execute(self, study: Any) -> str:
        return "Dataset Info: 2 files loaded, 250Hz, 22 channels."

class MockGenerateDatasetTool(BaseGenerateDatasetTool):
    def execute(self, study: Any, test_ratio: float = 0.2, val_ratio: float = 0.2, 
                split_strategy: str = "trial", training_mode: str = "individual") -> str:
        return f"Generated dataset (Split: {split_strategy}, Mode: {training_mode})."
