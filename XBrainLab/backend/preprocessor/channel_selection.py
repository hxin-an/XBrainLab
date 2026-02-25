"""Preprocessor for EEG channel selection."""

from ..load_data import Raw
from .base import PreprocessBase


class ChannelSelection(PreprocessBase):
    """Selects a subset of EEG channels from the data.

    Reduces the channel set to only those specified, dropping all others.
    This is useful for removing non-EEG channels or focusing on specific
    scalp regions.
    """

    def get_preprocess_desc(self, selected_channels: list[str]):
        """Returns a description of the channel selection step.

        Args:
            selected_channels: List of channel names to keep.

        Returns:
            A string describing how many channels were selected.
        """
        return f"Select {len(selected_channels)} Channel"

    def _data_preprocess(self, preprocessed_data: Raw, selected_channels: list[str]):
        """Picks the specified channels from the data.

        Args:
            preprocessed_data: The data instance to preprocess.
            selected_channels: List of channel names to keep.

        Raises:
            ValueError: If no channels are selected.
        """
        # Check if channel is selected
        if len(selected_channels) == 0:
            raise ValueError("No Channel is Selected")
        preprocessed_data.get_mne().pick_channels(selected_channels)
