"""Product-host contract for typed assistant workflow handoffs."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolutionStatus,
    WorkflowUiHandoffSurfaceKind,
    build_tool_workflow_handoff,
    workflow_ui_handoff_routes,
)
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.result_contract import UiRequest, UiRequestKind
from XBrainLab.ui.components.workflow_surface_router import WorkflowPanel
from XBrainLab.ui.components.workflow_ui_handoff_host import WorkflowUiHandoffHost
from XBrainLab.ui.interaction_outcome import (
    InteractionCompletionEvent,
    InteractionCompletionStatus,
    InteractionOutcome,
    current_interaction_completion,
)


def _main_window() -> Any:
    status_bar = MagicMock()
    window = SimpleNamespace(
        statusBar=MagicMock(return_value=status_bar),
        dataset_panel=SimpleNamespace(
            action_handler=SimpleNamespace(
                import_data=MagicMock(
                    return_value=InteractionOutcome.completed("Data imported.")
                ),
                review_current_import=MagicMock(
                    return_value=InteractionOutcome.completed("Data imported.")
                ),
            ),
            sidebar=SimpleNamespace(
                open_channel_selection=MagicMock(
                    return_value=InteractionOutcome.completed("Channels selected.")
                ),
                open_electrode_layout=MagicMock(
                    return_value=InteractionOutcome.completed(
                        "Electrode layout applied."
                    )
                ),
            ),
        ),
        preprocess_panel=SimpleNamespace(
            sidebar=SimpleNamespace(
                open_epoching=MagicMock(
                    return_value=InteractionOutcome.completed(
                        "Epoch settings were saved."
                    )
                )
            )
        ),
        training_panel=SimpleNamespace(
            sidebar=SimpleNamespace(
                split_data=MagicMock(
                    return_value=InteractionOutcome.completed("Dataset created.")
                ),
                training_setting=MagicMock(
                    return_value=InteractionOutcome.completed(
                        "Training settings were saved."
                    )
                ),
                select_model=MagicMock(
                    return_value=InteractionOutcome.completed("Model selected.")
                ),
            )
        ),
        visualization_panel=SimpleNamespace(
            compute_saliency=MagicMock(
                return_value=InteractionOutcome.completed("Saliency ready.")
            ),
            sidebar=SimpleNamespace(
                set_saliency=MagicMock(
                    return_value=InteractionOutcome.cancelled(
                        "Saliency settings were cancelled."
                    )
                ),
            ),
        ),
    )
    window.navigation_calls = []
    window.navigation_callbacks = []
    window.navigation_error = None

    def switch_page(index: int, *, on_ready, on_failed) -> bool:
        window.navigation_calls.append(index)
        window.navigation_callbacks.append((on_ready, on_failed))
        if window.navigation_error is not None:
            raise window.navigation_error
        on_ready(None)
        return True

    window.switch_page = switch_page
    return window


@pytest.mark.parametrize(
    ("tool_name", "command", "panel_index", "expected_method"),
    [
        (
            "import_eeg_data",
            CommandName.SCAN_SOURCE,
            0,
            "dataset_panel.action_handler.import_data",
        ),
        (
            "select_channels",
            CommandName.PREPROCESS,
            0,
            "dataset_panel.sidebar.open_channel_selection",
        ),
        (
            "set_montage",
            CommandName.APPLY_MONTAGE,
            0,
            "dataset_panel.sidebar.open_electrode_layout",
        ),
        (
            "create_epochs",
            CommandName.CREATE_EPOCH,
            1,
            "preprocess_panel.sidebar.open_epoching",
        ),
        (
            "configure_dataset_split",
            CommandName.CONFIGURE_DATASET_SPLIT,
            2,
            "training_panel.sidebar.split_data",
        ),
        (
            "select_model",
            CommandName.CONFIGURE_TRAINING,
            2,
            "training_panel.sidebar.select_model",
        ),
        (
            "configure_training",
            CommandName.CONFIGURE_TRAINING,
            2,
            "training_panel.sidebar.training_setting",
        ),
        (
            "compute_saliency",
            CommandName.SALIENCY,
            4,
            "visualization_panel.compute_saliency",
        ),
    ],
)
def test_registered_gui_tools_reach_their_existing_surface(
    tool_name,
    command,
    panel_index,
    expected_method,
) -> None:
    """Use real tool producers, not hand-authored legacy handoff payloads."""
    tool = next(tool for tool in get_all_tools() if tool.name == tool_name)
    effect = tool.execute(None)
    assert isinstance(effect, UiRequest)
    assert effect.kind is UiRequestKind.WORKFLOW_HANDOFF
    request = build_tool_workflow_handoff(effect.params)
    assert request is not None
    assert request.command is command
    assert request.tool_name == tool_name
    window = _main_window()
    host = WorkflowUiHandoffHost(window)

    result = host.open(request)

    assert result.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    assert result.matches(request)
    assert host.active_request is None
    assert window.navigation_calls == [panel_index]
    method = window
    for attribute in expected_method.split("."):
        method = getattr(method, attribute)
    method.assert_called_once_with()


def test_host_route_table_is_derived_from_typed_handoff_descriptors() -> None:
    host = WorkflowUiHandoffHost(_main_window())

    for descriptor in workflow_ui_handoff_routes():
        route = host._router.route_for(descriptor.command.value)

        assert route is not None
        assert route.panel.value == descriptor.target_panel.value
        assert (route.open_surface is not None) is (
            descriptor.surface_kind
            in {
                WorkflowUiHandoffSurfaceKind.DIALOG,
                WorkflowUiHandoffSurfaceKind.ACTION,
            }
        )


def _scheduled_acceptance() -> InteractionOutcome:
    completion = current_interaction_completion()
    assert completion is not None
    callbacks = completion.prepare_command(
        context=object(),
        on_result=lambda _result: None,
        on_error=None,
    )
    callbacks.mark_started(True)
    return InteractionOutcome.accepted("Epoch creation was scheduled.")


def test_completed_modal_routes_through_concrete_epoch_adapter() -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)

    request = WorkflowUiHandoffRequest.for_decision(
        "create_epoch",
        decision_fields=("epoch_window",),
    )
    outcome = host.open(request)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    assert outcome.request_id == request.request_id
    assert outcome.command_name == "create_epoch"
    assert outcome.decision_fields == ("epoch_window",)
    assert window.navigation_calls == [1]
    window.preprocess_panel.sidebar.open_epoching.assert_called_once_with()
    window.statusBar.return_value.showMessage.assert_called_with(
        "Opened Preprocess panel."
    )


def test_unmaterialized_modal_handoff_defers_without_touching_placeholder() -> None:
    """Workflow routing must not inspect a panel until async preparation completes."""
    window = _main_window()
    navigation_calls = []

    def _switch_page(index: int, *, on_ready, on_failed) -> bool:
        navigation_calls.append((index, on_ready, on_failed))
        return False

    window.switch_page = _switch_page
    window.preprocess_panel = SimpleNamespace()
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision(
        "create_epoch",
        decision_fields=("epoch_window",),
    )

    outcome = host.open(request)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
    assert host.active_request is request
    assert len(navigation_calls) == 1
    assert navigation_calls[0][0] == 1
    assert callable(navigation_calls[0][1])
    assert callable(navigation_calls[0][2])
    window.statusBar.return_value.showMessage.assert_called_with(
        "Opening Preprocess..."
    )


def test_epoch_handoff_leaves_choices_to_existing_dialog() -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision(
        "create_epoch",
        decision_fields=("epoch_window",),
    )

    outcome = host.open(request)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    window.preprocess_panel.sidebar.open_epoching.assert_called_once_with()


def test_dataset_handoff_leaves_choices_to_existing_dialog() -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision(
        "configure_dataset_split",
        decision_fields=("split_strategy",),
    )

    outcome = host.open(request)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    window.training_panel.sidebar.split_data.assert_called_once_with()


def test_training_handoff_stops_when_model_selection_is_cancelled() -> None:
    window = _main_window()
    window.training_panel.sidebar.select_model.return_value = (
        InteractionOutcome.cancelled("Model selection was cancelled.")
    )
    host = WorkflowUiHandoffHost(window)
    tool = next(tool for tool in get_all_tools() if tool.name == "select_model")
    effect = tool.execute(None)
    assert isinstance(effect, UiRequest)
    request = build_tool_workflow_handoff(effect.params)
    assert request is not None

    outcome = host.open(request)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.CANCELLED
    assert outcome.matches(request)
    assert host.active_request is None
    window.training_panel.sidebar.select_model.assert_called_once_with()
    window.training_panel.sidebar.training_setting.assert_not_called()


def test_training_options_handoff_preserves_cancelled_outcome() -> None:
    window = _main_window()
    window.training_panel.sidebar.training_setting.return_value = (
        InteractionOutcome.cancelled("Training settings were cancelled.")
    )
    host = WorkflowUiHandoffHost(window)
    tool = next(tool for tool in get_all_tools() if tool.name == "configure_training")
    effect = tool.execute(None)
    assert isinstance(effect, UiRequest)
    request = build_tool_workflow_handoff(effect.params)
    assert request is not None

    outcome = host.open(request)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.CANCELLED
    assert outcome.matches(request)
    assert host.active_request is None
    window.training_panel.sidebar.training_setting.assert_called_once_with()
    window.training_panel.sidebar.select_model.assert_not_called()


@pytest.mark.parametrize(
    ("command_name", "panel_index", "expected_status"),
    [
        ("scan_source", 0, WorkflowUiHandoffResolutionStatus.COMPLETED),
        ("configure_dataset_split", 2, WorkflowUiHandoffResolutionStatus.COMPLETED),
        (
            "configure_training",
            2,
            WorkflowUiHandoffResolutionStatus.COMPLETED,
        ),
        ("saliency", 4, WorkflowUiHandoffResolutionStatus.COMPLETED),
    ],
)
def test_host_owns_modal_route_table_and_outcome_conversion(
    command_name: str,
    panel_index: int,
    expected_status: WorkflowUiHandoffResolutionStatus,
) -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)

    request = (
        WorkflowUiHandoffRequest.for_action(command_name)
        if command_name == "saliency"
        else WorkflowUiHandoffRequest.for_decision(
            command_name,
            decision_fields=("training_options",)
            if command_name == "configure_training"
            else (),
        )
    )
    outcome = host.open(request)

    assert outcome.status is expected_status
    assert window.navigation_calls == [panel_index]
    if command_name == "saliency":
        window.visualization_panel.compute_saliency.assert_called_once_with()
        window.visualization_panel.sidebar.set_saliency.assert_not_called()


def test_epoch_handoff_retains_request_until_correlated_terminal_completion() -> None:
    window = _main_window()
    scheduled_callbacks = []

    def _schedule_command() -> InteractionOutcome:
        completion = current_interaction_completion()
        assert completion is not None
        callbacks = completion.prepare_command(
            context=object(),
            on_result=lambda _result: None,
            on_error=None,
        )
        callbacks.mark_started(True)
        scheduled_callbacks.append(callbacks)
        return InteractionOutcome.accepted("Epoch creation was scheduled.")

    window.preprocess_panel.sidebar.open_epoching.side_effect = _schedule_command
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    terminal = []

    initial = host.open(request, on_terminal=terminal.append)

    assert initial.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
    assert host.active_request is request

    scheduled_callbacks[0].on_result(
        CommandResult.success_result(
            command_name="create_epoch",
            message="Epoch creation completed.",
            state={},
            changed_state=ChangedState(epoch_changed=True),
        )
    )

    assert len(terminal) == 1
    assert terminal[0].status is WorkflowUiHandoffResolutionStatus.COMPLETED
    assert terminal[0].request_id == request.request_id
    assert host.active_request is None


def test_epoch_handoff_command_mismatch_fails_instead_of_waiting_forever() -> None:
    window = _main_window()
    scheduled_callbacks = []

    def _schedule_command() -> InteractionOutcome:
        completion = current_interaction_completion()
        assert completion is not None
        callbacks = completion.prepare_command(
            context=object(),
            on_result=lambda _result: None,
            on_error=None,
        )
        callbacks.mark_started(True)
        scheduled_callbacks.append(callbacks)
        return InteractionOutcome.accepted("Epoch creation was scheduled.")

    window.preprocess_panel.sidebar.open_epoching.side_effect = _schedule_command
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    terminal = []
    initial = host.open(request, on_terminal=terminal.append)

    scheduled_callbacks[0].on_result(
        CommandResult.success_result(
            command_name="configure_dataset_split",
            message="Unexpected dataset completion.",
            state={},
            changed_state=ChangedState(datasets_changed=True),
        )
    )

    assert initial.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
    assert len(terminal) == 1
    assert terminal[0].status is WorkflowUiHandoffResolutionStatus.FAILED
    assert host.active_request is None


def test_stop_abandons_pending_host_and_late_command_callback_is_harmless() -> None:
    window = _main_window()
    scheduled_callbacks = []

    def _schedule_command() -> InteractionOutcome:
        completion = current_interaction_completion()
        assert completion is not None
        callbacks = completion.prepare_command(
            context=object(),
            on_result=lambda _result: None,
            on_error=None,
        )
        callbacks.mark_started(True)
        scheduled_callbacks.append(callbacks)
        return InteractionOutcome.accepted("Epoch creation was scheduled.")

    window.preprocess_panel.sidebar.open_epoching.side_effect = _schedule_command
    host = WorkflowUiHandoffHost(window)
    terminal = []
    host.open(
        WorkflowUiHandoffRequest.for_decision("create_epoch"),
        on_terminal=terminal.append,
    )

    host.abandon_active()
    scheduled_callbacks[0].on_result(
        CommandResult.success_result(
            command_name="create_epoch",
            message="Late epoch completion.",
            state={},
            changed_state=ChangedState(epoch_changed=True),
        )
    )

    assert terminal == []
    assert host.active_request is None


def test_mismatched_async_callback_is_rejected_without_resolving_current_request() -> (
    None
):
    window = _main_window()
    window.preprocess_panel.sidebar.open_epoching.side_effect = _scheduled_acceptance
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    terminal = []
    host.open(request, on_terminal=terminal.append)

    accepted = host.resolve_terminal(
        InteractionCompletionEvent(
            request_id="stale-request",
            command_name=request.command_name,
            status=InteractionCompletionStatus.COMPLETED,
        )
    )

    assert accepted is False
    assert terminal == []
    assert host.active_request is request

    mismatched_command = host.resolve_terminal(
        InteractionCompletionEvent(
            request_id=request.request_id,
            command_name="configure_dataset_split",
            status=InteractionCompletionStatus.COMPLETED,
        )
    )

    assert mismatched_command is False
    assert terminal == []
    assert host.active_request is request


def test_malformed_async_callback_fails_current_request_instead_of_sticking() -> None:
    window = _main_window()
    window.preprocess_panel.sidebar.open_epoching.side_effect = _scheduled_acceptance
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    terminal = []
    host.open(request, on_terminal=terminal.append)

    accepted = host.resolve_terminal({"status": "completed"})

    assert accepted is True
    assert terminal[0].status is WorkflowUiHandoffResolutionStatus.FAILED
    assert host.active_request is None


def test_rejected_terminal_callback_retains_delivery_for_explicit_retry() -> None:
    window = _main_window()
    window.preprocess_panel.sidebar.open_epoching.side_effect = _scheduled_acceptance
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    deliveries = []

    def _reject_once(resolution):
        deliveries.append(resolution)
        return len(deliveries) > 1

    host.open(request, on_terminal=_reject_once)

    assert (
        host.resolve_terminal(
            InteractionCompletionEvent(
                request_id=request.request_id,
                command_name=request.command_name,
                status=InteractionCompletionStatus.COMPLETED,
            )
        )
        is False
    )
    assert host.active_request is request

    assert host.retry_terminal_delivery() is True
    assert deliveries[0] is deliveries[1]
    assert host.active_request is None


def test_epoch_handoff_without_registered_command_returns_failed_resolution() -> None:
    window = _main_window()
    window.preprocess_panel.sidebar.open_epoching.return_value = (
        InteractionOutcome.accepted("No applicable change was selected.")
    )
    host = WorkflowUiHandoffHost(window)

    outcome = host.open(WorkflowUiHandoffRequest.for_decision("create_epoch"))

    assert outcome.status is WorkflowUiHandoffResolutionStatus.FAILED
    assert host.active_request is None


def test_montage_handoff_uses_existing_dialog_without_supplied_choices() -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision(
        "apply_montage",
        decision_fields=("channel_mapping",),
    )

    outcome = host.open(request)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    assert window.navigation_calls == [0]
    window.dataset_panel.sidebar.open_electrode_layout.assert_called_once_with()
    window.statusBar.return_value.showMessage.assert_called_with(
        "Opened Dataset panel."
    )
    route = host._router.route_for("apply_montage")
    assert route is not None
    assert route.panel is WorkflowPanel.DATASET


def test_montage_navigation_failure_returns_correlated_failed_resolution() -> None:
    window = _main_window()
    window.navigation_error = RuntimeError("private navigation detail")
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("apply_montage")

    outcome = host.open(request)

    assert outcome.request_id == request.request_id
    assert outcome.status is WorkflowUiHandoffResolutionStatus.FAILED
    assert "private navigation detail" not in outcome.message
    window.dataset_panel.sidebar.open_electrode_layout.assert_not_called()


def test_montage_handoff_preserves_cancelled_dataset_outcome() -> None:
    window = _main_window()
    window.dataset_panel.sidebar.open_electrode_layout.return_value = (
        InteractionOutcome.cancelled("Electrode layout was cancelled.")
    )
    host = WorkflowUiHandoffHost(window)

    outcome = host.open(WorkflowUiHandoffRequest.for_decision("apply_montage"))

    assert outcome.status is WorkflowUiHandoffResolutionStatus.CANCELLED
    window.dataset_panel.sidebar.open_electrode_layout.assert_called_once_with()


def test_montage_dialog_failure_returns_correlated_failed_resolution() -> None:
    window = _main_window()
    window.dataset_panel.sidebar.open_electrode_layout.side_effect = RuntimeError(
        "private montage detail"
    )
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("apply_montage")

    outcome = host.open(request)

    assert outcome.request_id == request.request_id
    assert outcome.status is WorkflowUiHandoffResolutionStatus.FAILED
    assert "private montage detail" not in outcome.message


def test_invalid_dialog_outcome_fails_closed() -> None:
    window = _main_window()
    window.preprocess_panel.sidebar.open_epoching.return_value = True
    host = WorkflowUiHandoffHost(window)

    outcome = host.open(WorkflowUiHandoffRequest.for_decision("create_epoch"))

    assert outcome.status is WorkflowUiHandoffResolutionStatus.FAILED
    assert "valid outcome" in outcome.message


def test_failed_modal_outcome_is_preserved_without_claiming_completion() -> None:
    window = _main_window()
    window.preprocess_panel.sidebar.open_epoching.return_value = (
        InteractionOutcome.failed("Epoch settings could not be opened.")
    )
    host = WorkflowUiHandoffHost(window)

    outcome = host.open(WorkflowUiHandoffRequest.for_decision("create_epoch"))

    assert outcome.status is WorkflowUiHandoffResolutionStatus.FAILED
    assert outcome.message == "Epoch settings could not be opened."


def test_host_rejects_untyped_payload_instead_of_inferring_command_text() -> None:
    host = WorkflowUiHandoffHost(_main_window())

    with pytest.raises(TypeError, match="WorkflowUiHandoffRequest"):
        cast(Any, host).open(
            {"tool_name": "create_epoch", "command": "configure_dataset_split"}
        )
