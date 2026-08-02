"""Typed conversation history and UI synchronization for the chat panel."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import QObject, pyqtSignal

from XBrainLab.chat_contract import (
    CHAT_HISTORY_LIVE_WINDOW_ROWS,
    CHAT_HISTORY_SCHEMA_VERSION,
    MAX_CHAT_ACTION_ID_LENGTH,
    MAX_CHAT_ACTION_LABEL_LENGTH,
    MAX_CHAT_ACTION_PROMPT_LENGTH,
    MAX_CHAT_HISTORY_ROWS,
    MAX_CHAT_MESSAGE_CONTENT_LENGTH,
    MAX_CHAT_MESSAGE_ID_LENGTH,
    MAX_CHAT_PRESENTATION_ID_LENGTH,
    MAX_CHAT_PRESENTATION_ROWS_PER_TURN,
    MAX_CHAT_RESPONSE_ACTIONS,
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


class ChatResponseActionKind(str, Enum):
    """Bounded UI behavior attached to an assistant response."""

    SEND_MESSAGE = "send_message"
    OPEN_PANEL = "open_panel"
    OPEN_DATA_IMPORT = "open_data_import"


class ChatPanelTarget(str, Enum):
    """Existing main-window destinations available to response actions."""

    DATASET = "dataset"
    PREPROCESS = "preprocess"
    TRAINING = "training"
    EVALUATION = "evaluation"
    VISUALIZATION = "visualization"


class ChatActionState(str, Enum):
    """Whether persisted response actions may still be selected."""

    NONE = "none"
    ACTIVE = "active"
    CONSUMED = "consumed"


@dataclass(frozen=True, slots=True)
class ChatResponseAction:
    """Serializable, typed action rendered below one assistant response."""

    action_id: str
    label: str
    kind: ChatResponseActionKind
    prompt: str = ""
    panel: ChatPanelTarget | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ChatResponseActionKind):
            raise TypeError("Chat response action kind must be typed.")
        if self.panel is not None and not isinstance(self.panel, ChatPanelTarget):
            raise TypeError("Chat response panel target must be typed.")
        object.__setattr__(
            self,
            "action_id",
            bounded_chat_string(
                self.action_id,
                field_name="Chat response action id",
                maximum_length=MAX_CHAT_ACTION_ID_LENGTH,
                normalize_whitespace=True,
            ),
        )
        object.__setattr__(
            self,
            "label",
            bounded_chat_string(
                self.label,
                field_name="Chat response action label",
                maximum_length=MAX_CHAT_ACTION_LABEL_LENGTH,
                normalize_whitespace=True,
            ),
        )
        object.__setattr__(
            self,
            "prompt",
            bounded_chat_string(
                self.prompt,
                field_name="Chat response action prompt",
                maximum_length=MAX_CHAT_ACTION_PROMPT_LENGTH,
                normalize_whitespace=True,
            ),
        )
        if not self.action_id or not self.label:
            raise ValueError("Chat response actions require an id and label.")
        if self.kind is ChatResponseActionKind.SEND_MESSAGE:
            if not self.prompt or self.panel is not None:
                raise ValueError("Send-message actions require only a prompt.")
        elif self.kind is ChatResponseActionKind.OPEN_PANEL and (
            not isinstance(self.panel, ChatPanelTarget) or self.prompt
        ):
            raise ValueError("Open-panel actions require only a panel target.")
        elif self.kind is ChatResponseActionKind.OPEN_DATA_IMPORT and (
            self.prompt or self.panel is not None
        ):
            raise ValueError("Open-data-import actions do not accept payload fields.")

    def to_history_dict(self) -> dict[str, str | None]:
        """Return a JSON-safe action payload."""
        return {
            "action_id": self.action_id,
            "label": self.label,
            "kind": self.kind.value,
            "prompt": self.prompt,
            "panel": self.panel.value if self.panel is not None else None,
        }

    @classmethod
    def from_history_value(cls, value: object) -> ChatResponseAction | None:
        """Safely parse one persisted action, dropping malformed legacy data."""
        if not isinstance(value, Mapping) or not _is_json_like(value):
            return None
        action_id = value.get("action_id")
        label = value.get("label")
        kind_value = value.get("kind")
        prompt = value.get("prompt", "")
        panel_value = value.get("panel")
        if (
            not isinstance(action_id, str)
            or not isinstance(label, str)
            or not isinstance(kind_value, str)
            or not isinstance(prompt, str)
        ):
            return None
        if panel_value is not None and not isinstance(panel_value, str):
            return None
        try:
            kind = ChatResponseActionKind(kind_value)
            panel = (
                ChatPanelTarget(panel_value)
                if isinstance(panel_value, str) and panel_value
                else None
            )
            return cls(
                action_id=action_id,
                label=label,
                kind=kind,
                prompt=prompt,
                panel=panel,
            )
        except (TypeError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class ChatMessageRecord:
    """Immutable transcript record used by rendering and persistence."""

    role: ChatMessageRole
    content: str
    presentation_kind: ChatMessagePresentationKind
    message_id: str
    presentation_id: str = ""
    actions: tuple[ChatResponseAction, ...] = ()
    action_state: ChatActionState = ChatActionState.NONE

    def __post_init__(self) -> None:
        if not isinstance(self.role, ChatMessageRole):
            raise TypeError("Chat message role must be typed.")
        if not isinstance(self.presentation_kind, ChatMessagePresentationKind):
            raise TypeError("Chat message presentation kind must be typed.")
        if not isinstance(self.action_state, ChatActionState):
            raise TypeError("Chat message action state must be typed.")
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
        object.__setattr__(
            self,
            "presentation_id",
            bounded_chat_string(
                self.presentation_id,
                field_name="Chat presentation id",
                maximum_length=MAX_CHAT_PRESENTATION_ID_LENGTH,
            ),
        )
        if not isinstance(self.actions, tuple) or not all(
            isinstance(action, ChatResponseAction) for action in self.actions
        ):
            raise TypeError("Chat message actions must be a typed tuple.")
        if not self.message_id.strip():
            raise ValueError("Chat message id cannot be empty.")
        if self.presentation_id and not self.presentation_id.strip():
            raise ValueError("Chat presentation id cannot be blank.")
        if len(self.actions) > MAX_CHAT_RESPONSE_ACTIONS:
            raise ValueError(
                f"Chat messages may expose at most {MAX_CHAT_RESPONSE_ACTIONS} actions."
            )
        if len({action.action_id for action in self.actions}) != len(self.actions):
            raise ValueError("Chat response action ids must be unique per message.")
        if self.role is ChatMessageRole.USER:
            if self.presentation_kind is not ChatMessagePresentationKind.USER:
                raise ValueError("User messages require the user presentation kind.")
            if (
                self.actions
                or self.presentation_id
                or self.action_state is not ChatActionState.NONE
            ):
                raise ValueError("User messages cannot expose response actions.")
        elif self.presentation_kind is ChatMessagePresentationKind.USER:
            raise ValueError(
                "Assistant messages cannot use the user presentation kind."
            )
        if self.actions:
            if not self.presentation_id:
                raise ValueError("Response actions require a presentation id.")
            if self.action_state is ChatActionState.NONE:
                raise ValueError("Response actions require active or consumed state.")
        elif self.action_state is not ChatActionState.NONE:
            raise ValueError("Messages without actions require the none action state.")

    @property
    def has_active_actions(self) -> bool:
        """Return whether the response actions are still selectable."""
        return bool(self.actions and self.action_state is ChatActionState.ACTIVE)

    def to_history_dict(self) -> dict[str, Any]:
        """Return the versioned JSON-safe persistence payload."""
        return {
            "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
            "role": self.role.value,
            "content": self.content,
            "presentation_kind": self.presentation_kind.value,
            "message_id": self.message_id,
            "presentation_id": self.presentation_id,
            "actions": [action.to_history_dict() for action in self.actions],
            "action_state": self.action_state.value,
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

        raw_actions = value.get("actions", [])
        if not isinstance(raw_actions, list):
            return None
        if len(raw_actions) > MAX_CHAT_RESPONSE_ACTIONS:
            return None
        if role is ChatMessageRole.USER and raw_actions:
            return None
        parsed_action_values = [
            ChatResponseAction.from_history_value(action) for action in raw_actions
        ]
        if any(action is None for action in parsed_action_values):
            return None
        parsed_actions = tuple(
            action for action in parsed_action_values if action is not None
        )
        presentation_id_value = value.get("presentation_id", "")
        if not isinstance(presentation_id_value, str):
            return None
        presentation_id = presentation_id_value
        try:
            action_state_value = value.get("action_state", "none")
            if not isinstance(action_state_value, str):
                return None
            action_state = ChatActionState(action_state_value)
        except ValueError:
            return None
        if parsed_actions and (
            not presentation_id or action_state is ChatActionState.NONE
        ):
            return None
        if not parsed_actions:
            if action_state is not ChatActionState.NONE:
                return None
            action_state = ChatActionState.NONE
            presentation_id = ""

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
                presentation_id=presentation_id,
                actions=parsed_actions,
                action_state=action_state,
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
        presentation_ids = tuple(
            record.presentation_id for record in self.records if record.presentation_id
        )
        if len(set(presentation_ids)) != len(presentation_ids):
            raise ValueError(
                "Chat history replacement presentation ids must be unique."
            )
        action_ids = tuple(
            action.action_id for record in self.records for action in record.actions
        )
        if len(set(action_ids)) != len(action_ids):
            raise ValueError(
                "Chat history replacement response action ids must be unique."
            )


@dataclass(frozen=True, slots=True)
class ChatResponseActionSelection:
    """Untrusted UI selection values resolved against canonical history."""

    presentation_id: str
    action_id: str
    label: str
    kind: ChatResponseActionKind
    prompt: str = ""
    panel: ChatPanelTarget | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ChatResponseActionKind):
            raise TypeError("Chat action selection kind must be typed.")
        if self.panel is not None and not isinstance(self.panel, ChatPanelTarget):
            raise TypeError("Chat action selection panel must be typed.")
        limits = {
            "presentation_id": MAX_CHAT_PRESENTATION_ID_LENGTH,
            "action_id": MAX_CHAT_ACTION_ID_LENGTH,
            "label": MAX_CHAT_ACTION_LABEL_LENGTH,
            "prompt": MAX_CHAT_ACTION_PROMPT_LENGTH,
        }
        for field_name, maximum_length in limits.items():
            object.__setattr__(
                self,
                field_name,
                bounded_chat_string(
                    getattr(self, field_name),
                    field_name=f"Chat action selection {field_name}",
                    maximum_length=maximum_length,
                    normalize_whitespace=True,
                ),
            )
        if not self.presentation_id or not self.action_id or not self.label:
            raise ValueError(
                "Chat action selections require a presentation ID, action ID, "
                "and label."
            )

    @classmethod
    def from_action(
        cls,
        presentation_id: str,
        action: ChatResponseAction,
    ) -> ChatResponseActionSelection:
        if not isinstance(action, ChatResponseAction):
            raise TypeError("Chat action selections require a typed action.")
        return cls(
            presentation_id=presentation_id,
            action_id=action.action_id,
            label=action.label,
            kind=action.kind,
            prompt=action.prompt,
            panel=action.panel,
        )

    def matches(self, action: ChatResponseAction) -> bool:
        return bool(
            isinstance(action, ChatResponseAction)
            and self.action_id == action.action_id
            and self.label == action.label
            and self.kind is action.kind
            and self.prompt == action.prompt
            and self.panel is action.panel
        )


@dataclass(frozen=True, slots=True)
class ChatResponseActionResolution:
    """Canonical action plus the active record needed for a rejected UI retry."""

    action: ChatResponseAction
    source_record: ChatMessageRecord

    def __post_init__(self) -> None:
        if not isinstance(self.action, ChatResponseAction):
            raise TypeError("Chat response action resolutions require a typed action.")
        if not isinstance(self.source_record, ChatMessageRecord):
            raise TypeError("Chat response action resolutions require a typed record.")
        if (
            not self.source_record.has_active_actions
            or self.action not in self.source_record.actions
        ):
            raise ValueError(
                "Chat response action resolutions require their active source record."
            )


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
        """Add one user message and retire prior response actions."""
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
        presentation_id: str = "",
        actions: tuple[ChatResponseAction, ...] = (),
    ) -> ChatMessageRecord:
        """Add one explicitly typed assistant presentation."""
        if not isinstance(presentation_kind, ChatMessagePresentationKind):
            raise TypeError("Agent messages require a typed presentation kind.")
        if presentation_kind is ChatMessagePresentationKind.USER:
            raise ValueError("Agent messages cannot use the user presentation kind.")
        if actions and not presentation_id:
            raise ValueError("Agent response actions require a presentation id.")
        record = ChatMessageRecord(
            role=ChatMessageRole.ASSISTANT,
            content=text,
            presentation_kind=presentation_kind,
            message_id=uuid4().hex,
            presentation_id=presentation_id,
            actions=actions,
            action_state=(ChatActionState.ACTIVE if actions else ChatActionState.NONE),
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
        """Validate an append before any existing action state is mutated."""
        self._require_history_capacity()
        if any(item.message_id == record.message_id for item in self._history_records):
            raise ValueError("Chat message ids must be unique.")
        if record.presentation_id and any(
            item.presentation_id == record.presentation_id
            for item in self._history_records
        ):
            raise ValueError("Chat presentation ids must be unique.")
        known_action_ids = {
            action.action_id
            for item in self._history_records
            for action in item.actions
        }
        if any(action.action_id in known_action_ids for action in record.actions):
            raise ValueError("Chat response action ids must be unique.")

    def _append_record_transaction(self, record: ChatMessageRecord) -> None:
        """Commit action retirement and one append before publishing UI signals."""
        self._require_record_appendable(record)
        history_before = list(self._history_records)
        messages_before = list(self.messages)
        try:
            consumed_records = self._consume_active_actions(emit=False)
            self._append_record(record, emit=False)
        except Exception:
            self._history_records = history_before
            self.messages = messages_before
            raise

        for consumed_record in consumed_records:
            self._emit_record_updated(consumed_record)
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

    def consume_response_actions(self, presentation_id: str) -> bool:
        """Persist that one visible action set is no longer selectable."""
        if not isinstance(presentation_id, str) or not presentation_id:
            return False
        for index in range(len(self._history_records) - 1, -1, -1):
            record = self._history_records[index]
            if (
                record.presentation_id != presentation_id
                or not record.has_active_actions
            ):
                continue
            updated = replace(record, action_state=ChatActionState.CONSUMED)
            self._history_records[index] = updated
            self._emit_record_updated(updated)
            return True
        return False

    def consume_all_response_actions(self) -> None:
        """Make every live response action inert at a turn/session boundary."""
        self._consume_active_actions()

    def resolve_response_action(
        self,
        selection: ChatResponseActionSelection,
    ) -> ChatResponseAction | None:
        """Return one canonical active action after exact payload matching."""
        if not isinstance(selection, ChatResponseActionSelection):
            return None
        for record in reversed(self._history_records):
            if (
                record.presentation_id != selection.presentation_id
                or not record.has_active_actions
            ):
                continue
            action = next(
                (
                    candidate
                    for candidate in record.actions
                    if candidate.action_id == selection.action_id
                ),
                None,
            )
            if action is None or not selection.matches(action):
                return None
            return action
        return None

    def active_response_record(
        self,
        *,
        message_id: str,
        presentation_id: str,
    ) -> ChatMessageRecord | None:
        """Return one exact action row only while it remains canonically active."""
        if (
            type(message_id) is not str
            or not message_id
            or type(presentation_id) is not str
            or not presentation_id
        ):
            return None
        for record in reversed(self._history_records):
            if (
                record.message_id == message_id
                and record.presentation_id == presentation_id
                and record.has_active_actions
            ):
                return record
        return None

    def resolve_and_consume_response_action(
        self,
        selection: ChatResponseActionSelection,
    ) -> ChatResponseActionResolution | None:
        """Resolve one action and own its consume/retry transaction.

        Navigation actions are consumed immediately. Send-message actions remain
        active until an admitted user row consumes them, so rejected admission is
        retryable without restoring controller state.
        """
        if not isinstance(selection, ChatResponseActionSelection):
            return None
        for index in range(len(self._history_records) - 1, -1, -1):
            record = self._history_records[index]
            if (
                record.presentation_id != selection.presentation_id
                or not record.has_active_actions
            ):
                continue
            action = next(
                (
                    candidate
                    for candidate in record.actions
                    if candidate.action_id == selection.action_id
                ),
                None,
            )
            if action is None or not selection.matches(action):
                return None
            resolution = ChatResponseActionResolution(
                action=action,
                source_record=record,
            )
            if action.kind is ChatResponseActionKind.SEND_MESSAGE:
                return resolution
            updated = replace(record, action_state=ChatActionState.CONSUMED)
            self._history_records[index] = updated
            self._emit_record_updated(updated)
            return resolution
        return None

    def _consume_active_actions(
        self,
        *,
        emit: bool = True,
    ) -> tuple[ChatMessageRecord, ...]:
        consumed_records: list[ChatMessageRecord] = []
        for index, record in enumerate(self._history_records):
            if not record.has_active_actions:
                continue
            updated = replace(record, action_state=ChatActionState.CONSUMED)
            self._history_records[index] = updated
            consumed_records.append(updated)
            if emit:
                self._emit_record_updated(updated)
        return tuple(consumed_records)

    def update_presentation_kind(
        self,
        presentation_id: str,
        presentation_kind: ChatMessagePresentationKind,
    ) -> bool:
        """Update one correlated assistant record from a later typed event."""
        if not isinstance(presentation_kind, ChatMessagePresentationKind):
            raise TypeError("Updated chat presentation kind must be typed.")
        if presentation_kind is ChatMessagePresentationKind.USER:
            raise ValueError("Assistant presentations cannot become user messages.")
        for index in range(len(self._history_records) - 1, -1, -1):
            record = self._history_records[index]
            if record.presentation_id != presentation_id:
                continue
            updated = replace(record, presentation_kind=presentation_kind)
            self._history_records[index] = updated
            self._emit_record_updated(updated)
            return True
        return False

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
        presentation_ids: set[str] = set()
        action_ids: set[str] = set()
        try:
            for value in history:
                if len(parsed) >= MAX_CHAT_HISTORY_ROWS:
                    return 0
                record = ChatMessageRecord.from_history_value(value)
                if record is None:
                    return 0
                record_action_ids = {action.action_id for action in record.actions}
                if (
                    record.message_id in message_ids
                    or (
                        bool(record.presentation_id)
                        and record.presentation_id in presentation_ids
                    )
                    or bool(record_action_ids & action_ids)
                ):
                    return 0
                if record.actions:
                    record = replace(record, action_state=ChatActionState.CONSUMED)
                parsed.append(record)
                message_ids.add(record.message_id)
                if record.presentation_id:
                    presentation_ids.add(record.presentation_id)
                action_ids.update(record_action_ids)
        except Exception:
            return 0

        normalized: list[ChatMessageRecord] = []
        active_index: int | None = None
        for record in parsed:
            if active_index is not None:
                normalized[active_index] = replace(
                    normalized[active_index],
                    action_state=ChatActionState.CONSUMED,
                )
                active_index = None
            normalized.append(record)
            if record.has_active_actions:
                active_index = len(normalized) - 1

        self._history_records = normalized
        self._pruned_row_count = 0
        self._remaining_prepared_presentation_rows = None
        self.messages = [
            {"role": record.role.value, "content": record.content}
            for record in normalized
        ]
        restored_records = tuple(normalized)
        self._publish_history_replacement(
            ChatHistoryReplacement(
                kind=ChatHistoryReplacementKind.RESTORE,
                records=restored_records,
            )
        )
        return len(restored_records)
