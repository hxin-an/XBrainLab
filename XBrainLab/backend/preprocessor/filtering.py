from ..load_data import Raw
from .base import PreprocessBase


class Filtering(PreprocessBase):
    """Preprocessing class for filtering data.

    Input:
        l_freq: Low frequency.
        h_freq: High frequency.
    """

    def get_preprocess_desc(self, l_freq: float, h_freq: float, notch_freqs=None):
        desc_parts = []
        if l_freq is not None or h_freq is not None:
            desc_parts.append(f"Filtering {l_freq} ~ {h_freq} Hz")

        if notch_freqs:
            desc_parts.append(f"Notch {notch_freqs} Hz")

        return ", ".join(desc_parts)

    def _data_preprocess(self, preprocessed_data: Raw, l_freq: float, h_freq: float, notch_freqs=None):
        preprocessed_data.get_mne().load_data()
        mne_data = preprocessed_data.get_mne()

        # Apply Bandpass
        if l_freq is not None or h_freq is not None:
            mne_data = mne_data.filter(l_freq=l_freq, h_freq=h_freq)

        # Apply Notch
        if notch_freqs is not None:
            import numpy as np
            if isinstance(notch_freqs, (int, float)):
                notch_freqs = np.array([notch_freqs])
            mne_data = mne_data.notch_filter(freqs=notch_freqs)

        preprocessed_data.set_mne(mne_data)
