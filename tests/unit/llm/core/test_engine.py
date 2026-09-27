from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.application.resource_guard import ResourceChecker
from XBrainLab.llm.core.backends.local import LocalBackend
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.generation import GenerationProfile

# --- Fixtures ---


@pytest.fixture
def mock_config():
    return LLMConfig(
        model_name=LLMConfig.default_local_model_id(),
        inference_mode="local",
    )


@pytest.fixture
def safe_cpu_model_load_ram(monkeypatch):
    """Keep mocked model materialization independent of host memory pressure."""
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "total_bytes": 64 * 1024**3,
                "available_bytes": 48 * 1024**3,
                "used_bytes": 16 * 1024**3,
            }
        ),
    )


# --- Test LLMEngine Factory ---
# Backend allocation is lazy; only load_model() creates it.


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
        assert engine.active_backend is MockBackend.return_value


def test_engine_close_unloads_once_and_can_load_after_release(mock_config):
    engine = LLMEngine(mock_config)
    backend = MagicMock()
    replacement = MagicMock()
    with patch(
        "XBrainLab.llm.core.backends.local.LocalBackend",
        side_effect=[backend, replacement],
    ) as factory:
        engine.load_model()
        engine.load_model()
        factory.assert_called_once_with(mock_config)
        backend.load.assert_called_once()
        assert engine.close() is True
        assert engine.close() is True
        backend.unload.assert_called_once()
        assert engine.active_backend is None
        engine.load_model()
        assert engine.active_backend is replacement
        assert engine.close() is True
        replacement.unload.assert_called_once()


def test_engine_unloads_partially_initialized_backend_when_load_fails(mock_config):
    backend = MagicMock()
    backend.load.side_effect = RuntimeError("partial load failed")
    with patch(
        "XBrainLab.llm.core.backends.local.LocalBackend",
        return_value=backend,
    ):
        engine = LLMEngine(mock_config)

        with pytest.raises(RuntimeError, match="partial load failed"):
            engine.load_model()

    backend.unload.assert_called_once()
    assert engine.active_backend is None
    assert engine.close() is True
    backend.unload.assert_called_once()


@pytest.mark.parametrize("first_cleanup", [False, OSError("cleanup failed")])
@pytest.mark.parametrize("injected", [False, True])
def test_failed_load_retains_backend_until_cleanup_really_finishes(
    mock_config, first_cleanup, injected
):
    backend = MagicMock()
    backend.load.side_effect = RuntimeError("partial load failed")
    backend.unload.side_effect = [first_cleanup, False, True]
    with patch(
        "XBrainLab.llm.core.backends.local.LocalBackend", return_value=backend
    ) as factory:
        engine = LLMEngine(mock_config, backend_factory=factory if injected else None)
        with pytest.raises(RuntimeError, match="partial load failed"):
            engine.load_model()

        assert engine.active_backend is None
        with pytest.raises(RuntimeError, match="No active backend"):
            list(
                engine.generate_stream(
                    [], profile=GenerationProfile.STRUCTURED_DECISION
                )
            )
        assert engine.close() is False
        assert backend.unload.call_count == 2
        with pytest.raises(RuntimeError, match="cleanup"):
            engine.load_model()
        factory.assert_called_once_with(mock_config)
        backend.load.assert_called_once()
        engine.cancel_generation(wait_timeout=0.01)
        backend.cancel_generation.assert_called_once_with(wait_timeout=0.01)
        assert engine.close() is True
        assert backend.unload.call_count == 3
        assert engine.close() is True
        assert backend.unload.call_count == 3


@pytest.mark.parametrize("first_cleanup", [False, OSError("cleanup failed")])
def test_close_retires_readiness_but_retries_the_exact_backend(
    mock_config, first_cleanup
):
    backend = MagicMock()
    backend.unload.side_effect = [first_cleanup, True]
    with patch("XBrainLab.llm.core.backends.local.LocalBackend", return_value=backend):
        engine = LLMEngine(mock_config)
        engine.load_model()
        assert engine.active_backend is backend

        assert engine.close() is False
        assert engine.active_backend is None
        with pytest.raises(RuntimeError, match="No active backend"):
            list(
                engine.generate_stream(
                    [], profile=GenerationProfile.STRUCTURED_DECISION
                )
            )
        assert engine.close() is True
        assert backend.unload.call_count == 2


@patch("transformers.AutoTokenizer")
@patch("transformers.AutoModelForCausalLM")
def test_engine_cleans_real_local_backend_after_partial_model_load(
    model_class,
    tokenizer_class,
    mock_config,
    safe_cpu_model_load_ram,
):
    mock_config.device = "cpu"
    mock_config.load_in_4bit = False
    tokenizer_class.from_pretrained.return_value = MagicMock()
    model_class.from_pretrained.side_effect = RuntimeError("model load failed")
    original_unload = LocalBackend.unload
    with patch.object(
        LocalBackend,
        "unload",
        autospec=True,
        side_effect=original_unload,
    ) as unload:
        engine = LLMEngine(mock_config)

        with pytest.raises(RuntimeError, match="model load failed"):
            engine.load_model()

    unload.assert_called_once()
    backend = unload.call_args.args[0]
    assert backend.tokenizer is None
    assert backend.model is None
    assert backend.is_loaded is False


# --- Test LocalBackend ---


@patch("transformers.AutoTokenizer")
@patch("transformers.AutoModelForCausalLM")
def test_local_backend_load_success(
    mock_model_cls,
    mock_tokenizer_cls,
    mock_config,
    safe_cpu_model_load_ram,
):
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


def test_remote_backend_modules_removed():
    import importlib.util

    assert importlib.util.find_spec("XBrainLab.llm.core.backends.api") is None
    assert importlib.util.find_spec("XBrainLab.llm.core.backends.gemini") is None


@pytest.mark.parametrize("retired_mode", ("api", "gemini"))
def test_retired_remote_mode_migrates_to_local_runtime(retired_mode: str) -> None:
    config = LLMConfig(inference_mode=retired_mode)

    assert config.inference_mode == "local"
    assert config.assistant_runtime_selection().backend_mode == "local"
