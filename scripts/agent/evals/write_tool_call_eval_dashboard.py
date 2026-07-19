#!/usr/bin/env python3
"""Render a product-readable dashboard from tool-call eval artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CURRENT_LOCAL_EVAL_SCHEMA_VERSION = "xbrainlab.local_tool_call_eval.v5"
THESIS_MIN_RAW_PASS_RATE = 0.90
THESIS_MIN_CASES = 100
THESIS_MIN_REPEATS = 3


def load_eval_results(eval_dir: Path) -> list[dict[str, Any]]:
    """Load deterministic and local eval JSON artifacts from an eval directory."""
    deterministic_results: list[dict[str, Any]] = []
    legacy_local_results: list[dict[str, Any]] = []
    current_results: list[dict[str, Any]] = []
    deterministic = eval_dir / "latest.json"
    if deterministic.exists():
        deterministic_results.append(_load_json(deterministic))

    latest_paths = set(eval_dir.glob("local_*/local_latest.json"))
    latest_paths.update(
        path
        for path in (
            eval_dir / "local_latest.json",
            eval_dir / "current_candidate_strict" / "local_latest.json",
        )
        if path.exists()
    )
    for latest in sorted(latest_paths):
        latest_payload = _load_json(latest)
        latest_result = latest_payload.get("latest_result")
        if not isinstance(latest_result, str):
            continue
        result_path = latest.parent / latest_result
        if result_path.exists():
            result = _load_json(result_path)
            if _is_current_unassisted_result(result):
                current_results.append(result)
            elif _is_dashboard_candidate(result):
                legacy_local_results.append(result)
    return deterministic_results + (current_results or legacy_local_results)


def load_robustness_results(eval_dir: Path) -> list[dict[str, Any]]:
    """Load current robustness slices without mixing their case denominators."""
    latest = (
        eval_dir / "current_candidate_strict" / "anti_overfit" / "local_latest.json"
    )
    if not latest.exists():
        return []
    latest_payload = _load_json(latest)
    latest_result = latest_payload.get("latest_result")
    if not isinstance(latest_result, str):
        return []
    result_path = latest.parent / latest_result
    if not result_path.exists():
        return []
    result = _load_json(result_path)
    return [result] if _is_current_unassisted_result(result) else []


def render_dashboard(results: list[dict[str, Any]], eval_dir: Path) -> str:
    """Render a concise Markdown dashboard for human review."""
    lines = [
        "# XBrainLab Tool-Call Eval Dashboard",
        "",
        f"- eval directory: `{eval_dir}`",
        f"- result count: `{len(results)}`",
        "",
        "## Model Comparison",
        "",
        "| Runner / Model | Cases | Repeats | Raw Model Pass Rate | "
        "Host-Assisted Pass Rate | Stability | Exploratory |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        summary = result.get("summary", {})
        raw_summary = result.get("raw_model_summary") or summary
        host_summary = result.get("host_assisted_summary")
        runner = result.get("runner", "unknown")
        model = result.get("model_id") or "deterministic"
        repeats = result.get("repeat_count", "-")
        stability = raw_summary.get("local_llm_reliability_accuracy", 1.0)
        exploratory = result.get("exploratory", False)
        host_pass_rate = (
            _percent(host_summary.get("pass_rate", 0.0))
            if isinstance(host_summary, dict)
            else "-"
        )
        lines.append(
            f"| {runner} / {model} | {raw_summary.get('total_cases', 0)} | "
            f"{repeats} | {_percent(raw_summary.get('pass_rate', 0.0))} | "
            f"{host_pass_rate} | "
            f"{_percent(stability)} | {exploratory} |"
        )

    robustness_results = load_robustness_results(eval_dir)
    if robustness_results:
        lines.extend(
            [
                "",
                "## Robustness / Anti-Overfit Gate",
                "",
                "| Slice | Model | Cases | Repeats | Raw Model | Host Safety | Raw Gate |",
                "| --- | --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for result in robustness_results:
            raw_summary = result.get("raw_model_summary") or result.get("summary", {})
            host_summary = result.get("host_assisted_summary") or {}
            raw_gate_passed = bool((result.get("cli_gate") or {}).get("passed"))
            lines.append(
                f"| Anti-overfit paraphrases | {_result_label(result)} | "
                f"{raw_summary.get('total_cases', 0)} | "
                f"{result.get('repeat_count', '-')} | "
                f"{_percent(raw_summary.get('pass_rate'))} | "
                f"{_percent(host_summary.get('pass_rate'))} | "
                f"{'PASS' if raw_gate_passed else 'FAIL'} |"
            )
        if any(
            not bool((result.get("cli_gate") or {}).get("passed"))
            for result in robustness_results
        ):
            lines.append(
                "\n- Raw gate failed: product safety may still pass, but raw local-model "
                "accuracy is not release- or thesis-ready."
            )

    lines.extend(["", "## Metric Pass Rates", ""])
    metric_keys = _metric_keys(results)
    lines.append(
        "| Metric | " + " | ".join(_result_label(item) for item in results) + " |"
    )
    lines.append("| --- | " + " | ".join("---:" for _ in results) + " |")
    for metric in metric_keys:
        label = metric.removesuffix("_accuracy").replace("_", " ")
        values = [_metric_cell(item, metric) for item in results]
        lines.append(f"| {label} | " + " | ".join(values) + " |")

    lines.extend(
        [
            "",
            "## Metric Definitions",
            "",
            "- Tool selection is measured only on cases that expect a direct tool call.",
            "- Argument correctness is conditional on correct tool selection; wrong-tool and no-tool cases are excluded from its denominator.",
            "- Tool/no-tool decision is measured across all cases.",
            "- Missing-input fields require an exact set of machine-readable field identifiers.",
            "- Raw model and host-assisted scores remain separate; host safety cannot replace raw model accuracy.",
        ]
    )

    lines.extend(["", "## Family Pass Rates", ""])
    families = _families(results)
    lines.append(
        "| Family | " + " | ".join(_result_label(item) for item in results) + " |"
    )
    lines.append("| --- | " + " | ".join("---:" for _ in results) + " |")
    for family in families:
        values = []
        for result in results:
            stats = _raw_summary(result).get("family_pass_rates", {}).get(family)
            values.append(
                f"{_percent(stats.get('pass_rate', 0.0))} ({stats.get('passed', 0)}/{stats.get('total', 0)})"
                if isinstance(stats, dict)
                else "-"
            )
        lines.append(f"| {family} | " + " | ".join(values) + " |")

    lines.extend(["", "## Failure Taxonomy", ""])
    any_failure = False
    for result in results:
        taxonomy = result.get("failure_taxonomy") or result.get("summary", {}).get(
            "failure_taxonomy",
            {},
        )
        label = _result_label(result)
        if taxonomy:
            any_failure = True
            lines.append(
                f"- {label}: "
                + ", ".join(
                    f"{name}={count}" for name, count in sorted(taxonomy.items())
                )
            )
    if not any_failure:
        lines.append("- None.")

    lines.extend(["", "## Worst Cases", ""])
    worst = _worst_cases(results)
    if worst:
        for label, case in worst[:15]:
            lines.append(
                f"- {label} `{case.get('case_id')}`: "
                f"{', '.join(case.get('failures', []))}"
            )
    else:
        lines.append("- None.")

    lines.extend(["", "## Sources And Artifacts", ""])
    for result in results:
        label = _result_label(result)
        source_paths = result.get("fixture_source_paths") or []
        artifact_paths = result.get("artifact_paths") or {}
        for source_path in source_paths:
            lines.append(f"- {label} source: `{source_path}`")
        for artifact_label, artifact_path in artifact_paths.items():
            lines.append(f"- {label} {artifact_label}: `{artifact_path}`")

    lines.extend(["", "## Thesis Claim Boundary", ""])
    claim = _claim_boundary(results)
    lines.extend(f"- {item}" for item in claim)
    return "\n".join(lines) + "\n"


def write_dashboard(eval_dir: Path, output_path: Path | None = None) -> Path:
    """Load eval results and write the dashboard artifact."""
    results = load_eval_results(eval_dir)
    output = output_path or eval_dir / "dashboard.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dashboard(results, eval_dir), encoding="utf-8")
    return output


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload.setdefault("artifact_paths", {})
        payload["artifact_paths"].setdefault("json", str(path))
        return payload
    raise ValueError(f"Expected JSON object in {path}")


def _is_dashboard_candidate(result: dict[str, Any]) -> bool:
    """Return whether a local result belongs in the main thesis dashboard."""
    if result.get("runner") != "local-llm":
        return True
    if result.get("schema_version") != CURRENT_LOCAL_EVAL_SCHEMA_VERSION:
        return False
    if result.get("exploratory"):
        return False
    repeat_count = result.get("repeat_count", 0)
    total_cases = result.get("total_cases") or result.get("summary", {}).get(
        "total_cases",
        0,
    )
    return int(repeat_count) >= 3 and int(total_cases) >= 100


def _is_current_unassisted_result(result: dict[str, Any]) -> bool:
    if result.get("schema_version") != CURRENT_LOCAL_EVAL_SCHEMA_VERSION:
        return False
    prompt_condition = result.get("prompt_condition")
    if not isinstance(prompt_condition, dict):
        return False
    return bool(
        prompt_condition.get("name") == "state_capability_unassisted"
        and prompt_condition.get("primary_raw_accuracy") is True
    )


def _metric_keys(results: list[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for result in results:
        keys.update(key for key in _raw_summary(result) if key.endswith("_accuracy"))
    return sorted(keys)


def _families(results: list[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for result in results:
        keys.update(_raw_summary(result).get("family_pass_rates", {}).keys())
    return sorted(keys)


def _worst_cases(results: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []
    for result in results:
        label = _result_label(result)
        for case in result.get("cases", []):
            score = case.get("score") if isinstance(case, dict) else None
            candidate = score if isinstance(score, dict) else case
            if not isinstance(candidate, dict) or candidate.get("passed", True):
                continue
            visible_case = dict(candidate)
            visible_case.setdefault("case_id", case.get("case_id", "unknown"))
            cases.append((label, visible_case))
    return cases


def _claim_boundary(results: list[dict[str, Any]]) -> list[str]:
    local_results = [item for item in results if item.get("runner") == "local-llm"]
    if not local_results:
        return [
            "Deterministic eval alone is not thesis-ready evidence.",
            "Run local primary and fallback models at least three times each.",
        ]
    deterministic_total = _deterministic_case_count(results)
    local_totals = {
        int(item.get("total_cases") or item.get("summary", {}).get("total_cases", 0))
        for item in local_results
    }
    if deterministic_total and (
        any(total != deterministic_total for total in local_totals)
    ):
        return [
            "Local model results do not cover the latest deterministic case suite; rerun primary and fallback local models before claiming thesis evidence for new cases.",
            "Deterministic-only new cases cannot be claimed as local LLM tool-call evidence.",
        ]
    distinct_models = {
        str(item.get("model_id") or "").strip() for item in local_results
    } - {""}
    if len(distinct_models) < 2:
        return [
            "A thesis-candidate claim requires accepted primary and fallback model artifacts from two distinct local models.",
            "One model run cannot establish fallback robustness or cross-model repeatability.",
        ]

    protocol_failures = _thesis_protocol_failures(local_results)
    if protocol_failures:
        return protocol_failures

    min_pass = min(_raw_summary(item).get("pass_rate", 0.0) for item in local_results)
    if min_pass >= THESIS_MIN_RAW_PASS_RATE:
        return [
            "Local tool-call eval currently supports a thesis-candidate tool-call claim for this benchmark slice.",
            "This does not claim EEG training accuracy, full UI usability, Windows launcher coverage, or product completion.",
        ]
    return [
        "Local tool-call eval is not thesis-ready yet.",
        "Improve prompt, schema, parser, verifier, state snapshot, or model choice before claiming thesis evidence.",
    ]


def _thesis_protocol_failures(
    local_results: list[dict[str, Any]],
) -> list[str]:
    """Return evidence defects that invalidate a thesis-candidate claim."""
    if any(
        item.get("schema_version") != CURRENT_LOCAL_EVAL_SCHEMA_VERSION
        for item in local_results
    ):
        return [
            "Local artifacts use an obsolete scorer schema; rerun both models with the current evaluator before making a thesis claim."
        ]
    if any(item.get("exploratory") for item in local_results):
        return ["Exploratory local runs are engineering evidence, not thesis evidence."]
    if any(
        int(item.get("repeat_count", 0)) < THESIS_MIN_REPEATS
        or int(item.get("total_cases") or _raw_summary(item).get("total_cases", 0))
        < THESIS_MIN_CASES
        for item in local_results
    ):
        return [
            "Each local model requires at least 100 cases and three repeats for thesis-candidate evidence."
        ]
    if any(
        not bool(
            (item.get("evidence_status") or {}).get(
                "thesis_candidate_protocol_complete"
            )
        )
        for item in local_results
    ):
        return [
            "The benchmark protocol or negative/blocked/recovery case mix is incomplete."
        ]
    if any(
        not bool((item.get("benchmark_coverage") or {}).get("protocol_mix_complete"))
        for item in local_results
    ):
        return [
            "The benchmark does not meet the required negative, blocked, recovery, missing-input, and no-tool coverage mix."
        ]
    if any(
        (item.get("measurement_contract") or {}).get("raw_model_score_scope")
        != "raw_model_decision"
        or (item.get("measurement_contract") or {}).get("host_assisted_score_scope")
        != "host_assisted_decision"
        or _raw_summary(item).get("score_scope") != "raw_model_decision"
        or (item.get("host_assisted_summary") or {}).get("score_scope")
        != "host_assisted_decision"
        for item in local_results
    ):
        return [
            "Raw and host-assisted score scopes are missing or conflated in one or more artifacts."
        ]
    provenance = [item.get("provenance") or {} for item in local_results]
    if any(bool((item.get("git") or {}).get("dirty")) for item in provenance):
        return [
            "Thesis-candidate artifacts must be generated from a clean checkpoint; at least one worktree was dirty."
        ]
    commits = {str((item.get("git") or {}).get("commit") or "") for item in provenance}
    if len(commits) != 1 or "" in commits:
        return [
            "Primary and fallback artifacts must use the same clean source checkpoint."
        ]
    for key, label in (
        ("case_fingerprint", "case suite"),
        ("prompt_fingerprint", "prompt"),
        ("tool_contract_fingerprint", "tool contract"),
    ):
        values = {str(item.get(key) or "") for item in provenance}
        if len(values) != 1 or "" in values:
            return [
                f"Primary and fallback artifacts do not share one reproducible {label} fingerprint."
            ]
    if any(not str(item.get("model_revision") or "") for item in provenance):
        return ["Every local artifact must record an exact model revision."]
    return []


def _deterministic_case_count(results: list[dict[str, Any]]) -> int:
    for result in results:
        if result.get("runner") in {"deterministic-scripted-baseline", "deterministic"}:
            return int(
                result.get("total_cases")
                or result.get("summary", {}).get("total_cases", 0)
            )
    return 0


def _result_label(result: dict[str, Any]) -> str:
    model = result.get("model_id") or "deterministic"
    return str(model).split("/")[-1]


def _percent(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "0.00%"


def _raw_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("raw_model_summary") or result.get("summary") or {}
    return summary if isinstance(summary, dict) else {}


def _metric_cell(result: dict[str, Any], metric: str) -> str:
    summary = _raw_summary(result)
    value = summary.get(metric)
    dimension = metric.removesuffix("_accuracy")
    detail = (summary.get("dimension_metrics") or {}).get(dimension)
    if not isinstance(detail, dict):
        return _percent(value)
    applicable = int(detail.get("applicable_cases") or 0)
    if value is None or applicable == 0:
        return "N/A (0/0)"
    passed = round(float(value) * applicable)
    return f"{_percent(value)} ({passed}/{applicable})"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-dir", default="artifacts/agent_evals")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    output = write_dashboard(
        Path(args.eval_dir),
        Path(args.output) if args.output else None,
    )
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
