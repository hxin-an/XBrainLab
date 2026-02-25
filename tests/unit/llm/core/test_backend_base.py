"""Unit tests for LLM backends/base — BaseBackend abstract class."""

import pytest

from XBrainLab.llm.core.backends.base import BaseBackend


class TestBaseBackend:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseBackend()

    def test_subclass_must_implement_load(self):
        class Incomplete(BaseBackend):
            def generate_stream(self, messages):
                yield "test"

        with pytest.raises(TypeError):
            Incomplete()

    def test_subclass_must_implement_generate_stream(self):
        class Incomplete(BaseBackend):
            def load(self):
                pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_complete_subclass(self):
        class Complete(BaseBackend):
            def load(self):
                self.loaded = True

            def generate_stream(self, messages):
                yield "chunk"

        backend = Complete()
        backend.load()
        assert backend.loaded is True
        chunks = list(backend.generate_stream([]))
        assert chunks == ["chunk"]
