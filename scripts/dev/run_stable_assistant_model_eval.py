#!/usr/bin/env python3
"""Run the bounded Stable-v2 target selection suite against the local model."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from statistics import median
from time import perf_counter
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
from XBrainLab.llm.agent.context_encoding import decode_untrusted_context
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.conversation import ConversationHistory
from XBrainLab.llm.agent.parser import (
    CommandParser,
    ToolCommand,
    ToolEnvelopeParseResult,
    ToolEnvelopeStatus,
)
from XBrainLab.llm.agent.pending_interaction import PendingInteractionCoordinator
from XBrainLab.llm.agent.rag_process_lifecycle import (
    RAG_INITIALIZATION_TIMEOUT_SECONDS,
    RAG_RETRIEVAL_TIMEOUT_SECONDS,
    ProcessRAGRetrieverLifecycle,
)
from XBrainLab.llm.agent.strict_envelope_recovery import (
    DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY,
    STRICT_ENVELOPE_EXHAUSTED_MESSAGE,
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
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation
from XBrainLab.llm.agent.turn_orchestrator import (
    AssistantToolAttemptSession,
    AssistantTurnOrchestrator,
)
from XBrainLab.llm.agent.verifier import (
    ToolSchemaValidator,
    VerificationLayer,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.generation import (
    GenerationProfile,
    resolve_generation_options,
)
from XBrainLab.llm.core.model_catalog import local_model_spec
from XBrainLab.llm.pipeline_state import STAGE_CONFIG
from XBrainLab.llm.rag.config import RAGConfig
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
REPORT_SCHEMA = "xbrainlab.stable_assistant_model_eval.v17"
DEFAULT_SINGLE_TURN_CASES = (
    ROOT / "scripts/dev/stable_assistant_single_turn_cases_v1.json"
)
DEFAULT_ENGLISH_CASES = (
    ROOT / "scripts/dev/stable_assistant_english_generalization_cases_v1.json"
)
DEFAULT_RECOVERY_CASES = (
    ROOT / "scripts/dev/stable_assistant_format_recovery_cases_v1.json"
)
ENGLISH_CASES_SHA256 = "74f24fe9d8e7c17db5ee2abdafdd41b42f2a2ce6d92ffb75487eb585b9835d2b"  # pragma: allowlist secret
RECOVERY_CASES_SHA256 = "6821e92a529ee17045a705ebf461b6e23d2ceb2a804a523b5c61656179327443"  # pragma: allowlist secret
SINGLE_TURN_CASES_SHA256 = "5ef6bca6053b835ce1e21a68b51735e69630d0c881e28cf072fa61135abbd1a4"  # pragma: allowlist secret
DEFAULT_ENGINEERING_CASES = (
    ROOT / "scripts" / "dev" / "stable_assistant_engineering_cases.json"
)
PRECISION_CASE_COUNT = 24
CLARIFICATION_CASE_COUNT = 7
BOUNDED_BASELINE_FAILURE_CASE_IDS = frozenset(
    {
        "select_channels_before_data_en",
        "ambiguous_en",
        "generic_filter_selection",
    }
)
FROZEN_CASE_FILE_SHA256 = {  # pragma: allowlist secret - public fixture digests.
    "positive_cases_sha256": "5d60662ce3f43e36c346dbda238a23f7b22377c04043e1833a77296931546577",  # pragma: allowlist secret
    "challenge_cases_sha256": "e3625687d931be3c0abf5003af3bc9323bcc0c1cc11207249d7762db364beaa3",  # pragma: allowlist secret
    "precision_cases_sha256": "273834533ab7842899cf80c4d97b3ac83e7dd4c76bb9aa3da18891f5b21fe839",  # pragma: allowlist secret
    "clarification_cases_sha256": "18cd515562af68bbeaee1cd5e4a73def48ebab64717641634b3624f2912850d2",  # pragma: allowlist secret
}
BOUNDED_BASELINE_MODEL_ID = "ibm-granite/granite-4.0-micro"
BOUNDED_BASELINE_MODEL_REVISION = (  # pragma: allowlist secret - public model revision.
    "56111ae135df9c53a78c99028e7bc24035a9e979"  # pragma: allowlist secret
)
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
    parsed_tool: str | None
    parsed_parameters: dict[str, Any] | None
    detail: str
    product_outcome: PrecisionProductOutcome | None = None
    no_action_passed: bool | None = None


def _mixed_request_semantic_review(
    case: PrecisionCase, score: TargetEvalScore
) -> TargetEvalScore:
    """Separate observable no-action behavior from unscored choose-first meaning."""
    if case.category != "mixed_request":
        return score
    if not score.passed:
        return replace(score, no_action_passed=False)
    return replace(
        score,
        passed=False,
        failure_type="semantic_review_required",
        no_action_passed=True,
        detail=(
            "No-action check passed; whether the response asks which requested task "
            "to do first requires semantic review. passed=False means unverified, "
            "not a confirmed semantic error."
        ),
    )


@dataclass(frozen=True, slots=True)
class ProductRAGContextEvidence:
    """One evaluator retrieval observed through the product process lifecycle."""

    protocol: str
    sequence: int
    trajectory_case_id: str
    query: str
    allowed_tool_names: tuple[str, ...]
    status: str
    error: str | None
    context_item_ids: tuple[str, ...]
    assembled_context_item_ids: tuple[str, ...]
    context_sha256: str | None
    elapsed_seconds: float = 0.0


class _ProductRAGCaseMessages:
    """Build evaluator prompts through the same bounded RAG lifecycle as product turns."""

    def __init__(
        self,
        registry: ToolRegistry,
        lifecycle: ProcessRAGRetrieverLifecycle,
    ) -> None:
        self._registry = registry
        self._lifecycle = lifecycle
        self._next_turn_id = 0
        self._contexts: dict[
            tuple[str, str, str], tuple[str, ProductRAGContextEvidence]
        ] = {}

    def messages(
        self,
        case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
        *,
        recovery_messages: tuple[str, ...] = (),
        trace_case_id: str | None = None,
    ) -> list[dict[str, str]]:
        context, evidence = self._context_for(case, trace_case_id=trace_case_id)
        messages = _case_projection(
            case,
            self._registry,
            recovery_messages=recovery_messages,
            rag_context=context,
        )[0]
        self._record_assembled_context(case, evidence, messages)
        return messages

    def projection(
        self,
        case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
        *,
        trace_case_id: str | None = None,
    ) -> tuple[list[dict[str, str]], PromptToolPublication, ApplicationViewPublication]:
        context, evidence = self._context_for(case, trace_case_id=trace_case_id)
        projection = _case_projection(case, self._registry, rag_context=context)
        self._record_assembled_context(case, evidence, projection[0])
        return projection

    def evidence_for(
        self,
        case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
        *,
        trace_case_id: str | None = None,
    ) -> ProductRAGContextEvidence:
        _context, evidence = self._context_for(case, trace_case_id=trace_case_id)
        return evidence

    def all_evidence(self) -> list[ProductRAGContextEvidence]:
        """Return every observed retrieval in product turn order for the report."""
        return sorted(
            (evidence for _context, evidence in self._contexts.values()),
            key=lambda evidence: evidence.sequence,
        )

    def evidence_for_case(self, case_id: str) -> list[ProductRAGContextEvidence]:
        """Return all retrievals observed for a multi-turn evaluator trajectory."""
        return sorted(
            (
                evidence
                for (_internal_case_id, _query, _trace_case_id), (
                    _context,
                    evidence,
                ) in self._contexts.items()
                if evidence.trajectory_case_id == case_id
            ),
            key=lambda evidence: evidence.sequence,
        )

    def _context_for(
        self,
        case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
        *,
        trace_case_id: str | None = None,
    ) -> tuple[str, ProductRAGContextEvidence]:
        trajectory_case_id = trace_case_id or case.case_id
        query = ContextAssembler.retrieval_query(case.user_input)
        key = (case.case_id, query, trajectory_case_id)
        cached = self._contexts.get(key)
        if cached is not None:
            return cached
        assembler, _publication = _case_assembler(case, self._registry)
        self._next_turn_id += 1
        result = _retrieve_product_rag_context(
            assembler,
            query,
            lifecycle=self._lifecycle,
            turn_id=self._next_turn_id,
            trajectory_case_id=trajectory_case_id,
        )
        self._contexts[key] = result
        return result

    def _record_assembled_context(
        self,
        case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
        evidence: ProductRAGContextEvidence,
        messages: list[dict[str, str]],
    ) -> None:
        assembled_ids = tuple(
            item_id
            for message in messages
            for item_id in _rag_item_ids(message.get("content", ""))
        )
        if assembled_ids == evidence.assembled_context_item_ids:
            return
        key = (case.case_id, evidence.query, evidence.trajectory_case_id)
        self._contexts[key] = (
            self._contexts[key][0],
            replace(evidence, assembled_context_item_ids=assembled_ids),
        )


@dataclass(frozen=True, slots=True)
class ModelGenerationAttempt:
    """One policy classification; its preview is never raw-output identity evidence."""

    attempt_number: int
    response_preview: str
    envelope_status: str
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
    # Controller-observed evidence remains separate from raw and semantic scores.
    # Multi-turn trajectories retain the same projection per user turn.
    host_admission: dict[str, Any] | None = None
    product_terminal: dict[str, Any] | None = None
    turn_observations: tuple[dict[str, Any], ...] = ()


def target_tool_registry() -> ToolRegistry:
    """Build the exact approved target registry used by the product runtime."""
    registry = ToolRegistry()
    tools = get_all_tools()
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


def _proposed_command(envelope: ToolEnvelopeParseResult) -> ToolCommand:
    """Project raw parameters for scoring, never authorize execution."""
    if envelope.command is None:
        raise ValueError("An executable response requires a command.")
    return envelope.command


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
        self._pending_interactions = PendingInteractionCoordinator()
        self._conversation = ConversationHistory()
        self.presentations: list[str] = []
        self.metrics = _EvaluatorMetrics()
        self.status_update = _EvaluatorSignal()
        self.activity_changed = _EvaluatorSignal()
        self.response_presentation_ready = _EvaluatorSignal()
        self.confirmation_requested = _EvaluatorSignal()
        self.processing_finished = _EvaluatorSignal()
        self.is_processing = True
        self._observed_decision: ToolAttemptDecision | None = None
        self._observed_request_update: dict[str, Any] | None = None
        self._observed_terminal: dict[str, Any] | None = None
        self.current_response = ""
        self._user_turn_sequence = 0
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
        return self._conversation.messages

    def _append_history(self, role: str, content: str) -> None:
        self._conversation.append(role, content)

    def _publish_response(self, text: str, **_kwargs: Any) -> None:
        """Record a trusted controller presentation without creating a Qt event."""
        self.presentations.append(text)

    def _publish_activity(self, *_args: Any, **_kwargs: Any) -> None:
        """The evaluator intentionally has no activity presentation surface."""

    def _observe_decision(self, kind: str, **details: Any) -> None:
        """Retain the controller's actual draft validation before tool admission."""
        if kind == "request_update":
            self._observed_request_update = dict(details)

    def _emit_processing_finished(self, _outcome: str = "completed") -> None:
        pass

    def _require_active_turn_correlation(self) -> AssistantTurnCorrelation:
        return AssistantTurnCorrelation(generation=1, turn_id=self._user_turn_sequence)

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
        if self._tool_attempt_session.retry_count <= 0:
            raise RuntimeError(
                "Controller format retry did not record a recovery attempt."
            )
        request = self.assembler.get_generation_request(
            self.history,
            format_recovery=True,
        )
        self._recovery_generation_requested = True
        self._recovery_context = request.to_model_messages()[0]["content"].rsplit(
            "\n", 1
        )[-1]
        return True

    def _handle_tool_envelope_failure(
        self,
        envelope: ToolEnvelopeParseResult,
    ) -> bool:
        return LLMController._handle_tool_envelope_failure(  # type: ignore[arg-type]
            self,
            envelope,
        )

    def _process_tool_call(self, command: ToolCommand, response_text: str) -> None:
        LLMController._process_tool_call(self, command, response_text)  # type: ignore[arg-type]

    def replay_controller_generation(
        self,
        response: str,
    ) -> tuple[StrictEnvelopeRecoveryAction | None, str | None]:
        """Drive one evaluator output through the product controller path."""
        self._observed_decision = None
        self._observed_request_update = None
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

    def begin_turn(
        self,
        user_text: str,
        publication: PromptToolPublication,
    ) -> None:
        self._user_turn_sequence += 1
        self._append_history("user", user_text)
        LLMController._reset_user_turn_state(self)  # type: ignore[arg-type]
        self._turn_orchestrator.active_publication = publication

    def _evaluate_tool_proposal(
        self,
        command: tuple[str, dict[str, Any]],
        response_text: str,
    ) -> ToolAttemptDecision:
        decision = LLMController._evaluate_tool_proposal(  # type: ignore[arg-type]
            self,
            command,
            response_text,
        )
        self._observed_decision = decision
        return decision

    def _handle_tool_attempt_blocked(self, *_args: Any, **_kwargs: Any) -> None:
        self._record_terminal("blocked")

    def _present_tool_attempt_boundary(self, decision: ToolAttemptDecision) -> bool:
        self._observed_decision = decision
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

    def observed_controller_outcome(
        self,
        response: str,
        *,
        recovery_action: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Project the most recent controller replay without another policy path."""
        action = (
            self._observed_decision.action.value
            if self._observed_decision is not None
            else None
        )
        admission = {
            "path": (
                "proposal"
                if self._observed_decision is not None
                else "recovery"
                if recovery_action in {"exhausted", "retry_format"}
                else "no_tool"
            ),
            "attempt_action": action,
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


def _case_assembler(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    registry: ToolRegistry,
) -> tuple[ContextAssembler, ApplicationViewPublication]:
    """Create the production assembler against one evaluator publication fixture."""
    publication = _case_application_publication(case)
    runtime = _EvaluatorApplicationRuntime(publication)
    assembler = ContextAssembler(
        registry,
        _PublicationBackedEvaluatorStudy(),
        application_runtime=runtime,
    )
    return assembler, publication


def _rag_item_ids(context: str) -> tuple[str, ...]:
    items = decode_untrusted_context(context) or ()
    return tuple(
        str(item.source.id)
        for item in items
        if item.item_type == "rag_example" and item.source.id
    )


def _retrieve_product_rag_context(
    assembler: ContextAssembler,
    query: str,
    *,
    lifecycle: ProcessRAGRetrieverLifecycle,
    turn_id: int,
    trajectory_case_id: str,
) -> tuple[str, ProductRAGContextEvidence]:
    """Use the product RAG lifecycle once and retain only its returned context.

    The evaluator deliberately owns no retrieval policy: allowed tools are derived
    from the same assembler projection and the process lifecycle owns startup,
    timeout, child termination, and retriever cleanup.
    """
    started = perf_counter()
    allowed_tool_names = tuple(sorted(assembler.rag_allowed_tool_names()))
    completed = threading.Event()
    result: dict[str, str] = {"context": "", "error": ""}

    def receive(
        callback_turn_id: int,
        _query: str,
        context: str,
        error: str,
    ) -> None:
        if callback_turn_id != turn_id:
            return
        result["context"] = str(context or "")
        result["error"] = str(error or "")
        completed.set()

    queued = lifecycle.retrieve(
        turn_id,
        query,
        receive,
        allowed_tool_names=frozenset(allowed_tool_names),
    )
    if not queued:
        evidence = ProductRAGContextEvidence(
            protocol="product_process_rag.v1",
            sequence=turn_id,
            trajectory_case_id=trajectory_case_id,
            query=query,
            allowed_tool_names=allowed_tool_names,
            status="not_queued",
            error="Product RAG lifecycle did not accept the request.",
            context_item_ids=(),
            assembled_context_item_ids=(),
            context_sha256=None,
            elapsed_seconds=perf_counter() - started,
        )
        return "", evidence

    wait_seconds = (
        RAG_INITIALIZATION_TIMEOUT_SECONDS + RAG_RETRIEVAL_TIMEOUT_SECONDS + 1.0
    )
    if not completed.wait(wait_seconds):
        lifecycle.cancel_retrieval(turn_id)
        evidence = ProductRAGContextEvidence(
            protocol="product_process_rag.v1",
            sequence=turn_id,
            trajectory_case_id=trajectory_case_id,
            query=query,
            allowed_tool_names=allowed_tool_names,
            status="evaluator_wait_timeout",
            error="Evaluator did not receive the bounded product RAG callback.",
            context_item_ids=(),
            assembled_context_item_ids=(),
            context_sha256=None,
            elapsed_seconds=perf_counter() - started,
        )
        return "", evidence

    error = result["error"] or None
    context = "" if error else result["context"]
    status = "degraded" if error else "retrieved" if context else "empty"
    return context, ProductRAGContextEvidence(
        protocol="product_process_rag.v1",
        sequence=turn_id,
        trajectory_case_id=trajectory_case_id,
        query=query,
        allowed_tool_names=allowed_tool_names,
        status=status,
        error=error,
        context_item_ids=_rag_item_ids(context),
        assembled_context_item_ids=(),
        context_sha256=(
            hashlib.sha256(context.encode("utf-8")).hexdigest() if context else None
        ),
        elapsed_seconds=perf_counter() - started,
    )


def _case_projection(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    registry: ToolRegistry,
    *,
    recovery_messages: tuple[str, ...] = (),
    rag_context: str = "",
) -> tuple[
    list[dict[str, str]],
    PromptToolPublication,
    ApplicationViewPublication,
]:
    """Build one first-turn request from the product publication boundary."""
    assembler, publication = _case_assembler(case, registry)
    if rag_context:
        assembler.add_context(rag_context)
    messages = assembler.get_messages(
        [{"role": "user", "content": case.user_input}],
        format_recovery=bool(recovery_messages),
    )
    if isinstance(
        case, TargetEvalCase
    ) and not assembler.latest_tool_publication.permits(case.expected_tool):
        raise ValueError(
            f"Target case {case.case_id} is not callable from its production "
            f"fixture at {case.workflow_stage}."
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


def build_product_rag_case_messages(
    case_id: str,
    *,
    lifecycle: ProcessRAGRetrieverLifecycle,
) -> tuple[dict[str, Any], list[dict[str, str]], ProductRAGContextEvidence]:
    """Build one first-turn evaluator/export prompt through product RAG.

    Continuations require their actual admitted request and trajectory; this
    standalone export accepts only first-turn cases.
    """
    registry = target_tool_registry()
    for case in (
        *load_target_cases(DEFAULT_CASES),
        *load_challenge_cases(DEFAULT_CHALLENGES),
        *load_precision_cases(DEFAULT_PRECISION_CASES),
    ):
        if case.case_id != case_id:
            continue
        builder = _ProductRAGCaseMessages(registry, lifecycle)
        return asdict(case), builder.messages(case), builder.evidence_for(case)
    raise ValueError(
        "Product-RAG prompt export supports first-turn evaluator cases only; "
        "continuations must be captured from their actual controller trajectory."
    )


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
    """Require exact JSON, target tool, parameters, and registered schema."""
    envelope = CommandParser.parse_product(response)
    if envelope.status is not ToolEnvelopeStatus.VALID:
        return TargetEvalScore(
            False,
            "output_format",
            response[:1000],
            None,
            None,
            envelope.error,
        )

    tool_name, parameters = _proposed_command(envelope)
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
        tool_name == case.expected_tool
        and parameters == case.expected_parameters
        and schema_valid
    )
    if passed:
        failure_type = "none"
        detail = "Exact target action selected."
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
        tool_name,
        parameters,
        detail,
    )


def score_challenge_response(
    case: TargetChallengeCase,
    response: str,
    registry: ToolRegistry,
) -> TargetEvalScore:
    """Require a strict response without tool execution."""
    del registry
    envelope = CommandParser.parse_product(response)
    if envelope.status not in {ToolEnvelopeStatus.VALID, ToolEnvelopeStatus.NO_TOOL}:
        return TargetEvalScore(
            False,
            "output_format",
            response[:1000],
            None,
            None,
            envelope.error,
        )
    if envelope.status is ToolEnvelopeStatus.VALID:
        tool_name, parameters = _proposed_command(envelope)
        return TargetEvalScore(
            False,
            "unexpected_tool",
            response[:1000],
            tool_name,
            parameters,
            "Challenge required respond_to_user without executing a tool.",
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
    if envelope.status in {
        ToolEnvelopeStatus.FORMAT_ERROR,
        ToolEnvelopeStatus.MULTIPLE_OBJECTS,
    }:
        return TargetEvalScore(
            False,
            "output_format",
            response[:1000],
            None,
            None,
            envelope.error,
            PrecisionProductOutcome("format_error", None),
        )
    if envelope.status is ToolEnvelopeStatus.NO_TOOL:
        message = envelope.message
        passed = _valid_precision_message(message)
        return _mixed_request_semantic_review(
            case,
            TargetEvalScore(
                passed,
                "none" if passed else "response_content",
                response[:1000],
                "respond_to_user",
                {"message": message},
                (
                    "Exact no-execution response selected."
                    if passed
                    else "No-action response had an empty message or false completion claim."
                ),
                PrecisionProductOutcome("respond", message),
            ),
        )

    tool_name, parameters = _proposed_command(envelope)
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
            publication=prompt_publication,
            latest_user_text=case.user_input,
        )
    )
    safe_block = decision.action in {
        ToolAttemptAction.PUBLICATION_BLOCKED,
        ToolAttemptAction.VERIFICATION_BLOCKED,
        ToolAttemptAction.CAPABILITY_BLOCKED,
        ToolAttemptAction.RESOURCE_CONFIRMATION_BLOCKED,
    }
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
    if envelope.status not in {ToolEnvelopeStatus.VALID, ToolEnvelopeStatus.NO_TOOL}:
        return TargetEvalScore(
            False,
            "output_format",
            response[:1000],
            None,
            None,
            envelope.error,
        )
    if envelope.status is ToolEnvelopeStatus.VALID:
        tool_name, parameters = _proposed_command(envelope)
        return TargetEvalScore(
            False,
            "unexpected_tool",
            response[:1000],
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
    return _mixed_request_semantic_review(
        case,
        TargetEvalScore(
            passed,
            "none" if passed else "response_content",
            response[:1000],
            "respond_to_user",
            {"message": message},
            (
                "Model selected a valid no-action response."
                if passed
                else "Model did not provide the case-required no-action response."
            ),
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
    passed = bool(
        baseline.passed
        and no_side_effect
        and (
            (case.category == "missing_parameter" and kind == "respond")
            or (
                case.category == "out_of_stage"
                and envelope.status is ToolEnvelopeStatus.VALID
                and _proposed_command(envelope)[0] == case.requested_tool
                and kind == "blocked"
            )
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
        no_action_passed=(baseline.no_action_passed and no_side_effect)
        if baseline.no_action_passed is not None
        else None,
    )


def _evaluate_trajectory(
    *,
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

        envelope = CommandParser.parse_product(response)
        controller_action: StrictEnvelopeRecoveryAction | None = None
        controller_context: str | None = None
        if replay_controller_response is not None:
            controller_action, controller_context = replay_controller_response(response)
        recovery_envelope = envelope
        if controller_action is not None and envelope.status in {
            ToolEnvelopeStatus.VALID,
            ToolEnvelopeStatus.NO_TOOL,
        }:
            # Preserve actual parser failures (including multiple objects) in
            # the evidence. Only a parser-valid controller rejection needs the
            # synthetic format-failure projection used by this replay harness.
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
    product_rag_messages: _ProductRAGCaseMessages | None = None,
) -> CaseTrajectoryResult:
    """Generate and score one case through the product strict-recovery policy."""
    trajectory_case_id = trace_case_id or case.case_id

    def messages(recovery: tuple[str, ...]) -> list[dict[str, str]]:
        if product_rag_messages is not None:
            return product_rag_messages.messages(
                case,
                recovery_messages=recovery,
                trace_case_id=trajectory_case_id,
            )
        return (
            _build_recovery_case_messages(case, registry, recovery)
            if recovery
            else build_case_messages(case, registry)
        )

    _messages, prompt_publication, backend_publication = (
        product_rag_messages.projection(case, trace_case_id=trajectory_case_id)
        if product_rag_messages is not None
        else _case_projection(case, registry)
    )
    harness = _EvaluatorControllerHarness(
        registry=registry,
        publication=backend_publication,
    )
    harness.begin_turn(case.user_input, prompt_publication)
    trajectory = _evaluate_trajectory(
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
        trace_case_id=trajectory_case_id,
        replay_controller_response=harness.replay_controller_generation,
    )
    host_admission, product_terminal = harness.observed_controller_outcome(
        trajectory.final_response,
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


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


def _product_rag_protocol(*, dense_only: bool = False) -> dict[str, Any]:
    """Identify the current product retrieval path without claiming empty is healthy."""
    return {
        "name": "product_process_rag.v1",
        "lifecycle": "ProcessRAGRetrieverLifecycle",
        "retriever": "RAGRetriever.get_similar_examples",
        "embedding_model": RAGConfig.EMBEDDING_MODEL,
        "embedding_revision": RAGConfig.EMBEDDING_REVISION,
        "corpus_sha256": RAGConfig.GOLD_SET_SHA256,
        "index_schema_version": RAGConfig.INDEX_SCHEMA_VERSION,
        "dense_only": dense_only,
        "ranking": "dense_cosine" if dense_only else "reciprocal_rank_fusion",
        "dense_similarity_threshold": RAGConfig.SIMILARITY_THRESHOLD,
        "sparse_minimum_matched_terms": RAGConfig.MIN_SPARSE_MATCHED_TERMS,
        "sparse_minimum_coverage": RAGConfig.MIN_SPARSE_COVERAGE,
        "sparse_coverage_metric": "matched_idf_over_min_query_document_idf",
        "candidates_per_branch": RAGConfig.CANDIDATES_PER_BRANCH,
        "rrf_rank_constant": RAGConfig.RRF_RANK_CONSTANT,
        "top_k": RAGConfig.TOP_K,
        "empty_result_note": (
            "Empty means the ready product retriever found no eligible context; "
            "initialization and retrieval errors are reported as degraded."
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


def _duration_summary(values: list[float]) -> dict[str, int | float | None]:
    """Describe observed durations using an explicit nearest-rank P95."""
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "median": median(ordered) if ordered else None,
        "p95_nearest_rank": ordered[math.ceil(len(ordered) * 0.95) - 1]
        if ordered
        else None,
        "maximum": ordered[-1] if ordered else None,
    }


def load_single_turn_cases(
    path: Path = DEFAULT_SINGLE_TURN_CASES,
) -> tuple[TargetEvalCase | PrecisionCase, ...]:
    """Load the approved fixed 20, never rewrite old 81-case artifacts."""
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != SINGLE_TURN_CASES_SHA256:
        raise ValueError("Frozen single-turn manifest changed")
    manifest = json.loads(content)
    precision = {case.case_id: case for case in load_precision_cases()}
    cases = []
    for row in manifest["cases"]:
        if row["tool_name"] == "respond_to_user":
            source = precision.get(row["id"])
            cases.append(
                PrecisionCase(
                    row["id"],
                    row["input"],
                    row["workflow_stage"],
                    row["category"],
                    source.requested_tool if source is not None else None,
                )
            )
        else:
            cases.append(
                TargetEvalCase(
                    row["id"],
                    row["input"],
                    row["workflow_stage"],
                    row["tool_name"],
                    row["parameters"],
                )
            )
    return tuple(cases)


def load_eval_profile(
    profile: str,
) -> tuple[TargetEvalCase | TargetChallengeCase | PrecisionCase, ...]:
    """Select fixed engineering cases; keep historical manifests and scores intact."""
    if profile == "core":
        return load_single_turn_cases()
    if profile == "r3-comparison":
        return (
            *load_single_turn_cases(),
            *load_eval_profile("english"),
            *load_eval_profile("recovery"),
        )
    if profile == "english":
        path, digest = DEFAULT_ENGLISH_CASES, ENGLISH_CASES_SHA256
    elif profile == "recovery":
        path, digest = DEFAULT_RECOVERY_CASES, RECOVERY_CASES_SHA256
    else:
        raise ValueError(f"Unknown evaluation profile: {profile}")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError(f"Frozen {profile} manifest changed")
    cases: list[TargetEvalCase | TargetChallengeCase | PrecisionCase] = []
    for row in json.loads(content)["cases"]:
        if row["tool_name"] == "respond_to_user":
            # Approved tool-decision scope: require a valid nonempty reply, without
            # importing the old manifest's prose-quality criteria into its score.
            cases.append(
                TargetChallengeCase(
                    row["id"],
                    row["input"],
                    row["workflow_stage"],
                    row["category"],
                    (),
                    (),
                )
            )
        else:
            cases.append(
                TargetEvalCase(
                    row["id"],
                    row["input"],
                    row["workflow_stage"],
                    row["tool_name"],
                    row["parameters"],
                )
            )
    return tuple(cases)


def _build_report(
    *,
    model_id: str,
    results: list[dict[str, Any]],
    expected_case_ids: tuple[str, ...],
    complete: bool,
    generation_policy: dict[str, Any],
    generation_trace: list[GenerationTraceEntry],
    capture_integrity: dict[str, Any],
    rag_protocol: dict[str, Any],
    rag_retrievals: list[ProductRAGContextEvidence],
) -> dict[str, Any]:
    ids = [row["case"]["case_id"] for row in results]
    complete = complete and ids == list(expected_case_ids) and len(ids) == len(set(ids))
    fixed_ids = [case.case_id for case in load_single_turn_cases()]
    fixed_complete = complete and ids == fixed_ids
    raw_passed = sum(row["first_generation_score"]["passed"] for row in results)
    post_passed = sum(row["post_recovery_score"]["passed"] for row in results)
    semantic_ids = [
        row["case"]["case_id"] for row in results if row.get("semantic_review_required")
    ]
    spec = local_model_spec(model_id)
    return {
        "schema_version": REPORT_SCHEMA,
        "response_contract": "assistant_tool_response.v1",
        "model": {
            "id": model_id,
            "revision": spec.revision if spec else None,
            "backend": "local",
            "deterministic": not generation_policy["do_sample"],
        },
        "generation_policy": generation_policy,
        "manifest_sha256": SINGLE_TURN_CASES_SHA256,
        "case_summaries": {
            "total": {
                "expected_case_count": len(expected_case_ids),
                "case_count": len(results),
                "complete": complete,
                "first_generation_passed": raw_passed,
                "post_recovery_passed": post_passed,
            }
        },
        "candidate_gate": {
            "passed": False,
            "fixed_twenty_complete": fixed_complete,
            "post_format_repair_twenty_passed": fixed_complete and post_passed == 20,
            "capture_verified": capture_integrity.get("status") == "verified",
            "semantic_review": {
                "status": "required" if semantic_ids else "not_applicable",
                "case_ids": semantic_ids,
            },
            "claim_boundary": "Structural model scores and observed Host outcomes are separate. Missing replies must identify missing values and request full restatement; information must answer the question. No semantic pass is inferred from any reply or Host rejection. This report does not execute tools or establish GUI acceptance.",
        },
        "results": results,
        "generation_trace": [asdict(entry) for entry in generation_trace],
        "capture_integrity": capture_integrity,
        "rag_protocol": rag_protocol,
        "rag_retrievals": [asdict(row) for row in rag_retrievals],
    }


def report_candidate_passed(report: object) -> bool:
    """Do not silently promote a structural score into semantic acceptance."""
    if not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA:
        return False
    gate = report.get("candidate_gate", {})
    if not isinstance(gate, dict) or not isinstance(gate.get("semantic_review"), dict):
        return False
    return bool(
        report_automated_model_checks_passed(report)
        and gate.get("passed") is True
        and gate.get("fixed_twenty_complete") is True
        and gate.get("post_format_repair_twenty_passed") is True
        and gate.get("capture_verified") is True
        and gate.get("semantic_review", {}).get("status") == "passed"
    )


def report_automated_model_checks_passed(report: object) -> bool:
    """Mechanical gate only: success is not independent semantic acceptance."""
    if not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA:
        return False
    rows = report.get("results", [])
    expected = [asdict(case) for case in load_single_turn_cases()]
    model = report.get("model", {})
    if (
        not isinstance(model, dict)
        or not isinstance(rows, list)
        or any(not isinstance(row, dict) for row in rows)
        or any(
            not isinstance(row.get(key), dict)
            for row in rows
            for key in ("first_generation_score", "post_recovery_score", "trajectory")
        )
        or [row.get("case") for row in rows] != expected
        or model.get("id") != BOUNDED_BASELINE_MODEL_ID
        or model.get("revision") != BOUNDED_BASELINE_MODEL_REVISION
        or report.get("manifest_sha256") != SINGLE_TURN_CASES_SHA256
        or report.get("engine_closed") is not True
        or not all(
            row.get("post_recovery_score", {}).get("passed") is True for row in rows
        )
        or not all(
            type(row.get("first_generation_score", {}).get("passed")) is bool
            for row in rows
        )
    ):
        return False
    trace = report.get("generation_trace", [])
    capture = report.get("capture_integrity", {})
    generation_policy = report.get("generation_policy")
    rag_protocol = report.get("rag_protocol")
    if (
        not isinstance(capture, dict)
        or not isinstance(generation_policy, dict)
        or not isinstance(rag_protocol, dict)
        or not isinstance(trace, list)
        or not 20 <= len(trace) <= 40
        or any(not isinstance(entry, dict) for entry in trace)
        or [entry.get("global_call_index") for entry in trace]
        != list(range(1, len(trace) + 1))
        or capture.get("requested") is not True
        or capture.get("status") != "verified"
        or capture.get("artifact_count") != len(trace)
        or generation_policy.get("max_format_recovery_attempts") != 1
    ):
        return False
    for row in rows:
        trajectory = row.get("trajectory", {})
        entries = [
            entry["global_call_index"]
            for entry in trace
            if entry.get("case_id") == row["case"]["case_id"]
        ]
        attempts = trajectory.get("policy_attempts", [])
        if (
            not isinstance(attempts, list)
            or any(not isinstance(attempt, dict) for attempt in attempts)
            or type(trajectory.get("format_recovery_attempts")) is not int
            or not 1 <= len(entries) <= 2
            or trajectory.get("actual_generation_call_indices") != entries
            or len(attempts) != len(entries)
            or (
                len(entries) == 2
                and attempts[0].get("envelope_status") != "format_error"
            )
            or trajectory.get("format_recovery_attempts") != len(entries) - 1
        ):
            return False
    rag = rag_protocol.get("name")
    if rag == "product_process_rag.v1":
        return all(
            isinstance(row.get("rag_context"), dict)
            and row["rag_context"].get("status") in ("retrieved", "empty")
            for row in rows
        )
    return rag == "product_rag_disabled.v1"


def run_eval(
    config: LLMConfig,
    cases: tuple[TargetEvalCase | TargetChallengeCase | PrecisionCase, ...],
    *,
    checkpoint_path: Path | None = None,
    product_rag: bool = False,
    rag_mode: str | None = None,
) -> dict[str, Any]:
    """Run independent turns via current product assembly and format recovery."""
    if rag_mode is not None and rag_mode not in {"hybrid", "dense", "off"}:
        raise ValueError("Unknown RAG mode")
    product_rag = rag_mode != "off" if rag_mode is not None else product_rag
    selection = config.assistant_runtime_selection()
    registry = target_tool_registry()
    engine = LLMEngine(config)
    lifecycle = (
        ProcessRAGRetrieverLifecycle(dense_only=rag_mode == "dense")
        if product_rag
        else None
    )
    rag_messages = _ProductRAGCaseMessages(registry, lifecycle) if lifecycle else None
    protocol = (
        _product_rag_protocol(dense_only=rag_mode == "dense")
        if product_rag
        else {"name": "product_rag_disabled.v1", "status": "disabled"}
    )
    policy = _evaluation_generation_policy(config)
    capture_request = _capture_audit_request()
    recorder = GenerationTraceRecorder()
    results = []
    selected_cases = [asdict(case) for case in cases]
    case_set_identity = {
        "case_ids": [case.case_id for case in cases],
        "case_count": len(cases),
        "cases_sha256": hashlib.sha256(
            json.dumps(selected_cases, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest(),
        "hash_scope": "Ordered case DTOs including inputs, stages, and scoring expectations.",
    }

    def snapshot(complete: bool) -> dict[str, Any]:
        report = _build_report(
            model_id=selection.model_id,
            results=results,
            expected_case_ids=tuple(case.case_id for case in cases),
            complete=complete,
            generation_policy=policy,
            generation_trace=recorder.entries,
            capture_integrity=_capture_integrity_report(
                capture_request,
                recorder.entries,
                model_id=selection.model_id,
                generation_policy=policy,
            ),
            rag_protocol=protocol,
            rag_retrievals=rag_messages.all_evidence() if rag_messages else [],
        )
        report["case_set_identity"] = case_set_identity
        return report

    def generate(messages: list[dict[str, str]]) -> str:
        return "".join(
            engine.generate_stream(
                messages, profile=GenerationProfile.STRUCTURED_DECISION
            )
        )

    closed = False
    started = perf_counter()
    try:
        engine.load_model()
        model_load_seconds = perf_counter() - started
        for case in cases:
            print(f"Single-turn Assistant: {case.case_id}", file=sys.stderr, flush=True)
            started = perf_counter()
            trajectory = evaluate_case_trajectory(
                case,
                registry,
                generate,
                generation_recorder=recorder,
                product_rag_messages=rag_messages,
            )
            results.append(
                {
                    "suite": "single_turn",
                    "case": asdict(case),
                    "first_generation_score": asdict(trajectory.raw_score),
                    "post_recovery_score": asdict(trajectory.post_recovery_score),
                    "score_scope": (
                        "tool_decision_only; answer_quality_not_scored"
                        if case.case_id.startswith("english_generalization_")
                        else "model_choice_and_historical_content_screening; independent_semantic_review_required"
                    ),
                    "score": asdict(trajectory.final_score),
                    "raw_response": trajectory.final_response,
                    "trajectory": _trajectory_payload(
                        trajectory.attempts, recorder, case_id=case.case_id
                    ),
                    "host_admission": trajectory.host_admission,
                    "product_terminal": trajectory.product_terminal,
                    "semantic_review_required": isinstance(case, PrecisionCase),
                    "decision_seconds": perf_counter() - started,
                    "rag_context": asdict(rag_messages.evidence_for(case))
                    if rag_messages
                    else {"protocol": protocol["name"], "status": "not_requested"},
                }
            )
            if checkpoint_path is not None:
                _write_report(checkpoint_path, snapshot(False))
    finally:
        closed = engine.close()
        if lifecycle is not None:
            lifecycle.close()
    report = snapshot(True)
    report["engine_closed"] = closed
    report["automated_model_checks_passed"] = report_automated_model_checks_passed(
        report
    )
    report["timing"] = {
        "model_load_seconds": model_load_seconds,
        "first_turn_decision_seconds": _duration_summary(
            [row["decision_seconds"] for row in results]
        ),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument(
        "--rag-mode", choices=("hybrid", "dense", "off"), default="hybrid"
    )
    parser.add_argument("--case-id", action="append", default=[])
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--profile",
        choices=("core", "r3-comparison", "english", "recovery"),
        default="core",
        help="Fixed engineering subsets: 20 core, 34 comparison, 6 English, or 8 known format regressions.",
    )
    selection.add_argument(
        "--breadth",
        action="store_true",
        help="Report unchanged 74 historical single-turn questions separately, excluding seven retired continuations.",
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(effective_argv)
    cases = (
        (*load_target_cases(), *load_challenge_cases(), *load_precision_cases())
        if args.breadth
        else load_eval_profile(args.profile)
    )
    if args.case_id:
        unknown = set(args.case_id) - {case.case_id for case in cases}
        if unknown:
            parser.error(f"Unknown fixed case IDs: {sorted(unknown)}")
        cases = tuple(case for case in cases if case.case_id in args.case_id)
    config = _stable_eval_config(LLMConfig.load_from_file(), device=args.device)
    try:
        report = run_eval(
            config, tuple(cases), checkpoint_path=args.json_out, rag_mode=args.rag_mode
        )
    except Exception as exc:
        report = {
            "schema_version": REPORT_SCHEMA,
            "candidate_gate": {"passed": False},
            "failure": f"{type(exc).__name__}: {exc}",
        }
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("Git is required to record evaluation source identity")
    report["experiment_identity"] = {
        "source_sha": subprocess.check_output(  # noqa: S603 - resolved Git, fixed read-only args
            [git_executable, "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_changes_excluding_protected_settings": [
            line
            for line in subprocess.check_output(  # noqa: S603 - resolved Git, fixed read-only args
                [git_executable, "status", "--short"], cwd=ROOT, text=True
            ).splitlines()
            if line[3:] != "settings.json"
        ],
        "single_turn_manifest_sha256": SINGLE_TURN_CASES_SHA256,
    }
    report["invocation"] = {
        "argv": effective_argv,
        "working_directory_is_repository_root": Path.cwd().resolve() == ROOT,
    }
    report["evaluation_profile"] = "breadth" if args.breadth else args.profile
    report["comparison_manifests"] = {
        "english_sha256": ENGLISH_CASES_SHA256,
        "known_format_regressions_sha256": RECOVERY_CASES_SHA256,
        "claim_boundary": "Known historical format failures are regressions, not holdout evidence. English cases use tool-decision scoring; historical answer-quality criteria and scores are unchanged.",
    }
    if args.json_out is not None:
        _write_report(args.json_out, report)
    print(json.dumps(report, indent=2))
    return int(
        not (
            report_automated_model_checks_passed(report)
            if args.strict
            else report.get("case_summaries", {}).get("total", {}).get("complete")
            is True
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
