"""AI assistant settings dialog for the local-only runtime.

Provides UI for managing approved local model downloads and generation
parameters. Remote assistant runtimes are not part of the product path.
"""

import contextlib
import math
import weakref

from PyQt6.QtCore import (
    QCoreApplication,
    QObject,
    QSignalBlocker,
    QSize,
    Qt,
    QTimer,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.downloader import (
    ModelDownloadFailureCode,
    ModelDownloadOutcome,
    model_download_public_failure_message,
)
from XBrainLab.llm.core.model_catalog import (
    format_bytes,
    local_model_spec,
)
from XBrainLab.llm.core.model_download_lifecycle import (
    ModelCacheCleanupReason,
    ModelCacheCleanupResult,
    ModelDownloadLifecycle,
    ModelDownloadLifecycleContract,
    ModelStatusInspectionRequest,
    ModelStatusInspectionResult,
)
from XBrainLab.ui.chat.segmented_control import AssistantSegmentedControl
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.styles.theme import Theme

_RESPONSE_STYLE_PRESETS: dict[str, tuple[float, float]] = {
    "precise": (0.2, 0.8),
    "balanced": (0.7, 0.9),
    "exploratory": (1.0, 0.95),
}
_RESPONSE_LENGTH_PRESETS: dict[str, int] = {
    "short": 256,
    "standard": 512,
    "detailed": 1024,
}

_ASSISTANT_SETTINGS_STYLE = f"""
    QDialog#AssistantSettingsDialog {{
        background-color: {Theme.BACKGROUND_DARK};
        color: {Theme.TEXT_PRIMARY};
    }}
    QLabel#AssistantSettingsHeading {{
        color: {Theme.TEXT_PRIMARY};
        background: transparent;
        border: none;
        font-size: 20px;
        font-weight: 700;
    }}
    QLabel#AssistantSettingsSection {{
        color: {Theme.TEXT_PRIMARY};
        background: transparent;
        border: none;
        font-size: 14px;
        font-weight: 700;
    }}
    QLabel#AssistantSettingsMuted {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
        border: none;
        font-size: 12px;
    }}
    QLabel#AssistantSettingsSaveError {{
        color: {Theme.LOG_ERROR};
        background: transparent;
        border: none;
        font-size: 12px;
    }}
    QComboBox#AssistantModelCombo {{
        min-height: 34px;
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.BACKGROUND_MID};
        border: 1px solid {Theme.BORDER};
        border-radius: 5px;
        padding: 2px 9px;
    }}
    QDoubleSpinBox#AssistantExactValue,
    QSpinBox#AssistantExactValue {{
        min-height: 30px;
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.BACKGROUND_MID};
        border: 1px solid {Theme.BORDER};
        border-radius: 5px;
        padding: 1px 9px;
    }}
    QDoubleSpinBox#AssistantExactValue::up-button,
    QDoubleSpinBox#AssistantExactValue::down-button,
    QSpinBox#AssistantExactValue::up-button,
    QSpinBox#AssistantExactValue::down-button {{
        width: 0px;
        border: none;
        background: transparent;
    }}
    QComboBox#AssistantModelCombo:focus,
    QDoubleSpinBox#AssistantExactValue:focus,
    QSpinBox#AssistantExactValue:focus {{
        border-color: {Theme.BLUE_FOCUS_BORDER};
    }}
    QFrame#AssistantModelStatusDot {{
        min-width: 9px;
        max-width: 9px;
        min-height: 9px;
        max-height: 9px;
        border: none;
        border-radius: 4px;
        background-color: {Theme.GRAY_MUTED};
    }}
    QFrame#AssistantModelStatusDot[statusTone="ready"] {{
        background-color: {Theme.LOG_INFO};
    }}
    QFrame#AssistantModelStatusDot[statusTone="warning"] {{
        background-color: {Theme.LOG_WARNING};
    }}
    QFrame#AssistantModelStatusDot[statusTone="error"] {{
        background-color: {Theme.LOG_ERROR};
    }}
    QCheckBox#AssistantLocalEnabled {{
        color: {Theme.TEXT_MUTED};
        spacing: 8px;
    }}
    QToolButton#AssistantAdvancedToggle {{
        min-height: 38px;
        color: {Theme.TEXT_MUTED};
        background-color: {Theme.METRICS_TABLE_BG};
        border: 1px solid {Theme.METRICS_TABLE_GRID};
        border-radius: 5px;
        padding: 4px 11px;
        text-align: left;
        font-size: 13px;
        font-weight: 600;
    }}
    QToolButton#AssistantAdvancedToggle:hover {{
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.METRICS_TABLE_ALT_BG};
        border-color: {Theme.BORDER};
    }}
    QWidget#AssistantAdvancedContent {{
        background: transparent;
        border: 1px solid {Theme.METRICS_TABLE_GRID};
        border-radius: 5px;
    }}
    QPushButton#AssistantModelAction,
    QPushButton#AssistantSecondaryButton {{
        min-height: 34px;
        color: {Theme.TEXT_MUTED};
        background-color: {Theme.BACKGROUND_MID};
        border: 1px solid {Theme.BORDER};
        border-radius: 5px;
        padding: 3px 12px;
    }}
    QPushButton#AssistantModelAction:hover,
    QPushButton#AssistantSecondaryButton:hover {{
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.BACKGROUND_LIGHT};
        border-color: {Theme.GRAY_LIGHT};
    }}
    QPushButton#AssistantModelAction[destructive="true"] {{
        color: {Theme.LOG_ERROR};
        background-color: {Theme.BTN_DANGER_BG};
        border-color: {Theme.BTN_DANGER_BORDER};
    }}
    QPushButton#AssistantModelAction[destructive="true"]:hover {{
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.BTN_DANGER_HOVER};
        border-color: {Theme.ACCENT_ERROR};
    }}
    QPushButton#AssistantPrimaryButton {{
        min-height: 34px;
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.BLUE_PRIMARY};
        border: 1px solid transparent;
        border-radius: 5px;
        padding: 3px 18px;
        font-weight: 700;
    }}
    QPushButton#AssistantPrimaryButton:hover {{
        background-color: {Theme.BLUE_HOVER};
    }}
    QPushButton#AssistantPrimaryButton:pressed {{
        background-color: {Theme.BLUE_PRESSED};
    }}
    QPushButton#AssistantPrimaryButton:focus {{
        border-color: {Theme.BLUE_FOCUS_BORDER};
    }}
    QPushButton#AssistantPrimaryButton:disabled {{
        color: {Theme.BTN_DISABLED_TEXT};
        background-color: {Theme.BTN_DISABLED_BG};
        border-color: {Theme.BTN_DISABLED_BORDER};
    }}
    QFrame#AssistantSettingsDivider {{
        color: {Theme.METRICS_TABLE_GRID};
        background-color: {Theme.METRICS_TABLE_GRID};
        border: none;
        max-height: 1px;
    }}
    QProgressBar#AssistantDownloadProgress {{
        min-height: 5px;
        max-height: 5px;
        background-color: {Theme.METRICS_TABLE_BG};
        border: none;
        border-radius: 2px;
        text-align: center;
    }}
    QProgressBar#AssistantDownloadProgress::chunk {{
        background-color: {Theme.BLUE_PRIMARY};
        border-radius: 2px;
    }}
    QScrollArea#AssistantSettingsBodyScroll {{
        background: transparent;
        border: none;
    }}
    QScrollArea#AssistantSettingsBodyScroll > QWidget > QWidget {{
        background: {Theme.BACKGROUND_DARK};
    }}
    QWidget#AssistantAdvancedContent {{
        background: transparent;
        border: none;
    }}
"""


class ModelSettingsDialog(BaseDialog):
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
        self.is_downloading = self.download_lifecycle.active_target is not None
        self._inspection_request_id = 0
        self._pending_inspection_request_id: int | None = None
        self._current_local_model_state: ModelStatusInspectionResult | None = None
        self._updating_response_presets = False
        self._download_observers_attached = False

        super().__init__(
            parent=parent,
            title="Assistant Settings",
            width=560,
            height=560,
        )
        self.setMinimumWidth(520)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self._fit_initial_content)

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
        self.load_state()
        self._schedule_fit()

    def init_ui(self):
        """Initialize the dialog UI with local model settings."""
        self.setObjectName("AssistantSettingsDialog")
        self.setStyleSheet(f"{self.styleSheet()}\n{_ASSISTANT_SETTINGS_STYLE}")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.settings_body_scroll = QScrollArea(self)
        self.settings_body_scroll.setObjectName("AssistantSettingsBodyScroll")
        self.settings_body_scroll.setWidgetResizable(True)
        self.settings_body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.settings_body_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.settings_body_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.settings_body_scroll.setMinimumHeight(280)
        self.settings_body_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.settings_body = QWidget(self.settings_body_scroll)
        self.settings_body.setObjectName("AssistantSettingsBody")
        layout = QVBoxLayout(self.settings_body)
        layout.setContentsMargins(24, 18, 24, 16)
        layout.setSpacing(12)

        self.heading_label = QLabel("Assistant Settings")
        self.heading_label.setObjectName("AssistantSettingsHeading")
        layout.addWidget(self.heading_label)

        self.model_section_label = self._section_label("Model")
        layout.addWidget(self.model_section_label)

        # Model Dropdown
        self.local_model_combo = QComboBox()
        self.local_model_combo.setObjectName("AssistantModelCombo")
        self.local_model_combo.setAccessibleName("Assistant model")
        self.local_model_combo.setAccessibleDescription(
            "Select the exact local model used by XBrainLab Assistant."
        )
        self.model_section_label.setBuddy(self.local_model_combo)
        for model_id in LLMConfig.allowed_local_model_ids():
            spec = local_model_spec(model_id)
            self.local_model_combo.addItem(
                spec.label if spec is not None else model_id,
                model_id,
            )
            index = self.local_model_combo.count() - 1
            if spec is not None:
                self.local_model_combo.setItemData(
                    index,
                    (
                        f"{spec.provider} · {spec.parameters} · {spec.license}\n"
                        f"{spec.repo_id}"
                    ),
                    Qt.ItemDataRole.ToolTipRole,
                )
        self.local_model_combo.currentIndexChanged.connect(
            self.check_local_model_status
        )
        self.local_model_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.local_model_combo)

        self.model_migration_label = QLabel("")
        self.model_migration_label.setObjectName("AssistantSettingsMuted")
        self.model_migration_label.setWordWrap(True)
        self.model_migration_label.setVisible(False)
        layout.addWidget(self.model_migration_label)

        # Status & Actions
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(2, 0, 0, 0)
        status_layout.setSpacing(8)
        self.model_status_dot = QFrame(self)
        self.model_status_dot.setObjectName("AssistantModelStatusDot")
        self.model_status_dot.setProperty("statusTone", "neutral")
        status_layout.addWidget(self.model_status_dot)
        self.local_status_label = QLabel("Status: Checking...")
        status_layout.addWidget(self.local_status_label)
        status_layout.addStretch()

        self.local_action_btn = QPushButton("Install Model")
        self.local_action_btn.setObjectName("AssistantModelAction")
        self.local_action_btn.setMinimumWidth(110)
        self.local_action_btn.clicked.connect(self.on_local_action_clicked)
        status_layout.addWidget(self.local_action_btn)
        layout.addLayout(status_layout)

        runtime_layout = QHBoxLayout()
        runtime_layout.setContentsMargins(2, 0, 0, 0)
        runtime_layout.setSpacing(8)
        self.local_runtime_label = QLabel(
            "Environment check: Checking...",
            self.settings_body,
        )
        self.local_runtime_label.setObjectName("AssistantSettingsMuted")
        self.local_runtime_label.setWordWrap(True)
        runtime_layout.addWidget(self.local_runtime_label, 1)
        self.check_runtime_btn = QPushButton("Check again", self.settings_body)
        self.check_runtime_btn.setObjectName("AssistantSecondaryButton")
        self.check_runtime_btn.clicked.connect(self.check_local_model_status)
        runtime_layout.addWidget(self.check_runtime_btn)
        layout.addLayout(runtime_layout)

        self.last_runtime_attempt_label = QLabel(self.settings_body)
        self.last_runtime_attempt_label.setObjectName("AssistantSettingsMuted")
        self.last_runtime_attempt_label.setWordWrap(True)
        self.last_runtime_attempt_label.setStyleSheet(
            f"color: {Theme.LOG_WARNING}; background: transparent; border: none;"
        )
        self.last_runtime_attempt_label.setVisible(False)
        layout.addWidget(self.last_runtime_attempt_label)

        self.download_progress = QProgressBar(self)
        self.download_progress.setObjectName("AssistantDownloadProgress")
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setTextVisible(False)
        self.download_progress.setVisible(False)
        layout.addWidget(self.download_progress)

        self.local_enable_chk = QCheckBox("Use local assistant")
        self.local_enable_chk.setObjectName("AssistantLocalEnabled")
        self.local_enable_chk.toggled.connect(self._on_local_enable_toggled)
        layout.addWidget(self.local_enable_chk)

        self.response_style_label = self._section_label("Response style")
        layout.addWidget(self.response_style_label)
        self.response_style_control = AssistantSegmentedControl(
            (
                ("precise", "Precise"),
                ("balanced", "Balanced"),
                ("exploratory", "Varied"),
            ),
            descriptions={
                "precise": "More consistent explanatory wording.",
                "balanced": "Balanced detail and variation.",
                "exploratory": "More varied explanatory wording.",
            },
            parent=self,
        )
        self.response_style_control.selection_changed.connect(
            self._apply_response_style_preset
        )
        layout.addWidget(self.response_style_control)

        self.response_length_label = self._section_label("Response length")
        layout.addWidget(self.response_length_label)
        self.response_length_control = AssistantSegmentedControl(
            (
                ("short", "Short"),
                ("standard", "Standard"),
                ("detailed", "Detailed"),
            ),
            descriptions={
                "short": "Prefer concise explanations.",
                "standard": "Use normal explanatory detail.",
                "detailed": "Allow longer explanations.",
            },
            parent=self,
        )
        self.response_length_control.selection_changed.connect(
            self._apply_response_length_preset
        )
        layout.addWidget(self.response_length_control)

        self.advanced_toggle = QToolButton(self)
        self.advanced_toggle.setObjectName("AssistantAdvancedToggle")
        self.advanced_toggle.setText("Advanced settings")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.advanced_toggle.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.advanced_toggle.toggled.connect(self._set_advanced_visible)
        layout.addWidget(self.advanced_toggle)

        self.advanced_content = QWidget(self.settings_body)
        self.advanced_content.setObjectName("AssistantAdvancedContent")
        advanced_layout = QVBoxLayout(self.advanced_content)
        advanced_layout.setContentsMargins(10, 8, 10, 8)
        advanced_layout.setSpacing(7)

        exact_form = QFormLayout()
        exact_form.setContentsMargins(0, 0, 0, 0)
        exact_form.setHorizontalSpacing(18)
        exact_form.setVerticalSpacing(6)
        exact_form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        exact_form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)

        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setObjectName("AssistantExactValue")
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setDecimals(2)
        self.temperature_spin.setValue(self.config.temperature)
        self.temperature_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.temperature_spin.setFixedWidth(160)
        self.temperature_spin.setToolTip(
            "Controls variety in explanatory answers. Workflow actions always "
            "use deterministic decoding."
        )
        exact_form.addRow("Temperature", self.temperature_spin)

        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setObjectName("AssistantExactValue")
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setDecimals(2)
        self.top_p_spin.setValue(self.config.top_p)
        self.top_p_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.top_p_spin.setFixedWidth(160)
        self.top_p_spin.setToolTip("Nucleus sampling cutoff for explanatory answers.")
        exact_form.addRow("Top-p", self.top_p_spin)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setObjectName("AssistantExactValue")
        self.max_tokens_spin.setRange(64, 8192)
        self.max_tokens_spin.setSingleStep(64)
        self.max_tokens_spin.setValue(self.config.max_new_tokens)
        self.max_tokens_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.max_tokens_spin.setFixedWidth(160)
        self.max_tokens_spin.setToolTip(
            "Maximum length of explanatory answers. Workflow actions use a "
            "separate safety limit."
        )
        exact_form.addRow("Maximum tokens", self.max_tokens_spin)
        advanced_layout.addLayout(exact_form)

        self.local_resource_label = QLabel("", self.advanced_content)
        self.local_resource_label.setObjectName("AssistantSettingsMuted")
        self.local_resource_label.setWordWrap(True)
        advanced_layout.addWidget(self.local_resource_label)
        self.advanced_content.setVisible(False)
        layout.addWidget(self.advanced_content)

        self.temperature_spin.valueChanged.connect(
            self._sync_response_presets_from_exact_values
        )
        self.top_p_spin.valueChanged.connect(
            self._sync_response_presets_from_exact_values
        )
        self.max_tokens_spin.valueChanged.connect(
            self._sync_response_presets_from_exact_values
        )
        self._sync_response_presets_from_exact_values()

        layout.addStretch()
        self.settings_body_scroll.setWidget(self.settings_body)
        root_layout.addWidget(self.settings_body_scroll, 1)

        # --- Footer ---
        self.footer_widget = QWidget(self)
        footer_layout = QVBoxLayout(self.footer_widget)
        footer_layout.setContentsMargins(24, 0, 24, 16)
        footer_layout.setSpacing(12)

        divider = QFrame(self.footer_widget)
        divider.setObjectName("AssistantSettingsDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        footer_layout.addWidget(divider)

        self.save_error_label = QLabel(self.footer_widget)
        self.save_error_label.setObjectName("AssistantSettingsSaveError")
        self.save_error_label.setWordWrap(True)
        self.save_error_label.setVisible(False)
        footer_layout.addWidget(self.save_error_label)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(10)
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("AssistantSecondaryButton")
        self.btn_cancel.setMinimumWidth(94)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_activate = QPushButton("Save")
        self.btn_activate.setObjectName("AssistantPrimaryButton")
        self.btn_activate.setMinimumWidth(94)
        self.btn_activate.setEnabled(False)
        self.btn_activate.clicked.connect(self.on_activate_clicked)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_activate)
        footer_layout.addLayout(btn_layout)
        root_layout.addWidget(self.footer_widget)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("AssistantSettingsSection")
        return label

    def _selected_model_id(self) -> str:
        """Return the stable repository id behind the product-facing label."""
        value = self.local_model_combo.currentData()
        return str(value or "").strip()

    def _apply_response_style_preset(self, key: str) -> None:
        values = _RESPONSE_STYLE_PRESETS.get(key)
        if values is None:
            return
        self._updating_response_presets = True
        try:
            with (
                QSignalBlocker(self.temperature_spin),
                QSignalBlocker(self.top_p_spin),
            ):
                self.temperature_spin.setValue(values[0])
                self.top_p_spin.setValue(values[1])
        finally:
            self._updating_response_presets = False
        self._sync_response_presets_from_exact_values()

    def _apply_response_length_preset(self, key: str) -> None:
        value = _RESPONSE_LENGTH_PRESETS.get(key)
        if value is None:
            return
        self._updating_response_presets = True
        try:
            with QSignalBlocker(self.max_tokens_spin):
                self.max_tokens_spin.setValue(value)
        finally:
            self._updating_response_presets = False
        self._sync_response_presets_from_exact_values()

    def _sync_response_presets_from_exact_values(self, *_args) -> None:
        if self._updating_response_presets:
            return
        style_key = next(
            (
                key
                for key, (temperature, top_p) in _RESPONSE_STYLE_PRESETS.items()
                if math.isclose(
                    self.temperature_spin.value(),
                    temperature,
                    abs_tol=0.001,
                )
                and math.isclose(self.top_p_spin.value(), top_p, abs_tol=0.001)
            ),
            None,
        )
        length_key = next(
            (
                key
                for key, value in _RESPONSE_LENGTH_PRESETS.items()
                if self.max_tokens_spin.value() == value
            ),
            None,
        )
        self.response_style_control.set_selected(style_key)
        self.response_length_control.set_selected(length_key)
        custom_values = style_key is None or length_key is None
        self.advanced_toggle.setText(
            "Advanced settings · Custom" if custom_values else "Advanced settings"
        )

    def _set_advanced_visible(self, visible: bool) -> None:
        self.advanced_content.setVisible(visible)
        self.advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
        )
        self._schedule_fit()

    def _schedule_fit(self) -> None:
        """Coalesce content-fit requests in a timer owned by this dialog."""
        self._fit_timer.start(0)

    def _fit_initial_content(self) -> None:
        if not self.isVisible():
            return
        body_layout = self.settings_body.layout()
        if body_layout is not None:
            body_layout.activate()
        footer_layout = self.footer_widget.layout()
        if footer_layout is not None:
            footer_layout.activate()
        body_hint = self.settings_body.sizeHint()
        footer_hint = self.footer_widget.sizeHint()
        self.resize_preserving_center(
            QSize(
                min(max(520, body_hint.width()), 700),
                min(
                    max(
                        body_hint.height()
                        + footer_hint.height()
                        + (self.settings_body_scroll.frameWidth() * 2),
                        1,
                    ),
                    700,
                ),
            )
        )

    def _set_model_status_tone(self, tone: str) -> None:
        self.model_status_dot.setProperty("statusTone", tone)
        style = self.model_status_dot.style()
        if style is not None:
            style.unpolish(self.model_status_dot)
            style.polish(self.model_status_dot)

    def _set_model_action_destructive(self, destructive: bool) -> None:
        self.local_action_btn.setProperty("destructive", destructive)
        style = self.local_action_btn.style()
        if style is not None:
            style.unpolish(self.local_action_btn)
            style.polish(self.local_action_btn)

    def load_state(self):
        """Load lightweight config state and defer cache/runtime inspection."""
        selection = self.config.assistant_runtime_selection()

        with QSignalBlocker(self.local_model_combo):
            index = self.local_model_combo.findData(self.config.model_name)
            if index >= 0:
                self.local_model_combo.setCurrentIndex(index)
        self._update_model_migration_notice()

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

    @staticmethod
    def _set_status_text_color(label: QLabel, color: str) -> None:
        """Apply a semantic color without introducing a second dialog palette."""
        label.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def _show_model_status_checking(self) -> None:
        """Render a non-blocking placeholder while inspection runs."""
        self._current_local_model_state = None
        self.local_downloaded = False
        self.local_status_label.setText("Model: Checking...")
        self._set_status_text_color(self.local_status_label, Theme.TEXT_SECONDARY)
        self._set_model_status_tone("neutral")
        self.local_runtime_label.setText("Environment check: Checking...")
        self._set_status_text_color(self.local_runtime_label, Theme.TEXT_SECONDARY)
        self._render_runtime_attempt_notice()
        self.local_resource_label.setText("")
        self.local_action_btn.setText("Checking...")
        self._set_model_action_destructive(False)
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
            self._set_status_text_color(self.local_status_label, Theme.LOG_INFO)
            self._set_model_status_tone("warning")
            self.local_action_btn.setText("Delete")
            self._set_model_action_destructive(True)
        else:
            self.local_status_label.setText("Model: Not installed")
            self._set_status_text_color(
                self.local_status_label,
                Theme.TEXT_SECONDARY,
            )
            self._set_model_status_tone("neutral")
            self.local_action_btn.setText("Install Model")
            self._set_model_action_destructive(False)
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
            self._set_model_status_tone("ready")
            detail = state.runtime_message.removeprefix("Local runtime ready.").strip()
            if not detail:
                self.local_runtime_label.setText("Environment check: Ready")
                self._set_status_text_color(
                    self.local_runtime_label,
                    Theme.LOG_INFO,
                )
            else:
                self.local_runtime_label.setText(
                    f"Environment check: Ready with notes — {detail}"
                )
                self._set_status_text_color(
                    self.local_runtime_label,
                    Theme.LOG_WARNING,
                )
            self._render_runtime_attempt_notice()
            return

        detail = state.runtime_message.removeprefix("Local runtime unavailable. ")
        self.local_runtime_label.setText(f"Environment check: Not ready — {detail}")
        if "Missing optional packages" in state.runtime_message:
            self._set_status_text_color(
                self.local_runtime_label,
                Theme.LOG_ERROR,
            )
            self._set_model_status_tone("error")
        else:
            self._set_status_text_color(
                self.local_runtime_label,
                Theme.LOG_WARNING,
            )
            self._set_model_status_tone("warning")
        self._render_runtime_attempt_notice()

    def _render_runtime_attempt_notice(self) -> None:
        """Keep a failed start distinct from prerequisite readiness."""
        notice_reader = getattr(
            self.agent_manager,
            "assistant_runtime_settings_notice",
            None,
        )
        notice = notice_reader() if callable(notice_reader) else ""
        if not isinstance(notice, str) or not notice.strip():
            self.last_runtime_attempt_label.clear()
            self.last_runtime_attempt_label.setVisible(False)
            return
        self.last_runtime_attempt_label.setText(
            f"Last start attempt failed: {notice.strip()}"
        )
        self.last_runtime_attempt_label.setVisible(True)

    def check_local_model_status(self, *_args):
        """Request one coherent status snapshot without blocking the GUI."""
        if not self._download_observers_attached:
            return
        self._inspection_request_id += 1
        request = ModelStatusInspectionRequest(
            request_id=self._inspection_request_id,
            model_name=self._selected_model_id(),
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
        if result.request.model_name != self._selected_model_id():
            return
        self._pending_inspection_request_id = None
        self.is_downloading = self.download_lifecycle.active_target is not None
        self._render_local_model_state(result)
        self.update_validation_state()

    def _apply_config_to_controls(self) -> None:
        """Render a background-loaded config without emitting new inspections."""
        with QSignalBlocker(self.local_model_combo):
            index = self.local_model_combo.findData(self.config.model_name)
            if index >= 0:
                self.local_model_combo.setCurrentIndex(index)
        self._update_model_migration_notice()
        with QSignalBlocker(self.local_enable_chk):
            self.local_enable_chk.setChecked(self.config.local_model_enabled)
        self.temperature_spin.setValue(self.config.temperature)
        self.top_p_spin.setValue(self.config.top_p)
        self.max_tokens_spin.setValue(self.config.max_new_tokens)
        self._sync_response_presets_from_exact_values()

    def _update_model_migration_notice(self) -> None:
        """Present unsupported persisted choices without mutating settings."""
        message = self.config.configured_model_unavailable_message()
        self.model_migration_label.setText(message or "")
        self.model_migration_label.setVisible(bool(message))

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
        model_name = self._selected_model_id()
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
        self._set_model_status_tone("warning")
        self.download_progress.setRange(0, 0)
        self.download_progress.setVisible(True)
        self._schedule_fit()
        self.update_validation_state()

    def _delete_model(self):
        """Delete the selected local model from cache after confirmation."""
        repo_id = self._selected_model_id()
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
            self._set_model_status_tone("warning")
            self.download_progress.setRange(0, 0)
            self.download_progress.setVisible(True)
            self._schedule_fit()
            self.local_action_btn.setEnabled(False)
            self.update_validation_state()

    def on_download_progress(self, percent, msg):
        """Handle download progress updates.

        Args:
            percent: Download completion percentage.
            msg: Progress message to display.

        """
        target = self.download_lifecycle.active_target
        if target is None or target.repo_id == self._selected_model_id():
            self.local_status_label.setText(msg)
            if 0 <= int(percent) <= 100:
                self.download_progress.setRange(0, 100)
                self.download_progress.setValue(int(percent))
            else:
                self.download_progress.setRange(0, 0)
            self.download_progress.setVisible(True)

    def on_download_finished(self, outcome: object):
        """Handle successful download completion.

        Args:
            outcome: Immutable target-aware download outcome.

        """
        if not isinstance(outcome, ModelDownloadOutcome):
            return
        self.is_downloading = not self.download_lifecycle.is_idle()
        self.download_progress.setVisible(False)
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
        self.download_progress.setVisible(False)
        self._schedule_fit()
        selected_target = outcome.target.repo_id == self._selected_model_id()
        self.check_local_model_status()
        if outcome.cancelled:
            return
        logger.error(
            "Model download failed model=%s diagnostic=%s",
            outcome.target.repo_id,
            outcome.diagnostic_message or outcome.message,
        )
        if selected_target:
            self.local_status_label.setText(
                "Download timed out"
                if outcome.failure_code is ModelDownloadFailureCode.TIMEOUT
                else "Download failed"
            )
            self._set_status_text_color(self.local_status_label, Theme.LOG_ERROR)
            self._set_model_status_tone("error")
            self.local_action_btn.setText("Retry")
            self.download_progress.setVisible(False)
            self._schedule_fit()
        QMessageBox.critical(
            self,
            "Download Failed",
            model_download_public_failure_message(outcome),
        )

    def on_cache_cleanup_finished(self, result: object) -> None:
        """Render explicit deletion after app-owned recursive cleanup terminal."""
        if not isinstance(result, ModelCacheCleanupResult):
            return
        if result.reason is not ModelCacheCleanupReason.USER_DELETE:
            return
        self.is_downloading = not self.download_lifecycle.is_idle()
        self.download_progress.setVisible(False)
        self._schedule_fit()
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
        model_name = self._selected_model_id()
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
        self.config.model_name = self._selected_model_id()
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

        if not self.config.save_to_file():
            logger.error("Assistant settings could not be persisted")
            self.save_error_label.setText(
                "Settings could not be saved. Check that your XBrainLab settings "
                "folder is writable, then try again."
            )
            self.save_error_label.setVisible(True)
            self._schedule_fit()
            return

        self.save_error_label.clear()
        self.save_error_label.setVisible(False)
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

    def showEvent(self, event):  # noqa: N802
        """Fit the collapsed product form after Qt resolves visible size hints."""
        super().showEvent(event)
        self._schedule_fit()

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

    def get_result(self):
        """Return the configured local assistant settings."""
        return self.get_config()
