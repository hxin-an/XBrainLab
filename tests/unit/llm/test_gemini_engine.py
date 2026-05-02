"""Local-only guards for legacy Gemini runtime requests."""

from __future__ import annotations

import importlib.util

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine


def test_legacy_gemini_request_migrates_to_local_config():
    config = LLMConfig(inference_mode="gemini")

    assert config.inference_mode == "local"
    assert config.active_mode == "local"
    assert config.assistant_runtime_selection().backend_mode == "local"


def test_engine_has_no_legacy_gemini_backend_module():
    assert importlib.util.find_spec("XBrainLab.llm.core.backends.gemini") is None


def test_engine_switching_legacy_gemini_uses_local_model_id():
    config = LLMConfig(inference_mode="gemini")
    engine = LLMEngine(config)

    assert engine.config.inference_mode == "local"
    assert engine._get_current_model_id("gemini") == config.model_name
