"""Lifecycle tests for one verified assistant tool execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application import (
    ChangedState,
    Command,
    CommandResult,
    QueryStateCommand,
    build_capability_policy,
    get_application_service,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.tool_execution_coordinator import ToolExecutionCoordinator
from XBrainLab.llm.tools.application_surface import (
    APPLICATION_COMMAND_TOOLS,
    TOOL_TO_COMMAND,
    ToolAvailability,
    ToolAvailabilityContext,
    ToolCommandResult,
    get_application_context,
)
from XBrainLab.llm.tools.real.dataset_real import RealGetDatasetInfoTool
from XBrainLab.llm.tools.result_contract import (
    SAFE_UNEXPECTED_FAILURE_CODE,
    SAFE_UNEXPECTED_FAILURE_MESSAGE,
    ToolResult,
)


class _Registry:
    def __init__(self, execute: MagicMock) -> None:
        self.execute = execute

    def get_tool(self, command_name: str) -> object:
        return SimpleNamespace(name=command_name, execute=self.execute)


class _Host:
    def __init__(self, study: object | None = None) -> None:
        self.study = study if study is not None else object()
        self.legacy_execute = MagicMock(
            return_value=ToolResult(True, "Compatibility tool completed."),
        )
        self.registry: Any = _Registry(self.legacy_execute)
        self.metrics = SimpleNamespace(current_turn=None)
        self.status_update = MagicMock()
        self.application_command_started = MagicMock()
        self.application_command_completed = MagicMock()


class _BlockPolicy:
    def blocked_result(self, command_name, context):
        raise AssertionError("enabled tool must not use blocked-result path")


def _fake_study_context() -> object:
    return MagicMock(spec=Study)


class _StudyProxy:
    def __init__(self) -> None:
        self.study = Study()


class _HeadlessContext:
    def __init__(self) -> None:
        self.application_service = get_application_service(Study())


class _HeadlessRuntime:
    def __init__(self) -> None:
        self.service = get_application_service(Study())
        self.commands: list[Command] = []

    def get_view_publication(self) -> ApplicationViewPublication:
        return self.service.get_view_publication()

    def execute(self, command: Command) -> CommandResult:
        self.commands.append(command)
        return self.service.execute(command)


class _DatasetInfoRuntime:
    def __init__(self) -> None:
        publication = get_application_service(Study()).get_view_publication()
        state = replace(
            publication.state,
            raw=replace(
                publication.state.raw,
                loaded=True,
                count=1,
                files=["runtime-only.edf"],
                event_total=12,
                unique_events=["left", "right"],
            ),
            active_dataset=replace(
                publication.state.active_dataset,
                has_raw_data=True,
            ),
        )
        self.publication = ApplicationViewPublication(
            generation=41,
            state=state,
            capabilities=build_capability_policy(state),
        )
        self.commands: list[Command] = []

    def get_view_publication(self) -> ApplicationViewPublication:
        return self.publication

    def execute(self, command: Command) -> CommandResult:
        self.commands.append(command)
        return CommandResult.success_result(
            command_name="query_state",
            message="Dataset summary ready.",
            state=self.publication.state,
            changed_state=ChangedState(),
            diagnostics={
                "count": 1,
                "files": ["runtime-only.edf"],
                "total": 12,
                "unique_count": 2,
            },
        )


def _enabled_context(tool_name: str) -> ToolAvailabilityContext:
    return ToolAvailabilityContext(
        availability=ToolAvailability(
            tool_name=tool_name,
            enabled=True,
            command_name=(
                TOOL_TO_COMMAND[tool_name].value
                if tool_name in TOOL_TO_COMMAND
                else None
            ),
            read_only=tool_name not in TOOL_TO_COMMAND,
        ),
        state={"pipeline_stage": "empty"},
        generation=7,
    )


def test_unknown_tool_name_is_redacted_from_status_metrics_and_payload() -> None:
    private_tool_name = "/srv/private/patient-Jane/session.edf"
    host = _Host()
    host.registry.get_tool = MagicMock(return_value=None)
    current_turn = SimpleNamespace(record_tool=MagicMock())
    host.metrics.current_turn = current_turn
    coordinator = ToolExecutionCoordinator(host, block_policy=_BlockPolicy())

    outcome = coordinator.execute(
        private_tool_name,
        {},
        context=_enabled_context("list_files"),
    )

    assert outcome.success is False
    assert isinstance(outcome.result, ToolCommandResult)
    status = host.status_update.emit.call_args.args[0]
    payload = repr(outcome.result.to_payload())
    metrics = repr(current_turn.record_tool.call_args)
    for public_output in (status, payload, metrics):
        assert private_tool_name not in public_output
        assert "patient-Jane" not in public_output
    assert "[REDACTED_PATH]" in status
    assert "[REDACTED_PATH]" in payload


def test_normalization_failure_still_completes_application_command(
    monkeypatch,
) -> None:
    runtime = _HeadlessRuntime()
    context = get_application_context(
        object(),
        "set_model",
        runtime=runtime,
    )
    assert context is not None
    pre_execution_state = context.state
    host = _Host()
    current_turn = SimpleNamespace(record_tool=MagicMock())
    host.metrics.current_turn = current_turn
    coordinator = ToolExecutionCoordinator(
        host,
        block_policy=_BlockPolicy(),
        application_runtime=runtime,
    )

    def fail_normalization(*_args, **_kwargs):
        raise RuntimeError(
            "/home/alice/private/subject-17/events.tsv "
            "alice@example.test token=hf_super_secret"
        )

    monkeypatch.setattr(
        "XBrainLab.llm.agent.tool_execution_coordinator.normalize_tool_result",
        fail_normalization,
    )

    outcome = coordinator.execute(
        "set_model",
        {"model_name": "EEGNet"},
        context=context,
    )

    assert outcome.success is False
    assert isinstance(outcome.result, ToolCommandResult)
    assert outcome.result.ok is False
    assert outcome.result.command_name == "configure_training"
    assert outcome.result.message == SAFE_UNEXPECTED_FAILURE_MESSAGE
    assert outcome.result.error_code == SAFE_UNEXPECTED_FAILURE_CODE
    assert outcome.result.recovery_action == "refresh_application_state"
    assert outcome.result.raw_result is None
    assert outcome.result.state is not pre_execution_state
    assert outcome.result.state is not None
    assert outcome.result.state["training"]["model_name"] == "EEGNet (XBrainLab)"
    assert outcome.result.diagnostics["state_source"] == ("authoritative_publication")
    assert outcome.result.diagnostics["incident_id"]
    assert len(runtime.commands) == 1
    recorded_error = current_turn.record_tool.call_args.args[3]
    assert recorded_error == SAFE_UNEXPECTED_FAILURE_CODE
    status_message = host.status_update.emit.call_args.args[0]
    assert status_message == SAFE_UNEXPECTED_FAILURE_MESSAGE
    serialized_feedback = repr(outcome.result.to_payload())
    for private_value in (
        "/home/alice/private/subject-17/events.tsv",
        "alice@example.test",
        "hf_super_secret",
    ):
        assert private_value not in serialized_feedback
        assert private_value not in recorded_error
        assert private_value not in status_message
    host.application_command_started.emit.assert_called_once_with()
    host.application_command_completed.emit.assert_called_once_with(outcome.result)


@pytest.mark.parametrize(
    "study_factory",
    [_fake_study_context, _StudyProxy, _HeadlessContext],
    ids=["fake", "proxy", "headless"],
)
def test_all_mapped_product_names_fail_closed_without_runtime(
    study_factory: Callable[[], object],
) -> None:
    for tool_name in APPLICATION_COMMAND_TOOLS:
        command_name = TOOL_TO_COMMAND[tool_name]
        host = _Host(study_factory())
        coordinator = ToolExecutionCoordinator(host, block_policy=_BlockPolicy())

        outcome = coordinator.execute(
            tool_name,
            {},
            context=_enabled_context(tool_name),
        )

        assert outcome.success is False, tool_name
        assert isinstance(outcome.result, ToolCommandResult), tool_name
        assert outcome.result.ok is False, tool_name
        assert outcome.result.command_name == command_name.value, tool_name
        assert outcome.result.error_type == "contract", tool_name
        assert outcome.result.recoverable is False, tool_name
        assert outcome.result.error_code == "application_tool_runtime_required", (
            tool_name
        )
        assert outcome.result.recovery_action == ("provide_application_tool_runtime"), (
            tool_name
        )
        host.legacy_execute.assert_not_called()


def test_missing_runtime_failure_preserves_application_completion_semantics() -> None:
    host = _Host(_StudyProxy())
    coordinator = ToolExecutionCoordinator(host, block_policy=_BlockPolicy())

    outcome = coordinator.execute(
        "query_state",
        {},
        context=_enabled_context("query_state"),
    )

    assert isinstance(outcome.result, ToolCommandResult)
    host.application_command_started.emit.assert_called_once_with()
    host.application_command_completed.emit.assert_called_once_with(outcome.result)
    host.legacy_execute.assert_not_called()


def test_mapped_none_result_never_substitutes_legacy_execution(monkeypatch) -> None:
    host = _Host(Study())
    coordinator = ToolExecutionCoordinator(host, block_policy=_BlockPolicy())
    monkeypatch.setattr(
        "XBrainLab.llm.agent.tool_execution_coordinator."
        "execute_application_tool_command",
        lambda *_args, **_kwargs: None,
    )

    outcome = coordinator.execute(
        "query_state",
        {},
        context=_enabled_context("query_state"),
    )

    assert outcome.success is False
    assert isinstance(outcome.result, ToolCommandResult)
    assert outcome.result.message == SAFE_UNEXPECTED_FAILURE_MESSAGE
    assert outcome.result.error_code == SAFE_UNEXPECTED_FAILURE_CODE
    assert outcome.result.raw_result is None
    host.legacy_execute.assert_not_called()
    host.application_command_completed.emit.assert_called_once_with(outcome.result)


def test_genuine_study_runtime_keeps_application_command_path() -> None:
    host = _Host(Study())
    coordinator = ToolExecutionCoordinator(host, block_policy=_BlockPolicy())

    outcome = coordinator.execute(
        "query_state",
        {"query": "state"},
        context=_enabled_context("query_state"),
    )

    assert outcome.success is True
    assert isinstance(outcome.result, ToolCommandResult)
    assert outcome.result.command_name == "query_state"
    host.legacy_execute.assert_not_called()
    host.application_command_completed.emit.assert_called_once_with(outcome.result)


def test_explicit_runtime_keeps_headless_application_command_path() -> None:
    runtime = _HeadlessRuntime()
    context = get_application_context(
        object(),
        "query_state",
        runtime=runtime,
    )
    assert context is not None
    host = _Host()
    coordinator = ToolExecutionCoordinator(
        host,
        block_policy=_BlockPolicy(),
        application_runtime=runtime,
    )

    outcome = coordinator.execute("query_state", {}, context=context)

    assert outcome.success is True
    assert isinstance(outcome.result, ToolCommandResult)
    assert len(runtime.commands) == 1
    host.legacy_execute.assert_not_called()


def test_read_only_backend_adapter_uses_injected_runtime_on_non_study_host() -> None:
    runtime = _DatasetInfoRuntime()
    host = _Host(object())
    tool = RealGetDatasetInfoTool()
    host.registry = SimpleNamespace(get_tool=lambda _name: tool)
    coordinator = ToolExecutionCoordinator(
        host,
        block_policy=_BlockPolicy(),
        application_runtime=runtime,
    )
    context = get_application_context(
        host.study,
        "get_dataset_info",
        runtime=runtime,
    )
    assert context is not None

    outcome = coordinator.execute("get_dataset_info", {}, context=context)

    assert outcome.success is True
    assert isinstance(outcome.result, ToolCommandResult)
    assert outcome.result.message == (
        "Loaded 1 files:\nruntime-only.edf\nEvents: 12 (Unique: 2)"
    )
    assert outcome.result.raw_result["status"] == "ok"
    assert outcome.result.raw_result["command_name"] == "query_state"
    assert outcome.result.raw_result["changed_state"]["state_unknown"] is False
    diagnostics = outcome.result.raw_result["diagnostics"]
    assert diagnostics["count"] == 1
    assert diagnostics["total"] == 12
    assert diagnostics["unique_count"] == 2
    assert diagnostics["files"][0].startswith("file (.edf) [REDACTED_PATH]")
    assert "runtime-only.edf" not in diagnostics["files"][0]
    assert outcome.result.state == context.state
    assert len(runtime.commands) == 1
    assert isinstance(runtime.commands[0], QueryStateCommand)
    host.legacy_execute.assert_not_called()


def test_per_execution_runtime_override_does_not_replace_coordinator_default() -> None:
    default_runtime = _HeadlessRuntime()
    override_runtime = _HeadlessRuntime()
    host = _Host()
    coordinator = ToolExecutionCoordinator(
        host,
        block_policy=_BlockPolicy(),
        application_runtime=default_runtime,
    )
    override_context = get_application_context(
        object(),
        "query_state",
        runtime=override_runtime,
    )
    default_context = get_application_context(
        object(),
        "query_state",
        runtime=default_runtime,
    )
    assert override_context is not None
    assert default_context is not None

    overridden = coordinator.execute(
        "query_state",
        {},
        context=override_context,
        application_runtime=override_runtime,
    )
    defaulted = coordinator.execute("query_state", {}, context=default_context)

    assert overridden.success is True
    assert defaulted.success is True
    assert len(override_runtime.commands) == 1
    assert len(default_runtime.commands) == 1


def test_namespaced_unmapped_compatibility_tool_cannot_bypass_contract() -> None:
    tool_name = "compatibility__state_probe"
    assert tool_name not in TOOL_TO_COMMAND
    host = _Host()
    coordinator = ToolExecutionCoordinator(host, block_policy=_BlockPolicy())

    outcome = coordinator.execute(
        tool_name,
        {},
        context=_enabled_context(tool_name),
    )

    assert outcome.success is False
    assert isinstance(outcome.result, ToolCommandResult)
    assert outcome.result.error_type == "contract"
    assert outcome.result.recoverable is False
    assert "not classified" in outcome.result.message
    host.legacy_execute.assert_not_called()


def test_post_execution_failure_without_publication_marks_state_unknown_once(
    monkeypatch,
) -> None:
    class _Runtime:
        def __init__(self) -> None:
            self.service = get_application_service(Study())
            self.publication_reads = 0
            self.executed_commands: list[Command] = []

        def get_view_publication(self) -> ApplicationViewPublication:
            self.publication_reads += 1
            if self.publication_reads > 1:
                raise RuntimeError(
                    "/home/alice/private/subject-17/events.tsv token=hf_super_secret"
                )
            return self.service.get_view_publication()

        def execute(self, command: Command) -> CommandResult:
            self.executed_commands.append(command)
            return self.service.execute(command)

    runtime = _Runtime()
    context = get_application_context(
        object(),
        "set_model",
        runtime=runtime,
    )
    assert context is not None
    host = _Host()
    coordinator = ToolExecutionCoordinator(
        host,
        block_policy=_BlockPolicy(),
        application_runtime=runtime,
    )

    def fail_normalization(*_args, **_kwargs):
        raise RuntimeError("post-execution normalization failed")

    monkeypatch.setattr(
        "XBrainLab.llm.agent.tool_execution_coordinator.normalize_tool_result",
        fail_normalization,
    )

    outcome = coordinator.execute(
        "set_model",
        {"model_name": "EEGNet"},
        context=context,
    )

    assert outcome.success is False
    assert isinstance(outcome.result, ToolCommandResult)
    assert outcome.result.state is None
    assert outcome.result.changed_state["state_unknown"] is True
    assert outcome.result.diagnostics["state_source"] == "unavailable"
    assert outcome.result.diagnostics["refresh_required"] is True
    assert len(runtime.executed_commands) == 1
    host.application_command_completed.emit.assert_called_once_with(outcome.result)


def test_unclassified_tool_cannot_fall_through_to_direct_execution() -> None:
    host = _Host()
    coordinator = ToolExecutionCoordinator(host, block_policy=_BlockPolicy())

    outcome = coordinator.execute(
        "unclassified_mutation",
        {},
        context=_enabled_context("unclassified_mutation"),
    )

    assert outcome.success is False
    assert isinstance(outcome.result, ToolCommandResult)
    assert outcome.result.error_type == "contract"
    assert outcome.result.recoverable is False
    assert "not classified" in outcome.result.message
    host.legacy_execute.assert_not_called()
