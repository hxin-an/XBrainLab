"""Preprocessor for segmenting continuous EEG using a sliding window."""

import mne

from ..application.owned_work import owned_work_checkpoint
from ..load_data import Raw
from .base import PreprocessBase
from .normalize import Normalize


class WindowEpoch(PreprocessBase):
    """Segments continuous (raw) EEG data into fixed-length sliding-window epochs.

    Creates epochs of a given duration with optional overlap. The data must
    be raw (not already epoched) and must contain exactly one event label.
    """

    def check_data(self):
        """Validates that data is raw and contains exactly one event label.

        Raises:
            ValueError: If data is already epoched, has no event markers,
                or has more than one event label.

        """
        super().check_data()
        total = len(self.preprocessed_data_list)
        for index, preprocessed_data in enumerate(self.preprocessed_data_list):
            owned_work_checkpoint(
                "Validating sliding-window EEG recordings",
                completed=index,
                total=total,
            )
            if not preprocessed_data.is_raw():
                raise ValueError("Only raw data can be epoched, got epochs")
            events, event_id = preprocessed_data.get_event_list()
            if not event_id:
                raise ValueError(
                    f"No event markers found for {preprocessed_data.get_filename()}",
                )
            if len(events) != 1 or len(event_id) != 1:
                raise ValueError(
                    "Should only contain single event label, "
                    f"found events={len(events)}, event_id={len(event_id)}",
                )
            owned_work_checkpoint(
                "Validating sliding-window EEG recordings",
                completed=index + 1,
                total=total,
            )

    def get_preprocess_desc(self, duration: float, overlap: float):
        """Returns a description of the window-epoch step.

        Args:
            duration: Window duration in seconds.
            overlap: Overlap between consecutive windows in seconds.

        Returns:
            A string describing the sliding-window epoching parameters.

        """
        return f"Epoching {duration}s ({overlap}s overlap) by sliding window"

    def data_preprocess(
        self,
        duration: float,
        overlap: float | str,
    ) -> list[Raw]:
        """Create windows, then apply any leakage-safe normalization request."""
        result = super().data_preprocess(duration, overlap)
        total = len(result)
        for index, preprocessed_data in enumerate(result):
            owned_work_checkpoint(
                "Applying queued EEG epoch normalization",
                completed=index,
                total=total,
            )
            Normalize.apply_pending_epoch_normalization(preprocessed_data)
            owned_work_checkpoint(
                "Applying queued EEG epoch normalization",
                completed=index + 1,
                total=total,
            )
        return result

    def _data_preprocess(
        self,
        preprocessed_data: Raw,
        duration: float,
        overlap: float | str,
    ):
        """Segments a single raw data instance into sliding-window epochs.

        Args:
            preprocessed_data: The raw data instance to epoch.
            duration: Window duration in seconds.
            overlap: Overlap between consecutive windows in seconds.
                An empty string is treated as ``0.0``.

        """
        mne_data = preprocessed_data.get_mne()
        duration = float(duration)
        overlap = 0.0 if overlap == "" else float(overlap)
        fixed_id = 0
        epoch = mne.make_fixed_length_epochs(
            mne_data,
            duration=duration,
            overlap=overlap,
            preload=True,
            id=fixed_id,
        )
        _, event_id = preprocessed_data.get_event_list()
        epoch.event_id = {next(iter(event_id.keys())): fixed_id}
        preprocessed_data.set_mne_and_wipe_events(epoch)
