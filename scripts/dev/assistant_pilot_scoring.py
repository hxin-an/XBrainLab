"""Offline research decision scoring, independent of execution and Host rescue.

Consumes a normalized non-Test bank case and one *actual* model response.
It does not generate responses, infer side effects or certify product outcomes.
Legacy synthetic calibration and frozen acceptance scoring remain unchanged.
"""

from __future__ import annotations

import math
from typing import Any

from XBrainLab.backend.application.pipeline_stage import PipelineStage
from XBrainLab.llm.agent.decision_contract import MODEL_RESPONSE_TOOL_NAME
from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus
from XBrainLab.llm.agent.verifier import DIRECT_PARAMETER_TOOLS, ToolSchemaValidator
from XBrainLab.llm.pipeline_state import STAGE_CONFIG
from XBrainLab.llm.tools import get_all_tools

_CATEGORIES = {"Action", "Clarification", "No-call"}


def _finite_json(value: Any) -> bool:
    if type(value) is float:
        return math.isfinite(value)
    if value is None or type(value) in (str, int, bool):
        return True
    if type(value) is list:
        return all(_finite_json(item) for item in value)
    if type(value) is dict:
        return all(
            type(key) is str and _finite_json(item) for key, item in value.items()
        )
    return False


def _same_parameters(actual: Any, expected: Any) -> bool:
    if type(actual) in (int, float) and type(expected) in (int, float):
        return _finite_json(actual) and _finite_json(expected) and actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            _same_parameters(value, expected[key]) for key, value in actual.items()
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _same_parameters(a, b) for a, b in zip(actual, expected, strict=True)
        )
    return actual == expected


def score_decision(case: dict[str, Any], response: str | None) -> dict[str, Any]:
    """Score one generation without importing outcome or retry success.

    Invalid oracles raise a measurement error. Invalid/missing model output is
    an incorrect decision. Caller must separately establish trace completeness,
    case identity, decision timeout and whether this was first or final output.
    Neither a correct response nor a parser result proves Host admission.
    """
    category = case.get("decision")
    stage = case.get("expected_workflow_stage")
    tool = case.get("expected_tool")
    expected = case.get("expected_parameters")
    if (
        not isinstance(category, str)
        or category not in _CATEGORIES
        or not isinstance(stage, str)
        or stage not in {item.value for item in PipelineStage}
    ):
        raise ValueError("Invalid decision category or stage in oracle")
    schemas = {item.name: item.parameters for item in get_all_tools()}
    validator = ToolSchemaValidator(schemas)
    if category == "Action":
        if (
            not isinstance(tool, str)
            or tool == MODEL_RESPONSE_TOOL_NAME
            or tool not in schemas
            or type(expected) is not dict
            or not _finite_json(expected)
            or not validator.validate(tool, expected).is_valid
        ):
            raise ValueError("Action oracle violates the product tool/parameter schema")
    elif tool != MODEL_RESPONSE_TOOL_NAME or expected is not None:
        raise ValueError("Non-action oracle must expect a free-text response envelope")

    result: dict[str, Any] = {
        "correct": False,
        "reason": "missing_response",
        "observed_tool": None,
        "observed_stage": None,
    }
    if not isinstance(response, str) or not response.strip():
        return result
    parsed = CommandParser.parse_product(response)
    result["observed_stage"] = parsed.workflow_stage
    if parsed.status not in {ToolEnvelopeStatus.VALID, ToolEnvelopeStatus.NO_TOOL}:
        return {**result, "reason": "invalid_envelope"}
    if parsed.status is ToolEnvelopeStatus.NO_TOOL:
        result["observed_tool"] = MODEL_RESPONSE_TOOL_NAME
        # Static output validity uses the same direct-tool/schema/stage sources
        # as product clarification admission; it cannot establish live admission.
        if parsed.pending_action and (
            parsed.pending_action not in DIRECT_PARAMETER_TOOLS
            or parsed.pending_action not in STAGE_CONFIG[PipelineStage(stage)]["tools"]
            or not set(parsed.missing_inputs).issubset(
                schemas.get(parsed.pending_action, {}).get("required", [])
            )
        ):
            return {**result, "reason": "invalid_envelope"}
        correct = (
            category != "Action"
            and parsed.workflow_stage == stage
            and bool(parsed.message.strip())
        )
    else:
        actual_tool, actual_parameters = parsed.commands[0]
        result["observed_tool"] = actual_tool
        correct = (
            category == "Action"
            and parsed.workflow_stage == stage
            and actual_tool == tool
            and validator.validate(actual_tool, actual_parameters).is_valid
            and _same_parameters(actual_parameters, expected)
        )
    return {
        **result,
        "correct": bool(correct),
        "reason": "matched" if correct else "decision_mismatch",
    }


