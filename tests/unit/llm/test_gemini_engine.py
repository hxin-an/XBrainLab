from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import GeminiBackend, LLMEngine


@pytest.fixture
def gemini_config():
    config = LLMConfig()
    config.inference_mode = "gemini"
    config.gemini_api_key = "gemini-test-key"  # pragma: allowlist secret
    config.gemini_model_name = "gemini-mock"
    return config


def test_engine_initializes_gemini_backend(gemini_config):
    # Mock genai import at module level
    with patch("XBrainLab.llm.core.engine.genai"):
        engine = LLMEngine(gemini_config)
        assert isinstance(engine.backend, GeminiBackend)


def test_gemini_backend_load_initializes_client(gemini_config):
    with patch("XBrainLab.llm.core.engine.genai") as mock_genai:
        engine = LLMEngine(gemini_config)
        engine.load_model()
        # Verify Client is initialized with key
        # Verify Client is initialized with key
        mock_genai.Client.assert_called_once_with(
            api_key="gemini-test-key"  # pragma: allowlist secret
        )


def test_gemini_generate_stream(gemini_config):
    with patch("XBrainLab.llm.core.engine.genai") as mock_genai:
        # Mock Client and Chats
        mock_client = mock_genai.Client.return_value
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        # Mock response chunk
        mock_chunk = MagicMock()
        mock_chunk.text = "Gemini Response"

        # chat.send_message_stream returns an iterator
        mock_chat.send_message_stream.return_value = iter([mock_chunk])

        engine = LLMEngine(gemini_config)

        # Run generation
        messages = [{"role": "user", "content": "Hi"}]
        chunks = list(engine.generate_stream(messages))

        assert chunks == ["Gemini Response"]

        # Verify call arguments
        mock_client.chats.create.assert_called_once()
        # Verify history construction (empty for single message)
        _args, kwargs = mock_client.chats.create.call_args
        assert kwargs["model"] == "gemini-mock"
        assert kwargs["history"] == []

        mock_chat.send_message_stream.assert_called_once_with("Hi")
