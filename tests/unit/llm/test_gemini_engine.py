from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.backends.gemini import GeminiBackend
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine


@pytest.fixture
def gemini_config():
    config = LLMConfig()
    config.inference_mode = "gemini"
    config.gemini_api_key = "gemini-test-key"  # pragma: allowlist secret
    config.gemini_model_name = "gemini-mock"
    return config


def test_engine_initializes_gemini_backend(gemini_config):
    """Test that engine can load Gemini backend via load_model."""
    # Mock genai import at module level
    with patch("XBrainLab.llm.core.backends.gemini.genai"):
        engine = LLMEngine(gemini_config)
        # Lazy loading - call load_model to create backend
        engine.load_model()
        assert isinstance(engine.active_backend, GeminiBackend)


def test_gemini_backend_load_initializes_client(gemini_config):
    """Test that load triggers genai.Client initialization."""
    with patch("XBrainLab.llm.core.backends.gemini.genai") as mock_genai:
        engine = LLMEngine(gemini_config)
        engine.load_model()
        # Gemini backend is lazy - need to explicitly call load() on the active_backend
        engine.active_backend.load()
        # Verify Client is initialized with key
        mock_genai.Client.assert_called_once_with(
            api_key="gemini-test-key"  # pragma: allowlist secret
        )


def test_gemini_generate_stream(gemini_config):
    """Test that generate_stream delegates to Gemini backend."""
    with patch("XBrainLab.llm.core.backends.gemini.genai") as mock_genai:
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
        # Must load model first to create active backend
        engine.load_model()

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
