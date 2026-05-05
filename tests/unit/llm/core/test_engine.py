from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.backends.local import LocalBackend
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine

# --- Fixtures ---


@pytest.fixture
def mock_config():
    return LLMConfig(
        model_name=LLMConfig.default_local_model_id(),
        inference_mode="local",
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


def test_engine_init_legacy_remote_request_uses_local(mock_config):
    """Legacy remote mode requests are migrated to local backend creation."""
    mock_config.inference_mode = "api"
    with patch("XBrainLab.llm.core.backends.local.LocalBackend") as MockBackend:
        engine = LLMEngine(mock_config)
        engine.load_model()
        MockBackend.assert_called_once_with(mock_config)
        assert "local" in engine.backends


def test_engine_close_unloads_cached_backends(mock_config):
    engine = LLMEngine(mock_config)
    backend = MagicMock()
    engine.backends["local"] = backend
    engine._backend_model_ids["local"] = mock_config.model_name
    engine.active_backend = backend

    engine.close()

    backend.unload.assert_called_once()
    assert engine.backends == {}
    assert engine._backend_model_ids == {}
    assert engine.active_backend is None


# --- Test LocalBackend ---


@patch("transformers.AutoTokenizer")
@patch("transformers.AutoModelForCausalLM")
def test_local_backend_load_success(mock_model_cls, mock_tokenizer_cls, mock_config):
    backend = LocalBackend(mock_config)

    # Mock return values
    mock_tokenizer = MagicMock()
    mock_tokenizer_cls.from_pretrained.return_value = mock_tokenizer

    mock_model = MagicMock()
    mock_model.to.return_value = mock_model
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


def test_remote_backend_modules_removed():
    import importlib.util

    assert importlib.util.find_spec("XBrainLab.llm.core.backends.api") is None
    assert importlib.util.find_spec("XBrainLab.llm.core.backends.gemini") is None
