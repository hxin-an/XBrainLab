"""Contract tests for correlated assistant action confirmation."""

from __future__ import annotations

import pytest

from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)


def test_confirmation_request_binds_exact_action_without_exposing_receipt() -> None:
    request = AgentConfirmationRequest.for_action(
        command_name="start_training",
        params={
            "batch_size": 64,
            "resource_preflight_token": "backend-secret-receipt",
        },
        action_label="Start training",
        description="Train EEGNet with the reviewed settings.",
        destructive=False,
        publication_generation=12,
        confirmation_kind="resource_preflight",
        request_id="confirmation-1",
    )

    assert request.command_name == "start_training"
    assert request.publication_generation == 12
    assert request.params_fingerprint
    assert request.parameter_rows == (("Batch size", "64"),)
    assert "backend-secret-receipt" not in repr(request)


def test_confirmation_request_never_hides_reviewable_parameter_values() -> None:
    long_value = "/reviewed/output/" + ("segment/" * 32)
    params = {
        **{f"parameter_{index:02d}": f"value-{index}" for index in range(13)},
        "output_path": long_value,
    }

    request = AgentConfirmationRequest.for_action(
        command_name="configure_training",
        params=params,
        action_label="Apply reviewed settings",
        description="Apply the settings shown in this confirmation.",
        destructive=False,
        publication_generation=13,
    )

    assert len(request.parameter_rows) == len(params)
    assert ("Output path", long_value) in request.parameter_rows
    assert request.parameter_rows[-1] == ("Parameter 12", "value-12")


def test_confirmation_resolution_preserves_request_correlation() -> None:
    request = AgentConfirmationRequest.for_action(
        command_name="destructive_probe",
        params={"confirmed": False},
        action_label="Run destructive probe",
        description="Exercise destructive confirmation correlation.",
        destructive=True,
        publication_generation=4,
        request_id="confirmation-1",
    )

    resolution = AgentConfirmationResolution.for_request(
        request,
        status=AgentConfirmationResolutionStatus.APPROVED,
    )

    assert resolution.matches(request)
    assert resolution.approved
    assert resolution.request_id == request.request_id
    assert resolution.params_fingerprint == request.params_fingerprint


def test_confirmation_resolution_rejects_stale_request_or_generation() -> None:
    request = AgentConfirmationRequest.for_action(
        command_name="destructive_probe",
        params={},
        action_label="Run destructive probe",
        description="Exercise destructive confirmation correlation.",
        destructive=True,
        publication_generation=4,
        request_id="confirmation-1",
    )
    stale = AgentConfirmationResolution(
        request_id="confirmation-old",
        command_name=request.command_name,
        params_fingerprint=request.params_fingerprint,
        publication_generation=request.publication_generation,
        status=AgentConfirmationResolutionStatus.APPROVED,
    )
    wrong_generation = AgentConfirmationResolution(
        request_id=request.request_id,
        command_name=request.command_name,
        params_fingerprint=request.params_fingerprint,
        publication_generation=5,
        status=AgentConfirmationResolutionStatus.APPROVED,
    )

    assert not stale.matches(request)
    assert not wrong_generation.matches(request)


@pytest.mark.parametrize(
    "status",
    [
        AgentConfirmationResolutionStatus.APPROVED,
        AgentConfirmationResolutionStatus.CANCELLED,
    ],
)
def test_confirmation_resolution_status_has_explicit_approval_semantics(
    status: AgentConfirmationResolutionStatus,
) -> None:
    request = AgentConfirmationRequest.for_action(
        command_name="start_training",
        params={},
        action_label="Start training",
        description="Begin training.",
        destructive=False,
        publication_generation=None,
    )

    resolution = AgentConfirmationResolution.for_request(request, status=status)

    assert resolution.approved is (status is AgentConfirmationResolutionStatus.APPROVED)


def test_confirmation_contract_rejects_untyped_or_empty_values() -> None:
    with pytest.raises(ValueError, match="command"):
        AgentConfirmationRequest.for_action(
            command_name=" ",
            params={},
            action_label="Run",
            description="Run action.",
            destructive=False,
            publication_generation=None,
        )
    request = AgentConfirmationRequest.for_action(
        command_name="start_training",
        params={},
        action_label="Start training",
        description="Begin training.",
        destructive=False,
        publication_generation=1,
    )
    with pytest.raises(TypeError, match="status"):
        AgentConfirmationResolution.for_request(
            request,
            status="approved",  # type: ignore[arg-type]
        )
