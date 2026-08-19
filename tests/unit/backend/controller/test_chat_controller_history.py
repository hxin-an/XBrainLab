"""Typed persistence contract for the product chat transcript."""

from __future__ import annotations

import pytest

from XBrainLab.backend.controller.chat_controller import (
    ChatController,
    ChatHistoryReplacement,
    ChatHistoryReplacementKind,
    ChatMessagePresentationKind,
    ChatMessageRecord,
    ChatMessageRole,
)
from XBrainLab.chat_contract import (
    CHAT_HISTORY_LIVE_WINDOW_ROWS,
    CHAT_HISTORY_SCHEMA_VERSION,
    MAX_CHAT_HISTORY_ROWS,
    MAX_CHAT_MESSAGE_CONTENT_LENGTH,
    MAX_CHAT_MESSAGE_ID_LENGTH,
    MAX_CHAT_PRESENTATION_ROWS_PER_TURN,
    MIN_CHAT_TURN_HISTORY_ROWS,
)


def test_shared_chat_capacity_policy_remains_product_bounded() -> None:
    assert MAX_CHAT_HISTORY_ROWS == 500
    assert CHAT_HISTORY_LIVE_WINDOW_ROWS == 100
    assert MAX_CHAT_PRESENTATION_ROWS_PER_TURN == 2
    assert MIN_CHAT_TURN_HISTORY_ROWS == 3
    assert MAX_CHAT_MESSAGE_CONTENT_LENGTH == 16_384
    assert MAX_CHAT_MESSAGE_ID_LENGTH == 128


def test_history_replacement_rejects_duplicate_message_ids() -> None:
    controller = ChatController()
    record = controller.add_user_message("Keep one immutable row.")

    with pytest.raises(ValueError, match="message ids must be unique"):
        ChatHistoryReplacement(
            kind=ChatHistoryReplacementKind.RESTORE,
            records=(record, record),
        )


def test_typed_history_round_trip_keeps_only_transcript_fields() -> None:
    controller = ChatController()
    controller.add_user_message("Inspect the current workflow.")
    controller.add_agent_message(
        "The workflow needs attention.",
        presentation_kind=ChatMessagePresentationKind.ATTENTION,
    )

    stored = controller.get_history()

    assert stored[-1] == {
        "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
        "role": "assistant",
        "content": "The workflow needs attention.",
        "presentation_kind": "attention",
        "message_id": stored[-1]["message_id"],
    }
    assert not {"actions", "action_state", "presentation_id"} & stored[-1].keys()

    restored = ChatController()
    assert restored.restore_history(stored) == 2
    assert restored.get_history() == stored


def test_restore_ignores_retired_action_payload_fields() -> None:
    record = {
        "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
        "role": "assistant",
        "content": "Plain transcript copy.",
        "presentation_kind": "assistant",
        "message_id": "message-1",
        "presentation_id": "legacy-presentation",
        "actions": [{"kind": "open_panel", "label": "Open Dataset"}],
        "action_state": "active",
    }
    controller = ChatController()

    assert controller.restore_history([record]) == 1
    restored = controller.get_history()[0]
    assert restored["content"] == "Plain transcript copy."
    assert not {"actions", "action_state", "presentation_id"} & restored.keys()


@pytest.mark.parametrize(
    "value",
    [
        None,
        "not-a-record",
        {"role": "assistant"},
        {
            "schema_version": CHAT_HISTORY_SCHEMA_VERSION + 1,
            "role": "assistant",
            "content": "Wrong schema.",
            "message_id": "message-1",
        },
        {
            "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
            "role": "user",
            "content": "Wrong kind.",
            "presentation_kind": "assistant",
            "message_id": "message-1",
        },
    ],
)
def test_restore_rejects_malformed_current_rows_atomically(value: object) -> None:
    controller = ChatController()
    controller.add_user_message("Existing row.")
    before = controller.get_history()

    assert controller.restore_history([value]) == 0
    assert controller.get_history() == before


