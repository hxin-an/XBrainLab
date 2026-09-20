"""Read existing runtime evidence without executing or owning a product lifecycle."""

from __future__ import annotations

from dataclasses import asdict

from XBrainLab.backend.training_state_contract import (
    TrainingRunIdentity,
    TrainingTerminalOutcome,
)

_DECISION_BOUNDARIES = frozenset(
    {
        "command_started",
        "confirmation_requested",
        "ui_requested",
        "navigation_requested",
        "turn_terminal",
    }
)


def decision_boundary_ns(trace: dict) -> int | None:
    """First real response/action boundary, not a provisional parsed envelope.

    Returns the observer's absolute monotonic receipt time. It is independent
    of the runner's polling delay and excludes subsequent operation/UI waits.
    """
    elapsed = [
        event["elapsed_ns"]
        for event in trace.get("events", [])
        if event.get("kind") in _DECISION_BOUNDARIES
    ]
    if not elapsed:
        return None
    origin = trace.get("origin_monotonic_ns")
    if type(origin) is not int or any(
        type(value) is not int or value < 0 for value in elapsed
    ):
        raise ValueError("Invalid decision observation clock")
    return origin + min(elapsed)


def _run(value: object) -> TrainingRunIdentity | None:
    if not isinstance(value, dict):
        return None
    try:
        return TrainingRunIdentity(value.get("trainer_id"), value.get("run_id"))
    except (ValueError, TypeError):
        return None


def _state_run(state: dict | None) -> TrainingRunIdentity | None:
    if not isinstance(state, dict):
        return None
    return _run(state.get("training", {}).get("terminal_outcome", {}).get("run"))


def collect_runtime_evidence(service, trace: dict, fixture: dict, window) -> dict:
    """Read exact job IDs and run identities retained by normal owners.

    Training need not have an OwnedWork operation. A completed, unrelated run
    never certifies the requested start/stop. Fixture background work is recorded
    but only waited for when the actual model action targets it. No oracle is read.
    """
    events = trace.get("events", [])
    issues, operation_ids, awaited = [], set(), set()
    fixture_jobs = fixture.get("jobs", {})
    for job in fixture_jobs.values():
        if isinstance(job.get("operation_id"), str) and job["operation_id"]:
            operation_ids.add(job["operation_id"])
    expected_run = None
    training_action = None
    saliency_requested = False
    saliency_completed = False
    saliency_operation_id = None
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        tool = payload.get("tool_name")
        if tool == "compute_saliency":
            saliency_requested |= event.get("kind") == "ui_requested"
            saliency_completed |= (
                event.get("kind") == "ui_resolution"
                and payload.get("status") == "completed"
            )
        if event.get("kind") != "command_result":
            continue
        diagnostics = payload.get("diagnostics") or {}
        operation_id = diagnostics.get("operation_id")
        if isinstance(operation_id, str) and operation_id:
            operation_ids.add(operation_id)
            awaited.add(operation_id)
        if payload.get("ok") is not True or tool not in {
            "start_training",
            "stop_training",
        }:
            continue
        if training_action is not None:
            issues.append("multiple_training_actions")
        training_action = tool
        result_run = _run(diagnostics.get("training_run")) or _state_run(
            payload.get("state")
        )
        if tool == "stop_training":
            expected_run = _state_run(fixture.get("state"))
            if result_run is not None and result_run != expected_run:
                issues.append("stop_training_identity_mismatch")
            initial_operation = fixture_jobs.get("training", {}).get("operation_id")
            if isinstance(initial_operation, str) and initial_operation:
                awaited.add(initial_operation)
        else:
            expected_run = result_run
        if expected_run is None:
            issues.append("training_identity_missing")

    if saliency_requested:
        panel = getattr(window, "visualization_panel", None)
        button = getattr(panel, "compute_saliency_btn", None)
        operation_id = button.property("operationId") if button is not None else None
        if isinstance(operation_id, str) and operation_id:
            # This property survives terminal completion, unlike an active scan.
            saliency_operation_id = operation_id
            operation_ids.add(operation_id)
            awaited.add(operation_id)
        elif saliency_completed:
            issues.append("saliency_operation_identity_missing")

    jobs = {}
    waiting = False
    for operation_id in sorted(operation_ids):
        try:
            operation = service.get_owned_operation(operation_id)
            if operation.operation_id != operation_id:
                issues.append("operation_identity_mismatch")
                continue
            jobs[operation_id] = asdict(operation)
            if operation_id in awaited and not operation.phase.terminal:
                waiting = True
        except Exception:
            issues.append("operation_observation_unavailable:" + operation_id)

    training = {
        "action": training_action,
        "expected_run": asdict(expected_run) if expected_run is not None else None,
        "outcome": None,
        "matched": False,
    }
    try:
        outcome = service.training_runtime.terminal_outcome()
        if not isinstance(outcome, TrainingTerminalOutcome):
            issues.append("training_observation_unavailable")
        else:
            training["outcome"] = asdict(outcome)
            if expected_run is not None:
                training["matched"] = outcome.run == expected_run
                if outcome.run != expected_run:
                    issues.append("training_run_mismatch")
                elif not outcome.is_terminal:
                    waiting = True
    except Exception:
        issues.append("training_observation_unavailable")
    return {
        "jobs": jobs,
        "saliency_operation_id": saliency_operation_id,
        "training": training,
        "waiting": waiting,
        "issues": list(dict.fromkeys(issues)),
    }
