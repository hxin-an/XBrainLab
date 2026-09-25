"""Project recorded product evidence; never execute tools or reimplement admission.

Raw correctness remains the decision scorer's responsibility. Dialog readiness is
a handoff, not the completion of an operation performed later by a human. These
results describe engineering/Pilot observations, not independent Test evidence.
"""

from __future__ import annotations


def _recorded_ui_failures(ui):
    events = ui.get("events", [])
    requests = [e for e in events if e.get("kind") == "request_observed"]
    failures = []
    for event in events:
        if event.get("kind") not in {"readiness_timeout", "render_failed"}:
            continue
        clock = event.get("monotonic_ns")
        if type(clock) is not int or clock <= 0 or not event.get("screenshot"):
            continue
        identity = (
            ("request_id",)
            if event.get("request_id")
            else ("target", "view_mode", "correlation")
        )
        if not event.get(identity[0]):
            continue
        matching = [
            r for r in requests if all(r.get(k) == event.get(k) for k in identity)
        ]
        if (
            len(matching) == 1
            and type(matching[0].get("monotonic_ns")) is int
            and 0 < matching[0]["monotonic_ns"] <= clock
        ):
            failures.append(event)
    return failures


def ui_measurement_issues(ui: dict) -> list[str]:
    """Exclude only corroborated product failures, never missing observations."""
    recorded = _recorded_ui_failures(ui)
    kinds = {
        "readiness_timeout": "readiness_timeout",
        "visualization_render_failed": "render_failed",
    }
    confirmed = set()
    for code, kind in kinds.items():
        failures = [e for e in ui.get("events", []) if e.get("kind") == kind]
        if failures and all(e in recorded for e in failures):
            confirmed.add(code)
    return [code for code in ui.get("issues", []) if code not in confirmed]


def score_product_outcome(case: dict, result: dict) -> dict:
    """Score one completed recorder result, keeping all three evidence layers.

    The caller supplies the already validated decision scores and recorder-owned
    trace/UI/runtime snapshots. Missing observations fail closed; explicit model
    or product failures remain measured failures rather than exclusions.
    """
    trace = result.get("trace", {})
    scores = result.get("scores", {})
    ui = result.get("ui", {})
    runtime = result.get("runtime_evidence", {})
    ui_issues = ui_measurement_issues(ui)
    product_failures = set(ui.get("issues", [])) - set(ui_issues)
    issues = [
        issue for issue in result.get("issues", []) if issue not in product_failures
    ]
    issues.extend(ui_issues)
    for source, key in (
        (scores, "measurement_issues"),
        (trace, "measurement_issues"),
        (runtime, "issues"),
    ):
        issues.extend(source.get(key, []))
    if scores.get("measurement_valid") is not True:
        issues.append("decision_measurement_unavailable")
    if any(source.get("case_id") != case.get("case_id") for source in (result, trace)):
        issues.append("case_identity_mismatch")
    if not all(
        isinstance(result.get(key), dict) for key in ("before_state", "after_state")
    ):
        issues.append("state_observation_missing")
    terminal = trace.get("turn_terminal")
    if not isinstance(terminal, dict):
        issues.append("turn_terminal_missing")
    correct = scores.get("final_decision_correct")
    if type(correct) is not bool:
        issues.append("decision_correctness_missing")
    events = trace.get("events", [])

    def payloads(kind):
        return [
            e["payload"]
            for e in events
            if e.get("kind") == kind and isinstance(e.get("payload"), dict)
        ]

    admissions = [p for p in payloads("host_decision") if p.get("kind") == "admission"]
    commands = payloads("command_result")
    requests = payloads("ui_requested")
    navigation = [
        p for p in payloads("navigation_requested") if p.get("correlation") is not None
    ]
    expected = case.get("expected_tool")
    matching = [p for p in admissions if p.get("command_name") == expected]
    admission = matching[-1].get("action") if matching else "not_proposed"
    observed_actions = (
        [
            {
                "kind": "command_result",
                "tool_name": p.get("tool_name"),
                "ok": p.get("ok"),
            }
            for p in commands
        ]
        + [
            {
                "kind": "ui_requested",
                "tool_name": p.get("tool_name"),
                "request_id": p.get("request_id"),
            }
            for p in requests
        ]
        + [
            {
                "kind": "navigation_requested",
                "target": p.get("target"),
                "view_mode": p.get("view_mode"),
            }
            for p in navigation
        ]
    )
    answer = {
        "measurement_valid": False,
        "issues": issues,
        "decision_correct": correct,
        "admission": admission,
        "execution": "not_started",
        "ui_handoff": "not_requested",
        "outcome": "not_evaluated",
        "observed_actions": observed_actions,
        "observed_execution": "command_result_received"
        if commands
        else "requested"
        if observed_actions
        else "not_started",
        "unexpected_action": False,
    }

    if case.get("decision") in {"No-call", "Clarification"}:
        effects = (
            commands or requests or navigation or payloads("confirmation_requested")
        )
        answer["outcome"] = (
            "unexpected_execution" if effects else "correct_nonexecution"
        )
        answer["unexpected_action"] = bool(effects)
        if effects:
            answer["execution"] = "unexpected_action"
        if not effects and correct and (terminal or {}).get("outcome") != "completed":
            issues.append("normal_nonexecution_terminal_missing")
    elif isinstance(admission, str) and admission.endswith("blocked"):
        answer["outcome"] = "blocked"
    else:
        selected_commands = [p for p in commands if p.get("tool_name") == expected]
        selected_requests = [p for p in requests if p.get("tool_name") == expected]
        if selected_commands:
            _command_outcome(expected, selected_commands[-1], runtime, result, answer)
        elif selected_requests:
            _ui_outcome(
                selected_requests[-1], payloads("ui_resolution"), ui, runtime, answer
            )
        elif navigation:
            _navigation_outcome(navigation[-1], ui, answer)
        elif correct:
            issues.append("product_execution_observation_missing")
        elif observed_actions:
            answer["execution"] = "different_action"

    # Host protection, driver confirmation, or an unrelated successful command
    # cannot rescue an incorrect model decision. Retain observed layer fields.
    if correct is False:
        answer["outcome"] = "decision_incorrect"
    answer["issues"] = list(dict.fromkeys(issues))
    answer["measurement_valid"] = not answer["issues"]
    if not answer["measurement_valid"]:
        answer["outcome"] = "invalid_measurement"
    return answer


