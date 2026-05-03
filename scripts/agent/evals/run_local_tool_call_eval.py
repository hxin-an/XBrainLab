#!/usr/bin/env python3
"""Run local-model tool-call evals against the deterministic case schema."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

from scripts.agent.evals.run_tool_call_eval import (
    METHOD_REFERENCES,
    EvalCase,
    PredictedToolCall,
    Prediction,
    build_eval_cases,
    expected_verification_result_for,
    infer_intent,
    make_state,
    render_markdown_report,
    result_interpretation_for,
    score_case,
    state_delta_for,
    summarize_scores,
    tool_selection_matches,
)
from scripts.dev.inspect_local_assistant_runtime import classify_runtime
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.llm.agent.intent import command_for_intent, path_label_for_intent
from XBrainLab.llm.agent.parser import CommandParser
from XBrainLab.llm.agent.tool_call_normalizer import normalize_tool_call
from XBrainLab.llm.agent.verifier import PlaceholderArgumentValidator, VerificationLayer
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.model_catalog import (
    default_local_model_id,
    fallback_local_model_id,
)
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.application_surface import READ_ONLY_TOOLS, TOOL_TO_COMMAND


class TextGenerator(Protocol):
    """Callable interface used by tests and the real local model runner."""

    def __call__(self, messages: list[dict[str, str]]) -> str:
        """Return a model response for one prompt."""
        ...


TOOL_INTENTS: dict[str, str] = {
    "scan_source": "scan_source",
    "preview_interpretation": "preview_interpretation",
    "validate_interpretation": "validate_interpretation",
    "apply_interpretation": "apply_interpretation",
    "save_interpretation_recipe": "save_interpretation_recipe",
    "reload_interpretation_recipe": "reload_interpretation_recipe",
    "load_data": "load_data",
    "apply_standard_preprocess": "preprocess",
    "apply_bandpass_filter": "preprocess",
    "epoch_data": "create_epoch",
    "generate_dataset": "generate_dataset",
    "set_model": "configure_training",
    "configure_training": "configure_training",
    "start_training": "train",
    "clear_dataset": "reset_session",
    "query_state": "query_state",
    "get_dataset_info": "query_state",
}


def build_prompt_messages(case: EvalCase) -> list[dict[str, str]]:
    """Build a compact prompt for one local-model tool-call eval case."""
    available_tools = _available_tool_schemas(case.state_name)
    blocked_commands = _blocked_command_summary(case.state_name)
    turns = "\n".join(f"- user: {turn}" for turn in case.user_turns)
    inferred_intent = _inferred_case_intent(case)
    direct_command = command_for_intent(inferred_intent)
    direct_command_text = direct_command.value if direct_command else "none"
    system = (
        "You are the XBrainLab local assistant tool-call planner. "
        "Choose at most one tool for the next step. If a required input is "
        "missing, or the requested step is blocked, do not call a tool; reply "
        "with one concise user-facing sentence. If a tool is appropriate, "
        "output only one compact JSON object with keys tool_name and parameters. "
        "Never invent placeholder paths, recipe paths, ids, labels, or file names; "
        "ask for the actual value instead. If the user asks for a blocked workflow "
        "command, do not call a different tool to prepare or substitute for it; "
        "explain the blocked reason. The latest user turn is the next requested "
        "action; earlier turns are context and should not be repeated. "
        "The initial workflow state is authoritative: if the state is already "
        "scanned, previewed, validated, or applied, continue from that state "
        "instead of repeating an earlier scan or load step. Use "
        "apply_standard_preprocess for standard preprocessing or general "
        "preprocess requests, even when bandpass frequencies are included; use "
        "apply_bandpass_filter only for a bandpass-only operation. For "
        "generate_dataset, split_strategy must be trial, session, or subject; "
        "individual and group are training_mode values, not split_strategy values. "
        "Prefer the direct workflow tool named by the user request. Do not use "
        "list_files or get_dataset_info as a substitute for scan_source, "
        "preview_interpretation, validate_interpretation, apply_interpretation, "
        "generate_dataset, or training commands. Do not use markdown."
    )
    user = (
        f"Initial workflow state: {case.state_name}\n\n"
        f"Available tools:\n{json.dumps(available_tools, ensure_ascii=False)}\n\n"
        f"Blocked commands and reasons:\n"
        f"{json.dumps(blocked_commands, ensure_ascii=False)}\n\n"
        f"Inferred latest user intent: {inferred_intent}\n"
        f"Direct workflow command for latest intent: {direct_command_text}\n"
        "If the direct workflow command is available, use that command's tool. "
        "If it is blocked, do not substitute another tool; explain the blocked "
        "reason.\n\n"
        f"Conversation:\n{turns}\n\n"
        "Return the next assistant response now."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def score_local_case(case: EvalCase, raw_outputs: list[str]):
    """Score repeated local-model outputs for one eval case."""
    predictions = [
        prediction_from_model_output(case, raw_output) for raw_output in raw_outputs
    ]
    return score_case(case, predictions)


def prediction_from_model_output(case: EvalCase, raw_output: str) -> Prediction:
    """Convert one raw local-model response into the shared scorer prediction."""
    parsed = CommandParser.parse(raw_output) or []
    tool_calls = _prediction_tool_calls(case, parsed)
    requested_intent = _inferred_case_intent(case)
    if not tool_calls:
        text = raw_output.strip()
        lower = text.lower()
        blocked_intent_reason = _blocked_requested_intent_reason(
            case.state_name,
            requested_intent,
        )
        has_blocked_marker = any(
            marker in lower
            for marker in ("blocked", "cannot", "can't", "not available")
        )
        if blocked_intent_reason and has_blocked_marker:
            return Prediction(
                intent=requested_intent,
                tool_calls=[],
                blocked=True,
                blocked_reason=blocked_intent_reason,
                final_message=blocked_intent_reason,
            )
        asks_clarification = any(
            marker in lower
            for marker in (
                "provide",
                "missing",
                "which",
                "confirm",
            )
        ) or ("need" in lower and "path" in lower)
        blocked = any(
            marker in lower
            for marker in ("blocked", "cannot", "can't", "not available")
        ) or ("before" in lower and not asks_clarification)
        blocked = blocked or asks_clarification
        return Prediction(
            intent=requested_intent,
            tool_calls=[],
            blocked=blocked,
            asks_clarification=asks_clarification,
            blocked_reason=text if blocked else "",
            final_message=text,
        )

    first_tool = tool_calls[0].tool_name
    first_params = tool_calls[0].arguments
    blocked_intent_reason = _blocked_requested_intent_reason(
        case.state_name,
        requested_intent,
    )
    if blocked_intent_reason:
        return Prediction(
            intent=requested_intent,
            tool_calls=[],
            blocked=True,
            blocked_reason=blocked_intent_reason,
            final_message=blocked_intent_reason,
        )

    validation = _prediction_verifier().verify_tool_call((first_tool, first_params))
    if not validation.is_valid:
        message = validation.error_message or "Tool call did not pass verification."
        message = _intent_adjusted_verification_message(requested_intent, message)
        lower = message.lower()
        asks_clarification = any(
            marker in lower
            for marker in (
                "actual path",
                "missing required parameter",
                "required input",
                "is missing",
            )
        )
        return Prediction(
            intent=requested_intent,
            tool_calls=[],
            blocked=True,
            asks_clarification=asks_clarification,
            blocked_reason=message,
            final_message=message,
        )

    intent = TOOL_INTENTS.get(first_tool, "unknown")
    blocked_reason = _blocked_reason_for_tool(case.state_name, first_tool)
    confirmation_required = _confirmation_required_for_tool(case.state_name, first_tool)
    return Prediction(
        intent=intent,
        tool_calls=tool_calls,
        blocked=bool(blocked_reason),
        confirmation_required=confirmation_required,
        blocked_reason=blocked_reason,
        final_message="",
        result_interpretation=result_interpretation_for(case),
        state_delta=state_delta_for(case)
        if not blocked_reason
        and tool_selection_matches(case.expected_tools, tool_calls)
        else {},
    )


def run_local_eval(
    *,
    model_id: str,
    repeat_count: int,
    case_ids: list[str] | None = None,
    case_limit: int | None = None,
    max_new_tokens: int = 160,
    generator: TextGenerator | None = None,
) -> dict[str, Any]:
    """Run local-model evals and return a JSON-friendly report."""
    cases = _select_cases(build_eval_cases(), case_ids=case_ids, case_limit=case_limit)
    config = LLMConfig.load_from_file() or LLMConfig()
    config.apply_runtime_selection("local", model_id=model_id, ui_active_mode="local")
    config.max_new_tokens = max_new_tokens
    config.do_sample = False
    runtime = _artifact_runtime(classify_runtime(config))

    local_generator = generator or _build_engine_generator(config)
    schema_verifier = _prediction_verifier()
    case_runs: list[dict[str, Any]] = []
    scores = []
    for case in cases:
        outputs: list[str] = []
        runs: list[dict[str, Any]] = []
        for repeat_index in range(repeat_count):
            messages = build_prompt_messages(case)
            started = time.monotonic()
            try:
                raw_output = local_generator(messages)
                error = None
            except Exception as exc:
                raw_output = ""
                error = str(exc)
            elapsed = time.monotonic() - started
            outputs.append(raw_output)
            parsed = _normalized_parsed_tool_calls(
                case,
                CommandParser.parse(raw_output) or [],
            )
            runs.append(
                {
                    "repeat_index": repeat_index,
                    "raw_output": raw_output,
                    "parsed_tool_calls": [
                        {"tool_name": name, "arguments": params}
                        for name, params in parsed
                    ],
                    "schema_verification": _schema_verification(
                        schema_verifier,
                        parsed,
                    ),
                    "latency_seconds": round(elapsed, 3),
                    "error": error,
                },
            )

        score = score_local_case(case, outputs)
        scores.append(score)
        case_runs.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "expected_verification_result": (
                    expected_verification_result_for(case)
                ),
                "runs": runs,
                "score": asdict(score),
            },
        )

    summary = summarize_scores(scores)
    return {
        "benchmark": "xbrainlab-local-tool-call",
        "runner": "local-llm",
        "model_id": model_id,
        "repeat_count": repeat_count,
        "exploratory": repeat_count < 3 or len(cases) < 50,
        "runtime": runtime,
        "method_references": METHOD_REFERENCES,
        "total_cases": len(cases),
        "summary": summary,
        "failure_taxonomy": _failure_taxonomy(scores),
        "cases": case_runs,
    }


def write_local_artifacts(
    result: dict[str, Any], output_dir: Path
) -> tuple[Path, Path]:
    """Write local eval JSON and Markdown artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = _safe_suffix(str(result["model_id"]))
    json_path = output_dir / f"local_{suffix}.json"
    md_path = output_dir / f"local_{suffix}.md"
    json_path.write_text(_compact_json(result), encoding="utf-8")
    md_path.write_text(render_local_markdown_report(result), encoding="utf-8")
    latest_json = output_dir / "local_latest.json"
    latest_md = output_dir / "local_latest.md"
    latest_json.write_text(
        _compact_json(
            {
                "latest_result": json_path.name,
                "latest_report": md_path.name,
                "runner": result["runner"],
                "model_id": result["model_id"],
                "repeat_count": result["repeat_count"],
                "exploratory": result["exploratory"],
                "summary": result["summary"],
                "failure_taxonomy": result["failure_taxonomy"],
            },
        ),
        encoding="utf-8",
    )
    latest_md.write_text(
        "\n".join(
            [
                "# XBrainLab Local Tool-Call Eval Latest",
                "",
                f"- latest result: `{json_path.name}`",
                f"- latest report: `{md_path.name}`",
                f"- model: `{result['model_id']}`",
                f"- pass rate: `{result['summary']['pass_rate']:.2%}`",
                "",
            ],
        ),
        encoding="utf-8",
    )
    return json_path, md_path


