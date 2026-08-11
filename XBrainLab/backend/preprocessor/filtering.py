"""Preprocessor for frequency-domain filtering of EEG data."""

from __future__ import annotations

import mne
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
        finite_sample_mask = self._prepare_nonfinite_samples(
            preprocessed_data,
            mne_data,
        )

        # Apply Bandpass
        if l_freq is not None or h_freq is not None:
            if isinstance(mne_data, mne.io.BaseRaw):
                mne_data.filter(
                    l_freq=l_freq,
                    h_freq=h_freq,
                    skip_by_annotation=("edge", "bad"),
                )
            else:
                mne_data.filter(l_freq=l_freq, h_freq=h_freq)

        # Apply Notch
        if notch_freqs is not None:
            if isinstance(notch_freqs, (int, float)):
                notch_freqs = np.array([notch_freqs])
            if not isinstance(mne_data, mne.io.BaseRaw):
                raise AttributeError(
                    f"'{type(mne_data).__name__}' object has no attribute "
                    "'notch_filter'"
                )
            mne_data.notch_filter(
                freqs=notch_freqs,
                skip_by_annotation=("edge", "bad"),
            )

        if finite_sample_mask is not None:
            filtered = self._materialized_data(mne_data)
            if any(
                not np.isfinite(channel[finite_sample_mask]).all()
                for channel in filtered
            ):
                raise ValueError(
                    "EEG filtering produced NaN or infinite values outside "
                    "the preserved non-finite source segments."
                )

        preprocessed_data.set_mne(mne_data)

    @classmethod
    def _prepare_nonfinite_samples(
        cls,
        preprocessed_data: Raw,
        mne_data: mne.io.BaseRaw | mne.BaseEpochs,
    ) -> np.ndarray | None:
        data = cls._materialized_data(mne_data)
        if not isinstance(mne_data, mne.io.BaseRaw):
            if cls._all_finite(data):
                return None
            raise ValueError(
                "Epoched EEG data contains NaN or infinite values. Review the "
                "source channel selection and preprocessing before filtering."
            )

        finite_sample_mask = np.ones(data.shape[1], dtype=bool)
        channels_with_nonfinite: list[str] = []
        for name, channel in zip(mne_data.ch_names, data, strict=True):
            channel_finite = np.isfinite(channel)
            if not channel_finite.all():
                channels_with_nonfinite.append(name)
                finite_sample_mask &= channel_finite
        if not channels_with_nonfinite:
            return None
        if not finite_sample_mask.any():
            raise ValueError(
                "EEG recording has no samples where every selected channel is "
                "finite. Review channel selection before filtering."
            )

        spans = cls._contiguous_false_spans(finite_sample_mask)
        cls._replace_nonfinite_annotations(mne_data, spans)
        detail = {
            "status": "preserved_as_bad_annotations",
            "annotation": "BAD_nonfinite",
            "segment_count": len(spans),
            "sample_count": int(np.count_nonzero(~finite_sample_mask)),
            "channels_with_nonfinite": channels_with_nonfinite,
        }
        preprocessed_data.set_runtime_detail("filter_nonfinite_segments", detail)
        preprocessed_data.add_runtime_signal(
            "Non-finite source samples were preserved as BAD_nonfinite segments "
            "and excluded from filtering and epoch materialization."
        )
        return finite_sample_mask

    @staticmethod
    def _materialized_data(
        mne_data: mne.io.BaseRaw | mne.BaseEpochs,
    ) -> np.ndarray:
        data = getattr(mne_data, "_data", None)
        if isinstance(data, np.ndarray):
            return data
        materialized = mne_data.get_data()
        if not isinstance(materialized, np.ndarray):
            raise TypeError("MNE data materialization did not return an array.")
        return materialized

    @staticmethod
    def _all_finite(data: np.ndarray) -> bool:
        flat = data.reshape(-1)
        chunk_size = 1_048_576
        return all(
            np.isfinite(flat[start : start + chunk_size]).all()
            for start in range(0, flat.size, chunk_size)
        )

    @staticmethod
    def _contiguous_false_spans(mask: np.ndarray) -> list[tuple[int, int]]:
        padded = np.pad(mask.astype(np.int8), (1, 1), constant_values=1)
        transitions = np.diff(padded)
        starts = np.flatnonzero(transitions == -1)
        stops = np.flatnonzero(transitions == 1)
        return [
            (int(start), int(stop)) for start, stop in zip(starts, stops, strict=True)
        ]

    @staticmethod
    def _replace_nonfinite_annotations(
        mne_data: mne.io.BaseRaw,
        spans: list[tuple[int, int]],
    ) -> None:
        annotations = mne_data.annotations.copy()
        existing = [
            index
            for index, description in enumerate(annotations.description)
            if str(description).casefold() == "bad_nonfinite"
        ]
        if existing:
            annotations.delete(existing)

        sfreq = float(mne_data.info["sfreq"])
        nonfinite = mne.Annotations(
            onset=[mne_data.first_time + start / sfreq for start, _ in spans],
            duration=[(stop - start) / sfreq for start, stop in spans],
            description=["BAD_nonfinite"] * len(spans),
            orig_time=annotations.orig_time,
        )
        mne_data.set_annotations(annotations + nonfinite)
