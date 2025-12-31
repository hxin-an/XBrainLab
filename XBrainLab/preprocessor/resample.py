from ..load_data import Raw
from .base import PreprocessBase
import numpy as np


class Resample(PreprocessBase):
    """Preprocessing class for resampling data.

    Input:
        sfreq: Sampling frequency.
    """

    def get_preprocess_desc(self, sfreq: float):
        return f"Resample to {sfreq}"

    def _data_preprocess(self, preprocessed_data: Raw, sfreq: float):
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
