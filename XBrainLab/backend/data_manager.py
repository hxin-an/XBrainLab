"""Data lifecycle management for loading, preprocessing, epoching, and datasets."""

from copy import deepcopy

from .dataset import Dataset, DatasetGenerator, Epochs
from .load_data import Raw, RawDataLoader
from .preprocessor import PreprocessBase
from .utils import validate_issubclass, validate_list_type
from .utils.logger import logger


class DataManager:
    """Manages the data lifecycle for loading, preprocessing, epoching, and datasets.

    Extracted from the monolithic Study class (Reference: BR01).

    Attributes:
        loaded_data_list: List of loaded raw data objects.
        preprocessed_data_list: List of preprocessed raw data objects.
        epoch_data: Epoch data generated from preprocessed data, or None.
        datasets: List of generated dataset objects.
        dataset_generator: Dataset generator instance, or None.
        dataset_locked: Whether the dataset is locked for modification.
        backup_loaded_data_list: Backup of loaded data for undo, or None.
    """

    def __init__(self):
        # Data States
        self.loaded_data_list: list[Raw] = []
        self.preprocessed_data_list: list[Raw] = []
        self.epoch_data: Epochs | None = None

        # Generation
        self.datasets: list[Dataset] = []
        self.dataset_generator: DatasetGenerator | None = None

        # Locking & Backup
        self.dataset_locked = False
        self.backup_loaded_data_list: list[Raw] | None = None

    # --- Loading ---
    def get_raw_data_loader(self) -> RawDataLoader:
        """Get the raw data loader instance.

        Returns:
            RawDataLoader: An instance of the raw data loader.
        """
        return RawDataLoader()

    def set_loaded_data_list(
        self, loaded_data_list: list[Raw], force_update: bool = False
    ) -> None:
        """Set the loaded raw data list and propagate changes.

        Args:
            loaded_data_list (list[Raw]): List of loaded raw data objects.
            force_update (bool, optional): Whether to force update and clear
                downstream data. Defaults to False.
        """
        validate_list_type(loaded_data_list, Raw, "loaded_data_list")
        # Note: clean_raw_data is internal or called by Study facade if needed.
        # Here we assume manager logic.
        self.clean_raw_data(force_update)

        # Copy to preprocessed (Initial state)
        self.set_preprocessed_data_list(
            preprocessed_data_list=deepcopy(loaded_data_list), force_update=force_update
        )
        self.loaded_data_list = loaded_data_list
        logger.info(f"Loaded {len(loaded_data_list)} raw data files")

    def backup_loaded_data(self) -> None:
        """Backup the currently loaded data list to allow undoing changes
        (e.g., channel selection)."""
        if self.loaded_data_list:
            self.backup_loaded_data_list = deepcopy(self.loaded_data_list)
            logger.info("Backed up loaded data list")

    # --- Preprocessing ---
    def set_preprocessed_data_list(
        self, preprocessed_data_list: list[Raw], force_update: bool = False
    ) -> None:
        """Set the preprocessed data list and generate epochs if possible.

        Args:
            preprocessed_data_list (list[Raw]): List of preprocessed data objects.
            force_update (bool, optional): Whether to force update and clear
                downstream data. Defaults to False.
        """
        validate_list_type(preprocessed_data_list, Raw, "preprocessed_data_list")
        self.clean_datasets(force_update=force_update)

        self.preprocessed_data_list = preprocessed_data_list
        logger.info(
            f"Set preprocessed data list with {len(preprocessed_data_list)} items"
        )

        # Check if we should generate epochs
        for pp_data in preprocessed_data_list:
            if pp_data.is_raw():
                self.epoch_data = None
                return
        self.epoch_data = Epochs(preprocessed_data_list)

    def reset_preprocess(self, force_update=False) -> None:
        """Reset preprocessing to the original loaded data state.

        Args:
            force_update (bool, optional): Whether to force update. Defaults to False.
        """
        # Restore backup
        if self.backup_loaded_data_list:
            logger.info("Restoring loaded data from backup (Undoing Channel Selection)")
            self.loaded_data_list = self.backup_loaded_data_list
            self.backup_loaded_data_list = None
            self.unlock_dataset()

        if self.loaded_data_list:
            self.set_preprocessed_data_list(
                deepcopy(self.loaded_data_list), force_update=force_update
            )
        logger.info("Reset preprocess to loaded data")

    def preprocess(self, preprocessor: type[PreprocessBase], **kwargs) -> None:
        """Apply a preprocessing step to the current data.

        Args:
            preprocessor (type[PreprocessBase]): The preprocessor class to apply.
            **kwargs: Keyword arguments for the preprocessor's data_preprocess method.
        """
        validate_issubclass(preprocessor, PreprocessBase, "preprocessor")
        pp_instance = preprocessor(self.preprocessed_data_list)
        pp_instance.check_data()
        preprocessed_data_list = pp_instance.data_preprocess(**kwargs)
        self.set_preprocessed_data_list(preprocessed_data_list)
        logger.info(f"Applied preprocessing: {pp_instance.__class__.__name__}")

    # --- Datasets ---
    def set_datasets(self, datasets: list[Dataset], force_update: bool = False) -> None:
        """Set the generated datasets.

        Args:
            datasets (list[Dataset]): List of dataset objects.
            force_update (bool, optional): Whether to force update. Defaults to False.
        """
        validate_list_type(datasets, Dataset, "datasets")
        self.clean_datasets(force_update=force_update)
        self.datasets = datasets
        logger.info(f"Set {len(datasets)} datasets for training")

    # --- Cleaning ---
    def has_raw_data(self) -> bool:
        """Return whether raw data (or downstream datasets) exist.

        Pure query — never raises.
        """
        return bool(self.loaded_data_list) or self.has_datasets()

    def has_datasets(self) -> bool:
        """Return whether generated datasets exist.

        Pure query — never raises.
        """
        return bool(self.datasets)

    def _guard_clean_raw_data(self) -> None:
        """Raise if raw data or datasets exist (interactive guard)."""
        if self.has_raw_data():
            raise ValueError("This step has already been done… clean_raw_data first.")

    def _guard_clean_datasets(self) -> None:
        """Raise if datasets exist (interactive guard)."""
        if self.has_datasets():
            raise ValueError("This step has already been done… clean_datasets first.")

    def clean_raw_data(self, force_update: bool = True) -> None:
        """Clear all raw, preprocessed, and epoch data.

        Args:
            force_update: If ``False``, raises when data already exists.
        """
        self.clean_datasets(force_update=force_update)
        if not force_update:
            self._guard_clean_raw_data()
        self.loaded_data_list = []
        self.preprocessed_data_list = []
        self.epoch_data = None
        self.unlock_dataset()
        logger.info("Cleared raw data and downstream data")

    def clean_datasets(self, force_update: bool = True) -> None:
        """Clear generated datasets.

        Args:
            force_update: If ``False``, raises when datasets already exist.
        """
        if not force_update:
            self._guard_clean_datasets()
        self.datasets = []
        self.dataset_generator = None

    # --- Locking ---
    def lock_dataset(self) -> None:
        """Lock the dataset to prevent modification."""
        self.dataset_locked = True
        logger.info("Dataset locked")

    def unlock_dataset(self) -> None:
        """Unlock the dataset to allow modification."""
        self.dataset_locked = False
        logger.info("Dataset unlocked")

    def is_locked(self) -> bool:
        """Check if the dataset is locked.

        Returns:
            bool: True if locked, False otherwise.
        """
        return self.dataset_locked
