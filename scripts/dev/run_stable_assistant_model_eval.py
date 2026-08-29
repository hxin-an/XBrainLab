#!/usr/bin/env python3
"""Run the bounded Stable-v2 target selection suite against the local model."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.pipeline_stage import PipelineStage
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
    DatasetSplitLifecycle,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.assembler import ContextAssembler, PromptToolPublication
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.parser import (
    CommandParser,
    ToolEnvelopeParseResult,
    ToolEnvelopeStatus,
)
from XBrainLab.llm.agent.pending_interaction import PendingInteractionCoordinator
from XBrainLab.llm.agent.strict_envelope_recovery import (
    DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY,
    STRICT_ENVELOPE_EXHAUSTED_MESSAGE,
    STRICT_ENVELOPE_MULTIPLE_OBJECTS_MESSAGE,
    StrictEnvelopeRecoveryAction,
    StrictEnvelopeRecoveryRequest,
)
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ToolAttemptAction,
    ToolAttemptCoordinator,
    ToolAttemptDecision,
    ToolAttemptRequest,
)
from XBrainLab.llm.agent.tool_feedback import summarize_tool_result
from XBrainLab.llm.agent.turn import AssistantToolInputReceipt
from XBrainLab.llm.agent.turn_orchestrator import (
    AssistantToolAttemptSession,
    AssistantTurnOrchestrator,
)
from XBrainLab.llm.agent.verifier import (
    ToolSchemaValidator,
    VerificationLayer,
    verify_direct_parameter_origins,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.generation import (
    GenerationProfile,
    resolve_generation_options,
)
from XBrainLab.llm.core.model_catalog import local_model_spec
from XBrainLab.llm.pipeline_state import STAGE_CONFIG
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
    build_agent_tool_policy,
)
from XBrainLab.llm.tools.tool_registry import ToolRegistry

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT / "scripts" / "dev" / "stable_assistant_positive_cases.json"
DEFAULT_CHALLENGES = ROOT / "scripts" / "dev" / "stable_assistant_challenge_cases.json"
DEFAULT_PRECISION_CASES = (
    ROOT / "scripts" / "dev" / "stable_assistant_no_action_precision_cases.json"
)
DEFAULT_CLARIFICATION_CASES = (
    ROOT / "scripts" / "dev" / "stable_assistant_clarification_cases.json"
)
REPORT_SCHEMA = "xbrainlab.stable_assistant_model_eval.v11"
PRECISION_CASE_COUNT = 24
CLARIFICATION_CASE_COUNT = 7
RAW_OUTPUT_PREVIEW_CHAR_LIMIT = 1_000
_PROMPT_CAPTURE_DIRECTORY_ENV = "XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR"
_CAPTURE_FILE_NAMES = ("prompt.txt", "raw-output.txt", "metadata.json")
MISSING_PARAMETER_HOST_TOOLS = {
    "missing_bandpass_bounds_01": "apply_bandpass_filter",
    "missing_notch_frequency_01": "apply_notch_filter",
    "missing_resample_rate_01": "resample_data",
    "missing_reference_method_01": "set_reference",
    "missing_normalization_method_01": "normalize_data",
}
DIRECT_PARAMETER_TOOLS = frozenset(MISSING_PARAMETER_HOST_TOOLS.values())
_MISSING_PARAMETER_CONCEPTS = {
    "apply_bandpass_filter": (("bandpass",), ("low", "lower"), ("high", "upper")),
    "apply_notch_filter": (("notch",), ("frequency", "freq", "hz")),
    "resample_data": (("resample",), ("rate", "hz")),
    "set_reference": (("reference",), ("method", "average")),
    "normalize_data": (
        ("normalize", "normalization"),
        ("method", "z-score", "min-max"),
    ),
}


@dataclass(frozen=True, slots=True)
class TargetEvalCase:
    """One approved target selection example with a derived backend stage."""

    case_id: str
    user_input: str
    workflow_stage: str
    expected_tool: str
    expected_parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TargetChallengeCase:
    """One no-execution challenge against the same strict product envelope."""

    case_id: str
    user_input: str
    workflow_stage: str
    category: str
    required_concepts: tuple[tuple[str, ...], ...]
    forbidden_concepts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrecisionCase:
    """One English no-action outcome case against the product boundary."""

    case_id: str
    user_input: str
    workflow_stage: str
    category: str
    requested_tool: str | None


@dataclass(frozen=True, slots=True)
class ClarificationCase:
    """One second-turn answer bound to a missing-parameter precision case."""

    case_id: str
    expected_tool: str
    expected_parameters: dict[str, Any]
    source_case_id: str = ""
    reply: str = ""
    trajectory_kind: str = "direct"
    turns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PrecisionProductOutcome:
    """Product admission and presentation outcome for one precision response."""

    disposition: str
    message: str | None
    confirmation_requested: bool = False
    gui_handoff_permitted: bool = False
    application_service_permitted: bool = False
    tool_executor_permitted: bool = False
    state_mutation_permitted: bool = False


@dataclass(frozen=True, slots=True)
class TargetEvalScore:
    """Fail-closed score for one raw model response."""

    passed: bool
    failure_type: str
    response: str
    parsed_stage: str | None
    parsed_tool: str | None
    parsed_parameters: dict[str, Any] | None
    detail: str
    product_outcome: PrecisionProductOutcome | None = None


@dataclass(frozen=True, slots=True)
class ModelGenerationAttempt:
    """One policy classification; its preview is never raw-output identity evidence."""

    attempt_number: int
    response_preview: str
    envelope_status: str
    workflow_stage: str | None
    recovery_action: str
    taxonomy: str
    recovery_attempts_after: int


@dataclass(frozen=True, slots=True)
class GenerationTraceEntry:
    """One exact raw model output identity recorded by the evaluator runner."""

    global_call_index: int
    case_id: str
    turn_purpose: str
    raw_output_bytes: int
    raw_output_sha256: str
    raw_output_preview: str


@dataclass(frozen=True, slots=True)
class _CaptureAuditRequest:
    """One opt-in capture root snapshot made before the evaluator loads a model."""

    requested: bool
    root: Path | None
    prior_session_names: frozenset[str] = frozenset()
    failure_code: str | None = None


@dataclass(slots=True)
class GenerationTraceRecorder:
    """Record each evaluator generation before scoring normalizes its output."""

    entries: list[GenerationTraceEntry] = field(default_factory=list)

    def record(
        self,
        raw_output: str,
        *,
        case_id: str,
        turn_purpose: str,
    ) -> None:
        if type(raw_output) is not str:
            raise TypeError("Model generation must return one exact string.")
        raw_bytes = raw_output.encode("utf-8")
        self.entries.append(
            GenerationTraceEntry(
                global_call_index=len(self.entries) + 1,
                case_id=case_id,
                turn_purpose=turn_purpose,
                raw_output_bytes=len(raw_bytes),
                raw_output_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                raw_output_preview=raw_output[:RAW_OUTPUT_PREVIEW_CHAR_LIMIT],
            )
        )


@dataclass(frozen=True, slots=True)
class CaseTrajectoryResult:
    """First-generation, post-recovery, and product scores for one trajectory."""

    # This is the first model output, before any Host-issued recovery message.
    raw_score: TargetEvalScore
    # Diagnostic only: a later model output after format recovery, if any.
    post_recovery_score: TargetEvalScore
    final_score: TargetEvalScore
    final_response: str
    attempts: tuple[ModelGenerationAttempt, ...]
    receipt_origin: str | None = None
    # First-turn evaluator rows carry controller-observed evidence separately
    # from raw and semantic scores. Clarification trajectories already expose
    # their own pending-receipt trace and therefore leave these unset.
    host_admission: dict[str, Any] | None = None
    product_terminal: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ClarificationAdmission:
    """One controller-admitted typed receipt retained for evaluator follow-up."""

    receipt: AssistantToolInputReceipt
    receipt_origin: str
    harness: _EvaluatorControllerHarness
    prompt_publication: PromptToolPublication
    backend_publication: ApplicationViewPublication


def target_tool_registry() -> ToolRegistry:
    """Build the exact approved target registry used by the product runtime."""
    registry = ToolRegistry()
    tools = get_all_tools("mock")
    AGENT_ACTION_CONTRACTS.validate_registered_tool_names([tool.name for tool in tools])
    for tool in tools:
        registry.register(tool)
    return registry


def _first_stage_for_tool(tool_name: str) -> PipelineStage:
    # The historic 36-case catalog predates capability-filtered publication.
    # Starting a run needs a saved split, model, and training settings, which
    # truthfully places the product in dataset_ready rather than epoch_ready.
    # Keep the two-per-tool corpus count but evaluate that action at the first
    # production state where its command is actually published.
    if tool_name == "start_training":
        return PipelineStage.DATASET_READY
    for stage, config in STAGE_CONFIG.items():
        if tool_name in config["tools"]:
            return stage
    raise ValueError(f"Target tool has no backend stage publication: {tool_name}")


def load_target_cases(path: Path = DEFAULT_CASES) -> tuple[TargetEvalCase, ...]:
    """Load active English target examples and reject catalog drift."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load target model eval cases: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("Target model eval cases must be one JSON array.")

    approved = AGENT_ACTION_CONTRACTS.model_tool_names()
    cases: list[TargetEvalCase] = []
    seen_ids: set[str] = set()
    seen_normalized_inputs: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("Each target model eval case must be one object.")
        case_id = row.get("id")
        user_input = row.get("input")
        calls = row.get("expected_tool_calls")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError(f"Invalid or duplicate target case id: {case_id!r}")
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError(f"Target case {case_id} lacks a user input.")
        normalized_input = user_input.strip().casefold()
        if normalized_input in seen_normalized_inputs:
            raise ValueError(
                f"Target case {case_id} duplicates a normalized user input."
            )
        if not isinstance(calls, list) or len(calls) != 1:
            raise ValueError(f"Target case {case_id} must expect exactly one tool.")
        call = calls[0]
        if not isinstance(call, dict) or set(call) != {"tool_name", "parameters"}:
            raise ValueError(f"Target case {case_id} has an invalid expected call.")
        tool_name = call["tool_name"]
        parameters = call["parameters"]
        if tool_name not in approved or not isinstance(parameters, dict):
            raise ValueError(f"Target case {case_id} references a non-target tool.")
        stage = _first_stage_for_tool(tool_name)
        cases.append(
            TargetEvalCase(
                case_id=case_id,
                user_input=user_input.strip(),
                workflow_stage=stage.value,
                expected_tool=tool_name,
                expected_parameters=parameters,
            )
        )
        seen_ids.add(case_id)
        seen_normalized_inputs.add(normalized_input)

    counts = {
        tool_name: sum(case.expected_tool == tool_name for case in cases)
        for tool_name in approved
    }
    if set(counts.values()) != {2}:
        raise ValueError(
            "Target model eval must contain exactly two cases per approved tool."
        )
    return tuple(cases)


