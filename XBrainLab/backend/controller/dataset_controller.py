"""Dataset controller for managing data loading and manipulation.

Provides a high-level interface for importing, removing, and preprocessing
EEG data files, as well as label management and channel selection.
"""

# Ensure loaders are registered

from XBrainLab.backend import preprocessor
from XBrainLab.backend.exceptions import FileCorruptedError, UnsupportedFormatError
from XBrainLab.backend.load_data import EventLoader, RawDataLoader
from XBrainLab.backend.load_data.factory import RawDataLoaderFactory
from XBrainLab.backend.services.label_import_service import LabelImportService
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable


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

    def __init__(self, study):
        super().__init__()
        self.study = study
        self.label_service = LabelImportService()

    def get_loaded_data_list(self):
        """Return the list of currently loaded raw data objects.

        Returns:
            The list of raw data objects held by the study.
        """
        return self.study.loaded_data_list

    def is_locked(self):
        """Check if the dataset is locked.

        A dataset is locked when downstream operations (e.g. channel
        selection or epoching) have been applied.

        Returns:
            ``True`` if the dataset is locked, ``False`` otherwise.
        """
        return self.study.is_locked()

    def has_data(self):
        """Check whether any data has been loaded.

        Returns:
            ``True`` if the loaded data list is non-empty.
        """
        return bool(self.study.loaded_data_list)

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
        existing_data = []
        if self.study.loaded_data_list:
            existing_data = list(self.study.loaded_data_list)

        try:
            loader = RawDataLoader(existing_data)
        except Exception as e:
            # If existing dataset inconsistent
            raise ValueError(f"Existing dataset inconsistent: {e}") from e

        success_count = 0
        errors = []

        for path in filepaths:
            # Check duplicates
            if any(d.get_filepath() == path for d in loader):
                logger.info(f"Skipping duplicate: {path}")
                continue

            try:
                logger.info(f"Loading file: {path}")
                raw = RawDataLoaderFactory.load(path)

                if raw:
                    loader.append(raw)
                    success_count += 1
                else:
                    errors.append(f"{path}: Loader returned None.")

            except UnsupportedFormatError:
                logger.error(f"Unsupported format: {path}")
                errors.append(f"{path}: Unsupported format.")
            except FileCorruptedError:
                logger.error(f"File corrupted: {path}")
                errors.append(f"{path}: File corrupted.")
            except Exception as e:
                logger.error(f"Error loading {path}: {e}")
                errors.append(f"{path}: {e!s}")

        if success_count > 0:
            loader.apply(self.study, force_update=True)
            self.notify("data_changed")

        self.notify("import_finished", success_count, errors)

        return success_count, errors

    def clean_dataset(self):
        """Clear all loaded data and notify observers."""
        self.study.clean_raw_data(force_update=True)
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
        current_list = self.study.loaded_data_list
        if not current_list:
            return

        # Sort indices in descending order to avoid shifting issues
        indices = sorted(indices, reverse=True)
        new_list = list(current_list)

        changed = False
        for idx in indices:
            if 0 <= idx < len(new_list):
                del new_list[idx]
                changed = True

        if changed:
            # Directly update study state
            self.study.set_loaded_data_list(new_list, force_update=True)
            self.notify("data_changed")

    def run_import_labels(
        self, target_files, label_map, file_mapping, mapping, selected_event_names=None
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
        count = self.label_service.apply_labels_batch(
            target_files, label_map, file_mapping, mapping, selected_event_names
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
        total_events = 0
        unique_events = set()

        for data in self.study.loaded_data_list:
            mne_data = data.get_mne()
            if hasattr(mne_data, "annotations") and mne_data.annotations:
                total_events += len(mne_data.annotations)
                unique_events.update(set(mne_data.annotations.description))

        return {
            "total": total_events,
            "unique_count": len(unique_events),
            "unique_labels": sorted(unique_events),
        }

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
            data = current_list[index]
            if subject is not None:
                data.set_subject_name(subject)
            if session is not None:
                data.set_session_name(session)

            # Sync to study to trigger updates if necessary
            # (often metadata-only doesn't strictly require it,
            # but resetting preprocess ensures consistency)
            self.study.reset_preprocess(force_update=True)

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
        data_list = self.study.loaded_data_list
        count = 0
        for data in data_list:
            path = data.get_filepath()
            if path in results:
                sub, sess = results[path]
                if sub != "-":
                    data.set_subject_name(sub)
                if sess != "-":
                    data.set_session_name(sess)
                count += 1

        if count > 0:
            self.reset_preprocess()

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
        data_list = self.study.loaded_data_list
        process = preprocessor.ChannelSelection(data_list)

        try:
            # Performs processing
            result = process.data_preprocess(selected_channels)
        except Exception as e:
            logger.error(f"Channel selection failed: {e}")
            raise

        # Apply changes
        self.study.backup_loaded_data()
        self.study.set_loaded_data_list(result, force_update=True)
        self.study.lock_dataset()
        self.notify("data_changed")
        self.notify("dataset_locked", True)
        return True

    def get_filenames(self):
        """Return a list of file paths for all loaded data.

        Returns:
            List of file path strings.
        """
        return [d.get_filepath() for d in self.study.loaded_data_list]

    def reset_preprocess(self):
        """Reset downstream preprocessing and unlock the dataset."""
        self.study.reset_preprocess(force_update=True)
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
        data_list = self.study.loaded_data_list
        return [data_list[i] for i in indices if 0 <= i < len(data_list)]

    def apply_labels_batch(
        self, target_files, label_map, file_mapping, mapping, selected_event_names
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
        count = self.label_service.apply_labels_batch(
            target_files, label_map, file_mapping, mapping, selected_event_names
        )
        if count > 0:
            self.reset_preprocess()
        return count

    def apply_labels_legacy(
        self, target_files, labels, mapping, selected_event_names, force_import=False
    ):
        """Apply labels using the legacy import path.

        Args:
            target_files: Data objects to receive the labels.
            labels: Raw label data to apply.
            mapping: Column/field mapping configuration.
            selected_event_names: Event names to include during import.
            force_import: If ``True``, bypass validation checks.

        Returns:
            The number of files successfully updated.
        """
        count = self.label_service.apply_labels_legacy(
            target_files,
            labels,
            mapping,
            selected_event_names,
            force_import=force_import,
        )
        if count > 0:
            self.reset_preprocess()
        return count

    def get_epoch_count(self, data, event_names):
        """Get the number of epochs for a file given the target events.

        Args:
            data: A raw data object to inspect.
            event_names: Sequence of event name strings to count.

        Returns:
            The number of epochs that would be produced.
        """
        return self.label_service.get_epoch_count_for_file(data, event_names)

    def get_smart_filter_suggestions(self, data, target_count):
        """Return suggested event IDs for filtering based on a target count.

        Args:
            data: A raw data object to inspect.
            target_count: Desired number of epochs after filtering.

        Returns:
            Suggested event IDs suitable for reaching *target_count*.
        """
        loader = EventLoader(data)
        return loader.smart_filter(target_count)
