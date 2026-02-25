"""Unit tests for error_handler module — exception classes and decorator."""

import pytest

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
        @handle_error
        def boom():
            raise KeyError("oops")

        with pytest.raises(XBrainLabError, match="Unexpected error"):
            boom()

    def test_preserves_function_name(self):
        @handle_error
        def my_func():
            pass

        assert my_func.__name__ == "my_func"
