"""Unit tests for LLMConfig — dataclass, serialisation, and defaults."""

import json
import os
from unittest.mock import MagicMock, patch

from XBrainLab.llm.core.config import LLMConfig


class TestDefaults:
    def test_default_model_name(self):
        cfg = LLMConfig()
        assert cfg.model_name == "microsoft/Phi-4-mini-instruct"

    def test_default_device_is_string(self):
        cfg = LLMConfig()
        assert cfg.device in ("cpu", "cuda")

    def test_default_inference_mode(self):
        cfg = LLMConfig()
        assert cfg.inference_mode == "local"

    def test_default_has_no_remote_enabled_flag(self):
        cfg = LLMConfig()
        assert not hasattr(cfg, "gemini_enabled")

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
        assert "gemini_enabled" not in d
        assert "active_mode" in d


class TestSaveAndLoad:
    def test_save_and_load_roundtrip(self, tmp_path):
        filepath = str(tmp_path / "settings.json")
        cfg = LLMConfig()
        cfg.active_mode = "gemini"
        cfg.inference_mode = "gemini"
        cfg.gemini_enabled = True
        cfg.gemini_model_name = "gemini-2.0-flash"
        cfg.model_name = "TestModel"
        cfg.local_runtime_notice_acknowledged = True

        cfg.save_to_file(filepath)
        assert os.path.exists(filepath)

        loaded = LLMConfig.load_from_file(filepath)
        assert loaded is not None
        assert loaded.active_mode == "local"
        assert loaded.inference_mode == "local"
        assert not hasattr(loaded, "gemini_enabled")
        assert loaded.model_name == "TestModel"
        assert loaded.local_runtime_notice_acknowledged is True

    def test_save_and_load_migrates_remote_inference_mode(self, tmp_path):
        filepath = str(tmp_path / "settings.json")
        cfg = LLMConfig()
        cfg.active_mode = "local"
        cfg.inference_mode = "api"

        cfg.save_to_file(filepath)

        loaded = LLMConfig.load_from_file(filepath)
        assert loaded is not None
        assert loaded.active_mode == "local"
        assert loaded.inference_mode == "local"

    def test_load_from_nonexistent_returns_none(self):
        result = LLMConfig.load_from_file("/nonexistent/path/settings.json")
        assert result is None

    def test_save_excludes_legacy_remote_settings(self, tmp_path):
        filepath = str(tmp_path / "settings.json")
        cfg = LLMConfig()
        cfg.api_model_name = "gpt-4o"
        cfg.gemini_model_name = "gemini-2.0-flash"
        cfg.gemini_enabled = True
        cfg.save_to_file(filepath)

        with open(filepath) as f:
            data = json.load(f)

        raw_text = json.dumps(data)
        assert "gpt-4o" not in raw_text
        assert "gemini-2.0-flash" not in raw_text
        assert "gemini" not in raw_text

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
        assert not hasattr(loaded, "gemini_enabled")
        assert loaded.active_mode == "local"
        assert loaded.inference_mode == "local"

    def test_load_malformed_json_returns_none(self, tmp_path):
        filepath = str(tmp_path / "settings.json")
        with open(filepath, "w") as f:
            f.write("{not-valid-json")

        result = LLMConfig.load_from_file(filepath)
        assert result is None


