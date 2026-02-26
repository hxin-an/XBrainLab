"""Coverage tests for ModelSettingsDialog - targeting 272 uncovered lines."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.config import LLMConfig


@pytest.fixture
def config():
    cfg = LLMConfig()
    cfg.gemini_enabled = False
    cfg.inference_mode = "local"
    cfg.model_name = "Qwen/Qwen2.5-7B-Instruct"
    cfg.gemini_api_key = ""
    cfg.gemini_model_name = "gemini-2.0-flash"
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

    def test_combo_has_models(self, dialog):
        assert dialog.local_model_combo.count() >= 4


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
            patch("os.listdir", return_value=["file1"]),
        ):
            dialog.check_local_model_status()
            assert dialog.local_downloaded is True
            assert "downloaded" in dialog.local_status_label.text().lower()

    def test_start_download(self, dialog):
        dialog.is_downloading = False
        dialog._start_download()
        assert dialog.is_downloading is True
        assert "cancel" in dialog.local_action_btn.text().lower()

    def test_on_download_progress(self, dialog):
        dialog.on_download_progress(50, "50% done")
        assert "50" in dialog.local_status_label.text()

    def test_on_download_finished(self, dialog):
        dialog.is_downloading = True
        with patch("PyQt6.QtWidgets.QMessageBox.information"):
            dialog.on_download_finished("/path/to/model")
        assert dialog.is_downloading is False

    def test_on_download_failed(self, dialog):
        dialog.is_downloading = True
        with patch("PyQt6.QtWidgets.QMessageBox.critical"):
            dialog.on_download_failed("Network error")
        assert dialog.is_downloading is False
        assert "failed" in dialog.local_status_label.text().lower()

    def test_on_download_failed_cancelled(self, dialog):
        dialog.is_downloading = True
        with (
            patch(
                "XBrainLab.ui.dialogs.model_settings_dialog.ModelSettingsDialog._cleanup_partial_files"
            ),
        ):
            dialog.on_download_failed("Cancelled by user")
        assert dialog.is_downloading is False

    def test_on_local_action_clicked_cancel(self, dialog):
        dialog.is_downloading = True
        dialog.on_local_action_clicked()
        assert dialog.is_downloading is False

    def test_on_local_action_clicked_download(self, dialog):
        dialog.is_downloading = False
        dialog.local_downloaded = False
        dialog._start_download = MagicMock()
        dialog.on_local_action_clicked()
        dialog._start_download.assert_called_once()

    def test_on_local_action_clicked_delete(self, dialog):
        dialog.is_downloading = False
        dialog.local_downloaded = True
        dialog._delete_model = MagicMock()
        dialog.on_local_action_clicked()
        dialog._delete_model.assert_called_once()

    def test_delete_model_confirmed(self, dialog):
        from PyQt6.QtWidgets import QMessageBox

        dialog.local_downloaded = True
        with (
            patch.object(
                QMessageBox,
                "warning",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch("shutil.rmtree"),
            patch("os.path.exists", return_value=True),
            patch("os.listdir", return_value=[]),
        ):
            dialog._delete_model()

    def test_on_local_enable_toggled(self, dialog):
        with (
            patch("os.path.exists", return_value=False),
            patch("os.listdir", return_value=[]),
        ):
            dialog._on_local_enable_toggled(False)
            assert not dialog.local_model_combo.isEnabled()

    def test_cleanup_partial_files(self, dialog):
        with (
            patch("os.path.exists", return_value=True),
            patch("os.listdir", return_value=[]),
            patch("shutil.rmtree"),
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            dialog._cleanup_partial_files()


class TestGeminiSection:
    def test_on_test_connection_invalid_key(self, dialog):
        dialog.api_key_input.setText("bad-key")
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            dialog.on_test_connection_clicked()

    def test_on_test_connection_no_genai(self, dialog):
        dialog.api_key_input.setText("AIzaTestKey123")
        with (
            patch("XBrainLab.ui.dialogs.model_settings_dialog.genai", None),
            patch("PyQt6.QtWidgets.QMessageBox.critical"),
        ):
            dialog.on_test_connection_clicked()
        assert not dialog.gemini_enabled

    def test_on_conn_test_success(self, dialog):
        dialog._on_conn_test_success("AIzaKey123")
        assert dialog.gemini_enabled is True
        assert os.environ.get("GEMINI_API_KEY") == "AIzaKey123"

    def test_on_conn_test_error(self, dialog):
        with patch("PyQt6.QtWidgets.QMessageBox.critical"):
            dialog._on_conn_test_error("Connection refused")
        assert dialog.gemini_enabled is False


class TestActivateAndSave:
    def test_update_validation_state_not_ready(self, dialog):
        dialog.local_downloaded = False
        dialog.gemini_enabled = False
        dialog.is_downloading = False
        dialog.update_validation_state()
        assert not dialog.btn_activate.isEnabled()

    def test_update_validation_state_ready(self, dialog):
        dialog.local_downloaded = True
        dialog.gemini_enabled = False
        dialog.is_downloading = False
        dialog.update_validation_state()
        assert dialog.btn_activate.isEnabled()

    def test_on_activate_clicked(self, dialog):
        dialog.local_downloaded = True
        dialog.gemini_enabled = False
        dialog.api_key_input.setText("")
        with patch.object(LLMConfig, "save_to_file"):
            dialog.on_activate_clicked()

    def test_on_activate_clicked_gemini_only(self, dialog):
        dialog.local_downloaded = False
        dialog.gemini_enabled = True
        dialog.api_key_input.setText("AIzaKey123")
        with (
            patch.object(LLMConfig, "save_to_file"),
            patch("builtins.open", MagicMock()),
            patch("os.path.exists", return_value=False),
        ):
            dialog.on_activate_clicked()
        assert dialog.config.active_mode == "gemini"

    def test_save_api_key_to_env_no_key(self, dialog):
        dialog.api_key_input.setText("")
        dialog._save_api_key_to_env()
        # Should return early

    def test_save_api_key_to_env_valid(self, dialog):
        dialog.api_key_input.setText("AIzaValidKey123")
        with (
            patch("os.path.exists", return_value=False),
            patch("builtins.open", MagicMock()),
        ):
            dialog._save_api_key_to_env()


class TestRejectAndClose:
    def test_reject_while_downloading(self, dialog):
        dialog.is_downloading = True
        dialog.reject()
        dialog.downloader.cancel_download.assert_called()

    def test_close_event(self, dialog):
        dialog.is_downloading = True
        from PyQt6.QtGui import QCloseEvent

        event = QCloseEvent()
        dialog.closeEvent(event)
        dialog.downloader.cancel_download.assert_called()

    def test_get_config(self, dialog):
        cfg = dialog.get_config()
        assert cfg is dialog.config


class TestLoadState:
    def test_load_state(self, dialog):
        with (
            patch("os.path.exists", return_value=False),
            patch("os.listdir", return_value=[]),
        ):
            dialog.load_state()
        assert dialog.local_model_combo.currentText() is not None


class TestModelSettingsMoreCoverage:
    """Extra coverage for connection test threading and env file handling."""

    def test_on_test_connection_valid_key_starts_thread(self, dialog):
        """Test that valid API key starts connection test thread."""
        dialog.api_key_input.setText("AIzaValidKey123")
        mock_genai = MagicMock()
        with (
            patch("XBrainLab.ui.dialogs.model_settings_dialog.genai", mock_genai),
            patch("XBrainLab.ui.dialogs.model_settings_dialog.QThread") as MockThread,
            patch(
                "XBrainLab.ui.dialogs.model_settings_dialog.ConnectionTestWorker"
            ) as MockWorker,
        ):
            mock_worker = MockWorker.return_value
            mock_worker.finished = MagicMock()
            mock_worker.error = MagicMock()
            mock_thread = MockThread.return_value
            mock_thread.started = MagicMock()
            mock_thread.finished = MagicMock()
            dialog.on_test_connection_clicked()
            mock_thread.start.assert_called_once()

    def test_load_state_with_gemini_enabled(self, dialog, config):
        config.gemini_enabled = True
        config.gemini_api_key = "AIzaKey"  # pragma: allowlist secret
        with (
            patch("os.path.exists", return_value=False),
            patch("os.listdir", return_value=[]),
        ):
            dialog.load_state()
        assert "Verified" in dialog.gemini_status_label.text()

    def test_save_api_key_to_env_update_existing(self, dialog):
        dialog.api_key_input.setText("AIzaNewKey")  # pragma: allowlist secret
        existing_content = (
            "OTHER=value\nGEMINI_API_KEY=old\nFOO=bar\n"  # pragma: allowlist secret
        )
        from io import StringIO
        from unittest.mock import mock_open

        mock_read = mock_open(read_data=existing_content)
        written_lines = []

        def fake_open(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if "w" in mode:
                m = MagicMock()
                m.__enter__ = MagicMock(return_value=m)
                m.__exit__ = MagicMock(return_value=False)
                m.writelines = lambda lines: written_lines.extend(lines)
                return m
            return StringIO(existing_content)

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", side_effect=fake_open),
        ):
            dialog._save_api_key_to_env()
        assert any("AIzaNewKey" in line for line in written_lines)

    def test_save_api_key_to_env_append_new(self, dialog):
        dialog.api_key_input.setText("AIzaNewKey")
        existing_content = "OTHER=value\n"
        from io import StringIO

        written_lines = []

        def fake_open(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if "w" in mode:
                m = MagicMock()
                m.__enter__ = MagicMock(return_value=m)
                m.__exit__ = MagicMock(return_value=False)
                m.writelines = lambda lines: written_lines.extend(lines)
                return m
            return StringIO(existing_content)

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", side_effect=fake_open),
        ):
            dialog._save_api_key_to_env()
        assert any("GEMINI_API_KEY=AIzaNewKey" in line for line in written_lines)
