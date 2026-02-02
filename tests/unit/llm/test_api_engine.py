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
    with patch("XBrainLab.llm.core.backends.api.OpenAI"):
        engine = LLMEngine(api_config)
        assert isinstance(engine.backend, APIBackend)
        assert engine.backend.config.api_key == "sk-test"  # pragma: allowlist secret


def test_api_backend_load_uses_key(api_config):
    with patch("XBrainLab.llm.core.backends.api.OpenAI") as MockClient:
        engine = LLMEngine(api_config)
        engine.load_model()
        MockClient.assert_called_once_with(
            api_key="sk-test",  # pragma: allowlist secret
            base_url=api_config.base_url,
        )


def test_generate_stream_yields_content(api_config):
    with patch("XBrainLab.llm.core.backends.api.OpenAI") as MockClient:
        # Mock the stream response
        mock_chunk = MagicMock()
        mock_chunk.choices[0].delta.content = "Hello"

        mock_stream = iter([mock_chunk])

        mock_instance = MockClient.return_value
        mock_instance.chat.completions.create.return_value = mock_stream

        engine = LLMEngine(api_config)

        chunks = list(engine.generate_stream([{"role": "user", "content": "Hi"}]))

        assert chunks == ["Hello"]
        mock_instance.chat.completions.create.assert_called_once()
