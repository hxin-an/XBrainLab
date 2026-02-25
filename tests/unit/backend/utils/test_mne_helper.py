"""Unit tests for MNE helper functions."""

import numpy as np
import pytest

from XBrainLab.backend.utils.mne_helper import (
    get_builtin_montages,
    get_montage_channel_positions,
    get_montage_positions,
)


class TestGetBuiltinMontages:
    def test_returns_list_of_strings(self):
        montages = get_builtin_montages()
        assert isinstance(montages, list)
        assert len(montages) > 0
        assert all(isinstance(m, str) for m in montages)

    def test_standard_1020_in_list(self):
        montages = get_builtin_montages()
        assert "standard_1020" in montages


class TestGetMontagePositions:
    def test_returns_dict(self):
        positions = get_montage_positions("standard_1020")
        assert isinstance(positions, dict)
        assert "ch_pos" in positions

    def test_channel_positions_present(self):
        positions = get_montage_positions("standard_1020")
        ch_pos = positions["ch_pos"]
        assert "Cz" in ch_pos
        assert "Fz" in ch_pos


class TestGetMontageChannelPositions:
    def test_returns_correct_shape(self):
        channels = ["Cz", "Fz", "Pz"]
        pos = get_montage_channel_positions("standard_1020", channels)
        assert isinstance(pos, np.ndarray)
        assert pos.shape == (3, 3)

    def test_unknown_channel_raises(self):
        with pytest.raises(KeyError):
            get_montage_channel_positions("standard_1020", ["NONEXISTENT_CH"])
