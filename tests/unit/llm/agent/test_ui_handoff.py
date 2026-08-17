"""Typed contract tests for assistant handoff to existing product UI."""

from __future__ import annotations

from pathlib import Path

import pytest

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.view_publication import (
    InterpretationReviewIdentity,
)
from XBrainLab.llm.agent.assistant_activity import AssistantDecisionOwner
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffKind,
    WorkflowUiHandoffPanel,
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
    WorkflowUiHandoffRouteIdentity,
    WorkflowUiHandoffSession,
    WorkflowUiHandoffSessionStatus,
    WorkflowUiHandoffSurfaceKind,
    WorkflowUiHandoffTransitionStatus,
    workflow_ui_handoff_route_for,
    workflow_ui_handoff_routes,
)


def test_workflow_handoff_route_descriptors_preserve_existing_ui_taxonomy() -> None:
    expected = (
        (
            CommandName.SCAN_SOURCE,
            WorkflowUiHandoffSurfaceKind.DIALOG,
            AssistantDecisionOwner.GUI_DIALOG,
            WorkflowUiHandoffPanel.DATASET,
            WorkflowUiHandoffRouteIdentity.DATA_IMPORT_DIALOG,
            "Continue in Import EEG Data",
            "Finish or cancel in the open Import EEG Data dialog.",
        ),
        (
            CommandName.REVIEW_INTERPRETATION,
            WorkflowUiHandoffSurfaceKind.PANEL,
            AssistantDecisionOwner.PANEL_HANDOFF,
            WorkflowUiHandoffPanel.DATASET,
            WorkflowUiHandoffRouteIdentity.DATA_IMPORT_PANEL,
            "Continue in Import EEG Data",
            "Continue in the opened XBrainLab panel.",
        ),
        (
            CommandName.PREVIEW_INTERPRETATION,
            WorkflowUiHandoffSurfaceKind.PANEL,
            AssistantDecisionOwner.PANEL_HANDOFF,
            WorkflowUiHandoffPanel.DATASET,
            WorkflowUiHandoffRouteIdentity.DATA_IMPORT_PANEL,
            "Continue in Import EEG Data",
            "Continue in the opened XBrainLab panel.",
        ),
        (
            CommandName.VALIDATE_INTERPRETATION,
            WorkflowUiHandoffSurfaceKind.PANEL,
            AssistantDecisionOwner.PANEL_HANDOFF,
            WorkflowUiHandoffPanel.DATASET,
            WorkflowUiHandoffRouteIdentity.DATA_IMPORT_PANEL,
            "Continue in Import EEG Data",
            "Continue in the opened XBrainLab panel.",
        ),
        (
            CommandName.APPLY_INTERPRETATION,
            WorkflowUiHandoffSurfaceKind.DIALOG,
            AssistantDecisionOwner.GUI_DIALOG,
            WorkflowUiHandoffPanel.DATASET,
            WorkflowUiHandoffRouteIdentity.DATA_IMPORT_REVIEW_DIALOG,
            "Continue in Import EEG Data",
            "Finish or cancel in the open Import EEG Data dialog.",
        ),
        (
            CommandName.PREPROCESS,
            WorkflowUiHandoffSurfaceKind.DIALOG,
            AssistantDecisionOwner.GUI_DIALOG,
            WorkflowUiHandoffPanel.DATASET,
            WorkflowUiHandoffRouteIdentity.CHANNEL_SELECTION_DIALOG,
            "Continue in Channel Selection",
            "Finish or cancel in the open Channel Selection dialog.",
        ),
        (
            CommandName.CREATE_EPOCH,
            WorkflowUiHandoffSurfaceKind.DIALOG,
            AssistantDecisionOwner.GUI_DIALOG,
            WorkflowUiHandoffPanel.PREPROCESS,
            WorkflowUiHandoffRouteIdentity.EPOCH_SETTINGS_DIALOG,
            "Continue in EEG Epoch Settings",
            "Finish or cancel in the open EEG Epoch Settings dialog.",
        ),
        (
            CommandName.CONFIGURE_DATASET_SPLIT,
            WorkflowUiHandoffSurfaceKind.DIALOG,
            AssistantDecisionOwner.GUI_DIALOG,
            WorkflowUiHandoffPanel.TRAINING,
            WorkflowUiHandoffRouteIdentity.DATASET_SPLIT_DIALOG,
            "Continue in Dataset Split Settings",
            "Finish or cancel in the open Dataset Split Settings dialog.",
        ),
        (
            CommandName.CONFIGURE_TRAINING,
            WorkflowUiHandoffSurfaceKind.DIALOG,
            AssistantDecisionOwner.GUI_DIALOG,
            WorkflowUiHandoffPanel.TRAINING,
            WorkflowUiHandoffRouteIdentity.TRAINING_SETTINGS_DIALOG,
            "Continue in Training Settings",
            "Finish or cancel in the open Training Settings dialog.",
        ),
        (
            CommandName.TRAIN,
            WorkflowUiHandoffSurfaceKind.PANEL,
            AssistantDecisionOwner.PANEL_HANDOFF,
            WorkflowUiHandoffPanel.TRAINING,
            WorkflowUiHandoffRouteIdentity.TRAINING_PANEL,
            "Continue in Training",
            "Continue in the opened XBrainLab panel.",
        ),
        (
            CommandName.EVALUATE,
            WorkflowUiHandoffSurfaceKind.PANEL,
            AssistantDecisionOwner.PANEL_HANDOFF,
            WorkflowUiHandoffPanel.EVALUATION,
            WorkflowUiHandoffRouteIdentity.EVALUATION_PANEL,
            "Continue in Evaluation",
            "Continue in the opened XBrainLab panel.",
        ),
        (
            CommandName.VISUALIZE,
            WorkflowUiHandoffSurfaceKind.PANEL,
            AssistantDecisionOwner.PANEL_HANDOFF,
            WorkflowUiHandoffPanel.VISUALIZATION,
            WorkflowUiHandoffRouteIdentity.VISUALIZATION_PANEL,
            "Continue in Visualization",
            "Continue in the opened XBrainLab panel.",
        ),
        (
            CommandName.SALIENCY,
            WorkflowUiHandoffSurfaceKind.DIALOG,
            AssistantDecisionOwner.GUI_DIALOG,
            WorkflowUiHandoffPanel.VISUALIZATION,
            WorkflowUiHandoffRouteIdentity.SALIENCY_SETTINGS_DIALOG,
            "Continue in Saliency Settings",
            "Finish or cancel in the open Saliency Settings dialog.",
        ),
        (
            CommandName.APPLY_MONTAGE,
            WorkflowUiHandoffSurfaceKind.DIALOG,
            AssistantDecisionOwner.GUI_DIALOG,
            WorkflowUiHandoffPanel.VISUALIZATION,
            WorkflowUiHandoffRouteIdentity.MONTAGE_SETTINGS_DIALOG,
            "Continue in Montage Settings",
            "Finish or cancel in the open Montage Settings dialog.",
        ),
    )

    actual = tuple(
        (
            route.command,
            route.surface_kind,
            route.decision_owner,
            route.target_panel,
            route.route_identity,
            route.presentation_step,
            route.decision_copy,
        )
        for route in workflow_ui_handoff_routes()
    )

    assert actual == expected


