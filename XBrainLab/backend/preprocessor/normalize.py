"""Leakage-safe preprocessor for EEG data normalization."""

from __future__ import annotations

from ..application.owned_work import owned_work_checkpoint
from ..load_data import Raw
from .base import PreprocessBase

NORMALIZATION_RUNTIME_KEY = "normalization"
NORMALIZATION_SCOPE = "per_epoch_per_channel"
_EPSILON = 1e-12


class Normalize(PreprocessBase):
    """Normalize EEG epochs independently for each channel.

    Supports two normalization methods:

    * **z score** — subtracts the channel mean and divides by the channel
      standard deviation, computed independently for each epoch.
    * **minmax** — scales each channel to the [0, 1] range. For epoched
      data this is computed independently for each epoch.

    Raw recordings are not numerically normalized because fitting channel
    statistics across the whole recording can expose future validation or test
    samples to training epochs. A raw request is recorded and applied after
    epoch materialization, where every epoch is transformed without fitted
    cross-sample state.
    """

    def get_preprocess_desc(self, norm: str) -> str:
        """Returns a description of the normalization step.

        Args:
            norm: Normalization method (``"z score"`` or ``"minmax"``).

        Returns:
            A string describing the normalization applied.

        """
        return f"{self.canonical_method(norm)} normalization"

    def data_preprocess(self, norm: str) -> list[Raw]:
        """Queue raw requests or normalize already-epoched data."""
        canonical_method = self.canonical_method(norm)
        total = len(self.preprocessed_data_list)
        for index, preprocessed_data in enumerate(self.preprocessed_data_list):
            owned_work_checkpoint(
                "Normalizing EEG recordings",
                completed=index,
                total=total,
            )
            self._data_preprocess(preprocessed_data, canonical_method)
            if preprocessed_data.is_raw():
                description = (
                    f"{canonical_method} normalization requested "
                    "(deferred to per-epoch application)"
                )
            else:
                description = (
                    f"{canonical_method} normalization applied independently "
                    "per epoch and channel"
                )
            preprocessed_data.add_preprocess(description)
            owned_work_checkpoint(
                "Normalizing EEG recordings",
                completed=index + 1,
                total=total,
            )
        return self.preprocessed_data_list

    def _data_preprocess(self, preprocessed_data: Raw, norm: str) -> None:
        """Applies normalization to a single data instance.

        Args:
            preprocessed_data: The data instance to preprocess.
            norm: Normalization method (``"z score"`` or ``"minmax"``).

        """
        canonical_method = self.canonical_method(norm)
        if preprocessed_data.is_raw():
            preprocessed_data.set_runtime_detail(
                NORMALIZATION_RUNTIME_KEY,
                self._normalization_detail(
                    canonical_method,
                    status="pending",
                    requested_on="raw",
                ),
            )
            return

        self._normalize_epochs(preprocessed_data, canonical_method)
        preprocessed_data.set_runtime_detail(
            NORMALIZATION_RUNTIME_KEY,
            self._normalization_detail(
                canonical_method,
                status="applied",
                requested_on="epochs",
            ),
        )

    @classmethod
    def apply_pending_epoch_normalization(cls, preprocessed_data: Raw) -> bool:
        """Apply one raw normalization request after epochs are materialized."""
        detail = preprocessed_data.get_runtime_detail(NORMALIZATION_RUNTIME_KEY)
        if not isinstance(detail, dict) or detail.get("status") != "pending":
            return False
        if preprocessed_data.is_raw():
            raise ValueError("Pending normalization requires epoched data")

        method = cls.canonical_method(str(detail.get("method", "")))
        cls._normalize_epochs(preprocessed_data, method)
        preprocessed_data.set_runtime_detail(
            NORMALIZATION_RUNTIME_KEY,
            cls._normalization_detail(
                method,
                status="applied",
                requested_on="raw",
            ),
        )
        preprocessed_data.add_preprocess(
            f"{method} normalization applied independently per epoch and channel"
        )
        return True

    @staticmethod
    def canonical_method(norm: str) -> str:
        """Return the stable method name accepted by the numeric transform."""
        norm_key = str(norm).casefold().replace("-", "").replace("_", "")
        norm_key = "".join(norm_key.split())
        if norm_key == "zscore":
            return "z score"
        if norm_key == "minmax":
            return "minmax"
        raise ValueError(
            f"Unknown normalization method: '{norm}'. "
            f"Supported methods are 'z score' and 'minmax'.",
        )

    @staticmethod
    def _normalization_detail(
        method: str,
        *,
        status: str,
        requested_on: str,
    ) -> dict[str, str | bool]:
        return {
            "method": method,
            "scope": NORMALIZATION_SCOPE,
            "status": status,
            "requested_on": requested_on,
            "uses_recording_statistics": False,
        }

    @staticmethod
    def _normalize_epochs(preprocessed_data: Raw, method: str) -> None:
        mne_data = preprocessed_data.get_mne()
        mne_data.load_data()
        arrdata = mne_data._data
        if arrdata is None or arrdata.ndim != 3:
            raise ValueError(
                "Leakage-safe normalization requires epoched data with shape "
                "(epochs, channels, samples)"
            )

        if method == "z score":
            center = arrdata.mean(axis=-1, keepdims=True)
            scale = arrdata.std(axis=-1, keepdims=True)
        else:
            center = arrdata.min(axis=-1, keepdims=True)
            scale = arrdata.max(axis=-1, keepdims=True) - center
        mne_data._data = (arrdata - center) / (scale + _EPSILON)
