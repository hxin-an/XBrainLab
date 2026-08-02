"""Typed persistence contract for the product chat transcript."""

from __future__ import annotations

from dataclasses import replace

import pytest

from XBrainLab.backend.controller.chat_controller import (
    ChatActionState,
    ChatController,
    ChatHistoryReplacement,
    ChatHistoryReplacementKind,
    ChatMessagePresentationKind,
    ChatMessageRecord,
    ChatMessageRole,
    ChatPanelTarget,
    ChatResponseAction,
    ChatResponseActionKind,
    ChatResponseActionSelection,
)
from XBrainLab.chat_contract import (
    CHAT_HISTORY_LIVE_WINDOW_ROWS,
    MAX_CHAT_ACTION_ID_LENGTH,
    MAX_CHAT_ACTION_LABEL_LENGTH,
    MAX_CHAT_ACTION_PROMPT_LENGTH,
    MAX_CHAT_HISTORY_ROWS,
    MAX_CHAT_MESSAGE_CONTENT_LENGTH,
    MAX_CHAT_MESSAGE_ID_LENGTH,
    MAX_CHAT_PRESENTATION_ID_LENGTH,
    MAX_CHAT_PRESENTATION_ROWS_PER_TURN,
    MIN_CHAT_TURN_HISTORY_ROWS,
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
    assert CHAT_HISTORY_LIVE_WINDOW_ROWS == 100
    assert MAX_CHAT_PRESENTATION_ROWS_PER_TURN == 2
    assert MIN_CHAT_TURN_HISTORY_ROWS == 3
    assert _EXPECTED_MAX_CONTENT_LENGTH == 16_384
    assert _EXPECTED_MAX_ACTION_LABEL_LENGTH == 120
    assert _EXPECTED_MAX_ACTION_PROMPT_LENGTH == 4_096
    assert _EXPECTED_MAX_MESSAGE_ID_LENGTH == 128
    assert _EXPECTED_MAX_PRESENTATION_ID_LENGTH == 128
    assert _EXPECTED_MAX_ACTION_ID_LENGTH == 128


def test_history_replacement_rejects_duplicate_message_ids() -> None:
    controller = ChatController()
    record = controller.add_user_message("Keep one immutable row.")

    with pytest.raises(ValueError, match="message ids must be unique"):
        ChatHistoryReplacement(
            kind=ChatHistoryReplacementKind.RESTORE,
            records=(record, record),
        )


@pytest.mark.parametrize(
    ("duplicate_identity", "expected_message"),
    (
        ("presentation_id", "presentation ids must be unique"),
        ("action_id", "response action ids must be unique"),
    ),
)
def test_history_replacement_rejects_duplicate_presentation_identity(
    duplicate_identity: str,
    expected_message: str,
) -> None:
    action_id = "first-action"
    second_action_id = "second-action"
    first_presentation_id = "first-presentation"
    second_presentation_id = "second-presentation"
    if duplicate_identity == "presentation_id":
        second_presentation_id = first_presentation_id
    else:
        second_action_id = action_id
    records = (
        ChatMessageRecord(
            role=ChatMessageRole.ASSISTANT,
            content="First choice.",
            presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
            message_id="first-message",
            presentation_id=first_presentation_id,
            actions=(
                ChatResponseAction(
                    action_id=action_id,
                    label="First action",
                    kind=ChatResponseActionKind.SEND_MESSAGE,
                    prompt="Run the first action.",
                ),
            ),
            action_state=ChatActionState.ACTIVE,
        ),
        ChatMessageRecord(
            role=ChatMessageRole.ASSISTANT,
            content="Second choice.",
            presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
            message_id="second-message",
            presentation_id=second_presentation_id,
            actions=(
                ChatResponseAction(
                    action_id=second_action_id,
                    label="Second action",
                    kind=ChatResponseActionKind.SEND_MESSAGE,
                    prompt="Run the second action.",
                ),
            ),
            action_state=ChatActionState.ACTIVE,
        ),
    )

    with pytest.raises(ValueError, match=expected_message):
        ChatHistoryReplacement(
            kind=ChatHistoryReplacementKind.RESTORE,
            records=records,
        )


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

    assert restored is not None
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


def test_active_response_record_returns_only_the_canonical_live_action_row() -> None:
    controller = ChatController()
    controller.add_agent_message(
        "Choose the next step.",
        presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
        presentation_id="response-live",
        actions=(
            ChatResponseAction(
                action_id="check-workflow",
                label="Check workflow",
                kind=ChatResponseActionKind.SEND_MESSAGE,
                prompt="What is ready now?",
            ),
        ),
    )
    record = controller.get_typed_history()[0]

    assert (
        controller.active_response_record(
            message_id=record.message_id,
            presentation_id="response-live",
        )
        == record
    )
    assert (
        controller.active_response_record(
            message_id="other-message",
            presentation_id="response-live",
        )
        is None
    )
    assert controller.consume_response_actions("response-live") is True
    assert (
        controller.active_response_record(
            message_id=record.message_id,
            presentation_id="response-live",
        )
        is None
    )


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


def test_admitted_turn_reserves_and_enforces_maximum_presentation_rows() -> None:
    controller = ChatController()
    seed_rows = _EXPECTED_MAX_HISTORY_ROWS - MIN_CHAT_TURN_HISTORY_ROWS
    for index in range(seed_rows):
        controller.add_user_message(f"History row {index}")

    assert controller.can_accept_turn() is True
    assert controller.prepare_for_turn() == 0
    controller.add_user_message("Start the admitted turn.")
    controller.add_agent_message("Intermediate workflow result.")
    controller.add_agent_message("Terminal workflow result.")

    assert len(controller.get_typed_history()) == _EXPECTED_MAX_HISTORY_ROWS
    serialized_before = controller.get_history()
    ui_events: list[str] = []
    controller.message_record_added.connect(lambda _record: ui_events.append("add"))
    controller.message_record_updated.connect(
        lambda _record: ui_events.append("update")
    )

    with pytest.raises(ValueError, match="at most 2 presentation rows"):
        controller.add_agent_message("Unexpected third presentation.")

    assert controller.get_history() == serialized_before
    assert ui_events == []


def test_presentation_budget_is_reserved_before_synchronous_emit_reentry() -> None:
    controller = ChatController()
    controller.prepare_for_turn()
    controller.add_user_message("Start the admitted turn.")
    overflow_errors: list[str] = []

    def append_during_first_emit(record: ChatMessageRecord) -> None:
        if record.content != "First presentation.":
            return
        controller.add_agent_message("Second presentation.")
        try:
            controller.add_agent_message("Reentrant third presentation.")
        except ValueError as exc:
            overflow_errors.append(str(exc))

    controller.message_record_added.connect(append_during_first_emit)

    controller.add_agent_message("First presentation.")

    assert [record.content for record in controller.get_typed_history()] == [
        "Start the admitted turn.",
        "First presentation.",
        "Second presentation.",
    ]
    assert len(overflow_errors) == 1
    assert "at most 2 presentation rows" in overflow_errors[0]


def test_turn_budget_is_installed_before_synchronous_prune_replacement_slot() -> None:
    controller = ChatController()
    for index in range(_EXPECTED_MAX_HISTORY_ROWS):
        controller.add_user_message(f"History row {index}")
    attempted = False
    overflow_errors: list[str] = []

    def append_during_rebuild(*_payload: object) -> None:
        nonlocal attempted
        if attempted:
            return
        attempted = True
        for index in range(MAX_CHAT_PRESENTATION_ROWS_PER_TURN):
            controller.add_agent_message(f"Reentrant presentation {index}.")
        try:
            controller.add_agent_message(
                f"Reentrant presentation {MAX_CHAT_PRESENTATION_ROWS_PER_TURN}."
            )
        except ValueError as exc:
            overflow_errors.append(str(exc))

    controller.history_replaced.connect(append_during_rebuild)

    assert controller.prepare_for_turn() > 0

    contents = [record.content for record in controller.get_typed_history()]
    assert "Reentrant presentation 0." in contents
    assert "Reentrant presentation 1." in contents
    assert "Reentrant presentation 2." not in contents
    assert len(overflow_errors) == 1
    assert "at most 2 presentation rows" in overflow_errors[0]


def test_failed_append_rolls_back_reserved_presentation_budget(monkeypatch) -> None:
    controller = ChatController()
    controller.prepare_for_turn()
    user = controller.add_user_message("Start the admitted turn.")

    monkeypatch.setattr(
        "XBrainLab.backend.controller.chat_controller.uuid4",
        lambda: type("DuplicateUuid", (), {"hex": user.message_id})(),
    )
    with pytest.raises(ValueError, match="message ids must be unique"):
        controller.add_agent_message("Rejected duplicate.")
    monkeypatch.undo()

    controller.add_agent_message("First valid presentation.")
    controller.add_agent_message("Second valid presentation.")

    assert [record.content for record in controller.get_typed_history()] == [
        "Start the admitted turn.",
        "First valid presentation.",
        "Second valid presentation.",
    ]


@pytest.mark.parametrize(
    "duplicate_identifier",
    ("message_id", "presentation_id", "action_id"),
)
def test_duplicate_append_preserves_active_action_and_rolls_back_entire_transaction(
    duplicate_identifier: str,
    monkeypatch,
) -> None:
    controller = ChatController()
    active_action = ChatResponseAction(
        action_id="active-action",
        label="Check workflow",
        kind=ChatResponseActionKind.SEND_MESSAGE,
        prompt="Check what is ready now.",
    )
    active_record = controller.add_agent_message(
        "Keep this active choice.",
        presentation_id="active-presentation",
        actions=(active_action,),
    )
    controller.prepare_for_turn()
    history_before = controller.get_history()
    messages_before = list(controller.messages)
    ui_events: list[str] = []
    controller.message_record_added.connect(lambda _record: ui_events.append("add"))
    controller.message_record_updated.connect(
        lambda _record: ui_events.append("update")
    )

    candidate_presentation_id = "candidate-presentation"
    candidate_actions: tuple[ChatResponseAction, ...] = ()
    if duplicate_identifier == "presentation_id":
        candidate_presentation_id = active_record.presentation_id
    elif duplicate_identifier == "action_id":
        candidate_actions = (
            ChatResponseAction(
                action_id=active_action.action_id,
                label="Use duplicate action",
                kind=ChatResponseActionKind.SEND_MESSAGE,
                prompt="Use duplicate action.",
            ),
        )

    with monkeypatch.context() as patcher:
        if duplicate_identifier == "message_id":
            patcher.setattr(
                "XBrainLab.backend.controller.chat_controller.uuid4",
                lambda: type(
                    "DuplicateUuid",
                    (),
                    {"hex": active_record.message_id},
                )(),
            )
        with pytest.raises(ValueError, match="ids must be unique"):
            controller.add_agent_message(
                "Rejected duplicate.",
                presentation_id=candidate_presentation_id,
                actions=candidate_actions,
            )

    assert controller.get_history() == history_before
    assert controller.messages == messages_before
    assert controller.get_typed_history()[0].has_active_actions is True
    assert ui_events == []

    controller.add_agent_message("First valid presentation.")
    controller.add_agent_message("Second valid presentation.")
    assert [record.content for record in controller.get_typed_history()] == [
        "Keep this active choice.",
        "First valid presentation.",
        "Second valid presentation.",
    ]


def test_turn_reservation_prunes_before_user_plus_two_presentations_overflow() -> None:
    controller = ChatController()
    for index in range(_EXPECTED_MAX_HISTORY_ROWS - MIN_CHAT_TURN_HISTORY_ROWS + 1):
        controller.add_user_message(f"History row {index}")

    assert controller.can_accept_turn() is False
    assert controller.prepare_for_turn() > 0
    controller.add_user_message("Start the admitted turn.")
    controller.add_agent_message("Intermediate workflow result.")
    controller.add_agent_message("Terminal workflow result.")

    assert len(controller.get_typed_history()) <= _EXPECTED_MAX_HISTORY_ROWS


def test_turn_boundary_prunes_oldest_complete_rows_before_capacity_blocks() -> None:
    controller = ChatController()
    for index in range(_EXPECTED_MAX_HISTORY_ROWS // 2):
        controller.add_user_message(f"User turn {index}")
        controller.add_agent_message(f"Assistant turn {index}")

    replacements: list[ChatHistoryReplacement] = []
    added: list[ChatMessageRecord] = []
    legacy_clears: list[bool] = []
    controller.history_replaced.connect(replacements.append)
    controller.message_record_added.connect(added.append)
    controller.conversation_cleared.connect(lambda: legacy_clears.append(True))

    pruned = controller.prepare_for_turn()

    records = controller.get_typed_history()
    assert pruned == _EXPECTED_MAX_HISTORY_ROWS - CHAT_HISTORY_LIVE_WINDOW_ROWS
    assert len(records) == CHAT_HISTORY_LIVE_WINDOW_ROWS
    assert records[0].role is ChatMessageRole.USER
    retained_turn = (_EXPECTED_MAX_HISTORY_ROWS - CHAT_HISTORY_LIVE_WINDOW_ROWS) // 2
    assert records[0].content == f"User turn {retained_turn}"
    assert controller.pruned_row_count == pruned
    assert controller.can_accept_turn() is True
    assert replacements == [
        ChatHistoryReplacement(
            kind=ChatHistoryReplacementKind.PRUNE,
            records=records,
        )
    ]
    assert added == []
    assert legacy_clears == []


def test_turn_boundary_prune_delivers_replacement_then_reentrant_deltas_fifo() -> None:
    controller = ChatController()
    for index in range(_EXPECTED_MAX_HISTORY_ROWS // 2):
        controller.add_user_message(f"User turn {index}")
        if index == (_EXPECTED_MAX_HISTORY_ROWS // 2) - 1:
            controller.add_agent_message(
                f"Assistant turn {index}",
                presentation_id="latest-active-presentation",
                actions=(
                    ChatResponseAction(
                        action_id="latest-active-action",
                        label="Open Training",
                        kind=ChatResponseActionKind.OPEN_PANEL,
                        panel=ChatPanelTarget.TRAINING,
                    ),
                ),
            )
        else:
            controller.add_agent_message(f"Assistant turn {index}")

    replacements: list[ChatHistoryReplacement] = []
    typed_deliveries: list[str] = []
    legacy_deliveries: list[str] = []
    notification_order: list[str] = []
    appended = False

    def append_during_replacement(replacement: ChatHistoryReplacement) -> None:
        nonlocal appended
        replacements.append(replacement)
        notification_order.append(f"replacement:{replacement.kind.value}")
        if not appended:
            appended = True
            controller.add_user_message("Reentrant user turn")

    controller.history_replaced.connect(append_during_replacement)
    controller.message_record_added.connect(
        lambda record: (
            typed_deliveries.append(record.content),
            notification_order.append(f"added:{record.content}"),
        )
    )
    controller.message_added.connect(
        lambda content, _is_user: legacy_deliveries.append(content)
    )
    controller.message_record_updated.connect(
        lambda record: notification_order.append(f"updated:{record.content}")
    )

    assert controller.prepare_for_turn() > 0

    canonical_contents = [record.content for record in controller.get_typed_history()]
    assert canonical_contents[-1] == "Reentrant user turn"
    assert len(replacements) == 1
    assert replacements[0].kind is ChatHistoryReplacementKind.PRUNE
    assert [record.content for record in replacements[0].records] == canonical_contents[
        :-1
    ]
    assert typed_deliveries == ["Reentrant user turn"]
    assert legacy_deliveries == ["Reentrant user turn"]
    assert notification_order == [
        "replacement:prune",
        f"updated:Assistant turn {(_EXPECTED_MAX_HISTORY_ROWS // 2) - 1}",
        "added:Reentrant user turn",
    ]
    assert len(typed_deliveries) == len(set(typed_deliveries))
    assert len(canonical_contents) <= _EXPECTED_MAX_HISTORY_ROWS


def test_restore_delivers_replacement_then_reentrant_append_once() -> None:
    controller = ChatController()
    restored_rows = [_stored_plain_message(index) for index in range(3)]
    replacements: list[ChatHistoryReplacement] = []
    typed_deliveries: list[str] = []
    legacy_deliveries: list[str] = []
    appended = False

    def append_during_replacement(replacement: ChatHistoryReplacement) -> None:
        nonlocal appended
        replacements.append(replacement)
        if not appended:
            appended = True
            controller.add_agent_message("Reentrant assistant turn")

    controller.history_replaced.connect(append_during_replacement)
    controller.message_record_added.connect(
        lambda record: typed_deliveries.append(record.content)
    )
    controller.message_added.connect(
        lambda content, _is_user: legacy_deliveries.append(content)
    )

    assert controller.restore_history(restored_rows) == len(restored_rows)

    canonical_contents = [record.content for record in controller.get_typed_history()]
    assert canonical_contents == [
        *(row["content"] for row in restored_rows),
        "Reentrant assistant turn",
    ]
    assert len(replacements) == 1
    assert replacements[0].kind is ChatHistoryReplacementKind.RESTORE
    assert [record.content for record in replacements[0].records] == [
        row["content"] for row in restored_rows
    ]
    assert typed_deliveries == ["Reentrant assistant turn"]
    assert legacy_deliveries == ["Reentrant assistant turn"]
    assert typed_deliveries.count("Reentrant assistant turn") == 1
    assert len(canonical_contents) <= _EXPECTED_MAX_HISTORY_ROWS


def test_clear_publishes_one_empty_typed_replacement_and_legacy_clear() -> None:
    controller = ChatController()
    controller.add_user_message("Discard this transcript.")
    replacements: list[ChatHistoryReplacement] = []
    legacy_clears: list[bool] = []
    added: list[ChatMessageRecord] = []
    controller.history_replaced.connect(replacements.append)
    controller.conversation_cleared.connect(lambda: legacy_clears.append(True))
    controller.message_record_added.connect(added.append)

    controller.clear_conversation()

    assert replacements == [
        ChatHistoryReplacement(
            kind=ChatHistoryReplacementKind.CLEAR,
            records=(),
        )
    ]
    assert legacy_clears == [True]
    assert added == []


@pytest.mark.parametrize("nested_operation", ("clear", "restore", "prepare"))
def test_nested_replacement_is_rejected_before_canonical_state_mutates(
    nested_operation: str,
) -> None:
    controller = ChatController()
    restored_rows = [_stored_plain_message(index) for index in range(3)]
    published: list[ChatHistoryReplacement] = []
    nested_errors: list[str] = []

    def replace_during_replacement(replacement: ChatHistoryReplacement) -> None:
        published.append(replacement)
        try:
            if nested_operation == "clear":
                controller.clear_conversation()
            elif nested_operation == "restore":
                controller.restore_history([_stored_plain_message(99)])
            else:
                controller.prepare_for_turn()
        except RuntimeError as exc:
            nested_errors.append(str(exc))

    controller.history_replaced.connect(replace_during_replacement)

    assert controller.restore_history(restored_rows) == len(restored_rows)

    assert len(published) == 1
    assert nested_errors == ["Chat history replacement cannot be nested."]
    assert controller.get_typed_history() == published[0].records
    assert controller.messages == [
        {"role": record.role.value, "content": record.content}
        for record in published[0].records
    ]


def test_turn_boundary_pruning_retains_active_actions_until_user_turn_is_added() -> (
    None
):
    controller = ChatController()
    for index in range(_EXPECTED_MAX_HISTORY_ROWS - 1):
        controller.add_user_message(f"History row {index}")
    controller.add_agent_message(
        "Current proposed action",
        presentation_id="current-presentation",
        actions=(
            ChatResponseAction(
                action_id="current-action",
                label="Open Dataset",
                kind=ChatResponseActionKind.OPEN_PANEL,
                panel=ChatPanelTarget.DATASET,
            ),
        ),
    )
    updated: list[ChatMessageRecord] = []
    controller.message_record_updated.connect(updated.append)

    controller.prepare_for_turn()

    retained = controller.get_typed_history()[-1]
    assert retained.presentation_id == "current-presentation"
    assert retained.has_active_actions is True
    assert updated == []
    assert controller.can_accept_turn() is True

    controller.add_user_message("Start the admitted turn.")

    assert controller.get_typed_history()[-2].action_state is ChatActionState.CONSUMED
    assert updated[-1].presentation_id == "current-presentation"


def test_pruned_active_action_persists_only_as_inert_restore_audit_data() -> None:
    controller = ChatController()
    for index in range(_EXPECTED_MAX_HISTORY_ROWS - 1):
        controller.add_user_message(f"History row {index}")
    action = ChatResponseAction(
        action_id="stale-after-restore",
        label="Open Training",
        kind=ChatResponseActionKind.OPEN_PANEL,
        panel=ChatPanelTarget.TRAINING,
    )
    controller.add_agent_message(
        "Current proposed action",
        presentation_id="pruned-persisted-presentation",
        actions=(action,),
    )

    assert controller.prepare_for_turn() > 0
    assert controller.get_typed_history()[-1].has_active_actions is True
    persisted = controller.get_history()

    restored = ChatController()
    assert restored.restore_history(persisted) == len(persisted)
    restored_record = restored.get_typed_history()[-1]
    assert restored_record.action_state is ChatActionState.CONSUMED
    assert restored_record.has_active_actions is False
    selection = ChatResponseActionSelection.from_action(
        restored_record.presentation_id,
        restored_record.actions[0],
    )
    assert restored.resolve_and_consume_response_action(selection) is None
    assert restored.pruned_row_count == 0


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

    assert controller.resolve_response_action(forged) is None
    assert controller.resolve_response_action(forged_label) is None
    assert controller.resolve_response_action(exact) == action
    assert controller.get_typed_history()[0].has_active_actions is True
    assert controller.resolve_and_consume_response_action(forged) is None
    assert controller.resolve_and_consume_response_action(forged_label) is None
    resolution = controller.resolve_and_consume_response_action(exact)
    assert resolution is not None
    assert resolution.action == action
    assert resolution.source_record.has_active_actions is True
    assert controller.resolve_and_consume_response_action(exact) is None