def test_workflow_handoff_route_lookup_preserves_typed_command_identity() -> None:
    route = workflow_ui_handoff_route_for(" CREATE_EPOCH ")

    assert route is workflow_ui_handoff_route_for(CommandName.CREATE_EPOCH)
    assert route is not None
    assert route.command is CommandName.CREATE_EPOCH
    assert workflow_ui_handoff_route_for("not_a_command") is None


def test_workflow_handoff_consumers_do_not_redeclare_route_taxonomy() -> None:
    sources = {
        path: Path(path).read_text(encoding="utf-8")
        for path in (
            "XBrainLab/llm/agent/controller.py",
            "XBrainLab/ui/components/workflow_ui_handoff_host.py",
            "XBrainLab/ui/chat/presentation.py",
        )
    }

    assert (
        "_DIALOG_HANDOFF_COMMANDS" not in sources["XBrainLab/llm/agent/controller.py"]
    )
    assert (
        "_DATA_IMPORT_COMMANDS"
        not in sources["XBrainLab/ui/components/workflow_ui_handoff_host.py"]
    )
    assert (
        "panel_target_for_command"
        not in sources["XBrainLab/ui/components/workflow_ui_handoff_host.py"]
    )
    assert "_DIALOG_DECISION_COPY" not in sources["XBrainLab/ui/chat/presentation.py"]
    assert "_PANEL_DECISION_STEPS" not in sources["XBrainLab/ui/chat/presentation.py"]


