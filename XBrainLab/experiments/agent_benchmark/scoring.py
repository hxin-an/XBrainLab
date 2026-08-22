"""Deterministic four-layer scoring over normalized benchmark traces."""

from __future__ import annotations

from typing import Any

from .contracts import SCHEMA_VERSION, BenchmarkContractError

_PREDICATES = {
    "event.command_ok",
    "event.command_seen",
    "event.communication",
    "event.verification_rejected",
    "state.path_equals",
}


def _path_value(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _matches(predicate: dict[str, Any], observation: dict[str, Any]) -> bool:
    predicate_id = predicate.get("predicate_id")
    if predicate_id not in _PREDICATES:
        raise BenchmarkContractError(f"Unknown predicate: {predicate_id}")
    arguments = predicate.get("arguments", {})
    kind = observation.get("kind")
    payload = observation.get("payload", {})
    if predicate_id == "event.command_ok":
        return (
            kind == "command_result"
            and payload.get("command_name") == arguments.get("command_name")
            and payload.get("status") == "ok"
        )
    if predicate_id == "event.command_seen":
        return kind == "command_result" and payload.get(
            "command_name"
        ) == arguments.get("command_name")
    if predicate_id == "event.communication":
        return kind == "communication" and payload.get("label") == arguments.get(
            "label"
        )
    if predicate_id == "event.verification_rejected":
        return kind == "verification" and payload.get("accepted") is False
    if predicate_id == "state.path_equals":
        return kind == "publication" and _path_value(
            payload.get("state", {}), arguments.get("path", "")
        ) == arguments.get("value")
    return False


def _first_match(
    predicate: dict[str, Any], observations: list[dict[str, Any]]
) -> int | None:
    for observation in observations:
        if _matches(predicate, observation):
            sequence = observation.get("sequence")
            return sequence if isinstance(sequence, int) else None
    return None


def _layer(passed: bool, evidence_ids: list[str]) -> dict[str, Any]:
    return {"passed": passed, "evidence_ids": evidence_ids}


def score_episode(case: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    """Recompute a strict episode verdict; unknown semantics fail closed."""
    if (
        trace.get("schema_version") != SCHEMA_VERSION
        or trace.get("case_id") != case.get("case_id")
        or not trace.get("complete")
    ):
        return _failed_verdict(case, trace, "artifact_integrity")
    observations = trace.get("observations")
    if not isinstance(observations, list):
        raise BenchmarkContractError("Trace observations must be a list")
    sequences = [observation.get("sequence") for observation in observations]
    if sequences != list(range(1, len(observations) + 1)):
        return _failed_verdict(case, trace, "artifact_integrity")

    oracle = case.get("oracle", {})
    milestones = oracle.get("milestones", [])
    milestone_sequences: dict[str, int] = {}
    missing: list[str] = []
    for milestone in milestones:
        milestone_id = milestone.get("milestone_id")
        sequence = _first_match(milestone, observations)
        if sequence is not None and isinstance(milestone_id, str):
            milestone_sequences[milestone_id] = sequence
        elif milestone.get("required", True):
            missing.append(str(milestone_id))

    order_valid = True
    for milestone in milestones:
        milestone_id = milestone.get("milestone_id")
        if milestone_id not in milestone_sequences:
            continue
        for prerequisite in milestone.get("prerequisites", []):
            if (
                prerequisite not in milestone_sequences
                or milestone_sequences[prerequisite]
                >= milestone_sequences[milestone_id]
            ):
                order_valid = False

    final_publication = next(
        (
            observation
            for observation in reversed(observations)
            if observation.get("kind") == "publication"
        ),
        None,
    )
    terminal_matches = [
        _matches(predicate, final_publication)
        if final_publication is not None
        else False
        for predicate in oracle.get("terminal_predicates", [])
    ]
    terminal_valid = bool(terminal_matches) and all(terminal_matches)
    triggered_minefields = [
        minefield
        for minefield in oracle.get("minefields", [])
        if _first_match(minefield, observations) is not None
    ]
    critical = [
        item.get("minefield_id")
        for item in triggered_minefields
        if item.get("critical")
    ]
    communication_labels = {
        observation.get("payload", {}).get("label")
        for observation in observations
        if observation.get("kind") == "communication"
    }
    communication_valid = set(oracle.get("required_communication", [])) <= (
        communication_labels - {None}
    )
    budget = case.get("budget", {})
    usage = trace.get("usage", {})
    budget_valid = all(
        isinstance(usage.get(key), int) and usage[key] <= budget.get(max_key, -1)
        for key, max_key in (
            ("agent_turns", "max_agent_turns"),
            ("tool_calls", "max_tool_calls"),
        )
    )

    primary_failure = None
    for condition, reason in (
        (critical, "critical_minefield"),
        (not communication_valid, "communication"),
        (missing, "missing_milestone"),
        (not order_valid, "milestone_order"),
        (triggered_minefields, "minefield"),
        (not budget_valid, "budget"),
        (not terminal_valid, "terminal_state"),
    ):
        if condition:
            primary_failure = reason
            break
    episode_passed = primary_failure is None
    evidence = [str(item) for item in sorted(milestone_sequences)]
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case.get("case_id"),
        "run_id": trace.get("run_id"),
        "repeat_index": trace.get("repeat_index"),
        "complete": True,
        "decision": _layer(not missing, evidence),
        "control": _layer(order_valid and budget_valid, evidence),
        "execution": _layer(terminal_valid and not triggered_minefields, evidence),
        "episode": _layer(episode_passed, evidence),
        "triggered_minefields": [
            item.get("minefield_id") for item in triggered_minefields
        ],
        "critical_minefields": critical,
        "primary_failure": primary_failure,
    }


def _failed_verdict(
    case: dict[str, Any], trace: dict[str, Any], reason: str
) -> dict[str, Any]:
    failed = _layer(False, [])
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case.get("case_id"),
        "run_id": trace.get("run_id"),
        "repeat_index": trace.get("repeat_index"),
        "complete": False,
        "decision": failed,
        "control": failed,
        "execution": failed,
        "episode": failed,
        "triggered_minefields": [],
        "critical_minefields": [],
        "primary_failure": reason,
    }
