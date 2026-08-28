#!/usr/bin/env python3
"""Run the bounded Stable-v2 target selection suite against the local model."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.pipeline_stage import PipelineStage
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.assembler import ContextAssembler, PromptToolPublication
from XBrainLab.llm.agent.context_encoding import (
    UntrustedContextItem,
    UntrustedContextSource,
    encode_untrusted_context,
)
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.parser import (
    CommandParser,
    ToolEnvelopeParseResult,
    ToolEnvelopeStatus,
)
from XBrainLab.llm.agent.pending_interaction import PendingInteractionCoordinator
from XBrainLab.llm.agent.prompt_policy import STRICT_TOOL_RESPONSE_PROMPT_POLICY
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
DEFAULT_CASES = ROOT / "XBrainLab" / "llm" / "rag" / "data" / "gold_set.json"
DEFAULT_CHALLENGES = ROOT / "scripts" / "dev" / "stable_assistant_challenge_cases.json"
DEFAULT_PRECISION_CASES = (
    ROOT / "scripts" / "dev" / "stable_assistant_no_action_precision_cases.json"
)
DEFAULT_CLARIFICATION_CASES = (
    ROOT / "scripts" / "dev" / "stable_assistant_clarification_cases.json"
)
REPORT_SCHEMA = "xbrainlab.stable_assistant_model_eval.v8"
PRECISION_CASE_COUNT = 24
CLARIFICATION_CASE_COUNT = 7
MISSING_PARAMETER_HOST_TOOLS = {
    "missing_bandpass_bounds_01": "apply_bandpass_filter",
    "missing_notch_frequency_01": "apply_notch_filter",
    "missing_resample_rate_01": "resample_data",
    "missing_reference_method_01": "set_reference",
    "missing_normalization_method_01": "normalize_data",
}
DIRECT_PARAMETER_TOOLS = frozenset(MISSING_PARAMETER_HOST_TOOLS.values())


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
    """One bilingual no-action outcome case against the product boundary."""

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
    """One production-policy classification in a bounded generation trajectory."""

    attempt_number: int
    response: str
    envelope_status: str
    workflow_stage: str | None
    recovery_action: str
    taxonomy: str
    recovery_attempts_after: int


@dataclass(frozen=True, slots=True)
class CaseTrajectoryResult:
    """Raw and final scores for one product-like strict-envelope trajectory."""

    raw_score: TargetEvalScore
    final_score: TargetEvalScore
    final_response: str
    attempts: tuple[ModelGenerationAttempt, ...]


@dataclass(frozen=True, slots=True)
class ClarificationAdmission:
    """One controller-admitted typed receipt retained for evaluator follow-up."""

    receipt: AssistantToolInputReceipt
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
    for stage, config in STAGE_CONFIG.items():
        if tool_name in config["tools"]:
            return stage
    raise ValueError(f"Target tool has no backend stage publication: {tool_name}")


def load_target_cases(path: Path = DEFAULT_CASES) -> tuple[TargetEvalCase, ...]:
    """Load the bilingual target examples and reject catalog drift."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load target model eval cases: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("Target model eval cases must be one JSON array.")

    approved = AGENT_ACTION_CONTRACTS.model_tool_names()
    cases: list[TargetEvalCase] = []
    seen_ids: set[str] = set()
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
    """Load the separately versioned bilingual no-action precision corpus."""
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
            "zh",
        }:
            raise ValueError(f"Precision {category} cases must be bilingual.")
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


def _stage_catalog(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    registry: ToolRegistry,
) -> tuple[PipelineStage, str]:
    stage = PipelineStage(case.workflow_stage)
    allowed_tools = list(STAGE_CONFIG[stage]["tools"])
    assembler = ContextAssembler(
        registry,
        object(),
        application_runtime=object(),  # type: ignore[arg-type]
    )
    return stage, assembler._format_tools(
        allowed_tools,
        workflow_stage=stage.value,
    )


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
        self._max_tool_executions = 5
        self._pending_interactions = PendingInteractionCoordinator()
        self._history: list[dict[str, str]] = []
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

    def _latest_user_request_text(self) -> str:
        return LLMController._latest_user_request_text(self)  # type: ignore[arg-type]

    def _active_policy_mode(self) -> str:
        return LLMController._active_policy_mode(self)  # type: ignore[arg-type]

    def _remaining_tool_input_question(self, receipt: AssistantToolInputReceipt) -> str:
        return LLMController._remaining_tool_input_question(receipt)

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

    def evaluate_proposal(
        self,
        response: str,
    ) -> tuple[ToolAttemptDecision | None, dict[str, Any] | None]:
        envelope = CommandParser.parse_product(response)
        if envelope.status is not ToolEnvelopeStatus.VALID:
            return None, None
        command = LLMController._select_tool_proposal(  # type: ignore[arg-type]
            self,
            list(envelope.commands),
        )
        if command is None:
            return None, None
        decision = LLMController._evaluate_tool_proposal(  # type: ignore[arg-type]
            self,
            command,
            response,
        )
        return decision, command[1]


