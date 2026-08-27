#!/usr/bin/env python3
"""Evaluate the frozen development corpus through the real controller lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from scripts.dev.assistant_accuracy_case_packs import (
    PINNED_DEVELOPMENT_CASES_SHA256,
    AccuracyExperimentCase,
    AccuracyExperimentTurn,
    load_development_cases,
)
from scripts.dev.run_stable_assistant_model_eval import (
    PrecisionCase,
    _evaluation_generation_policy,
    _EvaluatorControllerSession,
    _precision_application_publication,
    _stable_eval_config,
    target_tool_registry,
)
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.pipeline_stage import PipelineStage
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.llm.agent.assembler import PromptToolPublication
from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus
from XBrainLab.llm.agent.strict_envelope_recovery import (
    DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY,
    StrictEnvelopeRecoveryRequest,
)
from XBrainLab.llm.agent.tool_attempt_coordinator import ToolAttemptAction
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.generation import GenerationProfile
from XBrainLab.llm.core.model_catalog import local_model_spec
from XBrainLab.llm.tools.tool_registry import ToolRegistry

ROOT = Path(__file__).resolve().parents[2]
REPORT_SCHEMA = "xbrainlab.assistant_accuracy_development_eval.v1"
DEFAULT_ARTIFACT_PATH = (
    ROOT / "artifacts" / "assistant_accuracy_development" / "latest.json"
)


@dataclass(frozen=True, slots=True)
class RawPrimaryOutcome:
    """Primary model output before strict-envelope recovery or host composition."""

    response: str
    envelope_status: str
    workflow_stage: str | None
    tool_name: str | None
    parameters: dict[str, Any] | None
    recovery_action: str
    taxonomy: str
    recovery_attempts_after: int


@dataclass(frozen=True, slots=True)
class StrictRecoveryAttempt:
    """One full repair generation after the raw primary model output."""

    attempt_number: int
    response: str
    envelope_status: str
    workflow_stage: str | None
    tool_name: str | None
    parameters: dict[str, Any] | None
    recovery_action: str
    taxonomy: str
    recovery_attempts_after: int


@dataclass(frozen=True, slots=True)
class StrictRecoveryOutcome:
    """Every repair generation controlled by the real controller policy."""

    repair_attempts: tuple[StrictRecoveryAttempt, ...]
    exhausted: bool


@dataclass(frozen=True, slots=True)
class ComposedBoundaryOutcome:
    """Host-composed boundary after parser, receipt, and attempt policy run."""

    passed: bool
    boundary: str | None
    detail: str
    receipt_active: bool
    receipt_pending: bool
    attempt_action: str | None


@dataclass(frozen=True, slots=True)
class ExecutionSafetyOutcome:
    """Observable evaluator guards around one controller terminal boundary."""

    verified_execute_boundary_intercepted: int
    executable_path_guard_calls: int
    tool_executor_guard_calls: int
    application_command_started_signals: int
    confirmation_requested_signals: int
    workflow_handoff_requested_signals: int
    controller_terminal_signals: int
    pending_confirmation: bool
    pending_workflow_handoff: bool
    publication_state_changed: bool

    @property
    def safe_for_non_execution_boundary(self) -> bool:
        return not any(
            (
                self.verified_execute_boundary_intercepted,
                self.executable_path_guard_calls,
                self.tool_executor_guard_calls,
                self.application_command_started_signals,
                self.confirmation_requested_signals,
                self.workflow_handoff_requested_signals,
                self.pending_confirmation,
                self.pending_workflow_handoff,
                self.publication_state_changed,
            )
        )

    @property
    def safe_for_verified_execute_boundary(self) -> bool:
        return bool(
            self.verified_execute_boundary_intercepted == 1
            and self.controller_terminal_signals == 1
            and not any(
                (
                    self.executable_path_guard_calls,
                    self.tool_executor_guard_calls,
                    self.application_command_started_signals,
                    self.confirmation_requested_signals,
                    self.workflow_handoff_requested_signals,
                    self.pending_confirmation,
                    self.pending_workflow_handoff,
                    self.publication_state_changed,
                )
            )
        )


@dataclass(frozen=True, slots=True)
class DevelopmentTurnOutcome:
    expected_boundary: str
    raw_primary: RawPrimaryOutcome
    strict_recovery: StrictRecoveryOutcome
    composed: ComposedBoundaryOutcome
    safety: ExecutionSafetyOutcome
    prompt_context_sha256s: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvaluatorLifecycleOutcome:
    """Terminal proof for the evaluator-owned controller worker."""

    shutdown_signal_count: int
    controller_closed: bool
    worker_cleared: bool
    worker_thread_stopped: bool


@dataclass(frozen=True, slots=True)
class DevelopmentCaseOutcome:
    case_id: str
    turns: tuple[DevelopmentTurnOutcome, ...]
    lifecycle: EvaluatorLifecycleOutcome

    @property
    def passed(self) -> bool:
        return all(turn.composed.passed for turn in self.turns)


def _publication_for_case(
    case: AccuracyExperimentCase,
    *,
    generation: int,
) -> ApplicationViewPublication:
    """Build a real read publication; executable turns are data-loaded only."""
    stage = PipelineStage(case.workflow_stage)
    if stage in {PipelineStage.EMPTY, PipelineStage.DATA_LOADED}:
        baseline = _precision_application_publication(
            PrecisionCase(
                case_id=case.case_id,
                user_input="",
                workflow_stage=stage.value,
                category="general",
                requested_tool=None,
            )
        )
        return replace(baseline, generation=generation)
    state = replace(ApplicationStateSnapshot.empty(), pipeline_stage=stage.value)
    return ApplicationViewPublication(
        generation=generation,
        state=state,
        capabilities=build_capability_policy(state),
    )


def _initial_prompt_publication(
    case: AccuracyExperimentCase,
    publication: ApplicationViewPublication,
) -> PromptToolPublication:
    """Start fail-closed; the session then builds the real current prompt."""
    return PromptToolPublication(
        tool_names=frozenset(),
        workflow_stage=case.workflow_stage,
        backend_generation=publication.generation,
    )


def _recovery_metadata(
    response_text: str,
    *,
    recovery_attempts_used: int,
    observed_decision: Any | None,
) -> tuple[str, str, str, int, str | None, str | None, dict[str, Any] | None]:
    """Record parser and strict-policy evidence without changing controller flow."""
    envelope = CommandParser.parse_product(response_text)
    if observed_decision is None:
        decision = DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY.decide(
            StrictEnvelopeRecoveryRequest(
                envelope=envelope,
                recovery_attempts_used=recovery_attempts_used,
            )
        )
    else:
        decision = observed_decision
    return (
        envelope.status.value,
        decision.action.value,
        decision.taxonomy.value,
        decision.recovery_attempts_after,
        envelope.workflow_stage,
        (
            envelope.commands[0][0]
            if envelope.status is ToolEnvelopeStatus.VALID
            else None
        ),
        (
            envelope.commands[0][1]
            if envelope.status is ToolEnvelopeStatus.VALID
            else None
        ),
    )


def _record_primary(
    response: str,
    *,
    response_text: str,
    recovery_attempts_used: int,
    observed_decision: Any | None,
) -> RawPrimaryOutcome:
    (
        envelope_status,
        recovery_action,
        taxonomy,
        recovery_attempts_after,
        workflow_stage,
        tool_name,
        parameters,
    ) = _recovery_metadata(
        response_text,
        recovery_attempts_used=recovery_attempts_used,
        observed_decision=observed_decision,
    )
    return RawPrimaryOutcome(
        response=response,
        envelope_status=envelope_status,
        workflow_stage=workflow_stage,
        tool_name=tool_name,
        parameters=parameters,
        recovery_action=recovery_action,
        taxonomy=taxonomy,
        recovery_attempts_after=recovery_attempts_after,
    )


def _record_repair(
    attempt_number: int,
    response: str,
    *,
    response_text: str,
    recovery_attempts_used: int,
    observed_decision: Any | None,
) -> StrictRecoveryAttempt:
    (
        envelope_status,
        recovery_action,
        taxonomy,
        recovery_attempts_after,
        workflow_stage,
        tool_name,
        parameters,
    ) = _recovery_metadata(
        response_text,
        recovery_attempts_used=recovery_attempts_used,
        observed_decision=observed_decision,
    )
    return StrictRecoveryAttempt(
        attempt_number=attempt_number,
        response=response,
        envelope_status=envelope_status,
        workflow_stage=workflow_stage,
        tool_name=tool_name,
        parameters=parameters,
        recovery_action=recovery_action,
        taxonomy=taxonomy,
        recovery_attempts_after=recovery_attempts_after,
    )


def _safety_outcome(
    session: _EvaluatorControllerSession,
    *,
    before: tuple[int, int, int, int, int, int, int, str],
) -> ExecutionSafetyOutcome:
    (
        verified_execute_before,
        executable_guard_before,
        tool_executor_guard_before,
        application_started_before,
        confirmation_before,
        handoff_before,
        terminal_before,
        publication_fingerprint,
    ) = before
    return ExecutionSafetyOutcome(
        verified_execute_boundary_intercepted=(
            session.verified_execute_boundary_intercepted - verified_execute_before
        ),
        executable_path_guard_calls=(
            session.executable_path_guard_calls - executable_guard_before
        ),
        tool_executor_guard_calls=(
            session.tool_executor_guard_calls - tool_executor_guard_before
        ),
        application_command_started_signals=(
            session.application_command_started_signals - application_started_before
        ),
        confirmation_requested_signals=(
            session.confirmation_requested_signals - confirmation_before
        ),
        workflow_handoff_requested_signals=(
            session.workflow_handoff_requested_signals - handoff_before
        ),
        controller_terminal_signals=session.turn_terminal_signals - terminal_before,
        pending_confirmation=session.pending_interactions.confirmation is not None,
        pending_workflow_handoff=(
            session.pending_interactions.workflow_handoff is not None
        ),
        publication_state_changed=session.publication_state_changed(
            publication_fingerprint
        ),
    )


def _composed_outcome(
    *,
    turn: AccuracyExperimentTurn,
    session: _EvaluatorControllerSession,
    safety: ExecutionSafetyOutcome,
    execution_calls_before: int,
) -> ComposedBoundaryOutcome:
    pending = session.pending_interactions.tool_input
    active = session.pending_interactions.active_tool_input
    attempt_action = (
        session.last_decision.action.value
        if session.last_decision is not None
        else None
    )
    expected = turn.expected_boundary
    if expected == "respond":
        passed = bool(
            safety.safe_for_non_execution_boundary
            and safety.controller_terminal_signals == 1
            and pending is None
            and active is None
        )
        return ComposedBoundaryOutcome(
            passed,
            "respond" if passed else None,
            "Controller finalized a response-only turn without residual receipt or side effect."
            if passed
            else "Response turn retained a receipt or crossed an unsafe boundary.",
            active is not None,
            pending is not None,
            attempt_action,
        )
    if expected == "typed_receipt":
        receipt = pending
        expected_receipt = turn.receipt
        passed = bool(
            expected_receipt is not None
            and safety.safe_for_non_execution_boundary
            and safety.controller_terminal_signals == 1
            and receipt is not None
            and receipt.command_name == turn.expected_tool
            and _remaining_receipt_inputs(receipt) == expected_receipt.missing_inputs
            and dict(receipt.verified_parameters) == expected_receipt.verified_values
            and active is None
        )
        return ComposedBoundaryOutcome(
            passed,
            "typed_receipt" if passed else None,
            "Controller created the exact typed receipt."
            if passed
            else "Typed receipt mismatch.",
            active is not None,
            pending is not None,
            attempt_action,
        )
    if expected == "verified_execute":
        decisions = session.execute_decisions[execution_calls_before:]
        decision = decisions[-1] if len(decisions) == 1 else None
        passed = bool(
            decision is not None
            and decision.action is ToolAttemptAction.EXECUTE
            and decision.command_name == turn.expected_tool
            and decision.params == turn.expected_parameters
            and safety.safe_for_verified_execute_boundary
            and active is None
            and pending is None
        )
        return ComposedBoundaryOutcome(
            passed,
            "verified_execute" if passed else None,
            "Non-mutating sentinel observed the exact verified execution boundary."
            if passed
            else "Controller did not reach the exact safe execution sentinel.",
            active is not None,
            pending is not None,
            attempt_action,
        )
    raise ValueError(f"Unsupported development boundary: {expected}")


def _remaining_receipt_inputs(receipt: Any) -> tuple[str, ...]:
    """Project a product receipt's unverified fields without changing it."""
    verified = dict(receipt.verified_parameters)
    return tuple(name for name in receipt.missing_inputs if name not in verified)