def score_case_decisions(
    case: dict[str, Any],
    trace: dict[str, Any],
    *,
    decision_timed_out: bool = False,
) -> dict[str, Any]:
    """Score a complete observed case; Host/product outcomes never rescue it.

    ``decision_timed_out`` is evidence from the runner's actual deadline and
    cancellation, not a deduction from empty output. The normal cancellation
    terminal must still be present. Runtime errors are measured wrong decisions;
    missing/corrupt evidence is instead an invalid measurement with null scores.
    """
    if type(decision_timed_out) is not bool:
        raise ValueError("decision_timed_out must be an observed boolean")
    score_decision(case, None)  # Invalid oracles remain measurement errors.
    issues = list(trace.get("measurement_issues", []))
    generations = trace.get("generations", [])
    events = trace.get("events", [])
    if not case.get("case_id") or trace.get("case_id") != case["case_id"]:
        issues.append("case_identity_mismatch")
    terminal = trace.get("turn_terminal")
    if not isinstance(terminal, dict) or not terminal.get("outcome"):
        issues.append("missing_turn_terminal")
    terminal_events = [
        event.get("payload") for event in events if event.get("kind") == "turn_terminal"
    ]
    if terminal_events != [terminal]:
        issues.append("turn_terminal_trace_mismatch")
    if decision_timed_out:
        if not isinstance(terminal, dict) or terminal.get("outcome") != "cancelled":
            issues.append("timeout_without_cancellation")
        if not generations:
            issues = [issue for issue in issues if issue != "missing_generation"]
    elif not generations:
        issues.append("missing_generation")
    if len(generations) > 3:
        issues.append("repair_budget_exceeded")

    attempts, seen = [], set()
    try:
        for generation in generations:
            identity = generation["generation_id"]
            if type(identity) is not int or identity <= 0 or identity in seen:
                issues.append("invalid_generation_identity")
            seen.add(identity)
            request = generation["request"]
            if (
                not isinstance(request, dict)
                or request.get("generation_id") != identity
                or request.get("response_contract") != "structured_action"
                or not request.get("messages")
            ):
                issues.append(f"invalid_generation_request:{identity}")
            recorded_requests = [
                event["payload"]
                for event in events
                if event["kind"] == "generation_request"
                and event["payload"].get("generation_id") == identity
            ]
            matching = [
                event["payload"]
                for event in events
                if event["kind"] == "generation_event"
                and event["payload"].get("generation_id") == identity
            ]
            phases = [event["phase"] for event in matching]
            endings = [
                phase for phase in phases if phase in {"finished", "error", "cancelled"}
            ]
            raw = "".join(
                event["text"] for event in matching if event["phase"] == "chunk"
            )
            phase = generation["terminal"]
            if (
                recorded_requests != [request]
                or raw != generation["raw_response"]
                or endings != [phase]
                or not phases
                or phases[-1] != phase
            ):
                issues.append(f"generation_trace_mismatch:{identity}")
            if phase == "finished" and "started" not in phases:
                issues.append(f"missing_generation_start:{identity}")
            if phase not in {"finished", "error", "cancelled"}:
                issues.append(f"missing_generation_terminal:{identity}")
            result = (
                score_decision(case, raw)
                if phase == "finished"
                else {
                    "correct": False,
                    "reason": "model_error" if phase == "error" else "cancelled",
                    "observed_tool": None,
                    "observed_stage": None,
                }
            )
            attempts.append({"generation_id": identity, **result})
        if (
            decision_timed_out
            and generations
            and generations[-1]["terminal"] != "cancelled"
        ):
            issues.append("timeout_without_generation_cancellation")
        observed_ids = {
            event["payload"]["generation_id"]
            for event in events
            if event["kind"] in {"generation_request", "generation_event"}
        }
        if observed_ids != seen:
            issues.append("generation_inventory_mismatch")
    except (KeyError, TypeError, ValueError):
        issues.append("malformed_generation_trace")

    valid = not issues
    final_phase = generations[-1].get("terminal") if generations else None
    status = (
        "invalid_measurement"
        if not valid
        else "decision_timeout"
        if decision_timed_out
        else "model_error"
        if final_phase == "error"
        else "cancelled"
        if final_phase == "cancelled"
        else "completed"
    )
    return {
        "measurement_valid": valid,
        "measurement_issues": list(dict.fromkeys(issues)),
        "execution_status": status,
        "repair_count": max(0, len(generations) - 1),
        "attempt_decisions": attempts,
        "first_decision_correct": (
            bool(attempts and attempts[0]["correct"]) if valid else None
        ),
        "final_decision_correct": (
            bool(attempts and attempts[-1]["correct"] and not decision_timed_out)
            if valid
            else None
        ),
        "host_observations": [
            event["payload"] for event in events if event.get("kind") == "host_decision"
        ],
    }
