"""Typed persistence contract for the product chat transcript."""

from __future__ import annotations

from dataclasses import replace

import pytest

from XBrainLab.backend.controller.chat_controller import (
    ChatActionState,
    ChatController,
    ChatMessagePresentationKind,
    ChatMessageRecord,
    ChatMessageRole,
    ChatPanelTarget,
    ChatResponseAction,
    ChatResponseActionKind,
    ChatResponseActionSelection,
)
from XBrainLab.chat_contract import (
    MAX_CHAT_ACTION_ID_LENGTH,
    MAX_CHAT_ACTION_LABEL_LENGTH,
    MAX_CHAT_ACTION_PROMPT_LENGTH,
    MAX_CHAT_HISTORY_ROWS,
    MAX_CHAT_MESSAGE_CONTENT_LENGTH,
    MAX_CHAT_MESSAGE_ID_LENGTH,
    MAX_CHAT_PRESENTATION_ID_LENGTH,
)

_EXPECTED_MAX_HISTORY_ROWS = MAX_CHAT_HISTORY_ROWS
_EXPECTED_MAX_CONTENT_LENGTH = MAX_CHAT_MESSAGE_CONTENT_LENGTH
_EXPECTED_MAX_ACTION_LABEL_LENGTH = MAX_CHAT_ACTION_LABEL_LENGTH
_EXPECTED_MAX_ACTION_PROMPT_LENGTH = MAX_CHAT_ACTION_PROMPT_LENGTH
_EXPECTED_MAX_ACTION_ID_LENGTH = MAX_CHAT_ACTION_ID_LENGTH
_EXPECTED_MAX_MESSAGE_ID_LENGTH = MAX_CHAT_MESSAGE_ID_LENGTH
_EXPECTED_MAX_PRESENTATION_ID_LENGTH = MAX_CHAT_PRESENTATION_ID_LENGTH


def test_shared_chat_capacity_policy_remains_product_bounded() -> None:
    assert _EXPECTED_MAX_HISTORY_ROWS == 500
    assert _EXPECTED_MAX_CONTENT_LENGTH == 16_384
    assert _EXPECTED_MAX_ACTION_LABEL_LENGTH == 120
    assert _EXPECTED_MAX_ACTION_PROMPT_LENGTH == 4_096
    assert _EXPECTED_MAX_MESSAGE_ID_LENGTH == 128
    assert _EXPECTED_MAX_PRESENTATION_ID_LENGTH == 128
    assert _EXPECTED_MAX_ACTION_ID_LENGTH == 128


def test_typed_history_round_trip_preserves_actions_as_inert_audit_data() -> None:
    controller = ChatController()
    action = ChatResponseAction(
        action_id="open-dataset",
        label="Open Dataset",
        kind=ChatResponseActionKind.OPEN_PANEL,
        panel=ChatPanelTarget.DATASET,
    )
    controller.add_user_message("Why is training unavailable?")
    controller.add_agent_message(
        "Review the imported labels before training.",
        presentation_kind=ChatMessagePresentationKind.ERROR,
        presentation_id="response-7",
        actions=(action,),
    )

    stored = controller.get_history()
    restored = ChatController()
    restored.restore_history(stored)

    records = restored.get_typed_history()
    assert [record.content for record in records] == [
        "Why is training unavailable?",
        "Review the imported labels before training.",
    ]
    assert records[-1].presentation_kind is ChatMessagePresentationKind.ERROR
    assert records[-1].presentation_id == "response-7"
    assert records[-1].actions == (action,)
    assert records[-1].action_state is ChatActionState.CONSUMED
    assert records[-1].has_active_actions is False
    selection = ChatResponseActionSelection.from_action(
        records[-1].presentation_id,
        records[-1].actions[0],
    )
    assert restored.resolve_and_consume_response_action(selection) is None


def test_typed_data_import_action_round_trips_without_prompt_or_panel() -> None:
    action = ChatResponseAction(
        action_id="open-data-import",
        label="Open Data Import",
        kind=ChatResponseActionKind.OPEN_DATA_IMPORT,
    )

    restored = ChatResponseAction.from_history_value(action.to_history_dict())

    assert restored == action
    assert restored.prompt == ""
    assert restored.panel is None


def test_consumed_actions_remain_auditable_but_do_not_restore_as_active() -> None:
    controller = ChatController()
    controller.add_agent_message(
        "Choose the next step.",
        presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
        presentation_id="response-8",
        actions=(
            ChatResponseAction(
                action_id="check-workflow",
                label="Check workflow",
                kind=ChatResponseActionKind.SEND_MESSAGE,
                prompt="What is ready now?",
            ),
        ),
    )

    assert controller.consume_response_actions("response-8") is True
    restored = ChatController()
    restored.restore_history(controller.get_history())

    record = restored.get_typed_history()[0]
    assert record.actions[0].label == "Check workflow"
    assert record.action_state is ChatActionState.CONSUMED
    assert record.has_active_actions is False


