"""Regression contracts for assistant confirmation approval and correlation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from XBrainLab.backend.application.training_recommendation import (
    TrainingRecommendationField,
)
from XBrainLab.llm.agent.assembler import PromptToolPublication
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.pending_interaction import (
    PendingConfirmationDecision,
    PendingInteractionCoordinator,
)
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ToolAttemptAction,
    ToolAttemptCoordinator,
    ToolAttemptDecision,
    ToolAttemptRequest,
)
from XBrainLab.llm.agent.verifier import VerificationLayer
from XBrainLab.llm.tools.application_surface import (
    AssistantSettingConfirmation,
    ToolAvailability,
    ToolAvailabilityContext,
)
from XBrainLab.llm.tools.definitions.dataset_def import BaseConfigureDatasetSplitTool
from XBrainLab.llm.tools.definitions.training_def import (
    BaseConfigureTrainingTool,
    BaseSetModelTool,
)


@dataclass(frozen=True)
class _Tool:
    requires_confirmation: bool = False
    description: str = "Apply the requested change."


class _Registry:
    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        self._tools = tools or {}

    def get_tool(self, name: str) -> Any:
        return self._tools.get(name, _Tool())


class _ContextSource:
    def __init__(self, context: ToolAvailabilityContext) -> None:
        self.context = context

    def get_context(self, tool_name: str) -> ToolAvailabilityContext:
        assert tool_name == self.context.availability.tool_name
        return self.context


def _context(
    tool_name: str,
    *,
    state: dict[str, Any] | None = None,
    capability_confirmation: bool = False,
) -> ToolAvailabilityContext:
    return ToolAvailabilityContext(
        availability=ToolAvailability(
            tool_name=tool_name,
            enabled=True,
            command_name=(
                "configure_training"
                if tool_name in {"set_model", "configure_training"}
                else tool_name
            ),
            confirmation_required=capability_confirmation,
            requires_confirmation=capability_confirmation,
            can_auto_execute=not capability_confirmation,
        ),
        state=state,
        generation=41,
    )


def _training_state(
    *,
    model_name: str = "EEGNet (XBrainLab)",
    epoch: int = 3,
) -> dict[str, Any]:
    return {
        "state_reliable": True,
        "training": {
            "has_model": True,
            "model_name": model_name,
            "model_params": {},
            "has_training_option": True,
            "training_option": {
                "epoch": epoch,
                "batch_size": 4,
                "learning_rate": 0.001,
                "repeat": 1,
                "device": "cpu",
                "optimizer": "adam",
                "evaluation_option": "last_epoch",
                "checkpoint_epoch": 0,
                "output_dir": "./output",
            },
        },
    }


def _evaluate_setting(
    tool_name: str,
    params: dict[str, Any],
    state: dict[str, Any],
) -> tuple[ToolAttemptCoordinator, ToolAttemptDecision]:
    tools = {
        "configure_dataset_split": BaseConfigureDatasetSplitTool(),
        "set_model": BaseSetModelTool(),
        "configure_training": BaseConfigureTrainingTool(),
    }
    context = _context(tool_name, state=state)
    coordinator = ToolAttemptCoordinator(
        registry=_Registry(tools),
        verifier=VerificationLayer(
            tool_schemas={tool_name: tools[tool_name].parameters},
        ),
        context_source=_ContextSource(context),
    )
    decision = coordinator.evaluate(
        ToolAttemptRequest(
            command_name=tool_name,
            params=params,
            confidence=0.9,
            publication=PromptToolPublication(
                tool_names=frozenset({tool_name}),
                backend_generation=41,
                authorized_command=(
                    "configure_training"
                    if tool_name in {"set_model", "configure_training"}
                    else tool_name
                ),
            ),
            latest_user_text=(
                "Use SCCNet for training."
                if tool_name == "set_model"
                else (
                    "Split trials for individual training."
                    if tool_name == "configure_dataset_split"
                    else "Configure training for five epochs with batch size four "
                    "and learning rate 0.001."
                )
            ),
        )
    )
    return coordinator, decision


def test_capability_confirmed_approval_injects_backend_boolean() -> None:
    tool_name = "reset_preprocess"
    params: dict[str, Any] = {}
    context = _context(tool_name, capability_confirmation=True)
    coordinator = ToolAttemptCoordinator(
        registry=_Registry(),
        verifier=VerificationLayer(tool_schemas={}),
        context_source=_ContextSource(context),
    )
    decision = ToolAttemptDecision(
        action=ToolAttemptAction.CONFIRMATION_REQUIRED,
        command_name=tool_name,
        params=params,
        context=context,
        tool=_Tool(),
    )

    approved = coordinator.approved_params(decision)

    assert approved == {**params, "confirmed": True}


@pytest.mark.parametrize(
    ("tool_name", "params"),
    [
        (
            "configure_dataset_split",
            {"split_strategy": "trial", "training_mode": "individual"},
        ),
        (
            "configure_training",
            {
                "epoch": 5,
                "batch_size": 4,
                "learning_rate": 0.001,
                "device": "cpu",
            },
        ),
    ],
)
def test_changed_complete_setting_requires_typed_host_confirmation(
    tool_name: str,
    params: dict[str, Any],
) -> None:
    coordinator, decision = _evaluate_setting(tool_name, params, _training_state())

    assert decision.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    assert decision.confirmation_kind == "setting_change"

    approved = coordinator.approved_params(decision)

    evidence = approved["assistant_setting_confirmation"]
    assert isinstance(evidence, AssistantSettingConfirmation)
    request = AgentConfirmationRequest.for_action(
        command_name=tool_name,
        params=decision.params,
        action_label="Apply change",
        description="Apply the reviewed change.",
        destructive=False,
        publication_generation=41,
    )
    assert evidence.tool_name == tool_name
    assert evidence.params_fingerprint == request.params_fingerprint
    assert evidence.publication_generation == request.publication_generation


def test_dataset_split_confirmation_defaults_keep_fingerprint_stable() -> None:
    coordinator, decision = _evaluate_setting(
        "configure_dataset_split",
        {"split_strategy": "trial", "training_mode": "individual"},
        _training_state(),
    )

    assert decision.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    assert decision.confirmation_kind == "setting_change"
    assert decision.params["test_ratio"] == 0.2
    assert decision.params["val_ratio"] == 0.2

    request = AgentConfirmationRequest.for_action(
        command_name=decision.command_name,
        params=decision.params,
        action_label="Apply change",
        description="Apply the reviewed split.",
        destructive=False,
        publication_generation=41,
    )
    approved = coordinator.approved_params(decision)

    evidence = approved["assistant_setting_confirmation"]
    assert isinstance(evidence, AssistantSettingConfirmation)
    assert evidence.params_fingerprint == request.params_fingerprint
    assert "confirmed" not in approved


def test_training_confirmation_preserves_only_explicit_field_provenance() -> None:
    coordinator, decision = _evaluate_setting(
        "configure_training",
        {
            "epoch": 5,
            "batch_size": 4,
            "learning_rate": 0.001,
            "device": "cpu",
        },
        _training_state(),
    )

    assert decision.params["optimizer"] == "adam"
    assert decision.params["evaluation_option"] == "last_epoch"

    approved = coordinator.approved_params(decision)

    evidence = approved["assistant_setting_confirmation"]
    assert isinstance(evidence, AssistantSettingConfirmation)
    assert evidence.edited_recommendation_fields == (
        TrainingRecommendationField.EPOCHS,
        TrainingRecommendationField.BATCH_SIZE,
        TrainingRecommendationField.LEARNING_RATE,
    )


def test_training_confirmation_preserves_explicit_recommendation_edits() -> None:
    coordinator, decision = _evaluate_setting(
        "configure_training",
        {
            "epoch": 5,
            "batch_size": 4,
            "learning_rate": 0.001,
            "device": "cpu",
            "optimizer": "adamw",
            "evaluation_option": "val_loss",
        },
        _training_state(),
    )

    approved = coordinator.approved_params(decision)

    evidence = approved["assistant_setting_confirmation"]
    assert isinstance(evidence, AssistantSettingConfirmation)
    assert evidence.edited_recommendation_fields == tuple(TrainingRecommendationField)


def test_setting_evidence_fingerprint_excludes_backend_confirmation_boolean() -> None:
    context = _context(
        "configure_training",
        state=_training_state(),
        capability_confirmation=True,
    )
    coordinator = ToolAttemptCoordinator(
        registry=_Registry({"configure_training": BaseConfigureTrainingTool()}),
        verifier=VerificationLayer(tool_schemas={}),
        context_source=_ContextSource(context),
    )
    decision = ToolAttemptDecision(
        action=ToolAttemptAction.CONFIRMATION_REQUIRED,
        command_name="configure_training",
        params={
            "epoch": 5,
            "batch_size": 4,
            "learning_rate": 0.001,
            "repeat": 1,
            "device": "cpu",
            "optimizer": "adam",
            "evaluation_option": "last_epoch",
            "save_checkpoints_every": 0,
        },
        context=context,
        tool=BaseConfigureTrainingTool(),
        confirmation_kind="setting_change",
    )
    request = AgentConfirmationRequest.for_action(
        command_name=decision.command_name,
        params=decision.params,
        action_label="Apply change",
        description="Apply the reviewed change.",
        destructive=False,
        publication_generation=context.generation,
    )

    approved = coordinator.approved_params(decision)

    evidence = approved["assistant_setting_confirmation"]
    assert approved["confirmed"] is True
    assert isinstance(evidence, AssistantSettingConfirmation)
    assert evidence.params_fingerprint == request.params_fingerprint


@pytest.mark.parametrize(
    ("tool_name", "params"),
    [
        (
            "configure_training",
            {
                "epoch": 3,
                "batch_size": 4,
                "learning_rate": 0.001,
                "device": "cpu",
            },
        ),
    ],
)
def test_unchanged_complete_setting_does_not_create_confirmation(
    tool_name: str,
    params: dict[str, Any],
) -> None:
    _coordinator, decision = _evaluate_setting(tool_name, params, _training_state())

    assert decision.action is ToolAttemptAction.EXECUTE


def test_incomplete_training_settings_keep_existing_input_handoff_boundary() -> None:
    _coordinator, decision = _evaluate_setting(
        "configure_training",
        {"epoch": 5},
        _training_state(),
    )

    assert decision.action is ToolAttemptAction.VERIFICATION_BLOCKED
    assert decision.result is not None
    assert decision.result.error_type == "input"
    assert "batch_size" in decision.result.message
    assert "learning_rate" in decision.result.message


_AFFECTED_CONFIRMATIONS = (
    ("reset_preprocessing", {}),
    ("clear_training_history", {}),
    ("start_training", {}),
)


@pytest.mark.parametrize(("tool_name", "params"), _AFFECTED_CONFIRMATIONS)
@pytest.mark.parametrize(
    ("resolution_case", "expected", "consumed"),
    [
        ("approve", PendingConfirmationDecision.APPROVE, True),
        ("cancel", PendingConfirmationDecision.CANCEL, True),
        ("stale", PendingConfirmationDecision.STALE, False),
        ("mismatched_fingerprint", PendingConfirmationDecision.STALE, False),
    ],
)
def test_confirmation_resolution_matrix_is_correlated_for_every_affected_command(
    tool_name: str,
    params: dict[str, Any],
    resolution_case: str,
    expected: PendingConfirmationDecision,
    consumed: bool,
) -> None:
    decision = ToolAttemptDecision(
        action=ToolAttemptAction.CONFIRMATION_REQUIRED,
        command_name=tool_name,
        params=params,
    )
    request = AgentConfirmationRequest.for_action(
        command_name=tool_name,
        params=params,
        action_label="Apply change",
        description="Apply the reviewed change.",
        destructive=tool_name in {"reset_preprocessing", "clear_training_history"},
        publication_generation=41,
        request_id=f"{tool_name}-request",
    )
    session = PendingInteractionCoordinator()
    session.begin_confirmation(decision, request)

    status = (
        AgentConfirmationResolutionStatus.CANCELLED
        if resolution_case == "cancel"
        else AgentConfirmationResolutionStatus.APPROVED
    )
    if resolution_case == "stale":
        resolution = AgentConfirmationResolution(
            request_id=f"{tool_name}-stale",
            command_name=tool_name,
            params_fingerprint=request.params_fingerprint,
            publication_generation=41,
            status=status,
        )
    elif resolution_case == "mismatched_fingerprint":
        resolution = AgentConfirmationResolution(
            request_id=request.request_id,
            command_name=tool_name,
            params_fingerprint="0" * 64,
            publication_generation=41,
            status=status,
        )
    else:
        resolution = AgentConfirmationResolution.for_request(request, status=status)

    result = session.resolve_confirmation(resolution)

    assert result.decision is expected
    assert (session.confirmation is None) is consumed
