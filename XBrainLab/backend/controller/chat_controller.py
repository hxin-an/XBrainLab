"""Typed conversation history and UI synchronization for the chat panel."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import QObject, pyqtSignal

from XBrainLab.chat_contract import (
    CHAT_HISTORY_LIVE_WINDOW_ROWS,
    CHAT_HISTORY_SCHEMA_VERSION,
    MAX_CHAT_HISTORY_ROWS,
    MAX_CHAT_MESSAGE_CONTENT_LENGTH,
    MAX_CHAT_MESSAGE_ID_LENGTH,
    MAX_CHAT_PRESENTATION_ROWS_PER_TURN,
    MIN_CHAT_TURN_HISTORY_ROWS,
    bounded_chat_string,
)


def _is_json_like(value: object) -> bool:
    """Return whether a persistence value can be represented by JSON."""
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_json_like(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _is_json_like(item) for key, item in value.items()
        )
    return False


class ChatMessageRole(str, Enum):
    """Supported product transcript roles."""

    USER = "user"
    ASSISTANT = "assistant"


class ChatMessagePresentationKind(str, Enum):
    """Persisted visual meaning of one transcript message."""

    USER = "user"
    ASSISTANT = "assistant"
    CLARIFICATION = "clarification"
    ATTENTION = "attention"
    ERROR = "error"
    TOOL_RESULT = "tool_result"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ChatMessageRecord:
    """Immutable transcript record used by rendering and persistence."""

    role: ChatMessageRole
    content: str
    presentation_kind: ChatMessagePresentationKind
    message_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, ChatMessageRole):
            raise TypeError("Chat message role must be typed.")
        if not isinstance(self.presentation_kind, ChatMessagePresentationKind):
            raise TypeError("Chat message presentation kind must be typed.")
        object.__setattr__(
            self,
            "content",
            bounded_chat_string(
                self.content,
                field_name="Chat message content",
                maximum_length=MAX_CHAT_MESSAGE_CONTENT_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "message_id",
            bounded_chat_string(
                self.message_id,
                field_name="Chat message id",
                maximum_length=MAX_CHAT_MESSAGE_ID_LENGTH,
            ),
        )
        if not self.message_id.strip():
            raise ValueError("Chat message id cannot be empty.")
        if self.role is ChatMessageRole.USER:
            if self.presentation_kind is not ChatMessagePresentationKind.USER:
                raise ValueError("User messages require the user presentation kind.")
        elif self.presentation_kind is ChatMessagePresentationKind.USER:
            raise ValueError(
                "Assistant messages cannot use the user presentation kind."
            )

    def to_history_dict(self) -> dict[str, Any]:
        """Return the versioned JSON-safe persistence payload."""
        return {
            "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
            "role": self.role.value,
            "content": self.content,
            "presentation_kind": self.presentation_kind.value,
            "message_id": self.message_id,
        }

    @classmethod
    def from_history_value(cls, value: object) -> ChatMessageRecord | None:
        """Parse current or legacy history without classifying message text."""
        if not isinstance(value, Mapping) or not _is_json_like(value):
            return None
        raw_schema = value.get("schema_version")
        content = value.get("content")
        role_value = value.get("role")
        if not isinstance(content, str) or not isinstance(role_value, str):
            return None
        try:
            role = ChatMessageRole(role_value)
        except ValueError:
            return None
        default_kind = (
            ChatMessagePresentationKind.USER
            if role is ChatMessageRole.USER
            else ChatMessagePresentationKind.ASSISTANT
        )
        if raw_schema is None:
            try:
                return cls(
                    role=role,
                    content=content,
                    presentation_kind=default_kind,
                    message_id=uuid4().hex,
                )
            except (TypeError, ValueError):
                return None
        if (
            isinstance(raw_schema, bool)
            or not isinstance(raw_schema, int)
            or raw_schema != CHAT_HISTORY_SCHEMA_VERSION
        ):
            return None
        kind_value = value.get("presentation_kind", default_kind.value)
        if not isinstance(kind_value, str):
            return None
        try:
            presentation_kind = ChatMessagePresentationKind(kind_value)
        except ValueError:
            return None
        if (
            role is ChatMessageRole.USER
            and presentation_kind is not ChatMessagePresentationKind.USER
        ):
            return None

        message_id_value = value.get("message_id", "")
        if not isinstance(message_id_value, str):
            return None
        if not message_id_value:
            return None
        try:
            return cls(
                role=role,
                content=content,
                presentation_kind=presentation_kind,
                message_id=message_id_value,
            )
        except (TypeError, ValueError):
            return None


class ChatHistoryReplacementKind(str, Enum):
    """Reason one immutable transcript snapshot replaced visible history."""

    PRUNE = "prune"
    RESTORE = "restore"
    CLEAR = "clear"


@dataclass(frozen=True, slots=True)
class ChatHistoryReplacement:
    """One atomic transcript replacement published before subsequent deltas."""

    kind: ChatHistoryReplacementKind
    records: tuple[ChatMessageRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ChatHistoryReplacementKind):
            raise TypeError("Chat history replacement kind must be typed.")
        if not isinstance(self.records, tuple) or not all(
            isinstance(record, ChatMessageRecord) for record in self.records
        ):
            raise TypeError("Chat history replacements require a typed tuple.")
        if len({record.message_id for record in self.records}) != len(self.records):
            raise ValueError("Chat history replacement message ids must be unique.")


class ChatController(QObject):
    """Own typed transcript history while preserving the legacy text view."""

    message_added = pyqtSignal(str, bool)
    message_record_added = pyqtSignal(object)
    message_record_updated = pyqtSignal(object)
    history_replaced = pyqtSignal(object)
    processing_state_changed = pyqtSignal(bool)
    conversation_cleared = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.messages: list[dict[str, str]] = []
        self._history_records: list[ChatMessageRecord] = []
        self._pruned_row_count = 0
        self._remaining_prepared_presentation_rows: int | None = None
        self._history_replacement_depth = 0
        self._deferred_history_notifications: list[tuple[str, ChatMessageRecord]] = []
        self.is_processing = False

    def add_user_message(self, text: str) -> ChatMessageRecord:
        """Add one user message."""
        record = ChatMessageRecord(
            role=ChatMessageRole.USER,
            content=text,
            presentation_kind=ChatMessagePresentationKind.USER,
            message_id=uuid4().hex,
        )
        self._append_record_transaction(record)
        return record

    def add_agent_message(
        self,
        text: str,
        *,
        presentation_kind: ChatMessagePresentationKind = (
            ChatMessagePresentationKind.ASSISTANT
        ),
    ) -> ChatMessageRecord:
        """Add one explicitly typed assistant presentation."""
        if not isinstance(presentation_kind, ChatMessagePresentationKind):
            raise TypeError("Agent messages require a typed presentation kind.")
        if presentation_kind is ChatMessagePresentationKind.USER:
            raise ValueError("Agent messages cannot use the user presentation kind.")
        record = ChatMessageRecord(
            role=ChatMessageRole.ASSISTANT,
            content=text,
            presentation_kind=presentation_kind,
            message_id=uuid4().hex,
        )
        reserved = self._reserve_prepared_presentation_capacity()
        try:
            self._append_record_transaction(record)
        except Exception:
            if reserved and not any(item is record for item in self._history_records):
                self._rollback_prepared_presentation_reservation()
            raise
        return record

    def _require_history_capacity(self) -> None:
        if len(self._history_records) >= MAX_CHAT_HISTORY_ROWS:
            raise ValueError(
                f"Chat history may contain at most {MAX_CHAT_HISTORY_ROWS} rows."
            )

    def _require_prepared_presentation_capacity(self) -> None:
        remaining = self._remaining_prepared_presentation_rows
        if remaining is not None and remaining <= 0:
            raise ValueError(
                "An admitted chat turn may contain at most "
                f"{MAX_CHAT_PRESENTATION_ROWS_PER_TURN} presentation rows."
            )

    def _reserve_prepared_presentation_capacity(self) -> bool:
        """Reserve one row before any synchronous transcript signal can re-enter."""
        self._require_prepared_presentation_capacity()
        if self._remaining_prepared_presentation_rows is None:
            return False
        self._remaining_prepared_presentation_rows -= 1
        return True

    def _rollback_prepared_presentation_reservation(self) -> None:
        """Return one reservation when its record never reached live history."""
        if self._remaining_prepared_presentation_rows is not None:
            self._remaining_prepared_presentation_rows += 1

    def can_accept_turn(self) -> bool:
        """Return whether one full admitted turn can be stored without pruning."""
        return (
            len(self._history_records) + MIN_CHAT_TURN_HISTORY_ROWS
            <= MAX_CHAT_HISTORY_ROWS
        )

    def prepare_for_turn(self) -> int:
        """Prune the oldest live rows at a user-turn boundary when needed.

        Workflow truth is rebuilt from the current Application publication on
        every turn, so old transcript prose must not become a second state
        store. The controller retains a generous recent window for the user
        while preventing a long session from hard-blocking new requests.
        """
        self._require_history_replacement_idle()
        if self.can_accept_turn():
            self._remaining_prepared_presentation_rows = (
                MAX_CHAT_PRESENTATION_ROWS_PER_TURN
            )
            return 0

        prune_count = max(
            1,
            len(self._history_records) - CHAT_HISTORY_LIVE_WINDOW_ROWS,
        )
        while (
            prune_count < len(self._history_records)
            and self._history_records[prune_count].role is ChatMessageRole.ASSISTANT
        ):
            prune_count += 1

        self._history_records = self._history_records[prune_count:]
        self.messages = [
            {"role": record.role.value, "content": record.content}
            for record in self._history_records
        ]
        self._pruned_row_count += prune_count
        self._remaining_prepared_presentation_rows = MAX_CHAT_PRESENTATION_ROWS_PER_TURN
        self._publish_history_replacement(
            ChatHistoryReplacement(
                kind=ChatHistoryReplacementKind.PRUNE,
                records=tuple(self._history_records),
            )
        )
        return prune_count

    @property
    def pruned_row_count(self) -> int:
        """Return rows removed from the live transcript in this conversation."""
        return self._pruned_row_count

    def _require_record_appendable(self, record: ChatMessageRecord) -> None:
        """Validate an append before canonical history is mutated."""
        self._require_history_capacity()
        if any(item.message_id == record.message_id for item in self._history_records):
            raise ValueError("Chat message ids must be unique.")

    def _append_record_transaction(self, record: ChatMessageRecord) -> None:
        """Commit one append before publishing UI signals."""
        self._require_record_appendable(record)
        history_before = list(self._history_records)
        messages_before = list(self.messages)
        try:
            self._append_record(record, emit=False)
        except Exception:
            self._history_records = history_before
            self.messages = messages_before
            raise

        self._emit_record_added(record)

    def _append_record(self, record: ChatMessageRecord, *, emit: bool = True) -> None:
        self._require_record_appendable(record)
        self._history_records.append(record)
        legacy = {"role": record.role.value, "content": record.content}
        self.messages.append(legacy)
        if emit:
            self._emit_record_added(record)

    def _emit_record_added(self, record: ChatMessageRecord) -> None:
        """Publish one committed record to typed and legacy UI consumers."""
        if self._history_replacement_depth:
            self._deferred_history_notifications.append(("added", record))
            return
        self._publish_record_added(record)

    def _publish_record_added(self, record: ChatMessageRecord) -> None:
        """Emit one record immediately after replay ordering has been resolved."""
        self.message_record_added.emit(record)
        self.message_added.emit(
            record.content,
            record.role is ChatMessageRole.USER,
        )

    def _emit_record_updated(self, record: ChatMessageRecord) -> None:
        """Publish or defer an update until an atomic replacement is visible."""
        if self._history_replacement_depth:
            self._deferred_history_notifications.append(("updated", record))
            return
        self.message_record_updated.emit(record)

    def _publish_history_replacement(
        self,
        replacement: ChatHistoryReplacement,
        *,
        emit_legacy_clear: bool = False,
    ) -> None:
        """Publish one snapshot, then drain reentrant record deltas in FIFO order."""
        if not isinstance(replacement, ChatHistoryReplacement):
            raise TypeError("Chat history replacement must be typed.")
        self._require_history_replacement_idle()
        self._history_replacement_depth = 1
        self._deferred_history_notifications.clear()
        try:
            self.history_replaced.emit(replacement)
            if emit_legacy_clear:
                self.conversation_cleared.emit()

            notification_index = 0
            while notification_index < len(self._deferred_history_notifications):
                kind, record = self._deferred_history_notifications[notification_index]
                notification_index += 1
                if kind == "updated":
                    self.message_record_updated.emit(record)
                else:
                    self._publish_record_added(record)
        finally:
            self._deferred_history_notifications.clear()
            self._history_replacement_depth = 0

    def _require_history_replacement_idle(self) -> None:
        """Reject a second replacement before it can mutate canonical history."""
        if self._history_replacement_depth:
            raise RuntimeError("Chat history replacement cannot be nested.")

    def clear_conversation(self) -> None:
        """Clear the entire conversation history and notify the UI."""
        self._require_history_replacement_idle()
        self.messages.clear()
        self._history_records.clear()
        self._pruned_row_count = 0
        self._remaining_prepared_presentation_rows = None
        self._publish_history_replacement(
            ChatHistoryReplacement(
                kind=ChatHistoryReplacementKind.CLEAR,
                records=(),
            ),
            emit_legacy_clear=True,
        )

    def set_processing(self, state: bool) -> None:
        """Publish the legacy busy flag; typed cancelability is owned by the UI host."""
        self.is_processing = bool(state)
        self.processing_state_changed.emit(self.is_processing)

    def get_typed_history(self) -> tuple[ChatMessageRecord, ...]:
        """Return immutable typed records for UI restore."""
        return tuple(self._history_records)

    def get_history(self) -> list[dict[str, Any]]:
        """Return versioned JSON-safe history for persistence."""
        return [record.to_history_dict() for record in self._history_records]

    def restore_history(self, history: Iterable[object]) -> int:
        """Atomically replace history only when every persisted row is valid."""
        self._require_history_replacement_idle()
        if isinstance(history, (str, bytes, Mapping)):
            return 0
        parsed: list[ChatMessageRecord] = []
        message_ids: set[str] = set()
        try:
            for value in history:
                if len(parsed) >= MAX_CHAT_HISTORY_ROWS:
                    return 0
                record = ChatMessageRecord.from_history_value(value)
                if record is None:
                    return 0
                if record.message_id in message_ids:
                    return 0
                parsed.append(record)
                message_ids.add(record.message_id)
        except Exception:
            return 0

        self._history_records = parsed
        self._pruned_row_count = 0
        self._remaining_prepared_presentation_rows = None
        self.messages = [
            {"role": record.role.value, "content": record.content} for record in parsed
        ]
        restored_records = tuple(parsed)
        self._publish_history_replacement(
            ChatHistoryReplacement(
                kind=ChatHistoryReplacementKind.RESTORE,
                records=restored_records,
            )
        )
        return len(restored_records)
