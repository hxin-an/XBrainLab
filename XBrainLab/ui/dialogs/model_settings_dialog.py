"""AI assistant settings dialog for the local-only runtime.

Provides UI for managing approved local model downloads and generation
parameters. Remote assistant runtimes are not part of the product path.
"""

import contextlib
import weakref

from PyQt6.QtCore import QCoreApplication, QObject, QSignalBlocker, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.downloader import ModelDownloadOutcome
from XBrainLab.llm.core.model_catalog import format_bytes
from XBrainLab.llm.core.model_download_lifecycle import (
    ModelCacheCleanupReason,
    ModelCacheCleanupResult,
    ModelDownloadLifecycle,
    ModelDownloadLifecycleContract,
    ModelStatusInspectionRequest,
    ModelStatusInspectionResult,
)


class ModelSettingsDialog(QDialog):
    """Dialog for configuring the local AI assistant runtime.

    Provides UI for selecting, installing, deleting, and activating approved
    local models.

    Attributes:
        agent_manager: Reference to AgentManager for safe backend switching.
        config: The current LLM configuration.
        local_downloaded: Whether the selected local model is downloaded.
        download_lifecycle: Application owner for model download resources.
        is_downloading: Whether a download is currently in progress.

    """

    def __init__(
        self,
        parent=None,
        config: LLMConfig | None = None,
        agent_manager=None,
        download_lifecycle: ModelDownloadLifecycleContract | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("AI Assistant Settings")
        self.setMinimumSize(460, 400)
        self.resize(500, 440)

        # Reference to AgentManager for safe deletion (switching backend)
        self.agent_manager = agent_manager

        # Load config or create default
        self._persisted_config_pending = config is None
        self.config = config or LLMConfig(device="cpu")
        self.config._force_local_runtime_selection()
        self.local_downloaded = False

        # Product composition injects the AgentManager-owned lifecycle. The
        # fallback is parented to the Qt application for standalone dialogs.
        if download_lifecycle is None:
            lifecycle_parent = (
                agent_manager
                if isinstance(agent_manager, QObject)
                else parent
                if isinstance(parent, QObject)
                else QCoreApplication.instance()
            )
            download_lifecycle = ModelDownloadLifecycle(
                parent=lifecycle_parent,
            )
        self.download_lifecycle = download_lifecycle
        self.download_lifecycle.progress.connect(self.on_download_progress)
        self.download_lifecycle.finished.connect(self.on_download_finished)
        self.download_lifecycle.failed.connect(self.on_download_failed)
        self.download_lifecycle.cache_cleanup_finished.connect(
            self.on_cache_cleanup_finished
        )
        self.download_lifecycle.inspection_finished.connect(
            self._on_model_inspection_finished
        )
        self._download_observers_attached = True
        self.is_downloading = self.download_lifecycle.active_target is not None
        self._inspection_request_id = 0
        self._pending_inspection_request_id: int | None = None
        self._current_local_model_state: ModelStatusInspectionResult | None = None

        self.init_ui()
        self.load_state()

    def init_ui(self):
        """Initialize the dialog UI with local model settings."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # --- Local Model Section ---
        local_group = QGroupBox("Local Model")
        local_layout = QVBoxLayout()

        # Model Dropdown
        self.local_model_combo = QComboBox()
        self.local_model_combo.addItems(LLMConfig.allowed_local_model_ids())
        self.local_model_combo.currentTextChanged.connect(self.check_local_model_status)
        local_layout.addWidget(QLabel("Select Model:"))
        local_layout.addWidget(self.local_model_combo)

        # Status & Actions
        status_layout = QHBoxLayout()
        self.local_status_label = QLabel("Status: Checking...")
        status_layout.addWidget(self.local_status_label)
        status_layout.addStretch()

        self.local_action_btn = QPushButton("Install Model")
        self.local_action_btn.setFixedWidth(100)
        self.local_action_btn.clicked.connect(self.on_local_action_clicked)
        status_layout.addWidget(self.local_action_btn)
        local_layout.addLayout(status_layout)

        self.local_runtime_label = QLabel("Runtime: Checking...")
        self.local_runtime_label.setWordWrap(True)
        local_layout.addWidget(self.local_runtime_label)

        self.local_resource_label = QLabel("")
        self.local_resource_label.setWordWrap(True)
        local_layout.addWidget(self.local_resource_label)

        self.local_enable_chk = QCheckBox("Use local assistant")
        self.local_enable_chk.toggled.connect(self._on_local_enable_toggled)
        local_layout.addWidget(self.local_enable_chk)

        local_group.setLayout(local_layout)
        layout.addWidget(local_group)

        # --- Generation Parameters Section ---
        gen_group = QGroupBox("Informational answer style")
        gen_layout = QVBoxLayout()

        # Temperature
        temp_layout = QHBoxLayout()
        temp_layout.addWidget(QLabel("Temperature:"))
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setDecimals(2)
        self.temperature_spin.setValue(self.config.temperature)
        self.temperature_spin.setToolTip(
            "Controls variety in explanatory answers. Workflow actions always "
            "use deterministic decoding."
        )
        temp_layout.addWidget(self.temperature_spin)
        gen_layout.addLayout(temp_layout)

        # Top-p
        topp_layout = QHBoxLayout()
        topp_layout.addWidget(QLabel("Top-p:"))
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setDecimals(2)
        self.top_p_spin.setValue(self.config.top_p)
        self.top_p_spin.setToolTip("Nucleus sampling cutoff for explanatory answers.")
        topp_layout.addWidget(self.top_p_spin)
        gen_layout.addLayout(topp_layout)

        # Max New Tokens
        tokens_layout = QHBoxLayout()
        tokens_layout.addWidget(QLabel("Max Tokens:"))
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(64, 8192)
        self.max_tokens_spin.setSingleStep(64)
        self.max_tokens_spin.setValue(self.config.max_new_tokens)
        self.max_tokens_spin.setToolTip(
            "Maximum length of explanatory answers. Workflow actions use a "
            "separate safety limit."
        )
        tokens_layout.addWidget(self.max_tokens_spin)
        gen_layout.addLayout(tokens_layout)

        gen_group.setLayout(gen_layout)
        layout.addWidget(gen_group)

        layout.addStretch()

        # --- Footer ---
        footer_layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_activate = QPushButton("Save")
        self.btn_activate.setEnabled(False)
        self.btn_activate.clicked.connect(self.on_activate_clicked)
        # Keep the primary Save action visually distinct from Cancel.
        self.btn_activate.setStyleSheet(
            """
            QPushButton {
                background-color: #007bff; color: white; border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:disabled { background-color: #555; color: #aaa; }
        """,
        )

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_activate)

        footer_layout.addLayout(btn_layout)
        layout.addLayout(footer_layout)

    def load_state(self):
        """Load lightweight config state and defer cache/runtime inspection."""
        selection = self.config.assistant_runtime_selection()

        with QSignalBlocker(self.local_model_combo):
            index = self.local_model_combo.findText(self.config.model_name)
            if index >= 0:
                self.local_model_combo.setCurrentIndex(index)

        with QSignalBlocker(self.local_enable_chk):
            self.local_enable_chk.setChecked(self.config.local_model_enabled)
        self.config.active_mode = selection.ui_active_mode
        self.config.inference_mode = selection.backend_mode

        self._show_model_status_checking()
        self.update_validation_state()
        dialog_ref = weakref.ref(self)
        QTimer.singleShot(
            0,
            lambda ref=dialog_ref: ModelSettingsDialog._run_deferred_status_check(ref),
        )

    @staticmethod
    def _run_deferred_status_check(dialog_ref) -> None:
        """Start deferred inspection without retaining a closed dialog."""
        dialog = dialog_ref()
        if dialog is not None:
            dialog.check_local_model_status()

    def _show_model_status_checking(self) -> None:
        """Render a non-blocking placeholder while inspection runs."""
        self._current_local_model_state = None
        self.local_downloaded = False
        self.local_status_label.setText("Model: Checking...")
        self.local_status_label.setStyleSheet("color: #888888;")
        self.local_runtime_label.setText("Runtime: Checking...")
        self.local_runtime_label.setStyleSheet("color: #888888;")
        self.local_resource_label.setText("")
        self.local_action_btn.setText("Checking...")
        self.local_action_btn.setEnabled(False)

    def _render_local_model_state(
        self,
        state: ModelStatusInspectionResult,
    ) -> None:
        """Render a coherent model state without re-querying the filesystem."""
        self._current_local_model_state = state
        self.local_downloaded = state.installed
        if state.installed:
            self.local_status_label.setText("Model: Installed")
            self.local_status_label.setStyleSheet("color: #4caf50;")
            self.local_action_btn.setText("Delete")
        else:
            self.local_status_label.setText("Model: Not installed")
            self.local_status_label.setStyleSheet("color: #888888;")
            self.local_action_btn.setText("Install Model")
        self.local_action_btn.setEnabled(
            not self.is_downloading and not state.diagnostic_message
        )

        if state.installed:
            self.local_resource_label.setText(
                f"Model cache: {format_bytes(state.current_cache_bytes)} used."
            )
        else:
            self.local_resource_label.setText(
                f"Download size: {format_bytes(state.estimated_download_bytes)}; "
                f"current model cache: {format_bytes(state.current_cache_bytes)}; "
                f"after install: {format_bytes(state.projected_cache_bytes)}."
            )

        if state.runtime_ready:
            detail = state.runtime_message.removeprefix("Local runtime ready.").strip()
            if not detail:
                self.local_runtime_label.setText("Runtime: Available")
                self.local_runtime_label.setStyleSheet("color: #4caf50;")
            else:
                self.local_runtime_label.setText(f"Runtime available: {detail}")
                self.local_runtime_label.setStyleSheet("color: #ff9800;")
            return

        detail = state.runtime_message.removeprefix("Local runtime unavailable. ")
        self.local_runtime_label.setText(f"Runtime unavailable: {detail}")
        if "Missing optional packages" in state.runtime_message:
            self.local_runtime_label.setStyleSheet("color: #f44336;")
        else:
            self.local_runtime_label.setStyleSheet("color: #ff9800;")

    def check_local_model_status(self, *_args):
        """Request one coherent status snapshot without blocking the GUI."""
        if not self._download_observers_attached:
            return
        self._inspection_request_id += 1
        request = ModelStatusInspectionRequest(
            request_id=self._inspection_request_id,
            model_name=self.local_model_combo.currentText(),
            cache_dir=self.config.cache_dir,
            device=str(self.config.device),
            load_in_4bit=bool(self.config.load_in_4bit),
            load_persisted_config=self._persisted_config_pending,
        )
        self._pending_inspection_request_id = request.request_id
        self._show_model_status_checking()
        self.update_validation_state()
        if self.download_lifecycle.request_model_inspection(request):
            return
        if self._pending_inspection_request_id != request.request_id:
            return
        self._on_model_inspection_finished(
            ModelStatusInspectionResult.unavailable(
                request,
                "Model status could not be checked. Try again.",
            )
        )

    def _on_model_inspection_finished(self, result: object) -> None:
        """Render only the latest selected-model inspection result."""
        if not self._download_observers_attached:
            return
        if not isinstance(result, ModelStatusInspectionResult):
            return
        if result.request.request_id != self._pending_inspection_request_id:
            return
        if self._persisted_config_pending:
            if result.resolved_config is not None:
                self.config = result.resolved_config
                self.config._force_local_runtime_selection()
                self._apply_config_to_controls()
            self._persisted_config_pending = False
        if result.request.model_name != self.local_model_combo.currentText():
            return
        self._pending_inspection_request_id = None
        self.is_downloading = self.download_lifecycle.active_target is not None
        self._render_local_model_state(result)
        self.update_validation_state()

    def _apply_config_to_controls(self) -> None:
        """Render a background-loaded config without emitting new inspections."""
        with QSignalBlocker(self.local_model_combo):
            index = self.local_model_combo.findText(self.config.model_name)
            if index >= 0:
                self.local_model_combo.setCurrentIndex(index)
        with QSignalBlocker(self.local_enable_chk):
            self.local_enable_chk.setChecked(self.config.local_model_enabled)
        self.temperature_spin.setValue(self.config.temperature)
        self.top_p_spin.setValue(self.config.top_p)
        self.max_tokens_spin.setValue(self.config.max_new_tokens)

    def on_local_action_clicked(self):
        """Handle local model install/delete/cancel button click."""
        if self.is_downloading:
            self.download_lifecycle.request_cancel()
            self.local_action_btn.setText("Cancelling...")
            self.local_action_btn.setEnabled(False)
            self.update_validation_state()
            return

        if self.local_downloaded:
            self._delete_model()
        else:
            self._start_download()

    def _on_local_enable_toggled(self, checked):
        """Update whether the current assistant preference can be saved."""
        del checked
        self.update_validation_state()

    def _start_download(self):
        """Begin downloading the selected local model."""
        model_name = self.local_model_combo.currentText()
        state = self._current_local_model_state
        if state is None or state.request.model_name != model_name:
            self.check_local_model_status()
            return
        if not state.preflight_ok:
            logger.warning(
                "Model download preflight blocked model=%s cache=%s reason=%s "
                "cleanup_candidates=%s",
                model_name,
                self.config.cache_dir,
                state.preflight_message,
                state.cleanup_candidates,
            )
            cleanup_hint = (
                "\n\nUnused or unsupported model files may need removal."
                if state.cleanup_candidates
                else ""
            )
            QMessageBox.warning(
                self,
                "Model Download Blocked",
                (
                    "The model download cannot start because the storage or "
                    "model policy check did not pass.\n\n"
                    f"Current cache: {format_bytes(state.current_cache_bytes)}\n"
                    f"Estimated download: "
                    f"{format_bytes(state.estimated_download_bytes)}\n"
                    f"Available disk: "
                    f"{format_bytes(state.available_disk_bytes)}\n"
                    f"Projected cache: "
                    f"{format_bytes(state.projected_cache_bytes)}"
                    f"{cleanup_hint}"
                ),
            )
            self.check_local_model_status()
            return

        started = self.download_lifecycle.start_download(
            model_name,
            self.config.cache_dir,
        )
        if not started:
            self.is_downloading = not self.download_lifecycle.is_idle()
            self.local_status_label.setText(
                "Another model download is still active."
                if self.is_downloading
                else "Download could not start."
            )
            self.update_validation_state()
            return
        self.is_downloading = True
        self.local_action_btn.setText("Cancel")
        self.local_status_label.setText("Downloading...")
        self.update_validation_state()

    def _delete_model(self):
        """Delete the selected local model from cache after confirmation."""
        repo_id = self.local_model_combo.currentText()
        reply = QMessageBox.warning(
            self,
            "Delete Model",
            f"Are you sure you want to delete {repo_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            # SAFETY: Switch backend if this model is active
            if self.agent_manager and not self.agent_manager.prepare_model_deletion(
                repo_id
            ):
                return

            started = self.download_lifecycle.request_cache_removal(
                repo_id,
                self.config.cache_dir,
                reason=ModelCacheCleanupReason.USER_DELETE,
            )
            if not started:
                QMessageBox.warning(
                    self,
                    "Model Cleanup Busy",
                    "Another model download or cleanup is still active.",
                )
                return
            self.is_downloading = True
            self.local_status_label.setText("Deleting model...")
            self.local_action_btn.setEnabled(False)
            self.update_validation_state()

    def on_download_progress(self, percent, msg):
        """Handle download progress updates.

        Args:
            percent: Download completion percentage.
            msg: Progress message to display.

        """
        del percent
        target = self.download_lifecycle.active_target
        if target is None or target.repo_id == self.local_model_combo.currentText():
            self.local_status_label.setText(msg)

    def on_download_finished(self, outcome: object):
        """Handle successful download completion.

        Args:
            outcome: Immutable target-aware download outcome.

        """
        if not isinstance(outcome, ModelDownloadOutcome):
            return
        self.is_downloading = not self.download_lifecycle.is_idle()
        self.check_local_model_status()
        QMessageBox.information(self, "Success", "Model downloaded successfully!")

    def on_download_failed(self, outcome: object):
        """Handle download failure.

        Args:
            outcome: Immutable target-aware download outcome.

        """
        if not isinstance(outcome, ModelDownloadOutcome):
            return
        self.is_downloading = not self.download_lifecycle.is_idle()
        selected_target = outcome.target.repo_id == self.local_model_combo.currentText()
        self.check_local_model_status()
        if outcome.cancelled:
            return
        logger.error(
            "Model download failed model=%s diagnostic=%s",
            outcome.target.repo_id,
            outcome.diagnostic_message or outcome.message,
        )
        if selected_target:
            self.local_status_label.setText("Download failed")
            self.local_status_label.setStyleSheet("color: #f44336;")
            self.local_action_btn.setText("Retry")
        QMessageBox.critical(
            self,
            "Download Failed",
            "Model download failed. Check the application log and try again.",
        )

    def on_cache_cleanup_finished(self, result: object) -> None:
        """Render explicit deletion after app-owned recursive cleanup terminal."""
        if not isinstance(result, ModelCacheCleanupResult):
            return
        if result.reason is not ModelCacheCleanupReason.USER_DELETE:
            return
        self.is_downloading = not self.download_lifecycle.is_idle()
        self.check_local_model_status()
        if result.ok:
            QMessageBox.information(
                self,
                "Model Deleted",
                result.public_message,
            )
        else:
            logger.error(
                "Model cleanup failed model=%s diagnostics=%s",
                result.target.repo_id,
                result.diagnostic_errors,
            )
            QMessageBox.warning(
                self,
                "Model Cleanup Failed",
                result.public_message,
            )

    def update_validation_state(self):
        """Allow Save when disabled, or when the enabled runtime is available."""
        model_name = self.local_model_combo.currentText()
        state = self._current_local_model_state
        enabled_runtime_ready = (
            state is not None
            and state.request.model_name == model_name
            and state.installed
            and state.runtime_ready
        )
        is_ready = not self.is_downloading and (
            not self.local_enable_chk.isChecked() or enabled_runtime_ready
        )

        self.btn_activate.setEnabled(is_ready)

    def on_activate_clicked(self):
        """Save settings, persist configuration, and accept the dialog."""
        # Save to config object
        self.config.local_model_enabled = self.local_enable_chk.isChecked()
        if self.config.local_model_enabled:
            self.config.local_runtime_notice_acknowledged = True
        self.config.model_name = self.local_model_combo.currentText()
        # Generation parameters
        self.config.temperature = self.temperature_spin.value()
        self.config.top_p = self.top_p_spin.value()
        self.config.max_new_tokens = self.max_tokens_spin.value()

        state = self._current_local_model_state
        if self.config.local_model_enabled and (
            state is None or state.request.model_name != self.config.model_name
        ):
            QMessageBox.warning(
                self,
                "Model Status Pending",
                "Wait for the selected model status check to finish, then try again.",
            )
            self.check_local_model_status()
            return

        local_ready = bool(
            self.config.local_model_enabled
            and state is not None
            and state.installed
            and state.runtime_ready
        )

        if self.config.local_model_enabled and not local_ready:
            QMessageBox.critical(
                self,
                "Local Runtime Unavailable",
                (
                    state.runtime_message
                    if state is not None
                    else "Local runtime status is unavailable. Try again."
                ),
            )
            return

        self.config.apply_runtime_selection(
            "local",
            model_id=self.config.model_name if local_ready else None,
            ui_active_mode="local",
        )

        # Persist to JSON
        self.config.save_to_file()

        self.accept()

    def accept(self) -> None:
        """Accept without retaining this dialog through lifecycle signals."""
        self._shutdown_active_download()
        self._detach_download_observers()
        super().accept()

    def reject(self):
        """Cancel any active download and reject the dialog."""
        self._shutdown_active_download()
        self._detach_download_observers()
        super().reject()

    def closeEvent(self, event):  # noqa: N802
        """Ensure threads stop on close."""
        self._shutdown_active_download()
        self._detach_download_observers()
        super().closeEvent(event)

    def _shutdown_active_download(self):
        """Request cancellation without releasing application ownership."""
        if self.is_downloading:
            return self.download_lifecycle.request_cancel()
        return True

    def _detach_download_observers(self) -> None:
        """Stop hidden-dialog callbacks without affecting app ownership."""
        connections = (
            (self.download_lifecycle.progress, self.on_download_progress),
            (self.download_lifecycle.finished, self.on_download_finished),
            (self.download_lifecycle.failed, self.on_download_failed),
            (
                self.download_lifecycle.cache_cleanup_finished,
                self.on_cache_cleanup_finished,
            ),
            (
                self.download_lifecycle.inspection_finished,
                self._on_model_inspection_finished,
            ),
        )
        for signal, slot in connections:
            with contextlib.suppress(RuntimeError, TypeError):
                signal.disconnect(slot)
        self._download_observers_attached = False
        self._pending_inspection_request_id = None

    def get_config(self):
        """Return the current LLM configuration.

        Returns:
            The LLMConfig instance with the current settings.

        """
        return self.config
