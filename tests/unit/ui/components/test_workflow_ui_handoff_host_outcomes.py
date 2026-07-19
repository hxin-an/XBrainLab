"""Lifecycle outcomes for modal handoffs deferred by lazy panel loading."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.ui.components.workflow_ui_handoff_host import WorkflowUiHandoffHost
from XBrainLab.ui.interaction_outcome import (
    InteractionOutcome,
    current_interaction_completion,
)
from XBrainLab.ui.panel_navigation import PanelPreparationFailure


class _DeferredWindow:
    def __init__(self, open_epoching: Callable[[], InteractionOutcome]) -> None:
        self.ready_callbacks: list[Callable[[object], None]] = []
        self.failed_callbacks: list[Callable[[object], None]] = []
        self.navigation_calls: list[int] = []
        self.navigation_sessions: list[Any] = []
        self.status_bar = MagicMock()
        self.preprocess_panel = SimpleNamespace(
            sidebar=SimpleNamespace(
                open_epoching=MagicMock(side_effect=open_epoching),
            )
        )

    def switch_page(
        self,
        index: int,
        *,
        on_ready: Callable[[object], None] | None = None,
        on_failed: Callable[[object], None] | None = None,
    ) -> bool:
        self.navigation_calls.append(index)
        self.navigation_sessions.append(current_interaction_completion())
        if on_ready is not None:
            self.ready_callbacks.append(on_ready)
        if on_failed is not None:
            self.failed_callbacks.append(on_failed)
        return False

    def statusBar(self) -> Any:
        return self.status_bar

    def deliver_ready(self) -> None:
        self.ready_callbacks[0](self.preprocess_panel)


class _FailingDeferredWindow(_DeferredWindow):
    def switch_page(
        self,
        index: int,
        *,
        on_ready: Callable[[object], None] | None = None,
        on_failed: Callable[[object], None] | None = None,
    ) -> bool:
        self.navigation_calls.append(index)
        self.navigation_sessions.append(current_interaction_completion())
        if on_ready is not None:
            self.ready_callbacks.append(on_ready)
        if on_failed is not None:
            self.failed_callbacks.append(on_failed)
        raise RuntimeError("panel preparation could not start")


class _SynchronouslyFailedWindow(_DeferredWindow):
    def switch_page(
        self,
        index: int,
        *,
        on_ready: Callable[[object], None] | None = None,
        on_failed: Callable[[object], None] | None = None,
    ) -> bool:
        self.navigation_calls.append(index)
        self.navigation_sessions.append(current_interaction_completion())
        if on_ready is not None:
            self.ready_callbacks.append(on_ready)
        if on_failed is not None:
            self.failed_callbacks.append(on_failed)
            on_failed(
                PanelPreparationFailure(
                    panel_index=index,
                    panel_name="Preprocess",
                    message="Could not open Preprocess.",
                )
            )
        return False


def test_deferred_modal_rebinds_original_session_until_async_terminal() -> None:
    scheduled_callbacks: list[Any] = []
    bound_sessions: list[Any] = []

    def _open_epoching() -> InteractionOutcome:
        completion = current_interaction_completion()
        assert completion is not None
        bound_sessions.append(completion)

        def _on_result(_result: CommandResult) -> None:
            return None

        callbacks = completion.prepare_command(
            context=object(),
            on_result=_on_result,
            on_error=None,
        )
        callbacks.mark_started(True)
        scheduled_callbacks.append(callbacks)
        return InteractionOutcome.accepted("Epoch creation was scheduled.")

    window = _DeferredWindow(_open_epoching)
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision(
        "create_epoch",
        decision_fields=("epoch_window",),
    )
    terminal: list[WorkflowUiHandoffResolution] = []

    initial = host.open(request, on_terminal=terminal.append)

    assert initial.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
    assert initial.status.is_terminal is False
    assert host.active_request is request
    assert terminal == []
    window.preprocess_panel.sidebar.open_epoching.assert_not_called()

    window.deliver_ready()

    assert host.active_request is request
    assert terminal == []
    assert len(bound_sessions) == 1
    assert bound_sessions[0] is window.navigation_sessions[0]
    assert bound_sessions[0].request_id == request.request_id
    assert bound_sessions[0].command_name == request.command_name
    window.preprocess_panel.sidebar.open_epoching.assert_called_once_with()

    scheduled_callbacks[0].on_result(
        CommandResult.success_result(
            command_name="create_epoch",
            message="Epoch creation completed.",
            state={},
            changed_state=ChangedState(epoch_changed=True),
        )
    )
    window.deliver_ready()
    scheduled_callbacks[0].on_result(
        CommandResult.success_result(
            command_name="create_epoch",
            message="Duplicate epoch completion.",
            state={},
            changed_state=ChangedState(epoch_changed=True),
        )
    )

    assert len(terminal) == 1
    assert terminal[0].status is WorkflowUiHandoffResolutionStatus.COMPLETED
    assert terminal[0].matches(request)
    assert host.active_request is None
    window.preprocess_panel.sidebar.open_epoching.assert_called_once_with()


@pytest.mark.parametrize(
    ("modal_outcome", "expected_status"),
    [
        (
            InteractionOutcome.completed("Epoch settings were applied."),
            WorkflowUiHandoffResolutionStatus.COMPLETED,
        ),
        (
            InteractionOutcome.cancelled("Epoch settings were cancelled."),
            WorkflowUiHandoffResolutionStatus.CANCELLED,
        ),
        (
            InteractionOutcome.failed("Epoch settings could not be opened."),
            WorkflowUiHandoffResolutionStatus.FAILED,
        ),
    ],
)
def test_deferred_modal_delivers_one_immediate_terminal_outcome(
    modal_outcome: InteractionOutcome,
    expected_status: WorkflowUiHandoffResolutionStatus,
) -> None:
    window = _DeferredWindow(lambda: modal_outcome)
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    terminal: list[WorkflowUiHandoffResolution] = []

    initial = host.open(request, on_terminal=terminal.append)
    window.deliver_ready()
    window.deliver_ready()

    assert initial.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
    assert len(terminal) == 1
    assert terminal[0].status is expected_status
    assert terminal[0].matches(request)
    assert host.active_request is None
    window.preprocess_panel.sidebar.open_epoching.assert_called_once_with()


def test_deferred_modal_acceptance_without_command_fails_terminally() -> None:
    window = _DeferredWindow(
        lambda: InteractionOutcome.accepted("Epoch settings were accepted.")
    )
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    terminal: list[WorkflowUiHandoffResolution] = []

    initial = host.open(request, on_terminal=terminal.append)
    window.deliver_ready()
    window.deliver_ready()

    assert initial.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
    assert len(terminal) == 1
    assert terminal[0].status is WorkflowUiHandoffResolutionStatus.FAILED
    assert terminal[0].matches(request)
    assert host.active_request is None
    window.preprocess_panel.sidebar.open_epoching.assert_called_once_with()


def test_stop_before_ready_invalidates_modal_callback_without_terminal_delivery() -> (
    None
):
    window = _DeferredWindow(
        lambda: InteractionOutcome.completed("Epoch settings were applied.")
    )
    host = WorkflowUiHandoffHost(window)
    terminal: list[WorkflowUiHandoffResolution] = []
    initial = host.open(
        WorkflowUiHandoffRequest.for_decision("create_epoch"),
        on_terminal=terminal.append,
    )

    host.abandon_active()
    window.failed_callbacks[0](
        PanelPreparationFailure(
            panel_index=1,
            panel_name="Preprocess",
            message="Could not open Preprocess.",
        )
    )
    window.deliver_ready()

    assert initial.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
    assert terminal == []
    assert host.active_request is None
    window.preprocess_panel.sidebar.open_epoching.assert_not_called()


def test_prepare_failure_is_terminal_and_invalidates_late_ready_callback() -> None:
    window = _DeferredWindow(
        lambda: InteractionOutcome.completed("Epoch settings were applied.")
    )
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    terminal: list[WorkflowUiHandoffResolution] = []

    initial = host.open(request, on_terminal=terminal.append)

    assert initial.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
    assert len(window.failed_callbacks) == 1

    window.failed_callbacks[0](
        PanelPreparationFailure(
            panel_index=1,
            panel_name="Preprocess",
            message="Could not open Preprocess.",
        )
    )
    window.deliver_ready()

    assert len(terminal) == 1
    assert terminal[0].status is WorkflowUiHandoffResolutionStatus.FAILED
    assert terminal[0].matches(request)
    assert host.active_request is None
    window.preprocess_panel.sidebar.open_epoching.assert_not_called()


def test_synchronous_prepare_start_failure_returns_correlated_terminal() -> None:
    window = _SynchronouslyFailedWindow(
        lambda: InteractionOutcome.completed("Epoch settings were applied.")
    )
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")

    outcome = host.open(request)
    window.deliver_ready()

    assert outcome.status is WorkflowUiHandoffResolutionStatus.FAILED
    assert outcome.matches(request)
    assert host.active_request is None
    window.preprocess_panel.sidebar.open_epoching.assert_not_called()


def test_navigation_preparation_failure_invalidates_late_ready_callback() -> None:
    window = _FailingDeferredWindow(
        lambda: InteractionOutcome.completed("Epoch settings were applied.")
    )
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")

    initial = host.open(request)
    window.deliver_ready()

    assert initial.status is WorkflowUiHandoffResolutionStatus.FAILED
    assert initial.matches(request)
    assert host.active_request is None
    window.preprocess_panel.sidebar.open_epoching.assert_not_called()


def test_deferred_panel_only_navigation_remains_terminal() -> None:
    window = _DeferredWindow(
        lambda: InteractionOutcome.completed("This modal must not open.")
    )
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("evaluate")

    outcome = host.open(request)
    window.failed_callbacks[0](
        PanelPreparationFailure(
            panel_index=3,
            panel_name="Evaluation",
            message="Could not open Evaluation.",
        )
    )
    window.deliver_ready()

    assert outcome.status is WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI
    assert outcome.matches(request)
    assert host.active_request is None
    assert window.navigation_calls == [3]
    window.preprocess_panel.sidebar.open_epoching.assert_not_called()
