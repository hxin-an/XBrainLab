"""First-run consent dialog for the local assistant runtime."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import (
    format_bytes,
    local_model_spec,
    plan_model_download,
)


class LocalRuntimeFirstRunDialog(QDialog):
    """Explain local runtime cost before loading or downloading a model."""

    ENABLE = "enable"
    DOWNLOAD = "download"
    USE_CACHE = "use_existing_cache"
    LATER = "later"
    DISABLE = "disable"

    def __init__(self, parent=None, config: LLMConfig | None = None):
        super().__init__(parent)
        self.config = config or LLMConfig()
        self.choice = self.LATER
        self.setWindowTitle("Local Assistant Runtime")
        self.setMinimumWidth(520)
        self._init_ui()

    def _init_ui(self) -> None:
        model_id = self.config.model_name
        spec = local_model_spec(model_id)
        preflight = plan_model_download(model_id, self.config.cache_dir)
        has_cache = self.config.has_local_model_cache(model_id)
        ready = self.config.local_backend_ready(model_id)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Start the local assistant?")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        intro = QLabel(
            "The assistant can run on this computer, but local models use GPU "
            "or CPU memory. XBrainLab will not load a model until you choose to "
            "enable it."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        details_group = QGroupBox("Runtime preflight")
        details = QVBoxLayout(details_group)
        detail_lines = [
            f"Model: {model_id}",
            f"Cache directory: {preflight.cache_dir}",
            f"Current cache: {format_bytes(preflight.current_cache_bytes)}",
            f"Estimated download: {format_bytes(preflight.estimated_download_bytes)}",
            f"Projected cache: {format_bytes(preflight.projected_cache_bytes)}",
        ]
        if spec is not None:
            detail_lines.extend(
                [
                    f"Provider: {spec.provider}",
                    f"License: {spec.license}",
                    f"Estimated VRAM: {spec.estimated_vram_gb:.1f} GB",
                ]
            )
        detail_lines.append(f"Cache status: {'available' if has_cache else 'missing'}")
        detail_lines.append(self.config.local_backend_status_message(model_id))
        if not preflight.ok:
            detail_lines.append(preflight.message)

        for line in detail_lines:
            label = QLabel(line)
            label.setWordWrap(True)
            details.addWidget(label)
        layout.addWidget(details_group)

        button_row = QHBoxLayout()
        self.enable_btn = QPushButton("Enable")
        self.enable_btn.setEnabled(ready)
        self.enable_btn.clicked.connect(lambda: self._choose(self.ENABLE))
        button_row.addWidget(self.enable_btn)

        self.download_btn = QPushButton("Download")
        self.download_btn.setEnabled(not has_cache and preflight.ok)
        self.download_btn.clicked.connect(lambda: self._choose(self.DOWNLOAD))
        button_row.addWidget(self.download_btn)

        self.use_cache_btn = QPushButton("Use existing cache")
        self.use_cache_btn.setEnabled(has_cache and ready)
        self.use_cache_btn.clicked.connect(lambda: self._choose(self.USE_CACHE))
        button_row.addWidget(self.use_cache_btn)

        self.later_btn = QPushButton("Later")
        self.later_btn.clicked.connect(lambda: self._choose(self.LATER))
        button_row.addWidget(self.later_btn)

        self.disable_btn = QPushButton("Disable")
        self.disable_btn.clicked.connect(lambda: self._choose(self.DISABLE))
        button_row.addWidget(self.disable_btn)

        layout.addLayout(button_row)

    def _choose(self, choice: str) -> None:
        self.choice = choice
        self.accept()
