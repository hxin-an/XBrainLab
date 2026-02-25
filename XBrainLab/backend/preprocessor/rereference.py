"""Preprocessor for EEG re-referencing."""

from ..load_data import Raw
from .base import PreprocessBase


class Rereference(PreprocessBase):
    """Re-references EEG data to specified channels or the average.

    Applies a new reference to the EEG data using MNE's
    ``set_eeg_reference``. Supports average reference or a custom set of
    reference channels.
    """

    def get_preprocess_desc(self, ref_channels):
        """Returns a description of the re-referencing step.

        Args:
            ref_channels: The reference specification — ``"average"`` for
                average reference, or a list of channel names.

        Returns:
            A string describing the re-reference method applied.

        """
        if ref_channels == "average":
            return "Re-reference (Average)"
        return f"Re-reference (Channels: {ref_channels})"

    def _data_preprocess(self, preprocessed_data: Raw, ref_channels):
        """Applies re-referencing to a single data instance.

        Args:
            preprocessed_data: The data instance to preprocess.
            ref_channels: ``"average"`` for average reference, or a list
                of channel names to use as reference.

        """
        preprocessed_data.get_mne().load_data()

        # Apply re-referencing
        # mne.set_eeg_reference returns (inst, ref_data), we just modify inst in-place
        preprocessed_data.get_mne().set_eeg_reference(
            ref_channels=ref_channels,
            verbose=False,
        )