def test_decision_handoff_normalizes_backend_command_and_fields() -> None:
    request = WorkflowUiHandoffRequest.for_decision(
        " CREATE_EPOCH ",
        decision_fields=[" epoch_window ", "target_event", "epoch_window"],
    )

    assert request.kind is WorkflowUiHandoffKind.DECISION_REQUIRED
    assert request.command is CommandName.CREATE_EPOCH
    assert request.command_name == "create_epoch"
    assert request.decision_fields == ("epoch_window", "target_event")
    assert request.request_id


def test_each_handoff_request_has_a_distinct_correlation_id() -> None:
    first = WorkflowUiHandoffRequest.for_decision("create_epoch")
    second = WorkflowUiHandoffRequest.for_decision("create_epoch")

    assert first.request_id != second.request_id


def test_resolution_preserves_request_identity_command_and_decision_fields() -> None:
    request = WorkflowUiHandoffRequest.for_decision(
        "create_epoch",
        decision_fields=("epoch_window", "target_event"),
    )

    resolution = WorkflowUiHandoffResolution.for_request(
        request,
        status=WorkflowUiHandoffResolutionStatus.COMPLETED,
        message="Epoch settings were applied.",
    )

    assert resolution.request_id == request.request_id
    assert resolution.command is CommandName.CREATE_EPOCH
    assert resolution.command_name == "create_epoch"
    assert resolution.decision_fields == ("epoch_window", "target_event")
    assert resolution.message == "Epoch settings were applied."


def test_import_review_handoff_preserves_domain_identity() -> None:
    identity = InterpretationReviewIdentity(
        publication_generation=17,
        scan_id="scan-a",
        candidate_id="candidate-a",
    )
    request = WorkflowUiHandoffRequest.for_decision(
        "apply_interpretation",
        decision_fields=("import_review",),
        interpretation_identity=identity,
    )

    resolution = WorkflowUiHandoffResolution.for_request(
        request,
        status=WorkflowUiHandoffResolutionStatus.CANCELLED,
    )

    assert request.interpretation_identity is identity
    assert resolution.interpretation_identity is identity
    assert resolution.matches(request) is True


def test_handoff_status_contract_distinguishes_initiation_from_terminal_results() -> (
    None
):
    assert WorkflowUiHandoffResolutionStatus.COMMAND_PENDING.is_terminal is False
    assert WorkflowUiHandoffResolutionStatus.NAVIGATED.is_terminal is True
    assert WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI.is_terminal is True
    assert WorkflowUiHandoffResolutionStatus.COMPLETED.is_terminal is True
    assert WorkflowUiHandoffResolutionStatus.FAILED.is_terminal is True
    assert WorkflowUiHandoffResolutionStatus.CANCELLED.is_terminal is True


@pytest.mark.parametrize(
    "status",
    [
        WorkflowUiHandoffResolutionStatus.NAVIGATED,
        WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI,
    ],
)
def test_navigation_handoff_terminates_without_verified_completion(
    status: WorkflowUiHandoffResolutionStatus,
) -> None:
    request = WorkflowUiHandoffRequest.for_decision("evaluate")
    session = WorkflowUiHandoffSession(request)
    resolution = WorkflowUiHandoffResolution.for_request(request, status=status)

    transition = session.resolve(resolution)

    assert transition is WorkflowUiHandoffTransitionStatus.TERMINATED
    assert session.status is WorkflowUiHandoffSessionStatus.TERMINAL
    assert session.terminal_resolution is resolution
    assert resolution.is_verified_completion is False


def test_correlated_handoff_session_stays_pending_until_terminal_callback() -> None:
    request = WorkflowUiHandoffRequest.for_decision(
        "create_epoch",
        decision_fields=("epoch_window",),
    )
    session = WorkflowUiHandoffSession(request)

    initiated = session.resolve(
        WorkflowUiHandoffResolution.for_request(
            request,
            status=WorkflowUiHandoffResolutionStatus.COMMAND_PENDING,
        )
    )

    assert initiated is WorkflowUiHandoffTransitionStatus.ADVANCED
    assert session.status is WorkflowUiHandoffSessionStatus.COMMAND_PENDING
    assert session.terminal_resolution is None

    completed = session.resolve(
        WorkflowUiHandoffResolution.for_request(
            request,
            status=WorkflowUiHandoffResolutionStatus.COMPLETED,
        )
    )

    assert completed is WorkflowUiHandoffTransitionStatus.TERMINATED
    assert session.status is WorkflowUiHandoffSessionStatus.TERMINAL
    assert session.terminal_resolution is not None


