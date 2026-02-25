"""Preprocessing controller for EEG signal processing operations.

Provides a high-level interface for filtering, resampling,
re-referencing, normalisation, epoching, and montage configuration.
"""

from XBrainLab.backend import preprocessor
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable


class PreprocessController(Observable):
    """Controller for managing preprocessing operations.

    Orchestrates EEG signal processing steps including filtering,
    resampling, re-referencing, normalisation, epoching, and montage
    configuration. All operations work on deep copies of the data to
    ensure thread safety, then atomically swap results back into the
    study.

    Events:
        preprocess_changed: Emitted when the preprocessing state
            changes (e.g. after a filter, resample, or epoch).

    Attributes:
        study: Reference to the :class:`Study` backend instance.

    """

    def __init__(self, study):
        """Initialise the preprocessing controller.

        Args:
            study: The :class:`Study` backend instance to operate on.

        """
        Observable.__init__(self)
        self.study = study

    def get_preprocessed_data_list(self):
        """Return the list of currently preprocessed data objects.

        Returns:
            The preprocessed data list held by the study.

        """
        return self.study.preprocessed_data_list

    def reset_preprocess(self):
        """Reset all preprocessing back to the raw state."""
        self.study.reset_preprocess(force_update=True)
        self.notify("preprocess_changed")

    def is_epoched(self):
        """Check whether the data is currently epoched.

        Returns:
            ``True`` if the first preprocessed data object is epoched,
            ``False`` otherwise or if no data is loaded.

        """
        data_list = self.study.preprocessed_data_list
        if data_list:
            return not data_list[0].is_raw()
        return False

    def has_data(self):
        """Check whether any preprocessed data exists.

        Returns:
            ``True`` if the preprocessed data list is non-empty.

        """
        return bool(self.study.preprocessed_data_list)

    def get_channel_names(self):
        """Return channel names from the first preprocessed data object.

        Returns:
            List of channel name strings, or an empty list if no data
            is loaded.

        """
        if self.study.preprocessed_data_list:
            return self.study.preprocessed_data_list[0].get_mne().ch_names
        return []

    def get_first_data(self):
        """Return the first preprocessed data object.

        Returns:
            The first data object, or ``None`` if no data is loaded.

        """
        if self.study.preprocessed_data_list:
            return self.study.preprocessed_data_list[0]
        return None

    def _apply_processor(self, processor_class, *args, **kwargs):
        """Apply a preprocessing processor and update the study.

        Creates deep copies of the current preprocessed data, applies
        the given processor, and atomically swaps the result back.

        Args:
            processor_class: The preprocessor class to instantiate.
            *args: Positional arguments forwarded to
                ``processor.data_preprocess()``.
            **kwargs: Keyword arguments forwarded to
                ``processor.data_preprocess()``.

        Returns:
            ``True`` if the processor was applied successfully.

        Raises:
            ValueError: If no data is available for preprocessing.
            Exception: Propagated from the underlying processor on
                failure.

        """
        data_list = self.study.preprocessed_data_list
        if not data_list:
            raise ValueError("No data to preprocess.")

        try:
            # Thread-safe operations: Work on a Deep Copy of the data
            # This prevents race conditions where UI might be reading/plotting data
            # while the background thread is modifying it in-place.
            working_list = [d.copy() for d in data_list]

            processor = processor_class(working_list)

            # Apply preprocessing on the COPIES
            result = processor.data_preprocess(*args, **kwargs)

            # Atomic swap of the results back to the study
            # This update is safe because it replaces the list reference
            self.study.set_preprocessed_data_list(result, force_update=True)
            self.notify("preprocess_changed")
        except Exception as e:
            logger.error("Preprocessing failed: %s", e)
            raise
        return True

    def apply_filter(self, l_freq, h_freq, notch_freqs=None):
        """Apply band-pass and optional notch filtering.

        Args:
            l_freq: Low cut-off frequency in Hz (high-pass edge).
            h_freq: High cut-off frequency in Hz (low-pass edge).
            notch_freqs: Optional sequence of notch filter frequencies.

        Returns:
            ``True`` on success.

        Raises:
            ValueError: If no data is available.

        """
        return self._apply_processor(
            preprocessor.Filtering,
            l_freq,
            h_freq,
            notch_freqs=notch_freqs,
        )

    def apply_resample(self, sfreq):
        """Resample the data to a new sampling frequency.

        Args:
            sfreq: Target sampling frequency in Hz.

        Returns:
            ``True`` on success.

        Raises:
            ValueError: If no data is available.

        """
        return self._apply_processor(preprocessor.Resample, sfreq)

    def apply_rereference(self, ref_channels):
        """Apply re-referencing to the specified channels.

        Args:
            ref_channels: Channel name(s) to use as reference.

        Returns:
            ``True`` on success.

        Raises:
            ValueError: If no data is available.

        """
        return self._apply_processor(
            preprocessor.Rereference,
            ref_channels=ref_channels,
        )

    def apply_normalization(self, method):
        """Apply normalisation to the data.

        Args:
            method: Normalisation method identifier (e.g. ``"zscore"``).

        Returns:
            ``True`` on success.

        Raises:
            ValueError: If no data is available.

        """
        return self._apply_processor(preprocessor.Normalize, norm=method)

    def get_unique_events(self):
        """Return unique event names across all preprocessed files.

        Returns:
            A sorted list of unique event name strings.

        """
        events = set()
        for data in self.study.preprocessed_data_list:
            try:
                _, ev_ids = data.get_event_list()
                if ev_ids:
                    events.update(ev_ids.keys())
            except Exception as e:  # noqa: PERF203
                logger.warning("Failed to get events from preprocessed data: %s", e)
        return sorted(events)

    def apply_epoching(self, baseline, selected_events, tmin, tmax):
        """Apply epoching to the preprocessed data.

        Creates epochs around events of interest and locks the
        dataset to prevent further raw-data modifications.

        Args:
            baseline: Baseline correction tuple ``(start, end)``
                or ``None``.
            selected_events: Mapping of selected event names to IDs.
            tmin: Epoch start time relative to event onset (seconds).
            tmax: Epoch end time relative to event onset (seconds).

        Returns:
            ``True`` on success.

        Raises:
            ValueError: If no data is available.

        """
        result = self._apply_processor(
            preprocessor.TimeEpoch,
            baseline,
            selected_events,
            tmin,
            tmax,
        )
        if result:
            self.study.lock_dataset()
        return result

    def apply_montage(
        self,
        mapped_channels: list[str],
        mapped_positions: list[tuple[float, float, float]],
    ):
        """Applies montage configuration to the study.

        Args:
            mapped_channels: List of channel names.
            mapped_positions: List of pos tuples (x, y, z).

        """
        self.study.set_channels(mapped_channels, mapped_positions)
        # Notify UI about preprocessing change (montage affects visualization)
        self.notify("preprocess_changed")
        return True
