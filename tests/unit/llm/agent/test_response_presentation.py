"""Contracts for bounded assistant responses and panel navigation."""

from __future__ import annotations

import pytest

from XBrainLab.backend.application import CommandName
from XBrainLab.chat_contract import MAX_CHAT_MESSAGE_CONTENT_LENGTH
from XBrainLab.llm.agent.interaction import (
    AgentInteractionOutcome,
    AgentInteractionStatus,
)
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
    AssistantResponseKind,
    AssistantResponsePresentation,
    interaction_outcome_kind,
    interaction_outcome_message,
    panel_target_for_command,
    user_facing_generation_error,
)
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation

_CORRELATION = AssistantTurnCorrelation(generation=1, turn_id=1)


def test_panel_navigation_request_is_typed_and_bounded() -> None:
    request = AssistantPanelNavigationRequest(
        target=AssistantPanelTarget.VISUALIZATION,
        view_mode="3d_plot",
    )

    assert request.target is AssistantPanelTarget.VISUALIZATION
    assert request.view_mode == "3d_plot"
    with pytest.raises(TypeError, match="panel target"):
        AssistantPanelNavigationRequest(target="training")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not available"):
        AssistantPanelNavigationRequest(
            target=AssistantPanelTarget.TRAINING,
            view_mode="metrics",
        )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (AgentInteractionStatus.CANCELLED, "workflow is unchanged"),
        (AgentInteractionStatus.CONFIRMED, "Approved"),
        (AgentInteractionStatus.DEFERRED_TO_UI, "open in the main window"),
        (AgentInteractionStatus.BLOCKED, "blocked"),
        (AgentInteractionStatus.UNAVAILABLE, "not available"),
        (AgentInteractionStatus.FAILED, "could not be opened"),
    ],
)
def test_interaction_copy_is_derived_from_structured_outcome(status, expected) -> None:
    outcome = AgentInteractionOutcome(status=status, command_name="reset_preprocess")
    assert expected in interaction_outcome_message(outcome)


def test_cancelled_data_import_uses_product_language() -> None:
    outcome = AgentInteractionOutcome(
        status=AgentInteractionStatus.CANCELLED,
        command_name="apply_interpretation",
    )
    assert interaction_outcome_message(outcome) == (
        "Data import was cancelled. No data was added."
    )


def test_handoff_blocker_uses_specific_product_surface_message() -> None:
    outcome = AgentInteractionOutcome(
        status=AgentInteractionStatus.BLOCKED,
        command_name="create_epoch",
        message="Load preprocessed data before creating epochs.",
    )
    assert interaction_outcome_message(outcome) == (
        "Load preprocessed data before creating epochs."
    )
    assert interaction_outcome_kind(outcome) is AssistantResponseKind.BLOCKED


def test_response_presentation_is_only_correlated_copy() -> None:
    presentation = AssistantResponsePresentation(
        text="Review the current workflow.",
        correlation=_CORRELATION,
        kind=AssistantResponseKind.BLOCKED,
    )

    assert presentation.text == "Review the current workflow."
    assert presentation.correlation == _CORRELATION
    assert not hasattr(presentation, "actions")
    assert not hasattr(presentation, "presentation_id")


def test_response_presentation_rejects_retired_action_payload() -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        AssistantResponsePresentation(
            text="Review the current workflow.",
            correlation=_CORRELATION,
            actions=(),  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    ("raw_error", "expected"),
    (
        ("CUDA out of memory while allocating tensor 0x7f00", "ran out of GPU memory"),
        ("Model load failed: /private/cache/model.gguf", "could not start or continue"),
        ("RuntimeError: internal engine detail", "could not complete the request"),
    ),
)
def test_generation_error_copy_is_actionable_without_raw_details(
    raw_error: str,
    expected: str,
) -> None:
    visible = user_facing_generation_error(raw_error)
    assert expected in visible
    assert raw_error not in visible
    assert "/private/cache" not in visible


@pytest.mark.parametrize("command_name", ["set_montage", "apply_montage"])
def test_montage_commands_share_visualization_surface_truth(command_name: str) -> None:
    assert panel_target_for_command(command_name) is AssistantPanelTarget.VISUALIZATION


def test_panel_routing_accepts_typed_canonical_command_identity() -> None:
    assert (
        panel_target_for_command(CommandName.CREATE_EPOCH)
        is AssistantPanelTarget.PREPROCESS
    )
    assert (
        panel_target_for_command(CommandName.APPLY_MONTAGE)
        is AssistantPanelTarget.VISUALIZATION
    )


def test_response_presentation_requires_exact_turn_generation_correlation() -> None:
    correlation = AssistantTurnCorrelation(generation=7, turn_id=11)
    presentation = AssistantResponsePresentation(
        text="Correlated response.",
        correlation=correlation,
    )

    assert presentation.correlation == correlation
    with pytest.raises(TypeError, match="correlation"):
        AssistantResponsePresentation(
            text="Uncorrelated response.",
            correlation=object(),  # type: ignore[arg-type]
        )


def test_response_accepts_exact_content_capacity_and_rejects_overflow() -> None:
    presentation = AssistantResponsePresentation(
        text="c" * MAX_CHAT_MESSAGE_CONTENT_LENGTH,
        correlation=_CORRELATION,
    )
    assert len(presentation.text) == MAX_CHAT_MESSAGE_CONTENT_LENGTH

    with pytest.raises(ValueError, match=r"maximum|at most"):
        AssistantResponsePresentation(
            text="c" * (MAX_CHAT_MESSAGE_CONTENT_LENGTH + 1),
            correlation=_CORRELATION,
        )


def test_assistant_response_redacts_private_diagnostic_context() -> None:
    private_path = "/srv/clinical/subject-17/events.tsv"
    private_subject = "Alice-Smith"
    presentation = AssistantResponsePresentation(
        text=(
            f"Could not read {private_path}\r\n"
            f"Review subject_id={private_subject} and retry."
        ),
        correlation=_CORRELATION,
    )

    serialized = repr(presentation)
    assert private_path not in serialized
    assert private_subject not in serialized
    assert "events.tsv" in presentation.text
    assert "[REDACTED_PATH]" in serialized
    assert "[SUBJECT_REF:" in serialized


def test_interaction_outcome_message_redacts_backend_failure_detail() -> None:
    private_path = r"\\research-nas\patient-share\sub-P001\recording.gdf"
    outcome = AgentInteractionOutcome(
        status=AgentInteractionStatus.BLOCKED,
        command_name="scan_source",
        message=f"Could not inspect {private_path}; subject_id=Alice.",
    )

    visible = interaction_outcome_message(outcome)
    assert private_path not in visible
    assert "sub-P001" not in visible
    assert "Alice" not in visible
    assert ".gdf" in visible
