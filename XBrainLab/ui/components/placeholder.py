from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderWidget(QWidget):
    def __init__(self, icon_text, message, parent=None):
        super().__init__(parent)
        self.init_ui(icon_text, message)

    def init_ui(self, icon_text, message):
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
