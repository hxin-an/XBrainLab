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
from XBrainLab.backend.load_data import Raw


def _first_data(controller: PreprocessController) -> Raw:
    data = controller.get_first_data()
    assert isinstance(data, Raw)
    return data


def _assert_signal_data_shape(raw: Raw) -> Any:
    data: Any = raw.get_mne().get_data()
    assert data.ndim in (2, 3)
    assert data.size > 0
    if data.ndim == 2:
        assert data.shape[0] == raw.get_nchan()
        assert data.shape[1] > 0
    else:
        assert data.shape[0] > 0
        assert data.shape[1] == raw.get_nchan()
        assert data.shape[2] > 0
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
    rng = np.random.default_rng(42)
    data = rng.standard_normal((n_channels, int(sfreq * duration))) * 1e-6
    assert data.shape == (n_channels, int(sfreq * duration))
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
        signal_before = _assert_signal_data_shape(data)
        events_before, event_id_before = mne.events_from_annotations(data.get_mne())
        assert event_id_before == {"left": 1, "right": 2}
        assert events_before.shape == (4, 3)

        pc.apply_resample(sfreq=128)

        data_after = _first_data(pc)
        signal_after = _assert_signal_data_shape(data_after)
        events_after, event_id_after = mne.events_from_annotations(data_after.get_mne())
        assert event_id_after == event_id_before
        assert events_after.shape == events_before.shape
        np.testing.assert_array_equal(events_after[:, -1], events_before[:, -1])
        assert data_after.get_mne().info["sfreq"] == 128
        assert signal_after.shape[0] == signal_before.shape[0]
        assert signal_after.shape[1] < signal_before.shape[1]

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
        epoched = _first_data(pc)
        epoch_data = _assert_signal_data_shape(epoched)
        epochs: Any = epoched.get_mne()
        assert target_event in epochs.event_id
        assert epochs.events.ndim == 2
        assert epochs.events.shape[0] > 0
        assert epochs.events.shape[1] == 3
        assert set(np.unique(epochs.events[:, -1]).tolist()) == {
            epochs.event_id[target_event]
        }
        assert epoch_data.shape[0] == len(epochs.events)

    def test_history_tracks_operations(self, study_with_synthetic):
        """Preprocessing history should record all operations."""
        pc = PreprocessController(study_with_synthetic)

        pc.apply_filter(l_freq=1, h_freq=40)
        pc.apply_resample(sfreq=128)

        history = _first_data(pc).get_preprocess_history()
        assert len(history) == 2
        assert all(isinstance(item, str) for item in history)
        assert any("Filtering" in item for item in history)
        assert any("Resample" in item for item in history)

    def test_reset_restores_original(self, study_with_synthetic):
        """Reset should restore data to original state."""
        pc = PreprocessController(study_with_synthetic)
        original = _first_data(pc)
        original_sfreq = original.get_mne().info["sfreq"]
        original_signal = _assert_signal_data_shape(original)

        pc.apply_resample(sfreq=64)
        assert _first_data(pc).get_mne().info["sfreq"] == 64

        pc.reset_preprocess()
        reset_data = _first_data(pc)
        assert reset_data.get_mne().info["sfreq"] == original_sfreq
        assert reset_data.get_preprocess_history() == []
        reset_signal = _assert_signal_data_shape(reset_data)
        assert reset_signal.shape == original_signal.shape
