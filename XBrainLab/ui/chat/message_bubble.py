"""
Message Bubble Widget for Chat Panel.
Single chat message widget with dynamic width adjustment.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .chat_styles import (
    AGENT_BUBBLE_FRAME_STYLE,
    AGENT_BUBBLE_TEXT_STYLE,
    USER_BUBBLE_FRAME_STYLE,
    USER_BUBBLE_TEXT_STYLE,
)


class MessageBubble(QWidget):
    """
    A chat message bubble widget.
    Contains a QFrame (bubble container) with a QLabel (text).
    Supports dynamic width adjustment on window resize.
    """

    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.bubble_frame: QFrame | None = None
        self.text_label: QLabel | None = None
        self._init_ui(text)

    def _init_ui(self, text: str):
        # Main horizontal layout for this row
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        # Create the bubble frame
        self.bubble_frame = QFrame()
        self.bubble_frame.setObjectName("BubbleFrame")
        self.bubble_frame.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )

        # Create bubble's internal layout
        bubble_layout = QVBoxLayout(self.bubble_frame)
        bubble_layout.setContentsMargins(15, 10, 15, 10)
        bubble_layout.setSpacing(0)

        # Create the text label
        self.text_label = QLabel(text)
        self.text_label.setTextFormat(
            Qt.TextFormat.PlainText
        )  # Prevent backslash/HTML parsing issues
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        bubble_layout.addWidget(self.text_label)

        # Apply styles based on sender
        if self.is_user:
            self.bubble_frame.setStyleSheet(USER_BUBBLE_FRAME_STYLE)
            self.text_label.setStyleSheet(USER_BUBBLE_TEXT_STYLE)
            row_layout.addWidget(self.bubble_frame)
            row_layout.setAlignment(self.bubble_frame, Qt.AlignmentFlag.AlignRight)
        else:
            self.bubble_frame.setStyleSheet(AGENT_BUBBLE_FRAME_STYLE)
            self.text_label.setStyleSheet(AGENT_BUBBLE_TEXT_STYLE)
            row_layout.addWidget(self.bubble_frame)
            row_layout.setAlignment(self.bubble_frame, Qt.AlignmentFlag.AlignLeft)

    def adjust_width(self, container_width: int):
        """Adjust bubble max width to 80% of container width."""
        if container_width <= 0:
            return

        max_width = int(container_width * 0.80)
        label_max_width = max_width - 30  # Account for padding

        # Get text and calculate natural width (single line)
        if self.text_label is None:
            return
        text = self.text_label.text()
        if not text:
            # Empty text - just set max width
            if self.bubble_frame:
                self.bubble_frame.setMaximumWidth(max_width)
            self.text_label.setMaximumWidth(label_max_width)
            return

        # Calculate natural text width using font metrics
        fm = self.text_label.fontMetrics()
        natural_width = fm.horizontalAdvance(text) + 10  # Small margin

        if natural_width > label_max_width:
            # Text is longer than 80% - use fixed width to force proper wrapping
            self.text_label.setFixedWidth(label_max_width)
            if self.bubble_frame:
                self.bubble_frame.setMaximumWidth(max_width)
        else:
            # Text fits - let it be natural size
            self.text_label.setMinimumWidth(0)
            self.text_label.setMaximumWidth(label_max_width)
            if self.bubble_frame:
                self.bubble_frame.setMaximumWidth(max_width)

    def set_text(self, text: str):
        """Update the text content (for streaming)."""
        if self.text_label:
            self.text_label.setText(text)

    def get_text(self) -> str:
        """Get current text content."""
        if self.text_label:
            return self.text_label.text()
        return ""