def render_local_markdown_report(result: dict[str, Any]) -> str:
    """Render local-model eval results as Markdown."""
    base = render_markdown_report(
        {
            "runner": result["runner"],
            "method_references": result["method_references"],
            "summary": result["summary"],
            "cases": [case["score"] for case in result["cases"]],
        },
    )
    runtime = result["runtime"]
    header = [
        "# XBrainLab Local Tool-Call Eval",
        "",
        f"- runner: `{result['runner']}`",
        f"- model: `{result['model_id']}`",
        f"- repeat count: `{result['repeat_count']}`",
        f"- exploratory: `{result['exploratory']}`",
        f"- runtime classification: `{runtime.get('classification')}`",
        f"- cache usage: `{runtime.get('cache_usage')}`",
        "",
        "## Failure Taxonomy",
        "",
    ]
    taxonomy = result["failure_taxonomy"]
    if taxonomy:
        header.extend(
            f"- {name}: `{count}`" for name, count in sorted(taxonomy.items())
        )
    else:
        header.append("- None.")
    header.extend(["", "## Scoring Detail", ""])
    return "\n".join(header) + "\n" + base


def _build_engine_generator(config: LLMConfig) -> TextGenerator:
    """Load a local engine once and return a generation callable."""
    if not config.local_backend_ready(config.model_name):
        raise RuntimeError(config.local_backend_status_message(config.model_name))
    engine = LLMEngine(config)
    engine.load_model()

    def _generate(messages: list[dict[str, str]]) -> str:
        return "".join(engine.generate_stream(messages)).strip()

    return _generate


