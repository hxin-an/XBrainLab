"""Chat Panel - Main chat interface component.

Provides the ``ChatPanel`` widget implementing a Copilot-style chat interface
using ``MessageBubble`` widgets. Handles user input, model/feature selection,
streaming responses, and debug-mode interception.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,  # Added for M3.1
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.controller.chat_controller import ChatController
from XBrainLab.backend.utils.logger import logger

# M3.1: Debug Mode
from XBrainLab.debug.tool_debug_mode import ToolDebugMode
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.ui.product_language import command_labels, workflow_stage_text_label

from ..styles.theme import Theme
from .message_bubble import MessageBubble
from .styles import (
    ASSISTANT_PANEL_STYLE,
    CONTROL_PANEL_STYLE,
    DROPDOWN_MENU_STYLE,
    EMPTY_STATE_STYLE,
    EMPTY_STATE_TEXT_STYLE,
    EMPTY_STATE_TITLE_STYLE,
    FOOTER_BUTTON_STYLE,
    FOOTER_STATUS_STYLE,
    GUIDANCE_PANEL_STYLE,
    GUIDANCE_STAGE_STYLE,
    GUIDANCE_TEXT_STYLE,
    HEADER_STYLE,
    HEADER_SUBTITLE_STYLE,
    HEADER_TITLE_STYLE,
    INPUT_FIELD_STYLE,
    NOTICE_LABEL_STYLE,
    SCROLL_AREA_STYLE,
    SEND_BUTTON_PROCESSING_STYLE,
    SEND_BUTTON_STYLE,
    STATUS_CHIP_STYLE,
    STATUS_CHIP_WARNING_STYLE,
    TOOLBAR_BUTTON_STYLE,
)

PRODUCT_STATUS_HIDDEN_COMMANDS = frozenset(
    {
        "load_data",
        "attach_labels",
        "import_labels",
    }
)


class ChatPanel(QWidget):
    """Copilot-style chat interface using MessageBubble widgets.

    Features QFrame-based bubbles, sender-based alignment, dynamic width
    adjustment, and streaming text support. UI state is decoupled from
    business logic via ``ChatController``.

    Attributes:
        current_agent_bubble: The active agent ``MessageBubble`` being
            streamed into, or ``None``.
        is_processing: Whether the panel is currently awaiting a response.
        debug_mode: Optional ``ToolDebugMode`` for interactive debug
            script playback.
        scroll_area: Scrollable area containing chat messages.
        input_field: Text input for user messages.
        send_btn: Button to send messages or stop generation.
        feature_btn: Dropdown button for feature/persona selection.
        model_btn: Dropdown button for LLM model selection.

    """

    # UI-driven Signals
    send_message = pyqtSignal(str)
    stop_generation = pyqtSignal()
    model_changed = pyqtSignal(str)
    execution_mode_changed = pyqtSignal(str)  # 'single' or 'multi'
    settings_requested = pyqtSignal()
    new_conversation_requested = pyqtSignal()  # M0.3 New Conversation
    retry_requested = pyqtSignal()
    debug_tool_requested = pyqtSignal(str, dict)  # M3.1 Debug Mode

    def __init__(self):
        """Initialize the ChatPanel with UI components and optional debug mode."""
        super().__init__()
        # Temporary state for current streaming bubble
        self.current_agent_bubble: MessageBubble | None = None

        self.is_processing = False
        self._retry_available = False
        self._footer_status_text = "No EEG data open · Import files to begin"
        self.setObjectName("AssistantPanel")
        self.setStyleSheet(ASSISTANT_PANEL_STYLE)
        self.init_ui()

        # M3.1 Interactive Debug Mode
        app = QApplication.instance()
        script_path = app.property("tool_debug_script") if app else None
        self.debug_mode = ToolDebugMode(script_path) if script_path else None

    def init_ui(self):
        """Initialize all UI sub-components including chat display and controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Builds compatibility anchors only; the user-facing controls live in
        # the dock title bar so the transcript/empty state is the first visual.
        self._build_header(layout)
        self._build_workflow_guidance(layout)

        # --- Chat Display (Scroll Area) ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.scroll_area.setStyleSheet(SCROLL_AREA_STYLE)

        # Container Widget inside ScrollArea
        self.chat_content_widget = QWidget()
        self.chat_content_widget.setStyleSheet("background-color: #1e1e1e;")
        self.chat_layout = QVBoxLayout(self.chat_content_widget)
        self.chat_layout.setContentsMargins(12, 12, 12, 12)
        self.chat_layout.setSpacing(12)
        self.empty_state_widget = self._build_empty_state()
        self.chat_layout.addWidget(self.empty_state_widget)
        self.chat_layout.addStretch()  # Push messages to top

        self.scroll_area.setWidget(self.chat_content_widget)
        layout.addWidget(self.scroll_area)

        # --- Control Panel (Bottom) ---
        control_panel = QWidget()
        self.control_panel = control_panel
        control_panel.setObjectName("ControlPanel")
        control_panel.setStyleSheet(CONTROL_PANEL_STYLE)
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(10, 8, 10, 8)
        control_layout.setSpacing(7)

        # Composer: Input Field and Send / Stop Button
        input_widget = QWidget()
        input_widget.setStyleSheet("background: transparent; border: none;")
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(4, 4, 4, 4)
        input_layout.setSpacing(10)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText(
            "Ask about data, preprocessing, epoching, datasets, or training..."
        )
        self.input_field.setStyleSheet(INPUT_FIELD_STYLE)
        self.input_field.returnPressed.connect(self._on_send)
        input_layout.addWidget(self.input_field, 1)

        self.send_btn = QToolButton()
        self.send_btn.setText("Send")
        self.send_btn.setFixedSize(64, 36)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_send)
        self.send_btn.setStyleSheet(SEND_BUTTON_STYLE)
        input_layout.addWidget(self.send_btn)

        control_layout.addWidget(input_widget)

        # Compatibility anchor for tests/callers that still read runtime status.
        # It is deliberately not added to the footer: the composer should stay
        # focused on input, not repeat workflow diagnostics.
        self.runtime_status_label = QLabel("")
        self.runtime_status_label.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; background: transparent; border: none;"
        )
        self.runtime_status_label.setWordWrap(False)
        self.runtime_status_label.setVisible(False)

        self.footer_status_label = QLabel(self._footer_status_text)
        self.footer_status_label.setObjectName("AssistantFooterStatus")
        self.footer_status_label.setStyleSheet(FOOTER_STATUS_STYLE)
        self.footer_status_label.setWordWrap(False)
        self.footer_status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.footer_status_label.setVisible(False)

        self.retry_btn = QToolButton()
        self.retry_btn.setText("")
        self.retry_btn.setFixedSize(52, 26)
        self.retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_btn.setToolTip("Send a request before retrying.")
        self.retry_btn.setStyleSheet(FOOTER_BUTTON_STYLE)
        self.retry_btn.setEnabled(False)
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(self._on_retry)

        self.clear_btn = QToolButton()
        self.clear_btn.setText("")
        self.clear_btn.setFixedSize(52, 26)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setToolTip("Clear conversation")
        self.clear_btn.setStyleSheet(FOOTER_BUTTON_STYLE)
        self.clear_btn.setVisible(False)
        self.clear_btn.clicked.connect(self._on_clear)

        self.step_mode_status_label = QLabel("")
        self.step_mode_status_label.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; background: transparent; border: none;"
        )
        self.step_mode_status_label.setVisible(False)

        self.notice_label = QLabel("")
        self.notice_label.setObjectName("AssistantNotice")
        self.notice_label.setStyleSheet(NOTICE_LABEL_STYLE)
        self.notice_label.setWordWrap(True)
        self.notice_label.setVisible(False)
        control_layout.addWidget(self.notice_label)
        layout.addWidget(control_panel)

    def _build_header(self, parent_layout: QVBoxLayout) -> None:
        """Build hidden compatibility anchors for older callers/tests."""
        header = QWidget()
        header.setObjectName("AssistantHeader")
        header.setStyleSheet(HEADER_STYLE)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        title_stack = QVBoxLayout()
        title_stack.setContentsMargins(0, 0, 0, 0)
        title_stack.setSpacing(2)

        self.title_label = QLabel("")
        self.title_label.setObjectName("AssistantTitle")
        self.title_label.setStyleSheet(HEADER_TITLE_STYLE)
        self.title_label.setVisible(False)

        subtitle = QLabel("Ask about data, preprocessing, and training.")
        subtitle.setObjectName("AssistantSubtitle")
        subtitle.setStyleSheet(HEADER_SUBTITLE_STYLE)
        subtitle.setWordWrap(True)
        subtitle.setVisible(False)
        title_stack.addWidget(subtitle)

        title_row.addLayout(title_stack, 1)

        self.options_btn = QToolButton()
        self.options_btn.setText("")
        self.options_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.options_btn.setFixedSize(32, 28)
        self.options_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.options_btn.setToolTip("Options")
        self.options_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        self.options_btn.setVisible(False)

        header_layout.addLayout(title_row)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)

        self.feature_btn = QPushButton("")
        self.feature_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.feature_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        self.feature_menu = QMenu(self)
        self.feature_menu.setStyleSheet(DROPDOWN_MENU_STYLE)
        self.feature_btn.setMenu(self.feature_menu)
        self.feature_btn.setVisible(False)

        self.model_btn = QPushButton("Local model")
        self.model_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.model_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)

        self.model_menu = QMenu(self)
        self.model_menu.setStyleSheet(DROPDOWN_MENU_STYLE)
        self.model_menu.setTitle("Runtime")
        self.model_btn.setMenu(self.model_menu)
        self.update_model_menu()
        self.model_btn.setVisible(False)

        self.mode_btn = QPushButton("")
        self.mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        self.mode_menu = QMenu(self)
        self.mode_menu.setStyleSheet(DROPDOWN_MENU_STYLE)
        self.mode_btn.setMenu(self.mode_menu)
        self.mode_btn.setVisible(False)

        self.options_menu = QMenu(self)
        self.options_menu.setStyleSheet(DROPDOWN_MENU_STYLE)
        self.settings_action = QAction("Assistant settings", self)
        self.settings_action.triggered.connect(
            lambda _checked=False: self.settings_requested.emit()
        )
        self.options_menu.addAction(self.settings_action)
        self.clear_conversation_action = QAction("Clear conversation", self)
        self.clear_conversation_action.setEnabled(False)
        self.clear_conversation_action.triggered.connect(self._on_clear)
        self.new_conversation_action = self.clear_conversation_action
        self.options_btn.setMenu(self.options_menu)
        toolbar_layout.addStretch()

        self.status_label = QLabel("No data loaded")
        self.status_label.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; background: transparent; border: none;",
        )
        self.status_label.setToolTip("Workflow status")
        self.status_label.setVisible(False)
        toolbar_layout.addWidget(self.status_label)

        header_layout.addLayout(toolbar_layout)
        header.setVisible(False)
        parent_layout.addWidget(header)

    def _build_workflow_guidance(self, parent_layout: QVBoxLayout) -> None:
        """Build hidden compatibility labels for workflow guidance.

        Product status belongs in header details and the empty state. These
        labels are kept for older callers/tests without rendering a persistent
        status dashboard inside the chat panel.
        """
        guidance = QWidget()
        guidance.setObjectName("WorkflowGuidance")
        guidance.setStyleSheet(GUIDANCE_PANEL_STYLE)
        guidance_layout = QVBoxLayout(guidance)
        guidance_layout.setContentsMargins(12, 8, 12, 8)
        guidance_layout.setSpacing(2)

        self.workflow_stage_label = QLabel("No data loaded")
        self.workflow_stage_label.setObjectName("WorkflowStage")
        self.workflow_stage_label.setStyleSheet(GUIDANCE_STAGE_STYLE)
        guidance_layout.addWidget(self.workflow_stage_label)

        self.workflow_next_label = QLabel("Import EEG files or ask what is ready.")
        self.workflow_next_label.setObjectName("WorkflowGuidanceText")
        self.workflow_next_label.setStyleSheet(GUIDANCE_TEXT_STYLE)
        self.workflow_next_label.setWordWrap(True)
        guidance_layout.addWidget(self.workflow_next_label)

        # Backward-compatible aliases for older tests/callers. They are no
        # longer rendered as chip dumps.
        self.backend_stage_chip = self.workflow_stage_label
        self.available_commands_chip = self.workflow_next_label
        self.model_status_chip = QLabel("")
        self.model_status_chip.setVisible(False)

        self.workflow_guidance = guidance
        guidance.setVisible(False)
        parent_layout.addWidget(guidance)

    def _build_empty_state(self) -> QFrame:
        """Build the initial guidance panel shown before conversation starts."""
        empty = QFrame()
        empty.setObjectName("AssistantEmptyState")
        empty.setStyleSheet(EMPTY_STATE_STYLE)
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(14, 14, 14, 14)
        empty_layout.setSpacing(8)

        self.empty_state_title = QLabel("Start with your EEG data")
        self.empty_state_title.setObjectName("AssistantEmptyTitle")
        self.empty_state_title.setStyleSheet(EMPTY_STATE_TITLE_STYLE)
        empty_layout.addWidget(self.empty_state_title)

        intro = QLabel(
            "Ask for a quick workflow check, plan preprocessing, or explain why "
            "training is blocked."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(EMPTY_STATE_TEXT_STYLE)
        empty_layout.addWidget(intro)

        self.empty_state_backend_label = QLabel("No EEG files are open yet.")
        self.empty_state_backend_label.setStyleSheet(EMPTY_STATE_TEXT_STYLE)
        self.empty_state_backend_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_state_backend_label)

        self.empty_state_model_label = QLabel("")
        self.empty_state_model_label.setStyleSheet(EMPTY_STATE_TEXT_STYLE)
        self.empty_state_model_label.setWordWrap(True)
        self.empty_state_model_label.setVisible(False)

        self.empty_state_next_label = QLabel("Import EEG files · Ask what is ready")
        self.empty_state_next_label.setStyleSheet(EMPTY_STATE_TEXT_STYLE)
        self.empty_state_next_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_state_next_label)

        return empty

    def update_model_menu(self):
        """Update the model dropdown menu based on current LLM configuration.

        Reads ``LLMConfig`` to determine whether the local model option
        should be enabled or disabled.
        """
        self.model_menu.clear()

        # Load config without blocking UI too cleanly (it's small JSON)
        # Use fallback if loading fails
        try:
            config = LLMConfig.load_from_file() or LLMConfig()
            local_enabled = config.local_model_enabled
            local_runtime_ready = config.local_backend_ready()
            local_runtime_message = config.local_backend_status_message()
            active_mode = LLMConfig.assistant_runtime_selection_from(
                config
            ).ui_active_mode
        except Exception:
            logger.debug("Failed to load LLM config for model menu", exc_info=True)
            local_enabled = True
            local_runtime_ready = True
            local_runtime_message = "Local runtime unavailable."
            active_mode = "local"

        local_action = QAction("Local model", self)
        if not local_enabled:
            local_action.setEnabled(False)
            local_action.setText("Local model disabled")
            local_action.setToolTip("Enable the local model in settings to use it.")
        elif not local_runtime_ready:
            local_action.setEnabled(False)
            local_action.setText("Local model unavailable")
            local_action.setToolTip(local_runtime_message)
        else:
            if local_runtime_message != "Local runtime ready.":
                local_action.setText("Local model (CPU fallback)")
                local_action.setToolTip(local_runtime_message)
            local_action.triggered.connect(
                lambda checked, action=local_action: self._set_model(
                    "local",
                    action.text(),
                )
            )
        self.model_menu.addAction(local_action)

        local_label = (
            "Local model (CPU fallback)"
            if local_runtime_ready and local_runtime_message != "Local runtime ready."
            else "Local model"
        )
        label = local_label if active_mode == "local" else "Local model"
        self.model_btn.setText(label)
        if hasattr(self, "runtime_status_label"):
            self.runtime_status_label.setText("")
            self.runtime_status_label.setToolTip(
                "Runtime details are available in options."
            )

    def connect_controller(self, controller: ChatController):
        """Connect to a backend ChatController for state synchronization.

        Wires the controller's signals (``message_added``,
        ``processing_state_changed``, ``conversation_cleared``) to the
        corresponding UI rendering methods.

        Args:
            controller: The ``ChatController`` instance to bind.

        """
        controller.message_added.connect(self._render_message)
        controller.processing_state_changed.connect(self._update_processing_ui)
        controller.conversation_cleared.connect(self._clear_ui)

    def _set_feature(self, feature_name: str):
        """Update the feature selector button text.

        Args:
            feature_name: The selected feature/persona name.

        """
        self.feature_btn.setText(feature_name)
        if hasattr(self, "options_btn"):
            self.options_btn.setToolTip(f"Mode: {feature_name}")

    def _set_model(self, mode_key: str, label: str | None = None):
        """Update the selector button and emit a normalized runtime mode.

        Args:
            mode_key: Runtime backend mode identifier.
            label: Optional UI label to show on the button.

        """
        normalized_mode = LLMConfig.normalize_backend_mode(mode_key)
        button_label = label if label is not None else ("Local model")
        self.model_btn.setText(button_label)
        if hasattr(self, "runtime_status_label"):
            self.runtime_status_label.setText("")
            self.runtime_status_label.setToolTip(
                "Runtime details are available in options."
            )
        self.model_changed.emit(normalized_mode)

    def _set_execution_mode(self, mode_key: str, label: str):
        """Update the execution mode selector and emit mode change signal.

        Args:
            mode_key: The mode identifier (``'single'`` or ``'multi'``).
            label: Human-friendly label for the button text.

        """
        self.mode_btn.setText(label)
        if hasattr(self, "step_mode_status_label"):
            self.step_mode_status_label.setText(label)
        self.execution_mode_changed.emit(mode_key)

    def _on_new_conversation(self):
        """Emit the new conversation requested signal."""
        self.new_conversation_requested.emit()

    def _on_retry(self):
        """Emit a request to retry the most recent user message."""
        if not self.is_processing:
            self.retry_requested.emit()

    def _on_clear(self):
        """Emit a request to clear the conversation."""
        if not self.is_processing:
            self.new_conversation_requested.emit()

    def _on_send(self):
        """Handle send button click or Enter key press.

        If currently processing, emits ``stop_generation``. If debug mode
        is active, dispatches the next debug tool call. Otherwise, emits
        ``send_message`` with the user's input text.
        """
        # UI Check: Processing state is now managed via signals
        # Use internal state instead of checking button text
        if self.is_processing:
            self.stop_generation.emit()
            return

        # M3.1 Debug Mode Interception
        if self.debug_mode:
            if not self.debug_mode.is_complete:
                call = self.debug_mode.next_call()
                if call:
                    # Clear input just in case
                    self.input_field.clear()
                    # Emit debug request
                    self.debug_tool_requested.emit(call.tool, call.params)
                else:
                    self.input_field.setText("Debug Script Completed.")
            else:
                self.input_field.setText("Debug Script Completed.")
            return

        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()
        self.send_message.emit(text)
        # Note: We don't verify processing state here implicitly,
        # Controller will call set_processing(True) which updates UI.

    def set_processing_state(self, is_processing: bool):
        """Update the processing state and refresh the UI accordingly.

        Args:
            is_processing: Whether the agent is currently generating.

        """
        self._update_processing_ui(is_processing)

    def _update_processing_ui(self, is_processing: bool):
        """Toggle send button appearance between send and stop states.

        Args:
            is_processing: Whether the agent is currently generating.

        """
        self.is_processing = is_processing  # Sync state
        if is_processing:
            self.send_btn.setText("Stop")
            self.send_btn.setStyleSheet(SEND_BUTTON_PROCESSING_STYLE)
        else:
            self.send_btn.setText("Send")
            self.send_btn.setStyleSheet(SEND_BUTTON_STYLE)

        if hasattr(self, "input_field"):
            self.input_field.setEnabled(not is_processing)
        if hasattr(self, "feature_btn"):
            self.feature_btn.setEnabled(not is_processing)
        if hasattr(self, "model_btn"):
            self.model_btn.setEnabled(not is_processing)
        if hasattr(self, "mode_btn"):
            self.mode_btn.setEnabled(not is_processing)
        if hasattr(self, "retry_btn"):
            self.retry_btn.setEnabled((not is_processing) and self._retry_available)
        if hasattr(self, "clear_btn"):
            self.clear_btn.setEnabled((not is_processing) and self._retry_available)
        if hasattr(self, "new_conversation_action"):
            self.new_conversation_action.setEnabled(
                (not is_processing) and self._retry_available
            )
        if hasattr(self, "options_btn"):
            self.options_btn.setEnabled(not is_processing)

    def set_status_summary(self, text: str, tooltip: str | None = None) -> None:
        """Set the compact backend/model status line shown in the toolbar."""
        if not hasattr(self, "status_label"):
            return
        if tooltip is not None:
            self.status_label.setToolTip(tooltip)

        stage = "checking"
        model_status = "checking"
        if "|" in text:
            stage_part, model_part = text.split("|", 1)
            stage = stage_part.replace("Backend:", "").strip()
            model_status = model_part.strip()
        elif text.lower().startswith("backend:"):
            stage = text.replace("Backend:", "").strip()
        stage = workflow_stage_text_label(stage)
        self.status_label.setText(stage)

        self._update_status_widgets(
            stage=stage,
            model_status=model_status,
            available_commands=None,
            tooltip=tooltip,
        )

    def set_product_status(
        self,
        stage: str,
        model_status: str,
        available_commands: list[str],
        tooltip: str | None = None,
        blocked_reason: str | None = None,
    ) -> None:
        """Update workflow guidance and low-priority diagnostics."""
        stage = workflow_stage_text_label(stage)
        self.status_label.setText(stage)
        if tooltip is not None:
            self.status_label.setToolTip(tooltip)
        self._update_status_widgets(
            stage=stage,
            model_status=model_status,
            available_commands=available_commands,
            tooltip=tooltip,
            blocked_reason=blocked_reason,
        )

    def _update_status_widgets(
        self,
        stage: str,
        model_status: str,
        available_commands: list[str] | None,
        tooltip: str | None = None,
        blocked_reason: str | None = None,
    ) -> None:
        """Apply status text to guidance and empty-state labels."""
        status_tooltip = f"Workflow: {stage}\nSetup: {model_status}"
        if tooltip:
            status_tooltip = f"{status_tooltip}\n\n{tooltip}"
        if hasattr(self, "title_label"):
            self.title_label.setToolTip(status_tooltip)
        if hasattr(self, "options_btn"):
            self.options_btn.setToolTip(status_tooltip)
        if hasattr(self, "status_label"):
            self.status_label.setToolTip(status_tooltip)

        if hasattr(self, "backend_stage_chip"):
            self.backend_stage_chip.setText(stage)
            if tooltip:
                self.backend_stage_chip.setToolTip(tooltip)

        model_ready = "ready" in model_status.lower() and "unavailable" not in (
            model_status.lower()
        )
        if hasattr(self, "model_status_chip"):
            self.model_status_chip.setText(model_status)
            self.model_status_chip.setStyleSheet(
                STATUS_CHIP_STYLE if model_ready else STATUS_CHIP_WARNING_STYLE
            )
            if tooltip:
                self.model_status_chip.setToolTip(tooltip)
        if hasattr(self, "runtime_status_label"):
            self.runtime_status_label.setText("")
            self.runtime_status_label.setToolTip(status_tooltip)

        visible_command_names = (
            None
            if available_commands is None
            else [
                name
                for name in available_commands
                if str(name) not in PRODUCT_STATUS_HIDDEN_COMMANDS
            ]
        )
        display_commands = (
            None
            if visible_command_names is None
            else command_labels(visible_command_names)
        )
        if display_commands is None:
            command_text = self._footer_status_for(stage, None, blocked_reason)
        elif visible_command_names:
            preview = ", ".join(display_commands[:3])
            extra_count = len(display_commands) - 3
            suffix = "" if extra_count <= 0 else f" +{extra_count}"
            command_text = f"{stage} · {preview}{suffix}"
        else:
            command_text = self._footer_status_for(stage, [], blocked_reason)

        if hasattr(self, "available_commands_chip"):
            self.available_commands_chip.setText(command_text)
            if tooltip:
                self.available_commands_chip.setToolTip(tooltip)

        if hasattr(self, "empty_state_backend_label"):
            self.empty_state_backend_label.setText(
                self._empty_state_stage_sentence(stage)
            )
        if hasattr(self, "empty_state_model_label"):
            self.empty_state_model_label.setText("")
        if hasattr(self, "empty_state_next_label"):
            if display_commands:
                self.empty_state_next_label.setText(
                    self._empty_state_next_text(display_commands)
                )
            elif blocked_reason:
                self.empty_state_next_label.setText(blocked_reason)
            else:
                self.empty_state_next_label.setText(
                    "Import EEG files · Ask what is ready"
                )
        self._footer_status_text = self._footer_status_for(
            stage,
            display_commands,
            blocked_reason,
        )
        self._update_footer_status_label()

    @staticmethod
    def _empty_state_stage_sentence(stage: str) -> str:
        """Return a conversational empty-state sentence for a workflow stage."""
        if stage == "No data loaded":
            return "No EEG files are open yet."
        return f"Current workflow stage: {stage}."

    @staticmethod
    def _empty_state_next_text(display_commands: list[str]) -> str:
        """Return compact next-step copy without exposing command identifiers."""
        return " · ".join(display_commands[:3])

    @staticmethod
    def _footer_status_for(
        stage: str,
        display_commands: list[str] | None,
        blocked_reason: str | None,
    ) -> str:
        """Return a user-facing workflow hint for the footer/status bar."""
        if display_commands:
            first_action = display_commands[0]
            if stage == "No data loaded" and first_action == "Scan data source":
                return "No EEG data open · Scan a data source to begin"
            return f"{stage} · {first_action}"
        if blocked_reason:
            return f"{stage} · Ask what is blocking training"
        if stage == "No data loaded":
            return "No EEG data open · Import files to begin"
        return f"{stage} · Ask what is ready"

    def _update_footer_status_label(self) -> None:
        """Elide the workflow footer hint to keep narrow docks readable."""
        if not hasattr(self, "footer_status_label"):
            return
        width = max(self.footer_status_label.width(), 90)
        text = self.footer_status_label.fontMetrics().elidedText(
            self._footer_status_text,
            Qt.TextElideMode.ElideRight,
            width,
        )
        self.footer_status_label.setText(text)
        self.footer_status_label.setToolTip(self._footer_status_text)

    def set_retry_available(self, available: bool) -> None:
        """Enable Retry only when there is a previous user request."""
        self._retry_available = available
        if hasattr(self, "retry_btn"):
            self.retry_btn.setEnabled(available and not self.is_processing)
            self.retry_btn.setVisible(False)
            self.retry_btn.setToolTip(
                "Retry the last request"
                if available
                else "Send a request before retrying."
            )
        if hasattr(self, "clear_btn"):
            self.clear_btn.setVisible(False)
            self.clear_btn.setEnabled(available and not self.is_processing)
        if hasattr(self, "new_conversation_action"):
            self.new_conversation_action.setEnabled(
                available and not self.is_processing
            )

    def show_notice(self, text: str) -> None:
        """Show a low-priority inline notice outside the transcript."""
        if not hasattr(self, "notice_label"):
            return
        self.notice_label.setText(text)
        self.notice_label.setVisible(bool(text.strip()))

    def resizeEvent(self, event):  # noqa: N802
        """Re-adjust all bubble widths on window resize.

        Args:
            event: The ``QResizeEvent``.

        """
        super().resizeEvent(event)
        self._update_footer_status_label()
        # M0.4: Dynamic Width Adjustment Fix
        viewport = self.scroll_area.viewport()
        if viewport:
            container_width = viewport.width()
            # Iterate through layout items to adjust bubbles
            for i in range(self.chat_layout.count()):
                item = self.chat_layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if isinstance(widget, MessageBubble):
                        widget.adjust_width(container_width)

    def _render_message(self, text: str, is_user: bool):
        """Create and display a message bubble.

        Args:
            text: The message text content.
            is_user: Whether the message is from the user.

        """
        bubble = MessageBubble(text, is_user)

        # M0.4: Initial width adjustment
        viewport = self.scroll_area.viewport()
        if viewport:
            bubble.adjust_width(viewport.width())

        # Insert before stretch
        if hasattr(self, "empty_state_widget"):
            self.empty_state_widget.setVisible(False)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()

        if not is_user:
            # Keep track of agent bubble for streaming updates if needed
            self.current_agent_bubble = bubble

    def _clear_ui(self):
        """Remove all message bubbles from the chat layout."""
        # Rebuild the message area with only the empty-state widget and stretch.
        empty_state = getattr(self, "empty_state_widget", None)
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item:
                w = item.widget()
                if w and w is not empty_state:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
        if empty_state is not None:
            self.chat_layout.addWidget(empty_state)
        self.chat_layout.addStretch()
        self.current_agent_bubble = None
        if empty_state is not None:
            empty_state.setVisible(True)

    def on_chunk_received(self, text: str):
        """Handle a streaming text chunk from the agent.

        Appends the chunk to the current agent bubble, creating one
        if necessary, and triggers width recalculation.

        Args:
            text: The incremental text chunk to append.

        """
        # Feature: Auto-create bubble if missing (Robustness)
        if not text:
            return
        if not self.current_agent_bubble:
            self._render_message("", is_user=False)

        if self.current_agent_bubble:
            current_text = self.current_agent_bubble.get_text()
            new_text = current_text + text
            # Strip trailing newlines to prevent bottom gap
            self.current_agent_bubble.set_text(new_text.rstrip("\n"))

            # M0.4: Recalculate width after text changes
            viewport = self.scroll_area.viewport()
            if viewport:
                self.current_agent_bubble.adjust_width(viewport.width())
            self._scroll_to_bottom()

    def start_agent_message(self):
        """Prepare for a new streaming agent message.

        In the current flow the controller calls ``add_agent_message("")``
        to start, so this may be redundant. Kept for backward compatibility.
        """
        # In the new flow, Controller calls add_agent_message("") to start
        # so this might be redundant if Controller handles it.
        # Kept for compatibility if AgentManager calls it expclicity.

    def _scroll_to_bottom(self):
        """Scroll the chat area to the bottom."""
        scroll_bar = self.scroll_area.verticalScrollBar()
        if scroll_bar:
            scroll_bar.setValue(scroll_bar.maximum())

    def append_message(self, sender: str, text: str):
        """Append a message bubble.

        Args:
            sender: Message sender identifier (e.g., ``"user"``,
                ``"assistant"``).
            text: The message text content.

        """
        is_user = sender.lower() == "user"
        self._render_message(text, is_user)

    def collapse_agent_message(self, text_to_remove: str):
        """Remove or collapse specific text from the current agent bubble.

        If the remaining content is empty after removal, the bubble is
        hidden entirely.

        Args:
            text_to_remove: Substring to remove from the current agent
                bubble's text.

        """
        if self.current_agent_bubble:
            current_text = self.current_agent_bubble.get_text()
            if text_to_remove and text_to_remove in current_text:
                current_text = current_text.replace(text_to_remove, "")

            if not current_text.strip():
                self.current_agent_bubble.hide()
            elif text_to_remove:
                self.current_agent_bubble.set_text(current_text.strip())
