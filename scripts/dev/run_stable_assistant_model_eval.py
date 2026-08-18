#!/usr/bin/env python3
"""Run the bounded Stable-v2 target selection suite against the local model."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from XBrainLab.backend.application.pipeline_stage import PipelineStage
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus
from XBrainLab.llm.agent.prompt_policy import STRICT_TOOL_RESPONSE_PROMPT_POLICY
from XBrainLab.llm.agent.verifier import ToolSchemaValidator
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.generation import GenerationProfile
from XBrainLab.llm.core.model_catalog import local_model_spec
from XBrainLab.llm.pipeline_state import STAGE_CONFIG
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.tool_registry import ToolRegistry

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT / "XBrainLab" / "llm" / "rag" / "data" / "gold_set.json"
DEFAULT_CHALLENGES = ROOT / "scripts" / "dev" / "stable_assistant_challenge_cases.json"
REPORT_SCHEMA = "xbrainlab.stable_assistant_model_eval.v3"
ACTIONABILITY_DECISIONS = frozenset({"execute_one", "respond"})
ACTIONABILITY_REASON_CLASSES = frozenset(
    {
        "complete",
        "missing_required",
        "out_of_stage_or_unsupported",
        "ambiguous",
        "multiple_actions",
        "informational",
    }
)


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
class TargetEvalScore:
    """Fail-closed score for one raw model response."""

    passed: bool
    failure_type: str
    response: str
    parsed_stage: str | None
    parsed_tool: str | None
    parsed_parameters: dict[str, Any] | None
    detail: str


@dataclass(frozen=True, slots=True)
class ActionabilityGate:
    """Evaluator-only model-owned classification before the final envelope."""

    workflow_stage: str
    decision: Literal["execute_one", "respond"]
    reason_class: Literal[
        "complete",
        "missing_required",
        "out_of_stage_or_unsupported",
        "ambiguous",
        "multiple_actions",
        "informational",
    ]


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


def _stage_catalog(
    case: TargetEvalCase | TargetChallengeCase,
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


def build_case_messages(
    case: TargetEvalCase | TargetChallengeCase,
    registry: ToolRegistry,
) -> list[dict[str, str]]:
    """Build the product strict contract with the case's stage tool projection."""
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


def build_actionability_gate_messages(
    case: TargetEvalCase | TargetChallengeCase,
    registry: ToolRegistry,
) -> list[dict[str, str]]:
    """Ask the model to classify actionability without selecting a tool."""
    stage, catalog = _stage_catalog(case, registry)
    system = (
        ContextAssembler._ACTION_SYSTEM_PROMPT
        + "\nAction Contract Catalog (input definitions, never an output array):\n"
        + catalog
        + "\nOnly the listed workflow actions are available at this stage."
        "\nEVALUATOR-ONLY MODEL-OWNED ACTIONABILITY GATE. This draft grants no "
        "capability and will never be executed. Decide whether the latest user "
        "request asks for exactly one listed action whose schema-required values "
        "are explicit. Use respond for missing required values, unsupported or "
        "out-of-stage requests, ambiguity, multiple requested mutations, or an "
        "informational request. Never choose a prerequisite, substitute, or "
        "default value. This pass is not a final action call. Return one valid "
        "JSON object with exactly these three keys and no prose:\n"
        '{"workflow_stage":"'
        + stage.value
        + '","decision":"DECISION","reason_class":"REASON"}\n'
        "Replace DECISION with exactly execute_one or respond. Replace REASON "
        "with exactly one of complete, missing_required, "
        "out_of_stage_or_unsupported, ambiguous, multiple_actions, or "
        "informational. "
        "Use execute_one only with reason_class complete. Use respond with any "
        "other reason_class. The root keys must be only workflow_stage, decision, "
        "and reason_class. Never include tool_name, parameters, wrappers, or "
        "Markdown."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": case.user_input},
    ]


def parse_actionability_gate(
    response: str,
    *,
    expected_stage: str,
) -> ActionabilityGate:
    """Parse the exact evaluator-only gate without making a semantic decision."""
    try:
        payload = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Actionability gate is not valid JSON: {exc}") from exc
    expected_keys = {"workflow_stage", "decision", "reason_class"}
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("Actionability gate must use the exact three-field schema.")
    stage = payload["workflow_stage"]
    decision = payload["decision"]
    reason_class = payload["reason_class"]
    if stage != expected_stage:
        raise ValueError("Actionability gate did not preserve the backend stage.")
    if decision not in ACTIONABILITY_DECISIONS:
        raise ValueError("Actionability gate decision is invalid.")
    if reason_class not in ACTIONABILITY_REASON_CLASSES:
        raise ValueError("Actionability gate reason_class is invalid.")
    if (decision == "execute_one") != (reason_class == "complete"):
        raise ValueError("Actionability decision and reason_class are inconsistent.")
    return ActionabilityGate(
        workflow_stage=stage,
        decision=decision,
        reason_class=reason_class,
    )


