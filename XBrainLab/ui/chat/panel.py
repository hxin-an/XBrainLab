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
    HEADER_STYLE,
    HEADER_SUBTITLE_STYLE,
    HEADER_TITLE_STYLE,
    INPUT_FIELD_STYLE,
    SCROLL_AREA_STYLE,
    SEND_BUTTON_PROCESSING_STYLE,
    SEND_BUTTON_STYLE,
    STATUS_CHIP_STYLE,
    STATUS_CHIP_WARNING_STYLE,
    TOOLBAR_BUTTON_STYLE,
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
    new_conversation_requested = pyqtSignal()  # M0.3 New Conversation
    retry_requested = pyqtSignal()
    debug_tool_requested = pyqtSignal(str, dict)  # M3.1 Debug Mode

    def __init__(self):
        """Initialize the ChatPanel with UI components and optional debug mode."""
        super().__init__()
        # Temporary state for current streaming bubble
        self.current_agent_bubble: MessageBubble | None = None

        self.is_processing = False
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

        self._build_header(layout)

        # --- Chat Display (Scroll Area) ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.scroll_area.setStyleSheet(SCROLL_AREA_STYLE)

        # Container Widget inside ScrollArea
        self.chat_content_widget = QWidget()
        self.chat_content_widget.setStyleSheet("background-color: #15191d;")
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
        layout.addWidget(control_panel)

    def _build_header(self, parent_layout: QVBoxLayout) -> None:
        """Build the product header with status chips and compact actions."""
        header = QWidget()
        header.setObjectName("AssistantHeader")
        header.setStyleSheet(HEADER_STYLE)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        title_stack = QVBoxLayout()
        title_stack.setContentsMargins(0, 0, 0, 0)
        title_stack.setSpacing(2)

        self.title_label = QLabel("XBrainLab Assistant")
        self.title_label.setObjectName("AssistantTitle")
        self.title_label.setStyleSheet(HEADER_TITLE_STYLE)
        title_stack.addWidget(self.title_label)

        subtitle = QLabel("Guide EEG workflows from data import to training")
        subtitle.setObjectName("AssistantSubtitle")
        subtitle.setStyleSheet(HEADER_SUBTITLE_STYLE)
        subtitle.setWordWrap(True)
        title_stack.addWidget(subtitle)

        title_row.addLayout(title_stack, 1)

        self.retry_btn = QToolButton()
        self.retry_btn.setText("Retry")
        self.retry_btn.setFixedSize(58, 28)
        self.retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_btn.setToolTip("Retry last user request")
        self.retry_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        self.retry_btn.clicked.connect(self._on_retry)
        title_row.addWidget(self.retry_btn)

        self.clear_btn = QToolButton()
        self.clear_btn.setText("Clear")
        self.clear_btn.setFixedSize(58, 28)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setToolTip("Clear conversation")
        self.clear_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        self.clear_btn.clicked.connect(self._on_clear)
        title_row.addWidget(self.clear_btn)

        header_layout.addLayout(title_row)

        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(6)

        self.backend_stage_chip = QLabel("Checking workflow")
        self.backend_stage_chip.setStyleSheet(STATUS_CHIP_STYLE)
        self.backend_stage_chip.setToolTip("Current backend workflow stage")
        chip_row.addWidget(self.backend_stage_chip)

        self.model_status_chip = QLabel("Checking local model")
        self.model_status_chip.setStyleSheet(STATUS_CHIP_WARNING_STYLE)
        self.model_status_chip.setToolTip("Local model status")
        chip_row.addWidget(self.model_status_chip)

        self.available_commands_chip = QLabel("Next steps: checking")
        self.available_commands_chip.setStyleSheet(STATUS_CHIP_STYLE)
        self.available_commands_chip.setToolTip("Available workflow actions")
        chip_row.addWidget(self.available_commands_chip, 1)

        header_layout.addLayout(chip_row)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)

        self.feature_btn = QPushButton("Workflow guide")
        self.feature_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.feature_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        self.feature_menu = QMenu(self)
        self.feature_menu.setStyleSheet(DROPDOWN_MENU_STYLE)
        for feat in ["Workflow guide", "EEG analyst", "Training helper"]:
            action = QAction(feat, self)
            action.triggered.connect(lambda checked, f=feat: self._set_feature(f))
            self.feature_menu.addAction(action)
        self.feature_btn.setMenu(self.feature_menu)
        toolbar_layout.addWidget(self.feature_btn)

        self.model_btn = QPushButton("Local model")
        self.model_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.model_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)

        self.model_menu = QMenu(self)
        self.model_menu.setStyleSheet(DROPDOWN_MENU_STYLE)
        self.model_btn.setMenu(self.model_menu)
        self.update_model_menu()
        toolbar_layout.addWidget(self.model_btn)

        self.mode_btn = QPushButton("Single step")
        self.mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        self.mode_btn.setToolTip(
            "Single step: stop after each completed action\n"
            "Auto steps: continue through safe follow-up actions until done"
        )
        self.mode_menu = QMenu(self)
        self.mode_menu.setStyleSheet(DROPDOWN_MENU_STYLE)
        for mode_label, mode_key in [
            ("Single step", "single"),
            ("Auto steps", "multi"),
        ]:
            action = QAction(mode_label, self)
            action.triggered.connect(
                lambda checked, m=mode_key, lbl=mode_label: self._set_execution_mode(
                    m, lbl
                )
            )
            self.mode_menu.addAction(action)
        self.mode_btn.setMenu(self.mode_menu)
        toolbar_layout.addWidget(self.mode_btn)
        toolbar_layout.addStretch()

        self.status_label = QLabel("Backend: checking")
        self.status_label.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; background: transparent; border: none;",
        )
        self.status_label.setToolTip("Backend and local model status")
        self.status_label.setVisible(False)
        toolbar_layout.addWidget(self.status_label)

        header_layout.addLayout(toolbar_layout)
        parent_layout.addWidget(header)

    def _build_empty_state(self) -> QFrame:
        """Build the initial guidance panel shown before conversation starts."""
        empty = QFrame()
        empty.setObjectName("AssistantEmptyState")
        empty.setStyleSheet(EMPTY_STATE_STYLE)
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(14, 14, 14, 14)
        empty_layout.setSpacing(8)

        self.empty_state_title = QLabel("Load EEG files to begin")
        self.empty_state_title.setObjectName("AssistantEmptyTitle")
        self.empty_state_title.setStyleSheet(EMPTY_STATE_TITLE_STYLE)
        empty_layout.addWidget(self.empty_state_title)

        intro = QLabel(
            "Ask the assistant to inspect workflow state, explain blocked steps, "
            "or guide data import, preprocessing, epoching, dataset creation, and "
            "training."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(EMPTY_STATE_TEXT_STYLE)
        empty_layout.addWidget(intro)

        self.empty_state_backend_label = QLabel("Workflow: checking")
        self.empty_state_backend_label.setStyleSheet(EMPTY_STATE_TEXT_STYLE)
        self.empty_state_backend_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_state_backend_label)

        self.empty_state_model_label = QLabel("Assistant runtime: checking")
        self.empty_state_model_label.setStyleSheet(EMPTY_STATE_TEXT_STYLE)
        self.empty_state_model_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_state_model_label)

        self.empty_state_next_label = QLabel(
            "Available next steps: waiting for workflow diagnostics."
        )
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
            gemini_enabled = config.gemini_enabled
            active_mode = LLMConfig.assistant_runtime_selection_from(
                config
            ).ui_active_mode
        except Exception:
            logger.debug("Failed to load LLM config for model menu", exc_info=True)
            local_enabled = True
            local_runtime_ready = True
            local_runtime_message = "Local runtime unavailable."
            gemini_enabled = False
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

        if gemini_enabled:
            gemini_action = QAction("Gemini (Remote)", self)
            gemini_action.triggered.connect(
                lambda checked, action=gemini_action: self._set_model(
                    "gemini",
                    action.text(),
                )
            )
            self.model_menu.addAction(gemini_action)

        local_label = (
            "Local model (CPU fallback)"
            if local_runtime_ready and local_runtime_message != "Local runtime ready."
            else "Local model"
        )
        label = (
            "Gemini (Remote)"
            if active_mode == "gemini" and gemini_enabled
            else local_label
        )
        self.model_btn.setText(label)

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

    def _set_model(self, mode_key: str, label: str | None = None):
        """Update the selector button and emit a normalized runtime mode.

        Args:
            mode_key: Runtime backend mode identifier.
            label: Optional UI label to show on the button.

        """
        normalized_mode = LLMConfig.normalize_backend_mode(mode_key)
        button_label = (
            label
            if label is not None
            else (
                "Gemini remote model" if normalized_mode == "gemini" else "Local model"
            )
        )
        self.model_btn.setText(button_label)
        self.model_changed.emit(normalized_mode)

    def _set_execution_mode(self, mode_key: str, label: str):
        """Update the execution mode selector and emit mode change signal.

        Args:
            mode_key: The mode identifier (``'single'`` or ``'multi'``).
            label: Human-friendly label for the button text.

        """
        self.mode_btn.setText(label)
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
            self.retry_btn.setEnabled(not is_processing)
        if hasattr(self, "clear_btn"):
            self.clear_btn.setEnabled(not is_processing)

    def set_status_summary(self, text: str, tooltip: str | None = None) -> None:
        """Set the compact backend/model status line shown in the toolbar."""
        if not hasattr(self, "status_label"):
            return
        self.status_label.setText(text)
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
        """Update header chips and empty-state diagnostics."""
        stage = workflow_stage_text_label(stage)
        text = f"Backend: {stage} | {model_status}"
        self.status_label.setText(text)
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
        """Apply status text to chips and empty-state labels."""
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

        display_commands = (
            None if available_commands is None else command_labels(available_commands)
        )
        if display_commands is None:
            command_text = "Next steps: see details"
        elif available_commands:
            preview = ", ".join(display_commands[:3])
            extra_count = len(display_commands) - 3
            suffix = "" if extra_count <= 0 else f" +{extra_count}"
            command_text = f"Next steps: {preview}{suffix}"
        else:
            command_text = "Next steps: none available"

        if hasattr(self, "available_commands_chip"):
            self.available_commands_chip.setText(command_text)
            if tooltip:
                self.available_commands_chip.setToolTip(tooltip)

        if hasattr(self, "empty_state_backend_label"):
            self.empty_state_backend_label.setText(f"Workflow: {stage}")
        if hasattr(self, "empty_state_model_label"):
            self.empty_state_model_label.setText(f"Assistant runtime: {model_status}")
        if hasattr(self, "empty_state_next_label"):
            if display_commands:
                self.empty_state_next_label.setText(
                    "Available next steps: " + ", ".join(display_commands[:4])
                )
            elif blocked_reason:
                self.empty_state_next_label.setText(f"Blocked: {blocked_reason}")
            else:
                self.empty_state_next_label.setText(
                    "Available next steps: ask for current state or load EEG data."
                )

    def resizeEvent(self, event):  # noqa: N802
        """Re-adjust all bubble widths on window resize.

        Args:
            event: The ``QResizeEvent``.

        """
        super().resizeEvent(event)
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
