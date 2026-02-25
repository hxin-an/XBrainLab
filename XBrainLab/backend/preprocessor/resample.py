"""Preprocessor for resampling EEG data to a new sampling frequency."""

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
        preprocessed_data.get_mne().load_data()
        if preprocessed_data.is_raw():
            events, event_id = preprocessed_data.get_event_list()
            old_sfreq = preprocessed_data.get_sfreq()

            # MNE resample modifies in-place and returns the instance (usually)
            # It does NOT reliably return (inst, events) tuple across versions/methods
            # So we manually resample events if they exist

            # So we manually resample events if they exist

            new_mne = preprocessed_data.get_mne().resample(sfreq=sfreq, events=None)
            preprocessed_data.set_mne(new_mne)

            if len(events) > 0:
                ratio = sfreq / old_sfreq
                new_events = events.copy()
                # Resample sample indices (column 0)
                new_events[:, 0] = np.round(new_events[:, 0] * ratio).astype(int)
                preprocessed_data.set_event(new_events, event_id)
        else:
            new_mne = preprocessed_data.get_mne().resample(sfreq=sfreq)
            preprocessed_data.set_mne_and_wipe_events(new_mne)
