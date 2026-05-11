"""Dataset package for data splitting, epoch management, and dataset generation."""

from .data_splitter import DataSplitter, DataSplittingConfig
from .dataset import Dataset
from .dataset_generator import DatasetGenerator
from .epochs import Epochs
from .option import SplitByType, SplitUnit, TrainingType, ValSplitByType
from .split_audit import (
    SplitAuditIssue,
    SplitAuditResult,
    audit_dataset_splits,
    build_split_artifact,
    split_indices,
    write_split_artifact,
)

__all__ = [
    "DataSplitter",
    "DataSplittingConfig",
    "Dataset",
    "DatasetGenerator",
    "Epochs",
    "SplitAuditIssue",
    "SplitAuditResult",
    "SplitByType",
    "SplitUnit",
    "TrainingType",
    "ValSplitByType",
    "audit_dataset_splits",
    "build_split_artifact",
    "split_indices",
    "write_split_artifact",
]