def _artifact_runtime(runtime: dict[str, object]) -> dict[str, object]:
    """Keep local eval artifacts useful without storing host-specific paths."""
    keep = {
        "classification",
        "message",
        "has_local_cache",
        "gpu_fallback_reason",
        "load_in_4bit",
        "effective_load_in_4bit",
        "policy_error",
        "primary_local_model",
        "fallback_local_model",
        "cache_usage_bytes",
        "cache_usage",
        "max_total_cache_gb",
        "model_estimates",
    }
    return {key: value for key, value in runtime.items() if key in keep}


def _compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def _select_cases(
    cases: list[EvalCase],
    *,
    case_ids: list[str] | None,
    case_limit: int | None,
) -> list[EvalCase]:
    if case_ids:
        requested = set(case_ids)
        selected = [case for case in cases if case.case_id in requested]
        missing = requested - {case.case_id for case in selected}
        if missing:
            raise ValueError(f"Unknown case id(s): {', '.join(sorted(missing))}")
    else:
        selected = list(cases)
    if case_limit is not None:
        return selected[:case_limit]
    return selected


def _available_tool_schemas(state_name: str) -> list[dict[str, Any]]:
    state = make_state(state_name)
    policy = build_capability_policy(state)
    schemas: list[dict[str, Any]] = []
    for tool in get_all_tools(mode="mock"):
        command_name = TOOL_TO_COMMAND.get(tool.name)
        if command_name is not None:
            capability = policy.get(command_name)
            if not capability.enabled:
                continue
            schemas.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "requires_confirmation": capability.requires_confirmation
                    or capability.confirmation_required,
                    "decision_boundary": capability.decision_boundary,
                },
            )
        elif tool.name in READ_ONLY_TOOLS:
            schemas.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "requires_confirmation": False,
                    "decision_boundary": None,
                },
            )
    return schemas


