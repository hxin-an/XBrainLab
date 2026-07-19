"""Shared persistence and capacity limits for product chat contracts."""

from __future__ import annotations

CHAT_HISTORY_SCHEMA_VERSION = 2
MAX_CHAT_HISTORY_ROWS = 500
MIN_CHAT_TURN_HISTORY_ROWS = 2
MAX_CHAT_MESSAGE_CONTENT_LENGTH = 16_384
MAX_CHAT_ACTION_LABEL_LENGTH = 120
MAX_CHAT_ACTION_PROMPT_LENGTH = 4_096
MAX_CHAT_MESSAGE_ID_LENGTH = 128
MAX_CHAT_PRESENTATION_ID_LENGTH = 128
MAX_CHAT_ACTION_ID_LENGTH = 128
MAX_CHAT_RESPONSE_ACTIONS = 3


def bounded_chat_string(
    value: object,
    *,
    field_name: str,
    maximum_length: int,
    normalize_whitespace: bool = False,
) -> str:
    """Return one typed bounded string without allocating an oversized copy."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if len(value) > maximum_length:
        raise ValueError(f"{field_name} maximum length is {maximum_length} characters.")
    if normalize_whitespace:
        return " ".join(value.split())
    return value
