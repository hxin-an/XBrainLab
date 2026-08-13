import warnings
from unittest.mock import MagicMock, call, patch

import mne
import numpy as np
import pytest

from XBrainLab.backend.exceptions import FileCorruptedError
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.load_data.raw_data_loader import (
    load_bdf_file,
    load_brainvision_file,
    load_cnt_file,
    load_edf_file,
    load_fif_file,
    load_gdf_file,
    load_raw_data,
    load_set_file,
)


def test_real_fif_loader_retains_lazy_source_dependency(tmp_path) -> None:
    """Characterize the source-file lifetime required by prepared imports."""
    path = tmp_path / "subject01_raw.fif"
    source = mne.io.RawArray(
        np.zeros((1, 100)),
        mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg"),
        verbose="ERROR",
    )
    source.save(path, overwrite=True, verbose="ERROR")

    loaded = load_fif_file(str(path))

    assert isinstance(loaded, Raw)
    assert loaded.get_mne().preload is False
    assert str(path) in {str(item) for item in loaded.get_mne().filenames}


class TestRawDataLoaderUnit:
    """
    Unit tests for raw_data_loader.py
    Uses mocking to avoid actual file I/O.
    """

    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_gdf")
    def test_load_gdf_success(self, mock_read_gdf, mock_validate):
        """Test successful GDF loading with mocked MNE."""
        # Setup mock return value
        mock_raw = MagicMock()
        mock_read_gdf.return_value = mock_raw

        # Execute
        result = load_gdf_file("dummy.gdf")

        # Verify
        mock_read_gdf.assert_called_once_with("dummy.gdf", preload=False)
        assert isinstance(result, Raw)
        assert result.get_mne() == mock_raw

    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.logger.warning")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_gdf")
    def test_load_gdf_logs_duplicate_channel_signal(
        self,
        mock_read_gdf,
        mock_logger_warning,
        mock_validate,
    ):
        """Surface a repo-specific warning when MNE auto-renames duplicate names."""
        mock_raw = MagicMock()
        mock_raw.info = {"ch_names": ["EEG-Fz", "EEG-0", "EEG-1", "EEG-Cz"]}

        def fake_read(*args, **kwargs):
            warnings.warn(
                "Channel names are not unique, found duplicates for: {'EEG'}. "
                "Applying running numbers for duplicates.",
                RuntimeWarning,
                stacklevel=1,
            )
            return mock_raw

        mock_read_gdf.side_effect = fake_read

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = load_gdf_file("dummy.gdf")

        assert isinstance(result, Raw)
        assert result.get_mne() == mock_raw
        mock_logger_warning.assert_called_once()
        assert (
            "auto-renaming duplicate channel names"
            in mock_logger_warning.call_args[0][1]
        )
        assert "dummy.gdf" in mock_logger_warning.call_args[0][1]
        assert result.has_runtime_signals()
        assert (
            "auto-renaming duplicate channel names" in result.get_runtime_signals()[0]
        )
        assert result.has_runtime_detail("gdf_duplicate_channel_names")
        assert result.has_gdf_duplicate_channel_detail()
        assert result.get_gdf_duplicate_channel_detail() == {
            "kind": "gdf_duplicate_channel_names",
            "filepath": "dummy.gdf",
            "generated_bases": ["EEG"],
            "generated_channels": ["EEG-0", "EEG-1"],
            "message": result.get_runtime_signals()[0],
        }
        assert any(
            "Channel names are not unique" in str(caught_warning.message)
            for caught_warning in caught_warnings
        )

    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.logger.info")
    @patch("XBrainLab.backend.load_data.raw_data_loader.logger.warning")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_gdf")
    def test_load_gdf_normalizes_known_graz_2a_duplicate_names(
        self,
        mock_read_gdf,
        mock_logger_warning,
        mock_logger_info,
        mock_validate,
    ):
        """Restore canonical labels when the known Graz 2a duplicate pattern appears."""
        ch_names = [
            "EEG-Fz",
            "EEG-0",
            "EEG-1",
            "EEG-2",
            "EEG-3",
            "EEG-4",
            "EEG-5",
            "EEG-C3",
            "EEG-6",
            "EEG-Cz",
            "EEG-7",
            "EEG-C4",
            "EEG-8",
            "EEG-9",
            "EEG-10",
            "EEG-11",
            "EEG-12",
            "EEG-13",
            "EEG-14",
            "EEG-Pz",
            "EEG-15",
            "EEG-16",
            "EOG-left",
            "EOG-central",
            "EOG-right",
        ]
        mock_raw = MagicMock()
        mock_raw.info = {"ch_names": ch_names.copy()}

        def rename_channels(mapping):
            mock_raw.info["ch_names"] = [mapping.get(name, name) for name in ch_names]

        mock_raw.rename_channels.side_effect = rename_channels

        def fake_read(*args, **kwargs):
            warnings.warn(
                "Channel names are not unique, found duplicates for: {'EEG'}. "
                "Applying running numbers for duplicates.",
                RuntimeWarning,
                stacklevel=1,
            )
            return mock_raw

        mock_read_gdf.side_effect = fake_read

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = load_gdf_file("A01T.gdf")

        assert isinstance(result, Raw)
        assert result.get_mne() == mock_raw
        mock_logger_warning.assert_not_called()
        mock_logger_info.assert_called_once()
        assert result.get_mne().info["ch_names"][1:6] == [
            "EEG-FC3",
            "EEG-FC1",
            "EEG-FCz",
            "EEG-FC2",
            "EEG-FC4",
        ]
        assert result.get_mne().info["ch_names"][18:22] == [
            "EEG-P1",
            "EEG-Pz",
            "EEG-P2",
            "EEG-POz",
        ]
        assert result.has_runtime_signals() is False
        detail = result.get_gdf_duplicate_channel_detail()
        assert detail is not None
        assert detail["resolved"] is True
        assert detail["normalization_name"] == "graz_2a_canonical_22"
        assert "EEG-0" in detail["generated_channels"]
        assert "EEG-FC3" in detail["normalized_channels"]
        assert not any(
            "Channel names are not unique" in str(caught_warning.message)
            for caught_warning in caught_warnings
        )

    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_gdf")
    def test_load_gdf_failure(self, mock_read_gdf):
        """Test GDF loading failure handling."""
        # Setup mock to raise exception
        mock_read_gdf.side_effect = Exception("File corrupted")

        # Execute & Verify
        # Execute & Verify

        with pytest.raises(FileCorruptedError):
            load_gdf_file("corrupted.gdf")

    @pytest.mark.parametrize(
        ("loader", "reader_path", "filename"),
        [
            (
                load_bdf_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_bdf",
                "recording.bdf",
            ),
            (
                load_cnt_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_cnt",
                "recording.cnt",
            ),
            (
                load_brainvision_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_brainvision",
                "recording.vhdr",
            ),
            (
                load_fif_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_fif",
                "recording.fif",
            ),
        ],
        ids=("bdf", "cnt", "brainvision", "fif"),
    )
    def test_format_loader_wraps_reader_result(
        self,
        loader,
        reader_path,
        filename,
    ):
        mne_raw = MagicMock()
        with (
            patch("XBrainLab.backend.load_data.raw.validate_type"),
            patch(reader_path, return_value=mne_raw) as reader,
        ):
            result = loader(filename)

        assert isinstance(result, Raw)
        assert result.get_mne() is mne_raw
        reader.assert_called_once_with(filename, preload=False)

    @pytest.mark.parametrize(
        ("loader", "reader_path", "filename"),
        [
            (
                load_edf_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_edf",
                "broken.edf",
            ),
            (
                load_bdf_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_bdf",
                "broken.bdf",
            ),
            (
                load_cnt_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_cnt",
                "broken.cnt",
            ),
            (
                load_brainvision_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_brainvision",
                "broken.vhdr",
            ),
        ],
        ids=("edf", "bdf", "cnt", "brainvision"),
    )
    def test_format_loader_translates_reader_failure(
        self,
        loader,
        reader_path,
        filename,
    ):
        reader_error = RuntimeError("corrupted payload")
        with (
            patch(reader_path, side_effect=reader_error),
            pytest.raises(FileCorruptedError) as raised,
        ):
            loader(filename)

        assert raised.value.__cause__ is reader_error
        assert filename in str(raised.value)
        assert "corrupted payload" in str(raised.value)

    @pytest.mark.parametrize(
        ("loader", "reader_path", "filename"),
        [
            (
                load_edf_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_edf",
                "empty.edf",
            ),
            (
                load_bdf_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_bdf",
                "empty.bdf",
            ),
            (
                load_cnt_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_cnt",
                "empty.cnt",
            ),
            (
                load_brainvision_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_brainvision",
                "empty.vhdr",
            ),
            (
                load_fif_file,
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_fif",
                "empty.fif",
            ),
        ],
        ids=("edf", "bdf", "cnt", "brainvision", "fif"),
    )
    def test_format_loader_preserves_empty_reader_result(
        self,
        loader,
        reader_path,
        filename,
    ):
        with patch(reader_path, return_value=None):
            assert loader(filename) is None

    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_edf")
    def test_load_edf_applies_inferred_types_without_renaming_channels(
        self,
        mock_read_edf,
        mock_validate,
    ):
        preserved_raw = MagicMock()
        preserved_raw.ch_names = ["EOG horizontal", "Marker"]
        preserved_raw.get_channel_types.return_value = ["eeg", "eeg"]
        inferred_raw = MagicMock()
        inferred_raw.ch_names = ["horizontal", "Marker"]
        inferred_raw.get_channel_types.return_value = ["eog", "eeg"]
        mock_read_edf.side_effect = [preserved_raw, inferred_raw]

        result = load_edf_file("recording.edf")

        assert result.get_mne() is preserved_raw
        assert mock_read_edf.call_args_list == [
            call("recording.edf", preload=False),
            call(
                "recording.edf",
                preload=False,
                infer_types=True,
                verbose="ERROR",
            ),
        ]
        preserved_raw.set_channel_types.assert_called_once_with(
            {"EOG horizontal": "eog", "Marker": "eeg"},
            on_unit_change="ignore",
        )
        assert result.get_runtime_detail("edf_channel_type_inference") == {
            "status": "applied",
            "method": "mne_edf_infer_types",
            "channel_names_preserved": True,
            "inferred_channel_types": {
                "EOG horizontal": "eog",
                "Marker": "eeg",
            },
            "recognized_prefix_channels": ["EOG horizontal"],
            "defaulted_to_eeg_channels": ["Marker"],
            "claim_boundary": (
                "Channels without an MNE-recognized EDF type prefix retain the "
                "reader's default EEG type; XBrainLab does not guess from names."
            ),
        }
        inferred_raw.close.assert_called_once_with()

    @pytest.mark.parametrize(
        "raw_error",
        [TypeError("not raw"), ValueError("not raw")],
        ids=("type-error", "value-error"),
    )
    def test_load_fif_falls_back_to_epochs(self, raw_error):
        epochs = MagicMock()
        with (
            patch("XBrainLab.backend.load_data.raw.validate_type"),
            patch(
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_fif",
                side_effect=raw_error,
            ) as read_raw,
            patch(
                "XBrainLab.backend.load_data.raw_data_loader.mne.read_epochs",
                return_value=epochs,
            ) as read_epochs,
        ):
            result = load_fif_file("epochs.fif")

        assert result.get_mne() is epochs
        read_raw.assert_called_once_with("epochs.fif", preload=False)
        read_epochs.assert_called_once_with("epochs.fif", preload=False)

    def test_load_fif_reports_raw_failure_when_epochs_fallback_also_fails(self):
        raw_error = ValueError("not raw")
        with (
            patch(
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_fif",
                side_effect=raw_error,
            ),
            patch(
                "XBrainLab.backend.load_data.raw_data_loader.mne.read_epochs",
                side_effect=RuntimeError("epochs unreadable"),
            ),
            pytest.raises(FileCorruptedError) as raised,
        ):
            load_fif_file("broken.fif")

        assert raised.value.__cause__ is raw_error
        assert "Failed to load FIF as Raw or Epochs: not raw" in str(raised.value)

    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_eeglab")
    def test_load_set_raw_success(self, mock_read_eeglab, mock_validate):
        """Test successful SET loading as Raw."""
        mock_raw = MagicMock()
        mock_read_eeglab.return_value = mock_raw

        result = load_set_file("dummy.set")

        mock_read_eeglab.assert_called_once()
        assert isinstance(result, Raw)
        assert result.get_mne() == mock_raw

    @pytest.mark.parametrize(
        "raw_error",
        [TypeError("not raw"), ValueError("not raw")],
        ids=("type-error", "value-error"),
    )
    def test_load_set_falls_back_to_epochs(self, raw_error):
        epochs = MagicMock()
        with (
            patch("XBrainLab.backend.load_data.raw.validate_type"),
            patch(
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_eeglab",
                side_effect=raw_error,
            ) as read_raw,
            patch(
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_epochs_eeglab",
                return_value=epochs,
            ) as read_epochs,
        ):
            result = load_set_file("epochs.set")

        assert result.get_mne() is epochs
        read_raw.assert_called_once_with(
            "epochs.set",
            uint16_codec="latin1",
            preload=False,
        )
        read_epochs.assert_called_once_with("epochs.set", uint16_codec="latin1")

    @pytest.mark.parametrize(
        "raw_error",
        [TypeError("not raw"), ValueError("not raw")],
        ids=("type-error", "value-error"),
    )
    def test_load_set_translates_failure_from_both_readers(self, raw_error):
        epochs_error = RuntimeError("epochs unreadable")
        with (
            patch(
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_eeglab",
                side_effect=raw_error,
            ),
            patch(
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_epochs_eeglab",
                side_effect=epochs_error,
            ),
            pytest.raises(FileCorruptedError) as raised,
        ):
            load_set_file("broken.set")

        assert "broken.set" in str(raised.value)
        if isinstance(raw_error, TypeError):
            assert "Failed to load as Epochs: epochs unreadable" in str(raised.value)
            assert raised.value.__cause__ is epochs_error
        else:
            assert "Failed to load as Raw or Epochs: not raw" in str(raised.value)
            assert raised.value.__cause__ is raw_error

    @patch("XBrainLab.backend.load_data.raw_data_loader.RawDataLoaderFactory.load")
    def test_load_raw_data_returns_factory_result(self, factory_load):
        raw = MagicMock(spec=Raw)
        factory_load.return_value = raw

        assert load_raw_data("recording.edf") is raw
        factory_load.assert_called_once_with("recording.edf")

    @patch("XBrainLab.backend.load_data.raw_data_loader.RawDataLoaderFactory.load")
    def test_load_raw_data_rejects_empty_factory_result(self, factory_load):
        factory_load.return_value = None

        with pytest.raises(
            ValueError,
            match=r"Failed to load raw data from recording\.edf",
        ):
            load_raw_data("recording.edf")
