"""Preprocessor for segmenting continuous EEG into time-locked epochs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import mne
import numpy as np

from ..load_data import Raw
from .base import PreprocessBase
from .normalize import Normalize


@dataclass(frozen=True)
class EpochBoundarySummary:
    """Describe selected events whose requested window exceeds a recording."""

    selected_event_count: int
    excluded_event_count: int
    affected_recording_count: int
    recording_count: int

    @property
    def remaining_event_count(self) -> int:
        return self.selected_event_count - self.excluded_event_count

    @property
    def excluded_ratio(self) -> float:
        if not self.selected_event_count:
            return 0.0
        return self.excluded_event_count / self.selected_event_count

    def to_diagnostics(self) -> dict[str, int | float]:
        return {
            "selected_event_count": self.selected_event_count,
            "excluded_event_count": self.excluded_event_count,
            "remaining_event_count": self.remaining_event_count,
            "affected_recording_count": self.affected_recording_count,
            "recording_count": self.recording_count,
            "excluded_ratio": self.excluded_ratio,
        }


def summarize_epoch_boundaries(
    data_list: list[Any],
    selected_event_names: list[str] | dict[str, int] | None,
    *,
    tmin: float,
    tmax: float,
) -> EpochBoundarySummary:
    """Count selected events that cannot contain the requested epoch window."""
    selected_total = 0
    excluded_total = 0
    affected_recordings = 0
    requested_names = (
        set(selected_event_names)
        if isinstance(selected_event_names, (list, dict))
        else None
    )

    for data in data_list:
        events, event_id = data.get_event_list()
        event_array = np.asarray(events)
        if event_array.ndim != 2 or event_array.shape[1] < 3:
            continue
        selected_codes = {
            int(code)
            for name, code in event_id.items()
            if requested_names is None or str(name) in requested_names
        }
        if not selected_codes:
            continue
        selected = event_array[
            np.isin(event_array[:, -1].astype(int, copy=False), list(selected_codes))
        ]
        selected_total += len(selected)
        if not len(selected):
            continue
        raw = data.get_mne()
        excluded = TimeEpoch._boundary_drop_count(
            raw,
            selected,
            tmin=tmin,
            tmax=tmax,
        )
        excluded_total += excluded
        affected_recordings += int(excluded > 0)

    return EpochBoundarySummary(
        selected_event_count=selected_total,
        excluded_event_count=excluded_total,
        affected_recording_count=affected_recordings,
        recording_count=len(data_list),
    )


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
        allow_boundary_drop: bool = False,
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
        suffix = (
            "; excluded boundary events after safety review"
            if allow_boundary_drop
            else ""
        )
        return f"Epoching {tmin} ~ {tmax} by event ({baseline} baseline){suffix}"

    def data_preprocess(
        self,
        baseline: list | tuple | None,
        selected_event_names: list | None,
        tmin: float,
        tmax: float,
        allow_boundary_drop: bool = False,
    ) -> list[Raw]:
        """Create epochs, then apply any leakage-safe normalization request."""
        result = super().data_preprocess(
            baseline,
            selected_event_names,
            tmin,
            tmax,
            allow_boundary_drop,
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
        allow_boundary_drop: bool = False,
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
        if boundary_drop_count and not allow_boundary_drop:
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
