from unittest.mock import ANY, MagicMock, patch

import pytest

from XBrainLab.llm.core.backends.api import APIBackend
from XBrainLab.llm.core.backends.gemini import GeminiBackend
from XBrainLab.llm.core.backends.local import LocalBackend
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine

# --- Fixtures ---


@pytest.fixture
def mock_config():
    return LLMConfig(
        model_name="test-model",
        inference_mode="local",
        api_key="test-key",  # pragma: allowlist secret
        gemini_api_key="test-gemini-key",  # pragma: allowlist secret
    )


# --- Test LLMEngine Factory ---
# NOTE: LLMEngine now uses lazy loading. Backend is not created until load_model() or switch_backend() is called.


def test_engine_init_local(mock_config):
    """Test that engine can be initialized with local mode and load_model creates backend."""
    mock_config.inference_mode = "local"
    with patch("XBrainLab.llm.core.backends.local.LocalBackend") as MockBackend:
        engine = LLMEngine(mock_config)
        # Lazy loading - backend not created yet
        assert engine.active_backend is None

        # Call load_model to trigger backend creation
        engine.load_model()
        assert engine.active_backend is not None
        MockBackend.assert_called_once_with(mock_config)


def test_engine_init_api(mock_config):
    """Test that engine can load API backend."""
    mock_config.inference_mode = "api"
    with patch("XBrainLab.llm.core.backends.api.APIBackend") as MockBackend:
        engine = LLMEngine(mock_config)
        engine.load_model()
        MockBackend.assert_called_with(mock_config)


def test_engine_init_gemini(mock_config):
    """Test that engine can load Gemini backend."""
    mock_config.inference_mode = "gemini"
    with patch("XBrainLab.llm.core.backends.gemini.GeminiBackend") as MockBackend:
        engine = LLMEngine(mock_config)
        engine.load_model()
        MockBackend.assert_called_with(mock_config)


# --- Test LocalBackend ---


@patch("transformers.AutoTokenizer")
@patch("transformers.AutoModelForCausalLM")
def test_local_backend_load_success(mock_model_cls, mock_tokenizer_cls, mock_config):
    backend = LocalBackend(mock_config)

    # Mock return values
    mock_tokenizer = MagicMock()
    mock_tokenizer_cls.from_pretrained.return_value = mock_tokenizer

    mock_model = MagicMock()
    mock_model_cls.from_pretrained.return_value = mock_model

    backend.load()

    assert backend.is_loaded
    assert backend.tokenizer == mock_tokenizer
    assert backend.model == mock_model
    mock_tokenizer_cls.from_pretrained.assert_called()


def test_local_backend_template_processing(mock_config):
    """Test the template processing logic (merging system prompts)."""
    backend = LocalBackend(mock_config)

    messages = [
        {"role": "system", "content": "SysInst"},
        {"role": "user", "content": "Query"},
    ]

    processed = backend._process_messages_for_template(messages)

    assert len(processed) == 1
    assert processed[0]["role"] == "user"
    assert "[Instructions]" in processed[0]["content"]
    assert "SysInst" in processed[0]["content"]
    assert "Query" in processed[0]["content"]


# --- Test APIBackend ---


@patch("XBrainLab.llm.core.backends.api.OpenAI")
def test_api_backend_load_success(mock_openai_cls, mock_config):
    backend = APIBackend(mock_config)
    backend.load()

    assert backend.client is not None
    mock_openai_cls.assert_called_with(
        api_key="test-key",  # pragma: allowlist secret
        base_url=ANY,
    )


@patch("XBrainLab.llm.core.backends.api.OpenAI")
def test_api_backend_generate_stream(mock_openai_cls, mock_config):
    backend = APIBackend(mock_config)

    # Mock client and stream
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock()]
    mock_chunk.choices[0].delta.content = "Hello"

    mock_client.chat.completions.create.return_value = [mock_chunk]

    # Run
    generator = backend.generate_stream([{"role": "user", "content": "Hi"}])
    result = list(generator)

    assert result == ["Hello"]
    mock_client.chat.completions.create.assert_called_once()


# --- Test GeminiBackend ---


@patch("XBrainLab.llm.core.backends.gemini.genai")
def test_gemini_backend_load_success(mock_genai, mock_config):
    # Setup mock to exist (simulate import success)
    backend = GeminiBackend(mock_config)

    backend.load()

    mock_genai.Client.assert_called_with(
        api_key="test-gemini-key"  # pragma: allowlist secret
    )
    assert backend.client is not None


@patch("XBrainLab.llm.core.backends.gemini.genai")
def test_gemini_backend_generate_stream(mock_genai, mock_config):
    backend = GeminiBackend(mock_config)

    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client

    mock_chat = MagicMock()
    mock_client.chats.create.return_value = mock_chat

    # Mock stream response
    mock_chunk = MagicMock()
    mock_chunk.text = "GeminiResponse"
    mock_chat.send_message_stream.return_value = [mock_chunk]

    generator = backend.generate_stream([{"role": "user", "content": "Hi"}])
    result = list(generator)

    assert result == ["GeminiResponse"]
    mock_client.chats.create.assert_called()  # Verifies session creation with history logic