def test_legacy_role_and_content_rows_restore_with_safe_default_kind() -> None:
    controller = ChatController()

    assert (
        controller.restore_history(
            [
                {"role": "user", "content": "Legacy user."},
                {"role": "assistant", "content": "Legacy assistant."},
            ]
        )
        == 2
    )

    records = controller.get_typed_history()
    assert records[0].presentation_kind is ChatMessagePresentationKind.USER
    assert records[1].presentation_kind is ChatMessagePresentationKind.ASSISTANT
    assert all(record.message_id for record in records)


def test_record_contract_rejects_role_presentation_mismatch() -> None:
    with pytest.raises(ValueError, match="User messages require"):
        ChatMessageRecord(
            role=ChatMessageRole.USER,
            content="Invalid.",
            presentation_kind=ChatMessagePresentationKind.ASSISTANT,
            message_id="message-1",
        )
    with pytest.raises(ValueError, match="Assistant messages cannot"):
        ChatMessageRecord(
            role=ChatMessageRole.ASSISTANT,
            content="Invalid.",
            presentation_kind=ChatMessagePresentationKind.USER,
            message_id="message-2",
        )


def test_exact_string_capacity_round_trips_and_overflow_fails() -> None:
    record = ChatMessageRecord(
        role=ChatMessageRole.ASSISTANT,
        content="c" * MAX_CHAT_MESSAGE_CONTENT_LENGTH,
        presentation_kind=ChatMessagePresentationKind.ASSISTANT,
        message_id="m" * MAX_CHAT_MESSAGE_ID_LENGTH,
    )
    assert ChatMessageRecord.from_history_value(record.to_history_dict()) == record

    with pytest.raises(ValueError, match=r"maximum|at most"):
        ChatMessageRecord(
            role=ChatMessageRole.ASSISTANT,
            content="c" * (MAX_CHAT_MESSAGE_CONTENT_LENGTH + 1),
            presentation_kind=ChatMessagePresentationKind.ASSISTANT,
            message_id="message-1",
        )


def test_append_is_atomic_when_message_id_is_duplicated() -> None:
    controller = ChatController()
    record = controller.add_user_message("First row.")
    before = controller.get_history()

    with pytest.raises(ValueError, match="message ids must be unique"):
        controller._append_record_transaction(record)
    assert controller.get_history() == before


def test_prepare_for_turn_prunes_to_live_window_and_preserves_order() -> None:
    controller = ChatController()
    for index in range(MAX_CHAT_HISTORY_ROWS - MIN_CHAT_TURN_HISTORY_ROWS + 1):
        controller.add_user_message(f"row-{index}")

    pruned = controller.prepare_for_turn()

    assert pruned > 0
    records = controller.get_typed_history()
    assert len(records) <= CHAT_HISTORY_LIVE_WINDOW_ROWS
    assert [record.content for record in records] == sorted(
        (record.content for record in records),
        key=lambda value: int(value.split("-")[1]),
    )


def test_prepared_turn_allows_only_bounded_assistant_rows() -> None:
    controller = ChatController()
    controller.prepare_for_turn()
    controller.add_user_message("One admitted turn.")
    controller.add_agent_message("First assistant row.")
    controller.add_agent_message("Second assistant row.")

    with pytest.raises(ValueError, match="at most"):
        controller.add_agent_message("Third assistant row.")


def test_clear_publishes_typed_empty_replacement_and_legacy_signal(qtbot) -> None:
    controller = ChatController()
    controller.add_user_message("Clear me.")
    replacements: list[ChatHistoryReplacement] = []
    clears: list[bool] = []
    controller.history_replaced.connect(replacements.append)
    controller.conversation_cleared.connect(lambda: clears.append(True))

    controller.clear_conversation()

    assert replacements == [
        ChatHistoryReplacement(kind=ChatHistoryReplacementKind.CLEAR, records=())
    ]
    assert clears == [True]
    assert controller.get_history() == []


def test_processing_state_remains_a_typed_ui_signal() -> None:
    controller = ChatController()
    states: list[bool] = []
    controller.processing_state_changed.connect(states.append)

    controller.set_processing(True)
    controller.set_processing(False)

    assert states == [True, False]
