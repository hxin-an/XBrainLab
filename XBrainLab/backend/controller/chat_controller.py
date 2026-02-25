"""Chat controller for managing conversational AI interactions.

Provides business logic and state management for the chat window,
including message flow, history management, and UI signal coordination.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class ChatController(QObject):
    """Manages chat conversation state and coordinates UI updates.

    Handles the lifecycle of chat messages between user and agent,
    maintains conversation history, and emits Qt signals to keep
    the UI synchronised with the underlying state.

    Signals:
        message_added(str, bool): Emitted when a message is added.
            The first argument is the message text, the second indicates
            whether the sender is the user (``True``) or the agent
            (``False``).
        processing_state_changed(bool): Emitted when the processing
            state changes. ``True`` means a request is in progress.
        conversation_cleared(): Emitted when the conversation history
            is cleared.

    Attributes:
        messages: List of message dictionaries with ``role`` and
            ``content`` keys.
        is_processing: Flag indicating whether an agent request is
            currently being processed.

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
        """Add a user message and notify the UI.

        Args:
            text: The message content from the user.

        """
        self.messages.append({"role": "user", "content": text})
        self.message_added.emit(text, True)

    def add_agent_message(self, text: str):
        """Add an agent response and notify the UI.

        Args:
            text: The response content from the agent.

        """
        self.messages.append({"role": "assistant", "content": text})
        self.message_added.emit(text, False)

    def clear_conversation(self):
        """Clear the entire conversation history and notify the UI."""
        self.messages.clear()
        self.conversation_cleared.emit()

    def set_processing(self, state: bool):
        """Set the processing state and emit a state-change signal.

        Args:
            state: ``True`` if a request is being processed,
                ``False`` otherwise.

        """
        self.is_processing = state
        self.processing_state_changed.emit(state)

    def get_history(self) -> list[dict]:
        """Return a copy of the full conversation history.

        Returns:
            A list of message dictionaries, each containing ``role``
            (``"user"`` or ``"assistant"``) and ``content`` keys.

        """
        return list(self.messages)
