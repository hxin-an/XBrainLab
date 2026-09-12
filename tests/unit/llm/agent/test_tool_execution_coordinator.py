"""Lifecycle tests for one verified target assistant tool execution."""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application import get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.metrics import AgentMetricsTracker
from XBrainLab.llm.agent.tool_execution_coordinator import ToolExecutionCoordinator
from XBrainLab.llm.tools.application_surface import (
    APPLICATION_COMMAND_TOOLS,
    TOOL_TO_COMMAND,
    ToolAvailability,
    ToolAvailabilityContext,
    ToolCommandResult,
)
from XBrainLab.llm.tools.result_contract import ToolResult


class _Registry:
    def __init__(self, execute: MagicMock) -> None:
        self.execute = execute

    def get_tool(self, command_name: str) -> object:
        return SimpleNamespace(name=command_name, execute=self.execute)


class _BlockPolicy:
    def blocked_result(self, command_name, context):
        raise AssertionError("enabled tool must not use blocked-result path")


class _StudyProxy:
    def __init__(self) -> None:
        self.study = Study()


class _HeadlessContext:
    def __init__(self) -> None:
        self.application_service = object()


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
        ),
        state={"pipeline_stage": "empty"},
        generation=7,
    )


def test_unknown_tool_name_is_redacted_from_status_metrics_and_payload() -> None:
    private_tool_name = "/srv/private/patient-Jane/session.edf"
    registry = MagicMock(get_tool=MagicMock(return_value=None))
    metrics = AgentMetricsTracker()
    current_turn = metrics.start_turn()
    statuses: list[str] = []
    coordinator = ToolExecutionCoordinator(
        object(),
        registry,
        metrics,
        block_policy=_BlockPolicy(),
        emit_status=statuses.append,
        emit_application_command_started=lambda: None,
        emit_application_command_completed=lambda _result: None,
    )

    outcome = coordinator.execute(
        private_tool_name,
        {},
        context=_enabled_context("switch_panel"),
    )

    assert outcome.success is False
    assert isinstance(outcome.result, ToolCommandResult)
    public_outputs = (
        statuses[0],
        repr(outcome.result.to_payload()),
        repr(current_turn),
    )
    for public_output in public_outputs:
        assert private_tool_name not in public_output
        assert "patient-Jane" not in public_output
    assert "[REDACTED_PATH]" in public_outputs[0]


@pytest.mark.parametrize(
    "study_factory",
    [lambda: MagicMock(spec=Study), _StudyProxy, _HeadlessContext],
    ids=["fake", "proxy", "headless"],
)
def test_all_mapped_target_names_fail_closed_without_runtime(
    study_factory: Callable[[], object],
) -> None:
    for tool_name in APPLICATION_COMMAND_TOOLS:
        command_name = TOOL_TO_COMMAND[tool_name]
        direct_execute = MagicMock(
            return_value=ToolResult(True, "Unexpected execution")
        )
        registry: Any = _Registry(direct_execute)
        starts: list[bool] = []
        completions: list[ToolCommandResult] = []
        coordinator = ToolExecutionCoordinator(
            study_factory(),
            registry,
            AgentMetricsTracker(),
            block_policy=_BlockPolicy(),
            emit_status=lambda _message: None,
            emit_application_command_started=lambda starts=starts: starts.append(True),
            emit_application_command_completed=completions.append,
        )

        outcome = coordinator.execute(
            tool_name,
            {},
            context=_enabled_context(tool_name),
        )

        assert outcome.success is False, tool_name
        assert isinstance(outcome.result, ToolCommandResult), tool_name
        assert outcome.result.command_name == command_name.value, tool_name
        assert outcome.result.error_code == "application_tool_runtime_required", (
            tool_name
        )
        direct_execute.assert_not_called()
        assert starts == [True]
        assert completions == [outcome.result]


@pytest.mark.parametrize(
    "tool_name",
    ("compatibility__state_probe", "unclassified_mutation"),
)
def test_unclassified_tool_cannot_fall_through_to_direct_execution(
    tool_name: str,
) -> None:
    assert tool_name not in TOOL_TO_COMMAND
    direct_execute = MagicMock(return_value=ToolResult(True, "Unexpected execution"))
    registry: Any = _Registry(direct_execute)
    starts: list[bool] = []
    completions: list[ToolCommandResult] = []
    coordinator = ToolExecutionCoordinator(
        object(),
        registry,
        AgentMetricsTracker(),
        block_policy=_BlockPolicy(),
        emit_status=lambda _message: None,
        emit_application_command_started=lambda: starts.append(True),
        emit_application_command_completed=completions.append,
    )

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
    direct_execute.assert_not_called()
    assert starts == []
    assert completions == []


def test_execution_exception_completes_one_command_and_recovers_current_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = Study()
    service = get_application_service(study)
    publication = service.get_view_publication()
    direct_execute = MagicMock()
    registry: Any = _Registry(direct_execute)
    events: list[object] = []
    metrics = AgentMetricsTracker()
    turn = metrics.start_turn()
    coordinator = ToolExecutionCoordinator(
        study,
        registry,
        metrics,
        block_policy=_BlockPolicy(),
        emit_status=lambda _message: None,
        emit_application_command_started=lambda: events.append("started"),
        emit_application_command_completed=events.append,
    )

    def fail_execution(*_args, **_kwargs):
        raise RuntimeError("Injected command transport failure")

    monkeypatch.setattr(
        "XBrainLab.llm.agent.tool_execution_coordinator."
        "execute_application_tool_command",
        fail_execution,
    )
    outcome = coordinator.execute(
        "reset_preprocessing",
        {"confirmed": True},
        context=_enabled_context("reset_preprocessing"),
        expected_publication_generation=publication.generation,
    )

    assert not outcome.success
    assert isinstance(outcome.result, ToolCommandResult)
    assert events == ["started", outcome.result]
    assert outcome.result.state == publication.state.to_dict()
    assert outcome.result.diagnostics["refresh_required"] is False
    assert turn.tool_count == 1
    assert turn.tool_success_count == 0
    direct_execute.assert_not_called()