def test_handoff_session_rejects_stale_terminal_without_resolving_current_request() -> (
    None
):
    current = WorkflowUiHandoffRequest.for_decision("create_epoch")
    stale = WorkflowUiHandoffRequest.for_decision("create_epoch")
    session = WorkflowUiHandoffSession(current)

    transition = session.resolve(
        WorkflowUiHandoffResolution.for_request(
            stale,
            status=WorkflowUiHandoffResolutionStatus.COMPLETED,
        )
    )

    assert transition is WorkflowUiHandoffTransitionStatus.STALE
    assert session.status is WorkflowUiHandoffSessionStatus.REQUESTED
    assert session.terminal_resolution is None


def test_handoff_preserves_normalized_ui_suggestions_for_exact_resolution() -> None:
    request = WorkflowUiHandoffRequest.for_decision(
        CommandName.APPLY_MONTAGE,
        decision_fields=("channel_mapping",),
        suggested_values={
            "montage_name": " standard_1020 ",
            "warning": " Review\nchannel identities. ",
            "empty": "  ",
        },
    )

    resolution = WorkflowUiHandoffResolution.for_request(
        request,
        status=WorkflowUiHandoffResolutionStatus.COMPLETED,
    )

    assert request.suggested_values == (
        ("montage_name", "standard_1020"),
        ("warning", "Review channel identities."),
    )
    assert request.suggestions == {
        "montage_name": "standard_1020",
        "warning": "Review channel identities.",
    }
    assert resolution.suggested_values == request.suggested_values
    assert resolution.matches(request)


def test_resolution_match_rejects_any_changed_correlation_field() -> None:
    request = WorkflowUiHandoffRequest.for_decision(
        "create_epoch",
        decision_fields=("epoch_window",),
        suggested_values={"target_event": "769"},
    )
    other_request = WorkflowUiHandoffRequest.for_decision(
        "create_epoch",
        decision_fields=("epoch_window",),
        suggested_values={"target_event": "769"},
    )
    resolution = WorkflowUiHandoffResolution.for_request(
        request,
        status=WorkflowUiHandoffResolutionStatus.COMPLETED,
    )

    assert not resolution.matches(other_request)
    assert not resolution.matches(object())


def test_handoff_rejects_unknown_command_instead_of_routing_text() -> None:
    with pytest.raises(ValueError, match="Unknown workflow UI handoff command"):
        WorkflowUiHandoffRequest.for_decision("not_a_command")