def test_legacy_role_content_history_restores_with_safe_presentation_defaults() -> None:
    controller = ChatController()

    restored_count = controller.restore_history(
        [
            {"role": "user", "content": "Keep this question"},
            {"role": "assistant", "content": "Keep this answer"},
        ]
    )

    assert restored_count == 2
    records = controller.get_typed_history()
    assert records[0].presentation_kind is ChatMessagePresentationKind.USER
    assert records[1].presentation_kind is ChatMessagePresentationKind.ASSISTANT
    assert records[1].actions == ()
    assert records[1].action_state is ChatActionState.NONE
    assert controller.messages == [
        {"role": "user", "content": "Keep this question"},
        {"role": "assistant", "content": "Keep this answer"},
    ]


def test_unversioned_action_payload_restores_only_inert_plain_text() -> None:
    controller = ChatController()
    legacy_actionable = {
        "role": "assistant",
        "content": "Legacy action copy remains auditable.",
        "presentation_kind": "clarification",
        "message_id": "legacy-message",
        "presentation_id": "legacy-presentation",
        "actions": [_stored_action(action_id="legacy-open")],
        "action_state": "active",
    }

    assert controller.restore_history([legacy_actionable]) == 1

    record = controller.get_typed_history()[0]
    assert record.presentation_kind is ChatMessagePresentationKind.ASSISTANT
    assert record.presentation_id == ""
    assert record.actions == ()
    assert record.action_state is ChatActionState.NONE
    forged_legacy_selection = ChatResponseActionSelection(
        presentation_id="legacy-presentation",
        action_id="legacy-open",
        label="Open Dataset",
        kind=ChatResponseActionKind.OPEN_PANEL,
        panel=ChatPanelTarget.DATASET,
    )
    assert (
        controller.resolve_and_consume_response_action(forged_legacy_selection) is None
    )


def test_invalid_new_history_fields_reject_the_entire_row() -> None:
    controller = ChatController()

    restored_count = controller.restore_history(
        [
            {
                "schema_version": 2,
                "role": "assistant",
                "content": "Retry is ordinary prose here.",
                "presentation_kind": "not-a-kind",
                "presentation_id": "legacy-response",
                "action_state": "active",
                "actions": [{"kind": "unknown", "label": "Retry"}],
            }
        ]
    )

    assert restored_count == 0
    assert controller.get_typed_history() == ()


def _stored_action(**overrides: object) -> dict[str, object]:
    action: dict[str, object] = {
        "action_id": "open-dataset",
        "label": "Open Dataset",
        "kind": "open_panel",
        "prompt": "",
        "panel": "dataset",
    }
    action.update(overrides)
    return action


def _stored_message(**overrides: object) -> dict[str, object]:
    message: dict[str, object] = {
        "schema_version": 2,
        "role": "assistant",
        "content": "Choose a next step.",
        "presentation_kind": "clarification",
        "message_id": "message-1",
        "presentation_id": "presentation-1",
        "actions": [_stored_action()],
        "action_state": "active",
    }
    message.update(overrides)
    return message


def _stored_plain_message(index: int, **overrides: object) -> dict[str, object]:
    message: dict[str, object] = {
        "schema_version": 2,
        "role": "assistant",
        "content": f"History row {index}",
        "presentation_kind": "assistant",
        "message_id": f"message-{index}",
        "presentation_id": "",
        "actions": [],
        "action_state": "none",
    }
    message.update(overrides)
    return message


def test_history_restore_accepts_only_json_like_mappings_and_rejects_future_schema() -> (
    None
):
    source = ChatController()
    source.add_agent_message("Domain object shortcut must not restore.")
    domain_record = source.get_typed_history()[0]
    controller = ChatController()

    assert controller.restore_history([domain_record]) == 0
    assert controller.restore_history([_stored_message(schema_version=999)]) == 0
    assert controller.get_typed_history() == ()


class _StringCoercionTrap:
    def __str__(self) -> str:
        return "open_panel"


def test_history_restore_never_coerces_arbitrary_action_values_to_strings() -> None:
    controller = ChatController()
    malformed = _stored_message(actions=[_stored_action(kind=_StringCoercionTrap())])

    assert controller.restore_history([malformed]) == 0
    assert controller.get_typed_history() == ()


def test_history_restore_rejects_oversized_or_partially_malformed_action_rows() -> None:
    controller = ChatController()
    too_many = _stored_message(
        actions=[_stored_action(action_id=f"action-{index}") for index in range(4)]
    )
    partially_malformed = _stored_message(
        message_id="message-2",
        presentation_id="presentation-2",
        actions=[_stored_action(), {"kind": "send_message"}],
    )

    assert controller.restore_history([too_many, partially_malformed]) == 0
    assert controller.get_typed_history() == ()


