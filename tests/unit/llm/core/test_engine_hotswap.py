from unittest.mock import MagicMock, patch

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
    def test_switch_backend_caching(self, mock_local, engine):
        """
        Verify that local backend caching survives legacy remote requests.
        """
        # 1. Setup Mock Config to match Engine Config (prevent stale detection)
        mock_local.return_value.config.model_name = engine.config.model_name

        # 2. Switch to Local
        engine.switch_backend("local")
        assert engine.active_backend == mock_local.return_value
        assert "local" in engine.backends
        mock_local.assert_called_once()  # Created once

        # 2. A legacy remote request resolves to the cached local backend.
        engine.switch_backend("gemini")
        assert engine.active_backend == mock_local.return_value
        assert "gemini" not in engine.backends

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

    @patch("XBrainLab.llm.core.backends.local.LocalBackend")
    def test_failed_hot_swap_restores_previous_backend(self, mock_local, engine):
        old_model_id = engine.config.model_name
        old_backend = MagicMock()
        old_backend.config = engine.config
        engine.backends["local"] = old_backend
        engine._backend_model_ids["local"] = old_model_id
        engine.active_backend = old_backend
        new_model_id = LLMConfig.fallback_local_model_id()
        assert new_model_id != old_model_id
        engine.config.apply_runtime_selection("local", model_id=new_model_id)
        replacement = mock_local.return_value
        replacement.load.side_effect = RuntimeError("replacement load failed")

        with pytest.raises(RuntimeError, match="replacement load failed"):
            engine.switch_backend("local")

        replacement.unload.assert_called_once()
        old_backend.unload.assert_called_once()
        old_backend.load.assert_called_once()
        assert engine.config.model_name == old_model_id
        assert engine.backends["local"] is old_backend
        assert engine.active_backend is old_backend
        assert engine._backend_model_ids["local"] == old_model_id