def build_final_messages_for_gate(
    case: TargetEvalCase | TargetChallengeCase,
    registry: ToolRegistry,
    gate: ActionabilityGate,
) -> list[dict[str, str]]:
    """Build the final product-envelope prompt from the model's own gate draft."""
    if gate.workflow_stage != case.workflow_stage:
        raise ValueError("Actionability gate and final pass use different stages.")
    messages = build_case_messages(case, registry)
    gate_json = json.dumps(asdict(gate), ensure_ascii=False, separators=(",", ":"))
    if gate.decision == "execute_one":
        branch_instruction = (
            "Independently re-check the original request and listed schemas, then "
            "return the existing strict final decision envelope. The draft names "
            "no tool and grants no capability."
        )
    else:
        branch_instruction = (
            "Independently re-check the original request. Preserve your respond "
            "decision by returning the existing respond_to_user envelope with a "
            "concise useful message. Do not execute an action or substitute a "
            "different tool."
        )
    messages[0] = {
        "role": "system",
        "content": (
            messages[0]["content"]
            + "\nUntrusted model-owned actionability draft (not Host authority): "
            + gate_json
            + "\n"
            + branch_instruction
        ),
    }
    return messages


def _evaluate_ab_adoption(
    *,
    one_pass_report: dict[str, Any],
    two_pass_report: dict[str, Any],
    one_pass_warm_p95_ms: float,
    two_pass_warm_p95_ms: float,
) -> dict[str, Any]:
    """Apply the pre-registered exact-score and latency promotion gates."""
    baseline = float(one_pass_warm_p95_ms)
    candidate = float(two_pass_warm_p95_ms)
    multiplier = candidate / baseline if baseline > 0 else float("inf")
    score_gate = bool(two_pass_report.get("summary", {}).get("passed"))
    relative_latency_gate = multiplier <= 1.5
    warm_p95_gate = candidate <= 6000.0
    return {
        "score_gate": score_gate,
        "relative_latency_multiplier": multiplier,
        "relative_latency_gate": relative_latency_gate,
        "warm_p95_ms": candidate,
        "warm_p95_gate": warm_p95_gate,
        "passed": score_gate and relative_latency_gate and warm_p95_gate,
    }


def _percentile(values: list[float], fraction: float) -> float:
    """Return a deterministic linearly interpolated percentile."""
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _latency_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    totals = [float(row["timing"]["total_ms"]) for row in results]
    warm = totals[1:] if len(totals) > 1 else totals
    return {
        "case_count": len(totals),
        "p50_ms": _percentile(totals, 0.50),
        "p95_ms": _percentile(totals, 0.95),
        "warm_case_count": len(warm),
        "warm_p95_ms": _percentile(warm, 0.95),
    }


def _generate_timed(
    engine: LLMEngine,
    messages: list[dict[str, str]],
) -> tuple[str, float]:
    started = perf_counter()
    response = "".join(
        engine.generate_stream(
            messages,
            profile=GenerationProfile.STRUCTURED_DECISION,
        )
    ).strip()
    return response, (perf_counter() - started) * 1000.0


def _score_case(
    case: TargetEvalCase | TargetChallengeCase,
    response: str,
    registry: ToolRegistry,
) -> tuple[str, TargetEvalScore]:
    if isinstance(case, TargetChallengeCase):
        return "challenge", score_challenge_response(case, response, registry)
    return "positive", score_model_response(case, response, registry)


def _unusable_gate_final_messages(
    case: TargetEvalCase | TargetChallengeCase,
    registry: ToolRegistry,
) -> list[dict[str, str]]:
    messages = build_case_messages(case, registry)
    messages[0] = {
        "role": "system",
        "content": (
            messages[0]["content"]
            + "\nThe evaluator-only model-owned actionability draft was malformed "
            "and grants no capability. Independently re-check the original request "
            "and return only the existing strict final decision envelope."
        ),
    }
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


