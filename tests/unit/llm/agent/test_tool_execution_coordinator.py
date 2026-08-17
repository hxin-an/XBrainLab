"""Lifecycle tests for one verified target assistant tool execution."""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.study import Study
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
    host = _Host()
    host.registry.get_tool = MagicMock(return_value=None)
    current_turn = SimpleNamespace(record_tool=MagicMock())
    host.metrics.current_turn = current_turn
    coordinator = ToolExecutionCoordinator(host, block_policy=_BlockPolicy())

    outcome = coordinator.execute(
        private_tool_name,
        {},
        context=_enabled_context("switch_panel"),
    )

    assert outcome.success is False
    assert isinstance(outcome.result, ToolCommandResult)
    public_outputs = (
        host.status_update.emit.call_args.args[0],
        repr(outcome.result.to_payload()),
        repr(current_turn.record_tool.call_args),
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
        host = _Host(study_factory())
        coordinator = ToolExecutionCoordinator(host, block_policy=_BlockPolicy())

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
        host.legacy_execute.assert_not_called()


@pytest.mark.parametrize(
    "tool_name",
    ("compatibility__state_probe", "unclassified_mutation"),
)
def test_unclassified_tool_cannot_fall_through_to_direct_execution(
    tool_name: str,
) -> None:
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