def _precision_application_publication(
    case: PrecisionCase,
) -> ApplicationViewPublication:
    """Build the smallest backend state that truthfully represents one case."""
    stage = PipelineStage(case.workflow_stage)
    state = ApplicationStateSnapshot.empty()
    if stage is PipelineStage.DATA_LOADED:
        state = replace(
            state,
            pipeline_stage=stage.value,
            raw=replace(state.raw, loaded=True, count=1),
            active_dataset=replace(state.active_dataset, has_raw_data=True),
        )
    elif stage is not PipelineStage.EMPTY:
        raise ValueError(
            "Precision capability fixtures currently support only empty and "
            "data_loaded stages."
        )
    return ApplicationViewPublication(
        generation=1,
        state=state,
        capabilities=build_capability_policy(state),
    )


def _precision_case_projection(
    case: PrecisionCase,
    registry: ToolRegistry,
) -> tuple[
    list[dict[str, str]],
    PromptToolPublication,
    ApplicationViewPublication,
]:
    """Build one precision request and admission publication from backend truth."""
    publication = _precision_application_publication(case)
    runtime = _EvaluatorApplicationRuntime(publication)
    assembler = ContextAssembler(
        registry,
        _PublicationBackedEvaluatorStudy(),
        application_runtime=runtime,
    )
    messages = assembler.get_messages([{"role": "user", "content": case.user_input}])
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
    """Project an admitted production receipt through the product assembler."""
    if (
        case.trajectory_kind == "direct" and source.case_id != case.source_case_id
    ) or source.category != "missing_parameter":
        raise ValueError("Clarification source does not match its missing case.")
    publication = _precision_application_publication(source)
    assembler = ContextAssembler(
        registry,
        _PublicationBackedEvaluatorStudy(),
        application_runtime=_EvaluatorApplicationRuntime(publication),
    )
    assembler.set_tool_input_receipt(receipt)
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
    """Build the product strict contract with the case's stage tool projection."""
    if isinstance(case, PrecisionCase):
        messages, _prompt_publication, _backend_publication = (
            _precision_case_projection(case, registry)
        )
        return messages

    # The evaluator deliberately reuses the product formatter so schemas cannot drift.
    stage, catalog = _stage_catalog(case, registry)
    system = (
        ContextAssembler._ACTION_SYSTEM_PROMPT
        + "\n"
        + STRICT_TOOL_RESPONSE_PROMPT_POLICY.decision_instructions(stage.value)
        + "\nAction Contract Catalog (input definitions, never an output array):\n"
        + catalog
        + "\nOnly the listed workflow actions are available at this stage."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": case.user_input},
    ]