def _drive_turn(
    *,
    case: AccuracyExperimentCase,
    turn: AccuracyExperimentTurn,
    publication: ApplicationViewPublication,
    session: _EvaluatorControllerSession,
    generate_response,
) -> DevelopmentTurnOutcome:
    session.set_publication(publication)
    session.begin_turn(
        turn.user_input,
        _initial_prompt_publication(case, publication),
    )
    messages = session.model_messages()
    prompt_hashes: list[str] = []
    raw_primary: RawPrimaryOutcome | None = None
    repair_attempts: list[StrictRecoveryAttempt] = []
    execution_calls_before = len(session.execute_decisions)
    safety_before = session.safety_snapshot()

    while True:
        prompt_hashes.append(
            hashlib.sha256(
                json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
        )
        response = generate_response(messages)
        if type(response) is not str:
            raise TypeError("Model generation must return one exact string.")
        response_text = response.strip()
        retry_count = session.controller._tool_attempt_session.retry_count
        recovery_observation_start = len(session.strict_recovery_decisions)
        session.complete_response(response_text)
        observed = session.strict_recovery_decisions[recovery_observation_start:]
        if len(observed) > 1:
            raise RuntimeError(
                "One generated response produced multiple recovery decisions."
            )
        observed_decision = observed[0].decision if observed else None
        if raw_primary is None:
            raw_primary = _record_primary(
                response,
                response_text=response_text,
                recovery_attempts_used=retry_count,
                observed_decision=observed_decision,
            )
        else:
            repair_attempts.append(
                _record_repair(
                    len(repair_attempts) + 2,
                    response,
                    response_text=response_text,
                    recovery_attempts_used=retry_count,
                    observed_decision=observed_decision,
                )
            )
        if session.controller._tool_attempt_session.retry_count > retry_count:
            messages = session.model_messages()
            continue
        break

    safety = _safety_outcome(
        session,
        before=safety_before,
    )
    composed = _composed_outcome(
        turn=turn,
        session=session,
        safety=safety,
        execution_calls_before=execution_calls_before,
    )
    return DevelopmentTurnOutcome(
        expected_boundary=turn.expected_boundary,
        raw_primary=raw_primary,
        strict_recovery=StrictRecoveryOutcome(
            repair_attempts=tuple(repair_attempts),
            exhausted=bool(
                raw_primary.recovery_action == "exhausted"
                or any(
                    attempt.recovery_action == "exhausted"
                    for attempt in repair_attempts
                )
            ),
        ),
        composed=composed,
        safety=safety,
        prompt_context_sha256s=tuple(prompt_hashes),
    )


def evaluate_development_case(
    case: AccuracyExperimentCase,
    registry: ToolRegistry,
    generate_response,
) -> DevelopmentCaseOutcome:
    """Consume one already-loaded development case through product lifecycle code."""
    generation = 1
    session = _EvaluatorControllerSession(
        registry=registry,
        publication=_publication_for_case(case, generation=generation),
    )
    turns: list[DevelopmentTurnOutcome] = []
    try:
        for turn in case.turns:
            if turn.publication_generation_advanced_before_turn:
                generation += 1
            turns.append(
                _drive_turn(
                    case=case,
                    turn=turn,
                    publication=_publication_for_case(case, generation=generation),
                    session=session,
                    generate_response=generate_response,
                )
            )
    finally:
        session.close()
    return DevelopmentCaseOutcome(
        case.case_id,
        tuple(turns),
        EvaluatorLifecycleOutcome(
            shutdown_signal_count=len(session.shutdown_terminals),
            controller_closed=session.shutdown_completed,
            worker_cleared=session.worker_cleared,
            worker_thread_stopped=session.worker_thread_stopped,
        ),
    )


def development_experiment_identity(
    *,
    model_id: str,
    generation_policy: dict[str, Any],
    selected_case_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Bind an artifact without reading or hashing any separately held corpus."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git is required to bind evaluator source identity.")
    source_sha = subprocess.check_output(  # noqa: S603 - fixed Git executable/argv
        [git, "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    status = subprocess.check_output(  # noqa: S603 - fixed Git executable/argv
        [git, "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    source_changes = [row for row in status if row[3:].strip() not in {"settings.json"}]

    def digest(relative_path: str) -> str:
        return hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()

    selected_ids = tuple(selected_case_ids or ())
    selected_ids_digest = hashlib.sha256(
        json.dumps(selected_ids, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    spec = local_model_spec(model_id)
    return {
        "source_sha": source_sha,
        "source_changes_excluding_protected_settings": source_changes,
        "source_is_clean_excluding_protected_settings": not source_changes,
        "model": {
            "id": model_id,
            "revision": spec.revision if spec is not None else None,
        },
        "generation_policy": generation_policy,
        "development_cases_sha256": PINNED_DEVELOPMENT_CASES_SHA256,
        "selected_case_ids": list(selected_ids),
        "selected_case_ids_sha256": selected_ids_digest,
        "prompt_policy_sha256": digest("XBrainLab/llm/agent/prompt_policy.py"),
        "context_assembler_sha256": digest("XBrainLab/llm/agent/assembler.py"),
        "parser_sha256": digest("XBrainLab/llm/agent/parser.py"),
        "strict_recovery_policy_sha256": digest(
            "XBrainLab/llm/agent/strict_envelope_recovery.py"
        ),
        "verification_layer_sha256": digest("XBrainLab/llm/agent/verifier.py"),
        "tool_attempt_coordinator_sha256": digest(
            "XBrainLab/llm/agent/tool_attempt_coordinator.py"
        ),
        "pending_interaction_coordinator_sha256": digest(
            "XBrainLab/llm/agent/pending_interaction.py"
        ),
        "application_view_publication_sha256": digest(
            "XBrainLab/backend/application/view_publication.py"
        ),
        "capability_policy_sha256": digest(
            "XBrainLab/backend/application/capabilities.py"
        ),
        "case_loader_sha256": digest("scripts/dev/assistant_accuracy_case_packs.py"),
        "scorer_sha256": digest(
            "scripts/dev/run_assistant_accuracy_development_eval.py"
        ),
        "product_runner_sha256": digest(
            "scripts/dev/run_stable_assistant_model_eval.py"
        ),
        "controller_sha256": digest("XBrainLab/llm/agent/controller.py"),
        "tool_registry_sha256": digest("XBrainLab/llm/tools/tool_registry.py"),
        "tool_contract_sha256": digest("XBrainLab/llm/action_contracts.py"),
    }


def build_development_report(
    *,
    model_id: str,
    generation_policy: dict[str, Any],
    outcomes: tuple[DevelopmentCaseOutcome, ...],
    complete: bool,
    selected_case_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Render raw, recovery, and composed evidence as distinct report fields."""
    turns = [turn for outcome in outcomes for turn in outcome.turns]
    return {
        "schema_version": REPORT_SCHEMA,
        "complete": complete,
        "experiment_identity": development_experiment_identity(
            model_id=model_id,
            generation_policy=generation_policy,
            selected_case_ids=selected_case_ids,
        ),
        "summary": {
            "case_count": len(outcomes),
            "turn_count": len(turns),
            "raw_primary_valid_count": sum(
                turn.raw_primary.envelope_status
                != ToolEnvelopeStatus.FORMAT_ERROR.value
                for turn in turns
            ),
            "strict_recovery_passed_count": sum(
                not turn.strict_recovery.exhausted for turn in turns
            ),
            "composed_passed_count": sum(turn.composed.passed for turn in turns),
            "passed": bool(
                complete and turns and all(turn.composed.passed for turn in turns)
            ),
        },
        "results": [asdict(outcome) for outcome in outcomes],
        "claim_boundary": (
            "This development-only run records product parser, recovery, receipt, "
            "and verified-boundary behavior. It does not establish holdout accuracy, "
            "EEG workflow success, clinical validity, product readiness, or local-model "
            "accuracy without the frozen protocol and scorer audit."
        ),
    }


def _write_development_report(path: Path, report: dict[str, Any]) -> None:
    """Persist full raw model text only in the ignored development artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temp_path = Path(temporary.name)
            temporary.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temp_path, path)
    except BaseException:
        if temp_path is not None:
            with suppress(OSError):
                temp_path.unlink(missing_ok=True)
        raise


def _select_development_cases(
    cases: tuple[AccuracyExperimentCase, ...],
    selected_case_ids: tuple[str, ...],
) -> tuple[AccuracyExperimentCase, ...]:
    """Select an ordered, unique development-only subset or fail closed."""
    if not selected_case_ids:
        return cases
    if any(not case_id.strip() for case_id in selected_case_ids):
        raise ValueError("Development case IDs must be non-empty.")
    if len(set(selected_case_ids)) != len(selected_case_ids):
        raise ValueError("Development case IDs must not repeat.")
    by_id = {case.case_id: case for case in cases}
    missing = [case_id for case_id in selected_case_ids if case_id not in by_id]
    if missing:
        raise ValueError(f"Unknown development case ID: {missing[0]}")
    return tuple(by_id[case_id] for case_id in selected_case_ids)


def run_development_eval(
    config: LLMConfig,
    *,
    checkpoint_path: Path = DEFAULT_ARTIFACT_PATH,
    selected_case_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Run one configured local engine across the development loader only."""
    selection = config.assistant_runtime_selection()
    if selection.backend_mode != "local":
        raise RuntimeError(f"Current assistant backend is {selection.backend_mode}.")
    if not config.local_backend_ready(selection.model_id):
        raise RuntimeError(config.local_backend_status_message(selection.model_id))
    all_cases = load_development_cases()
    if len(all_cases) != 48:
        raise RuntimeError("Development evaluator requires the frozen 48-case pack.")
    cases = _select_development_cases(all_cases, selected_case_ids)
    selected_ids = tuple(case.case_id for case in cases)
    registry = target_tool_registry()
    generation_policy = _evaluation_generation_policy(config)
    engine = LLMEngine(config)
    outcomes: list[DevelopmentCaseOutcome] = []
    try:
        engine.load_model()
        for index, case in enumerate(cases, start=1):
            print(
                f"Assistant development eval {index}/{len(cases)}: {case.case_id}",
                file=sys.stderr,
                flush=True,
            )
            outcomes.append(
                evaluate_development_case(
                    case,
                    registry,
                    lambda messages: "".join(
                        engine.generate_stream(
                            messages,
                            profile=GenerationProfile.STRUCTURED_DECISION,
                        )
                    ),
                )
            )
            _write_development_report(
                checkpoint_path,
                build_development_report(
                    model_id=selection.model_id,
                    generation_policy=generation_policy,
                    outcomes=tuple(outcomes),
                    complete=False,
                    selected_case_ids=selected_ids,
                ),
            )
    except Exception as exc:
        partial_report = build_development_report(
            model_id=selection.model_id,
            generation_policy=generation_policy,
            outcomes=tuple(outcomes),
            complete=False,
            selected_case_ids=selected_ids,
        )
        partial_report["failure"] = f"{type(exc).__name__}: {exc}"
        _write_development_report(checkpoint_path, partial_report)
        raise
    finally:
        engine.close()
    report = build_development_report(
        model_id=selection.model_id,
        generation_policy=generation_policy,
        outcomes=tuple(outcomes),
        complete=True,
        selected_case_ids=selected_ids,
    )
    _write_development_report(checkpoint_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", type=Path, default=DEFAULT_ARTIFACT_PATH)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args(argv)
    config = _stable_eval_config(LLMConfig.load_from_file(), device=args.device)
    try:
        report = run_development_eval(
            config,
            checkpoint_path=args.json_out,
            selected_case_ids=tuple(args.case_id),
        )
    except Exception as exc:
        report = {
            "schema_version": REPORT_SCHEMA,
            "complete": False,
            "summary": {"passed": False, "case_count": 0},
            "failure": f"{type(exc).__name__}: {exc}",
        }
    print(
        json.dumps(
            {
                "schema_version": REPORT_SCHEMA,
                "summary": report["summary"],
                "report_path": str(args.json_out),
            },
            ensure_ascii=False,
        )
    )
    return 0 if not args.strict or report["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
