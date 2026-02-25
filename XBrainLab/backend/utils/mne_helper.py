"""MNE-Python helper functions for montage queries and channel position lookups."""

import mne
import numpy as np


def get_builtin_montages():
    """Return a list of built-in MNE standard montage names.

    Returns:
        A list of strings, each being a valid montage name
        (e.g., ``'standard_1020'``).

    """
    return mne.channels.get_builtin_montages()


def get_montage_positions(montage_name: str) -> dict:
    """Return the full position dictionary for a standard montage.

    Args:
        montage_name: Name of the standard montage (e.g., ``'standard_1020'``).

    Returns:
        A dictionary containing channel positions and other montage metadata,
        as returned by :meth:`mne.channels.DigMontage.get_positions`.

    """
    montage = mne.channels.make_standard_montage(montage_name)
    return montage.get_positions()


def get_montage_channel_positions(montage_name, channel_names):
    """Return 3D positions for specified channels in a standard montage.

    Args:
        montage_name: Name of the standard montage.
        channel_names: List of channel name strings to look up.

    Returns:
        A numpy array of shape ``(len(channel_names), 3)`` with XYZ positions.

    """
    montage = mne.channels.make_standard_montage(montage_name)
    positions = montage.get_positions()["ch_pos"]
    return np.array([positions[ch] for ch in channel_names])