@pytest.mark.parametrize(
    ("overrides", "error_type", "error_match"),
    [
        ({"kind": "decision_required"}, TypeError, "kind must be typed"),
        (
            {"kind": WorkflowUiHandoffResolutionStatus.COMPLETED},
            TypeError,
            "kind must be typed",
        ),
        ({"command": "create_epoch"}, TypeError, "command must be typed"),
        (
            {"command": WorkflowUiHandoffKind.DECISION_REQUIRED},
            TypeError,
            "command must be typed",
        ),
        ({"request_id": 3}, TypeError, "request id must be a string"),
        ({"request_id": " "}, ValueError, "request id cannot be empty"),
        (
            {"decision_fields": "epoch_window"},
            TypeError,
            "decision_fields must be a tuple",
        ),
        (
            {"decision_fields": ["epoch_window"]},
            TypeError,
            "decision_fields must be a tuple",
        ),
        (
            {"decision_fields": ("epoch_window", 3)},
            TypeError,
            "decision_fields entries must be strings",
        ),
        (
            {"decision_fields": (CommandName.CREATE_EPOCH,)},
            TypeError,
            "decision_fields entries must be strings",
        ),
        (
            {"decision_fields": (" ",)},
            ValueError,
            "decision_fields entries cannot be empty",
        ),
        (
            {"suggested_values": "target_event=769"},
            TypeError,
            "suggested_values must be a tuple",
        ),
        (
            {"suggested_values": (("target_event", "769"), ["window", "1.0"])},
            TypeError,
            "suggested_values entries must be key/value tuples",
        ),
        (
            {"suggested_values": (("target_event",),)},
            TypeError,
            "suggested_values entries must be key/value tuples",
        ),
        (
            {"suggested_values": (("target_event", 769),)},
            TypeError,
            "suggested_values keys and values must be strings",
        ),
        (
            {"suggested_values": ((CommandName.CREATE_EPOCH, "769"),)},
            TypeError,
            "suggested_values keys and values must be strings",
        ),
        (
            {"suggested_values": (("target_event", " "),)},
            ValueError,
            "suggested_values cannot contain empty text",
        ),
    ],
)
def test_direct_handoff_request_construction_rejects_untyped_contract_values(
    overrides: dict[str, object],
    error_type: type[Exception],
    error_match: str,
) -> None:
    values: dict[str, object] = {
        "kind": WorkflowUiHandoffKind.DECISION_REQUIRED,
        "command": CommandName.CREATE_EPOCH,
        "request_id": "request-1",
        "decision_fields": ("epoch_window",),
        "suggested_values": (("target_event", "769"),),
    }
    values.update(overrides)

    with pytest.raises(error_type, match=error_match):
        WorkflowUiHandoffRequest(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "error_type", "error_match"),
    [
        ({"command": "create_epoch"}, TypeError, "command must be typed"),
        (
            {"command": WorkflowUiHandoffKind.DECISION_REQUIRED},
            TypeError,
            "command must be typed",
        ),
        ({"status": "completed"}, TypeError, "status must be typed"),
        (
            {"status": WorkflowUiHandoffKind.DECISION_REQUIRED},
            TypeError,
            "status must be typed",
        ),
        ({"request_id": 3}, TypeError, "request id must be a string"),
        ({"request_id": " "}, ValueError, "resolution id cannot be empty"),
        (
            {"decision_fields": "epoch_window"},
            TypeError,
            "decision_fields must be a tuple",
        ),
        (
            {"decision_fields": ["epoch_window"]},
            TypeError,
            "decision_fields must be a tuple",
        ),
        (
            {"decision_fields": ("epoch_window", 3)},
            TypeError,
            "decision_fields entries must be strings",
        ),
        (
            {"decision_fields": (CommandName.CREATE_EPOCH,)},
            TypeError,
            "decision_fields entries must be strings",
        ),
        (
            {"decision_fields": (" ",)},
            ValueError,
            "decision_fields entries cannot be empty",
        ),
        (
            {"suggested_values": "target_event=769"},
            TypeError,
            "suggested_values must be a tuple",
        ),
        (
            {"suggested_values": (("target_event", "769"), ["window", "1.0"])},
            TypeError,
            "suggested_values entries must be key/value tuples",
        ),
        (
            {"suggested_values": (("target_event",),)},
            TypeError,
            "suggested_values entries must be key/value tuples",
        ),
        (
            {"suggested_values": (("target_event", 769),)},
            TypeError,
            "suggested_values keys and values must be strings",
        ),
        (
            {"suggested_values": ((CommandName.CREATE_EPOCH, "769"),)},
            TypeError,
            "suggested_values keys and values must be strings",
        ),
        (
            {"suggested_values": (("target_event", " "),)},
            ValueError,
            "suggested_values cannot contain empty text",
        ),
    ],
)
def test_direct_handoff_resolution_construction_rejects_untyped_contract_values(
    overrides: dict[str, object],
    error_type: type[Exception],
    error_match: str,
) -> None:
    values: dict[str, object] = {
        "request_id": "request-1",
        "command": CommandName.CREATE_EPOCH,
        "status": WorkflowUiHandoffResolutionStatus.COMPLETED,
        "decision_fields": ("epoch_window",),
        "suggested_values": (("target_event", "769"),),
        "message": "Epoch settings were applied.",
    }
    values.update(overrides)

    with pytest.raises(error_type, match=error_match):
        WorkflowUiHandoffResolution(**values)  # type: ignore[arg-type]


def test_ui_host_does_not_classify_backend_decision_boundary_strings() -> None:
    source = Path("XBrainLab/ui/components/agent_manager.py").read_text(
        encoding="utf-8"
    )

    assert "_decision_requires_existing_ui" not in source
    assert "decision_boundary" not in source
    assert 'command in {"decision_required"' not in source


def test_prompt_context_does_not_publish_a_fake_ui_surface_action() -> None:
    source = Path("XBrainLab/llm/agent/decision_context.py").read_text(encoding="utf-8")

    assert "open_existing_ui_surface" not in source
