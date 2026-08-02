"""Unit tests for error_handler module — exception classes and decorator."""

import traceback

import pytest

from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.backend.utils import error_handler as error_handler_module
from XBrainLab.backend.utils.error_handler import (
    AgentError,
    DataNotLoadedError,
    PreprocessingError,
    XBrainLabError,
    handle_error,
)


class TestExceptionHierarchy:
    def test_base_is_exception(self):
        assert issubclass(XBrainLabError, Exception)

    def test_subclasses(self):
        assert issubclass(DataNotLoadedError, XBrainLabError)
        assert issubclass(PreprocessingError, XBrainLabError)
        assert issubclass(AgentError, XBrainLabError)

    def test_raise_and_catch(self):
        with pytest.raises(XBrainLabError):
            raise DataNotLoadedError("no data")

        with pytest.raises(XBrainLabError):
            raise PreprocessingError("bad data")

        with pytest.raises(XBrainLabError):
            raise AgentError("agent fail")


class TestHandleErrorDecorator:
    def test_normal_execution(self):
        @handle_error
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_xbrainlab_error_reraises(self):
        @handle_error
        def boom():
            raise DataNotLoadedError("missing")

        with pytest.raises(DataNotLoadedError, match="missing"):
            boom()

    def test_unexpected_error_wrapped(self):
        private_path = "/srv/clinical/sub-P001/events.tsv"
        private_values = (private_path, "Mary Example", "private-secret")
        raw_message = (
            f"Could not read {private_path}; subject_id=Mary Example; "
            "api_key=private-secret\r\nFORGED TRACEBACK"
        )

        @handle_error
        def boom():
            raise KeyError(raw_message)

        with pytest.raises(XBrainLabError, match="Unexpected error") as caught:
            boom()

        formatted = "".join(traceback.format_exception(caught.value))

        assert all(
            private_value in caught.value.message for private_value in private_values
        )
        assert all(
            private_value not in str(caught.value) for private_value in private_values
        )
        assert all(private_value not in formatted for private_value in private_values)
        assert "\r" not in str(caught.value)
        assert "\n" not in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__suppress_context__ is True

    def test_application_error_wrap_preserves_raw_message_for_local_recovery(self):
        private_path = "/srv/clinical/sub-P001/events.tsv"

        @handle_error
        def boom():
            raise ApplicationError(
                message=f"Could not read {private_path}",
                error_type=ErrorType.RUNTIME,
            )

        with pytest.raises(XBrainLabError) as caught:
            boom()

        assert private_path in caught.value.message
        assert private_path not in str(caught.value)

    def test_unexpected_error_does_not_materialize_custom_exception_string(self):
        private_path = "/srv/clinical/sub-P001/events.tsv"

        class UntrustedError(Exception):
            def __str__(self) -> str:
                raise AssertionError("Unexpected exceptions must not be stringified.")

        @handle_error
        def boom():
            raise UntrustedError(f"Could not read {private_path}")

        with pytest.raises(XBrainLabError) as caught:
            boom()

        assert private_path in caught.value.message
        assert private_path not in str(caught.value)

    def test_xbrainlab_error_with_hostile_accessors_is_reraised_unchanged(
        self,
        monkeypatch,
    ):
        class NaiveLogger:
            def error(self, template, *args):
                _ = template % args

        monkeypatch.setattr(error_handler_module, "logger", NaiveLogger())

        class HostileXBrainLabError(XBrainLabError):
            _armed = False

            def __getattribute__(self, name):
                if name == "_armed":
                    return object.__getattribute__(self, name)
                if object.__getattribute__(self, "_armed") and name in {
                    "args",
                    "message",
                }:
                    raise AssertionError(f"hostile {name} accessor executed")
                return object.__getattribute__(self, name)

            def __str__(self):
                raise AssertionError("hostile exception string protocol executed")

        error = HostileXBrainLabError("/srv/private/patient-Jane/session.edf")
        object.__setattr__(error, "_armed", True)

        @handle_error
        def boom():
            raise error

        with pytest.raises(HostileXBrainLabError) as caught:
            boom()

        assert caught.value is error

    def test_unexpected_error_uses_base_storage_without_hostile_protocols(self):
        private_path = "/srv/private/patient-Jane/session.edf"

        class HostileUnexpectedError(Exception):
            def __getattribute__(self, name):
                if name in {"args", "message"}:
                    raise AssertionError(f"hostile {name} accessor executed")
                return object.__getattribute__(self, name)

            def __str__(self):
                raise AssertionError("hostile exception string protocol executed")

        @handle_error
        def boom():
            raise HostileUnexpectedError(f"Could not read {private_path}")

        with pytest.raises(XBrainLabError) as caught:
            boom()

        assert private_path in caught.value.message
        assert private_path not in str(caught.value)

    def test_preserves_function_name(self):
        @handle_error
        def my_func():
            pass

        assert my_func.__name__ == "my_func"