def load_challenge_cases(
    path: Path = DEFAULT_CHALLENGES,
) -> tuple[TargetChallengeCase, ...]:
    """Load frozen no-execution cases without changing the RAG gold set."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load target challenge cases: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("Target challenge cases must be one JSON array.")

    allowed_categories = {
        "ambiguous",
        "general",
        "missing_parameter",
        "multi_action",
        "out_of_stage",
    }
    cases: list[TargetChallengeCase] = []
    seen_ids: set[str] = set()
    for row in payload:
        required_keys = {
            "id",
            "category",
            "input",
            "workflow_stage",
            "required_concepts",
        }
        if (
            not isinstance(row, dict)
            or not required_keys.issubset(row)
            or set(row).difference(required_keys | {"forbidden_concepts"})
        ):
            raise ValueError("Each target challenge case must use the exact schema.")
        case_id = row["id"]
        category = row["category"]
        user_input = row["input"]
        workflow_stage = row["workflow_stage"]
        concepts = row["required_concepts"]
        forbidden = row.get("forbidden_concepts", [])
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError(f"Invalid or duplicate challenge case id: {case_id!r}")
        if category not in allowed_categories:
            raise ValueError(f"Challenge case {case_id} has an invalid category.")
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError(f"Challenge case {case_id} lacks a user input.")
        try:
            PipelineStage(workflow_stage)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Challenge case {case_id} has an invalid workflow stage."
            ) from exc
        if not isinstance(concepts, list) or any(
            not isinstance(group, list)
            or not group
            or any(not isinstance(term, str) or not term for term in group)
            for group in concepts
        ):
            raise ValueError(f"Challenge case {case_id} has invalid required concepts.")
        if not isinstance(forbidden, list) or any(
            not isinstance(term, str) or not term for term in forbidden
        ):
            raise ValueError(
                f"Challenge case {case_id} has invalid forbidden concepts."
            )
        cases.append(
            TargetChallengeCase(
                case_id=case_id,
                user_input=user_input.strip(),
                workflow_stage=workflow_stage,
                category=category,
                required_concepts=tuple(
                    tuple(term for term in group) for group in concepts
                ),
                forbidden_concepts=tuple(forbidden),
            )
        )
        seen_ids.add(case_id)

    if len(cases) != 14:
        raise ValueError("Target challenge suite must contain exactly 14 cases.")
    return tuple(cases)


def load_precision_cases(
    path: Path = DEFAULT_PRECISION_CASES,
) -> tuple[PrecisionCase, ...]:
    """Load the separately versioned English no-action precision corpus."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load precision cases: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("Precision cases must be one JSON array.")

    allowed_categories = {
        "ambiguous",
        "general",
        "missing_parameter",
        "multi_action",
        "negated",
        "out_of_stage",
    }
    cases: list[PrecisionCase] = []
    seen_ids: set[str] = set()
    for row in payload:
        required = {"id", "category", "input", "workflow_stage"}
        if (
            not isinstance(row, dict)
            or not required.issubset(row)
            or set(row).difference(required | {"requested_tool"})
        ):
            raise ValueError("Each precision case must use the exact schema.")
        case_id = row["id"]
        category = row["category"]
        user_input = row["input"]
        workflow_stage = row["workflow_stage"]
        requested_tool = row.get("requested_tool")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError(f"Invalid or duplicate precision case id: {case_id!r}")
        if category not in allowed_categories:
            raise ValueError(f"Precision case {case_id} has an invalid category.")
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError(f"Precision case {case_id} lacks a user input.")
        try:
            PipelineStage(workflow_stage)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Precision case {case_id} has an invalid workflow stage."
            ) from exc
        if requested_tool is not None and (
            not isinstance(requested_tool, str)
            or requested_tool not in AGENT_ACTION_CONTRACTS.model_tool_names()
        ):
            raise ValueError(f"Precision case {case_id} has an invalid requested tool.")
        cases.append(
            PrecisionCase(
                case_id=case_id,
                user_input=user_input.strip(),
                workflow_stage=workflow_stage,
                category=category,
                requested_tool=requested_tool,
            )
        )
        seen_ids.add(case_id)

    if len(cases) != PRECISION_CASE_COUNT:
        raise ValueError(
            f"Precision suite must contain exactly {PRECISION_CASE_COUNT} cases."
        )
    requested_cases = [case for case in cases if case.requested_tool is not None]
    requested = {case.requested_tool for case in requested_cases}
    if (
        len(requested_cases) != len(AGENT_ACTION_CONTRACTS.model_tool_names())
        or requested != AGENT_ACTION_CONTRACTS.model_tool_names()
    ):
        raise ValueError("Precision suite must cover every approved model tool once.")
    for category in ("general", "ambiguous", "multi_action"):
        category_cases = [case for case in cases if case.category == category]
        if len(category_cases) != 2:
            raise ValueError(f"Precision suite must contain two {category} cases.")
        if {case.case_id.rsplit("_", 1)[-1] for case in category_cases} != {
            "en",
            "alt",
        }:
            raise ValueError(
                f"Precision {category} cases must provide two English variants."
            )
    if any(
        (case.category in {"general", "ambiguous", "multi_action"})
        != (case.requested_tool is None)
        for case in cases
    ):
        raise ValueError(
            "Only general, ambiguous, and multi-action cases may omit requested_tool."
        )
    return tuple(cases)


def load_clarification_cases(
    path: Path = DEFAULT_CLARIFICATION_CASES,
    *,
    precision_cases: tuple[PrecisionCase, ...],
) -> tuple[ClarificationCase, ...]:
    """Load five direct and two discriminated clarification trajectories."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load clarification cases: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("Clarification cases must be one JSON array.")

    sources = {
        case.case_id: case
        for case in precision_cases
        if case.category == "missing_parameter"
    }
    cases: list[ClarificationCase] = []
    seen_ids: set[str] = set()
    seen_sources: set[str] = set()
    for row in payload:
        direct_required = {
            "id",
            "source_case_id",
            "reply",
            "expected_tool",
            "expected_parameters",
        }
        trajectory_required = {
            "id",
            "trajectory_kind",
            "workflow_stage",
            "turns",
            "expected_tool",
            "expected_parameters",
        }
        if not isinstance(row, dict) or set(row) not in {
            frozenset(direct_required),
            frozenset(trajectory_required),
        }:
            raise ValueError(
                "Each clarification case must use a supported strict schema."
            )
        if set(row) == trajectory_required:
            case_id = row["id"]
            kind = row["trajectory_kind"]
            workflow_stage = row["workflow_stage"]
            turns = row["turns"]
            expected_tool = row["expected_tool"]
            expected_parameters = row["expected_parameters"]
            if (
                not isinstance(case_id, str)
                or case_id in seen_ids
                or kind
                not in {"generic_filter_selection", "partial_bandpass_accumulation"}
                or workflow_stage != "data_loaded"
                or not isinstance(turns, list)
                or not all(isinstance(turn, str) and turn.strip() for turn in turns)
                or len(turns) != 3
                or expected_tool != "apply_bandpass_filter"
                or not isinstance(expected_parameters, dict)
            ):
                raise ValueError(f"Invalid clarification trajectory: {case_id!r}")
            cases.append(
                ClarificationCase(
                    case_id=case_id,
                    expected_tool=expected_tool,
                    expected_parameters=expected_parameters,
                    trajectory_kind=kind,
                    turns=tuple(turn.strip() for turn in turns),
                )
            )
            seen_ids.add(case_id)
            continue
        case_id = row["id"]
        source_case_id = row["source_case_id"]
        reply = row["reply"]
        expected_tool = row["expected_tool"]
        expected_parameters = row["expected_parameters"]
        source = sources.get(source_case_id)
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError(f"Invalid or duplicate clarification id: {case_id!r}")
        if source is None or source_case_id in seen_sources:
            raise ValueError(
                f"Clarification {case_id} must reference one unique missing case."
            )
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError(f"Clarification {case_id} lacks a reply.")
        if (
            not isinstance(expected_tool, str)
            or expected_tool != source.requested_tool
            or expected_tool not in DIRECT_PARAMETER_TOOLS
            or not isinstance(expected_parameters, dict)
        ):
            raise ValueError(f"Clarification {case_id} has an invalid expected call.")
        cases.append(
            ClarificationCase(
                case_id=case_id,
                source_case_id=source_case_id,
                reply=reply.strip(),
                expected_tool=expected_tool,
                expected_parameters=expected_parameters,
            )
        )
        seen_ids.add(case_id)
        seen_sources.add(source_case_id)

    expected_trajectory_kinds = {
        "generic_filter_selection",
        "partial_bandpass_accumulation",
    }
    if (
        len(cases) != CLARIFICATION_CASE_COUNT
        or seen_sources != set(sources)
        or {case.trajectory_kind for case in cases if case.trajectory_kind != "direct"}
        != expected_trajectory_kinds
    ):
        raise ValueError(
            "Clarification suite must cover five direct and two trajectories."
        )
    return tuple(cases)


@dataclass(frozen=True, slots=True)
class _EvaluatorApplicationRuntime:
    """Read one immutable evaluator publication without a second state source."""

    publication: ApplicationViewPublication

    def get_view_publication(self) -> ApplicationViewPublication:
        return self.publication


class _PublicationBackedEvaluatorStudy(Study):
    """Type marker that makes stage projection consume the explicit publication."""

    def __init__(self) -> None:
        pass


class _EvaluatorSignal:
    """Minimal signal recorder for controller presentation calls without Qt."""

    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    def emit(self, *args: Any) -> None:
        self.events.append(args)


class _EvaluatorMetrics:
    """Keep controller terminal methods callable without collecting runtime metrics."""

    def finish_turn(self) -> None:
        return None


class _EvaluatorControllerHarness:
    """Minimal evaluator adapter that invokes the controller's existing policy.

    It owns no policy: every admission, proposal selection, and continuation
    transition below is an unbound ``LLMController`` method.  The harness only
    supplies deterministic evaluator fixtures in place of Qt/RAG execution.
    """

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        publication: ApplicationViewPublication,
    ) -> None:
        self.registry = registry
        self._turn_orchestrator = AssistantTurnOrchestrator()
        self._turn_orchestrator.active_publication = PromptToolPublication.empty()
        self._tool_attempt_session = AssistantToolAttemptSession()
        self._strict_envelope_recovery_policy = DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY
        self._max_tool_executions = 5
        self._pending_interactions = PendingInteractionCoordinator()
        self._history: list[dict[str, str]] = []
        self.presentations: list[str] = []
        self.metrics = _EvaluatorMetrics()
        self.status_update = _EvaluatorSignal()
        self.activity_changed = _EvaluatorSignal()
        self.response_presentation_ready = _EvaluatorSignal()
        self.confirmation_requested = _EvaluatorSignal()
        self.processing_finished = _EvaluatorSignal()
        self.is_processing = True
        self._observed_decision: ToolAttemptDecision | None = None
        self._observed_terminal: dict[str, Any] | None = None
        self.current_response = ""
        self._recovery_generation_requested = False
        self._recovery_context: str | None = None
        self._publication = publication
        runtime = _EvaluatorApplicationRuntime(publication)
        self.assembler = ContextAssembler(
            registry,
            _PublicationBackedEvaluatorStudy(),
            application_runtime=runtime,
        )
        self._tool_attempt_coordinator = _precision_attempt_coordinator(
            registry,
            publication=publication,
        )

    @property
    def pending_interactions(self) -> PendingInteractionCoordinator:
        return self._pending_interactions

    @property
    def history(self) -> list[dict[str, str]]:
        return self._history

    def _append_history(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})

    def _publish_response(self, text: str, **_kwargs: Any) -> None:
        """Record a trusted controller presentation without creating a Qt event."""
        self.presentations.append(text)

    def _publish_activity(self, *_args: Any, **_kwargs: Any) -> None:
        """The evaluator intentionally has no activity presentation surface."""

    def _emit_processing_finished(self, _outcome: str = "completed") -> None:
        self.pending_interactions.clear_active_tool_input()

    def _finalize_turn(self, response_text: str) -> None:
        LLMController._finalize_turn(self, response_text)  # type: ignore[arg-type]
        self._record_terminal("respond")

    def _arbitrate_generation_terminal(self, generation_id: int, _phase: Any) -> bool:
        """Keep controller generation correlation without a Qt event surface."""
        return self._turn_orchestrator.accept_generation_terminal(
            generation_id,
            _phase,
        )

    def _generate_response(self) -> bool:
        """Record a controller-requested retry; the evaluator owns model I/O."""
        if not self.assembler.context_notes:
            raise RuntimeError(
                "Controller format retry did not publish recovery context."
            )
        self._recovery_generation_requested = True
        self._recovery_context = self.assembler.context_notes[-1]
        return True

    def _handle_tool_envelope_failure(
        self,
        response_text: str,
        envelope: ToolEnvelopeParseResult,
    ) -> bool:
        return LLMController._handle_tool_envelope_failure(  # type: ignore[arg-type]
            self,
            response_text,
            envelope,
        )

    def _begin_typed_tool_input(self, envelope: ToolEnvelopeParseResult) -> bool:
        return LLMController._begin_typed_tool_input(self, envelope)  # type: ignore[arg-type]

    def _process_tool_calls(self, command_result: Any, response_text: str) -> None:
        LLMController._process_tool_calls(self, command_result, response_text)  # type: ignore[arg-type]

    def replay_controller_generation(
        self,
        response: str,
    ) -> tuple[StrictEnvelopeRecoveryAction | None, str | None]:
        """Drive one evaluator output through the product controller path."""
        self._observed_decision = None
        self._observed_terminal = None
        self._recovery_generation_requested = False
        self._recovery_context = None
        self.current_response = response
        # The evaluator has already admitted this model dispatch after the
        # user-authored clarification reply; model completion is processing.
        self.is_processing = True
        generation_id = self._turn_orchestrator.begin_generation()
        LLMController._on_generation_finished(self, generation_id, [])  # type: ignore[arg-type]
        if self._recovery_generation_requested:
            return StrictEnvelopeRecoveryAction.RETRY_FORMAT, self._recovery_context
        if not self.is_processing and self._observed_terminal is None:
            self._record_terminal("format_recovery_exhausted")
            return StrictEnvelopeRecoveryAction.EXHAUSTED, None
        return None, None

    @staticmethod
    def _empty_effects() -> dict[str, Any]:
        return {
            "confirmation_observed": False,
            "execution_boundary_reached": False,
            "execution_suppressed": False,
            "gui_handoff_reached": False,
            "application_service_called": False,
            "tool_executor_called": False,
            "state_mutation_observed": False,
        }

    def _record_terminal(self, kind: str) -> None:
        payload = {
            "kind": kind,
            "message": self.presentations[-1] if self.presentations else None,
            **self._empty_effects(),
        }
        if self._observed_terminal is not None:
            payload.update(self._observed_terminal)
            payload["kind"] = kind
        self._observed_terminal = payload

    def _latest_user_request_text(self) -> str:
        return LLMController._latest_user_request_text(self)  # type: ignore[arg-type]

    def _active_policy_mode(self) -> str:
        return LLMController._active_policy_mode(self)  # type: ignore[arg-type]

    def _remaining_tool_input_question(self, receipt: AssistantToolInputReceipt) -> str:
        return LLMController._remaining_tool_input_question(receipt)

    def collect_active_tool_input_reply(self, text: str) -> bool:
        """Delegate one reply to the controller before evaluator generation."""
        return LLMController._collect_active_tool_input_reply(self, text)  # type: ignore[arg-type]

    def _complete_tool_input_receipt(
        self,
        receipt: AssistantToolInputReceipt,
        latest_user_text: str,
    ) -> bool:
        """Mirror the production no-model receipt completion boundary."""
        self.pending_interactions.clear_active_tool_input()
        self.assembler.build_system_prompt(latest_user_text)
        publication = self.assembler.latest_tool_publication
        self._turn_orchestrator.set_active_publication(publication)
        decision = self._tool_attempt_coordinator.evaluate(
            ToolAttemptRequest(
                command_name=receipt.command_name,
                params=dict(receipt.verified_parameters),
                confidence=1.0,
                publication=publication,
                latest_user_text=latest_user_text,
                tool_input_receipt=receipt,
            )
        )
        self._observed_decision = decision
        if self._present_tool_attempt_boundary(decision):
            return True
        self._execute_tool_attempt(decision)
        return True

    def begin_turn(
        self,
        user_text: str,
        publication: PromptToolPublication,
    ) -> AssistantToolInputReceipt | None:
        self._append_history("user", user_text)
        LLMController._reset_user_turn_state(self)  # type: ignore[arg-type]
        self._turn_orchestrator.active_publication = publication
        return self.pending_interactions.active_tool_input

    def admit_typed_response(self, response: str) -> AssistantToolInputReceipt | None:
        envelope = CommandParser.parse_product(response)
        if envelope.status is not ToolEnvelopeStatus.NO_TOOL:
            return None
        LLMController._begin_typed_tool_input(self, envelope)  # type: ignore[arg-type]
        return self.pending_interactions.tool_input

    def _select_tool_proposal(
        self,
        command_result: Any,
    ) -> tuple[str, dict[str, Any]] | None:
        return LLMController._select_tool_proposal(self, command_result)  # type: ignore[arg-type]

    def _reject_excluded_turn_command(self, command_name: str) -> bool:
        return LLMController._reject_excluded_turn_command(  # type: ignore[arg-type]
            self,
            command_name,
        )

    def _evaluate_tool_proposal(
        self,
        command: tuple[str, dict[str, Any]],
        response_text: str,
        *,
        single_proposal: bool = True,
    ) -> ToolAttemptDecision:
        decision = LLMController._evaluate_tool_proposal(  # type: ignore[arg-type]
            self,
            command,
            response_text,
            single_proposal=single_proposal,
        )
        self._observed_decision = decision
        return decision

    def _handle_tool_attempt_blocked(self, *_args: Any, **_kwargs: Any) -> None:
        self._record_terminal("blocked")

    def _present_tool_attempt_boundary(self, decision: ToolAttemptDecision) -> bool:
        return LLMController._present_tool_attempt_boundary(  # type: ignore[arg-type]
            self,
            decision,
        )

    def _request_tool_confirmation(
        self,
        decision: ToolAttemptDecision,
        _context: ToolAvailabilityContext | None = None,
    ) -> None:
        self._observed_terminal = {
            "kind": "confirmation",
            "message": None,
            **self._empty_effects(),
            "confirmation_observed": True,
        }
        # The controller has already selected this branch. The real UI signal
        # is deliberately not emitted in evaluator mode.
        self.confirmation_requested.emit(decision)

    def _execute_tool_attempt(
        self, _decision: ToolAttemptDecision, **_kwargs: Any
    ) -> None:
        """Stop at the controller execution boundary; never invoke a tool."""
        self._observed_terminal = {
            "kind": "execution_boundary_suppressed",
            "message": None,
            **self._empty_effects(),
            "execution_boundary_reached": True,
            "execution_suppressed": True,
        }

    def _finalize_turn_after_tool(self, _outcome: str = "completed") -> None:
        self._record_terminal("proposal_not_selected")

    def evaluate_proposal(
        self,
        response: str,
    ) -> tuple[ToolAttemptDecision | None, dict[str, Any] | None]:
        envelope = CommandParser.parse_product(response)
        if envelope.status is not ToolEnvelopeStatus.VALID:
            return None, None
        command = self._select_tool_proposal(list(envelope.commands))
        if command is None:
            return None, None
        decision = self._evaluate_tool_proposal(
            command,
            response,
            single_proposal=len(envelope.commands) == 1,
        )
        return decision, command[1]

    def admit_origin_guard_response(
        self, response: str
    ) -> AssistantToolInputReceipt | None:
        """Present a Host-origin clarification through the controller boundary."""
        decision, _parameters = self.evaluate_proposal(response)
        if decision is None or decision.tool_input_receipt is None:
            return None
        LLMController._present_tool_attempt_boundary(self, decision)  # type: ignore[arg-type]
        return self.pending_interactions.tool_input

    def observed_controller_outcome(
        self,
        response: str,
        *,
        workflow_stage: str,
        recovery_action: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Project the most recent controller replay without another policy path."""
        envelope, _parsed_stage = _recovery_envelope(
            response,
            workflow_stage=workflow_stage,
        )
        receipt = self.pending_interactions.tool_input
        action = (
            self._observed_decision.action.value
            if self._observed_decision is not None
            else None
        )
        receipt_origin = (
            "model_typed"
            if envelope.status is ToolEnvelopeStatus.NO_TOOL and receipt is not None
            else "host_parameter_origin"
            if self._observed_decision is not None
            and self._observed_decision.tool_input_receipt is not None
            else None
        )
        admission = {
            "path": (
                "typed_receipt"
                if receipt_origin == "model_typed"
                else "proposal"
                if self._observed_decision is not None
                else "recovery"
                if recovery_action in {"choose_one", "exhausted", "retry_format"}
                else "no_tool"
            ),
            "attempt_action": action,
            "receipt_created": receipt is not None,
            "receipt_origin": receipt_origin,
            "result_error_type": (
                self._observed_decision.result.error_type
                if self._observed_decision is not None
                and self._observed_decision.result is not None
                else None
            ),
            "result_policy": (
                self._observed_decision.result.diagnostics.get("policy")
                if self._observed_decision is not None
                and self._observed_decision.result is not None
                else None
            ),
        }
        terminal = self._observed_terminal or {
            "kind": "unobserved",
            "message": None,
            **self._empty_effects(),
        }
        if recovery_action == "choose_one" and terminal["kind"] == "respond":
            # The controller publishes the trusted reply through its normal
            # response terminal; the shared recovery decision owns this
            # evaluator-facing choose-one classification.
            terminal = {**terminal, "kind": "choose_one"}
        return admission, terminal


