"""Unit tests for the local-only assistant settings dialog."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QPushButton

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.downloader import (
    MODEL_DOWNLOAD_TIMEOUT_PUBLIC_MESSAGE,
    ModelDownloadFailureCode,
    ModelDownloadOutcome,
    ModelDownloadStatus,
    ModelDownloadTarget,
)
from XBrainLab.llm.core.model_catalog import local_model_spec
from XBrainLab.llm.core.model_download_lifecycle import (
    ModelCacheCleanupReason,
    ModelCacheCleanupRequest,
    ModelCacheCleanupResult,
    ModelStatusInspectionRequest,
    ModelStatusInspectionResult,
)


class _FakeDownloadLifecycle(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(object)
    terminal = pyqtSignal(bool, str)
    cache_cleanup_finished = pyqtSignal(object)
    inspection_finished = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.idle = True
        self.cancel_requests = 0
        self.start_requests: list[tuple[str, str]] = []
        self.removal_requests: list[tuple[str, str, ModelCacheCleanupReason]] = []
        self.inspection_requests: list[ModelStatusInspectionRequest] = []
        self.active_target: ModelDownloadTarget | None = None

    def start_download(self, repo_id: str, cache_dir: str) -> bool:
        if not self.idle:
            return False
        self.idle = False
        self.start_requests.append((repo_id, cache_dir))
        self.active_target = ModelDownloadTarget.create(repo_id, cache_dir)
        return True

    def request_cancel(self) -> bool:
        self.cancel_requests += 1
        return self.idle

    def request_shutdown(self) -> bool:
        return self.request_cancel()

    def request_cache_removal(
        self,
        repo_id: str,
        cache_dir: str,
        *,
        reason: ModelCacheCleanupReason,
    ) -> bool:
        if not self.idle:
            return False
        self.idle = False
        self.removal_requests.append((repo_id, cache_dir, reason))
        return True

    def is_idle(self) -> bool:
        return self.idle

    def request_model_inspection(
        self,
        request: ModelStatusInspectionRequest,
    ) -> bool:
        self.inspection_requests.append(request)
        return True

    def complete_inspection(
        self,
        *,
        installed: bool,
        runtime_ready: bool,
        runtime_message: str,
        current_cache_bytes: int = 0,
        estimated_download_bytes: int = 8_000_000_000,
        projected_cache_bytes: int = 8_000_000_000,
        available_disk_bytes: int = 100_000_000_000,
        preflight_ok: bool = True,
        preflight_message: str = "Ready",
        cleanup_candidates: tuple[str, ...] = (),
        resolved_config: LLMConfig | None = None,
    ) -> ModelStatusInspectionResult:
        request = self.inspection_requests[-1]
        result = ModelStatusInspectionResult(
            request=request,
            installed=installed,
            runtime_ready=runtime_ready,
            runtime_message=runtime_message,
            estimated_download_bytes=estimated_download_bytes,
            current_cache_bytes=current_cache_bytes,
            projected_cache_bytes=projected_cache_bytes,
            available_disk_bytes=available_disk_bytes,
            preflight_ok=preflight_ok,
            preflight_message=preflight_message,
            cleanup_candidates=cleanup_candidates,
            resolved_config=resolved_config,
        )
        self.inspection_finished.emit(result)
        return result


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
    lifecycle = _FakeDownloadLifecycle()
    with patch.object(LLMConfig, "load_from_file", return_value=config):
        from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

        dlg = ModelSettingsDialog(
            parent=None,
            config=config,
            agent_manager=MagicMock(),
            download_lifecycle=lifecycle,
        )
        qtbot.addWidget(dlg)
        yield dlg


class TestModelSettingsInit:
    def test_creates_dialog(self, dialog):
        assert dialog.windowTitle() == "Assistant Settings"
        assert dialog.isVisible() is False

    def test_constructor_defers_cache_scan_and_runtime_probe(
        self,
        qtbot,
        config,
    ):
        lifecycle = _FakeDownloadLifecycle()
        with (
            patch.object(LLMConfig, "load_from_file", return_value=config),
            patch(
                "XBrainLab.llm.core.model_download_lifecycle.plan_model_download",
                side_effect=AssertionError("cache scan ran in constructor"),
            ),
            patch.object(
                config,
                "has_local_model_cache",
                side_effect=AssertionError("cache probe ran in constructor"),
            ),
            patch.object(
                config,
                "local_backend_ready",
                side_effect=AssertionError("runtime probe ran in constructor"),
            ),
            patch.object(
                config,
                "local_backend_status_message",
                side_effect=AssertionError("runtime status ran in constructor"),
            ),
        ):
            from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

            created = ModelSettingsDialog(
                parent=None,
                config=config,
                download_lifecycle=lifecycle,
            )
            qtbot.addWidget(created)

        assert lifecycle.inspection_requests == []
        assert created.local_status_label.text() == "Model: Checking..."
        qtbot.waitUntil(lambda: len(lifecycle.inspection_requests) == 1, timeout=1000)

    def test_constructor_defers_persisted_config_and_torch_defaults(self, qtbot):
        lifecycle = _FakeDownloadLifecycle()
        with patch.object(
            LLMConfig,
            "load_from_file",
            side_effect=AssertionError("persisted config loaded in constructor"),
        ):
            from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

            created = ModelSettingsDialog(
                parent=None,
                config=None,
                download_lifecycle=lifecycle,
            )
            qtbot.addWidget(created)

        assert lifecycle.inspection_requests == []
        qtbot.waitUntil(lambda: len(lifecycle.inspection_requests) == 1, timeout=1000)
        assert lifecycle.inspection_requests[0].load_persisted_config is True

    def test_combo_has_only_approved_local_models(self, dialog):
        model_labels = [
            dialog.local_model_combo.itemText(i)
            for i in range(dialog.local_model_combo.count())
        ]
        model_ids = [
            dialog.local_model_combo.itemData(i)
            for i in range(dialog.local_model_combo.count())
        ]

        assert model_ids == LLMConfig.allowed_local_model_ids()
        assert model_ids == ["ibm-granite/granite-3.3-2b-instruct"]
        expected_labels: list[str] = []
        for model_id in model_ids:
            spec = local_model_spec(model_id)
            assert spec is not None
            expected_labels.append(spec.label)
        assert model_labels == expected_labels
        assert all("/" not in label for label in model_labels)
        assert all("Qwen" not in str(model_id) for model_id in model_ids)
        assert dialog.model_section_label.buddy() is dialog.local_model_combo
        assert dialog.local_model_combo.accessibleName() == "Assistant model"

    def test_retired_phi_config_shows_migration_notice_without_mutating_config(
        self,
        qtbot,
    ):
        from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

        legacy_model = "microsoft/Phi-4-mini-instruct"
        config = LLMConfig(model_name=legacy_model, device="cpu")
        created = ModelSettingsDialog(
            parent=None,
            config=config,
            download_lifecycle=_FakeDownloadLifecycle(),
        )
        qtbot.addWidget(created)

        assert config.model_name == legacy_model
        assert created.local_model_combo.currentData() == (
            "ibm-granite/granite-3.3-2b-instruct"
        )
        assert created.model_migration_label.isHidden() is False
        assert "no longer available" in created.model_migration_label.text()
        assert "not changed" in created.model_migration_label.text()

    def test_no_remote_runtime_widgets_are_exposed(self, dialog):
        assert not hasattr(dialog, "api_key_input")
        assert not hasattr(dialog, "test_conn_btn")
        assert not hasattr(dialog, "gemini_group")
        assert not hasattr(dialog, "gemini_model_combo")

    def test_uses_one_enable_setting_and_a_save_action(self, dialog):
        assert dialog.local_enable_chk.text() == "Use local assistant"
        assert dialog.btn_activate.text() == "Save"
        assert not any(
            button.text() == "Activate" for button in dialog.findChildren(QPushButton)
        )

    def test_presents_response_presets_without_hiding_exact_controls(self, dialog):
        assert dialog.response_style_control.selected_key() == "balanced"
        assert dialog.response_length_control.selected_key() == "standard"
        assert dialog.advanced_content.isHidden()

        dialog.response_style_control.set_selected("precise", emit=True)
        dialog.response_length_control.set_selected("detailed", emit=True)

        assert dialog.temperature_spin.value() == pytest.approx(0.2)
        assert dialog.top_p_spin.value() == pytest.approx(0.8)
        assert dialog.max_tokens_spin.value() == 1024
        assert "Exploratory" not in {
            button.text()
            for button in dialog.response_style_control.findChildren(QPushButton)
        }

        dialog.advanced_toggle.setChecked(True)
        assert not dialog.advanced_content.isHidden()
        assert dialog.temperature_spin.isVisibleTo(dialog)
        assert dialog.top_p_spin.isVisibleTo(dialog)
        assert dialog.max_tokens_spin.isVisibleTo(dialog)

    def test_custom_exact_values_are_named_in_collapsed_preset_summary(
        self,
        dialog,
    ):
        dialog.temperature_spin.setValue(0.31)

        assert dialog.response_style_control.selected_key() is None
        assert dialog.advanced_toggle.text() == "Advanced settings · Custom"

    def test_settings_sections_and_footer_follow_product_hierarchy(self, dialog):
        assert dialog.heading_label.text() == "Assistant Settings"
        assert dialog.model_section_label.text() == "Model"
        assert dialog.response_style_label.text() == "Response style"
        assert dialog.response_length_label.text() == "Response length"
        assert dialog.btn_cancel.text() == "Cancel"
        assert dialog.btn_activate.text() == "Save"
        assert dialog.btn_cancel.icon().isNull()
        assert dialog.btn_activate.icon().isNull()

    def test_collapsed_settings_fit_all_primary_controls_before_scrolling(
        self,
        dialog,
        qtbot,
    ):
        dialog.show()
        qtbot.wait(20)

        body_viewport = dialog.settings_body_scroll.viewport()
        assert dialog.settings_body_scroll.verticalScrollBar().value() == 0
        assert body_viewport.rect().contains(
            dialog.advanced_toggle.mapTo(
                body_viewport,
                dialog.advanced_toggle.rect().center(),
            )
        )
        assert dialog.rect().contains(
            dialog.btn_activate.mapTo(dialog, dialog.btn_activate.rect().center())
        )
        assert dialog.rect().contains(
            dialog.btn_cancel.mapTo(dialog, dialog.btn_cancel.rect().center())
        )

    def test_dialog_supports_reasonable_resize_without_fixed_geometry(
        self,
        dialog,
        qtbot,
    ):
        dialog.show()
        qtbot.wait(0)
        minimum = dialog.minimumSize()

        dialog.resize(minimum.width() + 180, minimum.height() + 120)
        qtbot.wait(0)

        assert dialog.width() >= minimum.width() + 180
        assert dialog.height() >= minimum.height() + 120
        assert dialog.maximumWidth() > dialog.minimumWidth()
        assert dialog.maximumHeight() > dialog.minimumHeight()
        for widget in (
            dialog.local_status_label,
            dialog.local_runtime_label,
            dialog.local_resource_label,
            dialog.btn_activate,
            dialog.btn_cancel,
        ):
            assert dialog.rect().contains(widget.geometry().center())

    def test_expanded_advanced_settings_keep_footer_on_constrained_screen(
        self,
        dialog,
        qtbot,
    ):
        dialog.show()
        dialog.advanced_toggle.setChecked(True)
        qtbot.wait(20)
        dialog.resize(520, 552)
        qtbot.wait(20)

        assert dialog.height() <= 552
        assert dialog.minimumSizeHint().height() <= 552
        assert dialog.btn_activate.isVisibleTo(dialog)
        assert dialog.btn_cancel.isVisibleTo(dialog)
        body_viewport = dialog.settings_body_scroll.viewport()
        dialog.settings_body_scroll.ensureWidgetVisible(dialog.max_tokens_spin)
        qtbot.wait(20)
        for field in (
            dialog.temperature_spin,
            dialog.top_p_spin,
            dialog.max_tokens_spin,
        ):
            assert field.isVisibleTo(dialog)
        assert body_viewport.rect().contains(
            dialog.max_tokens_spin.mapTo(
                body_viewport,
                dialog.max_tokens_spin.rect().center(),
            )
        )
        assert dialog.rect().contains(
            dialog.btn_activate.mapTo(dialog, dialog.btn_activate.rect().center())
        )
        assert dialog.rect().contains(
            dialog.btn_cancel.mapTo(dialog, dialog.btn_cancel.rect().center())
        )

    def test_legacy_remote_config_loads_as_local_only(self, qtbot, config):
        config.inference_mode = "gemini"
        config.active_mode = "gemini"
        config.gemini_enabled = True

        with patch.object(LLMConfig, "load_from_file", return_value=config):
            from XBrainLab.ui.dialogs.model_settings_dialog import (
                ModelSettingsDialog,
            )

            dlg = ModelSettingsDialog(
                parent=None,
                config=config,
                download_lifecycle=_FakeDownloadLifecycle(),
            )
            qtbot.addWidget(dlg)

        assert dlg.config.assistant_runtime_selection().backend_mode == "local"
        assert dlg.config.active_mode == "local"
        assert dlg.config.inference_mode == "local"


class TestLocalModelSection:
    def test_check_local_model_status_not_downloaded(self, dialog):
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=False,
            runtime_ready=False,
            runtime_message="Local runtime unavailable. Model cache not found.",
        )

        assert (
            "not downloaded" in dialog.local_status_label.text().lower()
            or "install" in dialog.local_action_btn.text().lower()
        )

    def test_check_local_model_status_downloaded(self, dialog):
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=True,
            runtime_ready=True,
            runtime_message="Local runtime ready.",
        )

        assert dialog.local_downloaded is True
        assert dialog.local_status_label.text() == "Model: Installed"
        assert dialog.local_action_btn.text() == "Delete"
        assert dialog.local_action_btn.property("destructive") is True

    def test_status_runtime_and_cache_are_rendered_from_one_snapshot(self, dialog):
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=True,
            runtime_ready=True,
            runtime_message="Local runtime ready.",
            estimated_download_bytes=7_690_000_000,
            current_cache_bytes=3_250_000_000,
            projected_cache_bytes=10_940_000_000,
        )

        assert dialog.local_status_label.text() == "Model: Installed"
        assert dialog.local_runtime_label.text() == "Environment check: Ready"
        assert "3.25 GB" in dialog.local_resource_label.text()
        assert "[+]" not in dialog.local_status_label.text()

    def test_status_summary_never_exposes_the_local_cache_path(self, dialog):
        sensitive_cache = dialog.config.cache_dir
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=False,
            runtime_ready=False,
            runtime_message="Local runtime unavailable. Model cache not found.",
            current_cache_bytes=3_000_000_000,
            projected_cache_bytes=10_000_000_000,
        )

        visible = " ".join(
            (
                dialog.local_status_label.text(),
                dialog.local_runtime_label.text(),
                dialog.local_resource_label.text(),
            )
        )
        assert sensitive_cache not in visible

    def test_environment_readiness_keeps_last_start_failure_visible(
        self,
        qtbot,
        config,
    ):
        lifecycle = _FakeDownloadLifecycle()
        manager = MagicMock()
        manager.assistant_runtime_settings_notice.return_value = (
            "The local model could not start. Check the installed model and runtime."
        )
        with patch.object(LLMConfig, "load_from_file", return_value=config):
            from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

            created = ModelSettingsDialog(
                parent=None,
                config=config,
                agent_manager=manager,
                download_lifecycle=lifecycle,
            )
            qtbot.addWidget(created)

        qtbot.waitUntil(lambda: len(lifecycle.inspection_requests) == 1, timeout=1000)
        lifecycle.complete_inspection(
            installed=True,
            runtime_ready=True,
            runtime_message="Local runtime ready.",
        )

        assert created.local_runtime_label.text() == "Environment check: Ready"
        assert created.last_runtime_attempt_label.isHidden() is False
        assert created.last_runtime_attempt_label.text().startswith(
            "Last start attempt failed:"
        )

    def test_start_download(self, dialog):
        dialog.is_downloading = False
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=False,
            runtime_ready=False,
            runtime_message="Local runtime unavailable. Model cache not found.",
            preflight_ok=True,
            preflight_message="Download allowed",
        )

        dialog._start_download()

        assert dialog.is_downloading is True
        assert "cancel" in dialog.local_action_btn.text().lower()
        assert not dialog.download_progress.isHidden()
        assert dialog.download_progress.minimum() == 0
        assert dialog.download_progress.maximum() == 0

        dialog.on_download_progress(42, "Downloading model files...")

        assert dialog.download_progress.maximum() == 100
        assert dialog.download_progress.value() == 42
        assert dialog.local_status_label.text() == "Downloading model files..."

    def test_start_failure_is_not_misreported_as_an_active_download(self, dialog):
        dialog.is_downloading = False
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=False,
            runtime_ready=False,
            runtime_message="Local runtime unavailable. Model cache not found.",
        )
        with patch.object(
            dialog.download_lifecycle,
            "start_download",
            return_value=False,
        ):
            dialog.download_lifecycle.idle = True
            dialog._start_download()

        assert dialog.is_downloading is False
        assert dialog.local_status_label.text() == "Download could not start."
        assert "another" not in dialog.local_status_label.text().lower()

    def test_start_download_blocks_failed_preflight(self, dialog):
        dialog.is_downloading = False
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=False,
            runtime_ready=False,
            runtime_message="Local runtime unavailable. Model cache not found.",
            preflight_ok=False,
            preflight_message="cache too large",
            current_cache_bytes=15_000_000_000,
            estimated_download_bytes=8_000_000_000,
            available_disk_bytes=100_000_000_000,
            projected_cache_bytes=23_000_000_000,
            cleanup_candidates=("/models/blocked",),
        )
        with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning:
            dialog._start_download()

        assert dialog.is_downloading is False
        mock_warning.assert_called_once()
        rendered = str(mock_warning.call_args.args[2])
        assert "/models" not in rendered
        assert "/models/blocked" not in rendered

    @pytest.mark.parametrize(
        "sensitive",
        (
            "/home/alice/.cache/huggingface/private-model",
            r"C:\Users\alice\.cache\huggingface\private-model",
            r"\\server\private\model-cache",
            "PermissionError: token=hf_super_secret",
        ),
    )
    def test_download_failure_dialog_never_exposes_diagnostics(
        self,
        dialog,
        sensitive,
    ):
        target = ModelDownloadTarget.create(
            dialog.local_model_combo.currentData(),
            dialog.config.cache_dir,
        )
        outcome = ModelDownloadOutcome(
            target=target,
            status=ModelDownloadStatus.FAILED,
            message=sensitive,
        )
        dialog.download_lifecycle.idle = True

        with patch("PyQt6.QtWidgets.QMessageBox.critical") as critical:
            dialog.on_download_failed(outcome)

        rendered = " ".join(str(value) for value in critical.call_args.args)
        assert sensitive not in rendered
        assert "Check the application log" in rendered

    def test_download_timeout_explains_retry_without_exposing_diagnostics(
        self,
        dialog,
    ):
        target = ModelDownloadTarget.create(
            dialog.local_model_combo.currentData(),
            dialog.config.cache_dir,
        )
        outcome = ModelDownloadOutcome(
            target=target,
            status=ModelDownloadStatus.FAILED,
            message=MODEL_DOWNLOAD_TIMEOUT_PUBLIC_MESSAGE,
            failure_code=ModelDownloadFailureCode.TIMEOUT,
            diagnostic_message="/private/cache token=hf_super_secret deadline exceeded",
        )
        dialog.download_lifecycle.idle = True

        with patch("PyQt6.QtWidgets.QMessageBox.critical") as critical:
            dialog.on_download_failed(outcome)

        rendered = " ".join(str(value) for value in critical.call_args.args)
        assert MODEL_DOWNLOAD_TIMEOUT_PUBLIC_MESSAGE in rendered
        assert "/private/cache" not in rendered
        assert "hf_super_secret" not in rendered
        assert dialog.local_status_label.text() == "Download timed out"
        assert dialog.local_action_btn.text() == "Retry"

    @pytest.mark.parametrize(
        "sensitive",
        (
            "/home/alice/.cache/huggingface/private-model",
            r"C:\Users\alice\.cache\huggingface\private-model",
            r"\\server\private\model-cache",
            "RuntimeError: token=hf_super_secret",
        ),
    )
    def test_cache_cleanup_dialog_uses_public_message_only(
        self,
        dialog,
        sensitive,
    ):
        target = ModelDownloadTarget.create(
            dialog.local_model_combo.currentData(),
            dialog.config.cache_dir,
        )
        result = ModelCacheCleanupResult(
            request=ModelCacheCleanupRequest(
                target=target,
                reason=ModelCacheCleanupReason.USER_DELETE,
            ),
            errors=(sensitive,),
        )
        dialog.download_lifecycle.idle = True

        with patch("PyQt6.QtWidgets.QMessageBox.warning") as warning:
            dialog.on_cache_cleanup_finished(result)

        rendered = " ".join(str(value) for value in warning.call_args.args)
        assert sensitive not in rendered
        assert result.public_message in rendered

    def test_on_download_finished(self, dialog):
        dialog.is_downloading = True
        target = ModelDownloadTarget.create(
            dialog.local_model_combo.currentData(),
            dialog.config.cache_dir,
        )
        outcome = ModelDownloadOutcome(
            target=target,
            status=ModelDownloadStatus.SUCCEEDED,
            message="/path/to/model",
            model_path="/path/to/model",
        )
        dialog.download_lifecycle.idle = True
        with patch("PyQt6.QtWidgets.QMessageBox.information"):
            dialog.on_download_finished(outcome)

        assert dialog.is_downloading is False

    def test_cancel_outcome_uses_original_target_with_exact_model_choice(
        self,
        dialog,
    ):
        original_repo = dialog.local_model_combo.itemData(0)
        target = ModelDownloadTarget.create(original_repo, dialog.config.cache_dir)
        outcome = ModelDownloadOutcome(
            target=target,
            status=ModelDownloadStatus.CANCELLED,
            message="Cancelled by user",
        )
        dialog.is_downloading = True
        dialog.download_lifecycle.idle = True

        dialog.on_download_failed(outcome)

        assert outcome.target.repo_id == original_repo
        assert dialog.local_model_combo.currentData() == original_repo
        assert dialog.is_downloading is False
        assert not hasattr(dialog, "_cleanup_partial_files")

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

    def test_delete_model_delegates_recursive_cleanup_to_app_lifecycle(
        self,
        dialog,
    ):
        from PyQt6.QtWidgets import QMessageBox

        repo_id = dialog.local_model_combo.currentData()
        dialog.local_downloaded = True
        dialog.agent_manager.prepare_model_deletion.return_value = True
        with (
            patch.object(
                QMessageBox,
                "warning",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch("shutil.rmtree") as mock_rmtree,
        ):
            dialog._delete_model()

        assert dialog.download_lifecycle.removal_requests == [
            (
                repo_id,
                dialog.config.cache_dir,
                ModelCacheCleanupReason.USER_DELETE,
            )
        ]
        assert dialog.is_downloading is True
        mock_rmtree.assert_not_called()

    def test_on_local_enable_toggled(self, dialog):
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=False,
            runtime_ready=False,
            runtime_message="Local runtime unavailable. Model cache not found.",
        )
        dialog.local_enable_chk.setChecked(False)
        dialog._on_local_enable_toggled(False)

        assert dialog.local_model_combo.isEnabled()
        assert dialog.local_action_btn.isEnabled()
        assert dialog.btn_activate.isEnabled()


class TestActivateAndSave:
    def test_update_validation_state_not_ready(self, dialog):
        dialog.local_downloaded = False
        dialog.is_downloading = False
        dialog.update_validation_state()

        assert not dialog.btn_activate.isEnabled()

    def test_update_validation_state_allows_saving_disabled_assistant(self, dialog):
        dialog.local_enable_chk.setChecked(False)
        dialog.local_downloaded = False
        dialog.is_downloading = False

        dialog.update_validation_state()

        assert dialog.btn_activate.isEnabled()

    def test_update_validation_state_ready(self, dialog):
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=True,
            runtime_ready=True,
            runtime_message="Local runtime ready.",
        )
        dialog.is_downloading = False
        dialog.update_validation_state()

        assert dialog.btn_activate.isEnabled()

    def test_update_validation_state_blocks_missing_local_runtime(self, dialog):
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=True,
            runtime_ready=False,
            runtime_message="Local runtime unavailable. Missing accelerate.",
        )
        dialog.is_downloading = False
        dialog.local_enable_chk.setChecked(True)
        dialog.update_validation_state()

        assert not dialog.btn_activate.isEnabled()

    def test_model_status_shows_cpu_fallback(self, dialog):
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=True,
            runtime_ready=True,
            runtime_message=(
                "Local runtime ready. GPU execution is unavailable in this "
                "environment, so startup will fall back to CPU and disable "
                "4-bit loading."
            ),
        )

        assert "fall back to CPU" in dialog.local_runtime_label.text()

    def test_on_activate_clicked(self, dialog):
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=True,
            runtime_ready=True,
            runtime_message="Local runtime ready.",
        )
        with patch.object(LLMConfig, "save_to_file", return_value=True) as save:
            dialog.on_activate_clicked()

        save.assert_called_once()
        assert dialog.config.inference_mode == "local"
        assert dialog.config.active_mode == "local"
        assert not hasattr(dialog.config, "gemini_enabled")

    def test_save_failure_stays_open_and_shows_actionable_inline_error(self, dialog):
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=True,
            runtime_ready=True,
            runtime_message="Local runtime ready.",
        )
        accepted = MagicMock()
        dialog.accepted.connect(accepted)
        dialog.show()

        with patch.object(LLMConfig, "save_to_file", return_value=False) as save:
            dialog.on_activate_clicked()

        save.assert_called_once_with()
        accepted.assert_not_called()
        assert dialog.isVisible()
        assert dialog.save_error_label.isVisible()
        assert "could not be saved" in dialog.save_error_label.text().lower()
        assert "writable" in dialog.save_error_label.text().lower()

    def test_first_run_save_failure_uses_same_non_accepting_error_boundary(
        self,
        qtbot,
    ):
        from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog

        lifecycle = _FakeDownloadLifecycle()
        first_run_config = LLMConfig(device="cpu")
        first_run_config.local_model_enabled = False
        created = ModelSettingsDialog(
            parent=None,
            config=None,
            download_lifecycle=lifecycle,
        )
        qtbot.addWidget(created)
        qtbot.waitUntil(lambda: len(lifecycle.inspection_requests) == 1, timeout=1000)
        lifecycle.complete_inspection(
            installed=False,
            runtime_ready=False,
            runtime_message="Local runtime unavailable. Model cache not found.",
            resolved_config=first_run_config,
        )
        accepted = MagicMock()
        created.accepted.connect(accepted)
        created.show()

        with patch.object(LLMConfig, "save_to_file", return_value=False) as save:
            created.on_activate_clicked()

        save.assert_called_once_with()
        accepted.assert_not_called()
        assert created.config is first_run_config
        assert created.isVisible()
        assert created.save_error_label.isVisible()
        assert "could not be saved" in created.save_error_label.text().lower()

    def test_on_activate_clicked_blocks_local_runtime_gap(self, dialog):
        dialog.check_local_model_status()
        dialog.download_lifecycle.complete_inspection(
            installed=True,
            runtime_ready=False,
            runtime_message="Missing accelerate",
        )
        dialog.local_enable_chk.setChecked(True)
        with (
            patch.object(LLMConfig, "save_to_file") as mock_save,
            patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
        ):
            dialog.on_activate_clicked()

        mock_critical.assert_called_once()
        mock_save.assert_not_called()


class TestRejectAndClose:
    def test_accept_detaches_download_observers(self, dialog):
        dialog.local_status_label.setText("Before accept")

        dialog.accept()
        dialog.download_lifecycle.progress.emit(10, "Hidden callback")

        assert dialog.local_status_label.text() == "Before accept"

    def test_reject_while_downloading(self, dialog):
        dialog.is_downloading = True
        dialog.local_status_label.setText("Before reject")
        dialog.reject()
        dialog.download_lifecycle.progress.emit(10, "Hidden callback")

        assert dialog.download_lifecycle.cancel_requests == 1
        assert dialog.is_downloading is True
        assert dialog.local_status_label.text() == "Before reject"

    def test_close_event(self, dialog):
        dialog.is_downloading = True
        dialog.local_status_label.setText("Before close")
        from PyQt6.QtGui import QCloseEvent

        event = QCloseEvent()
        dialog.closeEvent(event)
        dialog.download_lifecycle.progress.emit(10, "Hidden callback")

        assert dialog.download_lifecycle.cancel_requests == 1
        assert dialog.is_downloading is True
        assert event.isAccepted() is True
        assert dialog.local_status_label.text() == "Before close"

    def test_get_config(self, dialog):
        cfg = dialog.get_config()
        assert cfg is dialog.config
