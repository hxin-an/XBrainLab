"""Contract tests for transient assistant turn activity."""

from __future__ import annotations

from dataclasses import fields

import pytest

from XBrainLab.llm.agent.assistant_activity import (
    AssistantAttentionKind,
    AssistantDecisionOwner,
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)


def test_turn_activity_normalizes_optional_correlation_metadata() -> None:
    activity = AssistantTurnActivity(
        phase=AssistantTurnActivityPhase.RUNNING_COMMAND,
        turn_id=42,
        command_name="  create_epoch  ",
        request_id="  request-42  ",
        message="  execution detail\nfor diagnostics  ",
    )

    assert activity.phase is AssistantTurnActivityPhase.RUNNING_COMMAND
    assert activity.turn_id == 42
    assert activity.command_name == "create_epoch"
    assert activity.request_id == "request-42"
    assert activity.message == "execution detail for diagnostics"


def test_attention_kind_is_typed_and_independent_of_message_copy() -> None:
    terse = AssistantTurnActivity(
        AssistantTurnActivityPhase.NEEDS_ATTENTION,
        attention_kind=AssistantAttentionKind.ERROR,
    )
    detailed = AssistantTurnActivity(
        AssistantTurnActivityPhase.NEEDS_ATTENTION,
        message="The local model returned no usable response.",
        attention_kind=AssistantAttentionKind.ERROR,
    )

    assert terse.attention_kind is detailed.attention_kind
    assert terse.attention_kind is AssistantAttentionKind.ERROR


def test_waiting_activity_requires_a_typed_decision_owner_and_identity() -> None:
    activity = AssistantTurnActivity(
        AssistantTurnActivityPhase.WAITING_FOR_DECISION,
        command_name="configure_training",
        request_id="confirmation-7",
        decision_owner=AssistantDecisionOwner.CONFIRMATION_CARD,
    )

    assert activity.decision_owner is AssistantDecisionOwner.CONFIRMATION_CARD

    with pytest.raises(ValueError, match="decision owner"):
        AssistantTurnActivity(
            AssistantTurnActivityPhase.WAITING_FOR_DECISION,
            command_name="configure_training",
            request_id="confirmation-7",
        )


@pytest.mark.parametrize("field_name", ["command_name", "request_id"])
def test_waiting_activity_rejects_missing_decision_identity(field_name: str) -> None:
    values = {
        "command_name": "create_epoch",
        "request_id": "epoch-dialog-1",
    }
    values[field_name] = ""

    with pytest.raises(ValueError, match="decision identity"):
        AssistantTurnActivity(
            AssistantTurnActivityPhase.WAITING_FOR_DECISION,
            decision_owner=AssistantDecisionOwner.GUI_DIALOG,
            **values,
        )


def test_non_waiting_activity_rejects_a_decision_owner() -> None:
    with pytest.raises(ValueError, match="only valid while waiting"):
        AssistantTurnActivity(
            AssistantTurnActivityPhase.THINKING,
            decision_owner=AssistantDecisionOwner.PANEL_HANDOFF,
        )


@pytest.mark.parametrize("turn_id", [0, -1, True, "7"])
def test_turn_activity_rejects_invalid_turn_correlation(turn_id: object) -> None:
    with pytest.raises((TypeError, ValueError), match="turn id"):
        AssistantTurnActivity(
            AssistantTurnActivityPhase.THINKING,
            turn_id=turn_id,  # type: ignore[arg-type]
        )


def test_turn_activity_requires_a_typed_phase() -> None:
    with pytest.raises(TypeError, match="phase must be typed"):
        AssistantTurnActivity(
            phase="thinking",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("field_name", ["command_name", "request_id", "message"])
def test_turn_activity_rejects_untyped_text_metadata(field_name: str) -> None:
    values = {field_name: object()}

    with pytest.raises(TypeError, match=field_name.replace("_", " ")):
        AssistantTurnActivity(
            phase=AssistantTurnActivityPhase.THINKING,
            **values,  # type: ignore[arg-type]
        )


def test_turn_activity_does_not_duplicate_backend_pipeline_readiness() -> None:
    field_names = {field.name for field in fields(AssistantTurnActivity)}

    assert field_names.isdisjoint(
        {
            "capabilities",
            "pipeline_ready",
            "pipeline_stage",
            "publication",
            "ready",
        }
    )
    assert {phase.value for phase in AssistantTurnActivityPhase}.isdisjoint(
        {
            "data_loaded",
            "dataset_ready",
            "epochs_ready",
            "preprocessed",
            "trained",
        }
    )