def _case_application_publication(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
) -> ApplicationViewPublication:
    """Build the smallest internally consistent product state for one stage."""
    stage = PipelineStage(case.workflow_stage)
    state = ApplicationStateSnapshot.empty()

    if stage is not PipelineStage.EMPTY:
        state = replace(
            state,
            pipeline_stage=stage.value,
            raw=replace(state.raw, loaded=True, count=1),
            active_dataset=replace(state.active_dataset, has_raw_data=True),
        )
    if stage in {
        PipelineStage.PREPROCESSED,
        PipelineStage.EPOCH_READY,
        PipelineStage.DATASET_READY,
        PipelineStage.TRAINING,
        PipelineStage.TRAINED,
    }:
        state = replace(
            state,
            preprocessed=replace(
                state.preprocessed,
                available=True,
                count=1,
                operations=["bandpass_filter"],
            ),
            active_dataset=replace(state.active_dataset, has_preprocessed_data=True),
        )
    if stage in {
        PipelineStage.EPOCH_READY,
        PipelineStage.DATASET_READY,
        PipelineStage.TRAINING,
        PipelineStage.TRAINED,
    }:
        state = replace(
            state,
            epoch=replace(
                state.epoch,
                available=True,
                exists=True,
                epoch_count=120,
                n_channels=22,
                n_times=256,
                sfreq=128.0,
                event_names=["rest", "task"],
                event_ids={"rest": 1, "task": 2},
            ),
            active_dataset=replace(state.active_dataset, has_epoch_data=True),
        )
    if stage in {
        PipelineStage.DATASET_READY,
        PipelineStage.TRAINING,
        PipelineStage.TRAINED,
    }:
        state = replace(
            state,
            dataset=replace(
                state.dataset,
                available=True,
                count=1,
                split_spec_saved=True,
                split_lifecycle=DatasetSplitLifecycle.VERIFIED,
                split_materialized=True,
            ),
            training=replace(
                state.training,
                has_model=True,
                model_name="EEGNet",
                has_training_option=True,
                training_option={"epoch": 1},
            ),
            active_dataset=replace(
                state.active_dataset,
                has_datasets=True,
                has_saved_split=True,
            ),
            active_training=replace(
                state.active_training,
                has_model=True,
                has_training_option=True,
            ),
        )
    if stage is PipelineStage.TRAINING:
        state = replace(
            state,
            training=replace(
                state.training,
                has_trainer=True,
                is_running=True,
                progress_message="Synthetic training run in progress.",
            ),
            active_training=replace(
                state.active_training,
                has_trainer=True,
                is_running=True,
            ),
        )
    if stage is PipelineStage.TRAINED:
        state = replace(
            state,
            training=replace(
                state.training,
                has_trainer=True,
                run_count=1,
                finished_run_count=1,
            ),
            evaluation=replace(
                state.evaluation,
                available=True,
                total_plans=1,
                total_runs=1,
                finished_runs=1,
                metrics_available=True,
            ),
            active_training=replace(
                state.active_training,
                has_trainer=True,
                finished_run_count=1,
            ),
        )
    return ApplicationViewPublication(
        generation=1,
        state=state,
        capabilities=build_capability_policy(state),
    )


def _case_projection(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    registry: ToolRegistry,
    *,
    recovery_messages: tuple[str, ...] = (),
) -> tuple[
    list[dict[str, str]],
    PromptToolPublication,
    ApplicationViewPublication,
]:
    """Build one first-turn request from the product publication boundary."""
    publication = _case_application_publication(case)
    runtime = _EvaluatorApplicationRuntime(publication)
    assembler = ContextAssembler(
        registry,
        _PublicationBackedEvaluatorStudy(),
        application_runtime=runtime,
    )
    for message in recovery_messages:
        assembler.add_context(message)
    messages = assembler.get_messages([{"role": "user", "content": case.user_input}])
    if isinstance(
        case, TargetEvalCase
    ) and not assembler.latest_tool_publication.permits(case.expected_tool):
        raise ValueError(
            f"Target case {case.case_id} is not callable from its production "
            f"fixture at {case.workflow_stage}."
        )
    return messages, assembler.latest_tool_publication, publication


def build_clarification_messages(
    case: ClarificationCase,
    source: PrecisionCase,
    *,
    receipt: AssistantToolInputReceipt,
    registry: ToolRegistry,
    recovery_messages: tuple[str, ...] = (),
) -> tuple[
    list[dict[str, str]],
    PromptToolPublication,
    ApplicationViewPublication,
]:
    """Build the visible clarification history without a receipt prompt bridge."""
    if (
        case.trajectory_kind == "direct" and source.case_id != case.source_case_id
    ) or source.category != "missing_parameter":
        raise ValueError("Clarification source does not match its missing case.")
    publication = _case_application_publication(source)
    assembler = ContextAssembler(
        registry,
        _PublicationBackedEvaluatorStudy(),
        application_runtime=_EvaluatorApplicationRuntime(publication),
    )
    for message in recovery_messages:
        assembler.add_context(message)
    messages = assembler.get_messages(
        [
            {"role": "assistant", "content": receipt.question},
            {"role": "user", "content": case.reply},
        ]
    )
    return messages, assembler.latest_tool_publication, publication


def build_case_messages(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    registry: ToolRegistry,
) -> list[dict[str, str]]:
    """Build every active first turn through the product context assembler."""
    messages, _prompt_publication, _backend_publication = _case_projection(
        case,
        registry,
    )
    return messages


def _build_recovery_case_messages(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    registry: ToolRegistry,
    recovery_messages: tuple[str, ...],
) -> list[dict[str, str]]:
    """Rebuild retry input through the same production context assembler."""
    messages, _prompt_publication, _backend_publication = _case_projection(
        case,
        registry,
        recovery_messages=recovery_messages,
    )
    return messages


def score_model_response(
    case: TargetEvalCase,
    response: str,
    registry: ToolRegistry,
) -> TargetEvalScore:
    """Require exact JSON, stage, target tool, parameters, and registered schema."""
    envelope = CommandParser.parse_product(response)
    if envelope.status is not ToolEnvelopeStatus.VALID:
        return TargetEvalScore(
            False,
            "output_format",
            response[:1000],
            envelope.workflow_stage,
            None,
            None,
            envelope.error,
        )

    tool_name, parameters = envelope.commands[0]
    tool = registry.get_tool(tool_name)
    if tool is None:
        schema_valid = False
        schema_detail = f"Tool is not registered: {tool_name}"
    else:
        schema_result = ToolSchemaValidator({tool.name: tool.parameters}).validate(
            tool_name, parameters
        )
        schema_valid = schema_result.is_valid
        schema_detail = (
            schema_result.error_message or "Tool parameters did not pass validation."
        )

    passed = bool(
        envelope.workflow_stage == case.workflow_stage
        and tool_name == case.expected_tool
        and parameters == case.expected_parameters
        and schema_valid
    )
    if passed:
        failure_type = "none"
        detail = "Exact target action selected."
    elif envelope.workflow_stage != case.workflow_stage:
        failure_type = "workflow_stage"
        detail = "Model did not acknowledge the exact target stage."
    elif tool_name != case.expected_tool:
        failure_type = "tool_selection"
        detail = "Model selected a different or retired tool."
    elif not schema_valid:
        failure_type = "parameter_schema"
        detail = schema_detail
    else:
        failure_type = "parameter_value"
        detail = "Model parameters did not exactly match the approved case."
    return TargetEvalScore(
        passed,
        failure_type,
        response[:1000],
        envelope.workflow_stage,
        tool_name,
        parameters,
        detail,
    )


