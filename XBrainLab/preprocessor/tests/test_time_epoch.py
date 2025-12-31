
import pytest
import numpy as np
import mne
from unittest.mock import MagicMock, patch
from XBrainLab.preprocessor.time_epoch import TimeEpoch
from XBrainLab.load_data import Raw

class TestTimeEpoch:
    @pytest.fixture
    def mock_raw(self):
        # Create a dummy Raw object
        sfreq = 1000.0
        n_channels = 1
        n_samples = 10000
        data = np.random.randn(n_channels, n_samples)
        info = mne.create_info(ch_names=['EEG1'], sfreq=sfreq, ch_types=['eeg'])
        mne_raw = mne.io.RawArray(data, info)
        
        # Add some events
        # Event 1 at 1000, Event 2 at 5000
        events = np.array([[1000, 0, 1], [5000, 0, 2]])
        event_id = {'Event1': 1, 'Event2': 2}
        
        # Mock the Raw wrapper
        raw = MagicMock(spec=Raw)
        raw.get_mne.return_value = mne_raw
        raw.get_sfreq.return_value = sfreq
        raw.is_raw.return_value = True
        raw.get_event_list.return_value = (events, event_id)
        
        # Mock set_mne to update the internal mne object
        def set_mne_side_effect(new_mne):
            raw.get_mne.return_value = new_mne
            raw.is_raw.return_value = False # Becomes epoched
        raw.set_mne.side_effect = set_mne_side_effect
        
        return raw, events, event_id

    def test_time_epoch_success(self, mock_raw):
        raw, events, event_id = mock_raw
        time_epoch = TimeEpoch([raw])
        
        # Select Event1
        time_epoch._data_preprocess(
            raw, 
            selected_event_names=['Event1'], 
            tmin=-0.1, 
            tmax=0.5, 
            baseline=None
        )
        
        # Verify set_mne was called with Epochs
        args, _ = raw.set_mne.call_args
        new_mne = args[0]
        assert isinstance(new_mne, mne.Epochs)
        assert len(new_mne) == 1 # Only 1 event selected
        assert new_mne.events[0, 2] == 1 # Event ID 1

    def test_time_epoch_no_matching_events(self, mock_raw):
        raw, events, event_id = mock_raw
        time_epoch = TimeEpoch([raw])
        
        # Select non-existent event
        with pytest.raises(ValueError, match="No event markers found"):
            time_epoch._data_preprocess(
                raw, 
                selected_event_names=['Event3'], 
                tmin=-0.1, 
                tmax=0.5, 
                baseline=None
            )

    def test_time_epoch_duplicate_events(self, mock_raw):
        raw, _, event_id = mock_raw
        
        # Create duplicate events at same sample
        events = np.array([[1000, 0, 1], [1000, 0, 1]])
        raw.get_event_list.return_value = (events, event_id)
        
        time_epoch = TimeEpoch([raw])
        
        # Should not raise error due to event_repeated='drop'
        time_epoch._data_preprocess(
            raw, 
            selected_event_names=['Event1'], 
            tmin=-0.1, 
            tmax=0.5, 
            baseline=None
        )
        
        args, _ = raw.set_mne.call_args
        new_mne = args[0]
        assert len(new_mne) == 1 # Duplicate dropped

    def test_time_epoch_already_epoched(self, mock_raw):
        raw, _, _ = mock_raw
        raw.is_raw.return_value = False
        
        with pytest.raises(ValueError, match="Only raw data can be epoched, got epochs"):
            time_epoch = TimeEpoch([raw])
