from unittest.mock import patch

import pytest

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine


class TestLLMEngineHotSwap:
    @pytest.fixture
    def engine(self):
        """Create an engine instance for testing."""
        # Use explicit config to ensure predictable mode
        config = LLMConfig(inference_mode="local")
        return LLMEngine(config)

    def test_initialization_defaults_to_local(self, engine):
        """Test that default init creates a local backend (or tries to)."""
        # Note: In real run, it imports LocalBackend. We should verify config mode.
        assert engine.config.inference_mode == "local"
        # Lazy loading - backend not created until load_model() called
        assert engine.active_backend is None

    @patch("XBrainLab.llm.core.backends.local.LocalBackend")
    @patch("XBrainLab.llm.core.backends.gemini.GeminiBackend")
    @patch("XBrainLab.llm.core.backends.api.APIBackend")
    def test_switch_backend_caching(self, mock_api, mock_gemini, mock_local, engine):
        """
        Verify that switching backends caches them and doesn't re-instantiate.
        """
        # 1. Setup Mock Config to match Engine Config (prevent stale detection)
        mock_local.return_value.config.model_name = engine.config.model_name
        mock_gemini.return_value.config.gemini_model_name = (
            engine.config.gemini_model_name
        )

        # 2. Switch to Local
        engine.switch_backend("local")
        assert engine.active_backend == mock_local.return_value
        assert "local" in engine.backends
        mock_local.assert_called_once()  # Created once

        # 2. Switch to Gemini
        engine.switch_backend("gemini")
        assert engine.active_backend == mock_gemini.return_value
        assert "gemini" in engine.backends
        mock_gemini.assert_called_once()

        # 3. Switch back to Local (Hot-Swap Check)
        engine.switch_backend("local")
        assert engine.active_backend == mock_local.return_value
        # Should NOT be called again
        mock_local.assert_called_once()

    @patch("XBrainLab.llm.core.backends.local.LocalBackend")
    def test_generate_stream_uses_active_backend(self, mock_local, engine):
        """Verify generate_stream delegates to the active backend."""
        mock_backend_instance = mock_local.return_value
        mock_backend_instance.generate_stream.return_value = iter(["chunk1", "chunk2"])

        engine.switch_backend("local")

        result = list(engine.generate_stream(["msg"]))
        assert result == ["chunk1", "chunk2"]
        mock_backend_instance.generate_stream.assert_called_with(["msg"])
