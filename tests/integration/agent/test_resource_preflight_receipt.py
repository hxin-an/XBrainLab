"""Training resource receipts stay bound across the Stable v2 tool boundary."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.integration.agent.deferred_split_support import (
    build_saved_split_runtime,
    install_materialized_candidate,
)
from XBrainLab.backend.application import ConfigureTrainingCommand
from XBrainLab.backend.application import training_service as training_service_module
from XBrainLab.backend.application.resource_guard import ResourcePreflightResult
from XBrainLab.backend.application.resource_preflight import (
    RESOURCE_PREFLIGHT_SCHEMA_VERSION,
    ResourcePreflightView,
)
from XBrainLab.backend.application.training_runtime import (
    TrainingCommandRuntimePort,
    TrainingRuntimeContext,
)
from XBrainLab.backend.application.training_service import TrainingCommandService
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingTerminalOutcome,
)
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ApplicationToolContextSource,
    ResourcePreflightReceipt,
    ToolAttemptAction,
    ToolAttemptCoordinator,
    ToolAttemptDecision,
)
from XBrainLab.llm.tools.application_surface import (
    ToolCommandResult,
    execute_application_tool_command,
)


def _required_receipt(
    pending: ToolAttemptDecision,
) -> ResourcePreflightReceipt:
    receipt = pending.resource_preflight_receipt
    assert receipt is not None
    return receipt


class _TrainingProbe:
    trainer_identity = "agent-receipt-training-probe"

    def __init__(self, resource_runtime: TrainingCommandRuntimePort) -> None:
        self._resource_runtime = resource_runtime
        self.preflight_revision = 1
        self.start_count = 0
        self._terminal_outcome = TrainingTerminalOutcome(
            state=TrainingOutcomeState.NOT_STARTED,
        )

    def start_training(
        self,
        *,
        append: bool = True,
        interactive: bool = True,
    ) -> int:
        del append, interactive
        self.start_count += 1
        self._terminal_outcome = TrainingTerminalOutcome(
            state=TrainingOutcomeState.RUNNING,
            run=TrainingRunIdentity(
                trainer_id=self.trainer_identity,
                run_id=self.start_count,
            ),
        )
        return self.start_count

    def resource_context(self) -> TrainingRuntimeContext:
        return self._resource_runtime.resource_context()

    def stop_training(self, *, wait_timeout: float | None = None) -> bool:
        del wait_timeout
        run = self._terminal_outcome.run
        if run is None:
            return False
        self._terminal_outcome = TrainingTerminalOutcome(
            state=TrainingOutcomeState.CANCELLED,
            run=run,
        )
        return True

    def wait_for_training_completion(
        self,
        *,
        expected_trainer_identity: str | None = None,
        timeout: float | None = None,
    ) -> bool:
        del timeout
        run = self._terminal_outcome.run
        return bool(
            self._terminal_outcome.is_terminal
            and run is not None
            and (
                expected_trainer_identity is None
                or run.trainer_id == expected_trainer_identity
            )
        )

    def terminal_outcome(self) -> TrainingTerminalOutcome:
        return self._terminal_outcome


def _training_receipt_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    Study,
    ToolAttemptCoordinator,
    ToolAttemptDecision,
    _TrainingProbe,
]:
    study = Study()
    service, epoch = build_saved_split_runtime(study)
    install_materialized_candidate(study, epoch)
    configured = service.execute(
        ConfigureTrainingCommand(
            model_name="EEGNet",
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            device="cpu",
        )
    )
    assert configured.ok is True
    probe = _TrainingProbe(service.training_runtime)
    service.training_commands._service_instance = TrainingCommandService(
        training=probe,
        training_runtime=probe,
        get_state=service.get_state,
    )

    def warning_preflight(
        _datasets: Any,
        _training_option: Any,
        _model_holder: Any,
    ) -> ResourcePreflightResult:
        return ResourcePreflightResult(
            issues=(),
            warnings=("Training may use most available memory.",),
            diagnostics={
                "preflight_revision": probe.preflight_revision,
                "estimated_gpu_batch_working_set_bytes": 4_096,
                "available_vram_bytes": 8_192,
            },
        )

    monkeypatch.setattr(
        training_service_module,
        "check_training_resource_preflight",
        warning_preflight,
    )
    context_source = ApplicationToolContextSource(study)
    context = context_source.get_context("start_training")
    assert context is not None
    assert context.availability.enabled
    first = execute_application_tool_command(
        study,
        "start_training",
        {"confirmed": True},
        availability=context.availability,
        state=context.state,
    )
    assert isinstance(first, ToolCommandResult)
    assert first.error_type == "confirmation_required", first
    state_after_preflight = service.get_state()
    assert state_after_preflight.dataset.split_spec_saved is True
    assert state_after_preflight.dataset.split_materialized is False
    assert study.datasets == []
    preflight = ResourcePreflightView.from_diagnostics(first.diagnostics)
    assert preflight is not None
    assert preflight.schema_version == RESOURCE_PREFLIGHT_SCHEMA_VERSION
    assert preflight.challenge is not None
    assert preflight.challenge.command_name == "start_training"
    assert preflight.challenge.candidate_id is None
    assert preflight.challenge.configuration_fingerprint
    assert preflight.challenge.preflight_fingerprint
    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name="start_training",
        params={},
        context=context,
    )
    pending = ToolAttemptCoordinator.resource_confirmation(initial, first)
    assert pending is not None
    assert pending.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    coordinator = ToolAttemptCoordinator(
        registry=MagicMock(),
        verifier=MagicMock(),
        context_source=context_source,
    )
    return study, coordinator, pending, probe


def _execute_training_replay(
    study: Study,
    coordinator: ToolAttemptCoordinator,
    pending: ToolAttemptDecision,
) -> ToolCommandResult:
    context = pending.context
    assert context is not None
    params = coordinator.approved_params(pending)
    result = execute_application_tool_command(
        study,
        "start_training",
        params,
        availability=context.availability,
        state=context.state,
    )
    assert isinstance(result, ToolCommandResult)
    return result


def test_agent_start_training_replays_matching_preflight_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study, coordinator, pending, probe = _training_receipt_runtime(monkeypatch)

    result = _execute_training_replay(study, coordinator, pending)

    assert result.ok
    assert (
        result.diagnostics["resource_preflight"]["confirmation_receipt_reused"] is True
    )
    assert result.diagnostics["training_trainer_identity"] == probe.trainer_identity
    assert probe.start_count == 1

    replayed = _execute_training_replay(study, coordinator, pending)

    assert replayed.error_type == "confirmation_required"
    assert probe.start_count == 1


@pytest.mark.parametrize("change", ["configuration", "preflight"])
def test_agent_start_training_rejects_stale_receipt_before_execution(
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    study, coordinator, pending, probe = _training_receipt_runtime(monkeypatch)
    old_receipt = _required_receipt(pending)
    if change == "configuration":
        option = study.training_option
        assert option is not None
        option.epoch = 20
        study.set_training_option(option)
    else:
        probe.preflight_revision += 1

    result = _execute_training_replay(study, coordinator, pending)

    assert result.error_type == "confirmation_required"
    assert probe.start_count == 0
    refreshed = ToolAttemptCoordinator.resource_confirmation(pending, result)
    assert refreshed is not None
    assert refreshed.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    new_receipt = _required_receipt(refreshed)
    assert new_receipt.token != old_receipt.token
    assert new_receipt.scope_fingerprint != old_receipt.scope_fingerprint
    if change == "configuration":
        assert (
            new_receipt.configuration_fingerprint
            != old_receipt.configuration_fingerprint
        )
        assert new_receipt.preflight_fingerprint == old_receipt.preflight_fingerprint
    else:
        assert (
            new_receipt.configuration_fingerprint
            == old_receipt.configuration_fingerprint
        )
        assert new_receipt.preflight_fingerprint != old_receipt.preflight_fingerprint


def test_agent_training_confirmation_never_bypasses_blocking_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study, coordinator, pending, probe = _training_receipt_runtime(monkeypatch)
    monkeypatch.setattr(
        training_service_module,
        "check_training_resource_preflight",
        lambda *_args: ResourcePreflightResult(
            issues=("Training exceeds available GPU memory.",),
            warnings=(),
            diagnostics={"risk_level": "blocking"},
        ),
    )

    result = _execute_training_replay(study, coordinator, pending)

    assert result.error_type == "precondition"
    assert "exceeds available GPU memory" in result.message
    assert probe.start_count == 0
