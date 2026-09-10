"""Conversation history management with sliding window truncation.

Encapsulates the message list and pruning logic previously embedded
in :class:`LLMController`.
"""

from __future__ import annotations

from typing import Any


class ConversationHistory:
    """Manages a bounded conversation history with sliding-window truncation.

    Maintains a list of ``{"role": str, "content": str}`` message dicts
    and automatically prunes to the most recent *max_size* entries when
    the limit is exceeded.

    Attributes:
        messages: List of message dictionaries.
        max_size: Maximum number of messages to retain.

    """

    def __init__(self, max_size: int = 20) -> None:
        self.messages: list[dict[str, Any]] = []
        self.max_size = max_size

    def append(self, role: str, content: str) -> None:
        """Append a message and prune if over the sliding window limit.

        Args:
            role: Message role (``'user'``, ``'assistant'``, or ``'system'``).
            content: The message text.

        """
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self.max_size:
            self.messages = self.messages[-self.max_size :]

    def clear(self) -> None:
        """Remove all messages from history."""
        self.messages.clear()
