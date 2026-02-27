"""Chat Panel - Main chat interface component.

Provides the ``ChatPanel`` widget implementing a Copilot-style chat interface
using ``MessageBubble`` widgets. Handles user input, model/feature selection,
streaming responses, and debug-mode interception.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,  # Added for M3.1
    QHBoxLayout,
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

from ..styles.theme import Theme
from .message_bubble import MessageBubble
from .styles import (
    CONTROL_PANEL_STYLE,
    DROPDOWN_MENU_STYLE,
    INPUT_FIELD_STYLE,
    SCROLL_AREA_STYLE,
    SEND_BUTTON_PROCESSING_STYLE,
    SEND_BUTTON_STYLE,
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
    debug_tool_requested = pyqtSignal(str, dict)  # M3.1 Debug Mode

    def __init__(self):
        """Initialize the ChatPanel with UI components and optional debug mode."""
        super().__init__()
        # Temporary state for current streaming bubble
        self.current_agent_bubble: MessageBubble | None = None

        self.is_processing = False
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

        # --- Chat Display (Scroll Area) ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.scroll_area.setStyleSheet(SCROLL_AREA_STYLE)

        # Container Widget inside ScrollArea
        self.chat_content_widget = QWidget()
        self.chat_content_widget.setStyleSheet(
            f"background-color: {Theme.BACKGROUND_DARK};",
        )
        self.chat_layout = QVBoxLayout(self.chat_content_widget)
        self.chat_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch()  # Push messages to top

        self.scroll_area.setWidget(self.chat_content_widget)
        layout.addWidget(self.scroll_area)

        # --- Control Panel (Bottom) ---
        control_panel = QWidget()
        control_panel.setObjectName("ControlPanel")
        control_panel.setStyleSheet(CONTROL_PANEL_STYLE)
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(10, 8, 10, 8)
        control_layout.setSpacing(5)

        # Row 1: Toolbar (Dropdowns)
        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet("background: transparent; border: none;")
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(10)

        # Feature Selector (Keep logic, maybe move to Backend later)
        self.feature_btn = QPushButton("General Assistant ▼")
        self.feature_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.feature_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        self.feature_menu = QMenu(self)
        self.feature_menu.setStyleSheet(DROPDOWN_MENU_STYLE)
        for feat in ["General Assistant", "EEG Analyst", "Coder"]:
            action = QAction(feat, self)
            action.triggered.connect(lambda checked, f=feat: self._set_feature(f))
            self.feature_menu.addAction(action)
        self.feature_btn.setMenu(self.feature_menu)
        toolbar_layout.addWidget(self.feature_btn)

        # Model Selector
        self.model_btn = QPushButton("Model: Gemini ▼")
        self.model_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.model_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)

        self.model_menu = QMenu(self)
        self.model_menu.setStyleSheet(DROPDOWN_MENU_STYLE)
        self.model_btn.setMenu(self.model_menu)

        # Initial population of menu
        self.update_model_menu()

        toolbar_layout.addWidget(self.model_btn)

        # Execution Mode Selector
        self.mode_btn = QPushButton("Single ▼")
        self.mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        self.mode_btn.setToolTip(
            "Single: stop after each tool success\n"
            "Multi: auto-continue until done or limit reached"
        )
        self.mode_menu = QMenu(self)
        self.mode_menu.setStyleSheet(DROPDOWN_MENU_STYLE)
        for mode_label, mode_key in [("Single", "single"), ("Multi", "multi")]:
            action = QAction(mode_label, self)
            action.triggered.connect(
                lambda checked, m=mode_key, lbl=mode_label: self._set_execution_mode(
                    m, lbl
                )
            )
            self.mode_menu.addAction(action)
        self.mode_btn.setMenu(self.mode_menu)
        toolbar_layout.addWidget(self.mode_btn)

        toolbar_layout.addStretch()  # Push buttons to left
        control_layout.addWidget(toolbar_widget)

        # Row 2: Input Field and Send Button
        input_widget = QWidget()
        input_widget.setStyleSheet("background: transparent; border: none;")
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(10, 5, 10, 10)
        input_layout.setSpacing(10)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask XBrainLab...")
        self.input_field.setStyleSheet(INPUT_FIELD_STYLE)
        self.input_field.returnPressed.connect(self._on_send)
        input_layout.addWidget(self.input_field, 1)

        self.send_btn = QToolButton()
        self.send_btn.setText("➤")
        self.send_btn.setFixedSize(36, 36)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_send)
        self.send_btn.setStyleSheet(SEND_BUTTON_STYLE)
        input_layout.addWidget(self.send_btn)

        control_layout.addWidget(input_widget)
        layout.addWidget(control_panel)

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
        except Exception:
            logger.debug("Failed to load LLM config for model menu", exc_info=True)
            local_enabled = True

        modes = ["Gemini", "Local"]
        for mode in modes:
            action = QAction(mode, self)

            # Feature: Disable Local selection if disabled in settings
            if mode == "Local" and not local_enabled:
                action.setEnabled(False)
                action.setText("Local (Disabled)")
                action.setToolTip("Enable Local Model in Settings (⚙) to use.")
            else:
                action.triggered.connect(lambda checked, m=mode: self._set_model(m))

            self.model_menu.addAction(action)

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
        self.feature_btn.setText(f"{feature_name} ▼")

    def _set_model(self, model_name: str):
        """Update the model selector button and emit model change signal.

        Args:
            model_name: The selected model name.

        """
        self.model_btn.setText(f"{model_name} ▼")
        self.model_changed.emit(model_name)

    def _set_execution_mode(self, mode_key: str, label: str):
        """Update the execution mode selector and emit mode change signal.

        Args:
            mode_key: The mode identifier (``'single'`` or ``'multi'``).
            label: Human-friendly label for the button text.

        """
        self.mode_btn.setText(f"{label} ▼")
        self.execution_mode_changed.emit(mode_key)

    def _on_new_conversation(self):
        """Emit the new conversation requested signal."""
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
            self.send_btn.setText("■")  # Pure text square, no emoji background
            self.send_btn.setStyleSheet(SEND_BUTTON_PROCESSING_STYLE)
        else:
            self.send_btn.setText("➤")
            self.send_btn.setStyleSheet(SEND_BUTTON_STYLE)

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
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()

        if not is_user:
            # Keep track of agent bubble for streaming updates if needed
            self.current_agent_bubble = bubble

    def _clear_ui(self):
        """Remove all message bubbles from the chat layout."""
        # Remove all widgets except stretch
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()
        self.current_agent_bubble = None

    def on_chunk_received(self, text: str):
        """Handle a streaming text chunk from the agent.

        Appends the chunk to the current agent bubble, creating one
        if necessary, and triggers width recalculation.

        Args:
            text: The incremental text chunk to append.

        """
        # Feature: Auto-create bubble if missing (Robustness)
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
