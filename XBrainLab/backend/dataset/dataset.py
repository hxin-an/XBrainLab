"""Dataset module for storing and managing split EEG data partitions."""

from __future__ import annotations

import numpy as np

from ..utils import validate_type
from .data_splitter import DataSplittingConfig
from .epochs import Epochs


class Dataset:
    """Container for a single split dataset with train/val/test partitions.

    Manages boolean masks over epoch data to define train, validation, and test
    splits without duplicating the underlying data.

    Attributes:
        SEQ: Class-level sequence counter for generating unique dataset IDs.
        name: Human-readable name of the dataset.
        epoch_data: Epoch data that this dataset partitions.
        config: Splitting configuration used to create this dataset.
        dataset_id: Unique identifier for this dataset instance.
        remaining_mask: Boolean mask of trials not yet assigned to any split.
        train_mask: Boolean mask of trials assigned to the training set.
        val_mask: Boolean mask of trials assigned to the validation set.
        test_mask: Boolean mask of trials assigned to the test set.
        is_selected: Whether this dataset is selected for downstream use.

    """

    SEQ = 0

    def __init__(self, epoch_data: Epochs, config: DataSplittingConfig):
        """Initialize a Dataset with epoch data and splitting config.

        Args:
            epoch_data: Epoch data to be split.
            config: Splitting configuration defining how data is partitioned.

        """
        validate_type(epoch_data, Epochs, "epoch_data")
        validate_type(config, DataSplittingConfig, "config")
        self.name = ""
        self.epoch_data = epoch_data
        self.config = config
        self.dataset_id = Dataset.SEQ
        Dataset.SEQ += 1

        data_length = epoch_data.get_data_length()
        self.remaining_mask = np.ones(data_length, dtype=bool)

        self.train_mask = np.zeros(data_length, dtype=bool)
        self.val_mask = np.zeros(data_length, dtype=bool)
        self.test_mask = np.zeros(data_length, dtype=bool)
        self.is_selected = True

    def get_epoch_data(self) -> Epochs:
        """Get the epoch data of the dataset."""
        return self.epoch_data

    def get_name(self) -> str:
        """Get the formatted name of the dataset."""
        return self.name

    def get_ori_name(self) -> str:
        """Get the original name of the dataset."""
        return self.name

    def get_all_trial_numbers(self) -> tuple:
        """Get each number of trials in train, validation and test set.

        Returns:
            (train_number, val_number, test_number)

        """
        train_number = sum(self.train_mask)
        val_number = sum(self.val_mask)
        test_number = sum(self.test_mask)
        return train_number, val_number, test_number

    def get_treeview_row_info(self) -> tuple:
        """Return the information of the dataset for displaying in UI treeview.

        Returns:
            (selected: str,
             name: str,
             train_number: int,
             val_number: int,
             test_number: int
            )

        """
        train_number, val_number, test_number = self.get_all_trial_numbers()
        selected = "O" if self.is_selected else "X"
        name = self.get_name()
        return selected, name, train_number, val_number, test_number

    def set_selection(self, select):
        """Set the dataset selection state.

        Args:
            select: Whether this dataset should be selected.

        """
        self.is_selected = select

    def set_name(self, name: str):
        """Set the dataset name.

        Args:
            name: New name for the dataset.

        """
        self.name = name

    def has_set_empty(self) -> bool:
        """Check whether any split (train, val, or test) is empty.

        Returns:
            True if any of the train, validation, or test sets has zero trials.

        """
        train_number, val_number, test_number = self.get_all_trial_numbers()
        return train_number == 0 or val_number == 0 or test_number == 0

    def set_test(self, mask: np.ndarray) -> None:
        """Set the test set mask and update the remaining mask.

        Args:
            mask: Boolean mask indicating candidate test trials.

        """
        self.test_mask = mask & self.remaining_mask
        self.remaining_mask &= np.logical_not(mask)

    def set_val(self, mask: np.ndarray) -> None:
        """Set the validation set mask and update the remaining mask.

        Args:
            mask: Boolean mask indicating candidate validation trials.

        """
        self.val_mask = mask & self.remaining_mask
        self.remaining_mask &= np.logical_not(mask)

    def set_remaining_to_train(self) -> None:
        """Set the remaining trials as training set."""
        self.train_mask |= self.remaining_mask
        self.remaining_mask &= False

    def get_remaining_mask(self) -> np.ndarray:
        """Return the mask for remaining trials."""
        return self.remaining_mask.copy()

    ## filter
    def intersection_with_subject_by_idx(
        self,
        mask: np.ndarray,
        idx: int,
    ) -> np.ndarray:
        """Return the intersection of the mask and the subject mask.

        Args:
            mask: Boolean mask to intersect.
            idx: Target subject index.

        Returns:
            Boolean mask of trials matching both the input mask and the subject.

        """
        return mask & self.epoch_data.pick_subject_mask_by_idx(idx)

    def set_remaining_by_subject_idx(self, subject_idx: int) -> None:
        """Restrict remaining mask to include only a specific subject.

        Args:
            subject_idx: Subject index to keep in the remaining mask.

        """
        subject_mask = self.epoch_data.pick_subject_mask_by_idx(subject_idx)
        self.remaining_mask &= subject_mask

    def discard_remaining_mask(self, mask: np.ndarray) -> None:
        """Remove masked trials from the remaining mask.

        Args:
            mask: Boolean mask of trials to discard from remaining.

        """
        self.remaining_mask &= np.logical_not(mask)

    # train
    def get_training_data(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the training data and label.

        WARNING: This creates a COPY of the data, doubling RAM usage.
        For training, use get_training_indices() and SharedMemoryDataset instead.
        """
        X = self.epoch_data.get_data()[self.train_mask]
        y = self.epoch_data.get_label_list()[self.train_mask]
        return X, y

    def get_training_indices(self) -> np.ndarray:
        """Return the indices of available training data."""
        return np.where(self.train_mask)[0]

    def get_val_indices(self) -> np.ndarray:
        """Return the indices of available validation data."""
        return np.where(self.val_mask)[0]

    def get_test_indices(self) -> np.ndarray:
        """Return the indices of available test data."""
        return np.where(self.test_mask)[0]

    def get_val_data(self) -> tuple:
        """Return the validation data and label.

        Returns:
            (X, y)

        """
        X = self.epoch_data.get_data()[self.val_mask]
        y = self.epoch_data.get_label_list()[self.val_mask]
        return X, y

    def get_test_data(self) -> tuple:
        """Return the test data and label.

        Returns:
            (X, y)

        """
        X = self.epoch_data.get_data()[self.test_mask]
        y = self.epoch_data.get_label_list()[self.test_mask]
        return X, y

    # get data len
    def get_train_len(self) -> int:
        """Return the number of trials in training set."""
        return sum(self.train_mask)

    def get_val_len(self) -> int:
        """Return number of trials in validation set."""
        return sum(self.val_mask)

    def get_test_len(self) -> int:
        """Return number of trials in test set."""
        return sum(self.test_mask)
