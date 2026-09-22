"""Read preserved Pilot artifacts; report partial evidence without model ranking."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from statistics import median

from scripts.dev.assistant_pilot_presentation import _details, write_presentation
from scripts.dev.run_assistant_pilot import (
    CONDITIONS,
    DEV_EXPERIMENT,
    SCHEMA,
    build_jobs,
    consumed_seconds,
    read_journal,
    valid_measurement,
)

CATEGORIES = ("Action", "Clarification", "No-call")
_MAX_ARTIFACT_BYTES = 32 * 1024**2


def _read(path: Path, expected_sha256: str | None = None) -> tuple[dict, str]:
    with path.open("rb") as source:
        content = source.read(_MAX_ARTIFACT_BYTES + 1)
    if len(content) > _MAX_ARTIFACT_BYTES:
        raise ValueError("Artifact exceeds bounded reader size")
    digest = hashlib.sha256(content).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("Artifact hash mismatch")
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("Artifact must be an object")
    return value, digest


def _summary(values: list[float]) -> dict:
    return {
        "n": len(values),
        "p50": median(values) if values else None,
        "max": max(values) if values else None,
    }


def _rate(values: list[bool]) -> dict:
    return {
        "numerator": sum(values),
        "denominator": len(values),
        "rate": sum(values) / len(values) if values else None,
    }


def _terminal_latencies(rows: list[dict]) -> tuple[dict, dict]:
    """DEV terminal time includes valid failures; each exclusion has one reason."""
    included, excluded = [], Counter()
    for row in rows:
        reason = None
        if row["evidence_status"] != "verified":
            reason = row["evidence_status"]
        elif not row["decision_valid"]:
            reason = "invalid_measurement"
        elif not row["case_recorded"]:
            reason = "case_not_recorded"
        elif "decision" not in row["timings"]:
            reason = "decision_timing_unavailable"
        if reason:
            excluded[reason] += 1
        else:
            included.append(row)
    summaries = {}
    for label, success in (("overall", None), ("success", True), ("failure", False)):
        values = sorted(
            row["timings"]["decision"]
            for row in included
            if success is None or row["final"] is success
        )
        p95 = None
        if values:
            position = (len(values) - 1) * 0.95
            lower, upper = math.floor(position), math.ceil(position)
            p95 = values[lower] + (values[upper] - values[lower]) * (position - lower)
        summaries[label] = {**_summary(values), "p95": p95}
    return summaries, {
        "planned": len(rows),
        "included": len(included),
        "excluded": sum(excluded.values()),
        "exclusions": dict(excluded),
        "execution_status_counts": dict(
            Counter(row["execution_status"] for row in included)
        ),
    }


def _timings(result: dict) -> tuple[dict, list[str]]:
    timings, issues = {}, []
    condition_evidence = result.get("condition_evidence")
    values = {
        "decision": result.get("decision_seconds"),
        "fixture": result.get("fixture_seconds"),
        "case_operation": result.get("case_operation_seconds"),
        "case_turn": result.get("case_turn_seconds"),
        "cleanup": result.get("cleanup_seconds"),
        "total": result.get("total_seconds"),
    }
    if not isinstance(condition_evidence, dict):
        values.update(
            model_load=result.get("model_load_seconds"),
            warmup=result.get("warmup", {}).get("seconds"),
            rag_warmup=result.get("rag_warmup", {}).get("seconds"),
        )
    for name, value in values.items():
        if name == "rag_warmup" and result.get("rag_enabled") is False:
            continue
        if value is None:
            issues.append("timing_unavailable:" + name)
        elif type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            issues.append("timing_invalid:" + name)
        else:
            timings[name] = value
    return timings, issues


def _condition_runtime_timings(result: dict) -> tuple[dict | None, list[str]]:
    evidence = result.get("condition_evidence")
    if evidence is None:
        return None, []
    if not isinstance(evidence, dict):
        return None, ["condition_evidence_invalid"]
    values = {
        "model_load": evidence.get("model_load_seconds"),
        "warmup": evidence.get("warmup", {}).get("seconds"),
    }
    if result.get("rag_enabled") is True:
        values["rag_warmup"] = evidence.get("rag_warmup", {}).get("seconds")
    issues = [
        "condition_timing_invalid:" + name
        for name, value in values.items()
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0
    ]
    runtime = evidence.get("runtime", {})
    if runtime.get("model_id") != result.get("model_id"):
        issues.append("condition_runtime_identity_mismatch")
    return (evidence if not issues else None), issues


def _provenance_issues(result: dict) -> list[str]:
    issues = []
    for name in ("input_audit", "capture_audit"):
        audit = result.get(name)
        if not isinstance(audit, dict) or not isinstance(audit.get("issues"), list):
            issues.append(name + ":missing")
        elif audit["issues"]:
            issues.append(name + ":failed")
    return issues


def _ui_request_key(event: dict) -> tuple | None:
    request_id = event.get("request_id")
    if isinstance(request_id, str) and request_id:
        return ("handoff", request_id)
    correlation = event.get("correlation")
    if event.get("route") != "panel_navigation":
        return None
    target, view = event.get("target"), event.get("view_mode")
    if (
        not isinstance(target, str)
        or not target
        or (view is not None and not isinstance(view, str))
    ):
        return None
    if correlation is None:
        return ("companion", target, view)
    if not isinstance(correlation, dict):
        return None
    turn, generation = correlation.get("turn_id"), correlation.get("generation")
    if (
        type(turn) is not int
        or turn <= 0
        or type(generation) is not int
        or generation <= 0
        or not isinstance(target, str)
        or not target
        or (view is not None and not isinstance(view, str))
    ):
        return None
    return ("navigation", turn, generation, target, view)


def _ui_latencies(result: dict) -> tuple[list[float], list[str]]:
    """Match actual ready observations to one captured signal by request identity."""
    events = result.get("ui", {}).get("events", [])
    values, issues = [], []
    for ready in events:
        if ready.get("kind") not in {"dialog_ready", "panel_ready"}:
            continue
        identity = _ui_request_key(ready)
        matches = [
            event
            for event in events
            if identity
            and event.get("kind") == "request_observed"
            and _ui_request_key(event) == identity
        ]
        ready_count = sum(
            event.get("kind") in {"dialog_ready", "panel_ready"}
            and _ui_request_key(event) == identity
            for event in events
        )
        if len(matches) != 1 or ready_count != 1:
            issues.append("ui_latency_unpaired")
            continue
        start, end = (
            matches[0].get("signal_observed_ns"),
            ready.get("ready_observed_ns"),
        )
        if type(start) is not int or type(end) is not int or start < 0 or end < start:
            issues.append("ui_latency_invalid_clock")
            continue
        values.append((end - start) / 1e9)
    return values, issues


def _repair(scores: dict) -> dict:
    attempts = scores.get("attempt_decisions", [])
    count = scores.get("repair_count")
    if (
        type(count) is not int
        or not 0 <= count <= 2
        or count != max(0, len(attempts) - 1)
        or any(type(attempt.get("correct")) is not bool for attempt in attempts)
    ):
        return {"count": None, "first_new_correct": False, "second_new_correct": False}
    correct = [attempt["correct"] for attempt in attempts]
    return {
        "count": count,
        "first_new_correct": len(correct) >= 2 and not correct[0] and correct[1],
        "second_new_correct": len(correct) == 3 and not any(correct[:2]) and correct[2],
    }


def _case(root: Path, job: dict, start: dict | None, end: dict | None) -> dict:
    artifact = start.get("artifact_id", job["id"]) if start else job["id"]
    row = {
        **job,
        "artifact_id": artifact,
        "evidence_status": "missing",
        "decision_valid": False,
        "issues": [],
    }
    if start is None:
        return row
    if end is None:
        return {**row, "evidence_status": "unresolved"}
    try:
        request_sha, result_sha = start.get("request_sha256"), end.get("result_sha256")
        if not all(
            isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
            for value in (request_sha, result_sha)
        ):
            raise ValueError("Missing recorded request/result digest")  # noqa: TRY301 - preserve a per-case invalid-evidence row
        request, _ = _read(root / "cases" / f"{artifact}.request.json", request_sha)
        result, _ = _read(root / "cases" / artifact / "result.json", result_sha)
        row.update(
            request_sha256=request_sha,
            result_sha256=result_sha,
            measurement_status=result.get("status"),
        )
        model, rag = CONDITIONS[job["condition"]]
        case = request["case"]
        if (
            case.get("case_id") != job["case_id"]
            or case.get("split") != "DEV"
            or case.get("decision") != job["decision"]
            or request.get("model_id") != model
            or request.get("rag_enabled") is not rag
            or type(request.get("seed")) is not int
            or request["seed"] != 0
            or type(request.get("repeat")) is not int
            or request["repeat"] != 0
            or result.get("case_id") != job["case_id"]
            or result.get("case") != case
            or result.get("model_id") != model
            or result.get("rag_enabled") is not rag
            or result.get("schema") != "xbrainlab.assistant_pilot_case.v1"
        ):
            raise ValueError("Case/model/condition identity mismatch")  # noqa: TRY301 - preserve a per-case invalid-evidence row
        scores = result.get("scores", {})
        provenance_issues = _provenance_issues(result)
        valid = scores.get("measurement_valid") is True and not provenance_issues
        if valid and (
            any(
                type(scores.get(f"{phase}_decision_correct")) is not bool
                for phase in ("first", "final")
            )
            or scores.get("execution_status")
            not in {"completed", "decision_timeout", "model_error", "cancelled"}
            or (
                scores.get("execution_status") == "decision_timeout"
                and scores["final_decision_correct"]
            )
            or bool(scores.get("measurement_issues"))
            or (result.get("decision_timed_out") is True)
            != (scores.get("execution_status") == "decision_timeout")
        ):
            raise ValueError("Invalid decision score contract")  # noqa: TRY301 - preserve a per-case invalid-evidence row
        timings, timing_issues = _timings(result)
        condition_evidence, condition_timing_issues = _condition_runtime_timings(result)
        ui_latencies, ui_timing_issues = _ui_latencies(result)
        product = result.get("product_outcome")
        row.update(
            evidence_status="verified",
            decision_valid=valid,
            execution_status=scores.get("execution_status", "invalid_measurement"),
            first=scores.get("first_decision_correct") if valid else None,
            final=scores.get("final_decision_correct") if valid else None,
            measurement_status=result.get("status"),
            case_recorded=end.get("status") == "recorded"
            and result.get("status") == "recorded"
            and result.get("cleanup_ok") is True
            and end.get("cleanup_certified") is True,
            invalid_model_output=any(
                attempt.get("reason") == "invalid_envelope"
                for attempt in scores.get("attempt_decisions", [])
            ),
            request_sha256=request_sha,
            result_sha256=result_sha,
            timings=timings,
            timing_issues=timing_issues + condition_timing_issues + ui_timing_issues,
            timing_complete=not (
                timing_issues or condition_timing_issues or ui_timing_issues
            ),
            condition_evidence=condition_evidence,
            ui_handoff_seconds=ui_latencies,
            repairs=_repair(scores),
            product_outcome=product,
            product_measurement_valid=isinstance(product, dict)
            and product.get("measurement_valid") is True
            and all(
                isinstance(product.get(key), str)
                for key in ("outcome", "execution", "ui_handoff")
            ),
            issues=result.get("issues", [])
            + scores.get("measurement_issues", [])
            + provenance_issues,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        row.update(evidence_status="invalid_evidence", issues=[str(exc)])
    return row


def _condition(
    rows: list[dict], *, dev: bool = False, previous: list[dict] | None = None
) -> dict:
    categories = {}
    for category in CATEGORIES:
        matching = [row for row in rows if row["decision"] == category]
        valid = [row for row in matching if row["decision_valid"]]
        categories[category] = {
            "planned": len(matching),
            **{
                phase: _rate([row[phase] for row in valid])
                for phase in ("first", "final")
            },
        }
    macro = {}
    for phase in ("first", "final"):
        values = [categories[category][phase]["rate"] for category in CATEGORIES]
        macro[phase] = (
            sum(values) / 3 if all(value is not None for value in values) else None
        )
    counts = Counter(
        {
            "planned": len(rows),
            "valid_decision": 0,
            "decision_timeout": 0,
            "model_error": 0,
            "cancelled": 0,
            "invalid_measurement": 0,
            "invalid_evidence": 0,
            "missing": 0,
            "unresolved": 0,
            "case_measurement_failed": 0,
            "timing_incomplete": 0,
            "product_outcome_missing": 0,
            "product_measurement_invalid": 0,
            "invalid_model_output": 0,
        }
    )
    for row in rows:
        if row["evidence_status"] != "verified":
            counts[row["evidence_status"]] += 1
            continue
        counts[
            "valid_decision" if row["decision_valid"] else "invalid_measurement"
        ] += 1
        counts["case_measurement_failed"] += not row["case_recorded"]
        counts["timing_incomplete"] += not row["timing_complete"]
        counts["product_outcome_missing"] += not isinstance(
            row["product_outcome"], dict
        )
        counts["product_measurement_invalid"] += not row["product_measurement_valid"]
        counts["decision_timeout"] += row["execution_status"] == "decision_timeout"
        counts["model_error"] += row["execution_status"] == "model_error"
        counts["cancelled"] += row["execution_status"] == "cancelled"
        counts["invalid_model_output"] += row["invalid_model_output"]
    completed = [
        row
        for row in rows
        if row["decision_valid"]
        and row["execution_status"] == "completed"
        and "decision" in row["timings"]
    ]
    timings = {}
    measured_rows = rows + (previous or [])
    for name in ("fixture", "case_operation", "case_turn", "cleanup", "total"):
        values = [
            row["timings"][name]
            for row in measured_rows
            if name in row.get("timings", {})
        ]
        timings[name] = {**_summary(values), "total": sum(values)}
    evidence = [
        row["condition_evidence"]
        for row in measured_rows
        if isinstance(row.get("condition_evidence"), dict)
    ]
    if evidence:
        groups = {}
        for item in evidence:
            identity = item.get("artifact_id", "legacy") if dev else "legacy"
            groups.setdefault(identity, []).append(item)
        runtimes = [
            group[0]
            for group in groups.values()
            if len({json.dumps(item, sort_keys=True) for item in group}) == 1
        ]
        for name in ("model_load", "warmup", "rag_warmup"):
            values = []
            for runtime in runtimes:
                value = (
                    runtime.get("model_load_seconds")
                    if name == "model_load"
                    else (runtime.get(name) or {}).get("seconds")
                )
                if type(value) in (int, float):
                    values.append(value)
            timings[name] = {**_summary(values), "total": sum(values)}
    else:
        for name in ("model_load", "warmup", "rag_warmup"):
            values = [
                row["timings"][name]
                for row in measured_rows
                if name in row.get("timings", {})
            ]
            timings[name] = {**_summary(values), "total": sum(values)}
    result = {
        "counts": dict(counts),
        "categories": categories,
        "macro": macro,
        "decision_latency_seconds": {
            label: _summary(
                [
                    row["timings"]["decision"]
                    for row in completed
                    if row["final"] is success
                ]
            )
            for label, success in (("success", True), ("failure", False))
        },
        "overhead_seconds": timings,
        "product_counts": {
            key: dict(
                Counter(
                    row["product_outcome"][key]
                    for row in rows
                    if isinstance(row.get("product_outcome"), dict)
                    and isinstance(row["product_outcome"].get(key), str)
                )
            )
            for key in ("outcome", "execution", "ui_handoff")
        },
        "repairs": {
            "histogram": {
                str(count): sum(
                    row["decision_valid"]
                    and row.get("repairs", {}).get("count") == count
                    for row in rows
                )
                for count in range(3)
            },
            "unavailable": sum(
                row["decision_valid"] and row.get("repairs", {}).get("count") is None
                for row in rows
            ),
            "first_new_correct": sum(
                row["decision_valid"]
                and row.get("repairs", {}).get("first_new_correct", False)
                for row in rows
            ),
            "second_new_correct": sum(
                row["decision_valid"]
                and row.get("repairs", {}).get("second_new_correct", False)
                for row in rows
            ),
        },
        "ui_handoff_latency_seconds": _summary(
            [value for row in rows for value in row.get("ui_handoff_seconds", [])]
        ),
    }
    if dev:
        result["overall"] = {
            phase: _rate([row[phase] for row in rows if row["decision_valid"]])
            for phase in ("first", "final")
        }
        result["decision_latency_seconds"], result["decision_latency_audit"] = (
            _terminal_latencies(rows)
        )
    return result


def build_report(run: Path) -> dict:
    root = run.resolve(strict=True)
    manifest, manifest_sha = _read(root / "manifest.json")
    experiment = manifest.get("experiment")
    dev = experiment == DEV_EXPERIMENT
    if experiment is not None and not dev:
        raise ValueError("Unknown experiment protocol identity")
    jobs = manifest.get("jobs", [])
    if (
        manifest.get("schema") != SCHEMA
        or not isinstance(jobs, list)
        or not 0 < len(jobs) <= (1320 if dev else 300)
        or len({job["id"] for job in jobs}) != len(jobs)
        or any(
            not re.fullmatch(r"[A-Za-z0-9_-]+", job["id"])
            or job.get("condition") not in CONDITIONS
            or job.get("decision") not in CATEGORIES
            or job["id"] != f"{job['condition']}__{job['case_id']}"
            or (dev and not CONDITIONS[job["condition"]][1])
            for job in jobs
        )
    ):
        raise ValueError("Invalid frozen manifest job inventory")
    journal_path = root / "journal.jsonl"
    journal_bytes = journal_path.read_bytes() if journal_path.exists() else b""
    records = read_journal(root)
    starts, ends, previous = {}, {}, []
    known = {job["id"]: job for job in jobs}
    for record in records:
        if record["event"] in {"case_start", "case_end"}:
            target = starts if record["event"] == "case_start" else ends
            identity = record.get("id")
            if identity not in known:
                raise ValueError("Duplicate or uncorrelated case journal")
            attempt = record.get("attempt", 1)
            artifact = record.get("artifact_id", identity)
            if (
                type(attempt) is not int
                or attempt not in (1, 2)
                or artifact != (identity if attempt == 1 else identity + "__attempt-2")
                or (not dev and attempt != 1)
            ):
                raise ValueError("Invalid case attempt identity")
            if target is starts and identity in starts:
                prior_end = ends.get(identity)
                if (
                    not dev
                    or not prior_end
                    or attempt != 2
                    or starts[identity].get("attempt", 1) != 1
                ):
                    raise ValueError("Duplicate or unresolved case journal")
                digest = prior_end.get("result_sha256")
                if not isinstance(digest, str) or not re.fullmatch(
                    r"[0-9a-f]{64}", digest
                ):
                    raise ValueError("Replacement original result digest is missing")
                prior_result, _ = _read(
                    root / "cases" / identity / "result.json",
                    digest,
                )
                if valid_measurement(prior_end, prior_result):
                    raise ValueError("Cannot replace a valid recorded measurement")
                if (
                    prior_end.get("cleanup_certified") is not True
                    or record.get("replaces_artifact_id") != identity
                ):
                    raise ValueError("Uncertified or uncorrelated replacement")
                original = _case(root, known[identity], starts[identity], prior_end)
                previous.append(original)
                del ends[identity]
            elif target is starts and (
                attempt != 1 or record.get("replaces_artifact_id") is not None
            ):
                raise ValueError("Replacement has no original measurement")
            elif target is ends and (
                identity in ends
                or identity not in starts
                or any(
                    record.get(key, default) != starts[identity].get(key, default)
                    for key, default in (
                        ("artifact_id", identity),
                        ("attempt", 1),
                        ("replaces_artifact_id", None),
                    )
                )
            ):
                raise ValueError("Duplicate or uncorrelated case journal")
            target[identity] = record
    rows = [
        _case(root, job, starts.get(job["id"]), ends.get(job["id"])) for job in jobs
    ]
    if dev:
        for row in rows:
            issues = _details(root, row, require_generation=True)["issues"]
            row["capture_integrity"] = {"verified": not issues, "issues": issues}
            if issues:
                row.update(decision_valid=False, first=None, final=None)
                row["issues"].append("capture_artifact_integrity_failed")
    for condition in {row["condition"] for row in rows}:
        matching = [
            row
            for row in rows + previous
            if row["condition"] == condition and row["evidence_status"] == "verified"
        ]
        groups = {}
        for row in matching:
            identity = (
                (row.get("condition_evidence") or {}).get("artifact_id", "legacy")
                if dev
                else "legacy"
            )
            groups.setdefault(identity, []).append(row)
        for group in groups.values():
            evidence = [row.get("condition_evidence") for row in group]
            if any(item is not None for item in evidence) and (
                any(not isinstance(item, dict) for item in evidence)
                or len({json.dumps(item, sort_keys=True) for item in evidence}) != 1
            ):
                for row in group:
                    row["timing_complete"] = False
                    row["timing_issues"].append("condition_evidence_mismatch")
    conditions = {
        condition: _condition(
            [row for row in rows if row["condition"] == condition],
            dev=dev,
            previous=[row for row in previous if row["condition"] == condition],
        )
        for condition in CONDITIONS
        if any(row["condition"] == condition for row in rows)
    }
    session_cleanup_certified = bool(
        records
        and records[-1]["event"] == "session_end"
        and records[-1].get("cleanup_certified") is True
    )
    complete = session_cleanup_certified and all(
        row.get("case_recorded")
        and row["decision_valid"]
        and row["timing_complete"]
        and row["product_measurement_valid"]
        for row in rows
    )
    full_matrix = (
        len(jobs) == 300
        and len(conditions) == 10
        and all(
            [condition["categories"][category]["planned"] for category in CATEGORIES]
            == [18, 6, 6]
            for condition in conditions.values()
        )
        and all(
            sum(job["phase"] == 1 for job in jobs if job["condition"] == name) == 6
            for name in conditions
        )
    )
    selection = manifest.get("selection", {})
    if not all(
        isinstance(selection.get(key), list)
        for key in ("phase_one_case_ids", "phase_two_case_ids")
    ):
        full_matrix = False
    elif full_matrix:
        expected = build_jobs(selection, list(CONDITIONS))
        full_matrix = [
            {key: job[key] for key in ("id", "condition", "case_id", "phase")}
            for job in jobs
        ] == expected
    dev_matrix = False
    if dev:
        case_ids = selection.get("case_ids", [])
        expected_conditions = [name for name, (_, rag) in CONDITIONS.items() if rag]
        dev_matrix = (
            selection.get("schema") == "xbrainlab.assistant_dev_selection.v1"
            and len(case_ids) == 264
            and len(set(case_ids)) == 264
            and case_ids == sorted(case_ids)
            and selection.get("counts")
            == {"Action": 144, "Clarification": 48, "No-call": 72}
            and selection.get("phase_one_case_ids") == case_ids
            and selection.get("phase_two_case_ids") == []
            and list(conditions) == expected_conditions
            and all(
                [
                    condition["categories"][category]["planned"]
                    for category in CATEGORIES
                ]
                == [144, 48, 72]
                for condition in conditions.values()
            )
            and [
                {key: job[key] for key in ("id", "condition", "case_id", "phase")}
                for job in jobs
            ]
            == build_jobs(selection, expected_conditions)
        )
    charged = consumed_seconds(records)
    if (journal_path.read_bytes() if journal_path.exists() else b"") != journal_bytes:
        raise ValueError(
            "Journal changed during report; retain artifacts and read a stable snapshot"
        )
    return {
        "schema": "xbrainlab.assistant_dev_report.v1"
        if dev
        else "xbrainlab.assistant_pilot_report.v1",
        "experiment": experiment,
        "latency_protocol": {
            "population": "valid_recorded_decision_terminals"
            if dev
            else "completed_decisions_only",
            "quantile_method": "linear interpolation at (n - 1) * p"
            if dev
            else "median; P95 not reported",
        },
        "run": str(root),
        "manifest_sha256": manifest_sha,
        "journal_sha256": hashlib.sha256(journal_bytes).hexdigest(),
        "session_cleanup_certified": session_cleanup_certified,
        "frozen_source": manifest["source"],
        "frozen_environment": manifest["environment"],
        "complete_selected_schedule": complete,
        "pilot_complete": not dev and full_matrix and complete,
        "dev_complete": dev and dev_matrix and complete,
        "partial": not ((dev_matrix if dev else full_matrix) and complete),
        "ranking_allowed": False,
        "limitations": [
            (
                "DEV initial baseline only; no tuning, Validation/Test conclusion or formal model ranking. P95 is descriptive."
                if dev
                else "DEV Pilot only; no formal model ranking or stable P95."
            ),
            "Incomplete conditions and invalid measurements are not model-correct decisions.",
            "Decision accuracy is separate from UI/backend outcomes; inspect preserved per-case evidence.",
            (
                "Latency includes all valid recorded decision terminals, including invalid output, host-blocked decisions and valid decision timeouts; it is not time to successful completion. Missing decision timing and invalid/unrecorded measurements are excluded with audited counts."
                if dev
                else "Latency includes only completed decisions, split by final correctness; timeouts are censored, not completion times."
            ),
            "Resumed active time includes setup and cleanup, excludes user idle; unresolved children retain conservative timeout reservations.",
        ],
        "active_budget": {
            "limit_seconds": manifest["budget_seconds"],
            "charged_seconds": charged,
            "remaining_seconds": max(0, manifest["budget_seconds"] - charged),
            "includes_conservative_reservations": bool(starts.keys() - ends.keys()),
        },
        "conditions": conditions,
        "cases": rows,
        "superseded_cases": previous,
    }


def write_report(run: Path, output: Path) -> dict:
    report = build_report(run)
    output.mkdir()
    write_presentation(report, output)
    with (output / "report.json").open("x", encoding="utf-8") as target:
        json.dump(
            report,
            target,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = write_report(args.run, args.output)
    print(
        json.dumps(
            {"partial": result["partial"], "report": str(args.output.absolute())}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
