"""Placeholder widget displaying a centered icon and message."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderWidget(QWidget):
    """A centered placeholder widget with a large icon and descriptive message.

    Used to indicate empty or uninitialized content areas.

    Attributes:
        icon_label: QLabel displaying the icon text (emoji or character).
        msg_label: QLabel displaying the descriptive message.

    """

    def __init__(self, icon_text, message, parent=None):
        """Initialize the placeholder widget.

        Args:
            icon_text: Large text or emoji to display as the icon.
            message: Descriptive message displayed below the icon.
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self.init_ui(icon_text, message)

    def init_ui(self, icon_text, message):
        """Build the centered icon and message layout.

        Args:
            icon_text: Large text or emoji for the icon label.
            message: Descriptive text for the message label.

        """
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icon Label (Large Emoji/Text)
        self.icon_label = QLabel(icon_text)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 64px; color: #555;")
        layout.addWidget(self.icon_label)

        # Message Label
        self.msg_label = QLabel(message)
        self.msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_label.setStyleSheet("font-size: 16px; color: #888; font-weight: bold;")
        layout.addWidget(self.msg_label)
