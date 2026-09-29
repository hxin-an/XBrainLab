"""Compare two saved experiment runs without inference, rescoring or input writes.

Uses a saved report bound to the current manifest/journal, then verifies its raw
request/result/capture evidence. An unavailable report is an explicit evidence
failure, never an invitation to rebuild scores with today's implementation.
"""

# Read-only fixed Git commands and explicit malformed-artifact aggregation.
# ruff: noqa: S607, TRY301

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from scripts.dev.assistant_experiment_audit import evidence_digest
from scripts.dev.assistant_pilot_presentation import _bytes, _details


def _json(root: Path, path: Path) -> dict:
    value = json.loads(_bytes(root, path))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _canonical(value) -> str:
    def normalized(item):
        if isinstance(item, dict):
            return {key: normalized(value) for key, value in item.items()}
        if isinstance(item, list):
            return [normalized(value) for value in item]
        if isinstance(item, float) and item.is_integer():
            return int(item)
        return item

    value = normalized(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _key(row: dict) -> tuple:
    return (row["condition"], row["case_id"], row.get("repeat", 0))


def _scoring_source(run: Path, job: dict, manifest: dict) -> dict:
    """Read immutable Git objects, never import/execute the candidate's scorer.

    Include parser/validator, tool schemas and backend schema dependencies;
    unrelated prompt/RAG/controller edits need not invalidate score equivalence.
    If the frozen checkout is absent, identical clean source SHAs suffice.
    """
    head = job.get("source_head", manifest.get("source", {}).get("head"))
    identity = {"head": head, "dependency_tree": None}
    if (
        manifest.get("source", {}).get("dirty")
        or not isinstance(head, str)
        or not re.fullmatch(r"[0-9a-f]{40}", head)
    ):
        return {"head": None, "dependency_tree": None}
    roots = [run.parent.parent / "sources" / head]
    if job.get("source_root"):
        roots.append(Path(job["source_root"]))
    paths = [
        "scripts/dev/assistant_pilot_scoring.py",
        "XBrainLab/backend",
        "XBrainLab/llm/tools",
        "XBrainLab/llm/agent/decision_contract.py",
        "XBrainLab/llm/agent/parser.py",
        "XBrainLab/llm/agent/prompt_policy.py",
        "XBrainLab/llm/agent/verifier.py",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        try:
            tree = subprocess.check_output(  # noqa: S603 -- fixed read-only Git, validated SHA
                ["git", "-C", str(root), "ls-tree", "-r", head, "--", *paths],
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
            entries = [line.split(b"\t", 1)[-1].decode() for line in tree.splitlines()]
            if all(
                any(name == path or name.startswith(path + "/") for name in entries)
                for path in paths
            ):
                identity["dependency_tree"] = hashlib.sha256(tree).hexdigest()
                break
        except (OSError, subprocess.SubprocessError):
            continue
    return identity


def _read_entry(
    run: Path, manifest: dict, records: list, entry: dict, row: dict, identities: dict
) -> None:
    raw, job = run / "raw", entry["job"]
    artifact = row.get("artifact_id", row["id"])
    for event, field in (
        ("case_start", "request_sha256"),
        ("case_end", "result_sha256"),
    ):
        matches = [
            record
            for record in records
            if record.get("event") == event
            and record.get("id") == job["id"]
            and record.get("artifact_id", record.get("id")) == artifact
        ]
        if len(matches) != 1 or matches[0].get(field) != row.get(field):
            entry["issues"].append("missing_or_duplicate_journal_" + event)
    detail = _details(raw, row, require_generation=True)
    entry.update({key: detail[key] for key in ("request", "result")})
    entry["issues"].extend(detail["issues"])
    entry["captures"] = [
        {**item, "path": str(item["path"])} for item in detail["captures"]
    ]
    scores = detail["result"].get("scores", {})
    case = detail["request"].get("case", {})
    if case.get("case_id") != job["case_id"] or detail["result"].get("case") != case:
        entry["issues"].append("saved_case_identity_mismatch")
    for name in ("input_audit", "capture_audit"):
        if detail["result"].get(name, {}).get("issues") != []:
            entry["issues"].append(name + "_failed_or_missing")
    attempts = scores.get("attempt_decisions", [])
    if not isinstance(attempts, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("explanation", {}), dict)
        for item in attempts
    ):
        entry["issues"].append("malformed_saved_decisions")
    if (
        row.get("decision_valid") is not True
        or scores.get("measurement_valid") is not True
    ):
        entry["issues"].append("invalid_or_missing_measurement")
    if any(
        type(scores.get(phase + "_decision_correct")) is not bool
        or row.get(phase) != scores.get(phase + "_decision_correct")
        for phase in ("first", "final")
    ):
        entry["issues"].append("saved_score_mismatch_or_unavailable")
    entry["artifact"] = str(raw / "cases" / artifact / "result.json")
    head = job.get("source_head", manifest.get("source", {}).get("head"))
    if not isinstance(head, str):
        raise ValueError("Invalid source identity")
    if head not in identities:
        identities[head] = _scoring_source(run, job, manifest)
    entry["scoring_source"] = identities[head]
    entry["valid"] = not entry["issues"]
    seconds = detail["result"].get("decision_seconds")
    entry["seconds"] = (
        seconds
        if entry["valid"]
        and row.get("case_recorded") is True
        and type(seconds) in (int, float)
        and math.isfinite(seconds)
        and seconds >= 0
        and row.get("timings", {}).get("decision") == seconds
        else None
    )


def _load(run: Path) -> dict:
    state = {"run": str(run), "issues": [], "rows": [], "manifest": {}, "report": None}
    try:
        raw = run / "raw"
        manifest = state["manifest"] = _json(run, raw / "manifest.json")
        jobs = manifest["jobs"]
        if not isinstance(jobs, list) or not jobs or len(jobs) > 1485:
            raise ValueError("Invalid or unbounded job inventory")
        for job in jobs:
            if not isinstance(job, dict) or any(
                not isinstance(job.get(key), str)
                for key in ("id", "condition", "case_id")
            ):
                raise ValueError("Invalid job identity")
            if type(job.get("repeat", 0)) is not int:
                raise ValueError("Invalid repeat identity")
        manifest_sha = hashlib.sha256(_bytes(run, raw / "manifest.json")).hexdigest()
        journal_bytes = _bytes(run, raw / "journal.jsonl")
        journal_sha = hashlib.sha256(journal_bytes).hexdigest()
        records = [
            json.loads(line) for line in journal_bytes.splitlines() if line.strip()
        ]
        reports = sorted((run / "reports").glob("*/report.json"), reverse=True)
        report = None
        for path in reports:
            try:
                candidate = _json(run, path)
                if (
                    candidate.get("manifest_sha256") == manifest_sha
                    and candidate.get("journal_sha256") == journal_sha
                ):
                    report = candidate
                    state["report"] = str(path)
                    break
                state["issues"].append("stale_report:" + str(path.relative_to(run)))
            except (OSError, ValueError) as error:
                state["issues"].append("unreadable_report:" + str(error))
        if report is None:
            raise ValueError("No saved report matches the current manifest and journal")
        reported = defaultdict(list)
        for row in report["cases"]:
            reported[row["id"]].append(row)
        if Counter(row["id"] for row in report["cases"]) != Counter(
            job["id"] for job in jobs
        ):
            state["issues"].append("report_inventory_mismatch_or_duplicate")
        identities = {}
        for job in jobs:
            matching = reported[job["id"]]
            entry = {
                "job": job,
                "issues": [],
                "valid": False,
                "captures": [],
                "result": {},
                "request": {},
            }
            state["rows"].append(entry)
            if len(matching) != 1:
                entry["issues"].append("missing_or_duplicate_report_row")
                continue
            row = matching[0]
            if any(row.get(key) != value for key, value in job.items()):
                entry["issues"].append("report_job_identity_mismatch")
                continue
            try:
                _read_entry(run, manifest, records, entry, row, identities)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                entry["valid"] = False
                entry["issues"].append("malformed_case_evidence:" + str(error))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        state["issues"].append(str(error))
        # An unreadable case must not erase earlier independently verified cases.
        if state["rows"]:
            state["rows"][-1]["valid"] = False
            state["rows"][-1]["issues"].append("malformed_case_evidence:" + str(error))
        jobs = state["manifest"].get("jobs", [])
        if isinstance(jobs, list):
            state["rows"].extend(
                {
                    "job": job,
                    "issues": ["run_evidence_unavailable"],
                    "valid": False,
                    "captures": [],
                    "request": {},
                    "result": {},
                }
                for job in jobs[len(state["rows"]) :]
                if isinstance(job, dict)
                and all(
                    isinstance(job.get(key), str)
                    for key in ("id", "condition", "case_id")
                )
                and type(job.get("repeat", 0)) is int
            )
    return state


def _decision(entry: dict | None, phase: str) -> dict | None:
    if not entry or not entry["valid"]:
        return None
    attempts = entry["result"]["scores"].get("attempt_decisions", [])
    if not attempts:
        return None
    attempt = attempts[0 if phase == "first" else -1]
    tool = attempt.get("observed_tool")
    if not isinstance(tool, str) or not tool:
        return None  # two invalid/missing outputs are not matching decisions
    observed = attempt.get("explanation", {}).get("observed", {})
    if not isinstance(observed, dict):
        return {"tool": tool, "parameters": None, "parameters_available": False}
    parameters = observed.get("parameters")
    if tool == "respond_to_user":
        if parameters is not None and not isinstance(parameters, dict):
            return {"tool": tool, "parameters": None, "parameters_available": False}
        parameters = {
            key: value for key, value in (parameters or {}).items() if key != "message"
        }
    return {
        "tool": tool,
        "parameters": parameters,
        "parameters_available": tool == "respond_to_user"
        or (observed.get("tool") == tool and isinstance(parameters, dict)),
    }


def _comparable(a: dict | None, b: dict | None) -> tuple[bool, str]:
    if not a or not b or not a["valid"] or not b["valid"]:
        return False, "missing_or_invalid_evidence"
    if a["request"].get("case") != b["request"].get("case"):
        return False, "case_or_oracle_changed"
    sa, sb = a["result"]["scores"], b["result"]["scores"]
    keys = ("scorer_schema", "response_contract", "parameter_scope")
    if not sa.get("scorer_schema") or any(sa.get(key) != sb.get(key) for key in keys):
        return False, "scorer_contract_changed_or_unknown"
    ia, ib = a["scoring_source"], b["scoring_source"]
    same = ia["head"] and ia["head"] == ib["head"]
    if not same and not (
        ia["dependency_tree"] and ia["dependency_tree"] == ib["dependency_tree"]
    ):
        return False, "scorer_source_changed_or_unknown"
    return True, "same_saved_oracle_and_scorer_identity"


def _quantiles(values: list) -> dict:
    ordered = sorted(values)

    def percentile(p):
        if not ordered:
            return None
        position = (len(ordered) - 1) * p
        lower, upper = math.floor(position), math.ceil(position)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    return {"n": len(values), "p50": percentile(0.5), "p95": percentile(0.95)}


def _aggregate(rows: list) -> dict:
    result = {}
    for phase in ("first", "final"):
        values = [row[phase] for row in rows]
        counts = Counter(value["correctness"] for value in values)
        result[phase] = {
            "correctness": {
                key: counts[key]
                for key in (
                    "both_right",
                    "both_wrong",
                    "improved",
                    "regressed",
                    "unavailable",
                )
            }
        }
        for metric in ("tool_equal", "tool_parameters_equal"):
            known = [value[metric] for value in values if value[metric] is not None]
            result[phase][metric] = {
                "numerator": sum(known),
                "denominator": len(known),
                "unavailable": len(rows) - len(known),
                "rate": sum(known) / len(known) if known else None,
            }
    return result


def _timing(rows: list) -> dict:
    timing = {}
    for name in ("a", "b"):
        included = [
            row[name]["seconds"]
            for row in rows
            if row[name] and row[name].get("seconds") is not None
        ]
        exclusions = Counter(
            "missing_or_duplicate_alignment"
            if not row[name]
            else "invalid_evidence"
            if not row[name]["valid"]
            else "unrecorded_or_missing_invalid_timing"
            for row in rows
            if not row[name] or row[name].get("seconds") is None
        )
        timing[name] = {
            **_quantiles(included),
            "planned_union": len(rows),
            "excluded": len(rows) - len(included),
            "exclusions": dict(exclusions),
        }
    deltas = [
        row["timing_delta_b_minus_a"]
        for row in rows
        if row["timing_delta_b_minus_a"] is not None
    ]
    timing["paired_delta_b_minus_a"] = {
        **_quantiles(deltas),
        "planned_union": len(rows),
        "excluded": len(rows) - len(deltas),
    }
    return timing


def compare_runs(run_a: Path, run_b: Path) -> dict:
    """Read saved evidence and return comparisons aligned by condition/case/repeat."""
    paths = [Path(path).resolve(strict=True) for path in (run_a, run_b)]
    before = [evidence_digest(path) for path in paths]
    states = [_load(path) for path in paths]
    differences = []
    for field in (
        "source",
        "config",
        "models",
        "bank_sha256",
        "experiment",
        "corpus_sha256",
        "embedding_sha256",
        "environment",
        "resource_inventory_sha256",
    ):
        a, b = (state["manifest"].get(field) for state in states)
        if a != b or a is None:
            differences.append(
                {
                    "field": field,
                    "a": a,
                    "b": b,
                    "status": "unknown" if a is None or b is None else "different",
                }
            )
    indexes = []
    for state in states:
        indexed = defaultdict(list)
        for entry in state["rows"]:
            indexed[_key(entry["job"])].append(entry)
        indexes.append(indexed)
    rows = []
    for key in sorted(indexes[0].keys() | indexes[1].keys()):
        pair = [index[key][0] if len(index[key]) == 1 else None for index in indexes]
        a, b = pair
        comparable, reason = _comparable(a, b)
        if a and b and a["valid"] and b["valid"]:
            for field in (
                "scorer_schema",
                "response_contract",
                "parameter_scope",
                "max_format_recovery_attempts",
            ):
                va, vb = (entry["result"]["scores"].get(field) for entry in pair)
                if va != vb:
                    differences.append(
                        {
                            "field": field,
                            "condition": key[0],
                            "case_id": key[1],
                            "repeat": key[2],
                            "a": va,
                            "b": vb,
                            "status": "different",
                        }
                    )
        row = {
            "condition": key[0],
            "case_id": key[1],
            "repeat": key[2],
            "a": a,
            "b": b,
            "alignment_counts": [len(index[key]) for index in indexes],
            "correctness_comparable": comparable,
            "correctness_reason": reason,
        }
        for phase in ("first", "final"):
            da, db = (_decision(entry, phase) for entry in pair)
            tool_equal = da["tool"] == db["tool"] if da and db else None
            params_equal = (
                tool_equal
                and _canonical(da["parameters"]) == _canonical(db["parameters"])
                if da
                and db
                and da["parameters_available"]
                and db["parameters_available"]
                else None
            )
            correctness = "unavailable"
            if comparable:
                ca, cb = (
                    entry["result"]["scores"][phase + "_decision_correct"]
                    for entry in pair
                )
                correctness = (
                    "both_right"
                    if ca and cb
                    else "both_wrong"
                    if not ca and not cb
                    else "improved"
                    if cb
                    else "regressed"
                )
            row[phase] = {
                "tool_equal": tool_equal,
                "tool_parameters_equal": params_equal,
                "correctness": correctness,
                "a": da,
                "b": db,
            }
        row["timing_delta_b_minus_a"] = (
            b["seconds"] - a["seconds"]
            if a and b and a.get("seconds") is not None and b.get("seconds") is not None
            else None
        )
        row["changed"] = any(
            row[phase]["tool_parameters_equal"] is False
            or row[phase]["correctness"] in {"improved", "regressed"}
            for phase in ("first", "final")
        )
        rows.append(row)
    for reason in sorted(
        {row["correctness_reason"] for row in rows if not row["correctness_comparable"]}
    ):
        differences.append(
            {
                "field": "oracle_or_scorer",
                "status": reason,
                "cases": sum(row["correctness_reason"] == reason for row in rows),
            }
        )
    incompatible = (
        not rows
        or any(state["issues"] for state in states)
        or any(not row["correctness_comparable"] for row in rows)
        or any(
            item["field"] == "bank_sha256" or item["status"] == "unknown"
            for item in differences
        )
    )
    classification = (
        "incompatible_or_unknown"
        if incompatible
        else "candidate_comparison"
        if any(item["status"] == "different" for item in differences)
        else "same_config_reproduction"
    )
    after = [evidence_digest(path) for path in paths]
    if before != after:
        raise ValueError(
            "Original run evidence changed while comparison was reading it"
        )
    grouped = {}
    for condition, repeat in sorted(
        {(row["condition"], row["repeat"]) for row in rows}
    ):
        matching = [
            row
            for row in rows
            if row["condition"] == condition and row["repeat"] == repeat
        ]
        grouped[f"{condition}/repeat-{repeat}"] = {
            "planned_union": len(matching),
            "summary": _aggregate(matching),
            "timing": _timing(matching),
        }
    return {
        "schema": "xbrainlab.assistant_experiment_comparison.v1",
        "classification": classification,
        "differences": differences,
        "runs": [
            {key: state[key] for key in ("run", "report", "issues")} for state in states
        ],
        "original_evidence": before,
        "original_evidence_unchanged": True,
        "planned_union": len(rows),
        "summary": _aggregate(rows),
        "by_model_repeat": grouped,
        "timing": _timing(rows),
        "cases": rows,
        "limitations": [
            "Saved scores only; no inference, parsing with current product code, or rescoring.",
            "Agreement is not correctness; respond_to_user.message wording is ignored.",
            "Correctness requires identical saved case/oracle and scorer contract plus identical source SHA or frozen scoring dependency Git trees.",
            "P50/P95 use linear interpolation at (n-1)*p over valid recorded decision terminals; paired deltas are B minus A, not time to successful completion.",
            "Combined summaries are descriptive paired observations, not thesis macro accuracy or formal model ranking.",
        ],
    }


def write_comparison(run_a: Path, run_b: Path, output: Path | None = None) -> dict:
    """Publish into a fresh external directory; never overwrite either run."""
    roots = [Path(path).resolve(strict=True) for path in (run_a, run_b)]
    if output is None:
        output = roots[0].parent / (
            "comparison-"
            + datetime.now(UTC).strftime("%Y%m%d-%H%M%S-")
            + uuid4().hex[:8]
        )
    output = Path(output).resolve()
    if any(output.is_relative_to(root) for root in roots):
        raise ValueError(
            "Comparison output must be outside both original run directories"
        )
    if output.exists():
        raise FileExistsError(output)
    result = compare_runs(*roots)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "comparison.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    text = [
        "# Saved experiment comparison",
        "",
        result["classification"],
        "",
        "## Source and comparability differences",
        "",
        "```json",
        json.dumps(result["differences"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Paired decisions",
        "",
        f"Planned union: {result['planned_union']}. Missing/invalid observations remain unavailable.",
        "",
        "```json",
        json.dumps(result["summary"], indent=2),
        "```",
        "",
        "## Decision timing (seconds)",
        "",
        "```json",
        json.dumps(result["timing"], indent=2),
        "```",
        "",
        "## Per-case evidence",
        "",
        "[Full comparison, actual inputs and raw outputs](comparison.json)",
        "",
    ]
    for row in result["cases"]:
        text.append(
            f"- {row['condition']} / {row['case_id']} / repeat {row['repeat']}: first {row['first']['correctness']}; final {row['final']['correctness']}; {row['correctness_reason']}"
        )
    text.extend(["", *result["limitations"], ""])
    with (output / "comparison.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(text))
    return {**result, "output": str(output)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_a", type=Path)
    parser.add_argument("run_b", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = write_comparison(args.run_a, args.run_b, args.output)
    print(
        json.dumps(
            {"classification": result["classification"], "output": result["output"]}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
