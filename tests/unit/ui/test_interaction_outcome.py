"""Tests for the UI-neutral interaction completion contract."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application.results import (
    ChangedState,
    CommandResult,
    ErrorType,
)
from XBrainLab.ui.interaction_outcome import (
    InteractionCompletionEvent,
    InteractionCompletionSession,
    InteractionCompletionStatus,
    InteractionOutcome,
    InteractionStatus,
    current_interaction_completion,
    reserve_interaction_continuation,
)


def _result(*, failed: bool = False) -> CommandResult:
    if failed:
        return CommandResult.failure_result(
            command_name="create_epoch",
            message="Epoch creation failed.",
            state={},
            changed_state=ChangedState(),
            error_type=ErrorType.PREPROCESSING,
            recoverable=True,
        )
    return CommandResult.success_result(
        command_name="create_epoch",
        message="Epoch creation completed.",
        state={},
        changed_state=ChangedState(epoch_changed=True),
    )


def _named_result(command_name: str, *, failed: bool = False) -> CommandResult:
    if failed:
        return CommandResult.failure_result(
            command_name=command_name,
            message=f"{command_name} requires confirmation.",
            state={},
            changed_state=ChangedState(),
            error_type=ErrorType.CONFIRMATION_REQUIRED,
            recoverable=True,
        )
    return CommandResult.success_result(
        command_name=command_name,
        message=f"{command_name} completed.",
        state={},
        changed_state=ChangedState(raw_changed=True),
    )


def test_async_acceptance_is_not_reported_as_completed():
    outcome = InteractionOutcome.accepted("Command scheduled.")

    assert outcome.status is InteractionStatus.ACCEPTED
    assert outcome.is_completed is False


def test_only_completed_outcome_reports_completed():
    outcome = InteractionOutcome.completed("Settings saved.")

    assert outcome.status is InteractionStatus.COMPLETED
    assert outcome.is_completed is True


def test_interaction_outcome_redacts_private_exception_context() -> None:
    private_path = "/srv/clinical/subject-17/events.tsv"

    outcome = InteractionOutcome.failed(
        f"Could not import {private_path}\r\nsubject_id=Alice-Smith."
    )

    assert private_path not in outcome.message
    assert "subject-17" not in outcome.message
    assert "Alice-Smith" not in outcome.message
    assert "events.tsv" in outcome.message
    assert "[REDACTED_PATH]" in outcome.message
    assert "[SUBJECT_REF:" in outcome.message
    assert "\n" not in outcome.message


def test_interaction_completion_event_redacts_private_exception_context() -> None:
    private_path = r"C:\Users\Alice\EEG\sub-P001\recording.edf"

    event = InteractionCompletionEvent(
        request_id="request-private",
        command_name="scan_source",
        status=InteractionCompletionStatus.FAILED,
        message=f"Could not inspect {private_path}; patient_id=Clinical-42.",
    )

    assert private_path not in event.message
    assert "sub-P001" not in event.message
    assert "Clinical-42" not in event.message
    assert ".edf" in event.message


def test_async_command_callback_emits_one_correlated_terminal_completion() -> None:
    terminal = []
    on_result = MagicMock(return_value=None)
    session = InteractionCompletionSession(
        request_id="request-1",
        command_name="create_epoch",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=object(),
        on_result=on_result,
        on_error=None,
    )
    callbacks.mark_started(True)

    callbacks.on_result(_result())

    on_result.assert_called_once()
    assert len(terminal) == 1
    assert terminal[0].request_id == "request-1"
    assert terminal[0].command_name == "create_epoch"
    assert terminal[0].status is InteractionCompletionStatus.COMPLETED
    assert session.is_terminal is True


def test_async_callback_exception_fails_session_deterministically() -> None:
    terminal = []
    session = InteractionCompletionSession(
        request_id="request-1",
        command_name="create_epoch",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=object(),
        on_result=MagicMock(side_effect=RuntimeError("callback exploded")),
        on_error=None,
    )
    callbacks.mark_started(True)

    callbacks.on_result(_result())

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert "callback" in terminal[0].message.lower()
    assert "exploded" not in terminal[0].message


def test_failed_command_result_reports_correlated_failure() -> None:
    terminal = []
    session = InteractionCompletionSession(
        request_id="request-1",
        command_name="create_epoch",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=object(),
        on_result=lambda _result: None,
        on_error=None,
    )
    callbacks.mark_started(True)

    callbacks.on_result(_result(failed=True))

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert terminal[0].message == "Epoch creation failed."


def test_confirmation_retry_defers_terminal_until_successor_command_completes() -> None:
    terminal = []
    retry_callbacks = []
    session = InteractionCompletionSession(
        request_id="request-retry",
        command_name="scan_source",
        on_terminal=terminal.append,
    )

    def _schedule_retry(_result: CommandResult) -> InteractionOutcome:
        callbacks = session.prepare_command(
            context=object(),
            result_command_name="apply_interpretation",
            on_result=lambda _result: InteractionOutcome.completed("Data imported."),
            on_error=None,
        )
        callbacks.mark_started(True)
        retry_callbacks.append(callbacks)
        return InteractionOutcome.accepted("Confirmed retry scheduled.")

    initial_callbacks = session.prepare_command(
        context=object(),
        result_command_name="review_interpretation",
        on_result=_schedule_retry,
        on_error=None,
    )
    initial_callbacks.mark_started(True)

    initial_callbacks.on_result(_named_result("review_interpretation", failed=True))

    assert terminal == []
    assert session.is_terminal is False

    retry_callbacks[0].on_result(_named_result("apply_interpretation"))

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.COMPLETED
    assert terminal[0].message == "Data imported."


def test_rejected_confirmation_reports_cancelled_and_ignores_late_result() -> None:
    terminal = []
    on_result = MagicMock(
        return_value=InteractionOutcome.cancelled("Import confirmation declined.")
    )
    session = InteractionCompletionSession(
        request_id="request-cancel",
        command_name="scan_source",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=object(),
        result_command_name="review_interpretation",
        on_result=on_result,
        on_error=None,
    )
    callbacks.mark_started(True)

    callbacks.on_result(_named_result("review_interpretation", failed=True))
    callbacks.on_result(_named_result("review_interpretation"))

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.CANCELLED
    assert terminal[0].message == "Import confirmation declined."
    on_result.assert_called_once()


def test_delayed_retry_lease_binds_successor_until_one_final_completion() -> None:
    terminal = []
    lease_holder = []
    retry_callbacks = []
    session = InteractionCompletionSession(
        request_id="request-delayed",
        command_name="scan_source",
        on_terminal=terminal.append,
    )

    def _reserve_retry(_result: CommandResult) -> InteractionOutcome:
        lease = reserve_interaction_continuation()
        assert lease is not None
        lease_holder.append(lease)
        return InteractionOutcome.accepted("Confirmed retry queued.")

    initial_callbacks = session.prepare_command(
        context=object(),
        result_command_name="apply_interpretation",
        on_result=_reserve_retry,
        on_error=None,
    )
    initial_callbacks.mark_started(True)
    initial_callbacks.on_result(_named_result("apply_interpretation", failed=True))

    assert terminal == []
    assert current_interaction_completion() is None

    def _start_retry() -> InteractionOutcome:
        assert current_interaction_completion() is session
        callbacks = session.prepare_command(
            context=object(),
            result_command_name="apply_interpretation",
            on_result=lambda _result: InteractionOutcome.completed("Data imported."),
            on_error=None,
        )
        callbacks.mark_started(True)
        retry_callbacks.append(callbacks)
        return InteractionOutcome.accepted("Confirmed retry started.")

    assert lease_holder[0].start(_start_retry) is True
    assert terminal == []

    retry_callbacks[0].on_result(_named_result("apply_interpretation"))
    retry_callbacks[0].on_result(_named_result("apply_interpretation"))

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.COMPLETED
    assert terminal[0].message == "Data imported."


def test_retry_that_completes_during_lease_start_still_settles_once() -> None:
    terminal = []
    lease_holder = []
    session = InteractionCompletionSession(
        request_id="request-immediate",
        command_name="scan_source",
        on_terminal=terminal.append,
    )

    def _reserve_retry(_result: CommandResult) -> InteractionOutcome:
        lease = reserve_interaction_continuation()
        assert lease is not None
        lease_holder.append(lease)
        return InteractionOutcome.accepted("Confirmed retry queued.")

    initial_callbacks = session.prepare_command(
        context=object(),
        result_command_name="apply_interpretation",
        on_result=_reserve_retry,
        on_error=None,
    )
    initial_callbacks.mark_started(True)
    initial_callbacks.on_result(_named_result("apply_interpretation", failed=True))

    def _start_and_finish_retry() -> InteractionOutcome:
        callbacks = session.prepare_command(
            context=object(),
            result_command_name="apply_interpretation",
            on_result=lambda _result: InteractionOutcome.completed("Data imported."),
            on_error=None,
        )
        callbacks.mark_started(True)
        callbacks.on_result(_named_result("apply_interpretation"))
        return InteractionOutcome.accepted("Confirmed retry started.")

    assert lease_holder[0].start(_start_and_finish_retry) is True

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.COMPLETED
    assert terminal[0].message == "Data imported."


def test_delayed_retry_start_failure_reports_failed_once_and_lease_is_one_shot() -> (
    None
):
    terminal = []
    lease_holder = []
    session = InteractionCompletionSession(
        request_id="request-start-failed",
        command_name="scan_source",
        on_terminal=terminal.append,
    )

    def _reserve_retry(_result: CommandResult) -> InteractionOutcome:
        lease = reserve_interaction_continuation()
        assert lease is not None
        lease_holder.append(lease)
        return InteractionOutcome.accepted("Confirmed retry queued.")

    callbacks = session.prepare_command(
        context=object(),
        result_command_name="apply_interpretation",
        on_result=_reserve_retry,
        on_error=None,
    )
    callbacks.mark_started(True)
    callbacks.on_result(_named_result("apply_interpretation", failed=True))
    retry = MagicMock(
        return_value=InteractionOutcome.blocked("Retry could not be started.")
    )

    assert lease_holder[0].start(retry) is False
    assert lease_holder[0].start(retry) is False

    assert retry.call_count == 1
    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert terminal[0].message == "Retry could not be started."


def test_delayed_retry_cancellation_reports_cancelled_once() -> None:
    terminal = []
    lease_holder = []
    session = InteractionCompletionSession(
        request_id="request-retry-cancelled",
        command_name="scan_source",
        on_terminal=terminal.append,
    )

    def _reserve_retry(_result: CommandResult) -> InteractionOutcome:
        lease = reserve_interaction_continuation()
        assert lease is not None
        lease_holder.append(lease)
        return InteractionOutcome.accepted("Confirmed retry queued.")

    callbacks = session.prepare_command(
        context=object(),
        result_command_name="apply_interpretation",
        on_result=_reserve_retry,
        on_error=None,
    )
    callbacks.mark_started(True)
    callbacks.on_result(_named_result("apply_interpretation", failed=True))

    assert (
        lease_holder[0].start(
            lambda: InteractionOutcome.cancelled("Confirmed retry was cancelled.")
        )
        is False
    )

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.CANCELLED
    assert terminal[0].message == "Confirmed retry was cancelled."


def test_cancelled_session_invalidates_pending_retry_lease() -> None:
    terminal = []
    lease_holder = []
    session = InteractionCompletionSession(
        request_id="request-stale-retry",
        command_name="scan_source",
        on_terminal=terminal.append,
    )

    def _reserve_retry(_result: CommandResult) -> InteractionOutcome:
        lease = reserve_interaction_continuation()
        assert lease is not None
        lease_holder.append(lease)
        return InteractionOutcome.accepted("Confirmed retry queued.")

    callbacks = session.prepare_command(
        context=object(),
        result_command_name="apply_interpretation",
        on_result=_reserve_retry,
        on_error=None,
    )
    callbacks.mark_started(True)
    callbacks.on_result(_named_result("apply_interpretation", failed=True))
    session.cancel("The handoff was stopped.")
    late_retry = MagicMock(return_value=InteractionOutcome.accepted("Late retry."))

    assert lease_holder[0].start(late_retry) is False

    assert late_retry.call_count == 0
    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.CANCELLED


def test_callback_claiming_follow_up_without_owner_fails_session() -> None:
    terminal = []
    session = InteractionCompletionSession(
        request_id="request-no-successor",
        command_name="scan_source",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=object(),
        result_command_name="review_interpretation",
        on_result=lambda _result: InteractionOutcome.accepted(
            "Retry was reported but not started."
        ),
        on_error=None,
    )
    callbacks.mark_started(True)

    callbacks.on_result(_named_result("review_interpretation", failed=True))

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert terminal[0].message == (
        "The UI command did not start its reported follow-up action."
    )


def test_continuation_cannot_be_reserved_without_an_active_command() -> None:
    session = InteractionCompletionSession(
        request_id="request-idle",
        command_name="scan_source",
        on_terminal=lambda _event: None,
    )

    assert session.reserve_continuation() is None


def test_mismatched_command_result_fails_session_once_and_ignores_late_result() -> None:
    terminal = []
    on_result = MagicMock(return_value=None)
    session = InteractionCompletionSession(
        request_id="request-1",
        command_name="create_epoch",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=object(),
        on_result=on_result,
        on_error=None,
    )
    callbacks.mark_started(True)
    mismatched = CommandResult.success_result(
        command_name="generate_dataset",
        message="Wrong command completed.",
        state={},
        changed_state=ChangedState(datasets_changed=True),
    )

    callbacks.on_result(mismatched)

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert terminal[0].message == (
        "The asynchronous UI command result did not match the scheduled command."
    )
    assert session.is_terminal is True
    on_result.assert_not_called()

    callbacks.on_result(_result())
    assert len(terminal) == 1
    on_result.assert_not_called()


def test_finished_without_result_or_error_fails_session_once() -> None:
    terminal = []
    session = InteractionCompletionSession(
        request_id="request-finished-only",
        command_name="create_epoch",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=object(),
        on_result=lambda _result: None,
        on_error=None,
    )
    callbacks.mark_started(True)

    callbacks.on_finished()
    callbacks.on_finished()

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert terminal[0].message == (
        "The asynchronous UI command finished without returning a result."
    )


@pytest.mark.parametrize("terminal_signal", ["result", "error"])
def test_finished_after_result_or_error_does_not_repeat_terminal_callback(
    terminal_signal: str,
) -> None:
    terminal = []
    session = InteractionCompletionSession(
        request_id=f"request-{terminal_signal}",
        command_name="create_epoch",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=object(),
        on_result=lambda _result: None,
        on_error=lambda _error: None,
    )
    callbacks.mark_started(True)

    if terminal_signal == "result":
        callbacks.on_result(_result())
    else:
        assert callbacks.on_error is not None
        callbacks.on_error((RuntimeError, RuntimeError("failed"), "traceback"))
    callbacks.on_finished()

    assert len(terminal) == 1
    expected = (
        InteractionCompletionStatus.COMPLETED
        if terminal_signal == "result"
        else InteractionCompletionStatus.FAILED
    )
    assert terminal[0].status is expected


def test_cancelled_session_reports_once_and_rejects_late_command_result() -> None:
    terminal = []
    on_result = MagicMock()
    session = InteractionCompletionSession(
        request_id="request-1",
        command_name="create_epoch",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=object(),
        on_result=on_result,
        on_error=None,
    )
    callbacks.mark_started(True)

    session.cancel("The pending settings command was cancelled.")
    callbacks.on_result(_result())

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.CANCELLED
    assert terminal[0].request_id == "request-1"
    on_result.assert_not_called()


def test_deleted_async_context_fails_pending_session(qtbot) -> None:
    owner = QWidget()
    qtbot.addWidget(owner)
    terminal = []
    session = InteractionCompletionSession(
        request_id="request-1",
        command_name="create_epoch",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=owner,
        on_result=lambda _result: None,
        on_error=None,
    )
    callbacks.mark_started(True)

    owner.deleteLater()
    qtbot.waitUntil(lambda: bool(terminal))

    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert session.is_terminal is True