class TestLocalRuntimeReadiness:
    @staticmethod
    def _write_cache(cache_path):
        cache_path.mkdir(parents=True)
        (cache_path / "config.json").write_text("{}", encoding="utf-8")
        (cache_path / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        (cache_path / "model.safetensors.index.json").write_text(
            "{}",
            encoding="utf-8",
        )

    def test_missing_local_runtime_packages(self):
        cfg = LLMConfig()
        cfg.load_in_4bit = True

        with patch(
            "XBrainLab.llm.core.config.importlib.util.find_spec",
            side_effect=lambda name: None
            if name in {"accelerate", "bitsandbytes"}
            else object(),
        ):
            assert cfg.missing_local_runtime_packages() == [
                "accelerate",
                "bitsandbytes",
            ]

    def test_local_backend_status_message_ready(self, tmp_path):
        cfg = LLMConfig()
        cache_path = tmp_path / "models" / "microsoft_Phi-4-mini-instruct"
        cache_path.mkdir(parents=True)
        (cache_path / "config.json").write_text("{}", encoding="utf-8")
        (cache_path / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        (cache_path / "model.safetensors.index.json").write_text(
            "{}",
            encoding="utf-8",
        )
        cfg.cache_dir = str(tmp_path / "models")
        cfg.device = "cpu"
        with patch(
            "XBrainLab.llm.core.config.importlib.util.find_spec",
            return_value=object(),
        ):
            assert cfg.local_backend_ready() is True
            assert cfg.local_backend_status_message() == "Local runtime ready."

    def test_local_backend_status_message_missing_model_cache(self, tmp_path):
        cfg = LLMConfig()
        cfg.cache_dir = str(tmp_path / "models")
        cfg.device = "cpu"

        with patch(
            "XBrainLab.llm.core.config.importlib.util.find_spec",
            return_value=object(),
        ):
            assert cfg.local_backend_ready() is False
            message = cfg.local_backend_status_message()

        assert "Model cache not found" in message
        assert cfg.model_name in message

    def test_local_backend_status_message_missing_packages(self):
        cfg = LLMConfig()
        cfg.load_in_4bit = True

        with patch(
            "XBrainLab.llm.core.config.importlib.util.find_spec",
            side_effect=lambda name: None
            if name in {"accelerate", "bitsandbytes"}
            else object(),
        ):
            message = cfg.local_backend_status_message()

        assert "accelerate, bitsandbytes" in message
        assert "enable local startup" in message

    def test_local_backend_status_message_warns_about_cpu_fallback(self, tmp_path):
        cfg = LLMConfig()
        cache_path = tmp_path / "models" / "microsoft_Phi-4-mini-instruct"
        cache_path.mkdir(parents=True)
        (cache_path / "config.json").write_text("{}", encoding="utf-8")
        (cache_path / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        (cache_path / "model.safetensors.index.json").write_text(
            "{}",
            encoding="utf-8",
        )
        cfg.cache_dir = str(tmp_path / "models")
        cfg.device = "cuda"
        cfg.load_in_4bit = True

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.zeros.side_effect = RuntimeError("no kernel image")

        with (
            patch(
                "XBrainLab.llm.core.config.importlib.util.find_spec",
                return_value=object(),
            ),
            patch.dict("sys.modules", {"torch": mock_torch}),
        ):
            assert cfg.local_backend_ready() is True
            message = cfg.local_backend_status_message()

        assert "fall back to CPU" in message
        assert "disable 4-bit loading" in message

    def test_available_local_model_uses_fallback_when_preferred_missing(
        self,
        tmp_path,
    ):
        cfg = LLMConfig()
        cfg.cache_dir = str(tmp_path / "models")
        cfg.device = "cpu"
        fallback_cache = tmp_path / "models" / "microsoft_Phi-3.5-mini-instruct"
        self._write_cache(fallback_cache)

        with patch(
            "XBrainLab.llm.core.config.importlib.util.find_spec",
            return_value=object(),
        ):
            model_id, message = cfg.available_local_model_id(cfg.model_name)

        assert model_id == cfg.fallback_local_model_id()
        assert "Falling back to supported local model" in message

    def test_available_local_model_can_fallback_from_blocked_provider(self, tmp_path):
        cfg = LLMConfig()
        cfg.model_name = "Qwen/Qwen2.5-7B-Instruct"
        cfg.cache_dir = str(tmp_path / "models")
        cfg.device = "cpu"
        fallback_cache = tmp_path / "models" / "microsoft_Phi-3.5-mini-instruct"
        self._write_cache(fallback_cache)

        with patch(
            "XBrainLab.llm.core.config.importlib.util.find_spec",
            return_value=object(),
        ):
            model_id, message = cfg.available_local_model_id(cfg.model_name)

        assert model_id == cfg.fallback_local_model_id()
        assert "blocked by policy" in message


class TestAssistantRuntimeSelection:
    def test_selection_migrates_legacy_remote_runtime_to_local(self):
        cfg = LLMConfig()
        cfg.active_mode = "gemini"
        cfg.inference_mode = "api"
        cfg.api_model_name = "gpt-4o"

        selection = cfg.assistant_runtime_selection()

        assert selection.backend_mode == "local"
        assert selection.model_id == cfg.model_name
        assert selection.ui_active_mode == "local"

    def test_apply_runtime_selection_updates_model_id_and_ui_mode(self):
        cfg = LLMConfig()
        cfg.active_mode = "local"
        cfg.inference_mode = "local"
        cfg.model_name = "microsoft/Phi-Old"

        selection = cfg.apply_runtime_selection(
            "local",
            model_id=LLMConfig.fallback_local_model_id(),
        )

        assert cfg.inference_mode == "local"
        assert cfg.active_mode == "local"
        assert cfg.model_name == LLMConfig.fallback_local_model_id()
        assert selection.backend_mode == "local"
        assert selection.model_id == LLMConfig.fallback_local_model_id()
        assert selection.ui_active_mode == "local"
