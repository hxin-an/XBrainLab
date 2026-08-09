"""Application-surface regressions for assistant confirmation evidence."""

from __future__ import annotations

from XBrainLab.backend.application import (
    ChangedState,
    Command,
    CommandName,
    CommandResult,
    ConfigureTrainingCommand,
    GenerateDatasetCommand,
    get_application_service,
)
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
from XBrainLab.llm.tools.application_surface import (
    AssistantSettingConfirmation,
    ToolCommandResult,
    _command_for_tool,
    authorize_assistant_setting_change,
    execute_application_tool_command,
)


def _training_params(*, epoch: int = 3) -> dict[str, object]:
    return {
        "epoch": epoch,
        "batch_size": 4,
        "learning_rate": 0.001,
        "device": "cpu",
    }


def _authorize(
    study: Study,
    tool_name: str,
    params: dict[str, object],
) -> dict[str, object]:
    generation = get_application_service(study).get_view_publication().generation
    return authorize_assistant_setting_change(
        tool_name,
        params,
        publication_generation=generation,
    )


def test_generate_dataset_builder_forwards_typed_confirmation_boolean() -> None:
    command = _command_for_tool(
        "generate_dataset",
        {
            "split_strategy": "trial",
            "training_mode": "full_data",
            "confirmed": True,
        },
    )

    assert isinstance(command, GenerateDatasetCommand)
    assert command.confirmed is True