def score_challenge_response(
    case: TargetChallengeCase,
    response: str,
    registry: ToolRegistry,
) -> TargetEvalScore:
    """Require a strict, stage-correct response without tool execution."""
    del registry
    envelope = CommandParser.parse_product(response)
    if envelope.status is ToolEnvelopeStatus.FORMAT_ERROR:
        return TargetEvalScore(
            False,
            "output_format",
            response[:1000],
            envelope.workflow_stage,
            None,
            None,
            envelope.error,
        )
    if envelope.status is ToolEnvelopeStatus.VALID:
        tool_name, parameters = envelope.commands[0]
        return TargetEvalScore(
            False,
            "unexpected_tool",
            response[:1000],
            envelope.workflow_stage,
            tool_name,
            parameters,
            "Challenge required respond_to_user without executing a tool.",
        )
    if envelope.workflow_stage != case.workflow_stage:
        return TargetEvalScore(
            False,
            "workflow_stage",
            response[:1000],
            envelope.workflow_stage,
            "respond_to_user",
            {"message": envelope.message},
            "Model did not acknowledge the exact target stage.",
        )

    folded_message = envelope.message.casefold()
    missing = [
        tuple(group)
        for group in case.required_concepts
        if not any(term.casefold() in folded_message for term in group)
    ]
    forbidden = [
        term for term in case.forbidden_concepts if term.casefold() in folded_message
    ]
    passed = not missing and not forbidden
    return TargetEvalScore(
        passed,
        "none" if passed else "response_content",
        response[:1000],
        envelope.workflow_stage,
        "respond_to_user",
        {"message": envelope.message},
        (
            "Exact no-execution response selected."
            if passed
            else (
                "Response violated its content contract: "
                f"missing={missing!r}, forbidden={forbidden!r}"
            )
        ),
    )


class _PrecisionContextSource:
    """Evaluator adapter backed by one production capability publication."""

    def __init__(self, publication: ApplicationViewPublication) -> None:
        self._publication = publication
        self._tool_policy = build_agent_tool_policy(
            object(),
            publication=publication,
            runtime=_EvaluatorApplicationRuntime(publication),
        )

    def get_context(self, tool_name: str) -> ToolAvailabilityContext:
        return ToolAvailabilityContext(
            availability=self._tool_policy.get(
                tool_name,
                ToolAvailability(
                    tool_name=tool_name,
                    enabled=False,
                    reasons=("Tool is not part of the target capability policy.",),
                ),
            ),
            state=self._publication.state.to_dict(),
            generation=self._publication.generation,
        )


def _precision_attempt_coordinator(
    registry: ToolRegistry,
    *,
    publication: ApplicationViewPublication,
) -> ToolAttemptCoordinator:
    """Use the production verifier and attempt coordinator, never a test router."""
    schemas = {tool.name: tool.parameters for tool in registry.get_all_tools()}
    return ToolAttemptCoordinator(
        registry=registry,
        verifier=VerificationLayer(tool_schemas=schemas),
        context_source=_PrecisionContextSource(publication),
    )


_FALSE_COMPLETION_PHRASES = (
    "has been completed",
    "completed successfully",
    "successfully applied",
    "successfully started",
    "successfully opened",
    "has started",
    "is now running",
    "i imported",
    "i applied",
    "i opened",
    "i started",
    "i stopped",
    "i created",
    "i configured",
    "i selected",
    "i cleared",
    "i reset",
    "i computed",
    "已完成",
    "已開始",
    "已匯入",
    "已套用",
    "已開啟",
    "已停止",
    "已建立",
    "已設定",
    "已選擇",
    "已清除",
    "已重設",
    "已計算",
)
_INVALID_PRECISION_MESSAGES = frozenset(
    {
        "...",
        "message",
        "<concise response or one clarifying question>",
    }
)


def _valid_precision_message(message: str | None) -> bool:
    if not isinstance(message, str):
        return False
    normalized = message.strip().casefold()
    return bool(
        normalized
        and normalized not in _INVALID_PRECISION_MESSAGES
        and not any(phrase in normalized for phrase in _FALSE_COMPLETION_PHRASES)
    )


def score_precision_response(
    case: PrecisionCase,
    response: str,
    registry: ToolRegistry,
) -> TargetEvalScore:
    """Score no-action safety through the product parser and attempt boundary."""
    envelope = CommandParser.parse_product(response)
    if envelope.status is ToolEnvelopeStatus.MULTIPLE_OBJECTS:
        passed = case.category == "multi_action"
        return TargetEvalScore(
            passed,
            "none" if passed else "multiple_objects",
            response[:RAW_OUTPUT_PREVIEW_CHAR_LIMIT],
            None,
            None,
            None,
            (
                "Host returned the trusted one-action-at-a-time boundary."
                if passed
                else "Multiple complete objects are not a valid response for this case."
            ),
            PrecisionProductOutcome(
                disposition="choose_one",
                message=STRICT_ENVELOPE_MULTIPLE_OBJECTS_MESSAGE,
            ),
        )
    if envelope.status is ToolEnvelopeStatus.FORMAT_ERROR:
        return TargetEvalScore(
            False,
            "output_format",
            response[:1000],
            envelope.workflow_stage,
            None,
            None,
            envelope.error,
            PrecisionProductOutcome("format_error", None),
        )
    if envelope.workflow_stage != case.workflow_stage:
        return TargetEvalScore(
            False,
            "workflow_stage",
            response[:1000],
            envelope.workflow_stage,
            None,
            None,
            "Model did not acknowledge the exact target stage.",
            PrecisionProductOutcome("format_error", None),
        )
    if envelope.status is ToolEnvelopeStatus.NO_TOOL:
        message = envelope.message
        passed = _valid_precision_message(message)
        return TargetEvalScore(
            passed,
            "none" if passed else "response_content",
            response[:1000],
            envelope.workflow_stage,
            "respond_to_user",
            {"message": message},
            (
                "Exact no-execution response selected."
                if passed
                else "No-action response had a wrong stage, empty message, or false completion claim."
            ),
            PrecisionProductOutcome("respond", message),
        )

    tool_name, parameters = envelope.commands[0]
    _messages, prompt_publication, backend_publication = _case_projection(
        case,
        registry,
    )
    coordinator = _precision_attempt_coordinator(
        registry,
        publication=backend_publication,
    )
    decision = coordinator.evaluate(
        ToolAttemptRequest(
            command_name=tool_name,
            params=parameters,
            confidence=1.0,
            publication=prompt_publication,
            latest_user_text=case.user_input,
        )
    )
    safe_block = decision.action in {
        ToolAttemptAction.PUBLICATION_BLOCKED,
        ToolAttemptAction.PROVENANCE_BLOCKED,
        ToolAttemptAction.VERIFICATION_BLOCKED,
        ToolAttemptAction.CAPABILITY_BLOCKED,
        ToolAttemptAction.RESOURCE_CONFIRMATION_BLOCKED,
        ToolAttemptAction.INTENT_BLOCKED,
    }
    import_positive_origin_block = bool(
        case.requested_tool == "import_eeg_data"
        and tool_name == "import_eeg_data"
        and decision.action is ToolAttemptAction.INTENT_BLOCKED
        and decision.result is not None
        and decision.result.error_type == "intent_mismatch"
        and decision.result.diagnostics.get("policy")
        == "import_eeg_data_positive_origin"
    )
    passed = bool(
        (
            case.category == "missing_parameter"
            and decision.action is ToolAttemptAction.RESPOND
        )
        or (
            case.category == "out_of_stage"
            and tool_name == case.requested_tool
            and safe_block
        )
        or import_positive_origin_block
    )
    if decision.action in {
        ToolAttemptAction.EXECUTE,
        ToolAttemptAction.CONFIRMATION_REQUIRED,
    }:
        passed = False
    if decision.action is ToolAttemptAction.RESPOND:
        disposition = "respond"
        product_message = decision.message
    elif safe_block:
        disposition = "blocked"
        product_message = (
            summarize_tool_result(tool_name, False, decision.result)
            if decision.result is not None
            else None
        )
    elif decision.action is ToolAttemptAction.CONFIRMATION_REQUIRED:
        disposition = "confirmation"
        product_message = None
    elif decision.action is ToolAttemptAction.EXECUTE:
        disposition = "execute"
        product_message = None
    else:
        disposition = decision.action.value
        product_message = decision.message
    confirmation_requested = decision.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    execution_permitted = decision.action is ToolAttemptAction.EXECUTE
    outcome = PrecisionProductOutcome(
        disposition=disposition,
        message=product_message,
        confirmation_requested=confirmation_requested,
        gui_handoff_permitted=execution_permitted,
        application_service_permitted=execution_permitted,
        tool_executor_permitted=execution_permitted,
        state_mutation_permitted=execution_permitted,
    )
    passed = bool(
        passed
        and _valid_precision_message(product_message)
        and not confirmation_requested
        and not execution_permitted
        and not outcome.gui_handoff_permitted
        and not outcome.application_service_permitted
        and not outcome.tool_executor_permitted
        and not outcome.state_mutation_permitted
    )
    return TargetEvalScore(
        passed,
        "none" if passed else "unexpected_tool",
        response[:1000],
        envelope.workflow_stage,
        tool_name,
        parameters,
        (
            "Production attempt policy produced a safe no-action outcome."
            if passed
            else f"Tool proposal reached unsafe or disallowed outcome: {decision.action.value}."
        ),
        outcome,
    )


def score_raw_precision_response(
    case: PrecisionCase,
    response: str,
    registry: ToolRegistry,
) -> TargetEvalScore:
    """Score the model's no-action choice before any Host intervention."""
    del registry
    envelope = CommandParser.parse_product(response)
    if envelope.status is ToolEnvelopeStatus.FORMAT_ERROR:
        return TargetEvalScore(
            False,
            "output_format",
            response[:1000],
            envelope.workflow_stage,
            None,
            None,
            envelope.error,
        )
    if envelope.workflow_stage != case.workflow_stage:
        return TargetEvalScore(
            False,
            "workflow_stage",
            response[:1000],
            envelope.workflow_stage,
            None,
            None,
            "Model did not acknowledge the exact target stage.",
        )
    if envelope.status is ToolEnvelopeStatus.VALID:
        tool_name, parameters = envelope.commands[0]
        return TargetEvalScore(
            False,
            "unexpected_tool",
            response[:1000],
            envelope.workflow_stage,
            tool_name,
            parameters,
            "Model proposed a tool where the case requires a no-action response.",
        )
    message = envelope.message
    passed = _valid_precision_message(message)
    if passed and case.category == "missing_parameter":
        concepts = _MISSING_PARAMETER_CONCEPTS.get(case.requested_tool or "", ())
        folded_message = message.casefold()
        passed = bool(
            concepts
            and all(
                any(term.casefold() in folded_message for term in group)
                for group in concepts
            )
        )
    return TargetEvalScore(
        passed,
        "none" if passed else "response_content",
        response[:1000],
        envelope.workflow_stage,
        "respond_to_user",
        {"message": message},
        (
            "Model selected a valid no-action response."
            if passed
            else "Model did not provide the case-required no-action response."
        ),
    )


def _score_case_response(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    response: str,
    registry: ToolRegistry,
) -> TargetEvalScore:
    if isinstance(case, PrecisionCase):
        # Product admission is evaluated only after the final response has
        # crossed the controller harness below. This first score remains the
        # model's semantic diagnostic and never instantiates an evaluator-side
        # coordinator surrogate.
        return score_raw_precision_response(case, response, registry)
    if isinstance(case, TargetChallengeCase):
        return score_challenge_response(case, response, registry)
    return score_model_response(case, response, registry)


def _score_raw_model_response(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    response: str,
    registry: ToolRegistry,
) -> TargetEvalScore:
    if isinstance(case, PrecisionCase):
        return score_raw_precision_response(case, response, registry)
    return _score_case_response(case, response, registry)


