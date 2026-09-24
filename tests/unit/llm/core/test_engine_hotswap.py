from unittest.mock import patch

import pytest

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.generation import (
    GenerationProfile,
    ResolvedGenerationOptions,
)


class TestLLMEngineGeneration:
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
    def test_generate_stream_uses_active_backend(self, mock_local, engine):
        """Verify generate_stream delegates to the active backend."""
        mock_backend_instance = mock_local.return_value
        mock_backend_instance.generate_stream.return_value = iter(["chunk1", "chunk2"])

        engine.load_model()

        result = list(
            engine.generate_stream(
                ["msg"],
                profile=GenerationProfile.INFORMATIONAL_TEXT,
            )
        )
        assert result == ["chunk1", "chunk2"]
        mock_backend_instance.generate_stream.assert_called_with(
            ["msg"],
            options=ResolvedGenerationOptions(
                max_new_tokens=engine.config.max_new_tokens,
                do_sample=True,
                temperature=engine.config.temperature,
                top_p=engine.config.top_p,
            ),
        )

    @patch("XBrainLab.llm.core.backends.local.LocalBackend")
    def test_generate_stream_forwards_generation_profile(self, mock_local, engine):
        mock_backend_instance = mock_local.return_value
        mock_backend_instance.generate_stream.return_value = iter(["chunk"])
        engine.load_model()

        result = list(
            engine.generate_stream(
                ["msg"],
                profile=GenerationProfile.STRUCTURED_DECISION,
            )
        )

        assert result == ["chunk"]
        mock_backend_instance.generate_stream.assert_called_once_with(
            ["msg"],
            options=ResolvedGenerationOptions(
                max_new_tokens=512,
                do_sample=False,
            ),
        )
