"""
Chat Panel - Main chat interface component.
Copilot-style chat interface using MessageBubble widgets.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .chat_styles import (
    CONTROL_PANEL_STYLE,
    DROPDOWN_MENU_STYLE,
    INPUT_FIELD_STYLE,
    SCROLL_AREA_STYLE,
    SEND_BUTTON_PROCESSING_STYLE,
    SEND_BUTTON_STYLE,
    TOOLBAR_BUTTON_STYLE,
)
from .message_bubble import MessageBubble


class ChatPanel(QWidget):
    """
    Copilot-style chat interface using MessageBubble widgets.
    Features: QFrame Bubbles, Perfect Alignment, Dynamic Width Adjustment.
    """

    send_message = pyqtSignal(str)
    stop_generation = pyqtSignal()
    model_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.is_processing = False
        self.message_list: list[MessageBubble] = []
        self.current_agent_bubble: MessageBubble | None = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Chat Display (Scroll Area) ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setStyleSheet(SCROLL_AREA_STYLE)

        # Container Widget inside ScrollArea
        self.chat_content_widget = QWidget()
        self.chat_content_widget.setStyleSheet("background-color: #1e1e1e;")
        self.chat_layout = QVBoxLayout(self.chat_content_widget)
        self.chat_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch()  # Push messages to top

        self.scroll_area.setWidget(self.chat_content_widget)
        layout.addWidget(self.scroll_area)

        # --- Control Panel (Bottom) ---
        control_panel = QWidget()
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

        # Feature Selector
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
        self.model_btn = QPushButton("Gemini 2.0 Flash ▼")
        self.model_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.model_btn.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        self.model_menu = QMenu(self)
        self.model_menu.setStyleSheet(DROPDOWN_MENU_STYLE)
        for model in ["Gemini 2.0 Flash", "Gemini 1.5 Pro", "Local (Qwen)"]:
            action = QAction(model, self)
            action.triggered.connect(lambda checked, m=model: self._set_model(m))
            self.model_menu.addAction(action)
        self.model_btn.setMenu(self.model_menu)
        toolbar_layout.addWidget(self.model_btn)

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
        self.send_btn.setText("▶")
        self.send_btn.setFixedSize(36, 36)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_send)
        self.send_btn.setStyleSheet(SEND_BUTTON_STYLE)
        input_layout.addWidget(self.send_btn)

        control_layout.addWidget(input_widget)
        layout.addWidget(control_panel)

    def _set_feature(self, feature_name: str):
        self.feature_btn.setText(f"{feature_name} ▼")

    def _set_model(self, model_name: str):
        self.model_btn.setText(f"{model_name} ▼")
        self.model_changed.emit(model_name)

    def _on_send(self):
        if self.is_processing:
            self.stop_generation.emit()
            self.set_processing_state(False)
            return

        text = self.input_field.text().strip()
        if not text:
            return

        self.add_message(text, is_user=True)
        self.input_field.clear()
        self.send_message.emit(text)
        self.set_processing_state(True)

    def set_processing_state(self, is_processing: bool):
        self.is_processing = is_processing
        if is_processing:
            self.send_btn.setText("■")
            self.send_btn.setStyleSheet(SEND_BUTTON_PROCESSING_STYLE)
        else:
            self.send_btn.setText("▶")
            self.send_btn.setStyleSheet(SEND_BUTTON_STYLE)

    def resizeEvent(self, event):  # noqa: N802
        # Update all bubble widths on window resize.
        super().resizeEvent(event)
        viewport = self.scroll_area.viewport()
        if viewport:
            container_width = viewport.width()
            for bubble in self.message_list:
                bubble.adjust_width(container_width)

    def add_message(self, text: str, is_user: bool = False):
        """Add a new message bubble to the chat."""
        bubble = MessageBubble(text, is_user)
        viewport = self.scroll_area.viewport()
        if viewport:
            bubble.adjust_width(viewport.width())

        # Insert before the stretch at the end
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self.message_list.append(bubble)
        self._scroll_to_bottom()

    def start_agent_message(self):
        """Create a new Agent bubble for streaming."""
        self.current_agent_bubble = MessageBubble("", is_user=False)
        viewport = self.scroll_area.viewport()
        if viewport:
            self.current_agent_bubble.adjust_width(viewport.width())

        self.chat_layout.insertWidget(
            self.chat_layout.count() - 1, self.current_agent_bubble
        )
        self.message_list.append(self.current_agent_bubble)
        self._scroll_to_bottom()

    def on_chunk_received(self, text: str):
        """Handle streaming text chunk."""
        if self.current_agent_bubble:
            current_text = self.current_agent_bubble.get_text()
            new_text = current_text + text
            # Strip trailing newlines to prevent bottom gap
            self.current_agent_bubble.set_text(new_text.rstrip("\n"))
            # Recalculate width after text changes
            viewport = self.scroll_area.viewport()
            if viewport:
                self.current_agent_bubble.adjust_width(viewport.width())
            self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        scroll_bar = self.scroll_area.verticalScrollBar()
        if scroll_bar:
            scroll_bar.setValue(scroll_bar.maximum())

    def append_message(self, sender: str, text: str):
        """Legacy method for compatibility - adds message with sender prefix."""
        is_user = sender.lower() == "user"
        self.add_message(text, is_user=is_user)

    def collapse_agent_message(self, text_to_remove: str):
        """Replace tool JSON with a simple indicator."""
        if self.current_agent_bubble:
            current_text = self.current_agent_bubble.get_text()
            if text_to_remove in current_text:
                new_text = current_text.replace(text_to_remove, "\n[🛠️ Tool Executed]")
                self.current_agent_bubble.set_text(new_text)

    # Legacy compatibility
    @property
    def current_agent_label(self):
        """Legacy property for compatibility."""
        if self.current_agent_bubble:
            return self.current_agent_bubble.text_label
        return None

    def set_status(self, status: str):
        """Legacy method - no-op for now."""
