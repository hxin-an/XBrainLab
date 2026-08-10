"""Execution harness for the fast Agent tool-call showcase."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from XBrainLab.backend.application.runtime import get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.interaction import (
    AgentInteractionOutcome,
    AgentInteractionStatus,
)
from XBrainLab.llm.agent.prompt_policy import prompt_action_authorization
from XBrainLab.llm.agent.request_admission import (
    UserRequestAdmission,
    UserRequestAdmissionAction,
    UserRequestAdmissionPolicy,
)
from XBrainLab.llm.agent.response_presentation import interaction_outcome_message
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ApplicationToolContextSource,
    ToolAttemptAction,
    ToolAttemptCoordinator,
    ToolAttemptDecision,
    ToolAttemptRequest,
)
from XBrainLab.llm.agent.tool_execution_coordinator import (
    ToolExecutionCoordinator,
)
from XBrainLab.llm.agent.tool_feedback import summarize_tool_result
from XBrainLab.llm.agent.verifier import VerificationLayer, VerificationResult
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.application_surface import (
    TOOL_TO_COMMAND,
    ApplicationToolRuntime,
    ToolCommandResult,
    application_tool_runtime,
    authorize_assistant_setting_change,
    execute_application_tool_command,
)
from XBrainLab.llm.tools.result_contract import UiRequest
from XBrainLab.llm.tools.tool_registry import ToolRegistry
from XBrainLab.product_language import tool_action_label

from .cases import ShowcaseCase
from .selector import ProposalSelector

SCHEMA_VERSION = "xbrainlab.agent_toolcall_showcase.v2"
DIAGNOSTIC_DISCLAIMER = (
    "This is a product showcase and diagnostic. It is not the frozen thesis "
    "benchmark, does not report Agent accuracy, and must not be cited as thesis "
    "evidence."
)


def showcase_limitations(mode: str) -> list[str]:
    """Return only the claim boundaries that apply to the selected runner mode."""
    limitations = [
        DIAGNOSTIC_DISCLAIMER,
        (
            "The fast matrix cancels training before execution and verifies "
            "evaluation and saliency as blocked before a finished run; it does "
            "not validate training quality or completed analysis output."
        ),
    ]
    if mode == "deterministic":
        limitations.append(
            "Deterministic mode scripts only proposal selection; every reported "
            "command result still comes from the current product execution boundary."
        )
    elif mode == "real_granite":
        limitations.append(
            "Real Granite mode is an opt-in local runtime diagnostic. A run is not "
            "an accuracy score, repeat study, or benchmark result."
        )
    else:
        limitations.append(
            "The proposal-selection mode is unknown, so this artifact cannot support "
            "a model-specific claim."
        )
    return limitations


_PREPARATION_ORDER = {
    "empty": 0,
    "scanned": 1,
    "previewed": 2,
    "validated": 3,
    "loaded": 4,
    "preprocessed": 5,
    "epoched": 6,
    "dataset_ready": 7,
    "training_configured": 8,
}


class ShowcaseContractError(RuntimeError):
    """Raised when the diagnostic cannot produce an authoritative outcome."""


class _SignalRecorder:
    def __init__(self) -> None:
        self.values: list[Any] = []

    def emit(self, value: Any = None) -> None:
        self.values.append(value)


@dataclass
class _Metrics:
    current_turn: Any = None


@dataclass
class _ExecutionHost:
    study: Study
    registry: ToolRegistry
    metrics: _Metrics
    status_update: _SignalRecorder
    application_command_started: _SignalRecorder
    application_command_completed: _SignalRecorder


class _RecordingVerifier:
    """Record the exact verification result consumed by the coordinator."""

    def __init__(self, verifier: VerificationLayer) -> None:
        self._verifier = verifier
        self.last: VerificationResult | None = None

    def verify_tool_call(
        self,
        tool_call: tuple[str, dict[str, Any]],
        *,
        confidence: float,
    ) -> VerificationResult:
        self.last = self._verifier.verify_tool_call(
            tool_call,
            confidence=confidence,
        )
        return self.last


class _FailOnceRuntime:
    """Inject one owned runtime exception, then delegate to the real service."""

    def __init__(self, delegate: ApplicationToolRuntime) -> None:
        self._delegate = delegate
        self.calls = 0

    def get_view_publication(self):
        return self._delegate.get_view_publication()

    def execute(self, command):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("showcase fail-once runtime diagnostic")
        return self._delegate.execute(command)


class WorkflowHarness:
    """Own one real Study and prepare requested workflow stages through commands."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.runtime_dir = output_dir / "runtime"
        self.source_path = (self.runtime_dir / "showcase_raw.fif").resolve()
        self.study = Study()
        self.service = get_application_service(self.study)

    def close(self) -> None:
        self.service.close()

    def publication(self):
        return self.service.get_view_publication()

    def ensure_source(self) -> Path:
        """Create one compact deterministic EEG source under repo-local build output."""
        if self.source_path.exists():
            return self.source_path
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

        import mne
        import numpy as np

        sfreq = 128
        info = mne.create_info(
            ch_names=["C3", "C4", "Cz", "Pz"],
            sfreq=sfreq,
            ch_types="eeg",
        )
        data = np.random.default_rng(41).normal(
            scale=1e-6,
            size=(4, sfreq * 16),
        )
        raw = mne.io.RawArray(data, info, verbose="ERROR")
        events = np.array(
            [[128 + index * 64, 0, 1 + index % 2] for index in range(24)],
            dtype=int,
        )
        raw.set_annotations(
            mne.annotations_from_events(
                events,
                sfreq=sfreq,
                event_desc={1: "left", 2: "right"},
            )
        )
        raw.save(self.source_path, overwrite=True, verbose="ERROR")
        return self.source_path

    def ensure(self, preparation: str) -> list[dict[str, Any]]:
        """Reach one stage using authoritative snapshots instead of shadow state."""
        if preparation not in _PREPARATION_ORDER:
            raise ShowcaseContractError(f"Unknown preparation stage: {preparation}")
        target = _PREPARATION_ORDER[preparation]
        trace: list[dict[str, Any]] = []

        state = self.service.get_state()
        if target >= 1 and not state.interpretation.has_scan_result:
            self.ensure_source()
            trace.append(
                self._setup_command(
                    "scan_source",
                    {"source_path": str(self.source_path)},
                )
            )
            state = self.service.get_state()
        if target >= 2 and not state.interpretation.has_candidate:
            trace.append(self._setup_command("preview_interpretation", {}))
            state = self.service.get_state()
        if target >= 3 and not state.interpretation.has_validation_decision:
            trace.append(self._setup_command("validate_interpretation", {}))
            state = self.service.get_state()
        if target >= 4 and not state.active_dataset.has_raw_data:
            trace.append(
                self._setup_command(
                    "apply_interpretation",
                    {"confirmed": True},
                )
            )
            state = self.service.get_state()
        if target >= 5 and not state.preprocessed.operations:
            trace.append(
                self._setup_command(
                    "apply_standard_preprocess",
                    {
                        "l_freq": 4.0,
                        "h_freq": 40.0,
                        "normalize_method": "z-score",
                    },
                )
            )
            state = self.service.get_state()
        if target >= 6 and not state.active_dataset.has_epoch_data:
            trace.append(
                self._setup_command(
                    "epoch_data",
                    {
                        "event_id": ["left", "right"],
                        "t_min": 0.0,
                        "t_max": 0.25,
                    },
                )
            )
            state = self.service.get_state()
        if target >= 7 and not state.active_dataset.has_datasets:
            trace.append(
                self._setup_command(
                    "configure_dataset_split",
                    {
                        "training_mode": "individual",
                        "split_strategy": "trial",
                        "val_ratio": 0.2,
                        "test_ratio": 0.2,
                    },
                )
            )
            state = self.service.get_state()
        if target >= 8 and not state.training.has_model:
            trace.append(
                self._setup_command(
                    "set_model",
                    authorize_assistant_setting_change(
                        "set_model",
                        {"model_name": "EEGNet"},
                        publication_generation=self.publication().generation,
                    ),
                )
            )
            state = self.service.get_state()
        if target >= 8 and not state.training.has_training_option:
            trace.append(
                self._setup_command(
                    "configure_training",
                    authorize_assistant_setting_change(
                        "configure_training",
                        {
                            "model_name": "EEGNet",
                            "epoch": 1,
                            "batch_size": 4,
                            "learning_rate": 0.001,
                            "device": "cpu",
                        },
                        publication_generation=self.publication().generation,
                    ),
                )
            )

        failed = [entry for entry in trace if not entry["ok"]]
        if failed:
            last = failed[-1]
            raise ShowcaseContractError(
                f"Setup command {last['tool_name']} failed: {last['message']}"
            )
        return trace

    def induce_revision_change(self) -> dict[str, Any]:
        """Advance the real publication generation with an actual setting command."""
        return self._setup_command(
            "set_model",
            authorize_assistant_setting_change(
                "set_model",
                {"model_name": "EEGNet"},
                publication_generation=self.publication().generation,
            ),
        )

    def _setup_command(
        self,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        result = execute_application_tool_command(self.study, tool_name, params)
        if not isinstance(result, ToolCommandResult):
            raise ShowcaseContractError(
                f"Setup command {tool_name} returned no terminal command result."
            )
        return {
            "tool_name": tool_name,
            "ok": result.ok,
            "error_type": result.error_type,
            "message": result.message,
            "changed_state": dict(result.changed_state),
        }


class ShowcaseRunner:
    """Run selected showcase cases and return one machine-readable report."""

    def __init__(
        self,
        *,
        output_dir: Path,
        selector: ProposalSelector,
    ) -> None:
        self.output_dir = output_dir.resolve()
        self.selector = selector
        self.registry = ToolRegistry()
        tools = get_all_tools(mode="real")
        for tool in tools:
            self.registry.register(tool)
        self.verifier = VerificationLayer(
            tool_schemas={tool.name: tool.parameters for tool in tools},
        )
        self.admission = UserRequestAdmissionPolicy()

    def run(
        self,
        cases: list[ShowcaseCase],
        *,
        resumed_from: str | None = None,
        retained_cases: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not cases:
            raise ShowcaseContractError("No showcase cases matched the selection.")

        started_wall = datetime.now(UTC)
        started = time.monotonic()
        source_commit = current_source_commit()
        source_fingerprint = current_source_fingerprint()
        selector_metadata = self.selector.metadata()
        selector_identity = _selector_identity(selector_metadata)
        world = WorkflowHarness(self.output_dir)
        results: list[dict[str, Any]] = []
        retained = retained_cases or {}
        try:
            for case in cases:
                previous = retained.get(case.case_id)
                if (
                    previous is not None
                    and resume_case_matches(case, previous)
                    and _resume_run_identity_matches(
                        previous,
                        source_commit=source_commit,
                        source_fingerprint=source_fingerprint,
                        selector_identity=selector_identity,
                    )
                ):
                    results.append(
                        _resumed_case_result(
                            case,
                            previous,
                            source_path=str(world.source_path),
                        )
                    )
                    continue
                target_world = (
                    WorkflowHarness(self.output_dir)
                    if case.flow == "stale_revision"
                    else world
                )
                try:
                    results.append(self._run_case(case, target_world))
                finally:
                    if target_world is not world:
                        target_world.close()
        finally:
            world.close()
            self.selector.close()

        require_source_stability(
            start_commit=source_commit,
            start_fingerprint=source_fingerprint,
            end_commit=current_source_commit(),
            end_fingerprint=current_source_fingerprint(),
        )

        duration_ms = (time.monotonic() - started) * 1000
        results = [
            finalize_case_result(case, result)
            for case, result in zip(cases, results, strict=True)
        ]
        passed = sum(result.get("pass") is True for result in results)
        terminal_missing = sum(
            not terminal_outcome_present(result) for result in results
        )
        status = (
            "passed" if passed == len(results) and terminal_missing == 0 else "failed"
        )
        source = world.source_path
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_kind": "product_showcase_diagnostic",
            "disclaimer": DIAGNOSTIC_DISCLAIMER,
            "run": {
                "status": status,
                "mode": self.selector.mode,
                "started_at": started_wall.isoformat(),
                "duration_ms": round(duration_ms, 3),
                "branch": _git_value("branch", "branch", "--show-current"),
                "commit": source_commit,
                "source_fingerprint": source_fingerprint,
                "case_count": len(results),
                "resumed_from": resumed_from,
                "selector": selector_metadata,
            },
            "summary": {
                "status": status,
                "total": len(results),
                "passed": passed,
                "failed": len(results) - passed,
                "missing_terminal_outcomes": terminal_missing,
            },
            "generated_data": {
                "written": source.exists(),
                "kind": "deterministic synthetic FIF" if source.exists() else None,
                "path": str(source) if source.exists() else None,
                "bytes": source.stat().st_size if source.exists() else 0,
                "downloaded": False,
            },
            "limitations": showcase_limitations(self.selector.mode),
            "cases": results,
        }

    def _run_case(
        self,
        case: ShowcaseCase,
        world: WorkflowHarness,
    ) -> dict[str, Any]:
        started = time.monotonic()
        setup_trace: list[dict[str, Any]] = []
        failures: list[str] = []
        terminal: dict[str, Any] = {}
        command_result: dict[str, Any] | None = None
        changed_state: dict[str, bool] = {}
        handoff: dict[str, Any] | None = None
        confirmation: dict[str, Any] | None = None
        presentation = ""
        selected_tool: str | None = None
        selected_params: dict[str, Any] | None = None
        selection_payload: dict[str, Any] = {
            "owner": None,
            "raw_output": None,
            "parse_status": None,
            "parse_error": None,
            "duration_ms": 0.0,
        }
        verification: dict[str, Any] = {}
        retry: dict[str, Any] | None = None

        try:
            setup_trace = world.ensure(case.preparation)
            if case.tool_name == "list_files":
                world.runtime_dir.mkdir(parents=True, exist_ok=True)
            if case.tool_name == "scan_source" and case.flow != "stale_revision":
                world.ensure_source()
        except Exception as exc:
            failures.append(f"Preparation failed: {type(exc).__name__}: {exc}")
            terminal = {"kind": "setup_failure", "status": "failed"}

        publication_before = world.publication()
        prompt = case.rendered_prompt(str(world.source_path))
        state_before = publication_before.state.to_dict()
        capabilities = publication_before.effective_capabilities.to_dict()
        exposed_names: list[str] = []
        admission = self.admission.evaluate(prompt, publication_before)
        admission_payload = _admission_payload(admission)

        if not failures:
            if case.flow == "runtime_retry":
                runtime_result = self._run_runtime_retry(case, world, admission)
                selected_tool = runtime_result["selected_tool"]
                selected_params = runtime_result["selected_params"]
                verification = runtime_result["verification"]
                command_result = runtime_result["command_result"]
                changed_state = runtime_result["changed_state"]
                presentation = runtime_result["presentation"]
                terminal = runtime_result["terminal"]
                retry = runtime_result["retry"]
            elif admission.action is UserRequestAdmissionAction.BLOCKED:
                selected_tool = case.tool_name
                selected_params = case.rendered_params(str(world.source_path))
                coordinator, _recording = self._attempt_coordinator(world)
                context = coordinator.context_for(case.tool_name)
                blocked = coordinator.blocked_result(case.tool_name, context)
                command_result = blocked.to_payload()
                changed_state = dict(blocked.changed_state)
                presentation = summarize_tool_result(case.tool_name, False, blocked)
                terminal = {"kind": "command_result", "status": "failed"}
                verification = {
                    "status": "request_admission_blocked",
                    "coordinator_action": "capability_blocked",
                    "valid": False,
                    "message": admission.message,
                }
            elif admission.action is UserRequestAdmissionAction.UI_HANDOFF:
                selected_tool = case.tool_name
                selected_params = case.rendered_params(str(world.source_path))
                outcome = AgentInteractionOutcome(
                    status=AgentInteractionStatus.DEFERRED_TO_UI,
                    command_name=(
                        admission.command.value
                        if admission.command is not None
                        else case.tool_name
                    ),
                    decision_fields=admission.decision_fields,
                    message=admission.message,
                )
                handoff = {
                    "kind": "workflow_ui_handoff",
                    "status": outcome.status.value,
                    "command_name": outcome.command_name,
                    "decision_fields": list(outcome.decision_fields),
                }
                presentation = interaction_outcome_message(outcome)
                terminal = {"kind": "handoff", "status": "requested"}
                verification = {
                    "status": "request_admission_ui_handoff",
                    "valid": True,
                }
            else:
                standard = self._run_generated_case(
                    case,
                    world,
                    prompt,
                    admission,
                )
                exposed_names = standard["exposed_tool_schema_names"]
                selection_payload = standard["selection"]
                selected_tool = standard["selected_tool"]
                selected_params = standard["selected_params"]
                verification = standard["verification"]
                confirmation = standard["confirmation"]
                handoff = standard["handoff"]
                command_result = standard["command_result"]
                changed_state = standard["changed_state"]
                presentation = standard["presentation"]
                terminal = standard["terminal"]
                setup_trace.extend(standard["case_internal_trace"])

        publication_after = world.publication()
        result = {
            "case_id": case.case_id,
            "case_identity": case.identity(),
            "prompt_identity": case.prompt_identity(),
            "title": case.title,
            "area": case.area,
            "tags": list(case.tags),
            "prompt": prompt,
            "case_contract": {
                "tool_name": case.tool_name,
                "parameters": case.rendered_params(str(world.source_path)),
                "preparation": case.preparation,
                "expected_terminal": case.expected_terminal,
                "expected_error_type": case.expected_error_type,
            },
            "setup_trace": setup_trace,
            "state_before": state_before,
            "capabilities": capabilities,
            "publication": {
                "before_generation": publication_before.generation,
                "before_revision": publication_before.revision,
                "after_generation": publication_after.generation,
                "after_revision": publication_after.revision,
            },
            "admission": admission_payload,
            "exposed_tool_schema_names": exposed_names,
            "selection": selection_payload,
            "selected_tool": selected_tool,
            "selected_parameters": selected_params,
            "verification": verification,
            "confirmation": confirmation,
            "handoff": handoff,
            "command_result": command_result,
            "changed_state": changed_state,
            "state_after": publication_after.state.to_dict(),
            "user_visible_presentation": presentation,
            "retry": retry,
            "terminal": terminal,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "failures": failures,
        }
        return finalize_case_result(case, result)

    def _run_generated_case(
        self,
        case: ShowcaseCase,
        world: WorkflowHarness,
        prompt: str,
        admission: UserRequestAdmission,
    ) -> dict[str, Any]:
        assembler = ContextAssembler(self.registry, world.study)
        authorization = _prompt_authorization(case, admission)
        assembler.set_turn_authorized_command(authorization)
        messages = assembler.get_messages([{"role": "user", "content": prompt}])
        prompt_publication = assembler.latest_tool_publication
        selection = self.selector.select(
            case,
            messages,
            source_path=str(world.source_path),
        )
        selection_payload = {
            "owner": selection.owner,
            "raw_output": selection.raw_output,
            "parse_status": selection.parsed.status.value,
            "parse_error": selection.parsed.error,
            "generation_error": selection.error,
            "duration_ms": round(selection.duration_ms, 3),
            "prompt_message_count": len(messages),
            "prompt_sha256": _messages_sha256(messages),
        }
        base: dict[str, Any] = {
            "exposed_tool_schema_names": sorted(prompt_publication.tool_names),
            "selection": selection_payload,
            "selected_tool": None,
            "selected_params": None,
            "verification": {
                "status": "selection_not_verified",
                "valid": False,
            },
            "confirmation": None,
            "handoff": None,
            "command_result": None,
            "changed_state": {},
            "presentation": "",
            "terminal": {"kind": "selection_error", "status": "failed"},
            "case_internal_trace": [],
        }
        if not selection.parsed.commands:
            base["presentation"] = (
                "The assistant did not produce one executable action envelope."
            )
            return base

        selected_tool, selected_params = selection.parsed.commands[0]
        base["selected_tool"] = selected_tool
        base["selected_params"] = selected_params
        coordinator, recording = self._attempt_coordinator(world)

        if case.flow == "stale_revision":
            trace = world.induce_revision_change()
            base["case_internal_trace"].append(
                {"purpose": "induce_real_publication_change", **trace}
            )

        decision = coordinator.evaluate(
            ToolAttemptRequest(
                command_name=selected_tool,
                params=selected_params,
                confidence=1.0,
                publication=prompt_publication,
                latest_user_text=prompt,
            )
        )
        base["verification"] = _verification_payload(decision, recording.last)
        if decision.action is ToolAttemptAction.CONFIRMATION_REQUIRED:
            return self._resolve_confirmation(case, world, coordinator, decision, base)
        if decision.action is not ToolAttemptAction.EXECUTE:
            result = decision.result
            if isinstance(result, ToolCommandResult):
                base["command_result"] = result.to_payload()
                base["changed_state"] = dict(result.changed_state)
                base["presentation"] = summarize_tool_result(
                    selected_tool,
                    False,
                    result,
                )
                base["terminal"] = {"kind": "command_result", "status": "failed"}
            return base

        return self._execute_decision(world, coordinator, decision, base)

    def _resolve_confirmation(
        self,
        case: ShowcaseCase,
        world: WorkflowHarness,
        coordinator: ToolAttemptCoordinator,
        decision: ToolAttemptDecision,
        base: dict[str, Any],
    ) -> dict[str, Any]:
        context = decision.context
        request = AgentConfirmationRequest.for_action(
            command_name=decision.command_name,
            params=decision.params,
            action_label=tool_action_label(decision.command_name),
            description=(
                decision.message
                or f"Review {tool_action_label(decision.command_name).lower()}."
            ),
            destructive=bool(context and context.availability.destructive),
            publication_generation=context.generation if context else None,
            confirmation_kind=decision.confirmation_kind,
            request_id=f"showcase-{case.case_id}",
        )
        resolution_status = (
            AgentConfirmationResolutionStatus.APPROVED
            if case.confirmation == "approve"
            else AgentConfirmationResolutionStatus.CANCELLED
        )
        resolution = AgentConfirmationResolution.for_request(
            request,
            status=resolution_status,
        )
        base["confirmation"] = {
            "required": True,
            "kind": request.confirmation_kind or "command_confirmation",
            "request_id": request.request_id,
            "command_name": request.command_name,
            "parameter_rows": [list(row) for row in request.parameter_rows],
            "publication_generation": request.publication_generation,
            "resolution": resolution.status.value,
            "correlation_valid": resolution.matches(request),
        }
        if not resolution.approved:
            outcome = AgentInteractionOutcome(
                status=AgentInteractionStatus.CANCELLED,
                command_name=decision.command_name,
                request_id=request.request_id,
            )
            base["presentation"] = interaction_outcome_message(outcome)
            base["terminal"] = {"kind": "confirmation", "status": "cancelled"}
            return base

        current_generation = coordinator.context_for(decision.command_name).generation
        if current_generation != request.publication_generation:
            result = ToolCommandResult.failure(
                decision.command_name,
                (
                    "Workflow state changed while this confirmation was open. "
                    "Review the action again before continuing."
                ),
                error_type="stale_confirmation",
                recoverable=True,
            )
            base["command_result"] = result.to_payload()
            base["presentation"] = summarize_tool_result(
                decision.command_name,
                False,
                result,
            )
            base["terminal"] = {"kind": "command_result", "status": "failed"}
            return base

        approved = ToolAttemptDecision(
            action=ToolAttemptAction.EXECUTE,
            command_name=decision.command_name,
            params=coordinator.approved_params(decision),
            context=decision.context,
            tool=decision.tool,
        )
        return self._execute_decision(world, coordinator, approved, base)

    def _execute_decision(
        self,
        world: WorkflowHarness,
        coordinator: ToolAttemptCoordinator,
        decision: ToolAttemptDecision,
        base: dict[str, Any],
    ) -> dict[str, Any]:
        if decision.context is None:
            return base
        executor = self._execution_coordinator(world, coordinator)
        outcome = executor.execute(
            decision.command_name,
            decision.params,
            context=decision.context,
        )
        if isinstance(outcome.result, UiRequest):
            base["handoff"] = {
                "kind": outcome.result.kind.value,
                "status": "requested",
                "parameters": dict(outcome.result.params),
            }
            base["presentation"] = summarize_tool_result(
                decision.command_name,
                True,
                outcome.result,
            )
            base["terminal"] = {"kind": "handoff", "status": "requested"}
            return base

        result = outcome.result
        base["command_result"] = result.to_payload()
        base["changed_state"] = dict(result.changed_state)
        base["presentation"] = summarize_tool_result(
            decision.command_name,
            outcome.success,
            result,
        )
        base["terminal"] = {
            "kind": "command_result",
            "status": "ok" if outcome.success else "failed",
        }
        return base

    def _run_runtime_retry(
        self,
        case: ShowcaseCase,
        world: WorkflowHarness,
        admission: UserRequestAdmission,
    ) -> dict[str, Any]:
        if admission.action is not UserRequestAdmissionAction.EXECUTE_READ_ONLY:
            return {
                "selected_tool": case.tool_name,
                "selected_params": case.rendered_params(str(world.source_path)),
                "verification": {
                    "status": "read_only_admission_failed",
                    "valid": False,
                },
                "command_result": None,
                "changed_state": {},
                "presentation": admission.message,
                "terminal": {"kind": "admission_error", "status": "failed"},
                "retry": None,
            }

        coordinator, _recording = self._attempt_coordinator(world)
        context = coordinator.context_for(case.tool_name)
        delegate = application_tool_runtime(world.study)
        if delegate is None:
            raise ShowcaseContractError(
                "Real ApplicationService runtime is unavailable."
            )
        fail_once = _FailOnceRuntime(delegate)
        executor = self._execution_coordinator(
            world,
            coordinator,
            application_runtime=fail_once,
        )
        params = case.rendered_params(str(world.source_path))
        first = executor.execute(case.tool_name, params, context=context)
        retry_decision = coordinator.after_failure(
            mode="multi",
            availability=context.availability,
            failure_count=1,
            global_retry_limit=2,
            execution_count=1,
            tool_cap=3,
            cancelled=False,
        )
        attempts = [_attempt_payload(1, first)]
        terminal_outcome = first
        if retry_decision.continue_workflow:
            terminal_outcome = executor.execute(case.tool_name, params, context=context)
            attempts.append(_attempt_payload(2, terminal_outcome))

        result = terminal_outcome.result
        result_payload = (
            result.to_payload() if isinstance(result, ToolCommandResult) else None
        )
        changed = (
            dict(result.changed_state) if isinstance(result, ToolCommandResult) else {}
        )
        presentation = summarize_tool_result(
            case.tool_name,
            terminal_outcome.success,
            result,
        )
        return {
            "selected_tool": case.tool_name,
            "selected_params": params,
            "verification": {
                "status": "host_admitted_read_only",
                "valid": True,
                "coordinator_action": "execute",
            },
            "command_result": result_payload,
            "changed_state": changed,
            "presentation": presentation,
            "terminal": {
                "kind": "command_result",
                "status": "ok" if terminal_outcome.success else "failed",
            },
            "retry": {
                "decision": retry_decision.reason,
                "continued": retry_decision.continue_workflow,
                "attempts": attempts,
            },
        }

    def _attempt_coordinator(
        self,
        world: WorkflowHarness,
    ) -> tuple[ToolAttemptCoordinator, _RecordingVerifier]:
        recording = _RecordingVerifier(self.verifier)
        return (
            ToolAttemptCoordinator(
                registry=self.registry,
                verifier=recording,
                context_source=ApplicationToolContextSource(world.study),
            ),
            recording,
        )

    def _execution_coordinator(
        self,
        world: WorkflowHarness,
        coordinator: ToolAttemptCoordinator,
        *,
        application_runtime: ApplicationToolRuntime | None = None,
    ) -> ToolExecutionCoordinator:
        host = _ExecutionHost(
            study=world.study,
            registry=self.registry,
            metrics=_Metrics(),
            status_update=_SignalRecorder(),
            application_command_started=_SignalRecorder(),
            application_command_completed=_SignalRecorder(),
        )
        return ToolExecutionCoordinator(
            host,
            block_policy=coordinator,
            application_runtime=application_runtime,
        )


def terminal_outcome_present(case_result: dict[str, Any]) -> bool:
    """Return whether one case has a recognized, non-empty terminal outcome."""
    terminal = case_result.get("terminal")
    if not isinstance(terminal, dict):
        return False
    kind = terminal.get("kind")
    status = terminal.get("status")
    return bool(
        isinstance(kind, str)
        and kind
        and isinstance(status, str)
        and status in {"ok", "failed", "requested", "cancelled"}
    )


def finalize_case_result(
    case: ShowcaseCase,
    case_result: dict[str, Any],
) -> dict[str, Any]:
    """Recompute one case verdict from the current executable contract."""
    result = dict(case_result)
    existing = result.get("failures")
    failures = (
        [item for item in existing if isinstance(item, str) and item]
        if isinstance(existing, list)
        else []
    )
    failures.extend(_case_contract_failures(case, result))
    if not terminal_outcome_present(result):
        failures.append(
            "Missing authoritative terminal outcome; diagnostic failed closed."
        )
    result["failures"] = list(dict.fromkeys(failures))
    result["pass"] = not result["failures"]
    return result


def finalize_showcase_payload(
    payload: dict[str, Any],
    cases: list[ShowcaseCase],
) -> dict[str, Any]:
    """Fail closed when a runner returns incomplete or optimistic case fields."""
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != len(cases):
        raise ShowcaseContractError(
            "Showcase payload case list does not match the current selection."
        )
    finalized: list[dict[str, Any]] = []
    for case, raw_result in zip(cases, raw_cases, strict=True):
        if (
            not isinstance(raw_result, dict)
            or raw_result.get("case_id") != case.case_id
        ):
            raise ShowcaseContractError(
                "Showcase payload case order does not match the current selection."
            )
        finalized.append(finalize_case_result(case, raw_result))

    missing = sum(not terminal_outcome_present(item) for item in finalized)
    passed = sum(item.get("pass") is True for item in finalized)
    status = "passed" if passed == len(finalized) and missing == 0 else "failed"
    result = dict(payload)
    result["cases"] = finalized
    run = dict(result.get("run")) if isinstance(result.get("run"), dict) else {}
    run["status"] = status
    run["case_count"] = len(finalized)
    result["run"] = run
    result["summary"] = {
        "status": status,
        "total": len(finalized),
        "passed": passed,
        "failed": len(finalized) - passed,
        "missing_terminal_outcomes": missing,
    }
    return result


def resume_case_matches(
    case: ShowcaseCase,
    case_result: dict[str, Any],
) -> bool:
    """Return whether a prior result is reusable for this exact case contract."""
    return bool(
        case_result.get("case_id") == case.case_id
        and case_result.get("case_identity") == case.identity()
        and case_result.get("prompt_identity") == case.prompt_identity()
        and case_result.get("pass") is True
        and terminal_outcome_present(case_result)
        and not _case_contract_failures(case, case_result)
    )


def resumable_passed_cases(
    payload: dict[str, Any],
    *,
    expected_cases: list[ShowcaseCase],
    expected_source_commit: str,
    expected_source_fingerprint: str,
    expected_selector: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return allowlisted prior evidence matching the current run contract."""
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ShowcaseContractError("Resume artifact uses an unsupported schema.")
    run = payload.get("run")
    if not isinstance(run, dict):
        raise ShowcaseContractError("Resume artifact has no run identity.")
    if (
        not expected_source_commit
        or expected_source_commit == "unavailable"
        or run.get("commit") != expected_source_commit
    ):
        raise ShowcaseContractError(
            "Resume artifact source commit does not match the current run."
        )
    if (
        not expected_source_fingerprint
        or run.get("source_fingerprint") != expected_source_fingerprint
    ):
        raise ShowcaseContractError(
            "Resume artifact source fingerprint does not match the current run."
        )
    prior_selector = run.get("selector")
    if not isinstance(prior_selector, dict) or (
        _selector_identity(prior_selector) != _selector_identity(expected_selector)
    ):
        raise ShowcaseContractError(
            "Resume artifact selector identity does not match the current run."
        )
    if run.get("mode") != expected_selector.get("mode"):
        raise ShowcaseContractError(
            "Resume artifact selector identity does not match the current run."
        )
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ShowcaseContractError("Resume artifact has no case list.")
    by_id: dict[str, dict[str, Any]] = {}
    for item in raw_cases:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            continue
        case_id = str(item["case_id"])
        if case_id in by_id:
            raise ShowcaseContractError(
                f"Resume artifact contains duplicate case id {case_id!r}."
            )
        by_id[case_id] = item

    retained: dict[str, dict[str, Any]] = {}
    for case in expected_cases:
        item = by_id.get(case.case_id)
        if item is None or not resume_case_matches(case, item):
            continue
        projected = _resume_evidence_projection(case, item)
        if resume_case_matches(case, projected):
            projected["_resume_identity"] = {
                "source_commit": expected_source_commit,
                "source_fingerprint": expected_source_fingerprint,
                "selector": _selector_identity(expected_selector),
            }
            retained[case.case_id] = projected
    return retained


def current_source_commit() -> str:
    """Return the exact Git commit used for resume identity."""
    commit = _git_value("commit", "rev-parse", "HEAD")
    if not commit or commit == "unavailable":
        raise ShowcaseContractError(
            "Current source commit is unavailable; resume cannot be validated."
        )
    return commit


def current_source_fingerprint() -> str:
    """Hash current product/showcase sources, including uncommitted edits."""
    root = Path(__file__).resolve().parents[3]
    package_dir = Path(__file__).resolve().parent
    paths = [
        *(root / "XBrainLab").rglob("*.py"),
        *package_dir.glob("*.py"),
        root / "scripts" / "dev" / "run_agent_toolcall_showcase.py",
        root / "pyproject.toml",
        root / "poetry.lock",
    ]
    digest = hashlib.sha256()
    try:
        for path in sorted({item.resolve() for item in paths if item.is_file()}):
            relative = path.relative_to(root).as_posix().encode("utf-8")
            digest.update(relative)
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    except (OSError, ValueError) as exc:
        raise ShowcaseContractError(
            "Current source fingerprint could not be established."
        ) from exc
    return digest.hexdigest()


def require_source_stability(
    *,
    start_commit: str,
    start_fingerprint: str,
    end_commit: str,
    end_fingerprint: str,
) -> None:
    """Reject an artifact assembled while its product source was changing."""
    if start_commit != end_commit or start_fingerprint != end_fingerprint:
        raise ShowcaseContractError(
            "Product or showcase source changed during the run; rerun the "
            "diagnostic from one stable source state."
        )


def _selector_identity(metadata: dict[str, Any]) -> dict[str, Any]:
    mode = metadata.get("mode")
    identity = {
        "mode": mode,
        "selector_id": metadata.get("selector_id"),
        "selector_version": metadata.get("selector_version"),
        "model_owned": metadata.get("model_owned"),
    }
    if mode == "deterministic":
        valid = (
            identity["selector_id"] == "deterministic_case_selector"
            and type(identity["selector_version"]) is int
            and identity["model_owned"] is False
        )
    elif mode == "real_granite":
        identity.update(
            {
                "model_id": metadata.get("model_id"),
                "revision": metadata.get("revision"),
                "offline": metadata.get("offline"),
                "silent_fallback": metadata.get("silent_fallback"),
            }
        )
        valid = bool(
            identity["selector_id"] == "ibm_granite_product_runtime"
            and type(identity["selector_version"]) is int
            and identity["model_owned"] is True
            and isinstance(identity["model_id"], str)
            and identity["model_id"]
            and isinstance(identity["revision"], str)
            and identity["revision"]
            and identity["offline"] is True
            and identity["silent_fallback"] is False
        )
    else:
        valid = False
    if not valid:
        raise ShowcaseContractError("Selector metadata has no valid resume identity.")
    return identity


def _resume_run_identity_matches(
    case_result: dict[str, Any],
    *,
    source_commit: str,
    source_fingerprint: str,
    selector_identity: dict[str, Any],
) -> bool:
    return case_result.get("_resume_identity") == {
        "source_commit": source_commit,
        "source_fingerprint": source_fingerprint,
        "selector": selector_identity,
    }


def _resume_evidence_projection(
    case: ShowcaseCase,
    case_result: dict[str, Any],
) -> dict[str, Any]:
    projected = {
        "case_id": case.case_id,
        "case_identity": case.identity(),
        "prompt_identity": case.prompt_identity(),
        "selection": {},
        "selected_tool": case_result.get("selected_tool"),
        "selected_parameters": _copy_resume_value(case.params),
        "verification": _copy_allowed_fields(
            case_result.get("verification"),
            {"status", "coordinator_action", "valid"},
        ),
        "confirmation": _copy_allowed_fields(
            case_result.get("confirmation"),
            {
                "required",
                "kind",
                "request_id",
                "command_name",
                "publication_generation",
                "resolution",
                "correlation_valid",
            },
            optional=True,
        ),
        "handoff": _copy_allowed_fields(
            case_result.get("handoff"),
            {"kind", "status", "command_name"},
            optional=True,
        ),
        "command_result": _command_result_projection(case_result.get("command_result")),
        "changed_state": _boolean_mapping(case_result.get("changed_state")),
        "retry": _retry_projection(case_result.get("retry")),
        "terminal": _copy_allowed_fields(
            case_result.get("terminal"),
            {"kind", "status"},
        ),
        "duration_ms": _duration_projection(case_result.get("duration_ms")),
    }
    finalized = finalize_case_result(case, projected)
    finalized.pop("failures", None)
    return finalized


def _resumed_case_result(
    case: ShowcaseCase,
    prior: dict[str, Any],
    *,
    source_path: str,
) -> dict[str, Any]:
    projected = _resume_evidence_projection(case, prior)
    result = {
        "case_id": case.case_id,
        "case_identity": case.identity(),
        "prompt_identity": case.prompt_identity(),
        "title": case.title,
        "area": case.area,
        "tags": list(case.tags),
        "prompt": case.rendered_prompt(source_path),
        "case_contract": {
            "tool_name": case.tool_name,
            "parameters": case.rendered_params(source_path),
            "preparation": case.preparation,
            "expected_terminal": case.expected_terminal,
            "expected_error_type": case.expected_error_type,
        },
        "setup_trace": [],
        "state_before": {},
        "capabilities": {},
        "publication": {},
        "admission": {},
        "exposed_tool_schema_names": [],
        "selection": projected["selection"],
        "selected_tool": projected["selected_tool"],
        "selected_parameters": case.rendered_params(source_path),
        "verification": projected["verification"],
        "confirmation": projected["confirmation"],
        "handoff": projected["handoff"],
        "command_result": projected["command_result"],
        "changed_state": projected["changed_state"],
        "state_after": {},
        "user_visible_presentation": (
            "Matching prior terminal evidence was resumed; no command ran in this run."
        ),
        "retry": projected["retry"],
        "terminal": projected["terminal"],
        "duration_ms": projected["duration_ms"],
        "failures": [],
        "reused_from_resume": True,
    }
    return finalize_case_result(case, result)


def _copy_allowed_fields(
    value: Any,
    allowed: set[str],
    *,
    optional: bool = False,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None if optional else {}
    return {
        str(key): _copy_resume_value(item)
        for key, item in value.items()
        if str(key) in allowed
    }


def _copy_resume_value(value: Any) -> Any:
    if value is None or type(value) in {bool, int, float, str}:
        return value
    if isinstance(value, list):
        return [_copy_resume_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _copy_resume_value(item) for key, item in value.items()}
    return None


def _command_result_projection(value: Any) -> dict[str, Any] | None:
    return _copy_allowed_fields(
        value,
        {"ok", "error_type", "recoverable"},
        optional=True,
    )


def _boolean_mapping(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if type(item) is bool
        and str(key)
        in {
            "raw_changed",
            "preprocessed_changed",
            "epoch_changed",
            "datasets_changed",
            "training_changed",
            "evaluation_changed",
            "visualization_changed",
            "interpretation_changed",
            "error_changed",
            "state_unknown",
        }
    }


def _retry_projection(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    attempts = value.get("attempts")
    projected_attempts = []
    if isinstance(attempts, list):
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            projected_attempts.append(
                {
                    "attempt": attempt.get("attempt"),
                    "success": attempt.get("success"),
                    "result": _command_result_projection(attempt.get("result")),
                }
            )
    return {
        "continued": value.get("continued"),
        "attempts": projected_attempts,
    }


def _duration_projection(value: Any) -> float:
    if type(value) not in {int, float} or float(value) < 0:
        return 0.0
    return float(value)


def _prompt_authorization(
    case: ShowcaseCase,
    admission: UserRequestAdmission,
) -> str | None:
    command = admission.command
    mapped = TOOL_TO_COMMAND.get(case.tool_name)
    if command is None or mapped is None:
        return None
    if mapped is not command:
        return command.value
    return prompt_action_authorization(
        command_name=command.value,
        tool_name=case.tool_name,
    )


def _admission_payload(admission: UserRequestAdmission) -> dict[str, Any]:
    return {
        "action": admission.action.value,
        "command": admission.command.value if admission.command is not None else None,
        "message": admission.message,
        "decision_fields": list(admission.decision_fields),
        "suggested_values": dict(admission.suggested_values),
    }


def _verification_payload(
    decision: ToolAttemptDecision,
    result: VerificationResult | None,
) -> dict[str, Any]:
    return {
        "status": (
            "verified"
            if decision.action
            in {
                ToolAttemptAction.EXECUTE,
                ToolAttemptAction.CONFIRMATION_REQUIRED,
            }
            else "blocked"
        ),
        "coordinator_action": decision.action.value,
        "valid": result.is_valid if result is not None else False,
        "message": (
            result.error_message
            if result is not None
            else decision.result.message
            if isinstance(decision.result, ToolCommandResult)
            else decision.message
        ),
        "capability": (
            decision.context.availability.to_dict()
            if decision.context is not None
            else None
        ),
    }


def _attempt_payload(index: int, outcome: Any) -> dict[str, Any]:
    result = outcome.result
    return {
        "attempt": index,
        "success": outcome.success,
        "result": result.to_payload()
        if isinstance(result, ToolCommandResult)
        else None,
    }


def _case_contract_failures(
    case: ShowcaseCase,
    result: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if result.get("selected_tool") != case.tool_name:
        failures.append(
            f"Selected tool {result.get('selected_tool')!r}; expected {case.tool_name!r}."
        )
    terminal = result.get("terminal") or {}
    command_result = result.get("command_result")
    verification = result.get("verification")
    verification = verification if isinstance(verification, dict) else {}
    confirmation = result.get("confirmation")
    error_type = (
        command_result.get("error_type") if isinstance(command_result, dict) else None
    )

    if case.expected_terminal == "command_ok":
        if terminal != {"kind": "command_result", "status": "ok"}:
            failures.append(f"Expected a successful command result; got {terminal!r}.")
        if not isinstance(command_result, dict) or command_result.get("ok") is not True:
            failures.append("Expected CommandResult.ok=true for successful execution.")
        if error_type not in {None, "none"}:
            failures.append("Successful execution must not report an error type.")
        if case.confirmation != "approve" and not (
            verification.get("status") == "verified"
            and verification.get("coordinator_action") == "execute"
            and verification.get("valid") is True
        ):
            failures.append("Expected exact verified execution semantics.")
    elif case.expected_terminal == "blocked":
        if terminal != {"kind": "command_result", "status": "failed"}:
            failures.append(f"Expected a blocked command result; got {terminal!r}.")
        if (
            not isinstance(command_result, dict)
            or command_result.get("ok") is not False
        ):
            failures.append("Expected CommandResult.ok=false for a blocked command.")
        if not (
            verification.get("status") == "request_admission_blocked"
            and verification.get("coordinator_action") == "capability_blocked"
            and verification.get("valid") is False
        ):
            failures.append(
                "Expected the current request-admission capability block semantics."
            )
    elif case.expected_terminal == "confirmation_cancelled":
        if terminal != {"kind": "confirmation", "status": "cancelled"}:
            failures.append(f"Expected a cancelled confirmation; got {terminal!r}.")
        failures.extend(
            _confirmation_contract_failures(
                case,
                confirmation,
                expected_resolution="cancelled",
            )
        )
        if command_result is not None:
            failures.append("A cancelled confirmation must not have a command result.")
        if not (
            verification.get("status") == "verified"
            and verification.get("coordinator_action") == "confirmation_required"
            and verification.get("valid") is True
        ):
            failures.append("Expected exact confirmation-required semantics.")
    elif case.expected_terminal == "ui_handoff":
        if terminal != {"kind": "handoff", "status": "requested"}:
            failures.append(f"Expected a UI handoff; got {terminal!r}.")
        handoff = result.get("handoff")
        if not (
            isinstance(handoff, dict)
            and handoff.get("kind") == "workflow_ui_handoff"
            and handoff.get("status") == "deferred_to_ui"
            and handoff.get("command_name") == case.tool_name
            and verification.get("status") == "request_admission_ui_handoff"
            and verification.get("valid") is True
        ):
            failures.append("Expected exact workflow UI handoff semantics.")
    elif case.expected_terminal == "stale_revision":
        if (
            terminal != {"kind": "command_result", "status": "failed"}
            or error_type != "stale_publication"
        ):
            failures.append(f"Expected stale-publication rejection; got {terminal!r}.")
        if (
            not isinstance(command_result, dict)
            or command_result.get("ok") is not False
        ):
            failures.append("Expected stale publication CommandResult.ok=false.")
        if not (
            verification.get("status") == "blocked"
            and verification.get("coordinator_action") == "publication_blocked"
            and verification.get("valid") is False
        ):
            failures.append("Expected exact stale-publication verification semantics.")
    elif case.expected_terminal == "retry_ok":
        retry = result.get("retry")
        attempts = retry.get("attempts") if isinstance(retry, dict) else None
        retry_shape_valid = bool(
            isinstance(attempts, list)
            and len(attempts) == 2
            and isinstance(attempts[0], dict)
            and isinstance(attempts[1], dict)
            and attempts[0].get("attempt") == 1
            and attempts[0].get("success") is False
            and isinstance(attempts[0].get("result"), dict)
            and attempts[0]["result"].get("ok") is False
            and attempts[0]["result"].get("error_type") == "runtime"
            and attempts[1].get("attempt") == 2
            and attempts[1].get("success") is True
            and isinstance(attempts[1].get("result"), dict)
            and attempts[1]["result"].get("ok") is True
            and retry.get("continued") is True
        )
        if (
            terminal != {"kind": "command_result", "status": "ok"}
            or not isinstance(command_result, dict)
            or command_result.get("ok") is not True
            or not retry_shape_valid
        ):
            failures.append("Expected one failed runtime attempt followed by success.")

    if case.confirmation == "approve":
        failures.extend(
            _confirmation_contract_failures(
                case,
                confirmation,
                expected_resolution="approved",
            )
        )
        if not (
            verification.get("status") == "verified"
            and verification.get("coordinator_action") == "confirmation_required"
            and verification.get("valid") is True
        ):
            failures.append(
                "Approved setting execution requires verified confirmation admission."
            )

    if case.expected_error_type and error_type != case.expected_error_type:
        failures.append(
            f"Error type {error_type!r}; expected {case.expected_error_type!r}."
        )
    changed = result.get("changed_state")
    for field in case.expected_changed_state:
        if not isinstance(changed, dict) or changed.get(field) is not True:
            failures.append(f"Expected changed_state.{field}=true.")
    return failures


def _confirmation_contract_failures(
    case: ShowcaseCase,
    confirmation: Any,
    *,
    expected_resolution: str,
) -> list[str]:
    if not isinstance(confirmation, dict):
        return ["Expected a correlated confirmation record."]
    expected_kind = (
        "setting_change" if case.confirmation == "approve" else "command_confirmation"
    )
    failures: list[str] = []
    if confirmation.get("required") is not True:
        failures.append("Expected confirmation.required=true.")
    if confirmation.get("kind") != expected_kind:
        failures.append(f"Expected confirmation kind {expected_kind!r}.")
    if confirmation.get("request_id") != f"showcase-{case.case_id}":
        failures.append("Confirmation request id does not match this case.")
    if confirmation.get("command_name") != case.tool_name:
        failures.append("Confirmation command does not match the selected tool.")
    generation = confirmation.get("publication_generation")
    if type(generation) is not int or generation < 0:
        failures.append("Confirmation publication generation is invalid.")
    if confirmation.get("resolution") != expected_resolution:
        failures.append(f"Expected confirmation resolution {expected_resolution!r}.")
    if confirmation.get("correlation_valid") is not True:
        failures.append("Confirmation resolution is not correlated to its request.")
    return failures


def _messages_sha256(messages: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        messages,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git_value(label: str, *args: str) -> str:
    del label
    executable = shutil.which("git")
    if executable is None:
        return "unavailable"
    try:
        return subprocess.run(  # noqa: S603 - fixed read-only Git subcommands
            [executable, *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