def _command_outcome(tool, command, runtime, result, answer):
    if type(command.get("ok")) is not bool:
        answer["issues"].append("command_result_status_missing")
        return
    execution = "completed" if command["ok"] else "failed"
    if command["ok"] and tool in {"start_training", "stop_training"}:
        training = runtime.get("training", {})
        outcome = training.get("outcome", {})
        if (
            training.get("action") != tool
            or training.get("matched") is not True
            or not training.get("expected_run")
            or training["expected_run"] != outcome.get("run")
        ):
            answer["issues"].append("training_terminal_binding_missing")
            execution = "unknown"
        elif result.get("fixture_cancel_requested", {}).get("accepted"):
            execution = "harness_cancelled"
        else:
            state = outcome.get("state")
            success = "completed" if tool == "start_training" else "cancelled"
            execution = "completed" if state == success else state
            if state not in {"completed", "failed", "cancelled"}:
                answer["issues"].append("training_terminal_missing")
            elif tool == "stop_training" and state == "completed":
                execution = "finished_before_stop"
    answer["execution"] = answer["outcome"] = execution


def _ui_outcome(request, resolutions, ui, runtime, answer):
    request_id = request.get("request_id")
    if not request_id:
        answer["issues"].append("ui_request_identity_missing")
        return
    events = [e for e in ui.get("events", []) if e.get("request_id") == request_id]
    failures = [
        e for e in _recorded_ui_failures(ui) if e.get("request_id") == request_id
    ]
    if failures:
        answer["ui_handoff"] = (
            "timed_out" if failures[-1]["kind"] == "readiness_timeout" else "failed"
        )
        answer["outcome"] = "failed"
        answer["execution"] = (
            "not_evaluated" if request.get("kind") == "decision_required" else "failed"
        )
        return
    ready = [e for e in events if e.get("kind") in {"dialog_ready", "panel_ready"}]
    resolved = [
        p
        for p in resolutions
        if p.get("request_id") == request_id
        and p.get("tool_name") == request.get("tool_name")
    ]
    terminal = [
        p
        for p in resolved
        if p.get("status") in {"completed", "failed", "cancelled", "blocked"}
    ]
    if ready:
        answer["ui_handoff"] = "ready"
    if request.get("kind") == "decision_required":
        answer["execution"] = "not_evaluated"
        if ready:
            answer["outcome"] = "handoff_ready"
        elif terminal and terminal[-1]["status"] in {"failed", "blocked"}:
            answer["outcome"] = terminal[-1]["status"]
        else:
            answer["issues"].append("ui_readiness_observation_missing")
        return
    if not terminal:
        answer["issues"].append("ui_action_terminal_missing")
        return
    answer["execution"] = answer["outcome"] = terminal[-1]["status"]
    if terminal[-1]["status"] != "completed":
        return
    if not ready or not any(
        e.get("projection_ready") is True and e.get("render_ready") is True
        for e in ready
    ):
        answer["issues"].append("ui_action_render_observation_missing")
    # Saliency has two distinct owners: compute and visualization rendering.
    # Their operation IDs must not be compared as though they were one job.
    if request.get("tool_name") == "compute_saliency":
        operation_id = runtime.get("saliency_operation_id")
        job = runtime.get("jobs", {}).get(operation_id, {})
        if job.get("kind") != "saliency" or job.get("phase") != "completed":
            answer["issues"].append("saliency_compute_terminal_missing")


def _navigation_outcome(request, ui, answer):
    failures = [
        e
        for e in _recorded_ui_failures(ui)
        if all(
            e.get(k) == request.get(k) for k in ("target", "view_mode", "correlation")
        )
    ]
    if failures:
        answer.update(
            execution="failed",
            outcome="failed",
            ui_handoff="timed_out"
            if failures[-1]["kind"] == "readiness_timeout"
            else "failed",
        )
        return
    ready = any(
        e.get("kind") == "panel_ready"
        and all(
            e.get(key) == request.get(key)
            for key in ("target", "view_mode", "correlation")
        )
        and e.get("projection_ready") is True
        and e.get("render_ready") is not False
        for e in ui.get("events", [])
    )
    if ready:
        answer.update(execution="completed", ui_handoff="ready", outcome="completed")
    else:
        answer["issues"].append("navigation_readiness_observation_missing")
