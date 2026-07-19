from __future__ import annotations

from typing import Any

from XBrainLab.backend.application import (
    CommandName,
    ConfigureTrainingCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
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
    ToolCommandResult,
    UserProvidedTrainingOutputDir,
    execute_application_tool_command,
)
from XBrainLab.llm.tools.definitions.training_def import (
    BaseConfigureTrainingTool,
    BaseStartTrainingTool,
)


class _TrainingRegistry:
    def __init__(self) -> None:
        self._tools = {
            "configure_training": BaseConfigureTrainingTool(),
            "start_training": BaseStartTrainingTool(),
        }

    def get_tool(self, name: str):
        return self._tools.get(name)


class _TrainingContextSource:
    def __init__(self, context: ToolAvailabilityContext) -> None:
        self.context = context

    def get_context(self, tool_name: str) -> ToolAvailabilityContext:
        assert tool_name == self.context.availability.tool_name
        return self.context


def _training_params(**overrides: Any) -> dict[str, Any]:
    return {
        "model_name": "EEGNet",
        "epoch": 3,
        "batch_size": 4,
        "learning_rate": 0.001,
        "device": "cpu",
        **overrides,
    }


def _training_state(
    *,
    output_dir: str,
    checkpoint_epoch: int,
) -> dict[str, Any]:
    return {
        "training": {
            "has_training_option": True,
            "training_option": {
                "output_dir": output_dir,
                "checkpoint_epoch": checkpoint_epoch,
            },
        }
    }


def _attempt(
    tool_name: str,
    params: dict[str, Any],
    *,
    latest_user_text: str,
    state: dict[str, Any] | None,
    requires_confirmation: bool = False,
):
    context = ToolAvailabilityContext(
        availability=ToolAvailability(
            tool_name=tool_name,
            enabled=True,
            command_name=(
                CommandName.TRAIN.value
                if tool_name == "start_training"
                else CommandName.CONFIGURE_TRAINING.value
            ),
            requires_confirmation=requires_confirmation,
        ),
        state=state,
        generation=17,
    )
    registry = _TrainingRegistry()
    tool = registry.get_tool(tool_name)
    assert tool is not None
    coordinator = ToolAttemptCoordinator(
        registry=registry,
        verifier=VerificationLayer(
            tool_schemas={
                tool_name: tool.parameters,
            }
        ),
        context_source=_TrainingContextSource(context),
    )
    return coordinator.evaluate(
        ToolAttemptRequest(
            command_name=tool_name,
            params=params,
            confidence=0.9,
            publication=PromptToolPublication(
                tool_names=frozenset({tool_name}),
                backend_generation=17,
            ),
            latest_user_text=latest_user_text,
        )
    )


def test_configure_training_schema_does_not_publish_output_dir() -> None:
    properties = BaseConfigureTrainingTool().parameters["properties"]

    assert "output_dir" not in properties


