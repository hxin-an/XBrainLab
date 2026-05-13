"""
Integration tests for preprocessing edge cases and validation.
"""

from typing import Any

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    LoadDataCommand,
    QueryStateCommand,
)
from XBrainLab.backend.controller.preprocess_controller import PreprocessController


def _first_data(controller: PreprocessController) -> Any:
    data = controller.get_first_data()
    assert data is not None
    return data


@pytest.fixture
def study_with_synthetic(tmp_path):
    """Create a Study with synthetic raw data loaded via a temp .fif file."""
    service = ApplicationService()

    # Create synthetic raw data with events
    sfreq = 256
    n_channels = 8
    duration = 10  # seconds
    ch_names = [f"EEG{i:03d}" for i in range(n_channels)]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    data = np.random.randn(n_channels, int(sfreq * duration)) * 1e-6
    raw = mne.io.RawArray(data, info)

    # Add events via annotations
    events = np.array([[256, 0, 1], [768, 0, 1], [1280, 0, 2], [1792, 0, 2]])
    annotations = mne.annotations_from_events(
        events, sfreq=sfreq, event_desc={1: "left", 2: "right"}
    )
    raw.set_annotations(annotations)

    # Save to temp .fif file and load through the command spine
    fif_path = str(tmp_path / "test_raw.fif")
    raw.save(fif_path, overwrite=True)

    load_result = service.execute(LoadDataCommand(paths=[fif_path]))
    assert load_result.ok is True
    query_result = service.execute(QueryStateCommand(query="state"))
    assert query_result.ok is True
    assert query_result.diagnostics["state"]["raw"]["count"] == 1
    return service.study


class TestPreprocessValidation:
    """Test preprocessing parameter validation and boundary cases."""

    def test_resample_preserves_events(self, study_with_synthetic):
        """After resampling, event count should remain the same."""
        pc = PreprocessController(study_with_synthetic)
        data = _first_data(pc)
        events_before = mne.events_from_annotations(data.get_mne())[0]

        pc.apply_resample(sfreq=128)

        data_after = _first_data(pc)
        events_after = mne.events_from_annotations(data_after.get_mne())[0]
        assert len(events_after) == len(events_before)
        assert data_after.get_mne().info["sfreq"] == 128

    def test_filter_then_epoch_pipeline(self, study_with_synthetic):
        """Sequential filter → epoch should produce valid epoched data."""
        pc = PreprocessController(study_with_synthetic)

        # Apply bandpass filter
        pc.apply_filter(l_freq=1, h_freq=40)
        assert not pc.is_epoched()

        # Get events and epoch
        unique_events = pc.get_unique_events()
        assert unique_events == ["left", "right"]

        target_event = "left"
        pc.apply_epoching(
            baseline=None,
            selected_events=[target_event],
            tmin=0.0,
            tmax=0.5,
        )
        assert pc.is_epoched()

    def test_history_tracks_operations(self, study_with_synthetic):
        """Preprocessing history should record all operations."""
        pc = PreprocessController(study_with_synthetic)

        pc.apply_filter(l_freq=1, h_freq=40)
        pc.apply_resample(sfreq=128)

        history = _first_data(pc).get_preprocess_history()
        assert len(history) >= 2

    def test_reset_restores_original(self, study_with_synthetic):
        """Reset should restore data to original state."""
        pc = PreprocessController(study_with_synthetic)
        original_sfreq = _first_data(pc).get_mne().info["sfreq"]

        pc.apply_resample(sfreq=64)
        assert _first_data(pc).get_mne().info["sfreq"] == 64

        pc.reset_preprocess()
        assert _first_data(pc).get_mne().info["sfreq"] == original_sfreq