def _score_precision_controller_terminal(
    case: PrecisionCase,
    response: str,
    admission: dict[str, Any],
    terminal: dict[str, Any],
    baseline: TargetEvalScore,
) -> TargetEvalScore:
    """Score the product no-action result from the observed controller terminal."""
    envelope = CommandParser.parse_product(response)
    kind = terminal["kind"]
    no_side_effect = not any(
        terminal[key]
        for key in (
            "confirmation_observed",
            "execution_boundary_reached",
            "gui_handoff_reached",
            "application_service_called",
            "tool_executor_called",
            "state_mutation_observed",
        )
    )
    import_blocked = bool(
        case.requested_tool == "import_eeg_data"
        and envelope.status is ToolEnvelopeStatus.VALID
        and envelope.commands[0][0] == "import_eeg_data"
        and kind == "blocked"
        and admission.get("attempt_action") == "intent_blocked"
        and admission.get("result_error_type") == "intent_mismatch"
        and admission.get("result_policy") == "import_eeg_data_positive_origin"
    )
    passed = bool(
        no_side_effect
        and (
            (case.category == "multi_action" and kind == "choose_one")
            or (case.category == "missing_parameter" and kind == "respond")
            or (
                case.category == "out_of_stage"
                and envelope.status is ToolEnvelopeStatus.VALID
                and envelope.commands[0][0] == case.requested_tool
                and kind == "blocked"
            )
            or import_blocked
            or (
                envelope.status is ToolEnvelopeStatus.NO_TOOL
                and kind == "respond"
                and _valid_precision_message(envelope.message)
            )
        )
    )
    failure_type = baseline.failure_type
    if not passed and failure_type == "none":
        failure_type = (
            "format_recovery_exhausted"
            if kind == "format_recovery_exhausted"
            else "controller_terminal"
        )
    return TargetEvalScore(
        passed,
        "none" if passed else failure_type,
        baseline.response,
        baseline.parsed_stage,
        baseline.parsed_tool,
        baseline.parsed_parameters,
        (
            "Controller replay reached the required no-action terminal."
            if passed
            else "Controller replay did not reach the required safe terminal."
        ),
        PrecisionProductOutcome(
            disposition=kind,
            message=terminal["message"],
            confirmation_requested=bool(terminal["confirmation_observed"]),
            gui_handoff_permitted=bool(terminal["gui_handoff_reached"]),
            application_service_permitted=bool(terminal["application_service_called"]),
            tool_executor_permitted=bool(terminal["tool_executor_called"]),
            state_mutation_permitted=bool(terminal["state_mutation_observed"]),
        ),
    )


def _recovery_envelope(
    response: str,
    *,
    workflow_stage: str,
) -> tuple[ToolEnvelopeParseResult, str | None]:
    """Apply the controller's exact stage check before recovery classification."""
    parsed = CommandParser.parse_product(response)
    parsed_stage = parsed.workflow_stage
    if (
        parsed.status in {ToolEnvelopeStatus.VALID, ToolEnvelopeStatus.NO_TOOL}
        and parsed.workflow_stage != workflow_stage
    ):
        return (
            ToolEnvelopeParseResult.format_error(
                "workflow_stage does not match the current backend publication."
            ),
            parsed_stage,
        )
    return parsed, parsed_stage


def _evaluate_trajectory(
    *,
    workflow_stage: str,
    build_messages: Callable[[tuple[str, ...]], list[dict[str, str]]],
    score_response: Callable[[str], TargetEvalScore],
    score_raw_model_response: Callable[[str], TargetEvalScore],
    generate_response: Callable[[list[dict[str, str]]], str],
    generation_recorder: GenerationTraceRecorder | None,
    trace_case_id: str,
    initial_turn_purpose: str = "first_turn",
    replay_controller_response: (
        Callable[[str], tuple[StrictEnvelopeRecoveryAction | None, str | None]] | None
    ) = None,
) -> CaseTrajectoryResult:
    """Generate one strict-envelope trajectory through the production policy."""
    recovery_messages: list[str] = []
    attempts: list[ModelGenerationAttempt] = []
    raw_score: TargetEvalScore | None = None

    while True:
        messages = build_messages(tuple(recovery_messages))
        response = generate_response(messages)
        if type(response) is not str:
            raise TypeError("Model generation must return one exact string.")
        if generation_recorder is not None:
            generation_recorder.record(
                response,
                case_id=trace_case_id,
                turn_purpose=(
                    initial_turn_purpose if not recovery_messages else "format_retry"
                ),
            )
        response = response.strip()
        if raw_score is None:
            raw_score = score_raw_model_response(response)

        envelope, parsed_stage = _recovery_envelope(
            response,
            workflow_stage=workflow_stage,
        )
        controller_action: StrictEnvelopeRecoveryAction | None = None
        controller_context: str | None = None
        if replay_controller_response is not None:
            controller_action, controller_context = replay_controller_response(response)
        recovery_envelope = envelope
        if controller_action is not None:
            recovery_envelope = ToolEnvelopeParseResult.format_error(
                "Controller rejected the clarification envelope."
            )
        decision = DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY.decide(
            StrictEnvelopeRecoveryRequest(
                envelope=recovery_envelope,
                recovery_attempts_used=len(recovery_messages),
            )
        )
        if controller_action is not None and decision.action is not controller_action:
            raise RuntimeError(
                "Controller and evaluator format-recovery decisions diverged."
            )
        attempts.append(
            ModelGenerationAttempt(
                attempt_number=len(attempts) + 1,
                response_preview=response[:RAW_OUTPUT_PREVIEW_CHAR_LIMIT],
                envelope_status=recovery_envelope.status.value,
                workflow_stage=parsed_stage,
                recovery_action=decision.action.value,
                taxonomy=decision.taxonomy.value,
                recovery_attempts_after=decision.recovery_attempts_after,
            )
        )

        if decision.action is StrictEnvelopeRecoveryAction.RETRY_FORMAT:
            if controller_action is StrictEnvelopeRecoveryAction.RETRY_FORMAT:
                if controller_context is None:
                    raise RuntimeError("Controller retry is missing recovery context.")
                recovery_messages.append(controller_context)
                continue
            if decision.message is None:
                raise RuntimeError("Format retry decision is missing recovery context.")
            recovery_messages.append(decision.message.content)
            continue

        final_score = score_response(response)
        if decision.action is StrictEnvelopeRecoveryAction.EXHAUSTED:
            final_score = replace(
                final_score,
                product_outcome=PrecisionProductOutcome(
                    disposition="format_recovery_exhausted",
                    message=STRICT_ENVELOPE_EXHAUSTED_MESSAGE,
                ),
            )
        return CaseTrajectoryResult(
            raw_score=raw_score,
            post_recovery_score=score_raw_model_response(response),
            final_score=final_score,
            final_response=response,
            attempts=tuple(attempts),
        )


def evaluate_case_trajectory(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    registry: ToolRegistry,
    generate_response: Callable[[list[dict[str, str]]], str],
    *,
    generation_recorder: GenerationTraceRecorder | None = None,
    trace_case_id: str | None = None,
) -> CaseTrajectoryResult:
    """Generate and score one case through the product strict-recovery policy."""

    def messages(recovery: tuple[str, ...]) -> list[dict[str, str]]:
        return (
            _build_recovery_case_messages(case, registry, recovery)
            if recovery
            else build_case_messages(case, registry)
        )

    _messages, prompt_publication, backend_publication = _case_projection(
        case,
        registry,
    )
    harness = _EvaluatorControllerHarness(
        registry=registry,
        publication=backend_publication,
    )
    harness.begin_turn(case.user_input, prompt_publication)
    trajectory = _evaluate_trajectory(
        workflow_stage=case.workflow_stage,
        build_messages=messages,
        score_response=lambda response: _score_case_response(
            case,
            response,
            registry,
        ),
        score_raw_model_response=lambda response: _score_raw_model_response(
            case,
            response,
            registry,
        ),
        generate_response=generate_response,
        generation_recorder=generation_recorder,
        trace_case_id=trace_case_id or case.case_id,
        replay_controller_response=harness.replay_controller_generation,
    )
    host_admission, product_terminal = harness.observed_controller_outcome(
        trajectory.final_response,
        workflow_stage=case.workflow_stage,
        recovery_action=trajectory.attempts[-1].recovery_action,
    )
    final_score = (
        _score_precision_controller_terminal(
            case,
            trajectory.final_response,
            host_admission,
            product_terminal,
            trajectory.final_score,
        )
        if isinstance(case, PrecisionCase)
        else trajectory.final_score
    )
    return replace(
        trajectory,
        final_score=final_score,
        host_admission=host_admission,
        product_terminal=product_terminal,
    )


def admit_clarification_receipt(
    source: PrecisionCase,
    response: str,
    *,
    expected_tool: str,
    registry: ToolRegistry,
) -> ClarificationAdmission | None:
    """Replay the first response through product admission before follow-up.

    The evaluator must not manufacture a receipt from the case fixture.  It
    derives one only from the model's first response plus the same parser,
    attempt coordinator, and pending-interaction owner used by the product.
    """
    _messages, prompt_publication, backend_publication = _case_projection(
        source,
        registry,
    )
    harness = _EvaluatorControllerHarness(
        registry=registry,
        publication=backend_publication,
    )
    harness.begin_turn(source.user_input, prompt_publication)
    receipt = harness.admit_typed_response(response)
    receipt_origin = "model_typed"
    if receipt is None:
        receipt = harness.admit_origin_guard_response(response)
        receipt_origin = "host_parameter_origin"
    if receipt is None or receipt.command_name != expected_tool:
        return None
    return ClarificationAdmission(
        receipt=receipt,
        receipt_origin=receipt_origin,
        harness=harness,
        prompt_publication=prompt_publication,
        backend_publication=backend_publication,
    )


def evaluate_clarification_trajectory(
    case: ClarificationCase,
    source: PrecisionCase,
    *,
    admission: ClarificationAdmission,
    registry: ToolRegistry,
    generate_response: Callable[[list[dict[str, str]]], str],
    generation_recorder: GenerationTraceRecorder | None = None,
    trace_case_id: str | None = None,
) -> CaseTrajectoryResult:
    """Generate an admitted receipt-backed second turn through recovery policy."""
    harness = admission.harness
    receipt = harness.begin_turn(case.reply, admission.prompt_publication)
    if receipt is None:
        raise RuntimeError("Controller did not activate the admitted clarification.")
    # A completed value-shaped reply must reach the product execution boundary
    # without another model generation.
    if harness.collect_active_tool_input_reply(case.reply):
        decision = harness._observed_decision
        parameters = decision.params if decision is not None else None
        passed = bool(
            decision is not None
            and decision.action is ToolAttemptAction.EXECUTE
            and decision.command_name == case.expected_tool
            and parameters == case.expected_parameters
        )
        terminal_score = TargetEvalScore(
            passed,
            "none" if passed else "clarification_collection",
            "",
            source.workflow_stage,
            decision.command_name if decision is not None else None,
            parameters,
            (
                "Controller reached the exact verified execution boundary without "
                "a second model turn."
                if passed
                else "Controller did not admit the verified receipt for execution."
            ),
            PrecisionProductOutcome(
                "execute_boundary"
                if decision is not None and decision.action is ToolAttemptAction.EXECUTE
                else (
                    decision.action.value if decision is not None else "format_error"
                ),
                decision.message if decision is not None else None,
                gui_handoff_permitted=bool(
                    decision is not None
                    and decision.action is ToolAttemptAction.EXECUTE
                ),
                application_service_permitted=bool(
                    decision is not None
                    and decision.action is ToolAttemptAction.EXECUTE
                ),
                tool_executor_permitted=bool(
                    decision is not None
                    and decision.action is ToolAttemptAction.EXECUTE
                ),
                state_mutation_permitted=bool(
                    decision is not None
                    and decision.action is ToolAttemptAction.EXECUTE
                ),
            ),
        )
        return CaseTrajectoryResult(
            raw_score=terminal_score,
            post_recovery_score=terminal_score,
            final_score=terminal_score,
            final_response="",
            attempts=(),
            receipt_origin=admission.receipt_origin,
            product_terminal=harness._observed_terminal,
        )
    receipt = harness.pending_interactions.active_tool_input
    if receipt is None:
        raise RuntimeError("Controller lost the admitted clarification receipt.")
    observed: dict[str, TargetEvalScore] = {}

    def score(response: str) -> TargetEvalScore:
        cached = observed.get(response)
        if cached is not None:
            return cached
        envelope = CommandParser.parse_product(response)
        decision = harness._observed_decision
        parameters = decision.params if decision is not None else None
        passed = bool(
            envelope.status is ToolEnvelopeStatus.VALID
            and envelope.workflow_stage == source.workflow_stage
            and envelope.commands[0][0] == case.expected_tool
            and parameters == case.expected_parameters
            and decision is not None
            and decision.action is ToolAttemptAction.EXECUTE
        )
        observed[response] = TargetEvalScore(
            passed,
            "none" if passed else "clarification_continuation",
            response[:1000],
            envelope.workflow_stage,
            envelope.commands[0][0]
            if envelope.status is ToolEnvelopeStatus.VALID
            else None,
            parameters,
            (
                "Controller reached the exact verified execution boundary."
                if passed
                else "Controller did not admit the exact continuation for execution."
            ),
            PrecisionProductOutcome(
                "execute_boundary"
                if decision is not None and decision.action is ToolAttemptAction.EXECUTE
                else (
                    decision.action.value if decision is not None else "format_error"
                ),
                decision.message if decision is not None else envelope.message,
                gui_handoff_permitted=bool(
                    decision is not None
                    and decision.action is ToolAttemptAction.EXECUTE
                ),
                application_service_permitted=bool(
                    decision is not None
                    and decision.action is ToolAttemptAction.EXECUTE
                ),
                tool_executor_permitted=bool(
                    decision is not None
                    and decision.action is ToolAttemptAction.EXECUTE
                ),
                state_mutation_permitted=bool(
                    decision is not None
                    and decision.action is ToolAttemptAction.EXECUTE
                ),
            ),
        )
        return observed[response]

    def raw_score(response: str) -> TargetEvalScore:
        envelope = CommandParser.parse_product(response)
        if envelope.status is not ToolEnvelopeStatus.VALID:
            return TargetEvalScore(
                False,
                "output_format",
                response[:1000],
                envelope.workflow_stage,
                None,
                None,
                envelope.error,
            )
        tool_name, parameters = envelope.commands[0]
        passed = bool(
            envelope.workflow_stage == source.workflow_stage
            and tool_name == case.expected_tool
            and parameters == case.expected_parameters
        )
        return TargetEvalScore(
            passed,
            "none" if passed else "clarification_continuation",
            response[:1000],
            envelope.workflow_stage,
            tool_name,
            parameters,
            (
                "Model selected the exact continuation action."
                if passed
                else "Model did not select the exact continuation action."
            ),
        )

    return replace(
        _evaluate_trajectory(
            workflow_stage=source.workflow_stage,
            build_messages=lambda recovery: build_clarification_messages(
                case,
                source,
                receipt=receipt,
                registry=registry,
                recovery_messages=recovery,
            )[0],
            score_response=score,
            score_raw_model_response=raw_score,
            generate_response=generate_response,
            generation_recorder=generation_recorder,
            trace_case_id=trace_case_id or case.case_id,
            initial_turn_purpose="clarification_proposal",
            replay_controller_response=harness.replay_controller_generation,
        ),
        receipt_origin=admission.receipt_origin,
        product_terminal=harness._observed_terminal,
    )