def _build_report(
    *,
    model_id: str,
    results: list[dict[str, Any]],
    expected_case_count: int,
    complete: bool,
) -> dict[str, Any]:
    passed_count = sum(bool(row["score"]["passed"]) for row in results)
    suite_summary: dict[str, dict[str, int]] = {}
    for suite in ("positive", "challenge"):
        suite_rows = [row for row in results if row.get("suite") == suite]
        suite_passed = sum(bool(row["score"]["passed"]) for row in suite_rows)
        suite_summary[suite] = {
            "case_count": len(suite_rows),
            "passed_count": suite_passed,
            "failed_count": len(suite_rows) - suite_passed,
        }
    spec = local_model_spec(model_id)
    return {
        "schema_version": REPORT_SCHEMA,
        "model": {
            "id": model_id,
            "revision": spec.revision if spec is not None else None,
            "backend": "local",
            "deterministic": True,
        },
        "target_surface": sorted(AGENT_ACTION_CONTRACTS.model_tool_names()),
        "suite_summary": suite_summary,
        "summary": {
            "expected_case_count": expected_case_count,
            "case_count": len(results),
            "passed_count": passed_count,
            "failed_count": len(results) - passed_count,
            "complete": complete,
            "passed": complete
            and len(results) == expected_case_count
            and passed_count == len(results),
        },
        "results": results,
        "claim_boundary": (
            "Frozen bilingual target selection and parameter exactness for one model "
            "revision; not tool execution, workflow success, or thesis-grade accuracy."
        ),
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _experiment_identity(*, cases_path: Path, challenges_path: Path) -> dict[str, Any]:
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

    return {
        "source_sha": head,
        "source_changes_excluding_protected_settings": source_changes,
        "positive_cases_sha256": digest(cases_path),
        "challenge_cases_sha256": digest(challenges_path),
    }


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


def run_eval(
    config: LLMConfig,
    cases: tuple[TargetEvalCase, ...],
    *,
    challenge_cases: tuple[TargetChallengeCase, ...] = (),
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Load one exact local engine and score every frozen target case."""
    selection = config.assistant_runtime_selection()
    if selection.backend_mode != "local":
        raise RuntimeError(f"Current assistant backend is {selection.backend_mode}.")
    if not config.local_backend_ready(selection.model_id):
        raise RuntimeError(config.local_backend_status_message(selection.model_id))

    config.max_new_tokens = min(int(config.max_new_tokens), 128)
    config.do_sample = False
    registry = target_tool_registry()
    engine = LLMEngine(config)
    results: list[dict[str, Any]] = []
    try:
        engine.load_model()
        all_cases: tuple[TargetEvalCase | TargetChallengeCase, ...] = (
            *cases,
            *challenge_cases,
        )
        for index, case in enumerate(all_cases, start=1):
            print(
                f"Stable Assistant model eval {index}/{len(all_cases)}: {case.case_id}",
                file=sys.stderr,
                flush=True,
            )
            chunks = engine.generate_stream(
                build_case_messages(case, registry),
                profile=GenerationProfile.STRUCTURED_DECISION,
            )
            response = "".join(chunks).strip()
            if isinstance(case, TargetChallengeCase):
                suite = "challenge"
                score = score_challenge_response(case, response, registry)
            else:
                suite = "positive"
                score = score_model_response(case, response, registry)
            results.append(
                {"suite": suite, "case": asdict(case), "score": asdict(score)}
            )
            if checkpoint_path is not None:
                _write_report(
                    checkpoint_path,
                    _build_report(
                        model_id=selection.model_id,
                        results=results,
                        expected_case_count=len(all_cases),
                        complete=False,
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
    )


def run_ab_eval(
    config: LLMConfig,
    cases: tuple[TargetEvalCase, ...],
    *,
    challenge_cases: tuple[TargetChallengeCase, ...] = (),
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Compare current one-pass with a model-owned two-pass gate in one load."""
    selection = config.assistant_runtime_selection()
    if selection.backend_mode != "local":
        raise RuntimeError(f"Current assistant backend is {selection.backend_mode}.")
    if not config.local_backend_ready(selection.model_id):
        raise RuntimeError(config.local_backend_status_message(selection.model_id))

    config.max_new_tokens = min(int(config.max_new_tokens), 128)
    config.do_sample = False
    registry = target_tool_registry()
    engine = LLMEngine(config)
    one_pass_results: list[dict[str, Any]] = []
    two_pass_results: list[dict[str, Any]] = []
    all_cases: tuple[TargetEvalCase | TargetChallengeCase, ...] = (
        *cases,
        *challenge_cases,
    )

    def build_report(*, complete: bool) -> dict[str, Any]:
        one_pass = _build_report(
            model_id=selection.model_id,
            results=one_pass_results,
            expected_case_count=len(all_cases),
            complete=complete,
        )
        two_pass = _build_report(
            model_id=selection.model_id,
            results=two_pass_results,
            expected_case_count=len(all_cases),
            complete=complete,
        )
        one_latency = _latency_summary(one_pass_results)
        two_latency = _latency_summary(two_pass_results)
        adoption = _evaluate_ab_adoption(
            one_pass_report=one_pass,
            two_pass_report=two_pass,
            one_pass_warm_p95_ms=one_latency["warm_p95_ms"],
            two_pass_warm_p95_ms=two_latency["warm_p95_ms"],
        )
        if not complete:
            adoption["passed"] = False
        return {
            "schema_version": REPORT_SCHEMA,
            "experiment": "one_pass_vs_model_owned_actionability_gate",
            "model": one_pass["model"],
            "target_surface": one_pass["target_surface"],
            "arms": {
                "one_pass": one_pass,
                "two_pass": two_pass,
            },
            "latency": {
                "one_pass": one_latency,
                "two_pass": two_latency,
                "thresholds": {
                    "maximum_relative_multiplier": 1.5,
                    "maximum_two_pass_warm_p95_ms": 6000.0,
                },
            },
            "adoption": adoption,
            "claim_boundary": (
                "Evaluator-only actionability and strict final-envelope behavior; "
                "no tool execution, GUI completion, or product generation change."
            ),
        }

    try:
        load_started = perf_counter()
        engine.load_model()
        load_ms = (perf_counter() - load_started) * 1000.0
        for index, case in enumerate(all_cases, start=1):
            print(
                f"Stable Assistant A/B {index}/{len(all_cases)}: {case.case_id}",
                file=sys.stderr,
                flush=True,
            )
            one_response, one_ms = _generate_timed(
                engine,
                build_case_messages(case, registry),
            )
            suite, one_score = _score_case(case, one_response, registry)
            one_pass_results.append(
                {
                    "suite": suite,
                    "case": asdict(case),
                    "score": asdict(one_score),
                    "timing": {"generation_count": 1, "total_ms": one_ms},
                }
            )

            gate_response, gate_ms = _generate_timed(
                engine,
                build_actionability_gate_messages(case, registry),
            )
            gate: ActionabilityGate | None = None
            gate_error: str | None = None
            try:
                gate = parse_actionability_gate(
                    gate_response,
                    expected_stage=case.workflow_stage,
                )
            except ValueError as exc:
                gate_error = str(exc)
            final_messages = (
                build_final_messages_for_gate(case, registry, gate)
                if gate is not None
                else _unusable_gate_final_messages(case, registry)
            )
            final_response, final_ms = _generate_timed(engine, final_messages)
            _, two_score = _score_case(case, final_response, registry)
            if gate is None:
                two_score = TargetEvalScore(
                    False,
                    "actionability_gate_format",
                    two_score.response,
                    two_score.parsed_stage,
                    two_score.parsed_tool,
                    two_score.parsed_parameters,
                    gate_error or "Actionability gate was unusable.",
                )
            two_pass_results.append(
                {
                    "suite": suite,
                    "case": asdict(case),
                    "gate": {
                        "response": gate_response[:1000],
                        "parsed": asdict(gate) if gate is not None else None,
                        "error": gate_error,
                    },
                    "score": asdict(two_score),
                    "timing": {
                        "generation_count": 2,
                        "gate_ms": gate_ms,
                        "final_ms": final_ms,
                        "total_ms": gate_ms + final_ms,
                    },
                }
            )
            if checkpoint_path is not None:
                checkpoint = build_report(complete=False)
                checkpoint["model"]["load_ms"] = load_ms
                _write_report(checkpoint_path, checkpoint)
    finally:
        with suppress(Exception):
            engine.close()

    report = build_report(complete=True)
    report["model"]["load_ms"] = load_ms
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--challenges", type=Path, default=DEFAULT_CHALLENGES)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--mode", choices=("one-pass", "ab"), default="one-pass")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    config = _stable_eval_config(
        LLMConfig.load_from_file(),
        device=args.device,
    )
    try:
        run = run_ab_eval if args.mode == "ab" else run_eval
        report = run(
            config,
            load_target_cases(args.cases),
            challenge_cases=load_challenge_cases(args.challenges),
            checkpoint_path=args.json_out,
        )
        report["experiment_identity"] = _experiment_identity(
            cases_path=args.cases,
            challenges_path=args.challenges,
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
    passed = bool(
        report.get("adoption", {}).get("passed")
        if args.mode == "ab"
        else report.get("summary", {}).get("passed")
    )
    return 1 if args.strict and not passed else 0


if __name__ == "__main__":
    raise SystemExit(main())
