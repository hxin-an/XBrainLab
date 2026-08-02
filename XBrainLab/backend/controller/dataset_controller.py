"""Dataset controller for managing data loading and manipulation.

Provides a high-level interface for importing, removing, and preprocessing
EEG data files, as well as label management and channel selection.
"""

from collections.abc import Sequence
from importlib import import_module
from typing import Any

from XBrainLab.backend.services.dataset_state_service import DatasetStateService
from XBrainLab.backend.utils.observer import Observable


class _LazyPreprocessorProxy:
    """Patch-friendly lazy proxy for the heavy preprocessor package."""

    def __getattr__(self, name: str) -> Any:
        preprocessor_module = import_module("XBrainLab.backend.preprocessor")
        return getattr(preprocessor_module, name)


preprocessor: Any = _LazyPreprocessorProxy()
EventLoader: Any | None = None
LabelImportService: Any | None = None
RawDataLoader: Any | None = None
RawDataLoaderFactory: Any | None = None


def _label_import_service_class() -> Any:
    patched = globals()["LabelImportService"]
    if patched is not None:
        return patched
    from XBrainLab.backend.services.label_import_service import (  # noqa: PLC0415
        LabelImportService,
    )

    return LabelImportService


def _raw_data_loader_class() -> Any:
    patched = globals()["RawDataLoader"]
    if patched is not None:
        return patched
    from XBrainLab.backend.load_data.data_loader import RawDataLoader  # noqa: PLC0415

    return RawDataLoader


def _raw_data_loader_factory() -> Any:
    patched = globals()["RawDataLoaderFactory"]
    if patched is not None:
        return patched
    from XBrainLab.backend.load_data.factory import (  # noqa: PLC0415
        RawDataLoaderFactory,
    )

    return RawDataLoaderFactory


def _event_loader_class() -> Any:
    patched = globals()["EventLoader"]
    if patched is not None:
        return patched
    from XBrainLab.backend.load_data.event_loader import EventLoader  # noqa: PLC0415

    return EventLoader


