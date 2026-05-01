"""Dedicated local-bootstrap validation for BUG-AGENT-001."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QObject

from XBrainLab.llm.core.config import LLMConfig


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
    model_root = cache_dir / f"models--{repo_id.replace('/', '--')}"
    snapshot_dir = model_root / "snapshots" / "test-revision"
    snapshot_dir.mkdir(parents=True)
    (model_root / "refs").mkdir(parents=True)
    (model_root / "refs" / "main").write_text("test-revision", encoding="utf-8")

    for filename in (
        "config.json",
        "tokenizer_config.json",
        "model.safetensors.index.json",
        "model-00001-of-00001.safetensors",
    ):
        (snapshot_dir / filename).write_text("{}", encoding="utf-8")


def _make_worker():
    from XBrainLab.llm.agent.worker import AgentWorker

    with patch.object(QObject, "__init__", lambda self: None):
        worker = AgentWorker()

    worker.finished = MagicMock()
    worker.chunk_received = MagicMock()
    worker.error = MagicMock()
    worker.log = MagicMock()
    return worker


class TestLocalBootstrapValidation:
    def test_saved_local_config_and_hf_cache_keep_ui_truth_consistent(
        self,
        qtbot,
        tmp_path,
    ):
        repo_id = "microsoft/Phi-4-mini-instruct"
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
            patch(
                "XBrainLab.ui.dialogs.model_settings_dialog.ModelDownloader"
            ) as MockDL,
            patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None),
            patch(
                "XBrainLab.ui.chat.panel.LLMConfig.load_from_file",
                return_value=config,
            ),
        ):
            dl = MockDL.return_value
            dl.progress = MagicMock()
            dl.finished = MagicMock()
            dl.failed = MagicMock()
            dl.progress.connect = MagicMock()
            dl.finished.connect = MagicMock()
            dl.failed.connect = MagicMock()

            from XBrainLab.ui.chat.panel import ChatPanel
            from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

            dialog = ModelSettingsDialog(
                parent=None,
                config=config,
                agent_manager=MagicMock(),
            )
            qtbot.addWidget(dialog)

            panel = ChatPanel()
            qtbot.addWidget(panel)

        local_action = next(
            action for action in panel.model_menu.actions() if "Local" in action.text()
        )

        assert config.active_mode == "local"
        assert config.inference_mode == "local"
        assert config.local_backend_ready() is True
        assert config.local_backend_status_message() == "Local runtime ready."
        assert dialog.local_downloaded is True
        assert "downloaded" in dialog.local_status_label.text().lower()
        assert dialog.local_runtime_label.text() == "Runtime: Ready"
        assert dialog.btn_activate.isEnabled() is True
        assert local_action.isEnabled() is True
        assert local_action.text() == "Local"

    def test_saved_local_config_without_cache_fails_closed_before_engine_load(
        self,
        tmp_path,
    ):
        settings_path = tmp_path / "settings.json"
        repo_id = "microsoft/Phi-4-mini-instruct"
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
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=config,
            ),
            patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEngine,
        ):
            worker.initialize_agent()

        MockEngine.assert_not_called()
        worker.error.emit.assert_called_once()
        assert "Model cache not found" in worker.error.emit.call_args.args[0]

    def test_dialog_uses_selected_model_for_local_runtime_truth(self, qtbot, tmp_path):
        saved_repo = "microsoft/Phi-4-mini-instruct"
        settings_path = tmp_path / "settings.json"
        cache_dir = tmp_path / "models"
        _write_settings(settings_path, saved_repo)
        _create_hf_cache(cache_dir, saved_repo)

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
            patch(
                "XBrainLab.ui.dialogs.model_settings_dialog.ModelDownloader"
            ) as MockDL,
        ):
            dl = MockDL.return_value
            dl.progress = MagicMock()
            dl.finished = MagicMock()
            dl.failed = MagicMock()
            dl.progress.connect = MagicMock()
            dl.finished.connect = MagicMock()
            dl.failed.connect = MagicMock()

            from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

            dialog = ModelSettingsDialog(
                parent=None,
                config=config,
                agent_manager=MagicMock(),
            )
            qtbot.addWidget(dialog)
            dialog.local_model_combo.setCurrentText("microsoft/Phi-3.5-mini-instruct")

        assert dialog.local_downloaded is False
        assert "model cache not found" in dialog.local_runtime_label.text().lower()
        assert dialog.btn_activate.isEnabled() is False

    def test_cpu_fallback_note_stays_consistent_across_ui_and_worker(
        self,
        qtbot,
        tmp_path,
    ):
        repo_id = "microsoft/Phi-4-mini-instruct"
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
            patch(
                "XBrainLab.ui.chat.panel.LLMConfig.load_from_file",
                return_value=config,
            ),
            patch(
                "XBrainLab.ui.dialogs.model_settings_dialog.ModelDownloader"
            ) as MockDL,
            patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=config,
            ),
            patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEngine,
        ):
            dl = MockDL.return_value
            dl.progress = MagicMock()
            dl.finished = MagicMock()
            dl.failed = MagicMock()
            dl.progress.connect = MagicMock()
            dl.finished.connect = MagicMock()
            dl.failed.connect = MagicMock()

            from XBrainLab.ui.chat.panel import ChatPanel
            from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

            dialog = ModelSettingsDialog(
                parent=None,
                config=config,
                agent_manager=MagicMock(),
            )
            qtbot.addWidget(dialog)

            panel = ChatPanel()
            qtbot.addWidget(panel)
            local_action = next(
                action
                for action in panel.model_menu.actions()
                if "Local" in action.text()
            )

            worker.initialize_agent()

        MockEngine.assert_called_once_with(config)
        assert "fall back to CPU" in dialog.local_runtime_label.text()
        assert "CPU fallback" in local_action.text()
        assert any(
            "fall back to CPU" in call.args[0]
            for call in worker.log.emit.call_args_list
        )
