"""Card widget component providing a styled container with shadow effect."""

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QVBoxLayout


class CardWidget(QFrame):
    """A styled card container with title, content area, and drop shadow.

    Provides a reusable framed widget with an optional title label,
    a content layout for child widgets, and a subtle drop shadow effect.

    Attributes:
        main_layout: The top-level QVBoxLayout of the card.
        title_label: QLabel displaying the card title (if provided).
        content_layout: QVBoxLayout where child widgets should be added.
    """

    def __init__(self, title, parent=None):
        """Initialize the card widget.

        Args:
            title: The card title text. Pass ``None`` or empty string
                to omit the title label.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("CardWidget")
        self.init_ui(title)

    def init_ui(self, title):
        """Build the card layout with title and content area.

        Args:
            title: The card title text.
        """
        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # Title
        if title:
            self.title_label = QLabel(title)
            self.title_label.setObjectName("CardTitle")
            self.main_layout.addWidget(self.title_label)

        # Content Layout (Publicly accessible)
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(10)
        self.main_layout.addLayout(self.content_layout)

        # Add Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

    def add_widget(self, widget):
        """Add a widget to the card's content area.

        Args:
            widget: The QWidget to add.
        """
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        """Add a sub-layout to the card's content area.

        Args:
            layout: The QLayout to add.
        """
        self.content_layout.addLayout(layout)
