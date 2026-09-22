import logging
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


def test_real_epochs_fif_fallback_is_debug_not_warning(
    tmp_path,
    capture_product_logs,
) -> None:
    """MNE-native epoched FIF support must not warn while probing Raw first."""
    path = tmp_path / "subject01_epo.fif"
    epochs = mne.EpochsArray(
        np.zeros((2, 1, 20)),
        mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg"),
        events=np.array([[0, 0, 1], [30, 0, 1]]),
        event_id={"event": 1},
        verbose="ERROR",
    )
    epochs.save(path, overwrite=True, verbose="ERROR")

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        with capture_product_logs(level=logging.DEBUG) as caplog:
            loaded = load_fif_file(str(path))

    assert isinstance(loaded, Raw)
    assert isinstance(loaded.get_mne(), mne.BaseEpochs)
    assert any(
        "does not conform to MNE naming conventions" in str(item.message)
        for item in caught_warnings
    )
    messages = [record.getMessage() for record in caplog.records]
    assert any("Failed to load FIF as Raw" in message for message in messages)
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


def test_set_epochs_probe_is_debug_not_warning(capture_product_logs) -> None:
    """An expected EEGLAB raw-reader rejection must stay diagnostic-only."""
    epochs = mne.EpochsArray(
        np.zeros((2, 1, 20)),
        mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg"),
        events=np.array([[0, 0, 1], [30, 0, 1]]),
        event_id={"event": 1},
        verbose="ERROR",
    )
    with (
        patch(
            "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_eeglab",
            side_effect=ValueError("not continuous raw"),
        ),
        patch(
            "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_epochs_eeglab",
            return_value=epochs,
        ),
        capture_product_logs(level=logging.DEBUG) as caplog,
    ):
        loaded = load_set_file("epoched.set")

    assert isinstance(loaded, Raw)
    assert loaded.get_mne() is epochs
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "Failed to load as Raw; trying epochs" in message for message in messages
    )
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


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
        assert result.get_runtime_signals()
        assert (
            "auto-renaming duplicate channel names" in result.get_runtime_signals()[0]
        )
        assert result.get_runtime_detail("gdf_duplicate_channel_names") is not None
        assert result.get_gdf_duplicate_channel_detail() is not None
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

    @pytest.mark.parametrize(
        "pattern",
        ["known", "changed_name", "swapped_order", "missing_channel"],
    )
    def test_load_gdf_normalizes_only_exact_graz_2a_channel_pattern(
        self,
        pattern,
        capture_product_logs,
    ):
        """Restore only known labels, preserving waveforms and channel order."""
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
        canonical_names = [
            "EEG-Fz",
            "EEG-FC3",
            "EEG-FC1",
            "EEG-FCz",
            "EEG-FC2",
            "EEG-FC4",
            "EEG-C5",
            "EEG-C3",
            "EEG-C1",
            "EEG-Cz",
            "EEG-C2",
            "EEG-C4",
            "EEG-C6",
            "EEG-CP3",
            "EEG-CP1",
            "EEG-CPz",
            "EEG-CP2",
            "EEG-CP4",
            "EEG-P1",
            "EEG-Pz",
            "EEG-P2",
            "EEG-POz",
            "EOG-left",
            "EOG-central",
            "EOG-right",
        ]
        if pattern == "changed_name":
            ch_names[0] = "EEG-Fpz"
        elif pattern == "swapped_order":
            ch_names[1], ch_names[2] = ch_names[2], ch_names[1]
        elif pattern == "missing_channel":
            ch_names.pop()

        # Distinct rows detect channel reordering as well as waveform mutation.
        waveform = np.arange(len(ch_names) * 40, dtype=float).reshape(-1, 40) * 1e-6
        source = mne.io.RawArray(
            waveform,
            mne.create_info(
                ch_names,
                sfreq=250.0,
                ch_types=[
                    "eog" if name.startswith("EOG") else "eeg" for name in ch_names
                ],
            ),
            verbose="ERROR",
        )
        original_names = source.ch_names.copy()
        original_waveform = source.get_data().copy()
        original_types = source.get_channel_types()

        def fake_read(*args, **kwargs):
            warnings.warn(
                "Channel names are not unique, found duplicates for: {'EEG'}. "
                "Applying running numbers for duplicates.",
                RuntimeWarning,
                stacklevel=1,
            )
            return source

        with (
            patch(
                "XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_gdf",
                side_effect=fake_read,
            ) as reader,
            warnings.catch_warnings(record=True) as caught_warnings,
            capture_product_logs(level=logging.INFO) as caplog,
        ):
            warnings.simplefilter("always")
            result = load_gdf_file("A01T.gdf")

        reader.assert_called_once_with("A01T.gdf", preload=False)
        assert isinstance(result, Raw)
        loaded = result.get_mne()
        assert loaded is source
        np.testing.assert_array_equal(loaded.get_data(), original_waveform)
        assert loaded.get_channel_types() == original_types
        assert loaded.info["sfreq"] == 250.0
        detail = result.get_gdf_duplicate_channel_detail()
        assert detail is not None
        assert detail["kind"] == "gdf_duplicate_channel_names"
        assert detail["filepath"] == "A01T.gdf"
        assert detail["generated_bases"] == ["EEG"]
        assert "EEG-0" in detail["generated_channels"]
        duplicate_warning = any(
            "Channel names are not unique" in str(caught_warning.message)
            for caught_warning in caught_warnings
        )
        if pattern == "known":
            assert loaded.ch_names == canonical_names
            assert result.get_runtime_signals() == []
            assert detail["resolved"] is True
            assert detail["normalization_name"] == "graz_2a_canonical_22"
            assert detail["normalized_channels"] == [
                normalized
                for original, normalized in zip(
                    original_names, canonical_names, strict=True
                )
                if original != normalized
            ]
            assert not duplicate_warning
            assert [
                record.levelno
                for record in caplog.records
                if record.getMessage() == detail["message"]
            ] == [logging.INFO]
            assert not any(
                record.levelno >= logging.WARNING for record in caplog.records
            )
        else:
            assert loaded.ch_names == original_names
            assert not detail.get("resolved", False)
            assert "normalization_name" not in detail
            assert "normalized_channels" not in detail
            assert result.get_runtime_signals() == [detail["message"]]
            assert "auto-renaming duplicate channel names" in detail["message"]
            assert duplicate_warning
            assert [
                record.levelno
                for record in caplog.records
                if record.getMessage() == detail["message"]
            ] == [logging.WARNING]

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

        mock_read_eeglab.assert_called_once_with(
            "dummy.set", uint16_codec="latin1", preload=False
        )
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
