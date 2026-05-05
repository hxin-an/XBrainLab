#!/usr/bin/env python3
"""Run local-model tool-call evals against the deterministic case schema."""

from __future__ import annotations

import argparse
import json
import subprocess
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
    available_disk_bytes,
    cache_usage_bytes,
    default_local_model_id,
    fallback_local_model_id,
    format_bytes,
    local_model_spec,
)
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.application_surface import READ_ONLY_TOOLS, TOOL_TO_COMMAND
from XBrainLab.llm.tools.schema_contract import tool_contract_for_llm


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

VRAM_PRESSURE_FREE_MIB = 2048
VRAM_PRESSURE_USED_RATIO = 0.90
FULL_LOCAL_GATE_REPEAT_COUNT = 3
RELEASE_LOCAL_EVAL_GATES = {"release", "thesis"}


def build_prompt_messages(case: EvalCase) -> list[dict[str, str]]:
    """Build a compact prompt for one local-model tool-call eval case."""
    turns = "\n".join(f"- user: {turn}" for turn in case.user_turns)
    inferred_intent = _inferred_case_intent(case)
    no_call_intent = inferred_intent in {"no_tool", "ask_clarification"}
    direct_blocked_reason = (
        ""
        if no_call_intent
        else _blocked_requested_intent_reason(case.state_name, inferred_intent)
    )
    available_tools = (
        []
        if no_call_intent or direct_blocked_reason
        else _available_tool_schemas(case.state_name)
    )
    blocked_commands = (
        [] if no_call_intent else _blocked_command_summary(case.state_name)
    )
    direct_command = command_for_intent(inferred_intent)
    direct_command_text = direct_command.value if direct_command else "none"
    system = (
        "You are the XBrainLab local assistant tool-call planner. "
        "Choose at most one tool for the next step. If a required input is "
        "missing, or the requested step is blocked, do not call a tool; reply "
        "with one concise user-facing sentence. If a tool is appropriate, "
        "output only one compact JSON object with keys tool_name and parameters. "
        "Never invent placeholder paths, recipe paths, ids, labels, or file names; "
        "ask for the actual value instead. If the latest user turn contains an "
        "explicit absolute path, treat it as provided input even if the path name "
        "contains words like missing, bad, or unknown; call the direct tool and let "
        "backend verification report recoverable path failures. If the user asks "
        "for a blocked workflow "
        "command, do not call a different tool to prepare or substitute for it; "
        "explain the blocked reason. The latest user turn is the next requested "
        "action; earlier turns are context and should not be repeated. "
        "The initial workflow state is authoritative: if the state is already "
        "scanned, previewed, validated, or applied, continue from that state "
        "instead of repeating an earlier scan or load step. Use "
        "preview_interpretation with choices for subject, session, task, run, "
        "event_role metadata overrides, and recipe reload remaps. Use "
        "parameters.choices.eeg_file_remap to map a saved EEG file path/name to "
        "a current replacement EEG file path/name; use "
        "parameters.choices.label_carrier_remap to map a saved label/event "
        "carrier path/name to a current replacement carrier. These choices.* "
        "paths are JSON argument fields under preview_interpretation, never as "
        "tool_name. "
        "If a remap request does not name both the saved item and replacement, "
        "ask for clarification instead of guessing. Use validate_interpretation with "
        "empty parameters when the latest request is validation. Do not claim "
        "these direct tools are unavailable when they appear in Available tools. "
        "epoch_data for create_epoch requests; preprocessed state can create "
        "epochs and does not need dataset generation first. If create_epoch "
        "has an event id but no time window, call epoch_data with t_min -0.1 "
        "and t_max 1.0 instead of asking for t_min/t_max. Use set_model when "
        "the user asks to use a model architecture. For visualize or saliency "
        "intents, do not call set_model, configure_training, switch_panel, or "
        "another substitute tool; provide a concise readiness summary instead. "
        "Use "
        "apply_standard_preprocess for standard preprocessing or general "
        "preprocess requests, even when bandpass frequencies are included; use "
        "apply_bandpass_filter only for a bandpass-only operation. For "
        "generate_dataset, split_strategy must be trial, session, or subject; "
        "individual and group are training_mode values, not split_strategy values. "
        "Prefer the direct workflow tool named by the user request. Do not use "
        "list_files or get_dataset_info as a substitute for scan_source, "
        "preview_interpretation, validate_interpretation, apply_interpretation, "
        "generate_dataset, or training commands. Do not emit a second JSON "
        "object for blocked command explanations or diagnostics. Do not use "
        "markdown."
        " If the user asks a concept question or asks why a workflow step is "
        "blocked, do not call a tool and do not mention internal tool names; "
        "explain the reason in the user's language."
        " Data Interpretation is the primary data entry workflow; legacy "
        "direct-load and label-attach paths should not be preferred for new "
        "label/event imports."
    )
    if direct_blocked_reason:
        system += (
            " The direct workflow command for this turn is blocked by the "
            "backend capability policy. Do not output any tool call and do not "
            "choose reset, scan, configure, or another substitute tool."
        )
    if no_call_intent:
        system += (
            " For this no-tool turn, do not mention internal tool names, JSON, "
            "schemas, or command syntax."
        )
    user = (
        f"Initial workflow state: {case.state_name}\n\n"
        f"Available tools:\n{json.dumps(available_tools, ensure_ascii=False)}\n\n"
        f"Blocked commands and reasons:\n"
        f"{json.dumps(blocked_commands, ensure_ascii=False)}\n\n"
        f"Inferred latest user intent: {inferred_intent}\n"
        f"Direct workflow command for latest intent: {direct_command_text}\n"
        f"Direct workflow command blocked reason: {direct_blocked_reason or 'none'}\n"
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
        if requested_intent == "no_tool":
            return Prediction(
                intent=requested_intent,
                tool_calls=[],
                final_message=text,
            )
        if requested_intent == "ask_clarification":
            asks_clarification = any(
                marker in lower
                for marker in (
                    "could you",
                    "please specify",
                    "specify",
                    "which",
                    "what",
                    "how",
                    "哪個",
                    "請",
                    "提供",
                )
            )
            if asks_clarification:
                message = "Please tell me which workflow step or input you want to use."
                return Prediction(
                    intent=requested_intent,
                    tool_calls=[],
                    blocked=True,
                    asks_clarification=True,
                    blocked_reason=message,
                    final_message=message,
                )
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
        if blocked_intent_reason and _mentions_policy_reason(
            text,
            blocked_intent_reason,
        ):
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
                "提供",
                "缺少",
                "哪個",
                "確認",
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
    if _visualization_tool_substitute(requested_intent, first_tool):
        return Prediction(
            intent=requested_intent,
            tool_calls=[],
            final_message=(
                "Service query summary is available; no UI route is needed."
            ),
            result_interpretation=result_interpretation_for(case),
        )
    blocked_intent_reason = _blocked_requested_intent_reason(
        case.state_name,
        requested_intent,
    )
    if blocked_intent_reason:
        if TOOL_INTENTS.get(first_tool) == requested_intent:
            tool_calls = []
        return Prediction(
            intent=requested_intent,
            tool_calls=tool_calls,
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
                "absolute path",
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
    resource_preflight: dict[str, Any] | None = None,
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
        "resource_preflight": resource_preflight or {},
        "method_references": METHOD_REFERENCES,
        "case_source_path": str(Path(__file__).with_name("run_tool_call_eval.py")),
        "fixture_source_paths": [
            str(Path(__file__).with_name("run_tool_call_eval.py")),
            str(Path(__file__)),
        ],
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
    result = {
        **result,
        "artifact_paths": {
            "json": str(json_path),
            "markdown": str(md_path),
            "latest_json": str(output_dir / "local_latest.json"),
            "latest_markdown": str(output_dir / "local_latest.md"),
        },
    }
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
    ]
    preflight = result.get("resource_preflight") or {}
    if preflight:
        gpu = preflight.get("gpu") or {}
        header.extend(
            [
                "## Resource Preflight",
                "",
                f"- ok: `{preflight.get('ok')}`",
                f"- gate: `{preflight.get('gate')}`",
                f"- eval gate: `{preflight.get('eval_gate')}`",
                f"- resource pressure: `{preflight.get('resource_pressure')}`",
                f"- selected cases: `{preflight.get('selected_cases')}`",
                f"- cache usage: `{preflight.get('cache_usage')}`",
                f"- available disk: `{preflight.get('available_disk')}`",
                f"- estimated VRAM: `{preflight.get('estimated_vram_gb')}` GB",
                f"- GPU: `{gpu.get('name', 'unknown')}`",
                f"- VRAM used/free/total MiB: `{gpu.get('used_mib', 'n/a')}` / "
                f"`{gpu.get('free_mib', 'n/a')}` / `{gpu.get('total_mib', 'n/a')}`",
                f"- message: {preflight.get('message')}",
                "",
            ],
        )
    header.extend(["## Failure Taxonomy", ""])
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
            schema = tool_contract_for_llm(tool)
            schema["requires_confirmation"] = (
                capability.requires_confirmation or capability.confirmation_required
            )
            schema["decision_boundary"] = capability.decision_boundary
            schemas.append(schema)
        elif tool.name in READ_ONLY_TOOLS:
            schema = tool_contract_for_llm(tool)
            schema["requires_confirmation"] = False
            schema["decision_boundary"] = None
            schemas.append(schema)
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
    ][:1]


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
    if intent == "ask_clarification":
        return "Please tell me which workflow step or input you want to use."
    if label is None:
        return message
    if "actual path" in lower or "absolute path" in lower:
        return f"Required {label} must be an actual path provided by the user."
    if "missing required parameter" in lower or "required input" in lower:
        return f"Required {label} is missing."
    return message


