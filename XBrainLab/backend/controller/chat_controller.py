from PyQt6.QtCore import QObject, pyqtSignal


class ChatController(QObject):
    """
    Manages the business logic and state of the chat window.
    Responsible for handling message flow, history management, and UI updates.
    """

    # Signals
    # text, is_user
    message_added = pyqtSignal(str, bool)

    # is_processing
    processing_state_changed = pyqtSignal(bool)

    # signal to clear UI
    conversation_cleared = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.messages: list[dict] = []
        self.is_processing = False

    def add_user_message(self, text: str):
        """Adds a user message and notifies the UI."""
        self.messages.append({"role": "user", "content": text})
        self.message_added.emit(text, True)

    def add_agent_message(self, text: str):
        """Adds an Agent response and notifies the UI."""
        self.messages.append({"role": "assistant", "content": text})
        self.message_added.emit(text, False)

    def clear_conversation(self):
        """Clears the conversation history."""
        self.messages.clear()
        self.conversation_cleared.emit()

    def set_processing(self, state: bool):
        """Sets the processing state."""
        self.is_processing = state
        self.processing_state_changed.emit(state)

    def get_history(self) -> list[dict]:
        """Returns the full conversation history."""
        return self.messages
