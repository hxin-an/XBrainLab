"""Typed contract tests for assistant handoff to existing product UI."""

from __future__ import annotations

from pathlib import Path

import pytest

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.view_publication import (
    InterpretationReviewIdentity,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffKind,
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
    WorkflowUiHandoffSession,
    WorkflowUiHandoffSessionStatus,
    WorkflowUiHandoffTransitionStatus,
)


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