def test_invented_training_output_dir_is_rejected_before_command() -> None:
    invented = "/tmp/model-invented-training-output"
    params = _training_params(output_dir=invented)
    provenance = PathProvenanceVerifier().validate(
        "configure_training",
        params,
        latest_user_text="Configure training for three epochs.",
        state=None,
    )

    assert provenance.is_valid is False
    assert "not provided in this turn" in str(provenance.error_message)

    decision = _attempt(
        "configure_training",
        dict(params),
        latest_user_text=(
            "Configure EEGNet for 3 epochs with batch size 4 and learning rate 0.001."
        ),
        state=None,
    )
    assert decision.action is ToolAttemptAction.PROVENANCE_BLOCKED

    study = Study()
    result = execute_application_tool_command(
        study,
        "configure_training",
        params,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "input"
    assert (
        get_application_service(study).get_state().training.has_training_option is False
    )


def test_selected_dataset_root_does_not_authorize_invented_training_output_dir(
    tmp_path,
) -> None:
    dataset_root = tmp_path / "selected-dataset"
    invented = dataset_root / "model-selected-output"
    params = _training_params(output_dir=str(invented))
    state = {
        "interpretation": {
            "source_path": str(dataset_root),
            "source_kind": "folder",
        }
    }

    provenance = PathProvenanceVerifier().validate(
        "configure_training",
        params,
        latest_user_text="Configure training for three epochs.",
        state=state,
    )

    assert provenance.is_valid is False
    assert "not provided in this turn" in str(provenance.error_message)


def test_explicit_user_training_output_dir_uses_typed_provenance_path(
    tmp_path,
) -> None:
    output_dir = tmp_path / "user-selected-training-output"
    params = _training_params(output_dir=str(output_dir))

    provenance = PathProvenanceVerifier().validate(
        "configure_training",
        params,
        latest_user_text=f"Save training output in `{output_dir}`.",
        state=None,
    )

    assert provenance.is_valid is True
    assert isinstance(params["output_dir"], UserProvidedTrainingOutputDir)

    schema = VerificationLayer(
        tool_schemas={
            "configure_training": BaseConfigureTrainingTool().parameters,
        }
    )
    assert schema.verify_tool_call(("configure_training", params)).is_valid is True

    result = execute_application_tool_command(
        Study(),
        "configure_training",
        params,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert result.command_name == CommandName.CONFIGURE_TRAINING.value
    assert result.state is not None
    assert result.state["training"]["training_option"]["output_dir"] == str(output_dir)

    decision = _attempt(
        "configure_training",
        _training_params(output_dir=str(output_dir)),
        latest_user_text=(
            "Configure EEGNet for 3 epochs with batch size 4 and learning rate "
            f"0.001, and save output in `{output_dir}`."
        ),
        state=None,
    )
    assert decision.action is ToolAttemptAction.EXECUTE
    assert isinstance(
        decision.params["output_dir"],
        UserProvidedTrainingOutputDir,
    )


def test_configure_training_without_output_dir_preserves_backend_value(
    tmp_path,
) -> None:
    output_dir = tmp_path / "settings-selected-training-output"
    study = Study()
    service = get_application_service(study)
    configured = service.execute(
        ConfigureTrainingCommand(
            **_training_params(output_dir=str(output_dir)),
        )
    )
    assert configured.ok is True

    state = service.get_state().to_dict()
    result = execute_application_tool_command(
        study,
        "configure_training",
        _training_params(epoch=5),
        state=state,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert result.state is not None
    assert result.state["training"]["training_option"]["output_dir"] == str(output_dir)


def test_start_training_confirmation_uses_authoritative_backend_values() -> None:
    output_dir = "/approved/training-output"
    params: dict[str, Any] = {
        "output_directory": "/model/invented-output",
        "checkpoint_policy": "Model-selected policy",
    }
    provenance = PathProvenanceVerifier().validate(
        "start_training",
        params,
        latest_user_text="Start training.",
        state=_training_state(output_dir=output_dir, checkpoint_epoch=5),
    )

    assert provenance.is_valid is True
    decision = _attempt(
        "start_training",
        {
            "output_directory": "/model/invented-output",
            "checkpoint_policy": "Model-selected policy",
        },
        latest_user_text="Start training.",
        state=_training_state(output_dir=output_dir, checkpoint_epoch=5),
        requires_confirmation=True,
    )
    assert decision.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    params = decision.params
    schema = VerificationLayer(
        tool_schemas={
            "start_training": BaseStartTrainingTool().parameters,
        }
    )
    assert schema.verify_tool_call(("start_training", params)).is_valid is True

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

    provenance = PathProvenanceVerifier().validate(
        "start_training",
        params,
        latest_user_text="Start training.",
        state=_training_state(output_dir="./output", checkpoint_epoch=0),
    )
    request = AgentConfirmationRequest.for_action(
        command_name="start_training",
        params=params,
        action_label="Start Training",
        description="Start the training process.",
        destructive=False,
        publication_generation=18,
    )

    assert provenance.is_valid is True
    assert request.parameter_rows == (
        ("Checkpoint policy", "Disabled"),
        ("Output directory", "./output"),
    )
