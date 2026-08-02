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

    def test_public_text_is_redacted_without_mutating_internal_arguments(self):
        private_path = "/srv/private/sub-P001/session.edf"
        raw_message = (
            f"Could not read {private_path}; subject_id=Mary Example; "
            "api_key=private-secret\r\nFORGED TRACEBACK"
        )
        err = XBrainLabError(raw_message)

        assert err.args == (raw_message,)
        assert err.message == raw_message
        assert private_path not in str(err)
        assert private_path not in repr(err)
        assert "Mary Example" not in str(err)
        assert "private-secret" not in str(err)
        assert "\r" not in str(err)
        assert "\n" not in str(err)
        assert "session.edf" in str(err)
        assert "[REDACTED_PATH]" in str(err)
        assert "[REDACTED_SECRET]" in str(err)
        assert "sub-P001" not in str(err)

    def test_hostile_message_subclass_fails_closed_without_rendering(self):
        class HostileMessage(str):
            def __str__(self) -> str:
                raise AssertionError("hostile message must not be rendered")

            def __format__(self, format_spec: str) -> str:
                raise AssertionError("hostile message must not be formatted")

        err = XBrainLabError(HostileMessage("/srv/private/sub-P001/session.edf"))

        assert err.message == "[UNSUPPORTED_VALUE]"
        assert str(err) == "[UNSUPPORTED_VALUE]"


class TestFileCorruptedError:
    def test_message_includes_path(self):
        path = "eeg_data/file.gdf"
        err = FileCorruptedError(path)
        assert path not in str(err)
        assert "file.gdf" not in str(err)
        assert ".gdf" in str(err)
        assert "[REDACTED_PATH]" in str(err)
        assert err.filepath == path
        assert isinstance(err, XBrainLabError)

    def test_custom_message(self):
        err = FileCorruptedError("/f.gdf", message="CRC check failed")
        assert "CRC check failed" in str(err)
        assert "/f.gdf" not in str(err)
        assert "f.gdf" in str(err)
        assert "[REDACTED_PATH]" in str(err)
        assert err.message == "CRC check failed: /f.gdf"
        assert err.filepath == "/f.gdf"

    def test_hostile_path_and_message_components_fail_closed(self):
        class HostileComponent:
            def __str__(self) -> str:
                raise AssertionError("hostile component must not be rendered")

            def __format__(self, format_spec: str) -> str:
                raise AssertionError("hostile component must not be formatted")

        err = FileCorruptedError(HostileComponent(), message=HostileComponent())

        assert err.message == "[UNSUPPORTED_VALUE]: [UNSUPPORTED_VALUE]"
        assert str(err) == "[UNSUPPORTED_VALUE]: [UNSUPPORTED_VALUE]"


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
