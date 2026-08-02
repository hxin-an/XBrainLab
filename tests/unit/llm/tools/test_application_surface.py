"""Tests for the ApplicationService-backed agent tool surface."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast
from unittest.mock import MagicMock

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    AttachLabelsCommand,
    ChangedState,
    Command,
    CommandName,
    CommandResult,
    LoadDataCommand,
    PreprocessedStateSnapshot,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    ResetPreprocessCommand,
    SaliencyCommand,
    StopTrainingCommand,
    get_application_service,
)
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.dataset import (
    Dataset,
    DataSplittingConfig,
    Epochs,
    EpochWindowProvenance,
    TrainingType,
)
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.study import Study
from XBrainLab.backend.training.trainer import Trainer
from XBrainLab.backend.utils.public_diagnostics import (
    PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES,
)
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
    CapabilityPolicyUnavailable,
    ToolAvailability,
    ToolCommandResult,
    UserProvidedTrainingOutputDir,
    _command_for_tool,
    blocked_tool_reasons,
    build_agent_tool_policy,
    execute_application_tool_command,
    get_application_context,
    normalize_tool_result,
)
from XBrainLab.llm.tools.result_contract import ToolResult
from XBrainLab.llm.tools.schema_contract import TOOL_TAXONOMY


class _ApplicationRuntimeFake:
    def __init__(
        self,
        *,
        publication: ApplicationViewPublication,
        command_result: CommandResult | None = None,
    ) -> None:
        self._publication = publication
        self._command_result = command_result
        self.publication_reads = 0
        self.commands: list[Command] = []

    def get_view_publication(self) -> ApplicationViewPublication:
        self.publication_reads += 1
        return self._publication

    def execute(self, command: Command) -> CommandResult:
        self.commands.append(command)
        if self._command_result is None:
            raise AssertionError("this fake was not configured for command execution")
        return self._command_result


def _assert_tool_command_result(
    result: object,
    *,
    tool_name: str,
    command_name: CommandName,
    ok: bool | None = None,
    error_type: str | None = None,
    raw_status: str | None = None,
) -> ToolCommandResult:
    assert isinstance(result, ToolCommandResult), result
    assert result.tool_name == tool_name
    assert result.command_name == command_name.value
    assert isinstance(result.state, dict)
    assert isinstance(result.capability, dict)
    assert result.capability["tool_name"] == tool_name
    assert result.capability["command_name"] == command_name.value
    if ok is not None:
        assert result.ok is ok
    if error_type is not None:
        assert result.error_type == error_type
    if raw_status is not None:
        assert isinstance(result.raw_result, dict)
        assert result.raw_result["status"] == raw_status
        assert result.raw_result["command_name"] == command_name.value
    return result


def _state(result: ToolCommandResult) -> dict[str, Any]:
    assert isinstance(result.state, dict)
    return result.state


def test_agent_action_contract_registry_has_unique_tools_and_intent_aliases():
    contracts = AGENT_ACTION_CONTRACTS.contracts
    tool_names = [contract.canonical_tool for contract in contracts]
    intent_aliases = [
        alias for contract in contracts for alias in contract.intent_aliases
    ]

    assert len(contracts) == 31
    assert len(tool_names) == len(set(tool_names))
    assert len(intent_aliases) == len(set(intent_aliases))


def test_tool_to_command_compatibility_view_does_not_drift_from_registry():
    expected = {
        "scan_source": CommandName.SCAN_SOURCE,
        "preview_interpretation": CommandName.PREVIEW_INTERPRETATION,
        "validate_interpretation": CommandName.VALIDATE_INTERPRETATION,
        "apply_interpretation": CommandName.APPLY_INTERPRETATION,
        "save_interpretation_recipe": CommandName.SAVE_INTERPRETATION_RECIPE,
        "reload_interpretation_recipe": CommandName.RELOAD_INTERPRETATION_RECIPE,
        "load_data": CommandName.LOAD_DATA,
        "attach_labels": CommandName.ATTACH_LABELS,
        "apply_standard_preprocess": CommandName.PREPROCESS,
        "apply_bandpass_filter": CommandName.PREPROCESS,
        "apply_notch_filter": CommandName.PREPROCESS,
        "resample_data": CommandName.PREPROCESS,
        "normalize_data": CommandName.PREPROCESS,
        "set_reference": CommandName.PREPROCESS,
        "select_channels": CommandName.PREPROCESS,
        "reset_preprocess": CommandName.RESET_PREPROCESS,
        "set_montage": CommandName.APPLY_MONTAGE,
        "epoch_data": CommandName.CREATE_EPOCH,
        "generate_dataset": CommandName.GENERATE_DATASET,
        "set_model": CommandName.CONFIGURE_TRAINING,
        "configure_training": CommandName.CONFIGURE_TRAINING,
        "start_training": CommandName.TRAIN,
        "stop_training": CommandName.STOP_TRAINING,
        "evaluate": CommandName.EVALUATE,
        "visualize": CommandName.VISUALIZE,
        "saliency": CommandName.SALIENCY,
        "clear_dataset": CommandName.RESET_SESSION,
        "query_state": CommandName.QUERY_STATE,
    }

    assert expected == TOOL_TO_COMMAND
    assert AGENT_ACTION_CONTRACTS.tool_to_command() == TOOL_TO_COMMAND


def test_action_contract_registry_is_the_complete_runtime_and_prompt_boundary():
    expected = AGENT_ACTION_CONTRACTS.tool_names()

    assert frozenset(TOOL_TAXONOMY) == expected
    assert frozenset(tool.name for tool in get_all_tools("mock")) == expected
    assert frozenset(tool.name for tool in get_all_tools("real")) == expected
    assert (
        AGENT_ACTION_CONTRACTS.tool_names_for_kind(
            AgentExecutionKind.APPLICATION_COMMAND
        )
        == APPLICATION_COMMAND_TOOLS
    )
    assert (
        AGENT_ACTION_CONTRACTS.tool_names_for_kind(AgentExecutionKind.UI_REQUEST)
        == UI_REQUEST_TOOLS
    )
    assert (
        AGENT_ACTION_CONTRACTS.tool_names_for_kind(AgentExecutionKind.READ_ONLY)
        == READ_ONLY_TOOLS
    )


def test_every_application_tool_builder_matches_its_declared_command():
    valid_params = {
        "scan_source": {"source_path": "recording.edf"},
        "preview_interpretation": {},
        "validate_interpretation": {},
        "apply_interpretation": {},
        "save_interpretation_recipe": {},
        "reload_interpretation_recipe": {"recipe_path": "import.recipe.json"},
        "attach_labels": {"mapping": {"recording.edf": "events.tsv"}},
        "apply_standard_preprocess": {},
        "apply_bandpass_filter": {"low_freq": 1.0, "high_freq": 40.0},
        "apply_notch_filter": {"freq": 50.0},
        "resample_data": {"rate": 128},
        "normalize_data": {"method": "zscore"},
        "set_reference": {"method": "average"},
        "select_channels": {"channels": ["C3", "C4"]},
        "reset_preprocess": {},
        "epoch_data": {"t_min": -0.2, "t_max": 1.0},
        "generate_dataset": {
            "split_strategy": "trial",
            "training_mode": "full_data",
        },
        "set_model": {"model_name": "EEGNet"},
        "configure_training": {
            "model_name": "EEGNet",
            "epoch": 1,
            "batch_size": 8,
            "learning_rate": 0.001,
        },
        "start_training": {},
        "stop_training": {},
        "evaluate": {},
        "visualize": {},
        "saliency": {},
        "clear_dataset": {},
        "query_state": {},
    }

    application_contracts = tuple(
        contract
        for contract in AGENT_ACTION_CONTRACTS.contracts_for_kind(
            AgentExecutionKind.APPLICATION_COMMAND
        )
        if contract.canonical_tool != "load_data"
    )
    assert set(valid_params) == {
        contract.canonical_tool for contract in application_contracts
    }
    for contract in application_contracts:
        command = _command_for_tool(
            contract.canonical_tool,
            valid_params[contract.canonical_tool],
        )
        if command is None:
            pytest.fail(
                f"{contract.canonical_tool} did not build its application command"
            )
        assert command.name is contract.capability_command, contract.canonical_tool
    assert _command_for_tool("load_data", {"paths": ["recording.edf"]}) is None


def test_agent_tool_policy_reuses_application_train_reasons():
    study = Study()
    service = get_application_service(study)

    application_train = service.get_capabilities().get(CommandName.TRAIN)
    tool_policy = build_agent_tool_policy(study)

    start_training = tool_policy["start_training"]
    assert start_training.enabled is False
    assert start_training.command_name == CommandName.TRAIN.value
    assert start_training.reasons == tuple(application_train.reasons)
    assert "Generate datasets before training." in start_training.reasons


def test_agent_tool_policy_disables_legacy_direct_file_loading():
    availability = build_agent_tool_policy(Study())["load_data"]

    assert availability.enabled is False
    assert availability.can_auto_execute is False
    assert availability.command_name == CommandName.LOAD_DATA.value
    assert "cannot preserve an authorized filesystem identity" in (
        availability.reason_text
    )


def test_agent_tool_policy_reads_state_and_capabilities_from_one_publication():
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=11,
        state=state,
        capabilities=build_capability_policy(state),
    )
    runtime = _ApplicationRuntimeFake(publication=publication)

    policy = build_agent_tool_policy(object(), runtime=runtime)

    assert runtime.publication_reads == 1
    assert policy["query_state"].enabled is True


def test_mapped_product_tool_without_application_runtime_fails_closed():
    result = execute_application_tool_command(
        object(),
        "query_state",
        {"query": "state"},
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.tool_name == "query_state"
    assert result.command_name == CommandName.QUERY_STATE.value
    assert result.error_type == "contract"
    assert result.recoverable is False
    assert result.error_code == "application_tool_runtime_required"
    assert result.message == (
        "ApplicationToolRuntime is required for mapped product tool execution."
    )
    assert result.recovery_action == "provide_application_tool_runtime"
    assert result.to_payload()["error_code"] == result.error_code
    assert result.to_payload()["recovery_action"] == result.recovery_action


def test_tool_payload_preserves_changed_state_for_agent_recovery():
    result = ToolCommandResult.failure(
        "query_state",
        "Application state must be refreshed.",
        error_code="unexpected_tool_failure",
        recovery_action="refresh_application_state",
        changed_state={"state_unknown": True},
    )

    assert result.to_payload()["changed_state"] == {"state_unknown": True}


def test_tool_payload_rejects_hostile_scalar_and_mapping_protocols() -> None:
    private_path = "/srv/private/patient-Jane/session.edf"

    class HostileTruth:
        def __bool__(self) -> bool:
            raise AssertionError("hostile bool protocol executed")

    class HostileText(str):
        def __str__(self) -> str:
            raise AssertionError("hostile string protocol executed")

    class HostileMapping(dict):
        def __iter__(self):
            raise AssertionError("hostile mapping iteration executed")

        def __len__(self):
            raise AssertionError("hostile mapping length executed")

        def __getitem__(self, key):
            raise AssertionError("hostile mapping item access executed")

        def items(self):
            raise AssertionError("hostile mapping items executed")

    result = ToolCommandResult(
        ok=HostileTruth(),  # type: ignore[arg-type]
        tool_name=HostileText(private_path),
        command_name=HostileText(private_path),
        message=HostileText(private_path),
        recoverable=HostileTruth(),  # type: ignore[arg-type]
        diagnostics=HostileMapping({"private_path": private_path}),
        changed_state=HostileMapping({"private_path": True}),
    )

    payload = result.to_payload()
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["ok"] is False
    assert payload["recoverable"] is False
    assert type(payload["tool_name"]) is str
    assert payload["command_name"] is None or type(payload["command_name"]) is str
    assert payload["changed_state"] == {}
    assert private_path not in serialized


def test_tool_payload_redacts_normalized_nested_sensitive_keys_fail_closed() -> None:
    private_values = (
        "credential-secret",
        "session=private-cookie",
        "private-refresh-token",
        "Mary Example",
        "subject-private-uuid",
        "Mary Example.edf",
        "Clinical Records/Mary Example",
        "recipes/Mary Example.json",
    )

    class HostileContainer(dict[str, object]):
        def __iter__(self):
            raise AssertionError("hostile container iteration executed")

        def __len__(self) -> int:
            raise AssertionError("hostile container length executed")

        def items(self):
            raise AssertionError("hostile container items executed")

    result = ToolCommandResult(
        ok=False,
        tool_name="query_state",
        message="The query failed; refresh application state.",
        raw_result={
            "nested": {
                "Credential": private_values[0],
                "Cookie": private_values[1],
                "refreshToken": private_values[2],
                "participant_identity": private_values[3],
                "subject_uuid": private_values[4],
                "filename": private_values[5],
                "input_path": private_values[6],
                "recipePath": private_values[7],
            },
            "hostile": HostileContainer({"input_path": private_values[6]}),
        },
        diagnostics={"hostile": HostileContainer({"Cookie": private_values[1]})},
    )

    payload = result.to_payload()
    serialized = json.dumps(payload, ensure_ascii=False)

    assert all(value not in serialized for value in private_values)
    assert payload["raw_result"]["hostile"] == "[UNSUPPORTED_VALUE]"
    assert payload["diagnostics"]["hostile"] == "[UNSUPPORTED_VALUE]"
    assert "refresh application state" in payload["message"]


def test_tool_payload_caps_the_complete_serialized_envelope() -> None:
    large = "x" * PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES
    result = ToolCommandResult(
        ok=True,
        tool_name=large,
        command_name=large,
        message=large,
        raw_result={"value": large},
        state={"value": large},
        capability={"value": large},
        diagnostics={"value": large},
        changed_state={large: True},
    )

    payload = result.to_payload()
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    assert set(payload) == {
        "ok",
        "tool_name",
        "command_name",
        "message",
        "error_type",
        "error_code",
        "recovery_action",
        "recoverable",
        "blocked_reason",
        "state",
        "capability",
        "diagnostics",
        "changed_state",
        "raw_result",
    }
    assert len(serialized) <= PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES


@pytest.mark.parametrize(
    ("tool_name", "command_name"),
    [
        ("reset_preprocess", CommandName.RESET_PREPROCESS),
        ("stop_training", CommandName.STOP_TRAINING),
    ],
)
def test_lifecycle_tools_without_application_runtime_fail_closed(
    tool_name: str,
    command_name: CommandName,
) -> None:
    result = execute_application_tool_command(object(), tool_name, {})

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.command_name == command_name.value
    assert result.error_code == "application_tool_runtime_required"
    assert result.recoverable is False


def test_explicit_application_runtime_executes_for_headless_context():
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=12,
        state=state,
        capabilities=build_capability_policy(state),
    )
    runtime = _ApplicationRuntimeFake(
        publication=publication,
        command_result=CommandResult.success_result(
            command_name=CommandName.QUERY_STATE.value,
            message="Application state snapshot ready.",
            state=state,
            changed_state=ChangedState(),
        ),
    )

    result = execute_application_tool_command(
        object(),
        "query_state",
        {"query": "state"},
        runtime=runtime,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert result.error_code is None
    assert result.recovery_action is None
    assert len(runtime.commands) == 1
    assert isinstance(runtime.commands[0], QueryStateCommand)


def test_saliency_application_surface_preserves_flat_noise_parameters() -> None:
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=13,
        state=state,
        capabilities=build_capability_policy(state),
    )
    runtime = _ApplicationRuntimeFake(
        publication=publication,
        command_result=CommandResult.success_result(
            command_name=CommandName.SALIENCY.value,
            message="Saliency parameters configured.",
            state=state,
            changed_state=ChangedState(visualization_changed=True),
        ),
    )
    availability = ToolAvailability(
        tool_name="saliency",
        enabled=True,
        command_name=CommandName.SALIENCY.value,
    )

    result = execute_application_tool_command(
        object(),
        "saliency",
        {
            "method": "SmoothGrad",
            "nt_samples": 2,
            "nt_samples_batch_size": 1,
            "stdevs": 1.0,
        },
        availability=availability,
        state=state.to_dict(),
        runtime=runtime,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert len(runtime.commands) == 1
    command = runtime.commands[0]
    assert isinstance(command, SaliencyCommand)
    assert command.method == "SmoothGrad"
    assert command.params == {
        "nt_samples": 2,
        "nt_samples_batch_size": 1,
        "stdevs": 1.0,
    }


def test_saliency_application_surface_preserves_host_resource_receipt() -> None:
    command = _command_for_tool(
        "saliency",
        {
            "method": "Gradient",
            "resource_preflight_confirmed": True,
            "resource_preflight_token": "saliency-receipt-1",
        },
    )

    assert isinstance(command, SaliencyCommand)
    command = cast(SaliencyCommand, command)
    assert command.resource_preflight_confirmed is True
    assert command.resource_preflight_token == "saliency-receipt-1"  # noqa: S105


def test_reset_preprocess_tool_routes_to_narrow_command_and_publishes_final_state():
    before = ApplicationStateSnapshot.empty()
    after = replace(
        before,
        pipeline_stage="data_loaded",
        preprocessed=PreprocessedStateSnapshot(),
        active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
    )
    publication = ApplicationViewPublication(
        generation=93,
        state=before,
        capabilities=build_capability_policy(before),
    )
    runtime = _ApplicationRuntimeFake(
        publication=publication,
        command_result=CommandResult.success_result(
            command_name=CommandName.RESET_PREPROCESS.value,
            message="Preprocessing reset to loaded raw data.",
            state=after,
            changed_state=ChangedState(preprocessed_changed=True),
        ),
    )
    availability = ToolAvailability(
        tool_name="reset_preprocess",
        enabled=True,
        command_name=CommandName.RESET_PREPROCESS.value,
    )

    result = execute_application_tool_command(
        object(),
        "reset_preprocess",
        {"confirmed": True},
        availability=availability,
        state=before.to_dict(),
        runtime=runtime,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert len(runtime.commands) == 1
    command = runtime.commands[0]
    assert isinstance(command, ResetPreprocessCommand)
    assert command.confirmed is True
    assert _state(result)["active_dataset"]["has_raw_data"] is True
    assert _state(result)["preprocessed"]["available"] is False


def test_stop_training_tool_routes_to_execution_control_and_publishes_final_state():
    before = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="training",
        active_training=ActiveTrainingSnapshot(
            has_model=True,
            has_training_option=True,
            has_trainer=True,
            is_running=True,
        ),
    )
    after = replace(
        before,
        pipeline_stage="trained",
        active_training=replace(before.active_training, is_running=False),
    )
    publication = ApplicationViewPublication(
        generation=94,
        state=before,
        capabilities=build_capability_policy(before),
    )
    runtime = _ApplicationRuntimeFake(
        publication=publication,
        command_result=CommandResult.success_result(
            command_name=CommandName.STOP_TRAINING.value,
            message="Training stopped.",
            state=after,
            changed_state=ChangedState(training_changed=True),
        ),
    )
    availability = ToolAvailability(
        tool_name="stop_training",
        enabled=True,
        command_name=CommandName.STOP_TRAINING.value,
    )

    result = execute_application_tool_command(
        object(),
        "stop_training",
        {},
        availability=availability,
        state=before.to_dict(),
        runtime=runtime,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert len(runtime.commands) == 1
    assert isinstance(runtime.commands[0], StopTrainingCommand)
    assert _state(result)["active_training"]["is_running"] is False


@pytest.mark.parametrize(
    ("tool_name", "command_name", "params", "command_type"),
    [
        (
            "preview_interpretation",
            CommandName.PREVIEW_INTERPRETATION,
            {
                "scan_id": "scan-1",
                "choices": {"skip_labels": True},
                "resource_preflight_confirmed": True,
                "resource_preflight_token": "preview-receipt-1",
            },
            PreviewInterpretationCommand,
        ),
        (
            "reload_interpretation_recipe",
            CommandName.RELOAD_INTERPRETATION_RECIPE,
            {
                "recipe_path": "/tmp/recipe.json",
                "resource_preflight_confirmed": True,
                "resource_preflight_token": "reload-receipt-1",
            },
            ReloadInterpretationRecipeCommand,
        ),
    ],
)
def test_data_interpretation_surface_forwards_host_resource_receipt(
    tool_name: str,
    command_name: CommandName,
    params: dict[str, object],
    command_type: type[Command],
) -> None:
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=95,
        state=state,
        capabilities=build_capability_policy(state),
    )
    runtime = _ApplicationRuntimeFake(
        publication=publication,
        command_result=CommandResult.success_result(
            command_name=command_name.value,
            message="Interpretation command completed.",
            state=state,
            changed_state=ChangedState(),
        ),
    )
    availability = ToolAvailability(
        tool_name=tool_name,
        enabled=True,
        command_name=command_name.value,
    )

    result = execute_application_tool_command(
        object(),
        tool_name,
        params,
        availability=availability,
        state=state.to_dict(),
        runtime=runtime,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is True
    assert len(runtime.commands) == 1
    command = runtime.commands[0]
    assert isinstance(command, command_type)
    assert command.resource_preflight_confirmed is True
    assert command.resource_preflight_token == params["resource_preflight_token"]


def test_attach_labels_surface_preserves_paths_and_host_resource_receipt() -> None:
    command = _command_for_tool(
        "attach_labels",
        {
            "mapping": {
                "A01T.gdf": "/labels/A01T.mat",
                "A02T.gdf": "/labels/A02T.mat",
            },
            "label_format": "mat",
            "selected_event_names": ["769", "770", "771", "772"],
            "resource_preflight_confirmed": True,
            "resource_preflight_token": "label-receipt-1",
        },
    )

    assert isinstance(command, AttachLabelsCommand)
    command = cast(AttachLabelsCommand, command)
    assert command.label_paths == ["/labels/A01T.mat", "/labels/A02T.mat"]
    assert command.label_format == "mat"
    assert command.selected_event_names == ["769", "770", "771", "772"]
    assert command.resource_preflight_confirmed is True
    assert command.resource_preflight_token == "label-receipt-1"  # noqa: S105


def test_generate_dataset_surface_does_not_guess_missing_split_decisions():
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=14,
        state=state,
        capabilities=build_capability_policy(state),
    )
    runtime = _ApplicationRuntimeFake(publication=publication)
    availability = ToolAvailability(
        tool_name="generate_dataset",
        enabled=True,
        reasons=(),
        command_name=CommandName.GENERATE_DATASET.value,
    )

    result = execute_application_tool_command(
        object(),
        "generate_dataset",
        {"test_ratio": 0.2, "val_ratio": 0.2},
        availability=availability,
        state=state.to_dict(),
        runtime=runtime,
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "input"
    assert result.recoverable is True
    assert runtime.commands == []


@pytest.mark.parametrize(
    ("tool_name", "command_name", "params"),
    [
        (
            "apply_interpretation",
            CommandName.APPLY_INTERPRETATION,
            {"confirmed": "false"},
        ),
        ("start_training", CommandName.TRAIN, {"confirmed": 1}),
        ("clear_dataset", CommandName.RESET_SESSION, {"confirmed": "true"}),
    ],
)
def test_application_surface_rejects_non_boolean_confirmation_values(
    tool_name: str,
    command_name: CommandName,
    params: dict[str, object],
) -> None:
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=15,
        state=state,
        capabilities=build_capability_policy(state),
    )
    runtime = _ApplicationRuntimeFake(publication=publication)
    availability = ToolAvailability(
        tool_name=tool_name,
        enabled=True,
        reasons=(),
        command_name=command_name.value,
    )

    result = execute_application_tool_command(
        object(),
        tool_name,
        params,
        availability=availability,
        state=state.to_dict(),
        runtime=runtime,
    )

    result = _assert_tool_command_result(
        result,
        tool_name=tool_name,
        command_name=command_name,
        ok=False,
        error_type="input",
    )
    assert "must be a boolean" in result.message
    assert runtime.commands == []


def test_stale_publication_preserves_recovery_tools_with_safe_public_reason():
    study = Study()
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=12,
        state=state,
        capabilities=build_capability_policy(state),
        verified=True,
        stale=True,
        refresh_error="training state changed during snapshot",
    )
    runtime = _ApplicationRuntimeFake(publication=publication)

    policy = build_agent_tool_policy(study, publication=publication)
    context = get_application_context(
        object(),
        "query_state",
        runtime=runtime,
    )

    if context is None:
        pytest.fail("explicit application runtime did not publish tool context")
    assert policy["query_state"].enabled is True
    assert policy["clear_dataset"].enabled is True
    assert policy["clear_dataset"].requires_confirmation is True
    assert policy["scan_source"].enabled is False
    assert policy["list_files"].enabled is False
    assert context.generation == publication.generation
    assert context.availability.enabled is True
    assert context.policy_error == "Workflow state is temporarily unavailable."
    assert publication.diagnostic_error == "training state changed during snapshot"
    assert context.state == state.to_dict()


def test_stale_publication_keeps_raw_diagnostic_out_of_capability_reasons():
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=13,
        state=state,
        capabilities=build_capability_policy(state),
        stale=True,
        refresh_error="Traceback: /private/runtime.py SECRET_TOKEN_123",
    )

    policy = build_agent_tool_policy(Study(), publication=publication)

    scan_source = policy["scan_source"]
    assert scan_source.enabled is False
    assert scan_source.reasons == ("Workflow state is temporarily unavailable.",)
    serialized = str(scan_source.to_dict())
    assert "Traceback" not in serialized
    assert "/private/runtime.py" not in serialized
    assert "SECRET_TOKEN_123" not in serialized
    assert publication.public_unavailable_code == "application_state_unavailable"
    assert publication.diagnostic_error == (
        "Traceback: /private/runtime.py SECRET_TOKEN_123"
    )


def test_application_tool_result_capability_is_rebuilt_from_post_command_state():
    study = Study()
    pre_command_availability = ToolAvailability(
        tool_name="set_model",
        enabled=True,
        reasons=("stale pre-command reason",),
        command_name=CommandName.CONFIGURE_TRAINING.value,
    )

    result = execute_application_tool_command(
        study,
        "set_model",
        {"model_name": "EEGNet"},
        availability=pre_command_availability,
        state={"pipeline_stage": "empty"},
    )

    result = _assert_tool_command_result(
        result,
        tool_name="set_model",
        command_name=CommandName.CONFIGURE_TRAINING,
        ok=True,
        raw_status="ok",
    )
    post_command_availability = build_agent_tool_policy(study)["set_model"]
    assert result.capability == post_command_availability.to_dict()
    assert result.capability != pre_command_availability.to_dict()
    assert _state(result)["training"]["has_model"] is True


def test_start_training_surface_preserves_backend_confirmation_boundary():
    study = Study()
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    study.loaded_data_list = [raw]
    labels = np.arange(12, dtype=int) % 2
    events = np.column_stack((np.arange(12), np.zeros(12, dtype=int), labels))
    info = mne.create_info(
        [f"EEG-{index}" for index in range(4)],
        sfreq=128,
        ch_types="eeg",
    )
    mne_epochs = mne.EpochsArray(
        np.zeros((12, 4, 168), dtype=np.float32),
        info,
        events=events,
        event_id={"class-0": 0, "class-1": 1},
        verbose=False,
    )
    epoch_data = Epochs([Raw("confirmation-boundary-epo.fif", mne_epochs)])
    epoch_data.epoch_window_provenance = tuple(
        EpochWindowProvenance(
            source_recording_id=f"path-sha256:{'a' * 64}",
            event_sample=index * 200,
            window_start_sample=index * 200,
            window_end_sample_exclusive=index * 200 + 168,
            source_sfreq=128.0,
            epoch_sfreq=128.0,
            tmin_seconds=0.0,
            tmax_seconds=167 / 128,
            source_coordinates_verified=True,
        )
        for index in range(12)
    )
    dataset = Dataset(
        epoch_data,
        DataSplittingConfig(TrainingType.FULL, False, [], []),
    )
    dataset.set_name("confirmation-boundary")
    dataset.train_mask[:8] = True
    dataset.val_mask[8:10] = True
    dataset.test_mask[10:] = True
    dataset.remaining_mask[:] = False
    cast(Any, study).datasets = [dataset]
    configured = execute_application_tool_command(
        study,
        "configure_training",
        {
            "model_name": "EEGNet",
            "epoch": 1,
            "batch_size": 2,
            "learning_rate": 0.001,
            "device": "cpu",
        },
    )
    assert isinstance(configured, ToolCommandResult)
    assert configured.ok is True
    training = study.training_state_service
    training.start_training = MagicMock(return_value=1)  # type: ignore[method-assign]

    unconfirmed = execute_application_tool_command(study, "start_training", {})

    unconfirmed = _assert_tool_command_result(
        unconfirmed,
        tool_name="start_training",
        command_name=CommandName.TRAIN,
        ok=False,
        error_type="confirmation_required",
        raw_status="failed",
    )
    assert unconfirmed.blocked_reason == "train requires confirmation."
    assert unconfirmed.raw_result["changed_state"]["error_changed"] is False
    assert unconfirmed.changed_state["error_changed"] is False

    trainer = Trainer([])
    trainer.run(interact=False)
    study.training_manager.trainer = trainer
    confirmed = execute_application_tool_command(
        study,
        "start_training",
        {"confirmed": True},
    )

    confirmed = _assert_tool_command_result(
        confirmed,
        tool_name="start_training",
        command_name=CommandName.TRAIN,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert confirmed.message == "Training started."
    diagnostics = confirmed.raw_result["diagnostics"]
    assert diagnostics["append"] is True
    assert diagnostics["interactive"] is True
    assert diagnostics["resource_preflight"]["risk_level"] in {
        "safe",
        "warning",
        "unknown",
    }
    training.start_training.assert_called_once()


def test_blocked_tool_reasons_are_grouped_by_application_command():
    blocked = blocked_tool_reasons(Study())

    assert "train" in blocked
    assert "preprocess" in blocked
    assert "start_training" not in blocked
    assert "apply_bandpass_filter" not in blocked


def test_mapped_tool_missing_params_returns_input_failure():
    study = Study()
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    study.data_manager.loaded_data_list = [raw]

    result = execute_application_tool_command(study, "apply_bandpass_filter", {})

    result = _assert_tool_command_result(
        result,
        tool_name="apply_bandpass_filter",
        command_name=CommandName.PREPROCESS,
        ok=False,
        error_type="input",
    )
    assert "Required inputs" in result.message


def test_clear_dataset_surface_preserves_reset_confirmation_boundary():
    study = Study()
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    raw.is_raw.return_value = True
    study.data_manager.loaded_data_list = [raw]

    clear_dataset = build_agent_tool_policy(study)["clear_dataset"]

    assert clear_dataset.enabled is True
    assert clear_dataset.command_name == CommandName.RESET_SESSION.value
    assert clear_dataset.destructive is True
    assert clear_dataset.confirmation_required is True


def test_data_interpretation_surface_preserves_autonomy_policy(tmp_path):
    study = Study()
    source = tmp_path / "sub-01_task-mi_run-1.gdf"
    source.write_bytes(b"placeholder")

    policy = build_agent_tool_policy(study)
    scan_source = policy["scan_source"]

    assert scan_source.enabled is True
    assert scan_source.command_name == CommandName.SCAN_SOURCE.value
    assert scan_source.can_auto_execute is True
    assert scan_source.decision_boundary == "read_only_discovery"

    scan_result = execute_application_tool_command(
        study,
        "scan_source",
        {"source_path": str(source)},
    )
    scan_result = _assert_tool_command_result(
        scan_result,
        tool_name="scan_source",
        command_name=CommandName.SCAN_SOURCE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert scan_result.raw_result["diagnostics"]["payload_type"] == "scan_result"

    preview_result = execute_application_tool_command(
        study,
        "preview_interpretation",
        {},
    )
    preview_result = _assert_tool_command_result(
        preview_result,
        tool_name="preview_interpretation",
        command_name=CommandName.PREVIEW_INTERPRETATION,
        ok=True,
        error_type="none",
        raw_status="ok",
    )

    validate_result = execute_application_tool_command(
        study,
        "validate_interpretation",
        {},
    )
    validate_result = _assert_tool_command_result(
        validate_result,
        tool_name="validate_interpretation",
        command_name=CommandName.VALIDATE_INTERPRETATION,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert _state(validate_result)["interpretation"]["has_validation_decision"] is True

    apply_interpretation = build_agent_tool_policy(study)["apply_interpretation"]

    assert apply_interpretation.enabled is True
    assert apply_interpretation.command_name == CommandName.APPLY_INTERPRETATION.value
    assert apply_interpretation.confirmation_required is True
    assert apply_interpretation.requires_confirmation is True
    assert apply_interpretation.can_auto_execute is False
    assert apply_interpretation.stop_after_success is True
    assert apply_interpretation.blocks_downstream_until_confirmed is True
    assert apply_interpretation.to_dict()["decision_boundary"] == "semantic_apply"


def test_application_tool_command_routes_data_interpretation_scan(tmp_path):
    source = tmp_path / "sample.fif"
    source.write_bytes(b"placeholder")

    result = execute_application_tool_command(
        Study(),
        "scan_source",
        {"source_path": str(source), "source_hint": "file"},
    )

    result = _assert_tool_command_result(
        result,
        tool_name="scan_source",
        command_name=CommandName.SCAN_SOURCE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert result.raw_result["diagnostics"]["payload_type"] == "scan_result"


def test_application_tool_command_routes_scan_label_sources(tmp_path):
    source_dir = tmp_path / "eeg"
    label_dir = tmp_path / "labels"
    source_dir.mkdir()
    label_dir.mkdir()
    eeg_path = source_dir / "sub-01_task-mi_raw.fif"
    label_path = label_dir / "sub-01_task-mi_events.tsv"
    eeg_path.write_bytes(b"placeholder")
    label_path.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")

    result = execute_application_tool_command(
        Study(),
        "scan_source",
        {"source_path": str(source_dir), "label_sources": [str(label_dir)]},
    )

    result = _assert_tool_command_result(
        result,
        tool_name="scan_source",
        command_name=CommandName.SCAN_SOURCE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    scan = result.raw_result["diagnostics"]["scan_result"]
    assert str(label_dir.resolve()) not in repr(scan["label_sources"])
    assert scan["label_sources"][0].startswith("private location [REDACTED_PATH]")
    assert str(label_path.resolve()) not in repr(scan["label_carriers"])
    assert "[REDACTED_PATH]" in scan["label_carriers"][0]
    assert "[SUBJECT_REF:" in scan["label_carriers"][0]


def test_application_tool_command_apply_surfaces_confirmation_required(tmp_path):
    study = Study()
    source = tmp_path / "sub-01_task-mi_run-1.gdf"
    source.write_bytes(b"placeholder")

    scan_result = execute_application_tool_command(
        study,
        "scan_source",
        {"source_path": str(source)},
    )
    scan_result = _assert_tool_command_result(
        scan_result,
        tool_name="scan_source",
        command_name=CommandName.SCAN_SOURCE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert scan_result.raw_result["diagnostics"]["payload_type"] == "scan_result"

    preview_result = execute_application_tool_command(
        study,
        "preview_interpretation",
        {},
    )
    preview_result = _assert_tool_command_result(
        preview_result,
        tool_name="preview_interpretation",
        command_name=CommandName.PREVIEW_INTERPRETATION,
        ok=True,
        error_type="none",
        raw_status="ok",
    )

    validate_result = execute_application_tool_command(
        study,
        "validate_interpretation",
        {},
    )
    validate_result = _assert_tool_command_result(
        validate_result,
        tool_name="validate_interpretation",
        command_name=CommandName.VALIDATE_INTERPRETATION,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert _state(validate_result)["interpretation"]["has_validation_decision"] is True

    result = execute_application_tool_command(study, "apply_interpretation", {})

    result = _assert_tool_command_result(
        result,
        tool_name="apply_interpretation",
        command_name=CommandName.APPLY_INTERPRETATION,
        ok=False,
        error_type="confirmation_required",
        raw_status="failed",
    )
    assert result.blocked_reason == "apply_interpretation requires confirmation."


def test_application_tool_command_routes_standard_preprocess(tmp_path):
    study = Study()
    info = mne.create_info(
        ch_names=["C3", "C4"],
        sfreq=128,
        ch_types="eeg",
    )
    data = np.random.default_rng(42).normal(size=(2, 128 * 20))
    source = tmp_path / "sample_raw.fif"
    mne.io.RawArray(data, info, verbose="ERROR").save(
        source,
        overwrite=True,
        verbose="ERROR",
    )
    load_result = get_application_service(study).execute(
        LoadDataCommand(paths=[str(source)]),
    )
    assert load_result.ok is True

    result = execute_application_tool_command(
        study,
        "apply_standard_preprocess",
        {
            "l_freq": 1,
            "h_freq": 30,
            "notch_freq": 0,
            "rereference": "average",
            "normalize_method": "z-score",
        },
    )

    result = _assert_tool_command_result(
        result,
        tool_name="apply_standard_preprocess",
        command_name=CommandName.PREPROCESS,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    operations = _state(result)["preprocessed"]["operations"]
    assert any("Re-reference (Average)" in item for item in operations)
    assert any(
        "z score normalization requested" in item
        and "deferred to per-epoch application" in item
        for item in operations
    )
    assert result.diagnostics["normalization_scope"] == "per_epoch_per_channel"
    assert result.diagnostics["raw_requests_deferred"] == 1
    assert result.diagnostics["epoched_items_normalized"] == 0
    assert result.diagnostics["recording_statistics_used"] is False
    assert result.changed_state["preprocessed_changed"] is True
    assert result.changed_state["epoch_changed"] is False
    assert _state(result)["epoch"]["exists"] is False


def test_application_surface_requires_real_study():
    with pytest.raises(CapabilityPolicyUnavailable):
        build_agent_tool_policy(object())


def test_explicit_tool_failure_becomes_failed_structured_result():
    result = normalize_tool_result(
        Study(),
        "start_training",
        ToolResult(
            False,
            "Generate datasets before training.",
            error_type="precondition",
        ),
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.command_name == CommandName.TRAIN.value
    assert result.error_type == "precondition"
    assert "Generate datasets" in result.message


def test_untyped_tool_text_fails_closed_as_invalid_contract():
    result = normalize_tool_result(Study(), "list_files", "Error-looking text")

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "contract"
    assert result.recoverable is False
    assert result.message == "The assistant tool returned an invalid result contract."
    assert result.raw_result is None
    assert result.diagnostics == {"returned_type": "str"}
    assert "Error-looking text" not in repr(result.to_payload())


def test_application_tool_command_returns_structured_result_for_model_config():
    study = Study()

    result = execute_application_tool_command(
        study,
        "set_model",
        {"model_name": "EEGNet"},
    )

    result = _assert_tool_command_result(
        result,
        tool_name="set_model",
        command_name=CommandName.CONFIGURE_TRAINING,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert _state(result)["training"]["model_name"] == "EEGNet"
    assert result.raw_result["changed_state"]["training_changed"] is True
    assert result.changed_state["training_changed"] is True


def test_application_tool_command_preserves_host_authorized_training_output_dir(
    tmp_path,
):
    output_dir = tmp_path / "chatpanel-training-output"

    result = execute_application_tool_command(
        Study(),
        "configure_training",
        {
            "model_name": "EEGNet",
            "epoch": 1,
            "batch_size": 2,
            "learning_rate": 0.001,
            "device": "cpu",
            "evaluation_option": "val_auc",
            "output_dir": UserProvidedTrainingOutputDir(str(output_dir)),
        },
    )

    result = _assert_tool_command_result(
        result,
        tool_name="configure_training",
        command_name=CommandName.CONFIGURE_TRAINING,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    training_state = result.raw_result["state"]["training"]["training_option"]
    assert result.raw_result["state"]["training"]["model_name"] == "EEGNet"
    assert str(output_dir) not in training_state["output_dir"]
    assert "[REDACTED_PATH]" in training_state["output_dir"]
    assert training_state["evaluation_option"] == "Best validation AUC"


def test_application_tool_command_accepts_backend_valid_learning_rate_one():
    result = execute_application_tool_command(
        Study(),
        "configure_training",
        {
            "model_name": "EEGNet",
            "epoch": 2,
            "batch_size": 4,
            "learning_rate": 1.0,
            "device": "cpu",
        },
    )

    result = _assert_tool_command_result(
        result,
        tool_name="configure_training",
        command_name=CommandName.CONFIGURE_TRAINING,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    training_state = _state(result)["training"]
    assert training_state["model_name"] == "EEGNet"
    assert training_state["training_option"]["epoch"] == 2
    assert training_state["training_option"]["batch_size"] == 4
    assert training_state["training_option"]["learning_rate"] == 1.0


def test_application_tool_command_rejects_partial_training_without_state_change():
    study = Study()
    service = get_application_service(study)
    before = service.get_state().training

    result = execute_application_tool_command(
        study,
        "configure_training",
        {"model_name": "EEGNet", "epoch": 10},
    )

    result = _assert_tool_command_result(
        result,
        tool_name="configure_training",
        command_name=CommandName.CONFIGURE_TRAINING,
        ok=False,
        error_type="input",
    )
    assert "batch_size" in result.message
    assert "learning_rate" in result.message
    assert service.get_state().training == before


@pytest.mark.parametrize(
    ("field", "value"),
    (("repeat", 1.75), ("save_checkpoints_every", 2.9)),
)
def test_application_tool_command_rejects_fractional_integer_options_without_state_change(
    field: str,
    value: float,
):
    study = Study()
    service = get_application_service(study)
    before = service.get_state().training
    params: dict[str, object] = {
        "model_name": "EEGNet",
        "epoch": 2,
        "batch_size": 4,
        "learning_rate": 0.001,
        "device": "cpu",
        field: value,
    }

    result = execute_application_tool_command(
        study,
        "configure_training",
        params,
    )

    result = _assert_tool_command_result(
        result,
        tool_name="configure_training",
        command_name=CommandName.CONFIGURE_TRAINING,
        ok=False,
        error_type="input",
    )
    assert field in result.message
    assert service.get_state().training == before


def test_application_tool_command_denies_legacy_direct_load(tmp_path):
    sample = tmp_path / "sample.unsupported"
    sample.write_text("not eeg", encoding="utf-8")

    result = execute_application_tool_command(
        Study(),
        "load_data",
        {"paths": [str(sample)]},
    )

    result = _assert_tool_command_result(
        result,
        tool_name="load_data",
        command_name=CommandName.LOAD_DATA,
        ok=False,
        error_type="precondition",
    )
    assert result.error_code == "assistant_direct_load_disabled"
    assert result.recoverable is False
    assert result.raw_result is None


def test_query_state_tool_uses_application_command_surface():
    study = Study()

    policy = build_agent_tool_policy(study)
    assert policy["query_state"].enabled is True
    assert policy["query_state"].command_name == CommandName.QUERY_STATE.value

    result = execute_application_tool_command(
        study,
        "query_state",
        {"query": "state"},
    )

    result = _assert_tool_command_result(
        result,
        tool_name="query_state",
        command_name=CommandName.QUERY_STATE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    diagnostics = result.raw_result["diagnostics"]
    assert diagnostics["state"]["pipeline_stage"] == "empty"
    assert diagnostics["capabilities"]["query_state"]["enabled"] is True


def test_query_state_tool_builds_only_detached_query_parameters() -> None:
    command = _command_for_tool(
        "query_state",
        {
            "query": "state",
            "params": {"detail": "summary"},
        },
    )

    assert isinstance(command, QueryStateCommand)
    assert vars(command) == {
        "query": "state",
        "params": {"detail": "summary"},
    }


def test_query_state_tool_surfaces_interpretation_review_truth(tmp_path):
    study = Study()
    service = get_application_service(study)
    source_dir = tmp_path / "agent_reviewed_source"
    source_dir.mkdir()
    eeg_path = source_dir / "sub-01_task-mi_raw.fif"
    events_path = source_dir / "events.tsv"
    eeg_path.write_bytes(b"placeholder")
    events_path.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    service.dataset.import_files = MagicMock(return_value=(1, []))

    execute_application_tool_command(
        study,
        "scan_source",
        {"source_path": str(source_dir)},
    )
    execute_application_tool_command(
        study,
        "preview_interpretation",
        {
            "choices": {
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": {
                            "left": {
                                "role": "stimulus",
                                "keep_event": True,
                                "use_as_class": True,
                                "class_name": "left hand",
                                "decision_source": "user_choice",
                                "provenance": "agent_tool",
                            },
                        },
                    },
                },
            },
        },
    )
    execute_application_tool_command(study, "validate_interpretation", {})
    execute_application_tool_command(study, "apply_interpretation", {"confirmed": True})
    result = execute_application_tool_command(study, "query_state", {"query": "state"})

    result = _assert_tool_command_result(
        result,
        tool_name="query_state",
        command_name=CommandName.QUERY_STATE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    interpretation = result.raw_result["diagnostics"]["state"]["interpretation"]
    public_path = interpretation["label_carrier_plan"][0]["path"]
    assert str(events_path) not in public_path
    assert public_path.startswith("events.tsv [REDACTED_PATH]")
    assert interpretation["label_carrier_plan"][0]["selected_label_field"] == (
        "trial_type"
    )
    capabilities = {
        item["name"]: item for item in interpretation["format_capabilities"]
    }
    assert capabilities["events.tsv"]["format"] == "BIDS events"
    assert interpretation["class_map"] == {"left": "left hand"}
    value_decision = interpretation["label_carrier_plan"][0]["value_decisions"]["left"]
    assert value_decision["role"] == "stimulus"
    assert value_decision["use_as_class"] is True
    assert value_decision["class_name"] == "left hand"


def test_analysis_tools_are_application_service_backed():
    study = Study()

    policy = build_agent_tool_policy(study)
    assert policy["evaluate"].command_name == CommandName.EVALUATE.value
    assert policy["evaluate"].stop_after_success is True
    assert policy["visualize"].command_name == CommandName.VISUALIZE.value
    assert policy["saliency"].command_name == CommandName.SALIENCY.value

    evaluate = execute_application_tool_command(study, "evaluate", {})
    visualize = execute_application_tool_command(
        study, "visualize", {"view": "summary"}
    )
    saliency = execute_application_tool_command(
        study,
        "saliency",
        {"method": "Gradient", "params": {"absolute": True}},
    )

    evaluate = _assert_tool_command_result(
        evaluate,
        tool_name="evaluate",
        command_name=CommandName.EVALUATE,
        ok=False,
        error_type="precondition",
        raw_status="failed",
    )
    assert (
        evaluate.blocked_reason == "Create a training plan before evaluating results."
    )

    visualize = _assert_tool_command_result(
        visualize,
        tool_name="visualize",
        command_name=CommandName.VISUALIZE,
        ok=False,
        error_type="precondition",
        raw_status="failed",
    )
    assert visualize.blocked_reason == (
        "Create EEG epochs, complete training, or configure saliency before opening "
        "visualization views."
    )

    saliency = _assert_tool_command_result(
        saliency,
        tool_name="saliency",
        command_name=CommandName.SALIENCY,
        ok=False,
        error_type="precondition",
        raw_status="failed",
    )
    assert saliency.blocked_reason == (
        "Create EEG epochs, build the training dataset, or select a model and training settings "
        "before querying saliency readiness."
    )


def test_application_tool_command_leaves_ui_request_tools_on_explicit_adapter_path():
    assert (
        execute_application_tool_command(
            Study(),
            "set_montage",
            {"montage_name": "standard_1020"},
        )
        is None
    )
