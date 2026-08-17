"""Target Assistant application-surface ownership and failure contracts."""

from dataclasses import replace

import pytest

from XBrainLab.backend.application import (
    CommandName,
    get_application_service,
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
from XBrainLab.llm.action_contracts import (
    AGENT_ACTION_CONTRACTS,
    AgentExecutionKind,
)
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.application_surface import (
    APPLICATION_COMMAND_TOOLS,
    READ_ONLY_TOOLS,
    TOOL_TO_COMMAND,
    UI_REQUEST_TOOLS,
    ToolCommandResult,
    _command_for_tool,
    build_agent_tool_policy,
    execute_application_tool_command,
    get_application_context,
)


def test_registry_is_the_complete_runtime_and_prompt_boundary() -> None:
    expected = frozenset(
        {
            "import_eeg_data",
            "select_channels",
            "set_montage",
            "create_epochs",
            "configure_dataset_split",
            "select_model",
            "configure_training",
            "apply_bandpass_filter",
            "apply_notch_filter",
            "resample_data",
            "set_reference",
            "normalize_data",
            "start_training",
            "stop_training",
            "reset_preprocessing",
            "clear_training_history",
            "switch_panel",
        }
    )

    assert AGENT_ACTION_CONTRACTS.tool_names() == expected
    assert {tool.name for tool in get_all_tools("mock")} == expected
    assert {tool.name for tool in get_all_tools("real")} == expected
    assert frozenset() == READ_ONLY_TOOLS
    assert expected == APPLICATION_COMMAND_TOOLS | UI_REQUEST_TOOLS
    assert frozenset() == APPLICATION_COMMAND_TOOLS & UI_REQUEST_TOOLS


def test_tool_to_command_projection_matches_approved_owners() -> None:
    assert TOOL_TO_COMMAND == {
        "import_eeg_data": CommandName.SCAN_SOURCE,
        "select_channels": CommandName.PREPROCESS,
        "set_montage": CommandName.APPLY_MONTAGE,
        "create_epochs": CommandName.CREATE_EPOCH,
        "configure_dataset_split": CommandName.CONFIGURE_DATASET_SPLIT,
        "select_model": CommandName.CONFIGURE_TRAINING,
        "configure_training": CommandName.CONFIGURE_TRAINING,
        "apply_bandpass_filter": CommandName.PREPROCESS,
        "apply_notch_filter": CommandName.PREPROCESS,
        "resample_data": CommandName.PREPROCESS,
        "set_reference": CommandName.PREPROCESS,
        "normalize_data": CommandName.PREPROCESS,
        "start_training": CommandName.TRAIN,
        "stop_training": CommandName.STOP_TRAINING,
        "reset_preprocessing": CommandName.RESET_PREPROCESS,
        "clear_training_history": CommandName.CLEAR_TRAINING_HISTORY,
    }


@pytest.mark.parametrize(
    ("tool_name", "params", "command_name"),
    (
        (
            "apply_bandpass_filter",
            {"low_freq": 4, "high_freq": 38},
            CommandName.PREPROCESS,
        ),
        ("apply_notch_filter", {"freq": 60}, CommandName.PREPROCESS),
        ("resample_data", {"rate": 128}, CommandName.PREPROCESS),
        ("set_reference", {"method": "average"}, CommandName.PREPROCESS),
        ("normalize_data", {"method": "z-score"}, CommandName.PREPROCESS),
        ("start_training", {}, CommandName.TRAIN),
        ("stop_training", {}, CommandName.STOP_TRAINING),
        ("reset_preprocessing", {}, CommandName.RESET_PREPROCESS),
        ("clear_training_history", {}, CommandName.CLEAR_TRAINING_HISTORY),
    ),
)
def test_application_command_builders_match_declared_owner(
    tool_name: str,
    params: dict[str, object],
    command_name: CommandName,
) -> None:
    contract = AGENT_ACTION_CONTRACTS.contract_for(tool_name)
    assert contract is not None
    assert contract.execution_kind is AgentExecutionKind.APPLICATION_COMMAND

    command = _command_for_tool(tool_name, params)

    assert command is not None
    assert command.name is command_name


@pytest.mark.parametrize(
    "tool_name",
    (
        "import_eeg_data",
        "select_channels",
        "set_montage",
        "create_epochs",
        "configure_dataset_split",
        "select_model",
        "configure_training",
        "switch_panel",
    ),
)
def test_ui_request_tools_never_build_application_commands(tool_name: str) -> None:
    assert _command_for_tool(tool_name, {}) is None
    assert execute_application_tool_command(Study(), tool_name, {}) is None


def test_application_command_without_runtime_fails_closed() -> None:
    result = execute_application_tool_command(
        object(),
        "apply_bandpass_filter",
        {"low_freq": 4, "high_freq": 38},
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "contract"
    assert result.error_code == "application_tool_runtime_required"


def test_direct_preprocess_uses_backend_precondition_on_empty_study() -> None:
    result = execute_application_tool_command(
        Study(),
        "apply_bandpass_filter",
        {"low_freq": 4, "high_freq": 38},
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "precondition"
    assert "Load raw data" in result.message


def test_start_training_preserves_backend_confirmation_boundary() -> None:
    result = execute_application_tool_command(Study(), "start_training", {})

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "precondition"
    assert "Save a valid data splitting specification" in result.message


def test_stale_publication_exposes_only_navigation() -> None:
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=12,
        state=state,
        capabilities=get_application_service(Study())
        .get_view_publication()
        .capabilities,
        verified=True,
        stale=True,
        refresh_error="Traceback: /private/runtime.py SECRET_TOKEN_123",
    )

    policy = build_agent_tool_policy(Study(), publication=publication)

    assert policy["switch_panel"].enabled is True
    for tool_name, availability in policy.items():
        if tool_name == "switch_panel":
            continue
        assert availability.enabled is False
        serialized = str(availability.to_dict())
        assert "Traceback" not in serialized
        assert "/private/runtime.py" not in serialized
        assert "SECRET_TOKEN_123" not in serialized


def test_target_policy_is_derived_from_one_publication_generation() -> None:
    study = Study()
    service = get_application_service(study)
    publication = service.get_view_publication()
    newer = replace(publication, generation=publication.generation + 1)

    class _Runtime:
        @staticmethod
        def get_view_publication():
            return newer

        @staticmethod
        def execute(command):
            raise AssertionError(command)

    policy = build_agent_tool_policy(study, publication=newer)
    context = get_application_context(object(), "switch_panel", runtime=_Runtime())

    assert set(policy) == AGENT_ACTION_CONTRACTS.tool_names()
    assert context is not None
    assert context.generation == newer.generation
