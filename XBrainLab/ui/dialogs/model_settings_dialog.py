"""AI model settings dialog for configuring local and Gemini API backends.

Provides a unified dialog for managing local model downloads and Gemini API
key verification, allowing users to switch between inference backends.
"""

import os

try:
    from google import genai
except ImportError:
    genai = None  # type: ignore[assignment]
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.downloader import ModelDownloader


class ModelSettingsDialog(QDialog):
    """Dialog for configuring AI model settings (Local vs Gemini).

    Provides UI for selecting and downloading local models, entering and
    verifying Gemini API keys, and activating the chosen backend.

    Attributes:
        agent_manager: Reference to AgentManager for safe backend switching.
        config: The current LLM configuration.
        gemini_enabled: Whether the Gemini backend is enabled and verified.
        local_downloaded: Whether the selected local model is downloaded.
        downloader: ModelDownloader instance for managing model downloads.
        is_downloading: Whether a download is currently in progress.
    """

    def __init__(
        self, parent=None, config: LLMConfig | None = None, agent_manager=None
    ):
        super().__init__(parent)
        self.setWindowTitle("AI Assistant Settings")
        self.setFixedSize(500, 500)

        # Reference to AgentManager for safe deletion (switching backend)
        self.agent_manager = agent_manager

        # Load config or create default
        saved_config = LLMConfig.load_from_file()
        self.config = saved_config if saved_config else (config or LLMConfig())

        self.gemini_enabled = self.config.gemini_enabled
        self.local_downloaded = False

        # Downloader
        self.downloader = ModelDownloader()
        self.downloader.progress.connect(self.on_download_progress)
        self.downloader.finished.connect(self.on_download_finished)
        self.downloader.failed.connect(self.on_download_failed)
        self.is_downloading = False

        self.init_ui()
        self.load_state()

    def init_ui(self):
        """Initialize the dialog UI with local model and Gemini API sections."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # --- Local Model Section ---
        local_group = QGroupBox("Local Model")
        local_layout = QVBoxLayout()

        # Model Dropdown
        self.local_model_combo = QComboBox()
        self.local_model_combo.addItems(
            [
                "Qwen/Qwen2.5-7B-Instruct",
                "google/gemma-2b-it",
                "microsoft/Phi-3.5-mini-instruct",
                "meta-llama/Llama-3.1-8B-Instruct",
            ]
        )
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

        # Enable Checkbox (Moved to bottom)
        self.local_enable_chk = QCheckBox("ACTIVATE LOCAL MODEL")
        self.local_enable_chk.toggled.connect(self._on_local_enable_toggled)
        local_layout.addWidget(self.local_enable_chk)

        local_group.setLayout(local_layout)
        layout.addWidget(local_group)

        # --- Gemini API Section ---
        gemini_group = QGroupBox("Gemini API")
        gemini_layout = QVBoxLayout()

        # API Key Input
        key_layout = QHBoxLayout()
        key_layout.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter Gemini API Key (AIza...)")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        key_layout.addWidget(self.api_key_input)
        gemini_layout.addLayout(key_layout)

        # Status & Test Button (Mirrors Local Model layout)
        status_layout = QHBoxLayout()
        self.gemini_status_label = QLabel("Status: Not Verified")
        status_layout.addWidget(self.gemini_status_label)
        status_layout.addStretch()

        self.test_conn_btn = QPushButton("Test Key")
        self.test_conn_btn.setFixedWidth(80)
        self.test_conn_btn.clicked.connect(self.on_test_connection_clicked)
        status_layout.addWidget(self.test_conn_btn)
        gemini_layout.addLayout(status_layout)

        gemini_group.setLayout(gemini_layout)
        layout.addWidget(gemini_group)

        # Gemini Model Dropdown (Restored)
        gemini_layout.addWidget(QLabel("Model:"))
        self.gemini_model_combo = QComboBox()
        self.gemini_model_combo.addItems(
            [
                "gemini-3.0-pro",
                "gemini-3.0-flash",
                "gemini-2.0-flash",
                "gemini-2.0-flash-thinking-exp",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
                "gemini-1.5-flash-8b",
            ]
        )
        gemini_layout.addWidget(self.gemini_model_combo)

        layout.addStretch()

        # --- Footer ---
        footer_layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_activate = QPushButton("Activate")
        self.btn_activate.setEnabled(False)
        self.btn_activate.clicked.connect(self.on_activate_clicked)
        # Style Activate button
        self.btn_activate.setStyleSheet(
            """
            QPushButton {
                background-color: #007bff; color: white; border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:disabled { background-color: #555; color: #aaa; }
        """
        )

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_activate)

        footer_layout.addLayout(btn_layout)
        layout.addLayout(footer_layout)

    def load_state(self):
        """Load UI state from config."""
        # Local
        index = self.local_model_combo.findText(self.config.model_name)
        if index >= 0:
            self.local_model_combo.setCurrentIndex(index)

        # Gemini
        if self.config.gemini_api_key:
            self.api_key_input.setText(self.config.gemini_api_key)

        if self.config.gemini_enabled:
            self.gemini_status_label.setText("Verified")
            self.gemini_status_label.setStyleSheet("color: #4caf50;")

        index = self.gemini_model_combo.findText(self.config.gemini_model_name)
        if index >= 0:
            self.gemini_model_combo.setCurrentIndex(index)

        # Set Enable Checkbox state and trigger update
        self.local_enable_chk.setChecked(self.config.local_model_enabled)
        self._on_local_enable_toggled(self.config.local_model_enabled)

        self.check_local_model_status()
        self.update_validation_state()

    def check_local_model_status(self):
        """Check if selected model exists in cache."""
        model_name = self.local_model_combo.currentText()
        repo_id = model_name  # In our list, text is repo_id

        # Expected path (simplified logic matching downloader)
        safe_name = repo_id.replace("/", "_")
        cache_dir = self.config.cache_dir
        model_path = os.path.join(cache_dir, safe_name)

        if os.path.exists(model_path) and os.listdir(model_path):
            self.local_downloaded = True
            self.local_status_label.setText("[+] Downloaded")
            self.local_status_label.setStyleSheet("color: #4caf50;")
            self.local_action_btn.setText("Delete")
            self.local_action_btn.setEnabled(True)
        else:
            self.local_downloaded = False
            self.local_status_label.setText("Status: Not downloaded")
            self.local_status_label.setStyleSheet("color: #888888;")
            self.local_action_btn.setText("Install Model")
            self.local_action_btn.setEnabled(True)

        self.update_validation_state()

    def on_local_action_clicked(self):
        """Handle local model install/delete/cancel button click."""
        if self.is_downloading:
            # Action is Cancel
            self.downloader.cancel_download()
            self.is_downloading = False
            self.check_local_model_status()
            return

        if self.local_downloaded:
            self._delete_model()
        else:
            self._start_download()

    def _on_local_enable_toggled(self, checked):
        """Enable/Disable local model controls."""
        self.local_model_combo.setEnabled(checked)
        self.local_action_btn.setEnabled(checked)
        self.check_local_model_status()

    def _start_download(self):
        """Begin downloading the selected local model."""
        model_name = self.local_model_combo.currentText()

        self.is_downloading = True
        self.local_action_btn.setText("Cancel")
        self.local_status_label.setText("Downloading...")

        self.downloader.start_download(model_name, self.config.cache_dir)
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
            if self.agent_manager:
                self.agent_manager.prepare_model_deletion(repo_id)

            import shutil

            safe_name = repo_id.replace("/", "_")
            path = os.path.join(self.config.cache_dir, safe_name)
            try:
                shutil.rmtree(path)
                self.check_local_model_status()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {e}")

    def on_download_progress(self, percent, msg):
        """Handle download progress updates.

        Args:
            percent: Download completion percentage.
            msg: Progress message to display.
        """
        self.local_status_label.setText(msg)

    def on_download_finished(self, path):
        """Handle successful download completion.

        Args:
            path: Path where the model was downloaded.
        """
        self.is_downloading = False
        self.check_local_model_status()
        QMessageBox.information(self, "Success", "Model downloaded successfully!")

    def on_download_failed(self, error):
        """Handle download failure.

        Args:
            error: Error message describing the failure.
        """
        self.is_downloading = False
        self.local_status_label.setText("[x] Failed")
        self.local_status_label.setStyleSheet("color: #f44336;")
        self.local_action_btn.setText("Retry")

        # Special handling for Cancellation Cleanup (User Request)
        if "Cancelled by user" in error:
            # User requested auto-cleanup without asking
            self._cleanup_partial_files()
            return

        QMessageBox.critical(self, "Download Failed", error)

    def _cleanup_partial_files(self):
        """Best-effort cleanup of partial download files."""
        try:
            import shutil

            repo_id = self.local_model_combo.currentText()
            safe_name = repo_id.replace("/", "_")
            path = os.path.join(self.config.cache_dir, safe_name)

            if os.path.exists(path):
                shutil.rmtree(path)
                self.check_local_model_status()  # Update UI state
                QMessageBox.information(self, "Cleanup", "Partial files removed.")
        except Exception as e:
            QMessageBox.warning(
                self, "Cleanup Error", f"Failed to cleanup partials directly: {e}"
            )

    def on_test_connection_clicked(self):
        """Validate and test the entered Gemini API key."""
        api_key = self.api_key_input.text().strip()

        # 1. Format Validation
        if not api_key.startswith("AIza"):
            QMessageBox.warning(self, "Invalid Key", "API Key must start with 'AIza'")
            return

        if genai is None:
            self.gemini_enabled = False
            self.gemini_status_label.setText("[x] Missing Lib")
            self.gemini_status_label.setStyleSheet("color: #f44336;")
            QMessageBox.critical(
                self,
                "Dependency Error",
                "Please install google-genai library:\npoetry add google-genai",
            )
            return

        # 2. Connection Test (Threaded)
        self.test_conn_btn.setEnabled(False)
        self.gemini_status_label.setText("Status: Testing...")

        self.conn_thread = QThread()
        self.conn_worker = ConnectionTestWorker(api_key)
        self.conn_worker.moveToThread(self.conn_thread)

        self.conn_thread.started.connect(self.conn_worker.run)
        self.conn_worker.finished.connect(self._on_conn_test_success)
        self.conn_worker.error.connect(self._on_conn_test_error)

        # Cleanup
        self.conn_worker.finished.connect(self.conn_thread.quit)
        self.conn_worker.error.connect(self.conn_thread.quit)
        self.conn_worker.finished.connect(self.conn_worker.deleteLater)
        self.conn_worker.error.connect(self.conn_worker.deleteLater)
        self.conn_thread.finished.connect(self.conn_thread.deleteLater)

        self.conn_thread.start()

    def _on_conn_test_success(self, api_key):
        """Handle successful Gemini API connection test.

        Args:
            api_key: The verified API key.
        """
        self.gemini_enabled = True
        self.gemini_status_label.setText("Status: Verified")
        self.gemini_status_label.setStyleSheet("color: #4caf50;")

        # Update config
        os.environ["GEMINI_API_KEY"] = api_key
        self.config.gemini_api_key = api_key

        self.test_conn_btn.setEnabled(True)
        self.update_validation_state()

    def _on_conn_test_error(self, error_msg):
        """Handle failed Gemini API connection test.

        Args:
            error_msg: Error message from the connection attempt.
        """
        self.gemini_enabled = False
        self.gemini_status_label.setText("Status: Failed")
        self.gemini_status_label.setStyleSheet("color: #f44336;")

        QMessageBox.critical(self, "Connection Failed", error_msg)
        self.test_conn_btn.setEnabled(True)
        self.update_validation_state()

    def update_validation_state(self):
        """Enable Activate button if conditions met."""
        # Core Condition: Local Downloaded OR Gemini Verified
        # Also disable if currently downloading
        is_ready = (
            self.local_downloaded or self.gemini_enabled
        ) and not self.is_downloading

        self.btn_activate.setEnabled(is_ready)

        if is_ready:
            pass
        else:
            pass

    def on_activate_clicked(self):
        """Save settings, persist configuration, and accept the dialog."""
        # Save to config object
        self.config.local_model_enabled = self.local_enable_chk.isChecked()
        self.config.model_name = self.local_model_combo.currentText()
        self.config.gemini_model_name = self.gemini_model_combo.currentText()
        self.config.gemini_enabled = self.gemini_enabled

        # Determine active mode
        if self.gemini_enabled and not self.local_downloaded:
            self.config.active_mode = "gemini"
        elif self.local_downloaded and not self.gemini_enabled:
            self.config.active_mode = "local"
        else:
            # Both available, default to what was last active or gemini preference?
            # Let's keep logic simple: gemini if user just verified it?
            # Or respect previous config.
            # Plan says: "If both, default to Local?" Let user choose via mode.
            # Here we just save what is available.
            pass

        # Persist to JSON
        self.config.save_to_file()

        # Persist API Key to .env (Mock for now, print to console or create .env file)
        self._save_api_key_to_env()

        self.accept()

    def _save_api_key_to_env(self):
        """Write API Key to .env file preserving other content."""
        key = self.api_key_input.text().strip()
        if not key or not key.startswith("AIza"):
            return

        # Resolve to project root (4 levels up from ui/dialogs/)
        package_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        env_path = os.path.join(os.path.dirname(package_root), ".env")
        try:
            # Read existing
            lines = []
            if os.path.exists(env_path):
                with open(env_path, encoding="utf-8") as f:
                    lines = f.readlines()

            # Update or Append
            new_lines = []
            found = False
            for line in lines:
                if line.strip().startswith("GEMINI_API_KEY="):
                    new_lines.append(f"GEMINI_API_KEY={key}\n")
                    found = True
                else:
                    new_lines.append(line)

            if not found:
                if new_lines and not new_lines[-1].endswith("\n"):
                    new_lines[-1] += "\n"
                new_lines.append("GEMINI_API_KEY=" + key + "\n")

            # Write back
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

        except Exception as e:
            QMessageBox.warning(self, "Config Error", f"Failed to save .env: {e}")

    def reject(self):
        """Cancel any active download and reject the dialog."""
        if self.is_downloading:
            self.downloader.cancel_download()
        super().reject()

    def closeEvent(self, event):  # noqa: N802
        """Ensure threads stop on close."""
        if self.is_downloading:
            self.downloader.cancel_download()
        super().closeEvent(event)

    def get_config(self):
        """Return the current LLM configuration.

        Returns:
            The LLMConfig instance with the current settings.
        """
        return self.config


class ConnectionTestWorker(QObject):
    """Background worker for testing Gemini API connectivity.

    Attributes:
        finished: Signal emitted with the API key on successful connection.
        error: Signal emitted with an error message on failure.
    """

    finished = pyqtSignal(str)  # api_key
    error = pyqtSignal(str)

    def __init__(self, api_key):
        """Initialize the connection test worker.

        Args:
            api_key: Gemini API key to test.
        """
        super().__init__()
        self.api_key = api_key

    def run(self):
        """Execute the API connection test.

        Emits ``finished`` with the API key on success, or ``error``
        with an error message on failure.
        """
        try:
            client = genai.Client(api_key=self.api_key)
            models = client.models.list()
            _ = next(iter(models))
            self.finished.emit(self.api_key)
        except Exception as e:
            self.error.emit(str(e))
