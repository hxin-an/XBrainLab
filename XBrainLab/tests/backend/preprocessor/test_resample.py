
import pytest
import numpy as np
import mne
from unittest.mock import MagicMock
from XBrainLab.backend.preprocessor.resample import Resample
from XBrainLab.backend.load_data import Raw

class TestResample:
    @pytest.fixture
    def mock_raw(self):
        # Create a dummy Raw object with some data and events
        sfreq = 1000.0
        n_channels = 1
        n_samples = 10000
        data = np.random.randn(n_channels, n_samples)
        info = mne.create_info(ch_names=['EEG1'], sfreq=sfreq, ch_types=['eeg'])
        mne_raw = mne.io.RawArray(data, info)
        
        # Add some events
        events = np.array([[1000, 0, 1], [5000, 0, 2]])
        event_id = {'Event1': 1, 'Event2': 2}
        
        # Mock the Raw wrapper
        raw = MagicMock(spec=Raw)
        raw.get_mne.return_value = mne_raw
        raw.get_sfreq.return_value = sfreq
        raw.is_raw.return_value = True
        
        # Mock get_event_list to return our events
        raw.get_event_list.return_value = (events, event_id)
        
        # Mock set_event to verify it's called
        raw.set_event = MagicMock()
        
        # Mock set_mne to update the internal mne object
        def set_mne_side_effect(new_mne):
            raw.get_mne.return_value = new_mne
        raw.set_mne.side_effect = set_mne_side_effect
        
        return raw, events, event_id

    def test_resample_downsample(self, mock_raw):
        raw, events, event_id = mock_raw
        resample = Resample([raw])
        target_sfreq = 100.0 # Downsample by 10x
        
        resample._data_preprocess(raw, sfreq=target_sfreq)
        
        # Verify MNE resample was called
        new_mne = raw.get_mne()
        assert new_mne.info['sfreq'] == target_sfreq
        
        # Verify events were updated
        # Expected events: 1000 -> 100, 5000 -> 500
        expected_events = np.array([[100, 0, 1], [500, 0, 2]])
        
        # Check if set_event was called with correct values
        args, _ = raw.set_event.call_args
        new_events_arg = args[0]
        
        np.testing.assert_array_equal(new_events_arg[:, 0], expected_events[:, 0])
        np.testing.assert_array_equal(new_events_arg[:, 2], expected_events[:, 2])

    def test_resample_upsample(self, mock_raw):
        raw, events, event_id = mock_raw
        resample = Resample([raw])
        target_sfreq = 2000.0 # Upsample by 2x
        
        resample._data_preprocess(raw, sfreq=target_sfreq)
        
        # Verify MNE resample was called
        new_mne = raw.get_mne()
        assert new_mne.info['sfreq'] == target_sfreq
        
        # Expected events: 1000 -> 2000, 5000 -> 10000
        expected_events = np.array([[2000, 0, 1], [10000, 0, 2]])
        
        args, _ = raw.set_event.call_args
        new_events_arg = args[0]
        
        np.testing.assert_array_equal(new_events_arg[:, 0], expected_events[:, 0])
        
    def test_resample_no_events(self, mock_raw):
        raw, _, _ = mock_raw
        # Mock no events
        raw.get_event_list.return_value = (np.array([]), {})
        
        resample = Resample([raw])
        resample._data_preprocess(raw, sfreq=100.0)
        
        # Verify set_event was NOT called
        raw.set_event.assert_not_called()
