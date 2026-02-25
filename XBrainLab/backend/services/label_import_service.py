"""Label import service for applying external labels to loaded EEG data files."""

from typing import Any

import numpy as np

from XBrainLab.backend.load_data import EventLoader
from XBrainLab.backend.utils.logger import logger


class LabelImportService:
    """Service for handling label import operations.

    Encapsulates logic for mapping label files to data files, filtering
    and synchronizing events, and applying labels to ``Raw`` objects.
    Supports batch mapping, sequential legacy mode, and force-import mode.
    """

    def apply_labels_batch(
        self,
        target_files: list[Any],
        label_map: dict[str, list[int]],
        file_mapping: dict[str, str],
        mapping: dict[int, str],
        selected_event_names: set[str] | None = None,
    ) -> int:
        """Apply labels to multiple files based on a file-to-label mapping.

        Args:
            target_files: List of Raw data objects to label.
            label_map: Mapping from label filename to its label array.
            file_mapping: Mapping from data filepath to label filename.
            mapping: Mapping from numeric label code to human-readable name.
            selected_event_names: Optional set of event names to filter by.

        Returns:
            Number of files successfully updated.
        """
        matched_count = 0

        for data in target_files:
            data_path = data.get_filepath()
            if data_path in file_mapping:
                label_fname = file_mapping[data_path]
                if label_fname in label_map:
                    matched_labels = label_map[label_fname]
                    try:
                        self.apply_labels_to_single_file(
                            data, matched_labels, mapping, selected_event_names
                        )
                        matched_count += 1
                    except Exception as e:
                        logger.error(
                            f"Error applying labels to {data_path}: {e}", exc_info=True
                        )
                        # Log error and continue to process remaining files.

        return matched_count

    def apply_labels_legacy(
        self,
        target_files: list[Any],
        labels: list[int],
        mapping: dict[int, str],
        selected_event_names: set[str] | None = None,
        force_import: bool = False,
    ) -> int:
        """Apply a flat label list sequentially across multiple files.

        Distributes labels based on each file's epoch count. Falls back
        to force-import mode if a count mismatch occurs and ``force_import``
        is True.

        Args:
            target_files: List of Raw data objects.
            labels: Flat list of labels to distribute.
            mapping: Mapping from numeric label code to human-readable name.
            selected_event_names: Optional set of event names to filter by.
            force_import: If True, ignore mismatches and force application.

        Returns:
            Number of files successfully updated, or 0 on mismatch
            without force.
        """
        label_count = len(labels)
        total_epochs = sum(
            self.get_epoch_count_for_file(d, selected_event_names) for d in target_files
        )

        if label_count == total_epochs and total_epochs > 0:
            current_idx = 0
            for data in target_files:
                n = self.get_epoch_count_for_file(data, selected_event_names)
                file_labels = labels[current_idx : current_idx + n]
                current_idx += n

                if n > 0:
                    self.apply_labels_to_single_file(
                        data, file_labels, mapping, selected_event_names
                    )
            return len(target_files)

        elif force_import:
            # Force Import Logic
            current_idx = 0
            applied_count = 0
            for data in target_files:
                # In force mode, we might not trust the filter, but let's try to
                # estimate size or just take chunks. The original UI logic used
                # get_epoch_count_for_file(data, None)
                n = self.get_epoch_count_for_file(data, None)
                if n == 0:
                    n = 100  # Default fallback from original code

                if current_idx + n <= len(labels):
                    file_labels = labels[current_idx : current_idx + n]
                    current_idx += n

                    self._force_apply_single(
                        data, file_labels, mapping, selected_event_names
                    )
                    applied_count += 1
            return applied_count

        else:
            # Mismatch and not forced
            return 0

    def apply_labels_to_single_file(
        self,
        data: Any,
        labels: list[Any],
        mapping: dict[int, str],
        selected_event_names: set[str] | None = None,
    ):
        """Apply labels to a single data object.

        Detects whether labels are in Timestamp Mode (list of dicts) or
        Sequence Mode (list of ints) and delegates accordingly.

        Args:
            data: Raw data object to apply labels to.
            labels: Labels to apply (ints for Sequence, dicts for Timestamp).
            mapping: Mapping from numeric label code to human-readable name.
            selected_event_names: Optional set of event names to filter by
                when creating events in Sequence Mode.
        """
        logger.info(
            f"Applying labels to {data.get_filename()}. Label count: {len(labels)}"
        )

        loader = EventLoader(data)
        loader.label_list = list(labels)  # type: ignore[assignment]

        # Check Mode
        is_timestamp_mode = (
            isinstance(labels, list) and len(labels) > 0 and isinstance(labels[0], dict)
        )

        if is_timestamp_mode:
            # Timestamp Mode: No filtering needed, just create events
            loader.create_event(mapping)
        else:
            # Sequence Mode: Handle filtering if names provided
            selected_ids = None
            if selected_event_names is not None and data.is_raw():
                _, event_id_map = data.get_event_list()
                if event_id_map:
                    selected_ids = [
                        eid
                        for name, eid in event_id_map.items()
                        if name in selected_event_names
                    ]
                    logger.info(
                        f"Filtered IDs for {data.get_filename()}: {selected_ids} "
                        f"(from names: {selected_event_names})"
                    )

            loader.create_event(mapping, selected_event_ids=selected_ids)

        loader.apply()
        data.set_labels_imported(True)
        logger.info(f"Successfully applied labels to {data.get_filename()}")

    def _force_apply_single(
        self,
        data: Any,
        labels: list[int],
        mapping: dict[int, str],
        selected_event_names: set[str] | None = None,
    ):
        """Force-apply labels to a single data object without validation.

        Args:
            data: Raw data object to apply labels to.
            labels: Integer labels to force-apply.
            mapping: Mapping from numeric label code to human-readable name.
            selected_event_names: Optional set of event names to filter by.
        """
        loader = EventLoader(data)
        loader.label_list = list(labels)  # type: ignore[assignment]

        # Handle filtering if names provided
        selected_ids = None
        if selected_event_names is not None and data.is_raw():
            _, event_id_map = data.get_event_list()
            if event_id_map:
                selected_ids = [
                    eid
                    for name, eid in event_id_map.items()
                    if name in selected_event_names
                ]
                logger.info(
                    f"Force Import: Filtered IDs for {data.get_filename()}: "
                    f"{selected_ids}"
                )

        loader.create_event(mapping, selected_event_ids=selected_ids)
        loader.apply()

        data.set_labels_imported(True)

    def get_epoch_count_for_file(
        self, data: Any, selected_event_names: set[str] | None
    ) -> int:
        """Calculate the number of epochs or events in a file matching a filter.

        Args:
            data: Raw data object to inspect.
            selected_event_names: Optional set of event names to count.
                If None, all events are counted.

        Returns:
            Number of matching epochs or events.
        """
        if data.is_raw():
            events, event_id_map = data.get_event_list()
            if selected_event_names is not None and event_id_map:
                relevant_ids = [
                    eid
                    for name, eid in event_id_map.items()
                    if name in selected_event_names
                ]
                if relevant_ids:
                    mask = np.isin(events[:, -1], relevant_ids)
                    return int(np.sum(mask))
                return 0
            return len(events)
        else:
            return data.get_epochs_length()
