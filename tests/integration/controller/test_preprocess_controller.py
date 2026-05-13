"""
Integration tests for PreprocessController using real GDF data.
"""

import os
from typing import Any

import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    LoadDataCommand,
    QueryStateCommand,
)
from XBrainLab.backend.controller.preprocess_controller import PreprocessController

# Locate test data (relative to project root)
TEST_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../fixtures/data")
)
GDF_FILE = os.path.join(TEST_DATA_DIR, "A01T.gdf")
EXPECTED_A01T_EVENTS = {"768", "769", "770", "771", "772"}


def _first_data(controller: PreprocessController) -> Any:
    data = controller.get_first_data()
    assert data is not None
    return data


@pytest.fixture
def study():
    service = ApplicationService()
    load_result = service.execute(LoadDataCommand(paths=[GDF_FILE]))
    assert load_result.ok is True
    state_result = service.execute(QueryStateCommand(query="state"))
    assert state_result.ok is True
    assert state_result.diagnostics["state"]["raw"]["count"] == 1
    return service.study


@pytest.fixture
def preprocess_controller(study):
    return PreprocessController(study)


class TestPreprocessController:
    """Test preprocessing pipeline operations."""

    def test_filter_application(self, preprocess_controller):
        """Test applying bandpass filter."""
        assert preprocess_controller.has_data()

        # Get raw data stats before filter
        data_before = _first_data(preprocess_controller).get_mne().get_data()
        std_before = np.std(data_before)

        # Apply strict bandpass (e.g. 8-12Hz Alpha)
        preprocess_controller.apply_filter(l_freq=8, h_freq=12)

        # Get data after
        data_after = _first_data(preprocess_controller).get_mne().get_data()
        std_after = np.std(data_after)

        # Filtered data should have lower variance (removed other freqs)
        assert std_after < std_before

        # Verify history updated
        history = _first_data(preprocess_controller).get_preprocess_history()
        assert any("Filtering" in h for h in history)

    def test_epoch_extraction(self, preprocess_controller):
        """Test epoching from events."""
        # A01T has events 768, 769, 770 etc.
        unique_events = preprocess_controller.get_unique_events()
        assert EXPECTED_A01T_EVENTS.issubset(set(unique_events))

        target_event = "769"

        # Apply epoching
        preprocess_controller.apply_epoching(
            baseline=None, selected_events=[target_event], tmin=0.0, tmax=4.0
        )

        assert preprocess_controller.is_epoched()

        epochs = _first_data(preprocess_controller).get_mne()
        assert target_event in epochs.event_id
        assert len(epochs.events) > 0
        assert epochs.tmax == 4.0

    def test_reset_preprocess(self, preprocess_controller):
        """Test resetting preprocessing pipeline."""
        preprocess_controller.apply_filter(8, 12)
        history_before_reset = _first_data(
            preprocess_controller,
        ).get_preprocess_history()
        assert any("Filtering" in h for h in history_before_reset)

        preprocess_controller.reset_preprocess()

        # History should be cleared (or just contain raw load info)
        # Note: implementation of reset usually reverts to raw state
        history = _first_data(preprocess_controller).get_preprocess_history()
        # Since reset restores from loaded_data_list deepcopy, history should be reset
        # Depending on if loaded data had history.
        # Check against pure raw load

        # Actually verify MNE object is raw again
        assert _first_data(preprocess_controller).is_raw()

    def test_sequential_pipeline(self, preprocess_controller):
        """Test multiple operations in sequence."""
        # 1. Filter
        preprocess_controller.apply_filter(1, 40)

        # 2. Resample (downsample to 100Hz)
        original_sfreq = _first_data(preprocess_controller).get_sfreq()
        preprocess_controller.apply_resample(100)

        current_data = _first_data(preprocess_controller)
        assert current_data.get_sfreq() == 100
        assert current_data.get_sfreq() != original_sfreq

        # 3. Epoching
        events = preprocess_controller.get_unique_events()
        assert EXPECTED_A01T_EVENTS.issubset(set(events))
        preprocess_controller.apply_epoching(None, ["769"], 0, 1)

        assert preprocess_controller.is_epoched()
