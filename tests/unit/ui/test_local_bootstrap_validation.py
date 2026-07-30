"""Dedicated local-bootstrap validation for BUG-AGENT-001."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import (
    MIN_MODEL_WEIGHT_BYTES,
    local_model_spec,
)
from XBrainLab.llm.core.runtime_selection import AssistantRuntimeLaunchResolver


def _write_settings(path: Path, repo_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                "local": {"model_name": repo_id, "enabled": True},
                "gemini": {"model_name": "gemini-2.0-flash", "enabled": False},
                "active_mode": "local",
                "generation": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_new_tokens": 512,
                },
            }
        ),
        encoding="utf-8",
    )


def _create_hf_cache(cache_dir: Path, repo_id: str) -> None:
    spec = local_model_spec(repo_id)
    assert spec is not None
    model_root = cache_dir / f"models--{repo_id.replace('/', '--')}"
    snapshot_dir = model_root / "snapshots" / spec.revision
    snapshot_dir.mkdir(parents=True)
    (model_root / "refs").mkdir(parents=True)
    (model_root / "blobs").mkdir(parents=True)
    (model_root / "refs" / "main").write_text(spec.revision, encoding="utf-8")
    (model_root / "blobs" / "fixture-blob").write_bytes(b"fixture")

    for filename in (
        "config.json",
        "tokenizer_config.json",
        "model.safetensors.index.json",
        "model-00001-of-00001.safetensors",
    ):
        (snapshot_dir / filename).write_text("{}", encoding="utf-8")
    (snapshot_dir / "model.safetensors.index.json").write_text(
        json.dumps(
            {
                "weight_map": {
                    "model.embed_tokens.weight": ("model-00001-of-00001.safetensors")
                }
            }
        ),
        encoding="utf-8",
    )
    with (snapshot_dir / "model-00001-of-00001.safetensors").open("r+b") as stream:
        stream.truncate(MIN_MODEL_WEIGHT_BYTES)


def _make_worker():
    from XBrainLab.llm.agent.worker import AgentWorker

    worker = AgentWorker()
    dynamic_worker = cast(Any, worker)
    dynamic_worker.finished = MagicMock()
    dynamic_worker.chunk_received = MagicMock()
    worker.error = MagicMock()
    worker.log = MagicMock()
    return worker


class TestLocalBootstrapValidation:
    def test_saved_local_config_and_hf_cache_keep_ui_truth_consistent(
        self,
        qtbot,
        tmp_path,
    ):
        repo_id = LLMConfig.default_local_model_id()
        settings_path = tmp_path / "settings.json"
        cache_dir = tmp_path / "models"
        _write_settings(settings_path, repo_id)
        _create_hf_cache(cache_dir, repo_id)

        config = LLMConfig.load_from_file(str(settings_path))
        assert config is not None
        config.cache_dir = str(cache_dir)
        config.device = "cpu"
        config.load_in_4bit = False

        with (
            patch(
                "XBrainLab.llm.core.config.importlib.util.find_spec",
                return_value=object(),
            ),
            patch(
                "XBrainLab.ui.dialogs.model_settings_dialog.LLMConfig.load_from_file",
                return_value=config,
            ),
        ):
            from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

            dialog = ModelSettingsDialog(
                parent=None,
                config=config,
                agent_manager=MagicMock(),
            )
            qtbot.addWidget(dialog)
            qtbot.waitUntil(
                lambda: (
                    dialog._pending_inspection_request_id is None
                    and dialog._current_local_model_state is not None
                ),
                timeout=3000,
            )

            assert config.active_mode == "local"
            assert config.inference_mode == "local"
            assert config.local_backend_ready() is True
            assert config.local_backend_status_message() == "Local runtime ready."
            assert dialog.local_downloaded is True
            assert dialog.local_status_label.text() == "Model: Installed"
            assert dialog.local_runtime_label.text() == "Environment check: Ready"
            assert dialog.btn_activate.isEnabled() is True

    def test_saved_local_config_without_cache_fails_closed_before_engine_load(
        self,
        tmp_path,
    ):
        settings_path = tmp_path / "settings.json"
        repo_id = LLMConfig.default_local_model_id()
        _write_settings(settings_path, repo_id)

        config = LLMConfig.load_from_file(str(settings_path))
        assert config is not None
        config.cache_dir = str(tmp_path / "models")
        config.load_in_4bit = False

        worker = _make_worker()

        with (
            patch(
                "XBrainLab.llm.core.config.importlib.util.find_spec",
                return_value=object(),
            ),
            patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEngine,
        ):
            resolution = AssistantRuntimeLaunchResolver().resolve(config)

        assert resolution.available is False
        assert resolution.failure is not None
        assert "Model cache not found" in resolution.failure.message
        MockEngine.assert_not_called()
        cast(MagicMock, worker.error.emit).assert_not_called()

    def test_dialog_uses_selected_model_for_local_runtime_truth(self, qtbot, tmp_path):
        saved_repo = "microsoft/Phi-4-mini-instruct"
        product_repo = LLMConfig.default_local_model_id()
        settings_path = tmp_path / "settings.json"
        cache_dir = tmp_path / "models"
        _write_settings(settings_path, saved_repo)
        _create_hf_cache(cache_dir, product_repo)
        original_settings = settings_path.read_bytes()

        config = LLMConfig.load_from_file(str(settings_path))
        assert config is not None
        config.cache_dir = str(cache_dir)
        config.load_in_4bit = False

        with (
            patch(
                "XBrainLab.llm.core.config.importlib.util.find_spec",
                return_value=object(),
            ),
            patch(
                "XBrainLab.ui.dialogs.model_settings_dialog.LLMConfig.load_from_file",
                return_value=config,
            ),
        ):
            from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

            dialog = ModelSettingsDialog(
                parent=None,
                config=config,
                agent_manager=MagicMock(),
            )
            qtbot.addWidget(dialog)
            qtbot.waitUntil(
                lambda: (
                    dialog._pending_inspection_request_id is None
                    and dialog._current_local_model_state is not None
                    and dialog._current_local_model_state.request.model_name
                    == product_repo
                ),
                timeout=3000,
            )

            assert config.model_name == saved_repo
            assert settings_path.read_bytes() == original_settings
            assert dialog.local_model_combo.currentData() == product_repo
            assert dialog.local_downloaded is True
            assert dialog.model_migration_label.isHidden() is False
            assert "no longer available" in dialog.model_migration_label.text()

    def test_cpu_fallback_note_stays_consistent_across_ui_and_worker(
        self,
        qtbot,
        tmp_path,
    ):
        repo_id = LLMConfig.default_local_model_id()
        settings_path = tmp_path / "settings.json"
        cache_dir = tmp_path / "models"
        _write_settings(settings_path, repo_id)
        _create_hf_cache(cache_dir, repo_id)

        config = LLMConfig.load_from_file(str(settings_path))
        assert config is not None
        config.cache_dir = str(cache_dir)
        config.device = "cuda"
        config.load_in_4bit = True

        worker = _make_worker()

        with (
            patch(
                "XBrainLab.llm.core.config.importlib.util.find_spec",
                return_value=object(),
            ),
            patch.object(
                LLMConfig,
                "local_backend_cpu_fallback_reason",
                return_value="no kernel image",
            ),
            patch(
                "XBrainLab.ui.dialogs.model_settings_dialog.LLMConfig.load_from_file",
                return_value=config,
            ),
            patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEngine,
        ):
            from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

            dialog = ModelSettingsDialog(
                parent=None,
                config=config,
                agent_manager=MagicMock(),
            )
            qtbot.addWidget(dialog)
            qtbot.waitUntil(
                lambda: (
                    dialog._pending_inspection_request_id is None
                    and dialog._current_local_model_state is not None
                ),
                timeout=3000,
            )

            resolution = AssistantRuntimeLaunchResolver().resolve(config)
            assert resolution.launch_spec is not None
            worker.initialize_agent(resolution.launch_spec)

        engine_config = MockEngine.call_args.args[0]
        assert engine_config.model_name == config.model_name
        assert engine_config.device == config.device
        assert engine_config.load_in_4bit == config.load_in_4bit
        assert "fall back to CPU" in dialog.local_runtime_label.text()
        assert any(
            "fall back to CPU" in call.args[0]
            for call in cast(MagicMock, worker.log.emit).call_args_list
        )