def evaluate_discriminated_clarification_trajectory(
    case: ClarificationCase,
    registry: ToolRegistry,
    generate_response: Callable[[list[dict[str, str]]], str],
    *,
    generation_recorder: GenerationTraceRecorder | None = None,
    trace_case_id: str | None = None,
) -> CaseTrajectoryResult:
    """Run the two approved multi-turn clarification trajectories."""
    if (
        case.trajectory_kind
        not in {
            "generic_filter_selection",
            "partial_bandpass_accumulation",
        }
        or len(case.turns) != 3
    ):
        raise ValueError("Unsupported discriminated clarification trajectory.")
    trace_case_id = trace_case_id or case.case_id
    first = PrecisionCase(
        case_id=f"{case.case_id}_first",
        user_input=case.turns[0],
        workflow_stage="data_loaded",
        category="general"
        if case.trajectory_kind == "generic_filter_selection"
        else "missing_parameter",
        requested_tool=(
            None
            if case.trajectory_kind == "generic_filter_selection"
            else case.expected_tool
        ),
    )
    first_trajectory = evaluate_case_trajectory(
        first,
        registry,
        generate_response,
        generation_recorder=generation_recorder,
        trace_case_id=trace_case_id,
    )
    first_envelope = CommandParser.parse_product(first_trajectory.final_response)
    if case.trajectory_kind == "generic_filter_selection":
        first_ok = (
            first_trajectory.final_score.passed
            and first_envelope.status is ToolEnvelopeStatus.NO_TOOL
            and not first_envelope.pending_action
        )
        action_request = case.turns[1]
    else:
        first_ok = first_trajectory.final_score.passed
        action_request = first.user_input
    if case.trajectory_kind == "partial_bandpass_accumulation":
        source = first
        action_trajectory = first_trajectory
        admission = admit_clarification_receipt(
            source,
            first_trajectory.final_response,
            expected_tool=case.expected_tool,
            registry=registry,
        )
    else:
        source = PrecisionCase(
            case_id=f"{case.case_id}_action",
            user_input=action_request,
            workflow_stage="data_loaded",
            category="missing_parameter",
            requested_tool=case.expected_tool,
        )
        action_trajectory = evaluate_case_trajectory(
            source,
            registry,
            generate_response,
            generation_recorder=generation_recorder,
            trace_case_id=trace_case_id,
        )
        admission = admit_clarification_receipt(
            source,
            action_trajectory.final_response,
            expected_tool=case.expected_tool,
            registry=registry,
        )
    if not first_ok or admission is None:
        failed = replace(
            action_trajectory.final_score,
            passed=False,
            failure_type="clarification_admission",
            detail="The prior model turn did not admit the required receipt.",
        )
        return CaseTrajectoryResult(
            raw_score=first_trajectory.raw_score,
            post_recovery_score=action_trajectory.post_recovery_score,
            final_score=failed,
            final_response=action_trajectory.final_response,
            attempts=(
                first_trajectory.attempts
                if action_trajectory is first_trajectory
                else first_trajectory.attempts + action_trajectory.attempts
            ),
            receipt_origin=None,
        )
    if case.trajectory_kind == "partial_bandpass_accumulation":
        harness = admission.harness
        receipt = harness.begin_turn(case.turns[1], admission.prompt_publication)
        if receipt is None:
            raise RuntimeError("Controller did not activate partial clarification.")
        requeued_for_reply = harness.collect_active_tool_input_reply(case.turns[1])
        requeued = harness.pending_interactions.tool_input
        if (
            not requeued_for_reply
            or requeued is None
            or dict(requeued.verified_parameters)
            or requeued.unassigned_bandpass_cutoff is None
            or requeued.remaining_reply_budget != 1
        ):
            failed = replace(
                action_trajectory.final_score,
                passed=False,
                failure_type="partial_accumulation",
                detail="Controller did not verify and requeue the partial reply.",
            )
            return CaseTrajectoryResult(
                raw_score=first_trajectory.raw_score,
                post_recovery_score=action_trajectory.post_recovery_score,
                final_score=failed,
                final_response=(
                    harness.history[-1]["content"] if harness.history else case.turns[1]
                ),
                attempts=first_trajectory.attempts,
                receipt_origin=admission.receipt_origin,
            )
    final_case = replace(case, reply=case.turns[2])
    final_trajectory = evaluate_clarification_trajectory(
        final_case,
        source,
        admission=admission,
        registry=registry,
        generate_response=generate_response,
        generation_recorder=generation_recorder,
        trace_case_id=trace_case_id,
    )
    return CaseTrajectoryResult(
        raw_score=first_trajectory.raw_score,
        post_recovery_score=final_trajectory.post_recovery_score,
        final_score=final_trajectory.final_score,
        final_response=final_trajectory.final_response,
        attempts=(
            first_trajectory.attempts + final_trajectory.attempts
            if action_trajectory is first_trajectory
            else first_trajectory.attempts
            + action_trajectory.attempts
            + final_trajectory.attempts
        ),
        receipt_origin=admission.receipt_origin,
    )


def score_missing_parameter_host_guard(
    case: TargetChallengeCase,
    response: str,
    registry: ToolRegistry,
) -> dict[str, Any]:
    """Score the deterministic host boundary for one missing-parameter case."""
    expected_tool = MISSING_PARAMETER_HOST_TOOLS.get(case.case_id)
    if expected_tool is None:
        return {"applicable": False, "passed": False}

    envelope = CommandParser.parse_product(response)
    if envelope.status is ToolEnvelopeStatus.NO_TOOL:
        raw_score = score_challenge_response(case, response, registry)
        return {
            "applicable": True,
            "passed": raw_score.passed,
            "execution_allowed": False,
            "tool_name": "respond_to_user",
            "message": envelope.message,
            "detail": (
                "The model requested the missing value without proposing execution."
                if raw_score.passed
                else raw_score.detail
            ),
        }
    if envelope.status is not ToolEnvelopeStatus.VALID:
        return {
            "applicable": True,
            "passed": False,
            "execution_allowed": False,
            "tool_name": None,
            "message": None,
            "detail": "The model output was not a legal product envelope.",
        }

    tool_name, parameters = envelope.commands[0]
    tool = registry.get_tool(tool_name)
    schema_valid = bool(
        tool is not None
        and ToolSchemaValidator({tool.name: tool.parameters})
        .validate(tool_name, parameters)
        .is_valid
    )
    if (
        envelope.workflow_stage != case.workflow_stage
        or tool_name != expected_tool
        or not schema_valid
    ):
        return {
            "applicable": True,
            "passed": False,
            "execution_allowed": False,
            "tool_name": tool_name,
            "message": None,
            "detail": "The proposal did not reach the expected host parameter guard.",
        }

    origin = verify_direct_parameter_origins(
        tool_name,
        parameters,
        case.user_input,
    )
    return {
        "applicable": True,
        "passed": not origin.is_valid and bool(origin.error_message),
        "execution_allowed": origin.is_valid,
        "tool_name": tool_name,
        "message": origin.error_message,
        "detail": (
            "The host rejected model-supplied values absent from the latest user "
            "request."
            if not origin.is_valid
            else "The host would allow model-supplied values absent from the request."
        ),
    }


def score_positive_parameter_host_guard(
    case: TargetEvalCase,
    response: str,
    registry: ToolRegistry,
) -> dict[str, Any]:
    """Require an exact positive direct action to pass the production guard."""
    if case.expected_tool not in DIRECT_PARAMETER_TOOLS:
        return {"applicable": False, "passed": False}
    raw_score = score_model_response(case, response, registry)
    if not raw_score.passed or raw_score.parsed_parameters is None:
        return {
            "applicable": True,
            "passed": False,
            "execution_allowed": False,
            "tool_name": raw_score.parsed_tool,
            "message": None,
        }
    origin = verify_direct_parameter_origins(
        case.expected_tool,
        raw_score.parsed_parameters,
        case.user_input,
    )
    return {
        "applicable": True,
        "passed": origin.is_valid,
        "execution_allowed": origin.is_valid,
        "tool_name": case.expected_tool,
        "message": origin.error_message,
    }


def _capture_audit_request() -> _CaptureAuditRequest:
    """Snapshot child session names only when developer capture is enabled."""
    configured = os.environ.get(_PROMPT_CAPTURE_DIRECTORY_ENV, "").strip()
    if not configured:
        return _CaptureAuditRequest(requested=False, root=None)
    root = Path(configured).expanduser()
    if not root.is_absolute():
        return _CaptureAuditRequest(
            requested=True,
            root=None,
            failure_code="invalid_capture_root",
        )
    try:
        prior_sessions = (
            frozenset(child.name for child in root.iterdir())
            if root.exists()
            else frozenset()
        )
    except OSError:
        return _CaptureAuditRequest(
            requested=True,
            root=None,
            failure_code="capture_snapshot_failed",
        )
    return _CaptureAuditRequest(
        requested=True,
        root=root,
        prior_session_names=prior_sessions,
    )


