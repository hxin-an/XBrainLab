"""Preprocessor for frequency-domain filtering of EEG data."""

import numpy as np

from ..load_data import Raw
from .base import PreprocessBase


class Filtering(PreprocessBase):
    """Applies bandpass and/or notch filtering to EEG data.

    Supports optional high-pass, low-pass, bandpass, and notch filtering
    using the underlying MNE filtering routines.
    """

    def get_preprocess_desc(self, l_freq: float, h_freq: float, notch_freqs=None):
        """Returns a description of the filtering step.

        Args:
            l_freq: Low cut-off frequency in Hz, or ``None`` for no
                high-pass.
            h_freq: High cut-off frequency in Hz, or ``None`` for no
                low-pass.
            notch_freqs: Frequency or array of frequencies (Hz) to notch
                filter, or ``None`` to skip notch filtering.

        Returns:
            A human-readable string describing the applied filters.

        """
        desc_parts = []
        if l_freq is not None or h_freq is not None:
            desc_parts.append(f"Filtering {l_freq} ~ {h_freq} Hz")

        if notch_freqs:
            desc_parts.append(f"Notch {notch_freqs} Hz")

        return ", ".join(desc_parts)

    def _data_preprocess(
        self,
        preprocessed_data: Raw,
        l_freq: float,
        h_freq: float,
        notch_freqs=None,
    ):
        """Applies frequency filtering to a single data instance.

        Args:
            preprocessed_data: The data instance to preprocess.
            l_freq: Low cut-off frequency in Hz, or ``None``.
            h_freq: High cut-off frequency in Hz, or ``None``.
            notch_freqs: Frequency or array of frequencies (Hz) to notch
                filter, or ``None`` to skip.

        """
        preprocessed_data.get_mne().load_data()
        mne_data = preprocessed_data.get_mne()

        # Apply Bandpass
        if l_freq is not None or h_freq is not None:
            mne_data = mne_data.filter(l_freq=l_freq, h_freq=h_freq)

        # Apply Notch
        if notch_freqs is not None:
            if isinstance(notch_freqs, (int, float)):
                notch_freqs = np.array([notch_freqs])
            mne_data = mne_data.notch_filter(freqs=notch_freqs)

        preprocessed_data.set_mne(mne_data)