class DatasetController(Observable):
    """Controller for managing dataset operations.

    Handles data loading, modification, label management, channel
    selection, and interactions with the :class:`Study` backend.

    Events:
        data_changed: Emitted when the loaded data list is modified.
        dataset_locked(bool): Emitted when the dataset lock state
            changes. ``True`` indicates downstream operations exist.
        import_finished(int, list): Emitted after an import operation
            completes, carrying the success count and a list of error
            messages.
        error_occurred(str): Emitted when a recoverable error occurs.

    Attributes:
        study: Reference to the :class:`Study` backend instance.
        label_service: Service for batch label import operations.

    """

    def __init__(
        self,
        study,
        dataset_state: DatasetStateService | None = None,
    ):
        super().__init__()
        self.study = study
        shared_state = dataset_state or vars(study).get("dataset_state_service")
        self._dataset_state = (
            shared_state
            if isinstance(shared_state, DatasetStateService)
            else DatasetStateService(
                study,
                raw_loader_provider=_raw_data_loader_class,
                raw_factory_provider=_raw_data_loader_factory,
                label_service_provider=_label_import_service_class,
                channel_selection_provider=lambda: preprocessor.ChannelSelection,
                event_loader_provider=_event_loader_class,
            )
        )

    @property
    def label_service(self) -> Any:
        """Label import service, materialized only when label import is used."""
        return self._dataset_state.label_service

    @label_service.setter
    def label_service(self, value: Any) -> None:
        self._dataset_state.label_service = value

    def get_loaded_data_list(self):
        """Return the list of currently loaded raw data objects.

        Returns:
            The list of raw data objects held by the study.

        """
        return self._dataset_state.get_loaded_data_list()

    def is_locked(self):
        """Check if the dataset is locked.

        A dataset is locked when downstream operations (e.g. channel
        selection or epoching) have been applied.

        Returns:
            ``True`` if the dataset is locked, ``False`` otherwise.

        """
        return self._dataset_state.is_locked()

    def has_data(self):
        """Check whether any data has been loaded.

        Returns:
            ``True`` if the loaded data list is non-empty.

        """
        return self._dataset_state.has_data()

    def import_files(self, filepaths):
        """Import EEG data files into the dataset.

        Iterates over the given file paths, skips duplicates, and
        delegates to the appropriate loader. Successfully loaded files
        are appended to the study. Observers are notified via
        ``data_changed`` and ``import_finished`` events.

        Args:
            filepaths: Iterable of file path strings to import.

        Returns:
            A tuple ``(success_count, errors)`` where *success_count*
            is the number of files successfully imported and *errors*
            is a list of human-readable error strings.

        Raises:
            ValueError: If the existing dataset is in an inconsistent
                state and cannot initialise a new loader.

        """
        success_count, errors = self._dataset_state.import_files(filepaths)
        if success_count > 0:
            self.notify("data_changed")
        self.notify("import_finished", success_count, errors)
        return success_count, errors

    def clean_dataset(self):
        """Clear all loaded data and notify observers."""
        self._dataset_state.clean_dataset()
        self.notify("data_changed")

    def remove_files(self, indices):
        """Remove files at the specified indices from the dataset.

        Indices are processed in descending order to avoid shifting
        issues. A ``data_changed`` event is emitted if any files were
        actually removed.

        Args:
            indices: Sequence of zero-based integer indices identifying
                the files to remove.

        """
        if self._dataset_state.remove_files(list(indices)):
            self.notify("data_changed")

    def run_import_labels(
        self,
        target_files,
        label_map,
        file_mapping,
        mapping,
        selected_event_names=None,
    ):
        """Run the label import logic via the label service.

        Args:
            target_files: Data objects to receive the labels.
            label_map: Mapping from label identifiers to label values.
            file_mapping: Mapping from data files to label sources.
            mapping: Column/field mapping configuration.
            selected_event_names: Optional set of event names to filter by.

        Returns:
            The number of files that were successfully updated.

        """
        count = self._dataset_state.run_import_labels(
            target_files,
            label_map,
            file_mapping,
            mapping,
            selected_event_names,
        )
        if count > 0:
            self.notify("data_changed")
        return count

    def get_event_info(self):
        """Return aggregated event statistics for all loaded data.

        Scans each loaded data object's MNE annotations and collects
        total event count and unique event labels.

        Returns:
            A dictionary with the following keys:

            - ``total`` (int): Total number of annotation events.
            - ``unique_count`` (int): Number of unique event labels.
            - ``unique_labels`` (list[str]): Sorted list of unique
              event label strings.

        """
        return self._dataset_state.get_event_info()

    def get_runtime_diagnostics(self) -> dict[str, Any]:
        """Return aggregated runtime diagnostics for currently loaded data."""
        return self._dataset_state.get_runtime_diagnostics()

    def update_metadata(self, index, subject=None, session=None):
        """Update subject and/or session metadata for a specific file.

        Args:
            index: Zero-based index of the target file in the loaded
                data list.
            subject: New subject name, or ``None`` to leave unchanged.
            session: New session name, or ``None`` to leave unchanged.

        """
        current_list = self.study.loaded_data_list
        if 0 <= index < len(current_list):
            self.update_metadata_batch([(index, subject, session)])

    def update_metadata_batch(
        self,
        updates: Sequence[tuple[int, str | None, str | None]],
    ) -> int:
        """Apply metadata changes on copies, then reset preprocessing once.

        A setter failure leaves the loaded rows and every downstream data
        reference untouched because no Study-owned state is changed until all
        requested row updates have succeeded.
        """
        return self._dataset_state.update_metadata_batch(list(updates))

    def apply_smart_parse(self, results):
        """Apply smart-parser results to the dataset.

        Updates subject and session names for each loaded file that
        has a corresponding entry in *results*. A value of ``"-"``
        for either subject or session is treated as *no change*.

        Args:
            results: Dictionary mapping file path strings to
                ``(subject, session)`` tuples.

        Returns:
            The number of files whose metadata was updated.

        """
        count = self._dataset_state.apply_smart_parse(results)
        if count == 0:
            return 0
        self.notify("data_changed")
        self.notify("dataset_locked", False)
        return count

    def apply_channel_selection(self, selected_channels):
        """Apply channel selection to the dataset.

        Runs the :class:`~preprocessor.ChannelSelection` processor on
        the currently loaded data, backs up the original data, and
        locks the dataset to prevent further raw-data edits.

        Args:
            selected_channels: Sequence of channel name strings to
                retain in the dataset.

        Returns:
            ``True`` if the channel selection was applied successfully.

        Raises:
            Exception: Propagated from the underlying processor if
                channel selection fails.

        """
        result = self._dataset_state.apply_channel_selection(selected_channels)
        self.notify("data_changed")
        self.notify("dataset_locked", True)
        return result

    def get_filenames(self):
        """Return a list of file paths for all loaded data.

        Returns:
            List of file path strings.

        """
        return self._dataset_state.get_filenames()

    def reset_preprocess(self):
        """Reset downstream preprocessing and unlock the dataset."""
        self._dataset_state.reset_preprocess()
        self.notify("data_changed")
        self.notify("dataset_locked", False)

    # Label Import Wrappers
    def get_data_at_assignments(self, indices):
        """Return data objects at the given indices.

        Args:
            indices: Sequence of zero-based integer indices.

        Returns:
            List of data objects corresponding to the valid indices.

        """
        return self._dataset_state.get_data_at_assignments(indices)

    def apply_labels_batch(
        self,
        target_files,
        label_map,
        file_mapping,
        mapping,
        selected_event_names,
    ):
        """Apply labels in batch via the label service.

        Args:
            target_files: Data objects to receive the labels.
            label_map: Mapping from label identifiers to label values.
            file_mapping: Mapping from data files to label sources.
            mapping: Column/field mapping configuration.
            selected_event_names: Event names to include during import.

        Returns:
            The number of files successfully updated.

        """
        count = self._dataset_state.apply_labels_batch(
            target_files,
            label_map,
            file_mapping,
            mapping,
            selected_event_names,
        )
        if count > 0:
            self.notify("data_changed")
            self.notify("dataset_locked", False)
        return count

    def apply_labels_sequence(
        self,
        target_files,
        labels,
        mapping,
        selected_event_names,
        force_import=False,
    ):
        """Apply a sequential label list to loaded files.

        Args:
            target_files: Data objects to receive the labels.
            labels: Raw label data to apply.
            mapping: Column/field mapping configuration.
            selected_event_names: Event names to include during import.
            force_import: If ``True``, bypass validation checks.

        Returns:
            The number of files successfully updated.

        """
        count = self._dataset_state.apply_labels_sequence(
            target_files,
            labels,
            mapping,
            selected_event_names,
            force_import=force_import,
        )
        if count > 0:
            self.notify("data_changed")
            self.notify("dataset_locked", False)
        return count

    def get_epoch_count(self, data, event_names):
        """Get the number of epochs for a file given the target events.

        Args:
            data: A raw data object to inspect.
            event_names: Sequence of event name strings to count.

        Returns:
            The number of epochs that would be produced.

        """
        return self._dataset_state.get_epoch_count(data, event_names)

    def get_smart_filter_suggestions(self, data, target_count):
        """Return suggested event IDs for filtering based on a target count.

        Args:
            data: A raw data object to inspect.
            target_count: Desired number of epochs after filtering.

        Returns:
            Suggested event IDs suitable for reaching *target_count*.

        """
        return self._dataset_state.get_smart_filter_suggestions(data, target_count)
