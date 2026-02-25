"""Base class for all EEG preprocessors."""

from copy import deepcopy

from ..load_data import Raw
from ..utils import validate_list_type


class PreprocessBase:
    """Base class for preprocessors.

    Provides the common interface for all preprocessing operations. Subclasses
    must implement :meth:`_data_preprocess` and :meth:`get_preprocess_desc`.

    Attributes:
        preprocessed_data_list: List of :class:`~XBrainLab.backend.load_data.Raw`
            instances to be preprocessed.
    """

    def __init__(self, preprocessed_data_list: list[Raw]):
        """Initializes the preprocessor with a deep copy of the data.

        Args:
            preprocessed_data_list: List of
                :class:`~XBrainLab.backend.load_data.Raw` instances to
                preprocess.

        Raises:
            TypeError: If the list contains invalid types.
            ValueError: If the list is empty.
        """
        self.preprocessed_data_list = deepcopy(preprocessed_data_list)
        self.check_data()

    def check_data(self) -> None:
        """Check if the data is valid.

        Raises:
            TypeError: If the data contains items that are
                        not instances of :class:`XBrainLab.backend.load_data.Raw`.
            ValueError: If the data is empty.
        """
        if not self.preprocessed_data_list:
            raise ValueError("No valid data is loaded")
        validate_list_type(self.preprocessed_data_list, Raw, "preprocessed_data_list")

    def get_preprocessed_data_list(self) -> list[Raw]:
        """Get the preprocessed data list."""
        return self.preprocessed_data_list

    def get_preprocess_desc(self, *args, **kwargs) -> str:
        """Returns a human-readable description of the preprocessing step.

        Args:
            *args: Preprocessing-specific positional arguments.
            **kwargs: Preprocessing-specific keyword arguments.

        Returns:
            A string describing the preprocessing operation.

        Raises:
            NotImplementedError: Must be overridden by subclasses.
        """
        raise NotImplementedError

    def data_preprocess(self, *args, **kwargs) -> list[Raw]:
        """Applies preprocessing to all data in the list.

        Iterates over each item in ``preprocessed_data_list``, calls
        :meth:`_data_preprocess`, and records the operation description
        in each item's preprocessing history.

        Args:
            *args: Preprocessing-specific positional arguments forwarded to
                :meth:`_data_preprocess`.
            **kwargs: Preprocessing-specific keyword arguments forwarded to
                :meth:`_data_preprocess`.

        Returns:
            The list of preprocessed
            :class:`~XBrainLab.backend.load_data.Raw` instances.
        """
        for preprocessed_data in self.preprocessed_data_list:
            self._data_preprocess(preprocessed_data, *args, **kwargs)
            preprocessed_data.add_preprocess(self.get_preprocess_desc(*args, **kwargs))
        return self.preprocessed_data_list

    def _data_preprocess(self, preprocessed_data: Raw, *args, **kwargs) -> None:
        """Applies a single preprocessing step to one data instance.

        Args:
            preprocessed_data: The data instance to preprocess.
            *args: Preprocessing-specific positional arguments.
            **kwargs: Preprocessing-specific keyword arguments.

        Raises:
            NotImplementedError: Must be overridden by subclasses.
        """
        raise NotImplementedError
