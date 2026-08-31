"""Preprocessor for resampling EEG data to a new sampling frequency."""

import mne
import numpy as np

from ..load_data import Raw
from .base import PreprocessBase


class Resample(PreprocessBase):
    """Resamples EEG data to a target sampling frequency.

    For raw (continuous) data, event sample indices are rescaled
    proportionally after resampling. For epoched data, MNE's built-in
    epoch resampling is used.
    """

    def get_preprocess_desc(self, sfreq: float):
        """Returns a description of the resampling step.

        Args:
            sfreq: Target sampling frequency in Hz.

        Returns:
            A string describing the resampling operation.

        """
        return f"Resample to {sfreq}Hz"

    def _data_preprocess(self, preprocessed_data: Raw, sfreq: float):
        """Resamples a single data instance to the target frequency.

        Args:
            preprocessed_data: The data instance to preprocess.
            sfreq: Target sampling frequency in Hz.

        """
        mne_data = preprocessed_data.get_mne()
        mne_data.load_data()
        self._require_finite_input(preprocessed_data)
        if isinstance(mne_data, mne.io.BaseRaw):
            events, event_id = preprocessed_data.get_event_list()
            old_sfreq = preprocessed_data.get_sfreq()

            mne_data.resample(sfreq=sfreq)
            preprocessed_data.set_mne(mne_data)

            if len(events) > 0:
                ratio = sfreq / old_sfreq
                new_events = events.copy()
                # Resample sample indices (column 0)
                new_events[:, 0] = np.round(new_events[:, 0] * ratio).astype(int)
                preprocessed_data.set_event(new_events, event_id)
        else:
            mne_data.resample(sfreq=sfreq)
            preprocessed_data.set_mne_and_wipe_events(mne_data)

    @staticmethod
    def _require_finite_input(preprocessed_data: Raw) -> None:
        """Reject non-finite input before FFT resampling contaminates all samples."""
        mne_data = preprocessed_data.get_mne()
        if isinstance(mne_data, mne.io.BaseRaw):
            channel_count = max(1, len(mne_data.ch_names))
            sample_chunk_size = max(1, 1_048_576 // channel_count)
            finite = all(
                np.isfinite(
                    mne_data.get_data(
                        start=start,
                        stop=min(start + sample_chunk_size, mne_data.n_times),
                    )
                ).all()
                for start in range(0, mne_data.n_times, sample_chunk_size)
            )
        else:
            epochs = mne_data.get_data(copy=False)
            finite = all(np.isfinite(epoch).all() for epoch in epochs)
        if finite:
            return
        raise ValueError(
            "Resampling requires finite EEG data. Remove the resampling step and "
            "keep this recording at its native sampling rate so BAD_nonfinite "
            "segments can be excluded during epoching, or select a recording "
            "without NaN or infinite samples. Raw FFT resampling can contaminate "
            "the complete recording."
        )