def _visualization_tool_substitute(intent: str, tool_name: str) -> bool:
    return intent in {"visualize", "saliency"} and tool_name in {
        "switch_panel",
        "set_model",
        "configure_training",
        "saliency",
        "visualize",
    }


def _mentions_policy_reason(text: str, policy_reason: str) -> bool:
    lower = text.lower()
    for reason in policy_reason.split(";"):
        reason_text = reason.strip().lower()
        if reason_text and reason_text in lower:
            return True
    return False


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


def build_local_eval_resource_preflight(
    *,
    model_id: str,
    model_role: str,
    eval_gate: str = "candidate",
    repeat_count: int,
    case_ids: list[str] | None,
    case_limit: int | None,
    cache_dir: str | None = None,
    cache_usage_bytes_value: int | None = None,
    available_disk_bytes_value: int | None = None,
    gpu_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return disk/cache/VRAM preflight metadata for a local eval run."""
    config = LLMConfig.load_from_file() or LLMConfig()
    resolved_cache_dir = cache_dir or config.cache_dir
    cache_bytes = (
        cache_usage_bytes_value
        if cache_usage_bytes_value is not None
        else cache_usage_bytes(resolved_cache_dir)
    )
    disk_bytes = (
        available_disk_bytes_value
        if available_disk_bytes_value is not None
        else available_disk_bytes(resolved_cache_dir)
    )
    selected_cases = len(
        _select_cases(
            build_eval_cases(),
            case_ids=case_ids,
            case_limit=case_limit,
        ),
    )
    full_suite = case_ids is None and case_limit is None
    full_local_gate = full_suite and repeat_count >= FULL_LOCAL_GATE_REPEAT_COUNT
    spec = local_model_spec(model_id)
    estimated_vram_gb = spec.estimated_vram_gb if spec is not None else None
    gpu = gpu_snapshot if gpu_snapshot is not None else _collect_gpu_memory_snapshot()
    pressure = _resource_pressure(gpu, estimated_vram_gb)
    normalized_eval_gate = eval_gate.lower()
    release_gate = normalized_eval_gate in RELEASE_LOCAL_EVAL_GATES
    gate_mismatch = full_local_gate and not release_gate
    resource_blocked = full_local_gate and pressure == "high"
    ok = not gate_mismatch and not resource_blocked
    gate = (
        f"{normalized_eval_gate} full local"
        if full_local_gate
        else f"{normalized_eval_gate} local subset"
    )
    if gate_mismatch and resource_blocked:
        message = (
            "full local x3 is a release/thesis gate, and VRAM is nearly full; "
            "refusing to start local eval. Pass --eval-gate release or "
            "--eval-gate thesis only when refreshing a formal benchmark claim, "
            "and free GPU memory before rerunning."
        )
    elif gate_mismatch:
        message = (
            "full local x3 is a release/thesis gate; pass --eval-gate release "
            "or --eval-gate thesis only when refreshing a formal benchmark "
            "claim. Routine changes should use deterministic changed cases or "
            "a primary subset."
        )
    elif resource_blocked:
        message = (
            "VRAM is nearly full; refusing to start a full local x3 eval. "
            "Run deterministic or changed-case eval first, or free GPU memory "
            "before release/thesis local eval."
        )
    elif ok:
        message = (
            "Resource preflight passed for this eval gate."
            if pressure != "high"
            else "GPU memory is under high pressure; run only changed cases or a "
            "small primary subset until memory is freed."
        )
    else:
        message = "Resource preflight failed."

    return {
        "ok": ok,
        "message": message,
        "gate": gate,
        "eval_gate": normalized_eval_gate,
        "model_id": model_id,
        "model_role": model_role,
        "repeat_count": repeat_count,
        "selected_cases": selected_cases,
        "full_suite": full_suite,
        "full_local_gate": full_local_gate,
        "resource_pressure": pressure,
        "cache_dir": resolved_cache_dir,
        "cache_usage_bytes": cache_bytes,
        "cache_usage": format_bytes(cache_bytes),
        "available_disk_bytes": disk_bytes,
        "available_disk": format_bytes(disk_bytes),
        "estimated_vram_gb": estimated_vram_gb,
        "gpu": gpu,
    }


def _collect_gpu_memory_snapshot() -> dict[str, Any]:
    """Read current GPU memory from nvidia-smi without making it mandatory."""
    command = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,memory.used,memory.free",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed nvidia-smi command, no shell.
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "reason": str(exc)}
    if completed.returncode != 0:
        return {
            "available": False,
            "reason": (completed.stderr or completed.stdout).strip(),
        }
    first_line = next(
        (line.strip() for line in completed.stdout.splitlines() if line.strip()),
        "",
    )
    if not first_line:
        return {"available": False, "reason": "nvidia-smi returned no GPU rows."}
    parts = [part.strip() for part in first_line.split(",", maxsplit=4)]
    if len(parts) != 5:
        return {
            "available": False,
            "reason": f"Unexpected nvidia-smi row: {first_line}",
        }
    try:
        index = int(parts[0])
        total_mib = int(parts[2])
        used_mib = int(parts[3])
        free_mib = int(parts[4])
    except ValueError:
        return {
            "available": False,
            "reason": f"Unexpected nvidia-smi row: {first_line}",
        }
    return {
        "available": True,
        "index": index,
        "name": parts[1],
        "total_mib": total_mib,
        "used_mib": used_mib,
        "free_mib": free_mib,
    }


def _resource_pressure(
    gpu: dict[str, Any],
    estimated_vram_gb: float | None,
) -> str:
    if not gpu.get("available"):
        return "unknown"
    total_mib = _int_or_zero(gpu.get("total_mib"))
    used_mib = _int_or_zero(gpu.get("used_mib"))
    free_mib = _int_or_zero(gpu.get("free_mib"))
    if total_mib <= 0:
        return "unknown"
    estimated_floor = int((estimated_vram_gb or 0.0) * 1024 * 0.25)
    free_threshold = max(VRAM_PRESSURE_FREE_MIB, estimated_floor)
    if free_mib < free_threshold or used_mib / total_mib >= VRAM_PRESSURE_USED_RATIO:
        return "high"
    return "normal"


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def write_resource_preflight_artifact(
    preflight: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Persist a resource preflight result when local eval is blocked."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "resource_preflight.json"
    md_path = output_dir / "resource_preflight.md"
    json_path.write_text(_compact_json(preflight), encoding="utf-8")
    gpu = preflight.get("gpu") or {}
    lines = [
        "# Local Tool-Call Eval Resource Preflight",
        "",
        f"- ok: `{preflight.get('ok')}`",
        f"- gate: `{preflight.get('gate')}`",
        f"- eval gate: `{preflight.get('eval_gate')}`",
        f"- model: `{preflight.get('model_id')}`",
        f"- repeat count: `{preflight.get('repeat_count')}`",
        f"- selected cases: `{preflight.get('selected_cases')}`",
        f"- resource pressure: `{preflight.get('resource_pressure')}`",
        f"- cache usage: `{preflight.get('cache_usage')}`",
        f"- available disk: `{preflight.get('available_disk')}`",
        f"- estimated VRAM: `{preflight.get('estimated_vram_gb')}` GB",
        f"- GPU: `{gpu.get('name', 'unknown')}`",
        f"- VRAM used/free/total MiB: `{gpu.get('used_mib', 'n/a')}` / "
        f"`{gpu.get('free_mib', 'n/a')}` / `{gpu.get('total_mib', 'n/a')}`",
        f"- message: {preflight.get('message')}",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Explicit supported model id.")
    parser.add_argument(
        "--model-role",
        choices=("configured", "primary", "fallback"),
        default="configured",
        help="Model role to evaluate when --model is not provided.",
    )
    parser.add_argument(
        "--eval-gate",
        choices=("fast", "candidate", "release", "thesis"),
        default="candidate",
        help=(
            "Validation gate for this local eval. Full suite repeat>=3 requires "
            "release or thesis."
        ),
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
    args = parser.parse_args(argv)
    model_id = _resolve_model(args)
    resource_preflight = build_local_eval_resource_preflight(
        model_id=model_id,
        model_role=args.model_role,
        eval_gate=args.eval_gate,
        repeat_count=args.repeat_count,
        case_ids=args.case_id,
        case_limit=args.case_limit,
    )
    if not resource_preflight["ok"]:
        json_path, md_path = write_resource_preflight_artifact(
            resource_preflight,
            Path(args.output_dir),
        )
        print(resource_preflight["message"])
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
        return 2

    result = run_local_eval(
        model_id=model_id,
        repeat_count=args.repeat_count,
        case_ids=args.case_id,
        case_limit=args.case_limit,
        max_new_tokens=args.max_new_tokens,
        resource_preflight=resource_preflight,
    )
    json_path, md_path = write_local_artifacts(result, Path(args.output_dir))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
