"""Base class for all EEG preprocessors."""

from concurrent.futures import Future, ThreadPoolExecutor, wait
from copy import deepcopy
from typing import Any

from ..application.owned_work import (
    bind_captured_owned_work,
    capture_owned_work,
    owned_work_checkpoint,
)
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

    max_parallel_recordings = 1

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
        self.preprocessed_data_list: list[Raw] = []
        total = len(preprocessed_data_list)
        memo: dict[int, Any] = {}
        for index, preprocessed_data in enumerate(preprocessed_data_list):
            owned_work_checkpoint(
                "Preparing working EEG recordings",
                completed=index,
                total=total,
            )
            self.preprocessed_data_list.append(deepcopy(preprocessed_data, memo))
            owned_work_checkpoint(
                "Preparing working EEG recordings",
                completed=index + 1,
                total=total,
            )
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
        if (
            len(self.preprocessed_data_list) <= 1
            or self.max_parallel_recordings == 1
            or not self._has_distinct_mne_instances()
        ):
            return self._data_preprocess_serial(*args, **kwargs)
        return self._data_preprocess_parallel(*args, **kwargs)

    def _data_preprocess_serial(self, *args, **kwargs) -> list[Raw]:
        total = len(self.preprocessed_data_list)
        for index, preprocessed_data in enumerate(self.preprocessed_data_list):
            owned_work_checkpoint(
                "Preprocessing EEG recordings",
                completed=index,
                total=total,
            )
            self._data_preprocess(preprocessed_data, *args, **kwargs)
            preprocessed_data.add_preprocess(self.get_preprocess_desc(*args, **kwargs))
            owned_work_checkpoint(
                "Preprocessing EEG recordings",
                completed=index + 1,
                total=total,
            )
        return self.preprocessed_data_list

    def _data_preprocess_parallel(self, *args, **kwargs) -> list[Raw]:
        """Run independent recording transforms with bounded worker ownership."""
        total = len(self.preprocessed_data_list)
        worker_count = min(2, self.max_parallel_recordings)
        captured_work = capture_owned_work()
        completed = 0

        def process_one(preprocessed_data: Raw) -> None:
            with bind_captured_owned_work(captured_work):
                owned_work_checkpoint(
                    "Preprocessing EEG recordings",
                    completed=completed,
                    total=total,
                )
                self._data_preprocess(preprocessed_data, *args, **kwargs)
                preprocessed_data.add_preprocess(
                    self.get_preprocess_desc(*args, **kwargs)
                )

        pending = iter(self.preprocessed_data_list)
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="XBrainLab-preprocess-recording",
        ) as executor:
            active: set[Future[None]] = set()
            for _ in range(min(worker_count, total)):
                active.add(executor.submit(process_one, next(pending)))
            while active:
                finished, _ = wait(active)
                for future in finished:
                    active.remove(future)
                    try:
                        future.result()
                    except BaseException:
                        for remaining in active:
                            remaining.cancel()
                        raise
                completed += len(finished)
                owned_work_checkpoint(
                    "Preprocessing EEG recordings",
                    completed=completed,
                    total=total,
                )
                for _ in finished:
                    try:
                        preprocessed_data = next(pending)
                    except StopIteration:
                        break
                    active.add(executor.submit(process_one, preprocessed_data))
        return self.preprocessed_data_list

    def _has_distinct_mne_instances(self) -> bool:
        """Reject a duplicate source retained by the deepcopy memo."""
        return len({id(row.get_mne()) for row in self.preprocessed_data_list}) == len(
            self.preprocessed_data_list
        )

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
