from ..load_data import Raw
from .base import PreprocessBase


class Rereference(PreprocessBase):
    """Preprocessing class for Re-referencing.

    Input:
        ref_channels: List of channels to use as reference.
                      If 'average', use average reference.
                      If [], use no reference (or keep existing).
    """

    def get_preprocess_desc(self, ref_channels):
        if ref_channels == 'average':
            return "Re-reference (Average)"
        return f"Re-reference (Channels: {ref_channels})"

    def _data_preprocess(self, preprocessed_data: Raw, ref_channels):
        preprocessed_data.get_mne().load_data()

        # Apply re-referencing
        # mne.set_eeg_reference returns (inst, ref_data), we just modify inst in-place
        preprocessed_data.get_mne().set_eeg_reference(ref_channels=ref_channels, verbose=False)
