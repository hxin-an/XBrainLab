from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QVBoxLayout


class CardWidget(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("CardWidget")
        self.init_ui(title)

    def init_ui(self, title):
        # Main Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # Title
        if title:
            self.title_label = QLabel(title)
            self.title_label.setObjectName("CardTitle")
            self.layout.addWidget(self.title_label)

        # Content Layout (Publicly accessible)
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(10)
        self.layout.addLayout(self.content_layout)

        # Add Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)