def test_invalid_action_state_cannot_restore_executable_actions() -> None:
    controller = ChatController()

    assert controller.restore_history([_stored_message(action_state="surprise")]) == 0
    assert controller.get_typed_history() == ()


def test_current_schema_rejects_role_kind_mismatch_and_blank_ids() -> None:
    controller = ChatController()
    mismatched_user = _stored_message(
        role="user",
        presentation_kind="assistant",
        actions=[],
        presentation_id="",
        action_state="none",
    )
    blank_message_id = _stored_message(message_id="   ")
    blank_presentation_id = _stored_message(presentation_id="   ")

    assert (
        controller.restore_history(
            [mismatched_user, blank_message_id, blank_presentation_id]
        )
        == 0
    )
    assert controller.get_typed_history() == ()


@pytest.mark.parametrize("malformed_first", [False, True])
def test_malformed_row_in_any_batch_position_preserves_existing_history(
    malformed_first: bool,
) -> None:
    controller = ChatController()
    controller.add_agent_message("Trusted existing history.")
    existing = controller.get_history()
    valid_actionable = _stored_message()
    malformed = _stored_plain_message(2, content=object())
    incoming = (
        [malformed, valid_actionable]
        if malformed_first
        else [valid_actionable, malformed]
    )

    assert controller.restore_history(incoming) == 0
    assert controller.get_history() == existing
    selection = ChatResponseActionSelection(
        presentation_id="presentation-1",
        action_id="open-dataset",
        label="Open Dataset",
        kind=ChatResponseActionKind.OPEN_PANEL,
        panel=ChatPanelTarget.DATASET,
    )
    assert controller.resolve_and_consume_response_action(selection) is None


@pytest.mark.parametrize(
    "duplicate",
    ["message_id", "presentation_id", "action_id"],
)
def test_duplicate_batch_identifier_rejects_all_rows_without_replacement(
    duplicate: str,
) -> None:
    controller = ChatController()
    controller.add_user_message("Trusted existing history.")
    existing = controller.get_history()
    first = _stored_message()
    second = _stored_message(
        message_id="message-2",
        presentation_id="presentation-2",
        actions=[_stored_action(action_id="action-2")],
    )
    if duplicate == "message_id":
        second["message_id"] = first["message_id"]
    elif duplicate == "presentation_id":
        second["presentation_id"] = first["presentation_id"]
    else:
        second["actions"] = [_stored_action()]

    assert controller.restore_history([first, second]) == 0
    assert controller.get_history() == existing


def test_exact_string_capacity_round_trips_for_current_schema_actions() -> None:
    record = ChatMessageRecord(
        role=ChatMessageRole.ASSISTANT,
        content="c" * _EXPECTED_MAX_CONTENT_LENGTH,
        presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
        message_id="m" * _EXPECTED_MAX_MESSAGE_ID_LENGTH,
        presentation_id="p" * _EXPECTED_MAX_PRESENTATION_ID_LENGTH,
        actions=(
            ChatResponseAction(
                action_id="a" * _EXPECTED_MAX_ACTION_ID_LENGTH,
                label="l" * _EXPECTED_MAX_ACTION_LABEL_LENGTH,
                kind=ChatResponseActionKind.OPEN_PANEL,
                panel=ChatPanelTarget.DATASET,
            ),
            ChatResponseAction(
                action_id="b" * _EXPECTED_MAX_ACTION_ID_LENGTH,
                label="Send",
                kind=ChatResponseActionKind.SEND_MESSAGE,
                prompt="q" * _EXPECTED_MAX_ACTION_PROMPT_LENGTH,
            ),
        ),
        action_state=ChatActionState.ACTIVE,
    )
    controller = ChatController()

    assert controller.restore_history([record.to_history_dict()]) == 1
    assert controller.get_typed_history() == (
        replace(record, action_state=ChatActionState.CONSUMED),
    )


