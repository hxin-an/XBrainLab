"""Resource receipts stay bound across the real agent command boundary."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import mne
import numpy as np
import pytest

from tests.integration.agent.deferred_split_support import (
    build_saved_split_runtime,
    install_materialized_candidate,
)
from XBrainLab.backend.application import (
    ChangedState,
    Command,
    CommandName,
    CommandResult,
    ConfigureTrainingCommand,
    SaliencyCommand,
    ValidateInterpretationCommand,
    get_application_service,
)
from XBrainLab.backend.application import analysis_service as analysis_service_module
from XBrainLab.backend.application import data_interpretation_service as service_module
from XBrainLab.backend.application import training_service as training_service_module
from XBrainLab.backend.application.analysis_service import AnalysisCommandService
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.backend.application.resource_guard import ResourcePreflightResult
from XBrainLab.backend.application.resource_preflight import (
    RESOURCE_PREFLIGHT_SCHEMA_VERSION,
    ResourcePreflightView,
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.training_runtime import (
    TrainingCommandRuntimePort,
    TrainingRuntimeContext,
)
from XBrainLab.backend.application.training_service import TrainingCommandService
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.load_data import Raw
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
from XBrainLab.llm.agent.tool_call_normalizer import normalize_tool_call
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
    ToolCommandResult,
    execute_application_tool_command,
)


def _warning_preflight(paths: list[str]) -> ResourcePreflightResult:
    files = [
        {
            "path": str(Path(path).resolve()),
            "file_bytes": Path(path).stat().st_size,
        }
        for path in paths
    ]
    return ResourcePreflightResult(
        issues=(),
        warnings=("Import is near the available RAM limit.",),
        diagnostics={
            "risk_level": "warning",
            "message": "Import is near the available RAM limit.",
            "files": files,
        },
    )


def _unknown_preflight(paths: list[str]) -> ResourcePreflightResult:
    files = [
        {
            "path": str(Path(path).resolve()),
            "file_bytes": Path(path).stat().st_size,
        }
        for path in paths
    ]
    return ResourcePreflightResult(
        issues=(),
        unknowns=("Import memory could not be estimated reliably.",),
        diagnostics={
            "risk_level": "unknown",
            "message": "Import memory could not be estimated reliably.",
            "files": files,
        },
    )


def _detached_raw(path: str) -> Raw:
    """Return one real holder for the detached interpretation-import seam."""
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    return Raw(
        path,
        mne.io.RawArray(
            np.zeros((1, 200), dtype=np.float64),
            info,
            verbose="ERROR",
        ),
    )


def _prepare_candidate(
    study: Study,
    source: Path,
    *,
    selected: Path | None = None,
) -> str:
    service = get_application_service(study)
    scan = service.scan_source(str(source))
    assert scan.ok
    choices: dict[str, Any] = {}
    if selected is not None:
        choices["selected_eeg_files"] = [str(selected.resolve())]
    context_source = ApplicationToolContextSource(study)
    context = context_source.get_context("preview_interpretation")
    assert context is not None
    params = {"choices": choices}
    preview = execute_application_tool_command(
        study,
        "preview_interpretation",
        params,
        availability=context.availability,
        state=context.state,
    )
    assert isinstance(preview, ToolCommandResult)
    if preview.error_type == "confirmation_required":
        initial = ToolAttemptDecision(
            action=ToolAttemptAction.EXECUTE,
            command_name="preview_interpretation",
            params=params,
            context=context,
        )
        pending = ToolAttemptCoordinator.resource_confirmation(initial, preview)
        assert pending is not None
        assert pending.action is ToolAttemptAction.CONFIRMATION_REQUIRED
        coordinator = ToolAttemptCoordinator(
            registry=MagicMock(),
            verifier=MagicMock(),
            context_source=context_source,
        )
        preview, _params = _execute_interpretation_approval(
            study,
            coordinator,
            pending,
        )
    assert preview.ok
    candidate_id = str(preview.diagnostics["candidate"]["candidate_id"])
    validation = service.execute(
        ValidateInterpretationCommand(candidate_id=candidate_id)
    )
    assert validation.ok
    return candidate_id


def _request_receipt(study: Study, candidate_id: str) -> ToolAttemptDecision:
    result = execute_application_tool_command(
        study,
        "apply_interpretation",
        {"candidate_id": candidate_id, "confirmed": True},
    )
    assert isinstance(result, ToolCommandResult)
    assert result.error_type == "confirmation_required"
    preflight = ResourcePreflightView.from_diagnostics(result.diagnostics)
    assert preflight is not None
    assert preflight.schema_version == RESOURCE_PREFLIGHT_SCHEMA_VERSION
    assert preflight.challenge is not None
    assert preflight.challenge.command_name == "apply_interpretation"
    assert preflight.challenge.candidate_id == candidate_id
    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name="apply_interpretation",
        params={"candidate_id": candidate_id, "confirmed": True},
        context=ToolAvailabilityContext(
            availability=ToolAvailability(
                tool_name="apply_interpretation",
                command_name="apply_interpretation",
                enabled=True,
            ),
            state=result.state,
            generation=1,
        ),
    )
    pending = ToolAttemptCoordinator.resource_confirmation(initial, result)
    assert pending is not None
    assert pending.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    assert pending.resource_preflight_receipt is not None
    return pending


def _required_receipt(
    pending: ToolAttemptDecision,
) -> ResourcePreflightReceipt:
    receipt = pending.resource_preflight_receipt
    assert receipt is not None
    return receipt


def _request_interpretation_receipt(
    study: Study,
    command_name: str,
    params: dict[str, Any],
) -> tuple[ToolAttemptCoordinator, ToolAttemptDecision]:
    context_source = ApplicationToolContextSource(study)
    context = context_source.get_context(command_name)
    assert context is not None
    assert context.availability.enabled, context.availability.reasons
    result = execute_application_tool_command(
        study,
        command_name,
        params,
        availability=context.availability,
        state=context.state,
    )
    assert isinstance(result, ToolCommandResult)
    assert result.error_type == "confirmation_required", result
    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name=command_name,
        params=dict(params),
        context=context,
    )
    pending = ToolAttemptCoordinator.resource_confirmation(initial, result)
    assert pending is not None
    assert pending.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    coordinator = ToolAttemptCoordinator(
        registry=MagicMock(),
        verifier=MagicMock(),
        context_source=context_source,
    )
    return coordinator, pending


def _execute_interpretation_approval(
    study: Study,
    coordinator: ToolAttemptCoordinator,
    pending: ToolAttemptDecision,
    *,
    mutate_params: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[ToolCommandResult, dict[str, Any]]:
    context = pending.context
    assert context is not None
    params = coordinator.approved_params(pending)
    if mutate_params is not None:
        mutate_params(params)
    result = execute_application_tool_command(
        study,
        pending.command_name,
        params,
        availability=context.availability,
        state=context.state,
    )
    assert isinstance(result, ToolCommandResult)
    return result, params


def _write_recipe(recipe_path: Path, source_path: Path) -> None:
    recipe_path.write_text(
        json.dumps(
            {
                "recipe_id": "recipe-1",
                "interpretation_id": "interpretation-1",
                "source_path": str(source_path),
                "source_kind": "file",
                "selected_eeg_files": [str(source_path)],
                "skip_labels": True,
            },
        ),
        encoding="utf-8",
    )


def _replay(
    study: Study,
    pending: ToolAttemptDecision,
    *,
    candidate_id: str | None = None,
) -> ToolCommandResult:
    params = ToolAttemptCoordinator.confirmed_params(
        "apply_interpretation",
        {
            "candidate_id": candidate_id or pending.params["candidate_id"],
            "confirmed": True,
        },
        confirmation_kind=pending.confirmation_kind,
        resource_preflight_receipt=_required_receipt(pending),
    )
    result = execute_application_tool_command(
        study,
        "apply_interpretation",
        params,
    )
    assert isinstance(result, ToolCommandResult)
    return result


def _replay_adversarial_candidate(
    study: Study,
    pending: ToolAttemptDecision,
    candidate_id: str,
) -> ToolCommandResult:
    """Bypass host binding to prove the adapter/backend boundary also rejects."""
    receipt = pending.resource_preflight_receipt
    assert receipt is not None
    result = execute_application_tool_command(
        study,
        "apply_interpretation",
        {
            "candidate_id": candidate_id,
            "confirmed": True,
            "resource_preflight_confirmed": True,
            "resource_preflight_token": receipt.token,
        },
    )
    assert isinstance(result, ToolCommandResult)
    return result


@pytest.fixture
def receipt_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Study, Any, Path, Path, str, MagicMock]:
    first = tmp_path / "first.fif"
    second = tmp_path / "second.fif"
    first.write_bytes(b"first EEG header")
    second.write_bytes(b"second EEG header")
    study = Study()
    service = get_application_service(study)
    load_raw = MagicMock(side_effect=_detached_raw)
    service.dataset._raw_factory_provider = lambda: SimpleNamespace(load=load_raw)
    first_candidate = _prepare_candidate(study, first)
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _warning_preflight,
    )
    # Review owns one SAFE admission. Simulate a changed runtime resource
    # boundary so Apply must obtain a fresh preflight before issuing a receipt.
    monkeypatch.setattr(service_module, "available_ram_bytes", lambda: None)
    return study, service, first, second, first_candidate, load_raw


def test_agent_replays_exact_backend_resource_receipt(receipt_runtime) -> None:
    study, _service, _first, _second, candidate_id, load_raw = receipt_runtime
    pending = _request_receipt(study, candidate_id)

    result = _replay(study, pending)

    assert result.ok
    assert (
        result.diagnostics["resource_preflight"]["confirmation_receipt_reused"] is True
    )
    load_raw.assert_called_once_with(str(_first.resolve()))


def test_agent_legacy_load_data_is_denied_before_resource_receipt(
    tmp_path: Path,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"EEG header")
    study = Study()
    service = get_application_service(study)
    load_raw = MagicMock()
    service.dataset._raw_factory_provider = lambda: SimpleNamespace(load=load_raw)
    context_source = ApplicationToolContextSource(study)
    context = context_source.get_context("load_data")
    assert context is not None
    assert context.availability.enabled is False
    params = {"paths": [str(eeg_path)]}
    denied = execute_application_tool_command(
        study,
        "load_data",
        params,
        availability=context.availability,
        state=context.state,
    )
    assert isinstance(denied, ToolCommandResult)
    assert denied.ok is False
    assert denied.error_code == "assistant_direct_load_disabled"
    assert denied.error_type == "precondition"
    assert "scan_source" in str(denied.recovery_action)
    load_raw.assert_not_called()


def test_agent_receipt_rejects_stale_candidate_with_same_scope(
    receipt_runtime,
) -> None:
    study, _service, first, _second, first_candidate, load_raw = receipt_runtime
    pending = _request_receipt(study, first_candidate)
    second_candidate = _prepare_candidate(
        study,
        first,
        selected=first,
    )

    with pytest.raises(ValueError, match="candidate does not match"):
        _replay(study, pending, candidate_id=second_candidate)
    tokenless = execute_application_tool_command(
        study,
        "apply_interpretation",
        {
            "candidate_id": second_candidate,
            "confirmed": True,
            "resource_preflight_confirmed": True,
        },
    )
    assert isinstance(tokenless, ToolCommandResult)
    assert tokenless.error_type == "confirmation_required"
    result = _replay_adversarial_candidate(study, pending, second_candidate)

    assert result.error_type == "confirmation_required"
    assert result.diagnostics["resource_preflight"]["candidate_id"] == second_candidate
    assert (
        result.diagnostics["resource_preflight"]["confirmation_token"]
        != _required_receipt(pending).token
    )
    load_raw.assert_not_called()


def test_agent_receipt_rejects_changed_selected_scope(receipt_runtime) -> None:
    study, _service, _first, second, first_candidate, load_raw = receipt_runtime
    pending = _request_receipt(study, first_candidate)
    second_candidate = _prepare_candidate(
        study,
        second.parent,
        selected=second,
    )

    with pytest.raises(ValueError, match="candidate does not match"):
        _replay(study, pending, candidate_id=second_candidate)
    result = _replay_adversarial_candidate(study, pending, second_candidate)

    assert result.error_type == "confirmation_required"
    assert (
        result.diagnostics["resource_preflight"]["scope_fingerprint"]
        != _required_receipt(pending).scope_fingerprint
    )
    load_raw.assert_not_called()


def test_agent_receipt_rejects_file_changed_after_confirmation(
    receipt_runtime,
) -> None:
    study, _service, first, _second, candidate_id, load_raw = receipt_runtime
    pending = _request_receipt(study, candidate_id)
    first.write_bytes(b"changed file invalidates the resource scope fingerprint")

    result = _replay(study, pending)

    assert result.error_type == "confirmation_required"
    assert (
        result.diagnostics["resource_preflight"]["confirmation_token"]
        != _required_receipt(pending).token
    )
    load_raw.assert_not_called()


def test_agent_receipt_rejects_expired_confirmation(
    receipt_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study, _service, _first, _second, candidate_id, load_raw = receipt_runtime
    monotonic_now = 100.0
    monkeypatch.setattr(service_module.time, "monotonic", lambda: monotonic_now)
    pending = _request_receipt(study, candidate_id)
    monotonic_now += service_module.IMPORT_PREFLIGHT_RECEIPT_TTL_SECONDS + 1.0

    result = _replay(study, pending)

    assert result.error_type == "confirmation_required"
    assert (
        result.diagnostics["resource_preflight"]["confirmation_token"]
        != _required_receipt(pending).token
    )
    load_raw.assert_not_called()


@pytest.mark.parametrize(
    "preflight_factory",
    [_warning_preflight, _unknown_preflight],
    ids=["warning", "unknown"],
)
def test_agent_preview_confirmation_consumes_exact_receipt_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    preflight_factory: Callable[[list[str]], ResourcePreflightResult],
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"EEG header")
    study = Study()
    service = get_application_service(study)
    scan = service.scan_source(str(eeg_path))
    assert scan.ok
    scan_id = str(scan.diagnostics["scan_result"]["scan_id"])
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        preflight_factory,
    )
    coordinator, pending = _request_interpretation_receipt(
        study,
        "preview_interpretation",
        {"scan_id": scan_id, "choices": {"skip_labels": True}},
    )

    result, approved = _execute_interpretation_approval(
        study,
        coordinator,
        pending,
    )

    assert result.ok
    assert (
        result.diagnostics["resource_preflight"]["confirmation_receipt_reused"] is True
    )
    assert approved["resource_preflight_token"] == _required_receipt(pending).token

    replayed = execute_application_tool_command(
        study,
        "preview_interpretation",
        approved,
        availability=pending.context.availability if pending.context else None,
        state=pending.context.state if pending.context else None,
    )
    assert isinstance(replayed, ToolCommandResult)
    assert replayed.error_type == "confirmation_required"


@pytest.mark.parametrize("mutation", ["choices", "source"])
def test_agent_preview_receipt_rejects_changed_request_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    first = tmp_path / "first.fif"
    second = tmp_path / "second.fif"
    first.write_bytes(b"first EEG header")
    second.write_bytes(b"second EEG header")
    study = Study()
    service = get_application_service(study)
    scan = service.scan_source(str(first))
    assert scan.ok
    first_scan_id = str(scan.diagnostics["scan_result"]["scan_id"])
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _warning_preflight,
    )
    coordinator, pending = _request_interpretation_receipt(
        study,
        "preview_interpretation",
        {"scan_id": first_scan_id, "choices": {"skip_labels": True}},
    )
    old_receipt = _required_receipt(pending)

    if mutation == "choices":

        def mutate(params: dict[str, Any]) -> None:
            params["choices"] = {"skip_labels": False}
    else:
        second_scan = service.scan_source(str(second))
        assert second_scan.ok
        second_scan_id = str(second_scan.diagnostics["scan_result"]["scan_id"])

        def mutate(params: dict[str, Any]) -> None:
            params["scan_id"] = second_scan_id

    result, _approved = _execute_interpretation_approval(
        study,
        coordinator,
        pending,
        mutate_params=mutate,
    )

    assert result.error_type == "confirmation_required"
    refreshed = ResourcePreflightView.from_diagnostics(result.diagnostics)
    assert refreshed is not None
    assert refreshed.challenge is not None
    assert refreshed.challenge.token != old_receipt.token


def test_agent_preview_warning_approval_cannot_bypass_new_blocking_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"EEG header")
    study = Study()
    service = get_application_service(study)
    scan = service.scan_source(str(eeg_path))
    assert scan.ok
    scan_id = str(scan.diagnostics["scan_result"]["scan_id"])
    risk_level = "warning"

    def _current_preflight(paths: list[str]) -> ResourcePreflightResult:
        if risk_level == "warning":
            return _warning_preflight(paths)
        return ResourcePreflightResult(
            issues=("Dataset is too large to preview safely.",),
            warnings=(),
            diagnostics={"risk_level": "blocking"},
        )

    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _current_preflight,
    )
    coordinator, pending = _request_interpretation_receipt(
        study,
        "preview_interpretation",
        {"scan_id": scan_id, "choices": {"skip_labels": True}},
    )
    risk_level = "blocking"

    result, _approved = _execute_interpretation_approval(
        study,
        coordinator,
        pending,
    )

    assert result.error_type == "precondition"
    assert "too large" in result.message.lower()
    assert service.interpretation.snapshot().has_preview is False


def test_agent_reload_warning_approval_consumes_exact_receipt_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    recipe_path = tmp_path / "recipe.json"
    eeg_path.write_bytes(b"EEG header")
    _write_recipe(recipe_path, eeg_path)
    study = Study()
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _warning_preflight,
    )
    coordinator, pending = _request_interpretation_receipt(
        study,
        "reload_interpretation_recipe",
        {"recipe_path": str(recipe_path)},
    )

    result, approved = _execute_interpretation_approval(
        study,
        coordinator,
        pending,
    )

    assert result.ok
    assert (
        result.diagnostics["resource_preflight"]["confirmation_receipt_reused"] is True
    )

    replayed = execute_application_tool_command(
        study,
        "reload_interpretation_recipe",
        approved,
        availability=pending.context.availability if pending.context else None,
        state=pending.context.state if pending.context else None,
    )
    assert isinstance(replayed, ToolCommandResult)
    assert replayed.error_type == "confirmation_required"


def test_agent_reload_receipt_rejects_changed_recipe_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.fif"
    second = tmp_path / "second.fif"
    recipe_path = tmp_path / "recipe.json"
    first.write_bytes(b"first EEG header")
    second.write_bytes(b"second EEG header")
    _write_recipe(recipe_path, first)
    study = Study()
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _warning_preflight,
    )
    coordinator, pending = _request_interpretation_receipt(
        study,
        "reload_interpretation_recipe",
        {"recipe_path": str(recipe_path)},
    )
    old_receipt = _required_receipt(pending)
    _write_recipe(recipe_path, second)

    result, _approved = _execute_interpretation_approval(
        study,
        coordinator,
        pending,
    )

    assert result.error_type == "confirmation_required"
    refreshed = ResourcePreflightView.from_diagnostics(result.diagnostics)
    assert refreshed is not None
    assert refreshed.challenge is not None
    assert refreshed.challenge.token != old_receipt.token
    assert (
        refreshed.challenge.configuration_fingerprint
        != old_receipt.configuration_fingerprint
    )


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


def test_agent_saliency_replays_only_exact_host_issued_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = ApplicationStateSnapshot.empty()
    state = replace(
        state,
        pipeline_stage="trained",
        evaluation=replace(
            state.evaluation,
            available=True,
            total_plans=1,
            total_runs=1,
            finished_runs=1,
        ),
        active_training=replace(
            state.active_training,
            has_model=True,
            has_training_option=True,
            has_trainer=True,
        ),
    )
    configured: list[dict[str, Any]] = []
    visualization = MagicMock()
    visualization.set_saliency_params.side_effect = configured.append
    visualization.get_saliency_params.side_effect = (
        lambda: configured[-1] if configured else None
    )
    training_runtime = MagicMock()
    training_runtime.resource_context.return_value = SimpleNamespace(
        datasets=(object(),),
        training_option=object(),
        model_holder=object(),
    )
    training_runtime.training_plan_holders.return_value = ()
    analysis = AnalysisCommandService(
        training_runtime=training_runtime,
        visualization=visualization,
        get_state=lambda: state,
    )
    monkeypatch.setattr(
        analysis_service_module,
        "check_saliency_resource_preflight",
        lambda *_args, **_kwargs: ResourcePreflightResult(
            issues=(),
            warnings=("Saliency may use most available memory.",),
            diagnostics={
                "risk_level": "warning",
                "operation": "saliency_recomputation",
            },
        ),
    )

    class _Runtime:
        def __init__(self) -> None:
            self.commands: list[SaliencyCommand] = []

        def get_view_publication(self) -> ApplicationViewPublication:
            return ApplicationViewPublication(
                generation=1,
                state=state,
                capabilities=build_capability_policy(state),
            )

        def execute(self, command: Command) -> CommandResult:
            assert isinstance(command, SaliencyCommand)
            self.commands.append(command)
            try:
                handler_result = analysis.handle_saliency(command)
            except ApplicationError as exc:
                return CommandResult.failure_result(
                    command_name=CommandName.SALIENCY.value,
                    message=str(exc),
                    state=state,
                    changed_state=ChangedState(),
                    error_type=exc.error_type,
                    recoverable=exc.recoverable,
                    error_message=str(exc),
                    diagnostics=exc.diagnostics,
                )
            assert isinstance(handler_result, tuple)
            message, diagnostics = handler_result
            return CommandResult.success_result(
                command_name=CommandName.SALIENCY.value,
                message=message,
                state=state,
                changed_state=ChangedState(visualization_changed=True),
                diagnostics=diagnostics,
            )

    runtime = _Runtime()
    tool_name, model_params = normalize_tool_call(
        "saliency",
        {
            "method": "Gradient",
            "resource_preflight_confirmed": True,
            "resource_preflight_token": "model-injected-receipt",
        },
    )
    assert model_params == {"method": "Gradient"}
    availability = ToolAvailability(
        tool_name="saliency",
        command_name=CommandName.SALIENCY.value,
        enabled=True,
    )
    challenged = execute_application_tool_command(
        object(),
        tool_name,
        model_params,
        availability=availability,
        state=state.to_dict(),
        runtime=runtime,
    )
    assert isinstance(challenged, ToolCommandResult)
    assert challenged.error_type == "confirmation_required"
    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name="saliency",
        params=model_params,
        context=ToolAvailabilityContext(
            availability=availability,
            state=state.to_dict(),
            generation=1,
        ),
    )
    pending = ToolAttemptCoordinator.resource_confirmation(initial, challenged)
    assert pending is not None
    assert pending.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    receipt = _required_receipt(pending)
    coordinator = ToolAttemptCoordinator(
        registry=MagicMock(),
        verifier=MagicMock(),
        context_source=MagicMock(),
    )

    approved = coordinator.approved_params(pending)
    accepted = execute_application_tool_command(
        object(),
        "saliency",
        approved,
        availability=availability,
        state=state.to_dict(),
        runtime=runtime,
    )

    assert runtime.commands[0].resource_preflight_confirmed is False
    assert runtime.commands[0].resource_preflight_token is None
    assert approved["resource_preflight_token"] == receipt.challenge_id
    assert approved["resource_preflight_token"] != "model-injected-receipt"  # noqa: S105
    assert isinstance(accepted, ToolCommandResult)
    assert accepted.ok
    assert (
        accepted.diagnostics["resource_preflight"]["confirmation_receipt_reused"]
        is True
    )
    assert configured

    replayed = execute_application_tool_command(
        object(),
        "saliency",
        approved,
        availability=availability,
        state=state.to_dict(),
        runtime=runtime,
    )

    assert isinstance(replayed, ToolCommandResult)
    assert replayed.error_type == "confirmation_required"
    assert len(configured) == 1
