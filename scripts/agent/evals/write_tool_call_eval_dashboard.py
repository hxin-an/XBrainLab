#!/usr/bin/env python3
"""Render a product-readable dashboard from tool-call eval artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_eval_results(eval_dir: Path) -> list[dict[str, Any]]:
    """Load deterministic and local eval JSON artifacts from an eval directory."""
    results: list[dict[str, Any]] = []
    deterministic = eval_dir / "latest.json"
    if deterministic.exists():
        results.append(_load_json(deterministic))

    for latest in sorted(eval_dir.glob("local_*/local_latest.json")):
        latest_payload = _load_json(latest)
        latest_result = latest_payload.get("latest_result")
        if not isinstance(latest_result, str):
            continue
        result_path = latest.parent / latest_result
        if result_path.exists():
            result = _load_json(result_path)
            if _is_dashboard_candidate(result):
                results.append(result)
    return results


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
        "| Runner / Model | Cases | Repeats | Pass Rate | Stability | Exploratory |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        summary = result.get("summary", {})
        runner = result.get("runner", "unknown")
        model = result.get("model_id") or "deterministic"
        repeats = result.get("repeat_count", "-")
        stability = summary.get("local_llm_reliability_accuracy", 1.0)
        exploratory = result.get("exploratory", False)
        lines.append(
            f"| {runner} / {model} | {summary.get('total_cases', 0)} | "
            f"{repeats} | {_percent(summary.get('pass_rate', 0.0))} | "
            f"{_percent(stability)} | {exploratory} |"
        )

    lines.extend(["", "## Metric Pass Rates", ""])
    metric_keys = _metric_keys(results)
    lines.append(
        "| Metric | " + " | ".join(_result_label(item) for item in results) + " |"
    )
    lines.append("| --- | " + " | ".join("---:" for _ in results) + " |")
    for metric in metric_keys:
        label = metric.removesuffix("_accuracy").replace("_", " ")
        values = [
            _percent(item.get("summary", {}).get(metric, 0.0)) for item in results
        ]
        lines.append(f"| {label} | " + " | ".join(values) + " |")

    lines.extend(["", "## Family Pass Rates", ""])
    families = _families(results)
    lines.append(
        "| Family | " + " | ".join(_result_label(item) for item in results) + " |"
    )
    lines.append("| --- | " + " | ".join("---:" for _ in results) + " |")
    for family in families:
        values = []
        for result in results:
            stats = result.get("summary", {}).get("family_pass_rates", {}).get(family)
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
    if result.get("exploratory"):
        return False
    repeat_count = result.get("repeat_count", 0)
    total_cases = result.get("total_cases") or result.get("summary", {}).get(
        "total_cases",
        0,
    )
    return int(repeat_count) >= 3 and int(total_cases) >= 100


def _metric_keys(results: list[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for result in results:
        keys.update(
            key for key in result.get("summary", {}) if key.endswith("_accuracy")
        )
    return sorted(keys)


def _families(results: list[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for result in results:
        keys.update(result.get("summary", {}).get("family_pass_rates", {}).keys())
    return sorted(keys)


def _worst_cases(results: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []
    for result in results:
        label = _result_label(result)
        for case in result.get("cases", []):
            if not case.get("passed", True):
                cases.append((label, case))
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
    all_non_exploratory = all(not item.get("exploratory") for item in local_results)
    min_pass = min(
        item.get("summary", {}).get("pass_rate", 0.0) for item in local_results
    )
    if all_non_exploratory and min_pass >= 0.9:
        return [
            "Local tool-call eval currently supports a thesis-candidate tool-call claim for this benchmark slice.",
            "This does not claim EEG training accuracy, full UI usability, Windows launcher coverage, or product completion.",
        ]
    return [
        "Local tool-call eval is not thesis-ready yet.",
        "Improve prompt, schema, parser, verifier, state snapshot, or model choice before claiming thesis evidence.",
    ]


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
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "0.00%"


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
