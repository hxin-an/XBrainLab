from unittest.mock import MagicMock

import mne
import numpy as np
import pytest

from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.preprocessor.resample import Resample


class TestResample:
    @pytest.fixture
    def mock_raw(self):
        # Create a dummy Raw object with some data and events
        sfreq = 1000.0
        n_channels = 1
        n_samples = 10000
        data = np.random.randn(n_channels, n_samples)
        info = mne.create_info(ch_names=["EEG1"], sfreq=sfreq, ch_types=["eeg"])
        mne_raw = mne.io.RawArray(data, info)

        # Add some events
        events = np.array([[1000, 0, 1], [5000, 0, 2]])
        event_id = {"Event1": 1, "Event2": 2}

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
        raw, _events, _event_id = mock_raw
        resample = Resample([raw])
        target_sfreq = 100.0  # Downsample by 10x

        resample._data_preprocess(raw, sfreq=target_sfreq)

        # Verify MNE resample was called
        new_mne = raw.get_mne()
        assert new_mne.info["sfreq"] == target_sfreq

        # Verify events were updated
        # Expected events: 1000 -> 100, 5000 -> 500
        expected_events = np.array([[100, 0, 1], [500, 0, 2]])

        # Check if set_event was called with correct values
        args, _ = raw.set_event.call_args
        new_events_arg = args[0]

        np.testing.assert_array_equal(new_events_arg[:, 0], expected_events[:, 0])
        np.testing.assert_array_equal(new_events_arg[:, 2], expected_events[:, 2])

    def test_resample_upsample(self, mock_raw):
        raw, _events, _event_id = mock_raw
        resample = Resample([raw])
        target_sfreq = 2000.0  # Upsample by 2x

        resample._data_preprocess(raw, sfreq=target_sfreq)

        # Verify MNE resample was called
        new_mne = raw.get_mne()
        assert new_mne.info["sfreq"] == target_sfreq

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

    def test_resample_rejects_tail_nonfinite_before_fft_spreads_it(self, mock_raw):
        raw, _, _ = mock_raw
        original = raw.get_mne().get_data().copy()
        raw.get_mne()._data[0, -127:] = np.nan

        expected_message = (
            "Resampling requires finite EEG data. Remove the resampling step and "
            "keep this recording at its native sampling rate so BAD_nonfinite "
            "segments can be excluded during epoching, or select a recording "
            "without NaN or infinite samples. Raw FFT resampling can contaminate "
            "the complete recording."
        )
        with pytest.raises(ValueError) as exc_info:
            Resample([raw])._data_preprocess(raw, sfreq=100.0)

        assert str(exc_info.value) == expected_message
        assert raw.get_mne().info["sfreq"] == 1000.0
        np.testing.assert_array_equal(
            raw.get_mne().get_data()[:, :-127],
            original[:, :-127],
        )
        assert np.isnan(raw.get_mne().get_data()[:, -127:]).all()
        raw.set_mne.assert_not_called()
        raw.set_event.assert_not_called()

    def test_finite_guard_reads_large_raw_in_bounded_chunks(self, mock_raw):
        raw, _, _ = mock_raw
        mne_raw = raw.get_mne()
        real_get_data = mne_raw.get_data
        calls: list[tuple[int, int | None]] = []

        def tracked_get_data(*args, **kwargs):
            calls.append((kwargs.get("start", 0), kwargs.get("stop")))
            return real_get_data(*args, **kwargs)

        mne_raw.get_data = tracked_get_data

        Resample._require_finite_input(raw)

        assert calls
        assert all(stop is not None for _, stop in calls)
        assert max(stop - start for start, stop in calls if stop is not None) <= 10000
