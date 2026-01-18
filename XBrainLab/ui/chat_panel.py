from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ChatPanel(QWidget):
    """
    A simple chat interface for the Agent.
    """

    send_message = pyqtSignal(str)  # Signal to send user input to MainWindow/Agent

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Chat History Display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        layout.addWidget(self.chat_display)

        # Status Label
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        # Input Area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type your instruction here...")
        self.input_field.returnPressed.connect(self.on_send)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.on_send)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

    def on_send(self):
        text = self.input_field.text().strip()
        if not text:
            return

        # Display user message
        self.append_message("User", text)
        self.input_field.clear()

        # Emit signal
        self.send_message.emit(text)
        self.set_status("Thinking...")

    def append_message(self, sender, text):
        color = "blue" if sender == "User" else "green"
        self.chat_display.append(f"<b style='color:{color}'>{sender}:</b> {text}")

    def start_agent_message(self):
        """Prepares the chat display for a new agent message."""
        self.chat_display.append("<b style='color:green'>Agent:</b> ")
        # We don't add a newline yet so chunks can be appended directly

    def on_chunk_received(self, text):
        """Appends a chunk of text to the chat display."""
        # Move cursor to end
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)

        # Insert text
        self.chat_display.insertPlainText(text)

        # Ensure scroll to bottom
        scrollbar = self.chat_display.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def set_status(self, status):
        self.status_label.setText(status)