def _build_recovery_case_messages(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    registry: ToolRegistry,
    recovery_messages: tuple[str, ...],
) -> list[dict[str, str]]:
    """Rebuild the eval request with the product's untrusted recovery-note encoding."""
    messages = build_case_messages(case, registry)
    context = encode_untrusted_context(
        tuple(
            UntrustedContextItem(
                item_type="runtime_context",
                source=UntrustedContextSource(kind="assistant_runtime_context"),
                data={"text": content},
            )
            for content in recovery_messages
        )
    )
    return [messages[0], {"role": "user", "content": context}, messages[-1]]


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
    _messages, prompt_publication, backend_publication = _precision_case_projection(
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


def _score_case_response(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    response: str,
    registry: ToolRegistry,
) -> TargetEvalScore:
    if isinstance(case, PrecisionCase):
        return score_precision_response(case, response, registry)
    if isinstance(case, TargetChallengeCase):
        return score_challenge_response(case, response, registry)
    return score_model_response(case, response, registry)


def _recovery_envelope(
    response: str,
    *,
    workflow_stage: str,
) -> tuple[ToolEnvelopeParseResult, str | None]:
    """Apply the controller's exact stage check before recovery classification."""
    parsed = CommandParser.parse_product(response)
    parsed_stage = parsed.workflow_stage
    if (
        parsed.status is not ToolEnvelopeStatus.FORMAT_ERROR
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
    generate_response: Callable[[list[dict[str, str]]], str],
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
        response = response.strip()
        if raw_score is None:
            raw_score = score_response(response)

        envelope, parsed_stage = _recovery_envelope(
            response,
            workflow_stage=workflow_stage,
        )
        decision = DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY.decide(
            StrictEnvelopeRecoveryRequest(
                envelope=envelope,
                recovery_attempts_used=len(recovery_messages),
            )
        )
        attempts.append(
            ModelGenerationAttempt(
                attempt_number=len(attempts) + 1,
                response=response[:1000],
                envelope_status=envelope.status.value,
                workflow_stage=parsed_stage,
                recovery_action=decision.action.value,
                taxonomy=decision.taxonomy.value,
                recovery_attempts_after=decision.recovery_attempts_after,
            )
        )

        if decision.action is StrictEnvelopeRecoveryAction.RETRY_FORMAT:
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
            final_score=final_score,
            final_response=response,
            attempts=tuple(attempts),
        )


def evaluate_case_trajectory(
    case: TargetEvalCase | TargetChallengeCase | PrecisionCase,
    registry: ToolRegistry,
    generate_response: Callable[[list[dict[str, str]]], str],
) -> CaseTrajectoryResult:
    """Generate and score one case through the product strict-recovery policy."""

    def messages(recovery: tuple[str, ...]) -> list[dict[str, str]]:
        return (
            _build_recovery_case_messages(case, registry, recovery)
            if recovery
            else build_case_messages(case, registry)
        )

    return _evaluate_trajectory(
        workflow_stage=case.workflow_stage,
        build_messages=messages,
        score_response=lambda response: _score_case_response(
            case,
            response,
            registry,
        ),
        generate_response=generate_response,
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
    _messages, prompt_publication, backend_publication = _precision_case_projection(
        source,
        registry,
    )
    harness = _EvaluatorControllerHarness(
        registry=registry,
        publication=backend_publication,
    )
    harness.begin_turn(source.user_input, prompt_publication)
    receipt = harness.admit_typed_response(response)
    if receipt is None or receipt.command_name != expected_tool:
        return None
    return ClarificationAdmission(
        receipt=receipt,
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
) -> CaseTrajectoryResult:
    """Generate an admitted receipt-backed second turn through recovery policy."""
    harness = admission.harness
    receipt = harness.begin_turn(case.reply, admission.prompt_publication)
    if receipt is None:
        raise RuntimeError("Controller did not activate the admitted clarification.")
    observed: dict[str, TargetEvalScore] = {}

    def score(response: str) -> TargetEvalScore:
        cached = observed.get(response)
        if cached is not None:
            return cached
        envelope = CommandParser.parse_product(response)
        decision, _supplied = harness.evaluate_proposal(response)
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

    return _evaluate_trajectory(
        workflow_stage=source.workflow_stage,
        build_messages=lambda recovery: build_clarification_messages(
            case,
            source,
            receipt=receipt,
            registry=registry,
            recovery_messages=recovery,
        )[0],
        score_response=score,
        generate_response=generate_response,
    )


def evaluate_discriminated_clarification_trajectory(
    case: ClarificationCase,
    registry: ToolRegistry,
    generate_response: Callable[[list[dict[str, str]]], str],
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
    first_trajectory = evaluate_case_trajectory(first, registry, generate_response)
    first_envelope = CommandParser.parse_product(first_trajectory.final_response)
    if case.trajectory_kind == "generic_filter_selection":
        first_ok = (
            first_trajectory.final_score.passed
            and first_envelope.status is ToolEnvelopeStatus.NO_TOOL
            and not first_envelope.pending_action
        )
        action_request = "bandpass"
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
            source, registry, generate_response
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
            final_score=failed,
            final_response=action_trajectory.final_response,
            attempts=(
                first_trajectory.attempts
                if action_trajectory is first_trajectory
                else first_trajectory.attempts + action_trajectory.attempts
            ),
        )
    if case.trajectory_kind == "partial_bandpass_accumulation":
        harness = admission.harness
        partial_case = replace(case, reply=case.turns[1])
        receipt = harness.begin_turn(case.turns[1], admission.prompt_publication)
        if receipt is None:
            raise RuntimeError("Controller did not activate partial clarification.")
        messages, _prompt, _backend = build_clarification_messages(
            partial_case, source, receipt=receipt, registry=registry
        )
        partial_response = generate_response(messages)
        partial_decision, partial_parameters = harness.evaluate_proposal(
            partial_response
        )
        requeued = harness.pending_interactions.tool_input
        if (
            partial_decision is None
            or partial_decision.action is not ToolAttemptAction.RESPOND
            or partial_parameters != {"low_freq": 12}
            or requeued is None
            or dict(requeued.verified_parameters) != {"low_freq": 12}
            or requeued.remaining_reply_budget != 1
        ):
            failed = replace(
                action_trajectory.final_score,
                passed=False,
                failure_type="partial_accumulation",
                detail="Controller did not verify and requeue the partial reply.",
            )
            return CaseTrajectoryResult(
                first_trajectory.raw_score,
                failed,
                partial_response,
                first_trajectory.attempts + action_trajectory.attempts,
            )
    final_case = replace(case, reply=case.turns[2])
    final_trajectory = evaluate_clarification_trajectory(
        final_case,
        source,
        admission=admission,
        registry=registry,
        generate_response=generate_response,
    )
    return CaseTrajectoryResult(
        raw_score=first_trajectory.raw_score,
        final_score=final_trajectory.final_score,
        final_response=final_trajectory.final_response,
        attempts=(
            first_trajectory.attempts + final_trajectory.attempts
            if action_trajectory is first_trajectory
            else first_trajectory.attempts
            + action_trajectory.attempts
            + final_trajectory.attempts
        ),
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


def _build_report(
    *,
    model_id: str,
    results: list[dict[str, Any]],
    expected_case_count: int,
    complete: bool,
    generation_policy: dict[str, Any] | None = None,
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
    raw_generation_summary: dict[str, dict[str, int]] = {}
    for suite in ("positive", "challenge", "precision", "clarification"):
        suite_rows = [row for row in results if row.get("suite") == suite]
        raw_passed = sum(
            bool(row.get("raw_score", row["score"])["passed"]) for row in suite_rows
        )
        raw_generation_summary[suite] = {
            "case_count": len(suite_rows),
            "passed_count": raw_passed,
            "failed_count": len(suite_rows) - raw_passed,
        }
    positive_passed = suite_summary["positive"]["passed_count"]
    positive_guard_rows = [
        row["parameter_origin_guard"]
        for row in results
        if isinstance(row.get("parameter_origin_guard"), dict)
        and row["parameter_origin_guard"].get("applicable") is True
    ]
    positive_guard_passed = sum(bool(row.get("passed")) for row in positive_guard_rows)
    host_guard_rows = [
        row["host_guard"]
        for row in results
        if isinstance(row.get("host_guard"), dict)
        and row["host_guard"].get("applicable") is True
    ]
    host_guard_passed = sum(bool(row.get("passed")) for row in host_guard_rows)
    frozen_core_passed = bool(
        complete
        and expected_case_count == 50
        and len(core_rows) == 50
        and suite_summary["positive"]["case_count"] == 36
        and positive_passed == 36
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
    candidate_passed = (
        frozen_core_passed and precision_passed_gate and clarification_passed_gate
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
        "target_surface": sorted(AGENT_ACTION_CONTRACTS.model_tool_names()),
        "suite_summary": suite_summary,
        "raw_generation_summary": raw_generation_summary,
        "candidate_gate": {
            "positive_exact": {"required": 36, "passed": positive_passed},
            "explicit_parameter_host_guard": {
                "required": 10,
                "passed": positive_guard_passed,
            },
            "missing_parameter_host_guard": {
                "required": 5,
                "passed": host_guard_passed,
            },
            "frozen_core_passed": frozen_core_passed,
            "precision_no_action": {
                "required": PRECISION_CASE_COUNT,
                "passed": precision_passed,
            },
            "clarification_continuation": {
                "required": CLARIFICATION_CASE_COUNT,
                "passed": clarification_passed,
            },
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
            "Frozen bilingual core preserves exact selection for 36 complete requests plus the "
            "deterministic host parameter-origin boundary for five missing-value "
            "requests. Candidate gates use the final bounded strict-envelope recovery, "
            "parser, attempt, and presentation outcome. Seven controller-backed "
            "clarification trajectories (five direct actions, generic filter selection, "
            "and partial bandpass accumulation) must reach the verified execution boundary; "
            "raw first-generation scores remain separate diagnostics. These suites are not "
            "workflow success or thesis-grade model accuracy."
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
        "max_format_recovery_attempts": (
            DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY.max_recovery_attempts
        ),
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
    results: list[dict[str, Any]] = []
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
                lambda messages: "".join(
                    engine.generate_stream(
                        messages,
                        profile=GenerationProfile.STRUCTURED_DECISION,
                    )
                ),
            )
            response = trajectory.final_response
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
            raw_score_payload = asdict(trajectory.raw_score)
            if trajectory.raw_score.product_outcome is None:
                raw_score_payload.pop("product_outcome")
            row = {
                "suite": suite,
                "case": asdict(case),
                "raw_score": raw_score_payload,
                "score": score_payload,
                "trajectory": {
                    "attempts": [asdict(attempt) for attempt in trajectory.attempts],
                    "recovery_attempts_used": len(trajectory.attempts) - 1,
                    "terminal_action": trajectory.attempts[-1].recovery_action,
                    "terminal_taxonomy": trajectory.attempts[-1].taxonomy,
                },
            }
            if isinstance(case, TargetEvalCase) and (
                case.expected_tool in DIRECT_PARAMETER_TOOLS
            ):
                row["parameter_origin_guard"] = score_positive_parameter_host_guard(
                    case,
                    response,
                    registry,
                )
            if isinstance(case, TargetChallengeCase) and (
                case.case_id in MISSING_PARAMETER_HOST_TOOLS
            ):
                row["host_guard"] = score_missing_parameter_host_guard(
                    case,
                    response,
                    registry,
                )
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
                    lambda messages: "".join(
                        engine.generate_stream(
                            messages,
                            profile=GenerationProfile.STRUCTURED_DECISION,
                        )
                    ),
                )
                score_payload = asdict(trajectory.final_score)
                raw_score_payload = asdict(trajectory.raw_score)
                attempts = [asdict(attempt) for attempt in trajectory.attempts]
                source = None
                source_has_receipt = True
            else:
                source = precision_by_id[case.source_case_id]
                source_row = result_by_id[case.source_case_id]
                source_score = source_row["score"]
                admission = (
                    admit_clarification_receipt(
                        source,
                        str(source_score.get("response", "")),
                        expected_tool=case.expected_tool,
                        registry=registry,
                    )
                    if source_score.get("passed") is True
                    else None
                )
                source_has_receipt = admission is not None
                if admission is not None:
                    trajectory = evaluate_clarification_trajectory(
                        case,
                        source,
                        admission=admission,
                        registry=registry,
                        generate_response=lambda messages: "".join(
                            engine.generate_stream(
                                messages,
                                profile=GenerationProfile.STRUCTURED_DECISION,
                            )
                        ),
                    )
                    score_payload = asdict(trajectory.final_score)
                    raw_score_payload = asdict(trajectory.raw_score)
                    attempts = [asdict(attempt) for attempt in trajectory.attempts]
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
                    raw_score_payload = dict(score_payload)
                    attempts = []
            if score_payload.get("product_outcome") is None:
                score_payload.pop("product_outcome", None)
            if raw_score_payload.get("product_outcome") is None:
                raw_score_payload.pop("product_outcome", None)
            results.append(
                {
                    "suite": "clarification",
                    "case": asdict(case),
                    "source_case": asdict(source) if source is not None else None,
                    "source_has_host_receipt": source_has_receipt,
                    "raw_score": raw_score_payload,
                    "score": score_payload,
                    "trajectory": {
                        "attempts": attempts,
                        "recovery_attempts_used": max(len(attempts) - 1, 0),
                        "terminal_action": (
                            attempts[-1]["recovery_action"] if attempts else None
                        ),
                        "terminal_taxonomy": (
                            attempts[-1]["taxonomy"] if attempts else None
                        ),
                    },
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
    )


def main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

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
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_out is not None:
        _write_report(args.json_out, report)
    passed = bool(report.get("summary", {}).get("passed"))
    return 1 if args.strict and not passed else 0


if __name__ == "__main__":
    raise SystemExit(main())
