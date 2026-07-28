"""Unit tests for LLMConfig — dataclass, serialisation, and defaults."""

import inspect
import json
import logging
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import (
    MIN_MODEL_WEIGHT_BYTES,
    model_snapshot_path,
)


def _settings_payload(model_name: str) -> dict[str, object]:
    return {
        "local": {
            "model_name": model_name,
            "enabled": True,
            "runtime_notice_acknowledged": True,
        },
        "active_mode": "local",
        "inference_mode": "local",
        "generation": {
            "temperature": 0.4,
            "top_p": 0.8,
            "max_new_tokens": 256,
        },
    }


def _write_complete_model_cache(cache_dir: Path, model_id: str) -> Path:
    snapshot = model_snapshot_path(str(cache_dir), model_id)
    assert snapshot is not None
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    with (snapshot / "model.safetensors").open("wb") as stream:
        stream.truncate(MIN_MODEL_WEIGHT_BYTES)
    return snapshot


class TestDefaults:
    def test_default_model_name(self):
        cfg = LLMConfig()
        assert cfg.model_name == "ibm-granite/granite-3.3-2b-instruct"

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
        cfg.__dict__["gemini_enabled"] = True
        cfg.__dict__["gemini_model_name"] = "gemini-2.0-flash"
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
        cfg.__dict__["api_model_name"] = "gpt-4o"
        cfg.__dict__["gemini_model_name"] = "gemini-2.0-flash"
        cfg.__dict__["gemini_enabled"] = True
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

    def test_save_creates_missing_parent_directories(self, tmp_path):
        filepath = tmp_path / "nested" / "config" / "settings.json"

        saved = LLMConfig().save_to_file(str(filepath))

        assert saved is True
        assert filepath.is_file()

    def test_failed_save_preserves_existing_settings_file(self, tmp_path):
        filepath = tmp_path / "settings.json"
        original = b'{"local":{"model_name":"known-good"}}\n'
        filepath.write_bytes(original)

        with patch(
            "XBrainLab.llm.core.config.json.dump",
            side_effect=RuntimeError("simulated interrupted write"),
        ):
            saved = LLMConfig().save_to_file(str(filepath))

        assert saved is False
        assert filepath.read_bytes() == original
        assert list(tmp_path.glob(".settings.json.*.tmp")) == []


