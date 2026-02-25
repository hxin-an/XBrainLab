"""Unit tests for preprocessor/export — Export to .mat."""

from unittest.mock import patch

import mne
import numpy as np

from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.preprocessor.export import Export


def _make_raw_with_name(sub="S01", sess="01"):
    info = mne.create_info(["Cz"], sfreq=256, ch_types="eeg")
    mne_raw = mne.io.RawArray(np.random.randn(1, 256), info)
    raw = Raw("test.gdf", mne_raw)
    raw.set_subject_name(sub)
    raw.set_session_name(sess)
    return raw


def _make_epoch_with_name(sub="S01", sess="01"):
    info = mne.create_info(["Cz"], sfreq=256, ch_types="eeg")
    data = np.random.randn(4, 1, 256)
    event_id = {"left": 1, "right": 2}
    events = np.array([[0, 0, 1], [256, 0, 2], [512, 0, 1], [768, 0, 2]])
    epochs = mne.EpochsArray(data, info, events=events, event_id=event_id)
    raw = Raw("test.gdf", epochs)
    raw.set_subject_name(sub)
    raw.set_session_name(sess)
    return raw


class TestExport:
    @patch("XBrainLab.backend.preprocessor.export.scipy.io.savemat")
    def test_export_raw(self, mock_savemat, tmp_path):
        raw = _make_raw_with_name("A01", "T")
        export = Export([raw])
        result = export.data_preprocess(filepath=str(tmp_path))

        assert len(result) == 1
        mock_savemat.assert_called_once()
        call_args = mock_savemat.call_args
        filepath_arg = call_args[0][0]
        data_arg = call_args[0][1]

        assert "Sub-A01" in filepath_arg
        assert "Sess-T" in filepath_arg
        assert filepath_arg.endswith(".mat")
        assert "x" in data_arg

    @patch("XBrainLab.backend.preprocessor.export.scipy.io.savemat")
    def test_export_epoch(self, mock_savemat, tmp_path):
        raw = _make_epoch_with_name("B02", "S2")
        export = Export([raw])
        result = export.data_preprocess(filepath=str(tmp_path))

        assert len(result) == 1
        mock_savemat.assert_called_once()
        call_args = mock_savemat.call_args
        data_arg = call_args[0][1]
        assert "x" in data_arg
        assert "y" in data_arg

    @patch("XBrainLab.backend.preprocessor.export.scipy.io.savemat")
    def test_export_multiple_files(self, mock_savemat, tmp_path):
        raw1 = _make_raw_with_name("S01", "01")
        raw2 = _make_raw_with_name("S02", "02")
        export = Export([raw1, raw2])
        export.data_preprocess(filepath=str(tmp_path))

        assert mock_savemat.call_count == 2
