"""Conversation history management with sliding window truncation.

Encapsulates the message list and pruning logic previously embedded
in :class:`LLMController`.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


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

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def get_messages(self) -> list[dict[str, Any]]:
        """Return a shallow copy of the message list."""
        return list(self.messages)

    def __len__(self) -> int:
        return len(self.messages)

    def __getitem__(self, index):
        return self.messages[index]

    __hash__ = None  # mutable container — unhashable

    def __eq__(self, other):
        if isinstance(other, list):
            return self.messages == other
        if isinstance(other, ConversationHistory):
            return self.messages == other.messages
        return NotImplemented

    def __repr__(self) -> str:
        return f"ConversationHistory({len(self.messages)} msgs, max={self.max_size})"
