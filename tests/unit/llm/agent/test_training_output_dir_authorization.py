"""Start-training confirmation reads values from authoritative backend state."""

from typing import Any

from XBrainLab.backend.application import CommandName
from XBrainLab.llm.agent.assembler import PromptToolPublication
from XBrainLab.llm.agent.confirmation import AgentConfirmationRequest
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ToolAttemptAction,
    ToolAttemptCoordinator,
    ToolAttemptRequest,
)
from XBrainLab.llm.agent.verifier import PathProvenanceVerifier, VerificationLayer
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
)
from XBrainLab.llm.tools.definitions.training_def import BaseStartTrainingTool


class _Registry:
    def __init__(self) -> None:
        self.tool = BaseStartTrainingTool()

    def get_tool(self, name: str):
        return self.tool if name == "start_training" else None


class _ContextSource:
    def __init__(self, state: dict[str, Any]) -> None:
        self.context = ToolAvailabilityContext(
            availability=ToolAvailability(
                tool_name="start_training",
                enabled=True,
                command_name=CommandName.TRAIN.value,
                requires_confirmation=True,
            ),
            state=state,
            generation=17,
        )

    def get_context(self, tool_name: str) -> ToolAvailabilityContext:
        assert tool_name == "start_training"
        return self.context


def _training_state(*, output_dir: str, checkpoint_epoch: int) -> dict[str, Any]:
    return {
        "training": {
            "has_training_option": True,
            "training_option": {
                "output_dir": output_dir,
                "checkpoint_epoch": checkpoint_epoch,
            },
        }
    }


def _attempt(state: dict[str, Any]):
    tool = BaseStartTrainingTool()
    coordinator = ToolAttemptCoordinator(
        registry=_Registry(),
        verifier=VerificationLayer(tool_schemas={"start_training": tool.parameters}),
        context_source=_ContextSource(state),
    )
    return coordinator.evaluate(
        ToolAttemptRequest(
            command_name="start_training",
            params={
                "output_directory": "/model/invented-output",
                "checkpoint_policy": "Model-selected policy",
            },
            confidence=0.9,
            publication=PromptToolPublication(
                tool_names=frozenset({"start_training"}),
                backend_generation=17,
            ),
            latest_user_text="Start training.",
        )
    )


def test_start_training_confirmation_uses_authoritative_backend_values() -> None:
    output_dir = "/approved/training-output"
    state = _training_state(output_dir=output_dir, checkpoint_epoch=5)
    params: dict[str, Any] = {
        "output_directory": "/model/invented-output",
        "checkpoint_policy": "Model-selected policy",
    }

    assert (
        PathProvenanceVerifier()
        .validate(
            "start_training",
            params,
            latest_user_text="Start training.",
            state=state,
        )
        .is_valid
    )
    decision = _attempt(state)
    assert decision.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    params = decision.params
    assert (
        VerificationLayer(
            tool_schemas={"start_training": BaseStartTrainingTool().parameters}
        )
        .verify_tool_call(("start_training", params))
        .is_valid
    )

    request = AgentConfirmationRequest.for_action(
        command_name="start_training",
        params=params,
        action_label="Start Training",
        description="Start the training process.",
        destructive=False,
        publication_generation=17,
    )

    assert request.parameter_rows == (
        ("Checkpoint policy", "Every 5 epochs"),
        ("Output directory", output_dir),
    )
    assert "/model/invented-output" not in repr(request)
    assert "Model-selected policy" not in repr(request)


def test_start_training_confirmation_reports_disabled_checkpoints() -> None:
    params: dict[str, Any] = {}
    state = _training_state(output_dir="./output", checkpoint_epoch=0)

    assert (
        PathProvenanceVerifier()
        .validate(
            "start_training",
            params,
            latest_user_text="Start training.",
            state=state,
        )
        .is_valid
    )
    request = AgentConfirmationRequest.for_action(
        command_name="start_training",
        params=params,
        action_label="Start Training",
        description="Start the training process.",
        destructive=False,
        publication_generation=18,
    )

    assert request.parameter_rows == (
        ("Checkpoint policy", "Disabled"),
        ("Output directory", "./output"),
    )