@pytest.mark.parametrize(
    "build",
    [
        lambda: ChatMessageRecord(
            role=ChatMessageRole.USER,
            content="c" * (_EXPECTED_MAX_CONTENT_LENGTH + 1),
            presentation_kind=ChatMessagePresentationKind.USER,
            message_id="message",
        ),
        lambda: ChatMessageRecord(
            role=ChatMessageRole.USER,
            content="content",
            presentation_kind=ChatMessagePresentationKind.USER,
            message_id="m" * (_EXPECTED_MAX_MESSAGE_ID_LENGTH + 1),
        ),
        lambda: ChatMessageRecord(
            role=ChatMessageRole.ASSISTANT,
            content="content",
            presentation_kind=ChatMessagePresentationKind.ASSISTANT,
            message_id="message",
            presentation_id="p" * (_EXPECTED_MAX_PRESENTATION_ID_LENGTH + 1),
        ),
        lambda: ChatResponseAction(
            action_id="action",
            label="l" * (_EXPECTED_MAX_ACTION_LABEL_LENGTH + 1),
            kind=ChatResponseActionKind.OPEN_PANEL,
            panel=ChatPanelTarget.DATASET,
        ),
        lambda: ChatResponseAction(
            action_id="action",
            label="Send",
            kind=ChatResponseActionKind.SEND_MESSAGE,
            prompt="q" * (_EXPECTED_MAX_ACTION_PROMPT_LENGTH + 1),
        ),
        lambda: ChatResponseAction(
            action_id="a" * (_EXPECTED_MAX_ACTION_ID_LENGTH + 1),
            label="Open Dataset",
            kind=ChatResponseActionKind.OPEN_PANEL,
            panel=ChatPanelTarget.DATASET,
        ),
    ],
)
def test_live_chat_contract_rejects_each_string_capacity_overflow(build) -> None:
    with pytest.raises(ValueError, match=r"maximum|at most"):
        build()


@pytest.mark.parametrize(
    "oversized",
    [
        _stored_plain_message(
            1,
            content="c" * (_EXPECTED_MAX_CONTENT_LENGTH + 1),
        ),
        _stored_plain_message(
            1,
            message_id="m" * (_EXPECTED_MAX_MESSAGE_ID_LENGTH + 1),
        ),
        _stored_message(
            presentation_id="p" * (_EXPECTED_MAX_PRESENTATION_ID_LENGTH + 1),
        ),
        _stored_message(
            actions=[
                _stored_action(label="l" * (_EXPECTED_MAX_ACTION_LABEL_LENGTH + 1))
            ],
        ),
        _stored_message(
            actions=[
                _stored_action(
                    kind="send_message",
                    prompt="q" * (_EXPECTED_MAX_ACTION_PROMPT_LENGTH + 1),
                    panel=None,
                )
            ],
        ),
        _stored_message(
            actions=[
                _stored_action(action_id="a" * (_EXPECTED_MAX_ACTION_ID_LENGTH + 1))
            ],
        ),
    ],
)
def test_restore_string_overflow_preserves_existing_history(
    oversized: dict[str, object],
) -> None:
    controller = ChatController()
    controller.add_user_message("Trusted existing history.")
    existing = controller.get_history()

    assert controller.restore_history([oversized]) == 0
    assert controller.get_history() == existing


def test_live_history_accepts_exact_row_capacity_and_rejects_next_row() -> None:
    controller = ChatController()
    for index in range(_EXPECTED_MAX_HISTORY_ROWS):
        controller.add_user_message(f"Message {index}")

    assert len(controller.get_typed_history()) == _EXPECTED_MAX_HISTORY_ROWS
    with pytest.raises(ValueError, match=r"history|rows"):
        controller.add_user_message("One row too many")
    assert len(controller.get_typed_history()) == _EXPECTED_MAX_HISTORY_ROWS


def test_restore_accepts_exact_row_capacity_and_rejects_overflow_atomically() -> None:
    exact = [
        _stored_plain_message(index) for index in range(_EXPECTED_MAX_HISTORY_ROWS)
    ]
    controller = ChatController()

    assert controller.restore_history(exact) == _EXPECTED_MAX_HISTORY_ROWS
    exact_history = controller.get_history()
    overflow = [
        *exact,
        _stored_plain_message(_EXPECTED_MAX_HISTORY_ROWS),
    ]

    assert controller.restore_history(overflow) == 0
    assert controller.get_history() == exact_history


def test_action_resolution_matches_exact_payload_and_consumes_once() -> None:
    controller = ChatController()
    action = ChatResponseAction(
        action_id="open-dataset",
        label="Open Dataset",
        kind=ChatResponseActionKind.OPEN_PANEL,
        panel=ChatPanelTarget.DATASET,
    )
    controller.add_agent_message(
        "Choose a next step.",
        presentation_id="presentation-1",
        actions=(action,),
    )
    forged = ChatResponseActionSelection(
        presentation_id="presentation-1",
        action_id="open-dataset",
        label="Open Dataset",
        kind=ChatResponseActionKind.OPEN_PANEL,
        panel=ChatPanelTarget.TRAINING,
    )
    forged_label = ChatResponseActionSelection(
        presentation_id="presentation-1",
        action_id="open-dataset",
        label="Open Training",
        kind=ChatResponseActionKind.OPEN_PANEL,
        panel=ChatPanelTarget.DATASET,
    )
    exact = ChatResponseActionSelection.from_action("presentation-1", action)

    assert controller.resolve_and_consume_response_action(forged) is None
    assert controller.resolve_and_consume_response_action(forged_label) is None
    assert controller.resolve_and_consume_response_action(exact) == action
    assert controller.resolve_and_consume_response_action(exact) is None
