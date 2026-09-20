"""Calibrate a three-decision scorer on synthetic Development observations only.

No model, application service, GUI or tool is executed. This module consumes
observations; it neither decides product readiness nor grants execution authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus
from XBrainLab.llm.agent.verifier import ToolSchemaValidator
from XBrainLab.llm.tools import get_all_tools

SCHEMA = "xbrainlab.assistant_benchmark_calibration.v1"
DEFAULT_CASES = Path(__file__).with_name("assistant_benchmark_calibration_cases.json")
LAYERS = ("raw", "agent", "outcome")
_CASE_FIELDS = {
    "id",
    "family_id",
    "split",
    "source",
    "input",
    "stage",
    "decision",
    "tool",
    "parameters",
    "missing_inputs",
    "completion",
    "requires_confirmation",
    "before",
    "after",
    "ui",
    "effects",
}
_OBSERVATION_FIELDS = {
    "id",
    "case_id",
    "raw_response",
    "agent_response",
    "complete",
    "host_verified",
    "terminal",
    "before",
    "after",
    "ui",
    "effects",
    "pending",
    "errors",
    "execution",
}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON value: {value}")


def _parse_calibration(content: bytes) -> dict[str, Any]:
    return json.loads(
        content,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )


def load_calibration(path: Path) -> dict[str, Any]:
    """Read only the supplied calibration manifest; never discover other splits."""
    return _parse_calibration(path.read_bytes())


def _equal(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's True == 1 loophole."""
    if type(left) in (int, float) and type(right) in (int, float):
        return math.isfinite(left) and math.isfinite(right) and left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _equal(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _validate_case(case: dict[str, Any], schemas: dict[str, Any]) -> None:
    if not isinstance(case, dict) or set(case) != _CASE_FIELDS:
        raise ValueError("Calibration case fields do not match the v1 contract")
    if case["split"] != "development":
        raise ValueError("This runner accepts development cases only")
    if case["source"] != "agent_authored_calibration":
        raise ValueError("Calibration examples cannot claim Human or sealed provenance")
    if not all(
        isinstance(case[key], str) and case[key].strip()
        for key in ("id", "family_id", "input", "stage")
    ):
        raise ValueError("Case identity, family, input and stage are required")
    if case["decision"] not in {"no_call", "clarification", "action"}:
        raise ValueError("Unknown expected decision")
    if type(case["requires_confirmation"]) is not bool:
        raise ValueError("Confirmation expectation must be a boolean")
    if not all(
        isinstance(case[key], dict) for key in ("before", "after", "ui", "parameters")
    ):
        raise ValueError("State/UI projections and parameters must be objects")
    if not case["before"] or case["before"].keys() != case["after"].keys():
        raise ValueError("Before/after must cover the same nonempty state projection")
    missing = case["missing_inputs"]
    if not isinstance(missing, list) or not all(
        isinstance(item, str) and item for item in missing
    ):
        raise ValueError("Missing-input oracle must be a list of field names")
    if len(set(missing)) != len(missing):
        raise ValueError("Duplicate expected missing inputs")
    effects = case["effects"]
    if not isinstance(effects, list) or not all(
        isinstance(item, dict)
        and set(item) == {"kind", "tool"}
        and item["tool"] == case["tool"]
        for item in effects
    ):
        raise ValueError("Effects must identify their expected tool")
    decision = case["decision"]
    if decision == "no_call":
        if (
            case["tool"] is not None
            or missing
            or case["parameters"]
            or effects
            or case["completion"] != "response"
        ):
            raise ValueError("No-call cannot expect an action or pending receipt")
    elif case["tool"] not in schemas:
        raise ValueError("Expected tool is not in the current product surface")
    elif decision == "clarification":
        required = schemas[case["tool"]].get("required", [])
        if not missing or not set(missing) <= set(required) or case["parameters"]:
            raise ValueError("Clarification must name actual required tool inputs")
        if case["completion"] != "clarification" or effects != [
            {"kind": "pending", "tool": case["tool"]}
        ]:
            raise ValueError("Clarification expects only an observed pending receipt")
    else:
        if not case["requires_confirmation"] and any(
            tool.name == case["tool"] and tool.requires_confirmation
            for tool in get_all_tools()
        ):
            raise ValueError("Oracle omits product-required confirmation")
        if (
            missing
            or not ToolSchemaValidator(schemas)
            .validate(case["tool"], case["parameters"])
            .is_valid
        ):
            raise ValueError("Action oracle violates the product parameter schema")
        terminal_effect = {"backend": "execution", "gui": "gui"}.get(case["completion"])
        expected_effects = [{"kind": "proposal", "tool": case["tool"]}]
        if case["requires_confirmation"]:
            expected_effects.append(
                {"kind": "confirmation_approved", "tool": case["tool"]}
            )
        expected_effects.append({"kind": terminal_effect, "tool": case["tool"]})
        if terminal_effect is None or effects != expected_effects:
            raise ValueError(
                "Action needs exact ordered confirmation and execution/GUI evidence"
            )
        if case["completion"] == "gui" and not (
            case["ui"].get("visible") is True
            and case["ui"].get("enabled") is True
            and isinstance(case["ui"].get("surface"), str)
            and case["ui"]["surface"]
        ):
            raise ValueError("GUI completion requires a named usable surface")
    if decision != "action" and case["requires_confirmation"]:
        raise ValueError("Non-action cannot require confirmation")
    if case["completion"] != "backend" and not _equal(case["before"], case["after"]):
        raise ValueError(
            "Response, clarification and opening a GUI cannot credit mutation"
        )


def _decision_score(
    case: dict[str, Any], response: Any, schemas: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(response, str):
        return {"passed": False, "decision": "invalid", "reason": "missing_response"}
    envelope = CommandParser.parse_product(response)
    if envelope.status not in {ToolEnvelopeStatus.VALID, ToolEnvelopeStatus.NO_TOOL}:
        return {"passed": False, "decision": "invalid", "reason": "invalid_envelope"}
    decision = (
        "action"
        if envelope.status is ToolEnvelopeStatus.VALID
        else ("clarification" if envelope.pending_action else "no_call")
    )
    passed = decision == case["decision"] and envelope.workflow_stage == case["stage"]
    if decision == "action":
        tool, parameters = envelope.commands[0]
        passed = (
            passed
            and tool == case["tool"]
            and _equal(parameters, case["parameters"])
            and ToolSchemaValidator(schemas).validate(tool, parameters).is_valid
        )
    elif decision == "clarification":
        passed = (
            passed
            and envelope.pending_action == case["tool"]
            and set(envelope.missing_inputs) == set(case["missing_inputs"])
        )
    return {
        "passed": bool(passed),
        "decision": decision,
        "reason": "matched" if passed else "decision_mismatch",
    }


def score_observation(
    case: dict[str, Any], observation: dict[str, Any]
) -> dict[str, Any]:
    """Score one synthetic observation, never infer missing execution evidence."""
    schemas = {tool.name: tool.parameters for tool in get_all_tools()}
    _validate_case(case, schemas)
    raw = _decision_score(case, observation.get("raw_response"), schemas)
    agent = _decision_score(case, observation.get("agent_response"), schemas)
    if observation.get("case_id") != case["id"]:
        raw = {**raw, "passed": False, "reason": "case_identity"}
        agent = {**agent, "passed": False, "reason": "case_identity"}
    expected_execution = None
    if case["completion"] == "backend":
        expected_execution = {
            "tool": case["tool"],
            "parameters": case["parameters"],
            "success": True,
        }
    expected_pending = None
    if case["decision"] == "clarification":
        expected_pending = {
            "tool": case["tool"],
            "missing_inputs": sorted(case["missing_inputs"]),
        }
    pending = observation.get("pending")
    if isinstance(pending, dict) and isinstance(pending.get("missing_inputs"), list):
        fields = pending["missing_inputs"]
        if all(isinstance(field, str) for field in fields):
            pending = {**pending, "missing_inputs": sorted(fields)}
    terminal = {
        "response": "response",
        "clarification": "clarification",
        "backend": "completed",
        "gui": "gui_ready",
    }[case["completion"]]
    checks = {
        "record_complete": set(observation) == _OBSERVATION_FIELDS
        and observation.get("complete") is True,
        "case_identity": observation.get("case_id") == case["id"],
        "admitted_decision": agent["passed"],
        "initial_state": _equal(observation.get("before"), case["before"]),
        "final_state": _equal(observation.get("after"), case["after"]),
        "ui_state": _equal(observation.get("ui"), case["ui"]),
        "effects": _equal(observation.get("effects"), case["effects"]),
        "pending": _equal(pending, expected_pending),
        "terminal": observation.get("terminal") == terminal,
        "errors": _equal(observation.get("errors"), []),
        "execution": _equal(observation.get("execution"), expected_execution),
        "host_verification": type(observation.get("host_verified")) is bool
        and (case["decision"] != "action" or observation["host_verified"] is True),
    }
    return {
        "raw": raw,
        "agent": agent,
        "outcome": {
            "passed": all(checks.values()),
            "failed_checks": [name for name, passed in checks.items() if not passed],
        },
    }


def calibrate(payload: dict[str, Any]) -> dict[str, Any]:
    """Compare scorer predictions with separate Development calibration labels."""
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "cases", "observations", "expected_scores"}
        or payload["schema"] != SCHEMA
    ):
        raise ValueError("Invalid calibration manifest schema")
    cases, observations, labels = (
        payload["cases"],
        payload["observations"],
        payload["expected_scores"],
    )
    if (
        not isinstance(cases, list)
        or not cases
        or not isinstance(observations, list)
        or not observations
        or not isinstance(labels, dict)
    ):
        raise ValueError("Calibration inventory must be nonempty")
    schemas = {tool.name: tool.parameters for tool in get_all_tools()}
    for case in cases:
        _validate_case(case, schemas)
    by_id = {case["id"]: case for case in cases}
    ids = [row.get("id") for row in observations if isinstance(row, dict)]
    if (
        len(by_id) != len(cases)
        or len(ids) != len(observations)
        or not all(isinstance(value, str) and value for value in ids)
        or len(set(ids)) != len(ids)
        or set(ids) != set(labels)
    ):
        raise ValueError("Duplicate/missing case, observation or expected score")
    if {row.get("case_id") for row in observations} != set(by_id):
        raise ValueError("Observations must cover exactly the declared cases")
    results = []
    totals = {
        layer: {"matched": 0, "false_positive": 0, "false_negative": 0}
        for layer in LAYERS
    }
    for row in observations:
        expected = labels[row["id"]]
        if (
            not isinstance(expected, dict)
            or set(expected) != set(LAYERS)
            or not all(type(value) is bool for value in expected.values())
        ):
            raise ValueError("Expected scores must label every layer with a boolean")
        scores = score_observation(by_id[row["case_id"]], row)
        for layer in LAYERS:
            predicted = scores[layer]["passed"]
            key = (
                "matched"
                if predicted == expected[layer]
                else "false_positive"
                if predicted
                else "false_negative"
            )
            totals[layer][key] += 1
        results.append(
            {
                "id": row["id"],
                "case_id": row["case_id"],
                "scores": scores,
                "expected": expected,
            }
        )
    return {
        "schema": SCHEMA,
        "evidence_kind": "synthetic_development_calibration",
        "model_executed": False,
        "product_benchmark_score": None,
        "human_agreement": None,
        "calibration": {
            "passed": all(
                counts["matched"] == len(observations) for counts in totals.values()
            ),
            "case_count": len(cases),
            "observation_count": len(observations),
            "layers": totals,
        },
        "results": results,
        "claim_boundary": "Agent-authored synthetic calibration labels; not blinded human agreement, model quality, real execution evidence or a sealed Benchmark.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = parser.parse_args(argv)
    try:
        content = args.cases.read_bytes()
        payload = _parse_calibration(content)
        report = calibrate(payload)
        report["case_file_sha256"] = hashlib.sha256(content).hexdigest()
        report["scorer_file_sha256"] = hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest()
        code = 0 if report["calibration"]["passed"] else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report = {
            "schema": SCHEMA,
            "calibration": {"passed": False},
            "failure": str(exc),
        }
        code = 2
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
