"""Unit tests for the local-only assistant settings dialog."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.config import LLMConfig


@pytest.fixture
def config():
    cfg = LLMConfig()
    cfg.inference_mode = "local"
    cfg.active_mode = "local"
    cfg.model_name = LLMConfig.default_local_model_id()
    cfg.device = "cpu"
    cfg.local_model_enabled = True
    return cfg


@pytest.fixture
def dialog(qtbot, config):
    with (
        patch.object(LLMConfig, "load_from_file", return_value=config),
        patch("XBrainLab.ui.dialogs.model_settings_dialog.ModelDownloader") as MockDL,
        patch("os.path.exists", return_value=False),
        patch("os.listdir", return_value=[]),
    ):
        dl = MockDL.return_value
        dl.progress = MagicMock()
        dl.finished = MagicMock()
        dl.failed = MagicMock()
        dl.progress.connect = MagicMock()
        dl.finished.connect = MagicMock()
        dl.failed.connect = MagicMock()

        from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

        dlg = ModelSettingsDialog(parent=None, config=config, agent_manager=MagicMock())
        qtbot.addWidget(dlg)
        yield dlg


class TestModelSettingsInit:
    def test_creates_dialog(self, dialog):
        assert dialog.windowTitle() == "AI Assistant Settings"
        assert dialog.isVisible() is False

    def test_combo_has_only_approved_local_models(self, dialog):
        model_ids = [
            dialog.local_model_combo.itemText(i)
            for i in range(dialog.local_model_combo.count())
        ]

        assert model_ids == LLMConfig.allowed_local_model_ids()
        assert all("Qwen" not in model_id for model_id in model_ids)

    def test_no_remote_runtime_widgets_are_exposed(self, dialog):
        assert not hasattr(dialog, "api_key_input")
        assert not hasattr(dialog, "test_conn_btn")
        assert not hasattr(dialog, "gemini_group")
        assert not hasattr(dialog, "gemini_model_combo")

    def test_legacy_remote_config_loads_as_local_only(self, qtbot, config):
        config.inference_mode = "gemini"
        config.active_mode = "gemini"
        config.gemini_enabled = True

        with (
            patch.object(LLMConfig, "load_from_file", return_value=config),
            patch(
                "XBrainLab.ui.dialogs.model_settings_dialog.ModelDownloader"
            ) as MockDL,
            patch("os.path.exists", return_value=False),
            patch("os.listdir", return_value=[]),
        ):
            dl = MockDL.return_value
            dl.progress = MagicMock()
            dl.finished = MagicMock()
            dl.failed = MagicMock()
            dl.progress.connect = MagicMock()
            dl.finished.connect = MagicMock()
            dl.failed.connect = MagicMock()

            from XBrainLab.ui.dialogs.model_settings_dialog import (
                ModelSettingsDialog,
            )

            dlg = ModelSettingsDialog(parent=None, config=config)
            qtbot.addWidget(dlg)

        assert dlg.config.assistant_runtime_selection().backend_mode == "local"
        assert dlg.config.active_mode == "local"
        assert dlg.config.inference_mode == "local"


class TestLocalModelSection:
    def test_check_local_model_status_not_downloaded(self, dialog):
        with patch("os.path.exists", return_value=False):
            dialog.check_local_model_status()

        assert (
            "not downloaded" in dialog.local_status_label.text().lower()
            or "install" in dialog.local_action_btn.text().lower()
        )

    def test_check_local_model_status_downloaded(self, dialog):
        with (
            patch("os.path.exists", return_value=True),
            patch(
                "os.listdir",
                return_value=[
                    "config.json",
                    "tokenizer_config.json",
                    "model.safetensors.index.json",
                ],
            ),
        ):
            dialog.check_local_model_status()

        assert dialog.local_downloaded is True
        assert "downloaded" in dialog.local_status_label.text().lower()

    def test_start_download(self, dialog):
        dialog.is_downloading = False
        with patch(
            "XBrainLab.ui.dialogs.model_settings_dialog.plan_model_download",
        ) as mock_plan:
            mock_plan.return_value.ok = True
            mock_plan.return_value.message = "Download allowed"
            dialog._start_download()

        assert dialog.is_downloading is True
        assert "cancel" in dialog.local_action_btn.text().lower()

    def test_start_download_blocks_failed_preflight(self, dialog):
        dialog.is_downloading = False
        with (
            patch(
                "XBrainLab.ui.dialogs.model_settings_dialog.plan_model_download",
            ) as mock_plan,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
        ):
            mock_plan.return_value.ok = False
            mock_plan.return_value.message = "cache too large"
            mock_plan.return_value.current_cache_bytes = 15_000_000_000
            mock_plan.return_value.estimated_download_bytes = 8_000_000_000
            mock_plan.return_value.available_disk_bytes = 100_000_000_000
            mock_plan.return_value.projected_cache_bytes = 23_000_000_000
            mock_plan.return_value.cache_dir = "/models"
            mock_plan.return_value.cleanup_candidates = ("/models/blocked",)
            dialog._start_download()

        assert dialog.is_downloading is False
        mock_warning.assert_called_once()

    def test_on_download_finished(self, dialog):
        dialog.is_downloading = True
        with patch("PyQt6.QtWidgets.QMessageBox.information"):
            dialog.on_download_finished("/path/to/model")

        assert dialog.is_downloading is False

    def test_on_download_failed_cancelled_cleans_partial_files(self, dialog):
        dialog.is_downloading = True
        with patch.object(dialog, "_cleanup_partial_files") as cleanup:
            dialog.on_download_failed("Cancelled by user")

        assert dialog.is_downloading is False
        cleanup.assert_called_once()

    def test_delete_model_aborts_when_agent_manager_blocks(self, dialog):
        from PyQt6.QtWidgets import QMessageBox

        dialog.local_downloaded = True
        dialog.agent_manager.prepare_model_deletion.return_value = False
        with (
            patch.object(
                QMessageBox,
                "warning",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch("shutil.rmtree") as mock_rmtree,
        ):
            dialog._delete_model()

        mock_rmtree.assert_not_called()

    def test_on_local_enable_toggled(self, dialog):
        with (
            patch("os.path.exists", return_value=False),
            patch("os.listdir", return_value=[]),
        ):
            dialog._on_local_enable_toggled(False)

        assert not dialog.local_model_combo.isEnabled()


class TestActivateAndSave:
    def test_update_validation_state_not_ready(self, dialog):
        dialog.local_downloaded = False
        dialog.is_downloading = False
        dialog.update_validation_state()

        assert not dialog.btn_activate.isEnabled()

    def test_update_validation_state_ready(self, dialog):
        dialog.local_downloaded = True
        dialog.is_downloading = False
        with patch.object(dialog.config, "local_backend_ready", return_value=True):
            dialog.update_validation_state()

        assert dialog.btn_activate.isEnabled()

    def test_update_validation_state_blocks_missing_local_runtime(self, dialog):
        dialog.local_downloaded = True
        dialog.is_downloading = False
        dialog.local_enable_chk.setChecked(True)
        with patch.object(dialog.config, "local_backend_ready", return_value=False):
            dialog.update_validation_state()

        assert not dialog.btn_activate.isEnabled()

    def test_refresh_local_runtime_status_shows_cpu_fallback(self, dialog):
        with (
            patch.object(dialog.config, "local_backend_ready", return_value=True),
            patch.object(
                dialog.config,
                "local_backend_status_message",
                return_value=(
                    "Local runtime ready. GPU execution is unavailable in this "
                    "environment, so startup will fall back to CPU and disable "
                    "4-bit loading."
                ),
            ),
        ):
            dialog._refresh_local_runtime_status()

        assert "fall back to CPU" in dialog.local_runtime_label.text()

    def test_on_activate_clicked(self, dialog):
        dialog.local_downloaded = True
        with (
            patch.object(dialog.config, "local_backend_ready", return_value=True),
            patch.object(LLMConfig, "save_to_file") as save,
        ):
            dialog.on_activate_clicked()

        save.assert_called_once()
        assert dialog.config.inference_mode == "local"
        assert dialog.config.active_mode == "local"
        assert not hasattr(dialog.config, "gemini_enabled")

    def test_on_activate_clicked_blocks_local_runtime_gap(self, dialog):
        dialog.local_downloaded = True
        dialog.local_enable_chk.setChecked(True)
        with (
            patch.object(dialog.config, "local_backend_ready", return_value=False),
            patch.object(
                dialog.config,
                "local_backend_status_message",
                return_value="Missing accelerate",
            ),
            patch.object(LLMConfig, "save_to_file") as mock_save,
            patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
        ):
            dialog.on_activate_clicked()

        mock_critical.assert_called_once()
        mock_save.assert_not_called()


class TestRejectAndClose:
    def test_reject_while_downloading(self, dialog):
        dialog.is_downloading = True
        dialog.reject()
        dialog.downloader.shutdown.assert_called_once()

    def test_close_event(self, dialog):
        dialog.is_downloading = True
        from PyQt6.QtGui import QCloseEvent

        event = QCloseEvent()
        dialog.closeEvent(event)
        dialog.downloader.shutdown.assert_called_once()

    def test_get_config(self, dialog):
        cfg = dialog.get_config()
        assert cfg is dialog.config
