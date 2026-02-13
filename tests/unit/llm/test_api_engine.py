from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.backends.api import APIBackend
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine


@pytest.fixture
def api_config():
    config = LLMConfig()
    config.inference_mode = "api"
    config.api_key = "sk-test"  # pragma: allowlist secret
    config.api_model_name = "gpt-mock"
    return config


def test_engine_initializes_api_backend(api_config):
    """Test that engine can load API backend via load_model."""
    with patch("XBrainLab.llm.core.backends.api.OpenAI"):
        engine = LLMEngine(api_config)
        # Lazy loading pattern - call load_model to create backend
        engine.load_model()
        assert isinstance(engine.active_backend, APIBackend)
        assert (
            engine.active_backend.config.api_key
            == "sk-test"  # pragma: allowlist secret
        )


def test_api_backend_load_uses_key(api_config):
    """Test that load_model triggers API client creation with correct key."""
    with patch("XBrainLab.llm.core.backends.api.OpenAI") as MockClient:
        engine = LLMEngine(api_config)
        engine.load_model()
        # API backend is lazy - need to explicitly call load() on the active_backend
        engine.active_backend.load()
        MockClient.assert_called_once_with(
            api_key="sk-test",  # pragma: allowlist secret
            base_url=api_config.base_url,
        )


def test_generate_stream_yields_content(api_config):
    """Test that generate_stream delegates to the active backend and yields content."""
    with patch("XBrainLab.llm.core.backends.api.OpenAI") as MockClient:
        # Mock the stream response
        mock_chunk = MagicMock()
        mock_chunk.choices[0].delta.content = "Hello"

        mock_stream = iter([mock_chunk])

        mock_instance = MockClient.return_value
        mock_instance.chat.completions.create.return_value = mock_stream

        engine = LLMEngine(api_config)
        # Must load model first to create active backend
        engine.load_model()

        chunks = list(engine.generate_stream([{"role": "user", "content": "Hi"}]))

        assert chunks == ["Hello"]
        mock_instance.chat.completions.create.assert_called_once()