def test_changed_model_setting_fails_closed_without_host_confirmation() -> None:
    study = Study()
    service = get_application_service(study)
    before = service.get_state().training

    result = execute_application_tool_command(
        study,
        "set_model",
        {"model_name": "EEGNet"},
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "confirmation_required"
    assert service.get_state().training == before


def test_host_confirmed_model_setting_executes_exact_proposal() -> None:
    study = Study()
    params = _authorize(
        study,
        "set_model",
        {"model_name": "EEGNet"},
    )

    result = execute_application_tool_command(study, "set_model", params)

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert result.state is not None
    assert result.state["training"]["model_name"] == "EEGNet (XBrainLab)"


def test_same_model_setting_does_not_require_reconfirmation() -> None:
    study = Study()
    service = get_application_service(study)
    configured = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
    assert configured.ok is True

    result = execute_application_tool_command(
        study,
        "set_model",
        {"model_name": "EEGNet"},
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True


def test_changed_complete_training_settings_require_host_confirmation() -> None:
    study = Study()
    service = get_application_service(study)
    configured = service.execute(ConfigureTrainingCommand(**_training_params()))
    assert configured.ok is True
    before = service.get_state().training

    result = execute_application_tool_command(
        study,
        "configure_training",
        _training_params(epoch=5),
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "confirmation_required"
    assert service.get_state().training == before


def test_host_confirmed_training_settings_execute_exact_proposal() -> None:
    study = Study()
    params = _authorize(
        study,
        "configure_training",
        _training_params(epoch=5),
    )

    result = execute_application_tool_command(study, "configure_training", params)

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert result.state is not None
    assert result.state["training"]["training_option"]["epoch"] == 5


def test_training_authorization_normalizes_the_reviewed_proposal() -> None:
    study = Study()

    params = _authorize(
        study,
        "configure_training",
        _training_params(epoch=5),
    )

    assert params["repeat"] == 1
    assert params["optimizer"] == "adam"
    assert params["evaluation_option"] == "last_epoch"
    assert params["save_checkpoints_every"] == 0
    evidence = params["assistant_setting_confirmation"]
    assert isinstance(evidence, AssistantSettingConfirmation)


def test_setting_confirmation_rejects_parameter_mutation_after_approval() -> None:
    study = Study()
    service = get_application_service(study)
    params = _authorize(study, "set_model", {"model_name": "EEGNet"})
    params["model_name"] = "SCCNet"

    result = execute_application_tool_command(study, "set_model", params)

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "confirmation_required"
    assert service.get_state().training.has_model is False


def test_training_confirmation_rejects_batch_size_mutation_after_approval() -> None:
    study = Study()
    service = get_application_service(study)
    params = _authorize(study, "configure_training", _training_params(epoch=5))
    params["batch_size"] = 8

    result = execute_application_tool_command(study, "configure_training", params)

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "confirmation_required"
    assert service.get_state().training.has_training_option is False


def test_training_confirmation_rejects_device_mutation_after_approval() -> None:
    study = Study()
    service = get_application_service(study)
    params = _authorize(study, "configure_training", _training_params(epoch=5))
    params["device"] = "cuda"

    result = execute_application_tool_command(study, "configure_training", params)

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "confirmation_required"
    assert service.get_state().training.has_training_option is False


def test_setting_confirmation_rejects_stale_generation_replay() -> None:
    study = Study()
    service = get_application_service(study)
    stale = _authorize(study, "set_model", {"model_name": "SCCNet"})
    intervening = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
    assert intervening.ok is True
    before = service.get_state().training

    result = execute_application_tool_command(study, "set_model", stale)

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "confirmation_required"
    assert service.get_state().training == before


def test_training_confirmation_rejects_stale_generation_replay() -> None:
    study = Study()
    service = get_application_service(study)
    stale = _authorize(
        study,
        "configure_training",
        _training_params(epoch=5),
    )
    intervening = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
    assert intervening.ok is True
    before = service.get_state().training

    result = execute_application_tool_command(
        study,
        "configure_training",
        stale,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "confirmation_required"
    assert service.get_state().training == before


def test_setting_confirmation_ignores_caller_supplied_stale_state() -> None:
    study = Study()
    service = get_application_service(study)
    configured = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
    assert configured.ok is True
    before = service.get_state().training
    stale_state = service.get_state().to_dict()
    stale_state["training"]["model_name"] = "SCCNet (XBrainLab)"

    result = execute_application_tool_command(
        study,
        "set_model",
        {"model_name": "SCCNet"},
        state=stale_state,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "confirmation_required"
    assert service.get_state().training == before


def test_training_command_uses_authoritative_state_after_confirmation() -> None:
    study = Study()
    service = get_application_service(study)
    configured = service.execute(
        ConfigureTrainingCommand(
            **_training_params(),
            output_dir="./authoritative-output",
        )
    )
    assert configured.ok is True
    params = _authorize(
        study,
        "configure_training",
        _training_params(epoch=5),
    )
    stale_state = service.get_state().to_dict()
    stale_state["training"]["training_option"]["output_dir"] = "./stale-output"

    result = execute_application_tool_command(
        study,
        "configure_training",
        params,
        state=stale_state,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert result.state is not None
    assert (
        result.state["training"]["training_option"]["output_dir"]
        == "./authoritative-output"
    )


def test_host_confirmation_evidence_is_stripped_before_application_command() -> None:
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=17,
        state=state,
        capabilities=build_capability_policy(state),
    )

    class _Runtime:
        command: Command | None = None

        def get_view_publication(self) -> ApplicationViewPublication:
            return publication

        def execute(self, command: Command) -> CommandResult:
            self.command = command
            return CommandResult.success_result(
                command_name=CommandName.CONFIGURE_TRAINING.value,
                message="Training configured.",
                state=state,
                changed_state=ChangedState(training_changed=True),
            )

    runtime = _Runtime()
    params = authorize_assistant_setting_change(
        "configure_training",
        _training_params(epoch=5),
        publication_generation=publication.generation,
    )

    result = execute_application_tool_command(
        object(),
        "configure_training",
        params,
        runtime=runtime,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert isinstance(runtime.command, ConfigureTrainingCommand)
    assert "assistant_setting_confirmation" not in vars(runtime.command)


def test_incomplete_training_settings_remain_an_input_handoff() -> None:
    study = Study()
    service = get_application_service(study)
    before = service.get_state().training

    result = execute_application_tool_command(
        study,
        "configure_training",
        {"epoch": 5},
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "input"
    assert "batch_size" in result.message
    assert "learning_rate" in result.message
    assert service.get_state().training == before
