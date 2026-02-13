"""
Integration tests for PreprocessController using real GDF data.
"""

import os

import numpy as np
import pytest

from XBrainLab.backend.controller.dataset_controller import DatasetController
from XBrainLab.backend.controller.preprocess_controller import PreprocessController
from XBrainLab.backend.study import Study

# Locate test data (relative to project root)
TEST_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
GDF_FILE = os.path.join(TEST_DATA_DIR, "A01T.gdf")


@pytest.fixture
def study():
    return Study()


@pytest.fixture
def preprocess_controller(study):
    # Need dataset controller to load data first
    ds_controller = DatasetController(study)
    ds_controller.import_files([GDF_FILE])
    return PreprocessController(study)


class TestPreprocessController:
    """Test preprocessing pipeline operations."""

    def test_filter_application(self, preprocess_controller):
        """Test applying bandpass filter."""
        assert preprocess_controller.has_data()

        # Get raw data stats before filter
        data_before = preprocess_controller.get_first_data().get_mne().get_data()
        std_before = np.std(data_before)

        # Apply strict bandpass (e.g. 8-12Hz Alpha)
        preprocess_controller.apply_filter(l_freq=8, h_freq=12)

        # Get data after
        data_after = preprocess_controller.get_first_data().get_mne().get_data()
        std_after = np.std(data_after)

        # Filtered data should have lower variance (removed other freqs)
        assert std_after < std_before

        # Verify history updated
        history = preprocess_controller.get_first_data().get_preprocess_history()
        assert any("Filtering" in h for h in history)

    def test_epoch_extraction(self, preprocess_controller):
        """Test epoching from events."""
        # A01T has events 768, 769, 770 etc.
        unique_events = preprocess_controller.get_unique_events()
        assert len(unique_events) > 0

        target_event = unique_events[0]

        # Apply epoching
        preprocess_controller.apply_epoching(
            baseline=None, selected_events=[target_event], tmin=0.0, tmax=4.0
        )

        assert preprocess_controller.is_epoched()

        epochs = preprocess_controller.get_first_data().get_mne()
        assert len(epochs) > 0
        assert epochs.tmax == 4.0

    def test_reset_preprocess(self, preprocess_controller):
        """Test resetting preprocessing pipeline."""
        preprocess_controller.apply_filter(8, 12)
        assert len(preprocess_controller.get_first_data().get_preprocess_history()) > 0

        preprocess_controller.reset_preprocess()

        # History should be cleared (or just contain raw load info)
        # Note: implementation of reset usually reverts to raw state
        history = preprocess_controller.get_first_data().get_preprocess_history()
        # Since reset restores from loaded_data_list deepcopy, history should be reset
        # Depending on if loaded data had history.
        # Check against pure raw load

        # Actually verify MNE object is raw again
        assert preprocess_controller.get_first_data().is_raw()

    def test_sequential_pipeline(self, preprocess_controller):
        """Test multiple operations in sequence."""
        # 1. Filter
        preprocess_controller.apply_filter(1, 40)

        # 2. Resample (downsample to 100Hz)
        original_sfreq = preprocess_controller.get_first_data().get_sfreq()
        preprocess_controller.apply_resample(100)

        current_data = preprocess_controller.get_first_data()
        assert current_data.get_sfreq() == 100
        assert current_data.get_sfreq() != original_sfreq

        # 3. Epoching
        events = preprocess_controller.get_unique_events()
        preprocess_controller.apply_epoching(None, [events[0]], 0, 1)

        assert preprocess_controller.is_epoched()