class TestPerUserSettingsBoundary:
    def test_windows_uses_roaming_app_data(self, tmp_path):
        from XBrainLab.llm.core.config_paths import user_settings_path

        roaming = tmp_path / "AppData" / "Roaming"

        path = user_settings_path(
            environ={"APPDATA": str(roaming)},
            system_name="Windows",
            home=tmp_path / "home",
        )

        assert path == roaming / "XBrainLab" / "settings.json"

    def test_linux_uses_xdg_config_home(self, tmp_path):
        from XBrainLab.llm.core.config_paths import user_settings_path

        xdg_home = tmp_path / "xdg"

        path = user_settings_path(
            environ={"XDG_CONFIG_HOME": str(xdg_home)},
            system_name="Linux",
            home=tmp_path / "home",
        )

        assert path == xdg_home / "xbrainlab" / "settings.json"

    def test_wsl_uses_linux_per_user_config_boundary(self, tmp_path):
        from XBrainLab.llm.core.config_paths import user_settings_path

        home = tmp_path / "wsl-home"

        path = user_settings_path(
            environ={"WSL_DISTRO_NAME": "Ubuntu"},
            system_name="Linux",
            home=home,
        )

        assert path == home / ".config" / "xbrainlab" / "settings.json"

    def test_explicit_config_directory_override_has_priority(self, tmp_path):
        from XBrainLab.llm.core.config_paths import user_settings_path

        override = tmp_path / "isolated-config"

        path = user_settings_path(
            environ={
                "APPDATA": str(tmp_path / "ignored"),
                "XBRAINLAB_CONFIG_DIR": str(override),
            },
            system_name="Windows",
            home=tmp_path / "home",
        )

        assert path == override / "settings.json"

    def test_relative_override_is_anchored_to_user_home(self, tmp_path):
        from XBrainLab.llm.core.config_paths import user_settings_path

        home = tmp_path / "home"

        path = user_settings_path(
            environ={"XBRAINLAB_CONFIG_DIR": "isolated-config"},
            system_name="Linux",
            home=home,
        )

        assert path == home / "isolated-config" / "settings.json"

    def test_relative_xdg_config_home_is_ignored(self, tmp_path):
        from XBrainLab.llm.core.config_paths import user_settings_path

        home = tmp_path / "home"

        path = user_settings_path(
            environ={"XDG_CONFIG_HOME": "relative-config"},
            system_name="Linux",
            home=home,
        )

        assert path == home / ".config" / "xbrainlab" / "settings.json"

    def test_default_path_never_uses_repo_root(self, tmp_path):
        from XBrainLab.config import AppConfig

        config_dir = tmp_path / "user-config"
        with patch.dict(
            os.environ,
            {"XBRAINLAB_CONFIG_DIR": str(config_dir)},
            clear=False,
        ):
            default_path = Path(LLMConfig._default_settings_path())

        assert default_path == config_dir / "settings.json"
        assert default_path != Path(AppConfig.BASE_DIR) / "settings.json"

    def test_default_path_source_guard_rejects_repo_root_dependency(self):
        source = inspect.getsource(LLMConfig._default_settings_path)

        assert "user_settings_path" in source
        assert "legacy" not in source.lower()
        assert "AppConfig" not in source
        assert "BASE_DIR" not in source
        assert 'return "settings.json"' not in source

    def test_first_run_writes_defaults_only_to_per_user_path(self, tmp_path):
        user_path = tmp_path / "user" / "settings.json"
        missing_legacy_path = tmp_path / "repo" / "settings.json"

        with (
            patch.object(
                LLMConfig,
                "_default_settings_path",
                return_value=str(user_path),
            ),
            patch.object(
                LLMConfig,
                "_legacy_settings_path",
                return_value=str(missing_legacy_path),
            ),
        ):
            loaded = LLMConfig.load_from_file()

        assert loaded is not None
        assert loaded.model_name == LLMConfig.default_local_model_id()
        assert user_path.is_file()
        assert not missing_legacy_path.exists()

    def test_valid_legacy_file_migrates_once_without_modifying_source(
        self,
        tmp_path,
        caplog,
    ):
        caplog.set_level(logging.INFO)
        user_path = tmp_path / "user" / "settings.json"
        legacy_path = tmp_path / "repo" / "settings.json"
        legacy_path.parent.mkdir(parents=True)
        legacy_model = "microsoft/Phi-3.5-mini-instruct"
        legacy_path.write_text(
            json.dumps(_settings_payload(legacy_model)),
            encoding="utf-8",
        )
        original_legacy = legacy_path.read_bytes()

        with (
            patch.object(
                LLMConfig,
                "_default_settings_path",
                return_value=str(user_path),
            ),
            patch.object(
                LLMConfig,
                "_legacy_settings_path",
                return_value=str(legacy_path),
            ),
        ):
            first = LLMConfig.load_from_file()
            assert legacy_path.read_bytes() == original_legacy
            legacy_path.write_text(
                json.dumps(_settings_payload("changed/legacy-model")),
                encoding="utf-8",
            )
            second = LLMConfig.load_from_file()

        assert first is not None
        assert second is not None
        assert first.model_name == legacy_model
        assert second.model_name == legacy_model
        assert user_path.is_file()
        assert "Migrated local LLM settings" in caplog.text

    def test_existing_malformed_user_file_never_falls_back_to_legacy(self, tmp_path):
        user_path = tmp_path / "user" / "settings.json"
        legacy_path = tmp_path / "repo" / "settings.json"
        user_path.parent.mkdir(parents=True)
        legacy_path.parent.mkdir(parents=True)
        user_path.write_text("{not-json", encoding="utf-8")
        legacy_path.write_text(
            json.dumps(_settings_payload("legacy/should-not-load")),
            encoding="utf-8",
        )

        with (
            patch.object(
                LLMConfig,
                "_default_settings_path",
                return_value=str(user_path),
            ),
            patch.object(
                LLMConfig,
                "_legacy_settings_path",
                return_value=str(legacy_path),
            ),
        ):
            loaded = LLMConfig.load_from_file()

        assert loaded is None
        assert user_path.read_text(encoding="utf-8") == "{not-json"

    def test_failed_migration_write_does_not_use_legacy_as_runtime_config(
        self,
        tmp_path,
        caplog,
    ):
        user_path = tmp_path / "user" / "settings.json"
        legacy_path = tmp_path / "repo" / "settings.json"
        legacy_path.parent.mkdir(parents=True)
        legacy_path.write_text(
            json.dumps(_settings_payload("legacy/not-persisted")),
            encoding="utf-8",
        )

        with (
            patch.object(
                LLMConfig,
                "_default_settings_path",
                return_value=str(user_path),
            ),
            patch.object(
                LLMConfig,
                "_legacy_settings_path",
                return_value=str(legacy_path),
            ),
            patch.object(LLMConfig, "save_to_file", return_value=False),
        ):
            loaded = LLMConfig.load_from_file()

        assert loaded is not None
        assert loaded.model_name == LLMConfig.default_local_model_id()
        assert loaded.model_name != "legacy/not-persisted"
        assert "could not be persisted" in caplog.text


class TestLocalRuntimeReadiness:
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
        cache_dir = tmp_path / "models"
        _write_complete_model_cache(cache_dir, cfg.model_name)
        cfg.cache_dir = str(cache_dir)
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
        cache_dir = tmp_path / "models"
        _write_complete_model_cache(cache_dir, cfg.model_name)
        cfg.cache_dir = str(cache_dir)
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


class TestAssistantRuntimeSelection:
    def test_selection_migrates_legacy_remote_runtime_to_local(self):
        cfg = LLMConfig()
        cfg.active_mode = "gemini"
        cfg.inference_mode = "api"
        cfg.__dict__["api_model_name"] = "gpt-4o"

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
