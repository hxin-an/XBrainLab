"""Unit tests for LLMConfig — dataclass, serialisation, and defaults."""

import json
import os

from XBrainLab.llm.core.config import LLMConfig


class TestDefaults:
    def test_default_model_name(self):
        cfg = LLMConfig()
        assert cfg.model_name == "Qwen/Qwen2.5-7B-Instruct"

    def test_default_device_is_string(self):
        cfg = LLMConfig()
        assert cfg.device in ("cpu", "cuda")

    def test_default_inference_mode(self):
        cfg = LLMConfig()
        assert cfg.inference_mode in ("local", "api", "gemini")

    def test_default_gemini_enabled(self):
        cfg = LLMConfig()
        assert cfg.gemini_enabled is False

    def test_default_active_mode(self):
        cfg = LLMConfig()
        assert cfg.active_mode == "local"

    def test_default_temperature(self):
        cfg = LLMConfig()
        assert 0.0 <= cfg.temperature <= 2.0

    def test_default_max_new_tokens(self):
        cfg = LLMConfig()
        assert cfg.max_new_tokens > 0


class TestToDict:
    def test_returns_dict(self):
        cfg = LLMConfig()
        d = cfg.to_dict()
        assert isinstance(d, dict)
        assert "model_name" in d
        assert "device" in d
        assert "gemini_enabled" in d
        assert "active_mode" in d


class TestSaveAndLoad:
    def test_save_and_load_roundtrip(self, tmp_path):
        filepath = str(tmp_path / "settings.json")
        cfg = LLMConfig()
        cfg.active_mode = "gemini"
        cfg.gemini_enabled = True
        cfg.gemini_model_name = "gemini-2.0-flash"
        cfg.model_name = "TestModel"

        cfg.save_to_file(filepath)
        assert os.path.exists(filepath)

        loaded = LLMConfig.load_from_file(filepath)
        assert loaded is not None
        assert loaded.active_mode == "gemini"
        assert loaded.gemini_enabled is True
        assert loaded.gemini_model_name == "gemini-2.0-flash"
        assert loaded.model_name == "TestModel"

    def test_load_from_nonexistent_returns_none(self):
        result = LLMConfig.load_from_file("/nonexistent/path/settings.json")
        assert result is None

    def test_save_excludes_api_keys(self, tmp_path):
        filepath = str(tmp_path / "settings.json")
        cfg = LLMConfig()
        cfg.api_key = "sk-secret-key"
        cfg.gemini_api_key = "AIza-secret"
        cfg.save_to_file(filepath)

        with open(filepath) as f:
            data = json.load(f)

        raw_text = json.dumps(data)
        assert "sk-secret-key" not in raw_text
        assert "AIza-secret" not in raw_text

    def test_load_backwards_compat_gemini_verified(self, tmp_path):
        """Ensure old 'verified' key is read as 'enabled'."""
        filepath = str(tmp_path / "settings.json")
        data = {
            "local": {"model_name": "test", "enabled": True},
            "gemini": {"model_name": "gemini-1.5-flash", "verified": True},
            "active_mode": "gemini",
        }
        with open(filepath, "w") as f:
            json.dump(data, f)

        loaded = LLMConfig.load_from_file(filepath)
        assert loaded is not None
        assert loaded.gemini_enabled is True

    def test_load_malformed_json_returns_none(self, tmp_path):
        filepath = str(tmp_path / "settings.json")
        with open(filepath, "w") as f:
            f.write("{not-valid-json")

        result = LLMConfig.load_from_file(filepath)
        assert result is None
