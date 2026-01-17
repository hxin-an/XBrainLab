import mne
import numpy as np


def get_builtin_montages():
    """Returns a list of built-in MNE montages."""
    return mne.channels.get_builtin_montages()


def get_montage_positions(montage_name):
    """
    Returns a dictionary of channel positions for the given montage.
    Returns: {'ch_pos': {ch_name: pos_array, ...}}
    """
    montage = mne.channels.make_standard_montage(montage_name)
    return montage.get_positions()


def get_montage_channel_positions(montage_name, channel_names):
    """
    Returns an array of positions for the specified channels in the given montage.
    """
    montage = mne.channels.make_standard_montage(montage_name)
    positions = montage.get_positions()["ch_pos"]
    return np.array([positions[ch] for ch in channel_names])
