"""Lifecycle tests for one verified target assistant tool execution."""

from collections.abc import Callable
from dataclasses import replace
from threading import Event
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application import StopTrainingCommand, get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import Trainer
from XBrainLab.backend.training_state_contract import TrainingOutcomeState
from XBrainLab.llm.agent.metrics import AgentMetricsTracker
from XBrainLab.llm.agent.tool_execution_coordinator import ToolExecutionCoordinator
from XBrainLab.llm.agent.tool_feedback import format_tool_output
from XBrainLab.llm.tools.application_surface import (
    APPLICATION_COMMAND_TOOLS,
    TOOL_TO_COMMAND,
    ToolAvailability,
    ToolAvailabilityContext,
)
from XBrainLab.llm.tools.result_contract import ToolCommandResult


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
        format_tool_output(outcome.result.tool_name, outcome.success, outcome.result),
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
            return_value=ToolCommandResult(True, tool_name, "Unexpected execution")
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
    direct_execute = MagicMock(
        return_value=ToolCommandResult(True, tool_name, "Unexpected execution")
    )
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


def test_stop_execution_carries_reviewed_run_and_rejects_replacement(monkeypatch):
    study = Study()
    service = get_application_service(study)
    old = Trainer([])
    old.run(interact=False)
    reviewed = old.get_terminal_outcome().run
    current = Trainer([])
    study.training_manager.trainer = current
    started = Event()
    finish = Event()

    def job():
        started.set()
        assert finish.wait(timeout=5)

    monkeypatch.setattr(current, "job", job)
    current.run(interact=True)
    assert started.wait(timeout=2)
    context = replace(
        _enabled_context("stop_training"),
        state={
            "state_reliable": True,
            "training_liveness_reliable": True,
            "training": {
                "is_running": True,
                "terminal_outcome": {"state": "running", "run": reviewed.to_dict()},
            },
        },
    )
    completed = []
    coordinator = ToolExecutionCoordinator(
        study,
        _Registry(MagicMock()),
        AgentMetricsTracker(),
        block_policy=_BlockPolicy(),
        emit_status=lambda _message: None,
        emit_application_command_started=lambda: None,
        emit_application_command_completed=completed.append,
    )
    try:
        outcome = coordinator.execute(
            "stop_training",
            {},
            context=context,
            expected_publication_generation=context.generation,
        )
        assert not outcome.success
        assert outcome.result.error_type == "precondition"
        assert outcome.result.diagnostics["stale_confirmation"] is True
        assert outcome.result.diagnostics["expected_training_run"] == reviewed.to_dict()
        assert completed == [outcome.result]
        assert current.get_terminal_outcome().state is TrainingOutcomeState.RUNNING
        assert not current.interrupt
    finally:
        current.stop()
        finish.set()
        assert current.wait_for_completion(timeout=3)
        service.close()


def test_bound_stop_result_never_attributes_replacement_outcome_to_reviewed_run(
    monkeypatch,
):
    study = Study()
    service = get_application_service(study)
    old = Trainer([])
    replacement = Trainer([])
    release_old = Event()
    release_new = Event()
    monkeypatch.setattr(old, "job", lambda: release_old.wait(timeout=5))
    monkeypatch.setattr(replacement, "job", lambda: release_new.wait(timeout=5))
    study.training_manager.trainer = old
    old.run(interact=True)
    reviewed = old.get_terminal_outcome().run
    read_outcome = service.training_runtime.terminal_outcome

    def replace_before_result_observation():
        assert old.interrupt
        release_old.set()
        assert old.wait_for_completion(timeout=2)
        with study.training_manager._training_pipeline_lock:
            study.training_manager.trainer = replacement
            replacement.run(interact=True)
        return read_outcome()

    monkeypatch.setattr(
        service.training_runtime, "terminal_outcome", replace_before_result_observation
    )
    try:
        result = service.execute(StopTrainingCommand(expected_run=reviewed))
        assert result.ok
        assert result.diagnostics["training_run"] == reviewed.to_dict()
        assert result.diagnostics["terminal_outcome"] == "unknown"
        assert replacement.get_terminal_outcome().state is TrainingOutcomeState.RUNNING
        assert not replacement.interrupt
    finally:
        monkeypatch.setattr(service.training_runtime, "terminal_outcome", read_outcome)
        old.stop()
        replacement.stop()
        release_old.set()
        release_new.set()
        assert old.wait_for_completion(timeout=3)
        assert replacement.wait_for_completion(timeout=3)
        service.close()
