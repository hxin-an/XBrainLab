#!/usr/bin/env python3
"""Run the bounded Stable-v2 target selection suite against the local model."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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
REPORT_SCHEMA = "xbrainlab.stable_assistant_model_eval.v1"


@dataclass(frozen=True, slots=True)
class TargetEvalCase:
    """One approved target selection example with a derived backend stage."""

    case_id: str
    user_input: str
    workflow_stage: str
    expected_tool: str
    expected_parameters: dict[str, Any]


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


def build_case_messages(
    case: TargetEvalCase,
    registry: ToolRegistry,
) -> list[dict[str, str]]:
    """Build the product strict contract with the case's stage tool projection."""
    stage = PipelineStage(case.workflow_stage)
    allowed_tools = list(STAGE_CONFIG[stage]["tools"])
    assembler = ContextAssembler(
        registry,
        object(),
        application_runtime=object(),  # type: ignore[arg-type]
    )
    # The evaluator deliberately reuses the product formatter so schemas cannot drift.
    catalog = assembler._format_tools(
        allowed_tools,
        workflow_stage=stage.value,
    )
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


def _build_report(
    *,
    model_id: str,
    results: list[dict[str, Any]],
    expected_case_count: int,
    complete: bool,
) -> dict[str, Any]:
    passed_count = sum(bool(row["score"]["passed"]) for row in results)
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
        for index, case in enumerate(cases, start=1):
            print(
                f"Stable Assistant model eval {index}/{len(cases)}: {case.case_id}",
                file=sys.stderr,
                flush=True,
            )
            chunks = engine.generate_stream(
                build_case_messages(case, registry),
                profile=GenerationProfile.STRUCTURED_DECISION,
            )
            response = "".join(chunks).strip()
            score = score_model_response(case, response, registry)
            results.append({"case": asdict(case), "score": asdict(score)})
            if checkpoint_path is not None:
                _write_report(
                    checkpoint_path,
                    _build_report(
                        model_id=selection.model_id,
                        results=results,
                        expected_case_count=len(cases),
                        complete=False,
                    ),
                )
    finally:
        with suppress(Exception):
            engine.close()

    return _build_report(
        model_id=selection.model_id,
        results=results,
        expected_case_count=len(cases),
        complete=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    config = _stable_eval_config(
        LLMConfig.load_from_file(),
        device=args.device,
    )
    try:
        report = run_eval(
            config,
            load_target_cases(args.cases),
            checkpoint_path=args.json_out,
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
