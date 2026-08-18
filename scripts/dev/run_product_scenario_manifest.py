#!/usr/bin/env python3
"""Run a bounded selection from the high-difference product scenario manifest."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)
from scripts.dev.handoff_gate_spec import HANDOFF_GATE_SPECS
from scripts.dev.owned_process_group import spawn_owned_process, terminate_and_collect
from scripts.dev.product_scenario_manifest import (
    IMMEDIATE_PROFILE_ID,
    PRODUCT_SCENARIO_EXECUTIONS,
    PRODUCT_SCENARIO_PROFILES,
    PRODUCT_SCENARIOS,
    ExecutionSpec,
    ScenarioManifestError,
    ScenarioSpec,
    validate_manifest,
)
from scripts.dev.pytest_completion_attestation import validate_attestation

ROOT = Path(__file__).resolve().parents[2]
REPORT_NAME = "product-scenario-report.json"
SCHEMA_VERSION = 1
_SANITIZED_INHERITED_ENVIRONMENT = (
    "COVERAGE_PROCESS_START",
    "PYTEST_ADDOPTS",
    "PYTEST_PLUGINS",
    "PYTHONBREAKPOINT",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONSTARTUP",
)


class ScenarioRunError(RuntimeError):
    """Raised when a scenario run cannot produce trustworthy bounded evidence."""


@dataclass(frozen=True, slots=True)
class ScenarioPlan:
    profile_id: str
    profile_expected_count: int
    profile_complete: bool
    scenarios: tuple[ScenarioSpec, ...]
    execution_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    execution_id: str
    command: tuple[str, ...]
    timeout_seconds: float
    return_code: int | None
    timed_out: bool
    duration_seconds: float
    stdout_path: str
    stderr_path: str
    failure_reason: str

    @classmethod
    def passed_for_test(cls, execution_id: str) -> CommandOutcome:
        return cls(
            execution_id=execution_id,
            command=("test-command",),
            timeout_seconds=1,
            return_code=0,
            timed_out=False,
            duration_seconds=0,
            stdout_path="logs/test.stdout.log",
            stderr_path="logs/test.stderr.log",
            failure_reason="",
        )


def _matches_selector(scenario: ScenarioSpec, selector: str) -> bool:
    normalized = selector.strip().casefold()
    if not normalized:
        return False
    values = (
        scenario.scenario_id.casefold(),
        scenario.title.casefold(),
        *(tag.casefold() for tag in scenario.coverage_tags),
    )
    return any(
        normalized in value or fnmatch.fnmatchcase(value, normalized)
        for value in values
    )


def build_plan(
    *,
    profile_id: str,
    scenario_selectors: Sequence[str] = (),
    tag_selectors: Sequence[str] = (),
) -> ScenarioPlan:
    """Resolve a profile and optional selectors without changing its denominator."""
    validate_manifest()
    profile = PRODUCT_SCENARIO_PROFILES.get(profile_id)
    if profile is None:
        raise ScenarioRunError(f"Unknown product scenario profile: {profile_id!r}.")
    profile_scenarios = tuple(PRODUCT_SCENARIOS[item] for item in profile.scenario_ids)
    selected = profile_scenarios
    normalized_scenario_selectors = tuple(
        item for item in scenario_selectors if item.strip()
    )
    normalized_tags = {
        item.strip().casefold() for item in tag_selectors if item.strip()
    }
    if normalized_scenario_selectors:
        selected = tuple(
            scenario
            for scenario in selected
            if any(
                _matches_selector(scenario, selector)
                for selector in normalized_scenario_selectors
            )
        )
    if normalized_tags:
        selected = tuple(
            scenario
            for scenario in selected
            if normalized_tags.intersection(
                tag.casefold() for tag in scenario.coverage_tags
            )
        )
    if not selected:
        raise ScenarioRunError("Product scenario selectors matched no scenarios.")
    execution_order: list[str] = []

    def add_execution(execution_id: str) -> None:
        execution = PRODUCT_SCENARIO_EXECUTIONS[execution_id]
        for dependency_id in execution.depends_on_execution_ids:
            add_execution(dependency_id)
        if execution_id not in execution_order:
            execution_order.append(execution_id)

    for scenario in selected:
        add_execution(scenario.execution_id)
    return ScenarioPlan(
        profile_id=profile.profile_id,
        profile_expected_count=profile.expected_scenario_count,
        profile_complete=tuple(item.scenario_id for item in selected)
        == profile.scenario_ids,
        scenarios=selected,
        execution_ids=tuple(execution_order),
    )


def require_source_stability(
    *,
    start: Mapping[str, Any],
    end: Mapping[str, Any],
) -> None:
    """Reject a run when commit or source-content identity changes in flight."""
    fields = ("commit_sha", "source_digest")
    if any(
        not start.get(field) or start.get(field) != end.get(field) for field in fields
    ):
        raise ScenarioRunError("Product scenario source changed during the run.")


def _safe_path(root: Path, relative_path: str) -> Path:
    resolved_root = root.resolve()
    candidate = resolved_root / relative_path
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as error:
        raise ScenarioRunError(
            f"Evidence artifact escapes its root: {relative_path!r}."
        ) from error
    cursor = candidate
    while cursor != resolved_root:
        if cursor.is_symlink():
            raise ScenarioRunError(
                f"Evidence artifact path contains a symlink: {relative_path!r}."
            )
        cursor = cursor.parent
    return candidate


def _clear_registered_artifacts(
    evidence_root: Path,
    execution: ExecutionSpec,
) -> None:
    for relative_path in execution.artifacts():
        path = _safe_path(evidence_root, relative_path)
        if path.is_symlink():
            raise ScenarioRunError(
                f"Refusing symlinked evidence artifact: {relative_path!r}."
            )
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _execution_environment(execution: ExecutionSpec) -> dict[str, str]:
    environment = os.environ.copy()
    for name in _SANITIZED_INHERITED_ENVIRONMENT:
        environment.pop(name, None)
    environment.update(execution.resolved_environment())
    return environment


def execute_bounded(
    *,
    repo_root: Path,
    evidence_root: Path,
    execution: ExecutionSpec,
) -> CommandOutcome:
    """Run one command in an owned process group and preserve bounded logs."""
    _clear_registered_artifacts(evidence_root, execution)
    command = execution.resolve_command(str(evidence_root))
    logs_dir = evidence_root / "logs"
    stdout_path = logs_dir / f"{execution.execution_id}.stdout.log"
    stderr_path = logs_dir / f"{execution.execution_id}.stderr.log"
    started = time.monotonic()
    timed_out = False
    return_code: int | None = None
    stdout = ""
    stderr = ""
    failure_reason = ""
    try:
        process, owner = spawn_owned_process(
            command,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            env=_execution_environment(execution),
        )
        try:
            stdout, stderr = process.communicate(timeout=execution.timeout_seconds)
            return_code = int(process.returncode)
        except subprocess.TimeoutExpired:
            timed_out = True
            stdout, stderr = terminate_and_collect(process, owner)
            return_code = 124
            failure_reason = (
                f"Command timed out after {execution.timeout_seconds:g} seconds."
            )
        finally:
            owner.close()
    except OSError as error:
        failure_reason = f"Could not execute command: {error}"
    _write_text(stdout_path, stdout)
    _write_text(stderr_path, stderr)
    stdout_artifact = execution.stdout_artifact()
    if stdout_artifact is not None:
        _write_text(_safe_path(evidence_root, stdout_artifact), stdout)
    if not failure_reason and return_code != 0:
        failure_reason = f"Command exited with return code {return_code}."
    return CommandOutcome(
        execution_id=execution.execution_id,
        command=command,
        timeout_seconds=execution.timeout_seconds,
        return_code=return_code,
        timed_out=timed_out,
        duration_seconds=round(time.monotonic() - started, 3),
        stdout_path=str(stdout_path.relative_to(evidence_root)),
        stderr_path=str(stderr_path.relative_to(evidence_root)),
        failure_reason=failure_reason,
    )


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"Required artifact is missing: {path.name}."
    except (OSError, json.JSONDecodeError):
        return None, f"Required JSON artifact is unreadable: {path.name}."
    if not isinstance(value, dict):
        return None, f"Required JSON artifact is not an object: {path.name}."
    return value, ""


def _json_value(payload: Mapping[str, Any], path: Sequence[str]) -> Any:
    value: Any = payload
    for part in path:
        if not isinstance(value, Mapping) or part not in value:
            raise KeyError(".".join(path))
        value = value[part]
    return value


def _required_paths_failure(
    required_paths: Sequence[str],
    evidence_root: Path,
) -> str:
    for relative_path in required_paths:
        try:
            path = _safe_path(evidence_root, relative_path)
        except ScenarioRunError as error:
            return str(error)
        if path.is_symlink() or not path.exists():
            return f"Required artifact is missing or unsafe: {relative_path}."
        if path.is_file() and path.stat().st_size <= 0:
            return f"Required artifact is empty: {relative_path}."
        if path.is_dir() and not any(path.iterdir()):
            return f"Required artifact directory is empty: {relative_path}."
    return ""


def _artifact_failure(scenario: ScenarioSpec, evidence_root: Path) -> str:
    execution = PRODUCT_SCENARIO_EXECUTIONS[scenario.execution_id]
    failure = _required_paths_failure(execution.artifacts(), evidence_root)
    if failure:
        return failure
    return _required_paths_failure(
        scenario.artifact_policy.required_paths,
        evidence_root,
    )


def _validate_pytest_attestation(
    scenario: ScenarioSpec,
    evidence_root: Path,
) -> str:
    execution = PRODUCT_SCENARIO_EXECUTIONS[scenario.execution_id]
    if execution.gate_id is None or scenario.validator.artifact_path is None:
        return "Pytest scenario is not bound to a canonical attesting gate."
    gate = HANDOFF_GATE_SPECS[execution.gate_id]
    contract = gate.pytest_attestation_contract()
    if contract is None:
        return "Canonical pytest gate has no attestation contract."
    runner_id, logical_args = contract
    payload, failure = validate_attestation(
        _safe_path(evidence_root, scenario.validator.artifact_path),
        expected_runner=runner_id,
        expected_args=logical_args,
        expected_exit_code=0,
    )
    if failure is not None or payload is None:
        return failure or "Pytest completion attestation is missing."
    counts = payload["counts"]
    if counts["passed"] <= 0:
        return "Pytest completion attestation reports no passing tests."
    forbidden = gate.outcome.forbidden_pytest_outcomes
    nonzero = [name for name in forbidden if counts.get(name, 0)]
    if nonzero:
        return f"Pytest completion attestation has forbidden outcomes: {nonzero}."
    return ""


def _validate_dpi_scale(payload: Mapping[str, Any], scale: float) -> str:
    if payload.get("status") != "passed" or not isinstance(
        payload.get("records"), list
    ):
        return "DPI gate summary did not pass."
    matching = [
        item
        for item in payload["records"]
        if isinstance(item, Mapping) and item.get("scale") == scale
    ]
    if len(matching) != 1:
        return f"DPI gate requires exactly one scale record for {scale:g}."
    record = matching[0]
    if record.get("status") != "passed":
        return f"DPI scale record {scale:g} did not pass."
    for field in ("full_window_dock", "narrow_crops", "dpi_content"):
        if not isinstance(record.get(field), list) or not record[field]:
            return f"DPI scale record {scale:g} lacks {field} evidence."
    return ""


def _validator_failure(scenario: ScenarioSpec, evidence_root: Path) -> str:
    validator = scenario.validator
    if validator.kind == "execution_artifacts":
        return ""
    if validator.kind == "pytest_attestation":
        return _validate_pytest_attestation(scenario, evidence_root)
    if validator.artifact_path is None:
        return "Scenario validator has no artifact path."
    try:
        artifact_path = _safe_path(evidence_root, validator.artifact_path)
    except ScenarioRunError as error:
        return str(error)
    payload, failure = _load_json(artifact_path)
    if failure or payload is None:
        return failure
    if validator.kind == "json_object":
        return ""
    if validator.kind == "dpi_scale":
        return _validate_dpi_scale(payload, float(validator.expected))
    try:
        value = _json_value(payload, validator.json_path)
    except KeyError:
        return f"JSON evidence path is missing: {'.'.join(validator.json_path)}."
    if validator.kind == "json_truthy" and value is not True:
        return f"JSON evidence is not true: {'.'.join(validator.json_path)}."
    if validator.kind == "json_equals" and value != validator.expected:
        return (
            f"JSON evidence mismatch at {'.'.join(validator.json_path)}: "
            f"expected {validator.expected!r}."
        )
    return ""


def evaluate_scenarios(
    *,
    scenarios: Sequence[ScenarioSpec],
    outcomes: Mapping[str, CommandOutcome],
    evidence_root: Path,
) -> list[dict[str, Any]]:
    """Evaluate each scenario against its own unique evidence selection."""
    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        outcome = outcomes.get(scenario.execution_id)
        failure = ""
        if outcome is None:
            failure = "Scenario execution outcome is missing."
        elif outcome.timed_out:
            failure = outcome.failure_reason or "Scenario command timed out."
        elif outcome.return_code != 0:
            failure = outcome.failure_reason or (
                f"Scenario command exited with return code {outcome.return_code}."
            )
        if not failure:
            failure = _artifact_failure(scenario, evidence_root)
        if not failure:
            failure = _validator_failure(scenario, evidence_root)
        results.append(
            {
                "scenario_id": scenario.scenario_id,
                "title": scenario.title,
                "scope": scenario.scope,
                "execution_id": scenario.execution_id,
                "evidence_key": scenario.evidence_key,
                "timeout_seconds": scenario.timeout_seconds,
                "artifact_policy": asdict(scenario.artifact_policy),
                "validator": asdict(scenario.validator),
                "pass_criteria": list(scenario.pass_criteria),
                "claim_boundary": scenario.claim_boundary,
                "coverage_tags": list(scenario.coverage_tags),
                "passed": not failure,
                "failure_reason": failure,
            }
        )
    return results


def _atomic_write_report(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text(path, json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")


def run_product_scenarios(
    *,
    repo_root: Path,
    evidence_root: Path,
    profile_id: str = IMMEDIATE_PROFILE_ID,
    scenario_selectors: Sequence[str] = (),
    tag_selectors: Sequence[str] = (),
) -> dict[str, Any]:
    """Execute selected groups once, then report each scenario independently."""
    plan = build_plan(
        profile_id=profile_id,
        scenario_selectors=scenario_selectors,
        tag_selectors=tag_selectors,
    )
    root = repo_root.expanduser().resolve(strict=True)
    output_root = evidence_root.expanduser()
    if not output_root.is_absolute():
        output_root = root / output_root
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    source_start = collect_source_identity(root, refresh=True)
    outcomes: dict[str, CommandOutcome] = {}
    for execution_id in plan.execution_ids:
        execution = PRODUCT_SCENARIO_EXECUTIONS[execution_id]
        failed_dependencies = [
            dependency_id
            for dependency_id in execution.depends_on_execution_ids
            if outcomes[dependency_id].return_code != 0
        ]
        if failed_dependencies:
            outcomes[execution_id] = CommandOutcome(
                execution_id=execution_id,
                command=execution.resolve_command(str(output_root)),
                timeout_seconds=execution.timeout_seconds,
                return_code=None,
                timed_out=False,
                duration_seconds=0,
                stdout_path="",
                stderr_path="",
                failure_reason=(
                    "Shared setup dependency failed: "
                    + ", ".join(failed_dependencies)
                    + "."
                ),
            )
            continue
        print(
            f"[product-scenarios] {execution_id} ({execution.timeout_seconds:g}s)",
            file=sys.stderr,
            flush=True,
        )
        outcomes[execution_id] = execute_bounded(
            repo_root=root,
            evidence_root=output_root,
            execution=execution,
        )
    source_end = collect_source_identity(root, refresh=True)
    source_stable = True
    source_failure = ""
    try:
        require_source_stability(start=source_start, end=source_end)
    except ScenarioRunError as error:
        source_stable = False
        source_failure = str(error)
    results = evaluate_scenarios(
        scenarios=plan.scenarios,
        outcomes=outcomes,
        evidence_root=output_root,
    )
    if source_failure:
        for result in results:
            result["passed"] = False
            result["failure_reason"] = source_failure
    passed_count = sum(item["passed"] is True for item in results)
    all_selected_passed = passed_count == len(results)
    immediate_profile_passed = (
        plan.profile_id == IMMEDIATE_PROFILE_ID
        and plan.profile_complete
        and len(results) == plan.profile_expected_count == 12
        and all_selected_passed
        and source_stable
    )
    profile = PRODUCT_SCENARIO_PROFILES[profile_id]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "xbrainlab.product_scenario_checkpoint",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "duration_seconds": round((datetime.now(UTC) - started_at).total_seconds(), 3),
        "profile": {
            "profile_id": profile.profile_id,
            "purpose": profile.purpose,
            "expected_scenario_count": profile.expected_scenario_count,
            "denominator_kind": profile.denominator_kind,
            "moabb_dataset_campaign_in_scope": (
                profile.moabb_dataset_campaign_in_scope
            ),
            "complete_selection": plan.profile_complete,
            "selected_scenario_ids": [item.scenario_id for item in plan.scenarios],
        },
        "source": {
            "start": source_start,
            "end": source_end,
            "stable": source_stable,
        },
        "executions": [asdict(outcomes[item]) for item in plan.execution_ids],
        "shared_setup_execution_ids": [
            item
            for item in plan.execution_ids
            if item not in {scenario.execution_id for scenario in plan.scenarios}
        ],
        "scenarios": results,
        "summary": {
            "selected": len(results),
            "passed": passed_count,
            "failed": len(results) - passed_count,
            "selected_status": "passed" if all_selected_passed else "failed",
            "immediate_profile_passed": immediate_profile_passed,
            "shared_execution_count": len(plan.execution_ids),
            "scenario_results_are_statistically_independent": False,
            "shared_results_counted_as_independent_successes": False,
            "unique_execution_evidence_keys_enforced": True,
            "counting_policy": (
                "Shared commands run once; each scenario must validate a unique "
                "execution/evidence key before it can pass."
            ),
        },
        "claim_boundary": profile.claim_boundary,
    }
    _atomic_write_report(output_root / REPORT_NAME, report)
    return report


def _plan_payload(plan: ScenarioPlan) -> dict[str, Any]:
    profile = PRODUCT_SCENARIO_PROFILES[plan.profile_id]
    return {
        "profile_id": plan.profile_id,
        "profile_expected_count": plan.profile_expected_count,
        "denominator_kind": profile.denominator_kind,
        "moabb_dataset_campaign_in_scope": (profile.moabb_dataset_campaign_in_scope),
        "profile_complete": plan.profile_complete,
        "selected_scenario_count": len(plan.scenarios),
        "shared_execution_count": len(plan.execution_ids),
        "execution_ids": list(plan.execution_ids),
        "claim_boundary": profile.claim_boundary,
        "scenarios": [
            {
                "scenario_id": scenario.scenario_id,
                "title": scenario.title,
                "scope": scenario.scope,
                "execution_id": scenario.execution_id,
                "command": list(
                    PRODUCT_SCENARIO_EXECUTIONS[
                        scenario.execution_id
                    ].command_template()
                ),
                "timeout_seconds": scenario.timeout_seconds,
                "artifact_policy": asdict(scenario.artifact_policy),
                "validator": asdict(scenario.validator),
                "evidence_key": scenario.evidence_key,
                "pass_criteria": list(scenario.pass_criteria),
                "claim_boundary": scenario.claim_boundary,
                "coverage_tags": list(scenario.coverage_tags),
            }
            for scenario in plan.scenarios
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default=IMMEDIATE_PROFILE_ID,
        choices=tuple(PRODUCT_SCENARIO_PROFILES),
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Select scenario id/title/tag by substring or glob; repeatable.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Further restrict selection to scenarios with any named tag.",
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=ROOT / "build" / "dev-artifacts" / "product-scenarios",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="List selected scenarios.")
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved plan without executing commands.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        plan = build_plan(
            profile_id=args.profile,
            scenario_selectors=args.scenario,
            tag_selectors=args.tag,
        )
        if args.list:
            print(
                f"{len(plan.scenarios)} selected product scenario(s); "
                f"profile denominator={plan.profile_expected_count}; "
                f"complete={plan.profile_complete}"
            )
            for scenario in plan.scenarios:
                print(
                    f"{scenario.scenario_id:48} "
                    f"{scenario.execution_id:38} {scenario.title}"
                )
            print(PRODUCT_SCENARIO_PROFILES[plan.profile_id].claim_boundary)
            return 0
        if args.dry_run:
            print(json.dumps(_plan_payload(plan), indent=2, sort_keys=True))
            return 0
        report = run_product_scenarios(
            repo_root=args.repo_root,
            evidence_root=args.evidence_root,
            profile_id=args.profile,
            scenario_selectors=args.scenario,
            tag_selectors=args.tag,
        )
    except (OSError, ScenarioManifestError, ScenarioRunError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if report["summary"]["selected_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
