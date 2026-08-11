#!/usr/bin/env python3
"""Plan, execute, and verify risk-selected XBrainLab validation gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dev.handoff_gate_spec import HANDOFF_GATE_SPECS
from scripts.dev.validation_control_plane import (
    ChangeDescriptor,
    ChangeIntent,
    ClaimLevel,
    ClaimVerdict,
    Layer,
    RiskLevel,
    ValidationPlan,
    ValidationReceipt,
    VerdictStatus,
    bind_validation_plan,
    evaluate_validation_receipt,
    plan_validation,
)
from scripts.dev.validation_gate_catalog import HANDOFF_VALIDATION_GATE_CATALOG

ROOT = Path(__file__).resolve().parents[2]


class ValidationExecutionError(RuntimeError):
    """Raised when a plan cannot safely enter the executable evidence boundary."""


GitRunner = Callable[..., str]
Recorder = Callable[..., Mapping[str, Any]]
DossierValidator = Callable[..., tuple[bool, str]]
ChangedPathCollector = Callable[..., tuple[str, ...]]

_MAIN_BASE_CLAIMS = frozenset(
    {
        ClaimLevel.BOUNDED_COMPLETE,
        ClaimLevel.PRODUCT_PR,
        ClaimLevel.HANDOFF,
        ClaimLevel.RELEASE,
        ClaimLevel.THESIS,
    }
)


def _evidence_profile_context(
    plan: ValidationPlan,
    *,
    evidence_profile: str | None,
    profile_metadata: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    profile = evidence_profile
    if profile is None:
        profile = (
            "handoff"
            if plan.descriptor.claim_level
            in {ClaimLevel.HANDOFF, ClaimLevel.RELEASE, ClaimLevel.THESIS}
            else "validation-plan"
        )
    if profile_metadata is not None:
        return profile, dict(profile_metadata)
    if profile == "handoff":
        return profile, {}
    return profile, {
        "plan_digest": plan.digest(),
        "source_sha": plan.source_sha,
        "full_plan_gate_ids": list(plan.execution_ids),
    }


def _run_git(repo_root: Path, *args: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise ValidationExecutionError("git executable is unavailable")
    completed = subprocess.run(  # noqa: S603 - fixed executable and bounded args.
        [git, *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValidationExecutionError(
            f"git {' '.join(args)} failed with {completed.returncode}: {detail}"
        )
    return completed.stdout


def collect_changed_paths(
    repo_root: Path,
    *,
    base_ref: str = "origin/main",
    git_runner: GitRunner = _run_git,
) -> tuple[str, ...]:
    """Union committed, staged, dirty, and untracked repository paths."""

    commands = (
        (
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACDMRTUXB",
            f"{base_ref}...HEAD",
        ),
        ("diff", "--name-only", "--no-renames", "--diff-filter=ACDMRTUXB"),
        (
            "diff",
            "--cached",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACDMRTUXB",
        ),
        ("ls-files", "--others", "--exclude-standard"),
    )
    paths: set[str] = set()
    for command in commands:
        output = git_runner(repo_root, *command)
        paths.update(line.strip() for line in output.splitlines() if line.strip())
    return tuple(sorted(paths))


def resolve_comparison_base(
    repo_root: Path,
    descriptor: ChangeDescriptor,
    *,
    base_ref: str,
    authorized_target_sha: str | None = None,
    git_runner: GitRunner = _run_git,
) -> str:
    """Resolve a merge base against an explicit immutable target identity."""

    if descriptor.claim_level in _MAIN_BASE_CLAIMS:
        if authorized_target_sha is None:
            raise ValidationExecutionError(
                "Claim-bearing validation requires an authorized target SHA."
            )
        target_sha = authorized_target_sha.strip()
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", target_sha):
            raise ValidationExecutionError("Authorized target SHA is invalid.")
        resolved_ref = git_runner(repo_root, "rev-parse", base_ref).strip()
        if resolved_ref != target_sha:
            raise ValidationExecutionError(
                "Comparison ref does not match the authorized target SHA."
            )
        base_ref = target_sha
    return git_runner(repo_root, "merge-base", "HEAD", base_ref).strip()


def _canonical_plan(plan: ValidationPlan) -> ValidationPlan:
    canonical = plan_validation(
        plan.descriptor,
        plan.changed_paths,
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )
    if (
        plan.source_sha is not None
        and plan.base_sha is not None
        and plan.target_sha is not None
    ):
        canonical = bind_validation_plan(
            canonical,
            source_sha=plan.source_sha,
            base_sha=plan.base_sha,
            target_sha=plan.target_sha,
        )
    return canonical


def _record_digest(record: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        record,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def execute_validation_plan(
    plan: ValidationPlan,
    *,
    repo_root: Path,
    evidence_root: Path,
    expected_branch: str,
    source_sha: str | None = None,
    expected_base_sha: str | None = None,
    expected_target_sha: str | None = None,
    model_cache_dir: Path | None = None,
    rag_cache_dir: Path | None = None,
    require_upstream: bool = True,
    allow_external_evidence_root: bool = False,
    execution_gate_ids: Sequence[str] | None = None,
    evidence_profile: str | None = None,
    profile_metadata: Mapping[str, Any] | None = None,
    recorder: Recorder | None = None,
    dossier_validator: DossierValidator | None = None,
    changed_path_collector: ChangedPathCollector = collect_changed_paths,
) -> ValidationReceipt:
    """Execute a canonical plan once, stopping at the first failed gate."""

    canonical = _canonical_plan(plan)
    if canonical.digest() != plan.digest():
        raise ValidationExecutionError(
            "Validation plan is stale or edited relative to the canonical catalog."
        )
    if not plan.ready:
        raise ValidationExecutionError(
            "Validation plan is blocked by unknown paths or unresolved rules."
        )
    if plan.source_sha is None or plan.base_sha is None or plan.target_sha is None:
        raise ValidationExecutionError("Validation plan is not bound to exact source.")
    if plan.descriptor.claim_level in _MAIN_BASE_CLAIMS and expected_base_sha is None:
        raise ValidationExecutionError(
            "Claim-bearing execution requires an authorized target merge base."
        )
    if plan.descriptor.claim_level in _MAIN_BASE_CLAIMS and expected_target_sha is None:
        raise ValidationExecutionError(
            "Claim-bearing execution requires an authorized target tip."
        )
    if expected_base_sha is not None and plan.base_sha != expected_base_sha:
        raise ValidationExecutionError(
            "Validation plan base differs from the authorized target merge base."
        )
    if expected_target_sha is not None and plan.target_sha != expected_target_sha:
        raise ValidationExecutionError(
            "Validation plan target differs from the authorized target tip."
        )
    if recorder is None or dossier_validator is None:
        from scripts.dev.handoff_evidence_recorder import (
            record_handoff_command,
            validate_handoff_dossier,
        )

        recorder = recorder or record_handoff_command
        dossier_validator = dossier_validator or validate_handoff_dossier
    resolved_profile, resolved_profile_metadata = _evidence_profile_context(
        plan,
        evidence_profile=evidence_profile,
        profile_metadata=profile_metadata,
    )

    planned = set(plan.execution_ids)
    if execution_gate_ids is None:
        selected = planned
    else:
        if not execution_gate_ids:
            raise ValidationExecutionError(
                "Partial execution requires at least one gate."
            )
        if len(execution_gate_ids) != len(set(execution_gate_ids)):
            raise ValidationExecutionError(
                "Partial execution repeats a duplicate gate ID."
            )
        selected = set(execution_gate_ids)
        unselected = selected.difference(planned)
        if unselected:
            raise ValidationExecutionError(
                "Partial execution includes gates not selected by the plan: "
                f"{sorted(unselected)}."
            )
    unregistered = selected.difference(HANDOFF_GATE_SPECS)
    if unregistered:
        raise ValidationExecutionError(
            f"Validation plan references unregistered gates: {sorted(unregistered)}."
        )
    ordered_ids = tuple(
        gate_id for gate_id in HANDOFF_GATE_SPECS if gate_id in selected
    )
    if set(ordered_ids) != selected:
        raise ValidationExecutionError("Validation plan could not be registry ordered.")

    root = repo_root.expanduser().resolve(strict=True)
    resolved_evidence_root = evidence_root.expanduser()
    if not resolved_evidence_root.is_absolute():
        resolved_evidence_root = root / resolved_evidence_root
    resolved_evidence_root = resolved_evidence_root.resolve()
    resolved_source_sha = source_sha or _run_git(root, "rev-parse", "HEAD").strip()
    if resolved_source_sha != plan.source_sha:
        raise ValidationExecutionError(
            "Current source SHA differs from planned source SHA."
        )
    current_paths = changed_path_collector(root, base_ref=plan.base_sha)
    planned_paths = tuple(changed.path for changed in plan.changed_paths)
    if current_paths != planned_paths:
        raise ValidationExecutionError(
            "Current changed paths differ from planned paths."
        )

    completed: list[str] = []
    failed: list[str] = []
    evidence: list[tuple[str, str]] = []
    for gate_id in ordered_ids:
        spec = HANDOFF_GATE_SPECS[gate_id]
        record = recorder(
            repo_root=root,
            evidence_root=resolved_evidence_root,
            section=spec.section,
            check_id=gate_id,
            command=spec.resolve_argv(
                resolved_evidence_root,
                expected_branch=expected_branch,
                target_sha=plan.target_sha,
            ),
            timeout_seconds=spec.timeout_seconds,
            expected_branch=expected_branch,
            target_sha=plan.target_sha,
            require_upstream=require_upstream,
            model_cache_dir=model_cache_dir,
            rag_cache_dir=rag_cache_dir,
            allow_external_evidence_root=allow_external_evidence_root,
            evidence_profile=resolved_profile,
            profile_metadata=resolved_profile_metadata,
        )
        completed.append(gate_id)
        evidence.append((gate_id, _record_digest(record)))
        if not bool(record.get("passed")):
            failed.append(gate_id)
            break

    if not failed:
        dossier_ok, dossier_reason = dossier_validator(
            repo_root=root,
            evidence_root=resolved_evidence_root,
            required_check_ids=ordered_ids,
            expected_branch=expected_branch,
            require_upstream=require_upstream,
            model_cache_dir=model_cache_dir,
            rag_cache_dir=rag_cache_dir,
            allow_external_evidence_root=allow_external_evidence_root,
            expected_profile=resolved_profile,
            expected_profile_metadata=resolved_profile_metadata,
            target_sha=plan.target_sha,
        )
        if not dossier_ok:
            raise ValidationExecutionError(
                f"Selected-gate dossier verification failed: {dossier_reason}"
            )

    return ValidationReceipt(
        plan_digest=plan.digest(),
        source_sha=resolved_source_sha,
        completed_gate_ids=tuple(completed),
        failed_gate_ids=tuple(failed),
        evidence_digests=tuple(evidence),
    )


def _blocked_verdict(
    plan: ValidationPlan,
    receipt: ValidationReceipt,
    *reasons: str,
) -> ClaimVerdict:
    return ClaimVerdict(
        status=VerdictStatus.BLOCKED,
        claim_level=plan.descriptor.claim_level,
        plan_digest=plan.digest(),
        source_sha=receipt.source_sha,
        reasons=tuple(reasons),
    )


def verify_validation_evidence(
    plan: ValidationPlan,
    receipt: ValidationReceipt,
    *,
    repo_root: Path,
    evidence_root: Path,
    expected_branch: str,
    source_sha: str | None = None,
    expected_base_sha: str | None = None,
    expected_target_sha: str | None = None,
    model_cache_dir: Path | None = None,
    rag_cache_dir: Path | None = None,
    require_upstream: bool = True,
    allow_external_evidence_root: bool = False,
    evidence_profile: str | None = None,
    profile_metadata: Mapping[str, Any] | None = None,
    dossier_validator: DossierValidator | None = None,
    changed_path_collector: ChangedPathCollector = collect_changed_paths,
) -> ClaimVerdict:
    """Verify receipt lineage against the current dossier and exact source."""

    canonical = _canonical_plan(plan)
    if canonical.digest() != plan.digest():
        return _blocked_verdict(plan, receipt, "plan-stale-or-edited")
    verdict = evaluate_validation_receipt(plan, receipt)
    if verdict.status is not VerdictStatus.PASSED:
        return verdict
    if plan.source_sha is None or plan.base_sha is None or plan.target_sha is None:
        return _blocked_verdict(plan, receipt, "plan-source-lineage-missing")
    if plan.descriptor.claim_level in _MAIN_BASE_CLAIMS and expected_base_sha is None:
        return _blocked_verdict(plan, receipt, "plan-target-base-missing")
    if plan.descriptor.claim_level in _MAIN_BASE_CLAIMS and expected_target_sha is None:
        return _blocked_verdict(plan, receipt, "plan-target-tip-missing")
    if expected_base_sha is not None and plan.base_sha != expected_base_sha:
        return _blocked_verdict(plan, receipt, "plan-target-base-mismatch")
    if expected_target_sha is not None and plan.target_sha != expected_target_sha:
        return _blocked_verdict(plan, receipt, "plan-target-tip-mismatch")
    if dossier_validator is None:
        from scripts.dev.handoff_evidence_recorder import validate_handoff_dossier

        dossier_validator = validate_handoff_dossier
    resolved_profile, resolved_profile_metadata = _evidence_profile_context(
        plan,
        evidence_profile=evidence_profile,
        profile_metadata=profile_metadata,
    )

    root = repo_root.expanduser().resolve(strict=True)
    current_source_sha = source_sha or _run_git(root, "rev-parse", "HEAD").strip()
    if (
        current_source_sha != receipt.source_sha
        or current_source_sha != plan.source_sha
    ):
        return _blocked_verdict(plan, receipt, "source-sha-mismatch")
    current_paths = changed_path_collector(root, base_ref=plan.base_sha)
    planned_paths = tuple(changed.path for changed in plan.changed_paths)
    if current_paths != planned_paths:
        return _blocked_verdict(plan, receipt, "changed-paths-mismatch")
    selected = set(plan.execution_ids)
    ordered_ids = tuple(
        gate_id for gate_id in HANDOFF_GATE_SPECS if gate_id in selected
    )
    dossier_ok, dossier_reason = dossier_validator(
        repo_root=root,
        evidence_root=evidence_root,
        required_check_ids=ordered_ids,
        expected_branch=expected_branch,
        require_upstream=require_upstream,
        model_cache_dir=model_cache_dir,
        rag_cache_dir=rag_cache_dir,
        allow_external_evidence_root=allow_external_evidence_root,
        expected_profile=resolved_profile,
        expected_profile_metadata=resolved_profile_metadata,
        target_sha=plan.target_sha,
    )
    if not dossier_ok:
        return _blocked_verdict(
            plan,
            receipt,
            f"dossier-invalid:{dossier_reason}",
        )
    try:
        expanded_evidence_root = evidence_root.expanduser()
        resolved_evidence_root = (
            expanded_evidence_root
            if expanded_evidence_root.is_absolute()
            else root / expanded_evidence_root
        ).resolve()
        dossier = json.loads(
            (resolved_evidence_root / "handoff-evidence.json").read_text(
                encoding="utf-8"
            )
        )
        checkout = dossier["checkout"]
        checks = dossier["checks"]
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
        return _blocked_verdict(plan, receipt, f"dossier-unreadable:{error}")
    if not isinstance(checkout, dict) or not isinstance(checks, dict):
        return _blocked_verdict(plan, receipt, "dossier-lineage-malformed")
    if checkout.get("commit_sha") != receipt.source_sha:
        return _blocked_verdict(plan, receipt, "dossier-source-sha-mismatch")
    expected_digests = dict(receipt.evidence_digests)
    for gate_id in ordered_ids:
        record = checks.get(gate_id)
        if not isinstance(record, dict) or _record_digest(
            record
        ) != expected_digests.get(gate_id):
            return _blocked_verdict(
                plan,
                receipt,
                "evidence-digest-mismatch",
                gate_id,
            )
    return verdict


def _write_output(value: str, output: Path | None) -> None:
    if output is None:
        print(value)
        return
    destination = output.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(value)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


def _read_text(path: Path) -> str:
    return path.expanduser().resolve(strict=True).read_text(encoding="utf-8")


def _add_descriptor_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--intent",
        choices=[intent.value for intent in ChangeIntent],
        required=True,
    )
    parser.add_argument(
        "--claim",
        choices=[claim.value for claim in ClaimLevel],
        default=ClaimLevel.CHECKPOINT.value,
    )
    parser.add_argument(
        "--layer",
        action="append",
        choices=[layer.value for layer in Layer],
        default=[],
    )
    parser.add_argument(
        "--risk",
        choices=[risk.name.casefold() for risk in RiskLevel],
        default=RiskLevel.LOW.name.casefold(),
    )
    parser.add_argument("--required-rule", action="append", default=[])


def _descriptor_from_args(args: argparse.Namespace) -> ChangeDescriptor:
    return ChangeDescriptor(
        intent=ChangeIntent(args.intent),
        claim_level=ClaimLevel(args.claim),
        declared_layers=frozenset(Layer(value) for value in args.layer),
        declared_risk=RiskLevel[args.risk.upper()],
        required_rule_ids=frozenset(args.required_rule),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    describe = subparsers.add_parser("describe", help="write a change descriptor")
    _add_descriptor_arguments(describe)
    describe.add_argument("--output", type=Path)

    plan = subparsers.add_parser("plan", help="select a canonical validation DAG")
    plan.add_argument("--repo-root", type=Path, default=ROOT)
    plan.add_argument("--descriptor", type=Path, required=True)
    plan.add_argument("--path", action="append", default=[])
    plan.add_argument("--base-ref", default="origin/main")
    plan.add_argument("--target-sha")
    plan.add_argument("--output", type=Path)

    run = subparsers.add_parser("run", help="execute selected registered gates")
    run.add_argument("--repo-root", type=Path, default=ROOT)
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--evidence-root", type=Path)
    run.add_argument("--receipt-output", type=Path)
    run.add_argument("--model-cache-dir", type=Path)
    run.add_argument("--rag-cache-dir", type=Path)
    run.add_argument("--expected-branch")
    run.add_argument("--target-ref")
    run.add_argument("--target-sha")
    run.add_argument("--no-upstream-check", action="store_true")
    run.add_argument("--allow-external-evidence-root", action="store_true")

    verify = subparsers.add_parser("verify", help="verify receipt and dossier lineage")
    verify.add_argument("--repo-root", type=Path, default=ROOT)
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--evidence-root", type=Path, required=True)
    verify.add_argument("--model-cache-dir", type=Path)
    verify.add_argument("--rag-cache-dir", type=Path)
    verify.add_argument("--expected-branch")
    verify.add_argument("--target-ref")
    verify.add_argument("--target-sha")
    verify.add_argument("--no-upstream-check", action="store_true")
    verify.add_argument("--allow-external-evidence-root", action="store_true")
    verify.add_argument("--output", type=Path)

    report = subparsers.add_parser("report", help="render a plan/receipt verdict")
    report.add_argument("--plan", type=Path, required=True)
    report.add_argument("--receipt", type=Path, required=True)
    report.add_argument("--output", type=Path)
    return parser


def _run_cli(args: argparse.Namespace) -> int:
    if args.command == "describe":
        _write_output(_descriptor_from_args(args).to_json(), args.output)
        return 0

    if args.command == "plan":
        descriptor = ChangeDescriptor.from_json(_read_text(args.descriptor))
        root = args.repo_root.expanduser().resolve(strict=True)
        base_sha = resolve_comparison_base(
            root,
            descriptor,
            base_ref=args.base_ref,
            authorized_target_sha=args.target_sha,
        )
        discovered_paths = collect_changed_paths(
            root,
            base_ref=base_sha,
        )
        paths = tuple(sorted(set(discovered_paths).union(args.path)))
        plan = plan_validation(
            descriptor,
            paths,
            gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
        )
        plan = bind_validation_plan(
            plan,
            source_sha=_run_git(root, "rev-parse", "HEAD").strip(),
            base_sha=base_sha,
            target_sha=base_sha if args.target_sha is None else args.target_sha,
        )
        _write_output(plan.to_json(), args.output)
        return 0 if plan.ready else 1

    if args.command == "run":
        plan = ValidationPlan.from_json(_read_text(args.plan))
        root = args.repo_root.expanduser().resolve(strict=True)
        source_sha = _run_git(root, "rev-parse", "HEAD").strip()
        branch = (
            args.expected_branch or _run_git(root, "branch", "--show-current").strip()
        )
        evidence_root = args.evidence_root or (
            root / "build" / "validation-evidence" / source_sha / plan.digest()
        )
        target_ref = args.target_ref or (
            "origin/main" if plan.descriptor.claim_level in _MAIN_BASE_CLAIMS else None
        )
        expected_base_sha = (
            resolve_comparison_base(
                root,
                plan.descriptor,
                base_ref=target_ref,
                authorized_target_sha=args.target_sha,
            )
            if target_ref is not None
            else None
        )
        receipt = execute_validation_plan(
            plan,
            repo_root=root,
            evidence_root=evidence_root,
            source_sha=source_sha,
            expected_base_sha=expected_base_sha,
            expected_target_sha=args.target_sha,
            expected_branch=branch,
            model_cache_dir=args.model_cache_dir,
            rag_cache_dir=args.rag_cache_dir,
            require_upstream=not args.no_upstream_check,
            allow_external_evidence_root=args.allow_external_evidence_root,
        )
        receipt_output = (
            args.receipt_output or evidence_root / "validation-receipt.json"
        )
        _write_output(receipt.to_json(), receipt_output)
        verdict = evaluate_validation_receipt(plan, receipt)
        print(verdict.to_json())
        return 0 if verdict.status is VerdictStatus.PASSED else 1

    plan = ValidationPlan.from_json(_read_text(args.plan))
    receipt = ValidationReceipt.from_json(_read_text(args.receipt))
    if args.command == "verify":
        root = args.repo_root.expanduser().resolve(strict=True)
        branch = (
            args.expected_branch or _run_git(root, "branch", "--show-current").strip()
        )
        target_ref = args.target_ref or (
            "origin/main" if plan.descriptor.claim_level in _MAIN_BASE_CLAIMS else None
        )
        expected_base_sha = (
            resolve_comparison_base(
                root,
                plan.descriptor,
                base_ref=target_ref,
                authorized_target_sha=args.target_sha,
            )
            if target_ref is not None
            else None
        )
        verdict = verify_validation_evidence(
            plan,
            receipt,
            repo_root=root,
            evidence_root=args.evidence_root,
            expected_branch=branch,
            expected_base_sha=expected_base_sha,
            expected_target_sha=args.target_sha,
            model_cache_dir=args.model_cache_dir,
            rag_cache_dir=args.rag_cache_dir,
            require_upstream=not args.no_upstream_check,
            allow_external_evidence_root=args.allow_external_evidence_root,
        )
    else:
        canonical = _canonical_plan(plan)
        if canonical.digest() != plan.digest():
            raise ValidationExecutionError("plan is stale relative to the catalog")
        verdict = evaluate_validation_receipt(plan, receipt)
        if verdict.status is VerdictStatus.PASSED:
            verdict = _blocked_verdict(
                plan,
                receipt,
                "dossier-verification-not-performed",
            )
    _write_output(verdict.to_json(), args.output)
    return 0 if verdict.status is VerdictStatus.PASSED else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return _run_cli(args)
    except (
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
