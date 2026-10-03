"""Aggregate explicit batch/reference selections using the saved-run comparator.

No model invocation, rescoring, implicit latest-run selection or result replacement.
Reference selectors admit complete conditions only (the authorized repaired candidate).
"""

from __future__ import annotations

import hashlib
import html
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from scripts.dev.assistant_experiment_audit import evidence_digest
from scripts.dev.assistant_experiment_compare import (
    _aggregate,
    _load,
    _timing,
    compare_states,
)


def _descriptor(root: Path) -> dict:
    path = root / "manifest.json"
    content = path.read_bytes()
    value = json.loads(content)
    schema = value.get("schema")
    if schema not in {
        "xbrainlab.assistant_experiment_batch.v1",
        "xbrainlab.assistant_experiment_reference.v1",
    }:
        raise ValueError("Unknown batch/reference schema")
    reference = schema.endswith("reference.v1")
    base = (root / value.get("root", ".")).resolve() if reference else root
    runs = value.get("runs")
    if not isinstance(runs, list) or len(runs) > 32:
        raise ValueError("Invalid or unbounded batch inventory")
    slots = defaultdict(list)
    for slot in runs:
        if not isinstance(slot, dict) or not isinstance(slot.get("scope"), str):
            raise ValueError("Invalid scope")
        if type(slot.get("expected_cases")) is not int or slot["expected_cases"] < 1:
            raise ValueError("Each comparison scope requires expected_cases")
        selections = slot.get("selections") if reference else [{"run": slot["run"]}]
        if not isinstance(selections, list) or not 1 <= len(selections) <= 6:
            raise ValueError("Invalid reference selections")
        selected = []
        for selection in selections:
            relative = Path(selection["run"])
            path = (base / relative).resolve()
            if relative.is_absolute() or not path.is_relative_to(base):
                raise ValueError("Selected evidence is outside its declared root")
            conditions = selection.get("conditions")
            if conditions is not None and (
                not isinstance(conditions, list)
                or not conditions
                or any(not isinstance(item, str) or not item for item in conditions)
                or len(set(conditions)) != len(conditions)
            ):
                raise ValueError("Invalid complete-condition selection")
            selected.append({"run": path, "conditions": conditions})
        issues = []
        if not reference and (
            slot.get("status") != "completed" or slot.get("exit_code") != 0
        ):
            issues.append("batch_child_not_completed")
        slots[slot["scope"]].append({**slot, "selections": selected, "issues": issues})
    return {"root": root, "slots": slots, "sha256": hashlib.sha256(content).hexdigest()}


def _selected(slot: dict | None, root: Path, cache: dict) -> dict:
    state = {"run": str(root), "report": None, "manifest": {}, "rows": [], "issues": []}
    if slot is None:
        state["issues"].append("missing_or_duplicate_scope")
        return state
    state["issues"].extend(slot["issues"])
    manifests = []
    for selection in slot["selections"]:
        path = selection["run"]
        if path not in cache:
            cache[path] = {"digest": evidence_digest(path), "state": _load(path)}
        loaded = cache[path]["state"]
        state["issues"].extend(loaded["issues"])
        conditions = selection["conditions"]
        selected = [
            entry
            for entry in loaded["rows"]
            if conditions is None or entry["job"]["condition"] in conditions
        ]
        if conditions and set(conditions) != {
            entry["job"]["condition"] for entry in selected
        }:
            state["issues"].append("missing_selected_condition")
        state["rows"].extend(selected)
        manifests.append(loaded["manifest"])
    if len(state["rows"]) != slot["expected_cases"]:
        state["issues"].append("selected_denominator_mismatch")
    # Retain every selected source identity. A mixed-source reference must never
    # be represented as the first run's source or today's engine.
    for field in {name for manifest in manifests for name in manifest} - {"jobs"}:
        values = [manifest.get(field) for manifest in manifests]
        state["manifest"][field] = (
            values[0] if all(value == values[0] for value in values) else values
        )
    return state