def _capture_integrity_report(
    request: _CaptureAuditRequest,
    generation_trace: tuple[GenerationTraceEntry, ...] | list[GenerationTraceEntry],
    *,
    model_id: str,
    generation_policy: dict[str, Any],
) -> dict[str, Any]:
    """Check one opt-in LocalBackend capture session without disclosing its content."""
    if not request.requested:
        return {
            "requested": False,
            "status": "not_requested",
            "artifact_count": 0,
            "session_id_sha256": None,
            "checks": {},
            "failure_codes": [],
        }
    checks = {
        "single_new_session": False,
        "artifact_directories": False,
        "contiguous_sequences": False,
        "completed_metadata": False,
        "regular_files": False,
        "metadata_matches_runtime": False,
        "utf8_byte_hashes": False,
        "trace_raw_identity": False,
    }
    report: dict[str, Any] = {
        "requested": True,
        "status": "failed",
        "artifact_count": 0,
        "session_id_sha256": None,
        "checks": checks,
        "failure_codes": [],
    }

    def fail(*codes: str) -> dict[str, Any]:
        report["failure_codes"] = list(codes)
        return report

    if request.failure_code is not None or request.root is None:
        return fail(request.failure_code or "capture_snapshot_failed")
    try:
        new_sessions = tuple(
            child
            for child in request.root.iterdir()
            if child.name not in request.prior_session_names
        )
    except OSError:
        return fail("capture_session_listing_failed")
    if len(new_sessions) != 1:
        return fail(
            "new_session_missing" if not new_sessions else "new_session_ambiguity"
        )

    session = new_sessions[0]
    checks["single_new_session"] = True
    report["session_id_sha256"] = hashlib.sha256(
        session.name.encode("utf-8")
    ).hexdigest()
    try:
        if session.is_symlink() or not session.is_dir():
            return fail("capture_session_invalid")
        artifact_directories = tuple(session.iterdir())
    except OSError:
        return fail("capture_artifact_listing_failed")

    expected_count = len(generation_trace)
    report["artifact_count"] = len(artifact_directories)
    if len(artifact_directories) != expected_count:
        return fail("artifact_count_mismatch")

    metadata_by_sequence: dict[int, tuple[dict[str, Any], bytes, bytes]] = {}
    try:
        for directory in artifact_directories:
            if directory.is_symlink() or not directory.is_dir():
                return fail("capture_artifact_directory_invalid")
            files = {name: directory / name for name in _CAPTURE_FILE_NAMES}
            if any(path.is_symlink() or not path.is_file() for path in files.values()):
                return fail("capture_artifact_file_invalid")
            prompt_bytes = files["prompt.txt"].read_bytes()
            raw_bytes = files["raw-output.txt"].read_bytes()
            metadata = json.loads(files["metadata.json"].read_text(encoding="utf-8"))
            prompt_bytes.decode("utf-8")
            raw_bytes.decode("utf-8")
            if type(metadata) is not dict:
                return fail("capture_metadata_mismatch")
            sequence = metadata.get("sequence")
            if (
                type(sequence) is not int
                or directory.name != str(sequence)
                or sequence in metadata_by_sequence
            ):
                return fail("capture_sequence_mismatch")
            metadata_by_sequence[sequence] = (metadata, prompt_bytes, raw_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return fail("capture_artifact_read_failed")

    expected_sequences = set(range(1, expected_count + 1))
    if set(metadata_by_sequence) != expected_sequences:
        return fail("capture_sequence_mismatch")
    checks.update(
        artifact_directories=True,
        regular_files=True,
        contiguous_sequences=True,
    )
    expected_model = local_model_spec(model_id)
    expected_options = {
        name: generation_policy[name]
        for name in ("max_new_tokens", "do_sample", "temperature", "top_p")
    }
    expected_model_payload = (
        {"id": expected_model.repo_id, "revision": expected_model.revision}
        if expected_model is not None
        else None
    )
    metadata_rows = tuple(
        metadata_by_sequence[sequence] for sequence in expected_sequences
    )
    checks["completed_metadata"] = all(
        metadata.get("status") == "completed"
        for metadata, _prompt, _raw in metadata_rows
    )
    checks["metadata_matches_runtime"] = bool(expected_model_payload) and all(
        metadata.get("model") == expected_model_payload
        and metadata.get("options") == expected_options
        and metadata.get("session_id") == session.name
        for metadata, _prompt, _raw in metadata_rows
    )
    checks["utf8_byte_hashes"] = all(
        metadata.get("prompt_bytes") == len(prompt)
        and metadata.get("prompt_sha256") == hashlib.sha256(prompt).hexdigest()
        and metadata.get("raw_output_bytes") == len(raw)
        and metadata.get("raw_output_sha256") == hashlib.sha256(raw).hexdigest()
        for metadata, prompt, raw in metadata_rows
    )
    checks["trace_raw_identity"] = all(
        trace.global_call_index == sequence
        and len(raw) == trace.raw_output_bytes
        and hashlib.sha256(raw).hexdigest() == trace.raw_output_sha256
        and metadata.get("raw_output_bytes") == trace.raw_output_bytes
        and metadata.get("raw_output_sha256") == trace.raw_output_sha256
        for sequence, trace in enumerate(generation_trace, start=1)
        for metadata, _prompt, raw in (metadata_by_sequence[sequence],)
    )
    failure_codes = [
        code
        for check, code in (
            ("completed_metadata", "capture_not_completed"),
            ("metadata_matches_runtime", "capture_metadata_mismatch"),
            ("utf8_byte_hashes", "capture_content_hash_mismatch"),
            ("trace_raw_identity", "capture_trace_raw_mismatch"),
        )
        if not checks[check]
    ]
    if failure_codes:
        return fail(*failure_codes)
    report["status"] = "verified"
    return report


def _build_report(
    *,
    model_id: str,
    results: list[dict[str, Any]],
    expected_case_count: int,
    complete: bool,
    generation_policy: dict[str, Any] | None = None,
    generation_trace: tuple[GenerationTraceEntry, ...]
    | list[GenerationTraceEntry] = (),
    capture_integrity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    core_rows = [
        row for row in results if row.get("suite") in {"positive", "challenge"}
    ]
    passed_count = sum(bool(row["score"]["passed"]) for row in core_rows)
    suite_summary: dict[str, dict[str, int]] = {}
    for suite in ("positive", "challenge"):
        suite_rows = [row for row in results if row.get("suite") == suite]
        suite_passed = sum(bool(row["score"]["passed"]) for row in suite_rows)
        suite_summary[suite] = {
            "case_count": len(suite_rows),
            "passed_count": suite_passed,
            "failed_count": len(suite_rows) - suite_passed,
        }
    precision_rows = [row for row in results if row.get("suite") == "precision"]
    precision_passed = sum(bool(row["score"]["passed"]) for row in precision_rows)
    clarification_rows = [row for row in results if row.get("suite") == "clarification"]
    clarification_passed = sum(
        bool(row["score"]["passed"]) for row in clarification_rows
    )
    first_generation_summary: dict[str, dict[str, int]] = {}
    post_recovery_summary: dict[str, dict[str, int]] = {}
    for suite in ("positive", "challenge", "precision", "clarification"):
        suite_rows = [row for row in results if row.get("suite") == suite]
        first_generation_passed = sum(
            bool(row.get("first_generation_score", row["score"])["passed"])
            for row in suite_rows
        )
        post_recovery_passed = sum(
            bool(row.get("post_recovery_score", row["score"])["passed"])
            for row in suite_rows
        )
        first_generation_summary[suite] = {
            "case_count": len(suite_rows),
            "passed_count": first_generation_passed,
            "failed_count": len(suite_rows) - first_generation_passed,
        }
        post_recovery_summary[suite] = {
            "case_count": len(suite_rows),
            "passed_count": post_recovery_passed,
            "failed_count": len(suite_rows) - post_recovery_passed,
        }
    positive_guard_rows = [
        row
        for row in results
        if row.get("suite") == "positive"
        and row.get("case", {}).get("expected_tool") in DIRECT_PARAMETER_TOOLS
    ]
    positive_guard_passed = sum(
        bool(
            isinstance(row.get("host_admission"), dict)
            and row["host_admission"].get("attempt_action") == "execute"
            and row.get("score", {}).get("passed") is True
        )
        for row in positive_guard_rows
    )
    host_guard_rows = [
        row
        for row in results
        if row.get("suite") == "challenge"
        and row.get("case", {}).get("case_id") in MISSING_PARAMETER_HOST_TOOLS
    ]
    host_guard_passed = sum(
        bool(
            isinstance(row.get("host_admission"), dict)
            and isinstance(row.get("product_terminal"), dict)
            and row["product_terminal"].get("execution_boundary_reached") is False
            and (
                (
                    row["host_admission"].get("attempt_action") == "respond"
                    and row["host_admission"].get("receipt_origin")
                    == "host_parameter_origin"
                )
                or (
                    row["host_admission"].get("attempt_action") is None
                    and row["host_admission"].get("path") == "no_tool"
                    and row["product_terminal"].get("kind") == "respond"
                    and row.get("score", {}).get("passed") is True
                )
            )
        )
        for row in host_guard_rows
    )
    challenge_rows = [row for row in results if row.get("suite") == "challenge"]
    challenge_critical_failures = sum(
        row.get("first_generation_score", row["score"]).get("failure_type")
        in {"output_format", "workflow_stage", "unexpected_tool"}
        for row in challenge_rows
    )
    challenge_wording_failures = sum(
        row.get("first_generation_score", row["score"]).get("failure_type")
        == "response_content"
        for row in challenge_rows
    )
    challenge_unclassified_failures = (
        len(challenge_rows)
        - first_generation_summary["challenge"]["passed_count"]
        - challenge_critical_failures
        - challenge_wording_failures
    )
    raw_model_gate = {
        "positive_exact": {
            "required": 36,
            "passed": first_generation_summary["positive"]["passed_count"],
        },
        "challenge_decision": {
            "required": 14,
            "critical_failures": challenge_critical_failures,
            "wording_failures": challenge_wording_failures,
            "max_wording_failures": 3,
            "unclassified_failures": challenge_unclassified_failures,
        },
        "precision_no_action": {
            "required": PRECISION_CASE_COUNT,
            "passed": first_generation_summary["precision"]["passed_count"],
        },
        "clarification_continuation": {
            "required": CLARIFICATION_CASE_COUNT,
            "passed": first_generation_summary["clarification"]["passed_count"],
        },
    }
    raw_model_gate["passed"] = bool(
        complete
        and first_generation_summary["positive"]["case_count"] == 36
        and raw_model_gate["positive_exact"]["passed"] == 36
    )
    host_safety_gate = {
        "explicit_parameter_origin": {"required": 10, "passed": positive_guard_passed},
        "missing_parameter_origin": {"required": 5, "passed": host_guard_passed},
        "continuation_boundaries": {
            "not_counted_in_model_report": [
                "cancel",
                "topic_switch",
                "stale_receipt",
                "different_tool",
                "partial_reply",
                "multi_action",
            ],
            "report_status": "not_measured_by_this_model_report",
            "external_evidence": "controller unit/integration coverage required",
        },
    }
    host_safety_gate["passed"] = bool(
        complete
        and expected_case_count == 50
        and len(core_rows) == 50
        and len(positive_guard_rows) == 10
        and positive_guard_passed == 10
        and len(host_guard_rows) == 5
        and host_guard_passed == 5
    )
    precision_complete = bool(complete and len(precision_rows) == PRECISION_CASE_COUNT)
    precision_passed_gate = bool(
        precision_complete and precision_passed == PRECISION_CASE_COUNT
    )
    clarification_complete = bool(
        complete and len(clarification_rows) == CLARIFICATION_CASE_COUNT
    )
    clarification_passed_gate = bool(
        clarification_complete and clarification_passed == CLARIFICATION_CASE_COUNT
    )
    direct_host_rows = [
        row for row in clarification_rows if row.get("source_case") is not None
    ]
    direct_host_admitted = sum(
        bool(
            row.get("source_has_host_receipt") is True
            and isinstance(row.get("receipt_admission"), dict)
            and row["receipt_admission"].get("admitted") is True
            and row["receipt_admission"].get("origin")
            in {"model_typed", "host_parameter_origin"}
        )
        for row in direct_host_rows
    )
    direct_host_admission_complete = bool(complete and len(direct_host_rows) == 5)
    direct_host_admission_passed = bool(
        direct_host_admission_complete and direct_host_admitted == 5
    )
    direct_host_admission_gate = {
        "required": 5,
        "passed": direct_host_admitted,
        "complete": direct_host_admission_complete,
        "status": "passed" if direct_host_admission_passed else "failed",
    }
    product_outcome_gate = {
        "precision_no_action": {
            "required": PRECISION_CASE_COUNT,
            "passed": precision_passed,
        },
        "clarification_execution_boundary": {
            "required": CLARIFICATION_CASE_COUNT,
            "passed": clarification_passed,
        },
    }
    product_outcome_gate["passed"] = bool(
        precision_passed_gate and clarification_passed_gate
    )
    capture_integrity = capture_integrity or {
        "requested": False,
        "status": "not_requested",
        "artifact_count": 0,
        "session_id_sha256": None,
        "checks": {},
        "failure_codes": [],
    }
    capture_integrity_passed = capture_integrity.get("status") in {
        "not_requested",
        "verified",
    }
    candidate_passed = bool(
        raw_model_gate["passed"]
        and host_safety_gate["passed"]
        and direct_host_admission_passed
        and product_outcome_gate["passed"]
        and capture_integrity_passed
    )
    spec = local_model_spec(model_id)
    return {
        "schema_version": REPORT_SCHEMA,
        "model": {
            "id": model_id,
            "revision": spec.revision if spec is not None else None,
            "backend": "local",
            "deterministic": True,
        },
        "generation_policy": generation_policy,
        "generation_attempt_count": len(generation_trace),
        "generation_trace": [asdict(entry) for entry in generation_trace],
        "target_surface": sorted(AGENT_ACTION_CONTRACTS.model_tool_names()),
        "suite_summary": suite_summary,
        "first_generation_summary": first_generation_summary,
        "post_recovery_summary": post_recovery_summary,
        "raw_model_gate": raw_model_gate,
        "host_safety_gate": host_safety_gate,
        "direct_host_admission_gate": direct_host_admission_gate,
        "product_outcome_gate": product_outcome_gate,
        "capture_integrity": capture_integrity,
        "candidate_gate": {
            "raw_model": raw_model_gate["passed"],
            "host_safety": host_safety_gate["passed"],
            "direct_host_admission": direct_host_admission_passed,
            "product_outcome": product_outcome_gate["passed"],
            "capture_integrity": capture_integrity_passed,
            "passed": candidate_passed,
        },
        "summary": {
            "expected_case_count": expected_case_count,
            "case_count": len(core_rows),
            "passed_count": passed_count,
            "failed_count": len(core_rows) - passed_count,
            "complete": complete,
            "passed": candidate_passed,
        },
        "precision_summary": {
            "expected_case_count": PRECISION_CASE_COUNT,
            "case_count": len(precision_rows),
            "passed_count": precision_passed,
            "failed_count": len(precision_rows) - precision_passed,
            "complete": precision_complete,
            "passed": precision_passed_gate,
        },
        "clarification_summary": {
            "expected_case_count": CLARIFICATION_CASE_COUNT,
            "case_count": len(clarification_rows),
            "passed_count": clarification_passed,
            "failed_count": len(clarification_rows) - clarification_passed,
            "complete": clarification_complete,
            "passed": clarification_passed_gate,
        },
        "results": results,
        "claim_boundary": (
            "Active English cases report raw model decisions, Host safety boundaries, and "
            "final product outcomes separately. A Host block or recovery can establish "
            "product safety but never counts as raw model quality. Seven controller-backed "
            "clarification trajectories (five direct actions, generic filter selection, and "
            "partial bandpass accumulation) must reach the verified execution boundary. "
            "Score response fields are bounded diagnostic previews; generation_trace records "
            "the pre-normalization raw-output byte count and SHA-256 for capture correlation. "
            "These suites are not workflow success or thesis-grade model accuracy."
        ),
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _experiment_identity(
    *,
    cases_path: Path,
    challenges_path: Path,
    precision_cases_path: Path,
    clarification_cases_path: Path,
) -> dict[str, Any]:
    """Bind the completed evaluator artifact to source and frozen corpora."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git is required to bind the evaluator source identity.")
    head = subprocess.check_output(  # noqa: S603 - fixed Git executable/argv
        [git, "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    status = subprocess.check_output(  # noqa: S603 - fixed Git executable/argv
        [git, "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    source_changes = [row for row in status if row[3:].strip() not in {"settings.json"}]

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    identity = {
        "source_sha": head,
        "source_changes_excluding_protected_settings": source_changes,
        "positive_cases_sha256": digest(cases_path),
        "challenge_cases_sha256": digest(challenges_path),
    }
    identity["precision_cases_sha256"] = digest(precision_cases_path)
    identity["clarification_cases_sha256"] = digest(clarification_cases_path)
    return identity


def _stable_eval_config(
    source: LLMConfig | None,
    *,
    device: str | None,
) -> LLMConfig:
    """Build a fixed-model eval config without persisting user settings."""
    config = source or LLMConfig()
    config.apply_runtime_selection(
        "local",
        model_id=LLMConfig.default_local_model_id(),
    )
    config.local_model_enabled = True
    if device is not None:
        config.device = device
    return config


def _evaluation_generation_policy(config: LLMConfig) -> dict[str, Any]:
    """Report the production structured-decision options used by the evaluator."""
    options = resolve_generation_options(
        profile=GenerationProfile.STRUCTURED_DECISION,
        max_new_tokens=config.max_new_tokens,
        do_sample=config.do_sample,
        temperature=config.temperature,
        top_p=config.top_p,
    )
    return {
        "profile": GenerationProfile.STRUCTURED_DECISION.value,
        "max_new_tokens": options.max_new_tokens,
        "do_sample": options.do_sample,
        "temperature": options.temperature,
        "top_p": options.top_p,
        "max_format_recovery_attempts": (
            DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY.max_recovery_attempts
        ),
    }


def _trajectory_payload(
    attempts: tuple[ModelGenerationAttempt, ...],
    generation_recorder: GenerationTraceRecorder,
    *,
    case_id: str,
) -> dict[str, Any]:
    """Keep policy classification distinct from actual model-call provenance."""
    return {
        "policy_attempts": [asdict(attempt) for attempt in attempts],
        "format_recovery_attempts": sum(
            attempt.recovery_action == StrictEnvelopeRecoveryAction.RETRY_FORMAT.value
            for attempt in attempts
        ),
        "policy_terminal_action": attempts[-1].recovery_action if attempts else None,
        "policy_terminal_taxonomy": attempts[-1].taxonomy if attempts else None,
        "actual_generation_call_indices": [
            entry.global_call_index
            for entry in generation_recorder.entries
            if entry.case_id == case_id
        ],
    }


def run_eval(
    config: LLMConfig,
    cases: tuple[TargetEvalCase, ...],
    *,
    challenge_cases: tuple[TargetChallengeCase, ...] = (),
    precision_cases: tuple[PrecisionCase, ...],
    clarification_cases: tuple[ClarificationCase, ...],
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Load one exact local engine and score every frozen target case."""
    selection = config.assistant_runtime_selection()
    if selection.backend_mode != "local":
        raise RuntimeError(f"Current assistant backend is {selection.backend_mode}.")
    if not config.local_backend_ready(selection.model_id):
        raise RuntimeError(config.local_backend_status_message(selection.model_id))
    if len(precision_cases) != PRECISION_CASE_COUNT:
        raise ValueError(
            f"Candidate evaluation requires exactly {PRECISION_CASE_COUNT} precision cases."
        )
    if len(clarification_cases) != CLARIFICATION_CASE_COUNT:
        raise ValueError(
            "Candidate evaluation requires exactly seven clarification cases."
        )

    generation_policy = _evaluation_generation_policy(config)
    registry = target_tool_registry()
    engine = LLMEngine(config)
    capture_request = _capture_audit_request()
    checkpoint_capture_integrity = (
        {
            "requested": True,
            "status": (
                "failed" if capture_request.failure_code is not None else "incomplete"
            ),
            "artifact_count": 0,
            "session_id_sha256": None,
            "checks": {},
            "failure_codes": (
                [capture_request.failure_code]
                if capture_request.failure_code is not None
                else []
            ),
        }
        if capture_request.requested
        else None
    )

    def generate_from_engine(messages: list[dict[str, str]]) -> str:
        return "".join(
            engine.generate_stream(
                messages,
                profile=GenerationProfile.STRUCTURED_DECISION,
            )
        )

    generation_recorder = GenerationTraceRecorder()
    results: list[dict[str, Any]] = []
    final_responses_by_case: dict[str, str] = {}
    try:
        engine.load_model()
        all_cases: tuple[TargetEvalCase | TargetChallengeCase | PrecisionCase, ...] = (
            *cases,
            *challenge_cases,
            *precision_cases,
        )
        total_case_count = len(all_cases) + len(clarification_cases)
        for index, case in enumerate(all_cases, start=1):
            print(
                f"Stable Assistant model eval {index}/{total_case_count}: {case.case_id}",
                file=sys.stderr,
                flush=True,
            )
            trajectory = evaluate_case_trajectory(
                case,
                registry,
                generate_from_engine,
                generation_recorder=generation_recorder,
                trace_case_id=case.case_id,
            )
            response = trajectory.final_response
            final_responses_by_case[case.case_id] = response
            score = trajectory.final_score
            suite = (
                "precision"
                if isinstance(case, PrecisionCase)
                else "challenge"
                if isinstance(case, TargetChallengeCase)
                else "positive"
            )
            score_payload = asdict(score)
            if score.product_outcome is None:
                score_payload.pop("product_outcome")
            first_generation_score_payload = asdict(trajectory.raw_score)
            if trajectory.raw_score.product_outcome is None:
                first_generation_score_payload.pop("product_outcome")
            post_recovery_score_payload = asdict(trajectory.post_recovery_score)
            if trajectory.post_recovery_score.product_outcome is None:
                post_recovery_score_payload.pop("product_outcome")
            row = {
                "suite": suite,
                "case": asdict(case),
                "first_generation_score": first_generation_score_payload,
                "post_recovery_score": post_recovery_score_payload,
                "score": score_payload,
                "trajectory": _trajectory_payload(
                    trajectory.attempts,
                    generation_recorder,
                    case_id=case.case_id,
                ),
                "host_admission": trajectory.host_admission,
                "product_terminal": trajectory.product_terminal,
            }
            results.append(row)
            if checkpoint_path is not None:
                _write_report(
                    checkpoint_path,
                    _build_report(
                        model_id=selection.model_id,
                        results=results,
                        expected_case_count=len(cases) + len(challenge_cases),
                        complete=False,
                        generation_policy=generation_policy,
                        generation_trace=generation_recorder.entries,
                        capture_integrity=checkpoint_capture_integrity,
                    ),
                )
        precision_by_id = {case.case_id: case for case in precision_cases}
        result_by_id = {row["case"]["case_id"]: row for row in results}
        for offset, case in enumerate(clarification_cases, start=1):
            index = len(all_cases) + offset
            print(
                f"Stable Assistant model eval {index}/{total_case_count}: {case.case_id}",
                file=sys.stderr,
                flush=True,
            )
            if case.trajectory_kind != "direct":
                trajectory = evaluate_discriminated_clarification_trajectory(
                    case,
                    registry,
                    generate_from_engine,
                    generation_recorder=generation_recorder,
                    trace_case_id=case.case_id,
                )
                score_payload = asdict(trajectory.final_score)
                first_generation_score_payload = asdict(trajectory.raw_score)
                post_recovery_score_payload = asdict(trajectory.post_recovery_score)
                trajectory_attempts = trajectory.attempts
                source = None
                receipt_origin = trajectory.receipt_origin
                source_has_receipt = receipt_origin is not None
                source_first_generation_score = None
            else:
                source = precision_by_id[case.source_case_id]
                source_row = result_by_id[case.source_case_id]
                source_first_generation_score = source_row["first_generation_score"]
                admission = admit_clarification_receipt(
                    source,
                    final_responses_by_case[case.source_case_id],
                    expected_tool=case.expected_tool,
                    registry=registry,
                )
                source_has_receipt = admission is not None
                receipt_origin = (
                    admission.receipt_origin if admission is not None else None
                )
                if admission is not None:
                    trajectory = evaluate_clarification_trajectory(
                        case,
                        source,
                        admission=admission,
                        registry=registry,
                        generate_response=generate_from_engine,
                        generation_recorder=generation_recorder,
                        trace_case_id=case.case_id,
                    )
                    score_payload = asdict(trajectory.final_score)
                    first_generation_score_payload = asdict(trajectory.raw_score)
                    post_recovery_score_payload = asdict(trajectory.post_recovery_score)
                    trajectory_attempts = trajectory.attempts
                else:
                    unavailable = TargetEvalScore(
                        False,
                        "source_without_host_receipt",
                        "",
                        source.workflow_stage,
                        None,
                        None,
                        "First turn did not produce the exact Host clarification receipt.",
                    )
                    score_payload = asdict(unavailable)
                    first_generation_score_payload = dict(score_payload)
                    post_recovery_score_payload = dict(score_payload)
                    trajectory_attempts = ()
            if score_payload.get("product_outcome") is None:
                score_payload.pop("product_outcome", None)
            if first_generation_score_payload.get("product_outcome") is None:
                first_generation_score_payload.pop("product_outcome", None)
            if post_recovery_score_payload.get("product_outcome") is None:
                post_recovery_score_payload.pop("product_outcome", None)
            results.append(
                {
                    "suite": "clarification",
                    "case": asdict(case),
                    "source_case": asdict(source) if source is not None else None,
                    "source_has_host_receipt": source_has_receipt,
                    "receipt_admission": {
                        "admitted": source_has_receipt,
                        "origin": receipt_origin,
                    },
                    "source_raw_model_score": source_first_generation_score,
                    "first_generation_score": first_generation_score_payload,
                    "post_recovery_score": post_recovery_score_payload,
                    "score": score_payload,
                    "trajectory": _trajectory_payload(
                        trajectory_attempts,
                        generation_recorder,
                        case_id=case.case_id,
                    ),
                }
            )
            if checkpoint_path is not None:
                _write_report(
                    checkpoint_path,
                    _build_report(
                        model_id=selection.model_id,
                        results=results,
                        expected_case_count=len(cases) + len(challenge_cases),
                        complete=False,
                        generation_policy=generation_policy,
                        generation_trace=generation_recorder.entries,
                        capture_integrity=checkpoint_capture_integrity,
                    ),
                )
    finally:
        with suppress(Exception):
            engine.close()

    return _build_report(
        model_id=selection.model_id,
        results=results,
        expected_case_count=len(cases) + len(challenge_cases),
        complete=True,
        generation_policy=generation_policy,
        generation_trace=generation_recorder.entries,
        capture_integrity=_capture_integrity_report(
            capture_request,
            generation_recorder.entries,
            model_id=selection.model_id,
            generation_policy=generation_policy,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--challenges", type=Path, default=DEFAULT_CHALLENGES)
    parser.add_argument("--precision-cases", type=Path, default=DEFAULT_PRECISION_CASES)
    parser.add_argument(
        "--clarification-cases",
        type=Path,
        default=DEFAULT_CLARIFICATION_CASES,
    )
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(effective_argv)

    config = _stable_eval_config(
        LLMConfig.load_from_file(),
        device=args.device,
    )
    try:
        precision_cases = load_precision_cases(args.precision_cases)
        report = run_eval(
            config,
            load_target_cases(args.cases),
            challenge_cases=load_challenge_cases(args.challenges),
            precision_cases=precision_cases,
            clarification_cases=load_clarification_cases(
                args.clarification_cases,
                precision_cases=precision_cases,
            ),
            checkpoint_path=args.json_out,
        )
        report["experiment_identity"] = _experiment_identity(
            cases_path=args.cases,
            challenges_path=args.challenges,
            precision_cases_path=args.precision_cases,
            clarification_cases_path=args.clarification_cases,
        )
    except Exception as exc:
        report = {
            "schema_version": REPORT_SCHEMA,
            "summary": {"passed": False, "case_count": 0},
            "failure": f"{type(exc).__name__}: {exc}",
        }
    report["invocation"] = {
        "argv": effective_argv,
        "working_directory_is_repository_root": Path.cwd().resolve() == ROOT,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_out is not None:
        _write_report(args.json_out, report)
    passed = bool(report.get("summary", {}).get("passed"))
    return 1 if args.strict and not passed else 0


if __name__ == "__main__":
    raise SystemExit(main())
