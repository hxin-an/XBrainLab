from unittest.mock import MagicMock, patch

import numpy as np

from XBrainLab.backend.dataset import DatasetGenerator
from XBrainLab.backend.dataset.data_splitter import DataSplitter, DataSplittingConfig
from XBrainLab.backend.dataset.option import (
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)


def test_val_generation():
    # Mock Epochs
    epoch_data = MagicMock()
    epoch_data.get_data_length.return_value = 10

    # Mock pick methods to return a mask
    # Simulate picking 5 epochs for validation
    def pick_subject(mask, clean_mask, value, split_unit, group_idx):
        # Select last 5 epochs
        selected = np.zeros(10, dtype=bool)
        selected[5:] = True
        remaining = mask & (~selected)
        return selected & mask, remaining

    epoch_data.pick_subject.side_effect = pick_subject

    # Create Config
    test_splitter = DataSplitter(SplitByType.DISABLE, "0", SplitUnit.RATIO)
    val_splitter = DataSplitter(
        ValSplitByType.SUBJECT, "1", SplitUnit.MANUAL
    )  # Use index 1 for S2

    config = DataSplittingConfig(
        train_type=TrainingType.FULL,
        is_cross_validation=False,
        val_splitter_list=[val_splitter],
        test_splitter_list=[test_splitter],
    )

    # Create Generator
    with patch("XBrainLab.backend.dataset.dataset_generator.validate_type"):
        generator = DatasetGenerator(epoch_data, config)

    # Generate
    with (
        patch("XBrainLab.backend.dataset.dataset_generator.validate_type"),
        patch("XBrainLab.backend.dataset.dataset.validate_type"),
    ):
        generator.apply(MagicMock())

    # Check Dataset
    datasets = generator.datasets
    if not datasets:
        print("No datasets generated!")
        return

    dataset = datasets[0]

    # Dataset.get_val_data() calls epoch_data.get_data() and slices it
    # We need to mock get_data too if we want to check lengths
    epoch_data.get_data.return_value = np.random.randn(10, 3, 100)
    epoch_data.get_label_list.return_value = np.zeros(10)

    # We need to ensure dataset has the masks set
    # DatasetGenerator sets dataset.val_mask

    print(f"Val Mask: {dataset.val_mask}")
    print(f"Val Size: {sum(dataset.val_mask)}")

    if sum(dataset.val_mask) == 0:
        print("FAILURE: Validation mask is empty!")
    else:
        print("SUCCESS: Validation mask populated.")


if __name__ == "__main__":
    test_val_generation()