def _tool_schema_map() -> dict[str, dict[str, Any]]:
    return {tool.name: tool.parameters for tool in get_all_tools(mode="mock")}


def _prediction_verifier() -> VerificationLayer:
    """Return local-eval verification without host filesystem path checks."""
    return VerificationLayer(
        validators=[PlaceholderArgumentValidator()],
        tool_schemas=_tool_schema_map(),
    )


def _prediction_tool_calls(
    case: EvalCase,
    parsed: list[tuple[str, dict[str, Any]]],
) -> list[PredictedToolCall]:
    return [
        PredictedToolCall(
            tool_name=name,
            arguments=_normalized_prediction_arguments(name, params),
        )
        for name, params in _normalized_parsed_tool_calls(case, parsed)
    ]


def _normalized_parsed_tool_calls(
    case: EvalCase,
    parsed: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    latest_user_text = case.user_turns[-1] if case.user_turns else ""
    return [
        normalize_tool_call(name, params, latest_user_text=latest_user_text)
        for name, params in parsed
    ]


def _normalized_prediction_arguments(
    tool_name: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(params)
    if tool_name == "generate_dataset":
        normalized.setdefault("val_ratio", 0.2)
    return normalized


def _inferred_case_intent(case: EvalCase) -> str:
    latest = infer_intent(case.user_turns[-1].lower()) if case.user_turns else "unknown"
    if latest != "unknown":
        return latest
    return infer_intent(" ".join(case.user_turns).lower())


def _intent_adjusted_verification_message(intent: str, message: str) -> str:
    label = path_label_for_intent(intent)
    lower = message.lower()
    if label is None:
        return message
    if "actual path" in lower:
        return f"Required {label} must be an actual path provided by the user."
    if "missing required parameter" in lower or "required input" in lower:
        return f"Required {label} is missing."
    return message


def _blocked_requested_intent_reason(state_name: str, intent: str) -> str:
    command_name = command_for_intent(intent)
    if command_name is None:
        return ""
    capability = build_capability_policy(make_state(state_name)).get(command_name)
    if capability.enabled:
        return ""
    return "; ".join(capability.reasons)


def _schema_verification(
    verifier: VerificationLayer,
    parsed: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        {
            "tool_name": name,
            "is_valid": result.is_valid,
            "error_message": result.error_message,
        }
        for name, params in parsed
        for result in [verifier.verify_tool_call((name, params))]
    ]


def _blocked_command_summary(state_name: str) -> list[dict[str, Any]]:
    policy = build_capability_policy(make_state(state_name))
    return [
        {"command": capability.command_name, "reasons": capability.reasons}
        for capability in policy.capabilities.values()
        if not capability.enabled and capability.reasons
    ]


def _blocked_reason_for_tool(state_name: str, tool_name: str) -> str:
    command_name = TOOL_TO_COMMAND.get(tool_name)
    if command_name is None:
        return "" if tool_name in READ_ONLY_TOOLS else "Tool is not available."
    capability = build_capability_policy(make_state(state_name)).get(command_name)
    if capability.enabled:
        return ""
    return "; ".join(capability.reasons)


def _confirmation_required_for_tool(state_name: str, tool_name: str) -> bool:
    command_name = TOOL_TO_COMMAND.get(tool_name)
    if command_name is None:
        return False
    capability = build_capability_policy(make_state(state_name)).get(command_name)
    return capability.requires_confirmation or capability.confirmation_required


def _failure_taxonomy(scores: list[Any]) -> dict[str, int]:
    taxonomy: dict[str, int] = {}
    for score in scores:
        for failure in score.failures:
            key = failure.split(" expected ", maxsplit=1)[0]
            taxonomy[key] = taxonomy.get(key, 0) + 1
    return taxonomy


def _safe_suffix(model_id: str) -> str:
    return model_id.replace("/", "_").replace("-", "_").lower()


def _resolve_model(args: argparse.Namespace) -> str:
    if args.model:
        return str(args.model)
    if args.model_role == "primary":
        return default_local_model_id()
    if args.model_role == "fallback":
        return fallback_local_model_id()
    config = LLMConfig.load_from_file() or LLMConfig()
    return config.model_name


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Explicit supported model id.")
    parser.add_argument(
        "--model-role",
        choices=("configured", "primary", "fallback"),
        default="configured",
        help="Model role to evaluate when --model is not provided.",
    )
    parser.add_argument("--repeat-count", type=int, default=3)
    parser.add_argument("--case-limit", type=int, default=None)
    parser.add_argument("--case-id", action="append", default=None)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument(
        "--output-dir",
        default="artifacts/agent_evals",
        help="Directory for local eval artifacts.",
    )
    args = parser.parse_args()

    result = run_local_eval(
        model_id=_resolve_model(args),
        repeat_count=args.repeat_count,
        case_ids=args.case_id,
        case_limit=args.case_limit,
        max_new_tokens=args.max_new_tokens,
    )
    json_path, md_path = write_local_artifacts(result, Path(args.output_dir))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
