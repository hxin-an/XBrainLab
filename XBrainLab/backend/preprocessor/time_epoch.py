"""Preprocessor for segmenting continuous EEG into time-locked epochs."""

import mne
import numpy as np

from ..load_data import Raw
from .base import PreprocessBase
from .normalize import Normalize


class TimeEpoch(PreprocessBase):
    """Segments continuous (raw) EEG data into time-locked epochs.

    Extracts fixed-length time windows around event markers. Supports
    baseline correction and event selection. Only applicable to raw
    (non-epoched) data that contains event markers.
    """

    def check_data(self):
        """Validates that data is raw and contains event markers.

        Raises:
            ValueError: If data is already epoched or has no event markers.

        """
        super().check_data()
        sampling_frequencies = [
            float(data.get_sfreq()) for data in self.preprocessed_data_list
        ]
        if sampling_frequencies and not np.allclose(
            sampling_frequencies,
            sampling_frequencies[0],
            rtol=1e-9,
            atol=1e-9,
        ):
            distinct_frequencies = sorted(set(sampling_frequencies))
            frequencies = ", ".join(
                f"{frequency:g} Hz" for frequency in distinct_frequencies
            )
            raise ValueError(
                "Loaded EEG files use different sampling frequencies "
                f"({frequencies}). Resample them to one shared rate before "
                "creating epochs."
            )
        for preprocessed_data in self.preprocessed_data_list:
            if not preprocessed_data.is_raw():
                raise ValueError("Only raw data can be epoched, got epochs")
            _, event_id = preprocessed_data.get_event_list()
            if not event_id:
                raise ValueError(
                    f"No event markers found for {preprocessed_data.get_filename()}",
                )

    def get_preprocess_desc(
        self,
        baseline: list | tuple | None,
        selected_event_names: list | None,
        tmin: float,
        tmax: float,
    ):
        """Returns a description of the time-epoch step.

        Args:
            baseline: Baseline correction window as ``(start, end)`` in
                seconds, or ``None`` for no baseline correction.
            selected_event_names: List of event names to include.
            tmin: Epoch start time relative to event onset, in seconds.
            tmax: Epoch end time relative to event onset, in seconds.

        Returns:
            A string describing the epoching parameters.

        """
        return f"Epoching {tmin} ~ {tmax} by event ({baseline} baseline)"

    def data_preprocess(
        self,
        baseline: list | tuple | None,
        selected_event_names: list | None,
        tmin: float,
        tmax: float,
    ) -> list[Raw]:
        """Create epochs, then apply any leakage-safe normalization request."""
        result = super().data_preprocess(
            baseline,
            selected_event_names,
            tmin,
            tmax,
        )
        for preprocessed_data in result:
            Normalize.apply_pending_epoch_normalization(preprocessed_data)
        return result

    def _data_preprocess(
        self,
        preprocessed_data: Raw,
        baseline: list | tuple | None,
        selected_event_names: list | None,
        tmin: float,
        tmax: float,
    ):
        """Segments a single raw data instance into time-locked epochs.

        Args:
            preprocessed_data: The raw data instance to epoch.
            baseline: Baseline correction window, or ``None``.
            selected_event_names: Event names to include, or ``None``
                to include all.
            tmin: Epoch start time relative to event onset, in seconds.
            tmax: Epoch end time relative to event onset, in seconds.

        Raises:
            ValueError: If no matching events are found or the data is
                already epoched.

        """
        raw_events, raw_event_id = preprocessed_data.get_event_list()

        selected_event_id = {}
        if selected_event_names is None:
            # If None, select all available events
            selected_event_id = raw_event_id.copy()
        else:
            for event_name in selected_event_names:
                if event_name in raw_event_id:
                    selected_event_id[event_name] = raw_event_id[event_name]

        selection_mask = np.zeros(raw_events.shape[0], dtype=bool)
        for event_id in selected_event_id.values():
            selection_mask = np.logical_or(
                selection_mask,
                raw_events[:, -1] == event_id,
            )
        selected_events = raw_events[selection_mask]

        if len(selected_events) == 0:
            available = list(raw_event_id.keys())
            raise ValueError(
                f"No event markers found. Selected: {selected_event_names}. "
                f"Available: {available}",
            )

        if not preprocessed_data.is_raw():
            raise ValueError(
                "Data is already epoched. Cannot perform TimeEpoch on epoched data.",
            )

        mne_raw = preprocessed_data.get_mne()
        boundary_drop_count = self._boundary_drop_count(
            mne_raw,
            selected_events,
            tmin=tmin,
            tmax=tmax,
        )
        if boundary_drop_count:
            suffix = "" if boundary_drop_count == 1 else "s"
            raise ValueError(
                f"Epoch window {tmin} to {tmax} seconds exceeds recording "
                f"bounds for {boundary_drop_count} selected event{suffix}. "
                "Shorten the epoch window before creating epochs."
            )

        data = mne.Epochs(
            mne_raw,
            selected_events,
            event_id=selected_event_id,
            tmin=tmin,
            tmax=tmax,
            baseline=baseline,
            preload=True,
            event_repeated="drop",
        )
        if len(data) == 0:
            raise ValueError(
                "No usable epochs remain after MNE rejected the selected "
                "events. Adjust the epoch window or review bad annotations "
                "before creating epochs."
            )

        # FIX: Clear raw events to prevent set_mne from overwriting the correct
        # epoch events with the original (larger) raw events list.
        preprocessed_data.raw_events = None
        preprocessed_data.raw_event_id = None

        preprocessed_data.set_mne(data)

    @staticmethod
    def _boundary_drop_count(
        mne_raw,
        selected_events: np.ndarray,
        *,
        tmin: float,
        tmax: float,
    ) -> int:
        """Count selected events whose fixed window exceeds recording bounds."""
        sfreq = float(mne_raw.info["sfreq"])
        start_offset = round(float(tmin) * sfreq)
        stop_offset = round(float(tmax) * sfreq)
        first_sample = int(mne_raw.first_samp)
        last_sample = int(mne_raw.last_samp)
        event_samples = selected_events[:, 0].astype(int, copy=False)
        outside = (event_samples + start_offset < first_sample) | (
            event_samples + stop_offset > last_sample
        )
        return int(np.count_nonzero(outside))
