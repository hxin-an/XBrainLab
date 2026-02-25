"""Data splitter module defining splitting configuration for dataset partitioning."""

from __future__ import annotations

from ..utils import validate_list_type, validate_type
from .option import SplitByType, SplitUnit, TrainingType, ValSplitByType


class DataSplitter:
    """Configuration for a single data splitting action.

    Encapsulates the split type, value, and unit for one splitting step
    (e.g. "split 20% of trials by session").

    Attributes:
        split_type: Type of splitting action (e.g. by session, trial, subject).
        value_var: String representation of the splitting value.
        split_unit: Unit of the splitting value (ratio, number, kfold, manual).
        is_option: Whether this splitter is a real option or just a label.
        text: Human-readable string representation of the split type.

    """

    def __init__(
        self,
        split_type: SplitByType | ValSplitByType,
        value_var: str | None = None,
        split_unit: SplitUnit | None = None,
        is_option: bool = True,
    ):
        """Initialize a DataSplitter.

        Args:
            split_type: Type of splitting action.
            value_var: String representation of the splitting value.
            split_unit: Unit of the splitting value.
            is_option: Whether this splitter is a real option or just a label.

        """
        validate_type(split_type, (SplitByType, ValSplitByType), "split_type")
        if split_unit:
            validate_type(split_unit, SplitUnit, "split_unit")
        self.is_option = is_option
        self.split_type = split_type
        self.text = split_type.value
        self.value_var = value_var
        self.split_unit = split_unit

    def is_valid(self) -> bool:
        """Check whether the splitter's value matches its unit and constraints.

        Returns:
            True if the value is valid for the configured split unit.

        """
        # check if all required fields are filled
        if self.value_var is None:
            return False
        if self.split_unit is None:
            return False

        # ratio: should be float
        if self.split_unit == SplitUnit.RATIO:
            try:
                val = float(self.value_var)
                if 0 <= val <= 1:
                    return True
            except ValueError:
                return False
        # number: should be int
        elif self.split_unit == SplitUnit.NUMBER:
            return str(self.value_var).isdigit()
        # kfold: should be int > 0
        elif self.split_unit == SplitUnit.KFOLD:
            val_str = str(self.value_var)
            if val_str.isdigit():
                return int(val_str) > 0
        # manual: should be list of int separated by space
        elif self.split_unit == SplitUnit.MANUAL:
            val_str = str(self.value_var).strip()
            vals = val_str.split(" ")
            return all(not (len(val.strip()) > 0 and not val.isdigit()) for val in vals)
        else:
            raise NotImplementedError

        return False

    def get_value(self) -> float | list[int]:
        """Get the parsed option value based on split unit.

        Returns:
            Parsed value: a list of ints for manual selection, or a float
            for ratio/number/kfold.

        Raises:
            ValueError: If the splitter is invalid or value_var is None.

        """
        if not self.is_valid():
            raise ValueError("Splitter is not valid")
        if self.value_var is None:
            raise ValueError("value_var cannot be None")
        if self.split_unit == SplitUnit.MANUAL:
            return [
                int(i) for i in self.value_var.strip().split(" ") if len(i.strip()) > 0
            ]
        return float(self.value_var)

    def get_raw_value(self) -> str:
        """Get the raw string value.

        Returns:
            The raw string value of this splitter.

        Raises:
            ValueError: If the splitter is invalid or value_var is None.

        """
        if not self.is_valid():
            raise ValueError("Splitter is not valid")
        if self.value_var is None:
            raise ValueError("value_var cannot be None")
        return self.value_var

    def get_split_unit(self) -> SplitUnit | None:
        """Get the split unit.

        Returns:
            The split unit, or None if not set.

        """
        return self.split_unit

    def get_split_unit_repr(self) -> str:
        """Get a string representation of the split unit.

        Returns:
            String in the form ``"SplitUnit.NAME"`` or ``"None"``.

        """
        if self.split_unit is None:
            return "None"
        return f"{self.split_unit.__class__.__name__}.{self.split_unit.name}"

    def get_split_type_repr(self) -> str:
        """Get a string representation of the split type.

        Returns:
            String in the form ``"SplitByType.NAME"``.

        """
        return f"{self.split_type.__class__.__name__}.{self.split_type.name}"


class DataSplittingConfig:
    """Configuration container for a complete data splitting scheme.

    Stores the training type, cross-validation flag, and lists of splitters
    for both validation and test sets.

    Attributes:
        train_type: Training scheme type (full-data or individual).
        is_cross_validation: Whether cross-validation is enabled.
        val_splitter_list: List of splitters for the validation set.
        test_splitter_list: List of splitters for the test set.

    """

    def __init__(
        self,
        train_type: TrainingType,
        is_cross_validation: bool,
        val_splitter_list: list[DataSplitter],
        test_splitter_list: list[DataSplitter],
    ):
        """Initialize a DataSplittingConfig.

        Args:
            train_type: Training scheme type.
            is_cross_validation: Whether to use cross-validation.
            val_splitter_list: List of splitters for the validation set.
            test_splitter_list: List of splitters for the test set.

        """
        validate_type(train_type, TrainingType, "train_type")
        validate_type(is_cross_validation, bool, "is_cross_validation")
        validate_list_type(val_splitter_list, DataSplitter, "val_splitter_list")
        validate_list_type(test_splitter_list, DataSplitter, "test_splitter_list")

        self.train_type = train_type  # TrainingType
        self.is_cross_validation = is_cross_validation
        self.val_splitter_list = val_splitter_list
        self.test_splitter_list = test_splitter_list

    def get_splitter_option(self) -> tuple[list[DataSplitter], list[DataSplitter]]:
        """Get the validation and test splitter lists.

        Returns:
            Tuple of (val_splitter_list, test_splitter_list).

        """
        return self.val_splitter_list, self.test_splitter_list

    def get_train_type_repr(self) -> str:
        """Get a string representation of the training type.

        Returns:
            String in the form ``"TrainingType.NAME"``.

        """
        return f"{self.train_type.__class__.__name__}.{self.train_type.name}"
