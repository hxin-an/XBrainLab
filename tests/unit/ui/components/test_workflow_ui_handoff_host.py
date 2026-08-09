"""Product-host contract for typed assistant workflow handoffs."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ApplicationStateSnapshot,
    InterpretationStateSnapshot,
)
from XBrainLab.backend.application.view_publication import (
    ApplicationViewPublication,
    InterpretationReviewIdentity,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolutionStatus,
    WorkflowUiHandoffSurfaceKind,
    workflow_ui_handoff_routes,
)
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
        switch_page=MagicMock(),
        statusBar=MagicMock(return_value=status_bar),
        dataset_panel=SimpleNamespace(
            action_handler=SimpleNamespace(
                import_data=MagicMock(
                    return_value=InteractionOutcome.completed("Data imported.")
                ),
                review_current_import=MagicMock(
                    return_value=InteractionOutcome.completed("Data imported.")
                ),
            )
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
                configure_training=MagicMock(
                    return_value=InteractionOutcome.completed(
                        "Training configuration was saved."
                    )
                ),
                select_model=MagicMock(
                    return_value=InteractionOutcome.completed("Model selected.")
                ),
            )
        ),
        visualization_panel=SimpleNamespace(
            sidebar=SimpleNamespace(
                set_montage=MagicMock(
                    return_value=InteractionOutcome.completed("Montage set.")
                ),
                set_saliency=MagicMock(
                    return_value=InteractionOutcome.cancelled(
                        "Saliency settings were cancelled."
                    )
                ),
            )
        ),
    )
    return window


def test_host_route_table_is_derived_from_typed_handoff_descriptors() -> None:
    host = WorkflowUiHandoffHost(_main_window())

    for descriptor in workflow_ui_handoff_routes():
        route = host._router.route_for(descriptor.command.value)

        assert route is not None
        assert route.panel.value == descriptor.target_panel.value
        assert (route.open_surface is not None) is (
            descriptor.surface_kind is WorkflowUiHandoffSurfaceKind.DIALOG
        )


def _review_identity() -> InterpretationReviewIdentity:
    return InterpretationReviewIdentity(
        publication_generation=9,
        scan_id="scan-a",
        candidate_id="candidate-a",
    )


def _publication(
    state: ApplicationStateSnapshot,
    *,
    usable: bool = True,
) -> ApplicationViewPublication:
    return ApplicationViewPublication(
        generation=1,
        revision=1,
        state=state,
        capabilities=build_capability_policy(state),
        verified=usable,
        stale=not usable,
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


def test_current_data_import_opens_file_chooser_from_empty_state() -> None:
    state = ApplicationStateSnapshot.empty()
    window = _main_window()
    publication = _publication(state)
    host = WorkflowUiHandoffHost(window)

    outcome = host.open_current_data_import(publication)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    assert outcome.command_name == CommandName.SCAN_SOURCE.value
    assert outcome.decision_fields == ("source_path",)
    window.dataset_panel.action_handler.import_data.assert_called_once_with()
    window.statusBar.return_value.showMessage.assert_called_with(
        "Data imported.",
        6000,
    )


@pytest.mark.parametrize(
    ("interpretation", "expected_command"),
    [
        (
            InterpretationStateSnapshot(
                source_path="/datasets/demo",
                has_scan_result=True,
                latest_scan_id="scan-a",
            ),
            CommandName.PREVIEW_INTERPRETATION,
        ),
        (
            InterpretationStateSnapshot(
                source_path="/datasets/demo",
                has_scan_result=True,
                has_candidate=True,
                latest_scan_id="scan-a",
                latest_candidate_id="candidate-a",
            ),
            CommandName.VALIDATE_INTERPRETATION,
        ),
    ],
)
def test_current_data_import_navigates_to_backend_projected_stage(
    interpretation: InterpretationStateSnapshot,
    expected_command: CommandName,
) -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        interpretation=interpretation,
    )
    window = _main_window()
    host = WorkflowUiHandoffHost(window)

    outcome = host.open_current_data_import(_publication(state))

    assert outcome.status is WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI
    assert outcome.command_name == expected_command.value
    window.switch_page.assert_called_once_with(0)
    window.dataset_panel.action_handler.import_data.assert_not_called()
    window.dataset_panel.action_handler.review_current_import.assert_not_called()


def test_current_data_import_opens_exact_published_review_for_apply_stage() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        interpretation=InterpretationStateSnapshot(
            source_path="/datasets/demo",
            has_scan_result=True,
            has_candidate=True,
            has_validation_decision=True,
            latest_scan_id="scan-a",
            latest_candidate_id="candidate-a",
            validation_decision="needs_confirmation",
            pending_confirmation=True,
        ),
    )
    window = _main_window()
    publication = _publication(state)
    host = WorkflowUiHandoffHost(window)

    outcome = host.open_current_data_import(publication)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    assert outcome.command_name == CommandName.APPLY_INTERPRETATION.value
    window.dataset_panel.action_handler.import_data.assert_not_called()
    window.dataset_panel.action_handler.review_current_import.assert_called_once_with(
        initial_step="Review and Import",
        expected_identity=InterpretationReviewIdentity(
            publication_generation=publication.generation,
            scan_id="scan-a",
            candidate_id="candidate-a",
        ),
    )


def test_current_data_import_opens_blocked_review_at_resolvable_step() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        interpretation=InterpretationStateSnapshot(
            source_path="/datasets/demo",
            has_scan_result=True,
            has_candidate=True,
            has_validation_decision=True,
            latest_scan_id="scan-a",
            latest_candidate_id="candidate-a",
            validation_decision="blocked",
            blocked_reasons=["Label placement is unresolved."],
            action_items=[
                {
                    "issue": "Label placement is unresolved.",
                    "impact": "Labels cannot be applied safely.",
                    "next_action": "Review label placement.",
                    "target_step": "Match Labels",
                    "severity": "blocked",
                }
            ],
        ),
    )
    window = _main_window()
    publication = _publication(state)
    host = WorkflowUiHandoffHost(window)

    outcome = host.open_current_data_import(publication)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    assert outcome.command_name == CommandName.APPLY_INTERPRETATION.value
    window.dataset_panel.action_handler.review_current_import.assert_called_once_with(
        initial_step="Match Labels",
        expected_identity=InterpretationReviewIdentity(
            publication_generation=publication.generation,
            scan_id="scan-a",
            candidate_id="candidate-a",
        ),
    )


def test_current_data_import_fails_closed_for_unusable_publication() -> None:
    state = ApplicationStateSnapshot.empty()
    window = _main_window()
    host = WorkflowUiHandoffHost(window)

    outcome = host.open_current_data_import(_publication(state, usable=False))

    assert outcome.status is WorkflowUiHandoffResolutionStatus.FAILED
    assert outcome.message == "Application state is unavailable. Try again shortly."
    window.dataset_panel.action_handler.import_data.assert_not_called()
    window.statusBar.return_value.showMessage.assert_called_with(
        outcome.message,
        6000,
    )


def test_stale_open_data_import_action_does_not_route_to_non_import_workflow() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="data_loaded",
        active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
        interpretation=InterpretationStateSnapshot(
            has_applied_interpretation=True,
        ),
    )
    window = _main_window()
    host = WorkflowUiHandoffHost(window)

    outcome = host.open_current_data_import(_publication(state))

    assert outcome.status is WorkflowUiHandoffResolutionStatus.FAILED
    assert outcome.message == "There is no pending Data Import step to open."
    window.switch_page.assert_not_called()
    window.dataset_panel.action_handler.import_data.assert_not_called()
    window.dataset_panel.action_handler.review_current_import.assert_not_called()


def test_current_data_import_fails_closed_when_apply_identity_is_incomplete() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        interpretation=InterpretationStateSnapshot(
            source_path="/datasets/demo",
            has_scan_result=True,
            has_candidate=True,
            has_validation_decision=True,
            validation_decision="safe",
        ),
    )
    window = _main_window()
    host = WorkflowUiHandoffHost(window)

    outcome = host.open_current_data_import(_publication(state))

    assert outcome.status is WorkflowUiHandoffResolutionStatus.FAILED
    assert "identity is unavailable" in outcome.message
    window.dataset_panel.action_handler.review_current_import.assert_not_called()


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
    window.switch_page.assert_called_once_with(1)
    window.preprocess_panel.sidebar.open_epoching.assert_called_once_with()
    window.statusBar.return_value.showMessage.assert_called_with(
        "Opened Preprocess panel."
    )


def test_unmaterialized_modal_handoff_defers_without_touching_placeholder() -> None:
    """Workflow routing must not inspect a panel until async preparation completes."""
    window = _main_window()
    navigation_calls = []

    def _switch_page(index: int, *, on_ready=None) -> bool:
        navigation_calls.append((index, on_ready))
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
    assert outcome.is_verified_completion is False
    assert host.active_request is request
    assert len(navigation_calls) == 1
    assert navigation_calls[0][0] == 1
    assert callable(navigation_calls[0][1])
    window.statusBar.return_value.showMessage.assert_called_with(
        "Opening Preprocess..."
    )


def test_epoch_handoff_prefills_values_already_supplied_by_user() -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision(
        "create_epoch",
        decision_fields=("epoch_window",),
        suggested_values={"target_event": "769"},
    )

    outcome = host.open(request)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    window.preprocess_panel.sidebar.open_epoching.assert_called_once_with(
        suggested_values={"target_event": "769"}
    )


def test_dataset_handoff_prefills_values_already_supplied_by_user() -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision(
        "generate_dataset",
        decision_fields=("split_strategy",),
        suggested_values={"training_mode": "individual", "test_ratio": "0.2"},
    )

    outcome = host.open(request)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    window.training_panel.sidebar.split_data.assert_called_once_with(
        suggested_values={"training_mode": "individual", "test_ratio": "0.2"}
    )


def test_training_handoff_coordinates_missing_model_and_explicit_options() -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision(
        "configure_training",
        decision_fields=("model", "training_options"),
        suggested_values={"batch_size": "32", "learning_rate": "0.001"},
    )

    outcome = host.open(request)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    window.training_panel.sidebar.configure_training.assert_called_once_with(
        suggested_model=None,
        suggested_values={"batch_size": "32", "learning_rate": "0.001"},
    )
    window.training_panel.sidebar.select_model.assert_not_called()
    window.training_panel.sidebar.training_setting.assert_not_called()


def test_training_handoff_stops_when_model_selection_is_cancelled() -> None:
    window = _main_window()
    window.training_panel.sidebar.configure_training.return_value = (
        InteractionOutcome.cancelled("Training configuration was cancelled.")
    )
    host = WorkflowUiHandoffHost(window)

    outcome = host.open(
        WorkflowUiHandoffRequest.for_decision(
            "configure_training",
            decision_fields=("model", "training_options"),
        )
    )

    assert outcome.status is WorkflowUiHandoffResolutionStatus.CANCELLED
    window.training_panel.sidebar.configure_training.assert_called_once_with(
        suggested_model=None,
        suggested_values={},
    )
    window.training_panel.sidebar.select_model.assert_not_called()
    window.training_panel.sidebar.training_setting.assert_not_called()


@pytest.mark.parametrize(
    ("decision_fields", "suggested_values", "expected_action", "expected_kwargs"),
    [
        (
            ("model",),
            {"model": "EEGNet"},
            "select_model",
            {"suggested_model": "EEGNet"},
        ),
        (
            ("training_options",),
            {"batch_size": "32"},
            "training_setting",
            {"suggested_values": {"batch_size": "32"}},
        ),
    ],
)
def test_training_handoff_preserves_standalone_configuration_actions(
    decision_fields: tuple[str, ...],
    suggested_values: dict[str, str],
    expected_action: str,
    expected_kwargs: dict[str, object],
) -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)

    outcome = host.open(
        WorkflowUiHandoffRequest.for_decision(
            "configure_training",
            decision_fields=decision_fields,
            suggested_values=suggested_values,
        )
    )

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    getattr(window.training_panel.sidebar, expected_action).assert_called_once_with(
        **expected_kwargs
    )
    window.training_panel.sidebar.configure_training.assert_not_called()


@pytest.mark.parametrize(
    ("command_name", "panel_index", "expected_status"),
    [
        ("scan_source", 0, WorkflowUiHandoffResolutionStatus.COMPLETED),
        ("generate_dataset", 2, WorkflowUiHandoffResolutionStatus.COMPLETED),
        (
            "configure_training",
            2,
            WorkflowUiHandoffResolutionStatus.COMPLETED,
        ),
        ("saliency", 4, WorkflowUiHandoffResolutionStatus.CANCELLED),
    ],
)
def test_host_owns_modal_route_table_and_outcome_conversion(
    command_name: str,
    panel_index: int,
    expected_status: WorkflowUiHandoffResolutionStatus,
) -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)

    outcome = host.open(WorkflowUiHandoffRequest.for_decision(command_name))

    assert outcome.status is expected_status
    window.switch_page.assert_called_once_with(panel_index)


@pytest.mark.parametrize(
    ("decision_fields", "expected_step"),
    [
        (("metadata_review",), "Review Metadata"),
        (("label_source",), "Load Labels"),
        (("label_matching",), "Match Labels"),
        (("import_review",), "Review and Import"),
    ],
)
def test_apply_interpretation_handoff_opens_current_review_at_target_step(
    decision_fields: tuple[str, ...],
    expected_step: str,
) -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)
    identity = _review_identity()

    outcome = host.open(
        WorkflowUiHandoffRequest.for_decision(
            "apply_interpretation",
            decision_fields=decision_fields,
            interpretation_identity=identity,
        )
    )

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    window.switch_page.assert_called_once_with(0)
    window.dataset_panel.action_handler.review_current_import.assert_called_once_with(
        initial_step=expected_step,
        expected_identity=identity,
    )
    window.dataset_panel.action_handler.import_data.assert_not_called()
    assert not hasattr(host, "_application_service")


def test_apply_interpretation_handoff_without_domain_identity_fails_closed() -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)

    outcome = host.open(
        WorkflowUiHandoffRequest.for_decision(
            "apply_interpretation",
            decision_fields=("import_review",),
        )
    )

    assert outcome.status is WorkflowUiHandoffResolutionStatus.BLOCKED
    assert "identity" in outcome.message.lower()
    window.dataset_panel.action_handler.review_current_import.assert_not_called()


def test_panel_only_handoff_defers_to_manual_ui_without_claiming_completion() -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)

    outcome = host.open(
        WorkflowUiHandoffRequest.for_decision(
            "evaluate",
            decision_fields=("result_view",),
        )
    )

    assert outcome.status is WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI
    assert outcome.is_verified_completion is False
    assert outcome.command_name == "evaluate"
    assert host.active_request is None
    window.switch_page.assert_called_once_with(3)


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
            command_name="generate_dataset",
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
            command_name="generate_dataset",
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


def test_montage_handoff_uses_existing_dialog_and_preserves_agent_suggestion() -> None:
    window = _main_window()
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision(
        "apply_montage",
        decision_fields=("channel_mapping",),
        suggested_values={
            "montage_name": "standard_1020",
            "warning": "Review channel identities.",
        },
    )

    outcome = host.open(request)

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMPLETED
    assert outcome.suggested_values == request.suggested_values
    window.switch_page.assert_called_once_with(4)
    window.visualization_panel.sidebar.set_montage.assert_called_once_with(
        default_montage="standard_1020",
        warning="Review channel identities.",
    )
    window.statusBar.return_value.showMessage.assert_called_with(
        "Opened Visualization panel."
    )
    route = host._router.route_for("apply_montage")
    assert route is not None
    assert route.panel is WorkflowPanel.VISUALIZATION


def test_montage_navigation_failure_returns_correlated_failed_resolution() -> None:
    window = _main_window()
    window.switch_page.side_effect = RuntimeError("private navigation detail")
    host = WorkflowUiHandoffHost(window)
    request = WorkflowUiHandoffRequest.for_decision("apply_montage")

    outcome = host.open(request)

    assert outcome.request_id == request.request_id
    assert outcome.status is WorkflowUiHandoffResolutionStatus.FAILED
    assert "private navigation detail" not in outcome.message
    window.visualization_panel.sidebar.set_montage.assert_not_called()


def test_montage_dialog_failure_returns_correlated_failed_resolution() -> None:
    window = _main_window()
    window.visualization_panel.sidebar.set_montage.side_effect = RuntimeError(
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
    assert outcome.is_verified_completion is False
    assert outcome.message == "Epoch settings could not be opened."


def test_host_rejects_untyped_payload_instead_of_inferring_command_text() -> None:
    host = WorkflowUiHandoffHost(_main_window())

    with pytest.raises(TypeError, match="WorkflowUiHandoffRequest"):
        cast(Any, host).open(
            {"tool_name": "create_epoch", "command": "generate_dataset"}
        )
