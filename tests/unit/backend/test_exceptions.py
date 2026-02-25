"""Unit tests for custom exception classes."""

import pytest

from XBrainLab.backend.exceptions import (
    DataMismatchError,
    FileCorruptedError,
    UnsupportedFormatError,
    XBrainLabError,
)


class TestXBrainLabError:
    def test_base_exception(self):
        err = XBrainLabError("base msg")
        assert str(err) == "base msg"
        assert isinstance(err, Exception)

    def test_raise_and_catch(self):
        with pytest.raises(XBrainLabError, match="test"):
            raise XBrainLabError("test")


class TestFileCorruptedError:
    def test_message_includes_path(self):
        path = "eeg_data/file.gdf"
        err = FileCorruptedError(path)
        assert path in str(err)
        assert err.filepath == path
        assert isinstance(err, XBrainLabError)

    def test_custom_message(self):
        err = FileCorruptedError("/f.gdf", message="CRC check failed")
        assert "CRC check failed" in str(err)
        assert "/f.gdf" in str(err)


class TestUnsupportedFormatError:
    def test_message_includes_extension(self):
        err = UnsupportedFormatError(".xyz")
        assert ".xyz" in str(err)
        assert err.file_extension == ".xyz"
        assert isinstance(err, XBrainLabError)

    def test_custom_message(self):
        err = UnsupportedFormatError(".abc", message="Cannot read")
        assert "Cannot read" in str(err)
        assert ".abc" in str(err)


class TestDataMismatchError:
    def test_default_message(self):
        err = DataMismatchError()
        assert "mismatch" in str(err).lower()
        assert isinstance(err, XBrainLabError)

    def test_custom_message(self):
        err = DataMismatchError("sfreq differs: 256 vs 512")
        assert "256" in str(err)