def compare_batches(run_a: Path, run_b: Path) -> dict:
    """Compare complete selected slots; missing/duplicate evidence stays visible."""
    roots = [Path(path).resolve(strict=True) for path in (run_a, run_b)]
    descriptors = [_descriptor(root) for root in roots]
    cache, comparisons, rows = {}, {}, []
    for scope in sorted(set(descriptors[0]["slots"]) | set(descriptors[1]["slots"])):
        slots = [descriptor["slots"].get(scope, []) for descriptor in descriptors]
        states = [
            _selected(items[0] if len(items) == 1 else None, root, cache)
            for items, root in zip(slots, roots, strict=True)
        ]
        result = compare_states(states, strict_identity=True)
        if (
            len(slots[0]) == len(slots[1]) == 1
            and slots[0][0]["expected_cases"] != slots[1][0]["expected_cases"]
        ):
            result["classification"] = "incompatible_or_unknown"
            result["differences"].append(
                {"field": "expected_cases", "status": "different"}
            )
        for row in result["cases"]:
            row["scope"] = scope
        rows.extend(result.pop("cases"))
        comparisons[scope] = result
    for path, loaded in cache.items():
        if evidence_digest(path) != loaded["digest"]:
            raise ValueError("Original run evidence changed during batch comparison")
    if any(
        hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
        != descriptor["sha256"]
        for root, descriptor in zip(roots, descriptors, strict=True)
    ):
        raise ValueError("Batch descriptor changed during comparison")
    classes = {result["classification"] for result in comparisons.values()}
    classification = (
        "incompatible_or_unknown"
        if not rows or "incompatible_or_unknown" in classes
        else "candidate_comparison"
        if "candidate_comparison" in classes
        else "same_config_reproduction"
    )
    return {
        "schema": "xbrainlab.assistant_experiment_batch_comparison.v1",
        "classification": classification,
        "batches": [
            {"root": str(root), "manifest_sha256": descriptor["sha256"]}
            for root, descriptor in zip(roots, descriptors, strict=True)
        ],
        "original_evidence": {
            str(path): loaded["digest"] for path, loaded in cache.items()
        },
        "original_evidence_unchanged": True,
        "planned_union": len(rows),
        "summary": _aggregate(rows),
        "timing": _timing(rows),
        "inputs": {
            key: {
                "equal": sum(row[key] is True for row in rows),
                "different": sum(row[key] is False for row in rows),
                "unavailable": sum(row[key] is None for row in rows),
            }
            for key in ("first_input_equal", "all_inputs_equal")
        },
        "scopes": comparisons,
        "cases": rows,
        "limitations": [
            "Saved evidence only: no inference, parsing or rescoring.",
            "Alignment is scope, split, candidate, condition/model/ablation, case and repeat.",
            "Source/scorer differences remain explicit; matching decisions are not proof of exact reproduction.",
            "Complete-condition reference selection is explicit; no per-case score-based replacement.",
            "First input equality is distinct from all-attempt equality: divergent outputs may cause different retries.",
            "Combined counts are descriptive, not thesis macro accuracy or model ranking.",
        ],
    }


def _render(result: dict, output: Path) -> str:
    escape = html.escape
    parts = [
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Batch comparison</title>",
        "<style>body{font:16px system-ui;margin:2rem}table{border-collapse:collapse}td,th{padding:.5rem;border:1px solid #bbb}code{overflow-wrap:anywhere}</style>",
        "<h1>Saved experiment comparison</h1>",
        f"<p>Classification: <strong>{escape(result['classification'])}</strong>. Paired union: {result['planned_union']}.</p>",
        "<p>A = reference; B = rerun. Agreement is not correctness. No inference or rescoring.</p>",
        "<p><a href='comparison.json'>Complete JSON, input/output evidence and per-case differences</a></p>",
        "<h2>Inputs</h2><pre>"
        + escape(json.dumps(result["inputs"], indent=2))
        + "</pre>",
        "<h2>Per-scope evidence</h2><table><tr><th>Scope</th><th>Cases</th><th>Classification</th><th>Tool + parameters equal</th><th>A wrong → B right</th><th>A right → B wrong</th><th>Correctness unavailable</th></tr>",
    ]
    for scope, value in result["scopes"].items():
        final = value["summary"]["final"]
        agree, scores = final["tool_parameters_equal"], final["correctness"]
        parts.append(
            f"<tr><td>{escape(scope)}</td><td>{value['planned_union']}</td><td>{escape(value['classification'])}</td><td>{agree['numerator']}/{agree['denominator']}; unavailable {agree['unavailable']}</td><td>{scores['improved']}</td><td>{scores['regressed']}</td><td>{scores['unavailable']}</td></tr>"
        )
    parts.extend(
        [
            "</table><h2>Decision timing (seconds)</h2><pre>",
            escape(json.dumps(result["timing"], indent=2)),
            "</pre><h2>Original evidence</h2><ul>",
        ]
    )
    for path in result["original_evidence"]:
        root = Path(path)
        target = root / "index.html" if (root / "index.html").is_file() else root
        link = quote(Path(os.path.relpath(target, output)).as_posix(), safe="/")
        parts.append(
            f"<li><a href='{escape(link, quote=True)}'>{escape(str(root))}</a></li>"
        )
    parts.append("</ul><h2>Limits</h2><ul>")
    parts.extend(f"<li>{escape(item)}</li>" for item in result["limitations"])
    parts.append("</ul></html>")
    return "\n".join(parts)


def write_batch_comparison(
    run_a: Path, run_b: Path, output: Path | None = None
) -> dict:
    roots = [Path(path).resolve(strict=True) for path in (run_a, run_b)]
    output = (
        Path(output).resolve()
        if output is not None
        else roots[1].parent
        / (
            "comparison-"
            + datetime.now(UTC).strftime("%Y%m%d-%H%M%S-")
            + uuid4().hex[:8]
        )
    )
    descriptors = [_descriptor(root) for root in roots]
    evidence = [
        selection["run"]
        for descriptor in descriptors
        for slots in descriptor["slots"].values()
        for slot in slots
        for selection in slot["selections"]
    ]
    if any(output.is_relative_to(root) for root in [*roots, *evidence]):
        raise ValueError(
            "Comparison output must be outside original batches and selected evidence"
        )
    if output.exists():
        raise FileExistsError(output)
    result = compare_batches(*roots)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "comparison.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    with (output / "index.html").open("x", encoding="utf-8") as stream:
        stream.write(_render(result, output))
    return {**result, "output": str(output)}
