"""Unit tests for LocalBackend — message processing, init, and stream API."""

from unittest.mock import MagicMock

import pytest

from XBrainLab.llm.core.backends.local import LocalBackend
from XBrainLab.llm.core.config import LLMConfig


@pytest.fixture
def config():
    cfg = LLMConfig()
    cfg.device = "cpu"
    cfg.model_name = "test-model"
    cfg.cache_dir = "test_cache_dir"
    cfg.load_in_4bit = False
    return cfg


@pytest.fixture
def backend(config):
    return LocalBackend(config)


class TestInit:
    def test_initial_state(self, backend):
        assert backend.model is None
        assert backend.tokenizer is None
        assert backend.is_loaded is False

    def test_stores_config(self, backend, config):
        assert backend.config is config


class TestProcessMessages:
    def test_empty_messages(self, backend):
        result = backend._process_messages_for_template([])
        assert result == []

    def test_system_merged_into_first_user(self, backend):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        result = backend._process_messages_for_template(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "You are helpful." in result[0]["content"]
        assert "Hello" in result[0]["content"]

    def test_system_only_creates_user_message(self, backend):
        messages = [{"role": "system", "content": "Instructions"}]
        result = backend._process_messages_for_template(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "Instructions" in result[0]["content"]

    def test_consecutive_same_role_merged(self, backend):
        messages = [
            {"role": "user", "content": "msg1"},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": "reply"},
        ]
        result = backend._process_messages_for_template(messages)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert "msg1" in result[0]["content"]
        assert "msg2" in result[0]["content"]
        assert result[1]["role"] == "assistant"

    def test_alternating_roles_preserved(self, backend):
        messages = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
        ]
        result = backend._process_messages_for_template(messages)
        assert len(result) == 3

    def test_no_system_passthrough(self, backend):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        result = backend._process_messages_for_template(messages)
        assert len(result) == 2
        assert result[0]["content"] == "Hello"


class TestGenerateStream:
    def test_raises_if_not_loaded(self, backend):
        # Mock load to do nothing (don't actually download model)
        backend.load = MagicMock(side_effect=RuntimeError("no model"))
        with pytest.raises(RuntimeError):
            list(backend.generate_stream([{"role": "user", "content": "hi"}]))
