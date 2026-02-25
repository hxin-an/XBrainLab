"""Preprocessor for EEG data normalization."""

import numpy as np

from .base import PreprocessBase


class Normalize(PreprocessBase):
    """Normalizes EEG data channel-wise.

    Supports two normalization methods:

    * **z score** — subtracts the channel mean and divides by the channel
      standard deviation. For epoched data this is computed per trial.
    * **minmax** — scales each channel to the [0, 1] range. For epoched
      data this is computed per trial.
    """

    def get_preprocess_desc(self, norm: str):
        """Returns a description of the normalization step.

        Args:
            norm: Normalization method (``"z score"`` or ``"minmax"``).

        Returns:
            A string describing the normalization applied.
        """
        return f"{norm} normalization"

    def _data_preprocess(self, preprocessed_data, norm: str):
        """Applies normalization to a single data instance.

        Args:
            preprocessed_data: The data instance to preprocess.
            norm: Normalization method (``"z score"`` or ``"minmax"``).
        """
        preprocessed_data.get_mne().load_data()
        # Normalize variant names (accept 'z-score', 'z score', 'zscore')
        norm_key = norm.lower().replace("-", " ").replace("_", " ").strip()
        if norm_key == "z score":
            if preprocessed_data.is_raw():
                arrdata = preprocessed_data.get_mne()._data.copy()
                preprocessed_data.get_mne()._data = (
                    arrdata
                    - np.multiply(arrdata.mean(axis=-1)[:, None], np.ones_like(arrdata))
                ) / np.multiply(
                    arrdata.std(axis=-1)[:, None] + 1e-12,
                    np.ones_like(arrdata),
                )
            else:
                arrdata = preprocessed_data.get_mne()._data.copy()
                for ep in range(preprocessed_data.get_epochs_length()):
                    trial_mean, trial_std = (
                        arrdata[ep, :, :].mean(axis=-1),
                        arrdata[ep, :, :].std(axis=-1),
                    )
                    arrdata[ep, :, :] = (
                        arrdata[ep, :, :]
                        - np.multiply(
                            trial_mean[:, None], np.ones_like(arrdata[ep, :, :])
                        )
                    ) / np.multiply(
                        trial_std[:, None] + 1e-12,
                        np.ones_like(arrdata[ep, :, :]),
                    )
                preprocessed_data.get_mne()._data = arrdata
        elif norm_key == "minmax":
            if preprocessed_data.is_raw():
                arrdata = preprocessed_data.get_mne()._data.copy()
                ch_min, ch_max = (
                    np.multiply(arrdata.min(axis=-1)[:, None], np.ones_like(arrdata)),
                    np.multiply(arrdata.max(axis=-1)[:, None], np.ones_like(arrdata)),
                )
                arrdata = (arrdata - ch_min) / (ch_max - ch_min + 1e-12)
                preprocessed_data.get_mne()._data = arrdata
            else:
                arrdata = preprocessed_data.get_mne()._data.copy()
                for ep in range(preprocessed_data.get_epochs_length()):
                    ch_min = np.multiply(
                        arrdata[ep, :, :].min(axis=-1)[:, None],
                        np.ones_like(arrdata[ep, :, :]),
                    )
                    ch_max = np.multiply(
                        arrdata[ep, :, :].max(axis=-1)[:, None],
                        np.ones_like(arrdata[ep, :, :]),
                    )
                    arrdata[ep, :, :] = (arrdata[ep, :, :] - ch_min) / (
                        ch_max - ch_min + 1e-12
                    )
                preprocessed_data.get_mne()._data = arrdata
        else:
            raise ValueError(
                f"Unknown normalization method: '{norm}'. "
                f"Supported methods are 'z score' and 'minmax'."
            )
