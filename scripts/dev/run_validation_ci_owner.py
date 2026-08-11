#!/usr/bin/env python3
"""Run, attest, and verify exact-source CI validation owners."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dev.ci_gate_ownership import CI_OWNER_EXECUTION_MODES
from scripts.dev.handoff_evidence_recorder import (
    DOSSIER_NAME,
    validate_portable_ci_owner_dossier,
)
from scripts.dev.run_validation_control_plane import (
    execute_validation_plan,
    resolve_comparison_base,
)
from scripts.dev.validation_ci_evidence import (
    CiCapabilityStatus,
    CiCapabilityVerdict,
    CiOwnerReceipt,
    collect_clean_ci_source_identity,
    evaluate_ci_capability_receipts,
    record_ci_owner_success,
    verify_ci_native_owner_evidence,
    verify_ci_owner_source_identity,
)
from scripts.dev.validation_ci_plan import CiValidationPlan
from scripts.dev.validation_control_plane import ValidationPlan

ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    return path.expanduser().resolve(strict=True).read_text(encoding="utf-8")


def _write(path: Path, value: str) -> None:
    destination = path.expanduser().resolve()
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
        handle.write(value + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


def _common(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--plan", type=Path, required=True)
    subparser.add_argument("--ci-plan", type=Path, required=True)
    subparser.add_argument("--owner", required=True)
    subparser.add_argument("--output", type=Path, required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record", help="attest a CI-native owner")
    _common(record)
    record.add_argument("--repo-root", type=Path, default=ROOT)
    record.add_argument("--evidence", type=Path, action="append", required=True)

    run = subparsers.add_parser("run", help="run one registry-backed CI owner")
    _common(run)
    run.add_argument("--repo-root", type=Path, default=ROOT)
    run.add_argument("--evidence-root", type=Path, required=True)
    run.add_argument("--target-sha", required=True)

    verify = subparsers.add_parser("verify", help="verify all owner receipts")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--ci-plan", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, action="append", default=[])
    verify.add_argument("--receipt-dir", type=Path)
    verify.add_argument("--registry-evidence-dir", type=Path)
    verify.add_argument("--repo-root", type=Path, default=ROOT)
    verify.add_argument("--target-sha", required=True)
    verify.add_argument("--output", type=Path, required=True)
    return parser


def _load_plans(args: argparse.Namespace) -> tuple[ValidationPlan, CiValidationPlan]:
    plan = ValidationPlan.from_json(_read(args.plan))
    ci_plan = CiValidationPlan.from_json(_read(args.ci_plan))
    if ci_plan.plan_digest != plan.digest():
        raise ValueError("CI plan digest differs from validation plan")
    if plan.source_sha is None or ci_plan.source_sha != plan.source_sha:
        raise ValueError("CI plan source differs from validation plan")
    return plan, ci_plan


def _run(args: argparse.Namespace) -> int:
    plan, ci_plan = _load_plans(args)
    if args.command == "record":
        receipt = record_ci_owner_success(
            plan,
            ci_plan,
            owner=args.owner,
            evidence_paths=args.evidence,
            repo_root=args.repo_root,
        )
        _write(args.output, receipt.to_json())
        return 0
    if args.command == "run":
        gate_ids = ci_plan.gate_ids_for_owner(args.owner)
        if not gate_ids or args.owner not in ci_plan.required_owners:
            raise ValueError(f"CI owner {args.owner!r} is not selected")
        if CI_OWNER_EXECUTION_MODES.get(args.owner) != "registry":
            raise ValueError(f"CI owner {args.owner!r} requires CI-native recording")
        expected_base_sha = resolve_comparison_base(
            args.repo_root.expanduser().resolve(strict=True),
            plan.descriptor,
            base_ref=args.target_sha,
            authorized_target_sha=args.target_sha,
        )
        partial = execute_validation_plan(
            plan,
            repo_root=args.repo_root,
            evidence_root=args.evidence_root,
            expected_branch="",
            source_sha=ci_plan.source_sha,
            expected_base_sha=expected_base_sha,
            require_upstream=False,
            execution_gate_ids=gate_ids,
            evidence_profile="ci-owner",
            profile_metadata={
                "owner": args.owner,
                "plan_digest": plan.digest(),
                "ci_plan_digest": ci_plan.digest(),
                "full_plan_gate_ids": list(plan.execution_ids),
            },
        )
        source_sha, head_tree_sha = collect_clean_ci_source_identity(args.repo_root)
        receipt = CiOwnerReceipt(
            owner=args.owner,
            execution_mode=CI_OWNER_EXECUTION_MODES[args.owner],
            plan_digest=partial.plan_digest,
            ci_plan_digest=ci_plan.digest(),
            source_sha=source_sha,
            head_tree_sha=head_tree_sha,
            completed_gate_ids=partial.completed_gate_ids,
            failed_gate_ids=partial.failed_gate_ids,
            evidence_digests=partial.evidence_digests,
        )
        _write(args.output, receipt.to_json())
        return (
            0
            if not receipt.failed_gate_ids and receipt.completed_gate_ids == gate_ids
            else 1
        )

    receipt_paths = list(args.receipt)
    if args.receipt_dir is not None:
        receipt_paths.extend(
            sorted(args.receipt_dir.expanduser().resolve(strict=True).glob("*.json"))
        )
    if not receipt_paths:
        raise ValueError("CI capability verification requires owner receipts")
    receipts = tuple(CiOwnerReceipt.from_json(_read(path)) for path in receipt_paths)
    evidence_reasons = _verify_owner_evidence(
        plan,
        ci_plan,
        receipts,
        repo_root=args.repo_root,
        registry_evidence_dir=args.registry_evidence_dir,
        target_sha=args.target_sha,
    )
    verdict = evaluate_ci_capability_receipts(
        plan,
        ci_plan,
        receipts,
        evidence_verified_owner_ids=(
            () if evidence_reasons else ci_plan.required_owners
        ),
    )
    if evidence_reasons:
        verdict = CiCapabilityVerdict(
            status=CiCapabilityStatus.BLOCKED,
            plan_digest=plan.digest(),
            source_sha=ci_plan.source_sha,
            missing_owners=verdict.missing_owners,
            failed_gate_ids=verdict.failed_gate_ids,
            reasons=tuple(sorted({*verdict.reasons, *evidence_reasons})),
        )
    _write(args.output, verdict.to_json())
    print(verdict.to_json())
    return 0 if verdict.status is CiCapabilityStatus.PASSED else 1


def _verify_owner_evidence(
    plan: ValidationPlan,
    ci_plan: CiValidationPlan,
    receipts: Sequence[CiOwnerReceipt],
    *,
    repo_root: Path,
    registry_evidence_dir: Path | None,
    target_sha: str,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    try:
        expected_base_sha = resolve_comparison_base(
            repo_root.expanduser().resolve(strict=True),
            plan.descriptor,
            base_ref=target_sha,
            authorized_target_sha=target_sha,
        )
    except (OSError, RuntimeError, ValueError):
        reasons.add("plan-target-base-unavailable")
    else:
        if plan.base_sha != expected_base_sha:
            reasons.add("plan-target-base-mismatch")
    registry_receipts = {
        receipt.owner: receipt
        for receipt in receipts
        if receipt.execution_mode == "registry"
    }
    dossier_by_owner: dict[str, Path] = {}
    if registry_evidence_dir is not None and registry_receipts:
        try:
            evidence_dir = registry_evidence_dir.expanduser().resolve(strict=True)
            dossier_paths = tuple(sorted(evidence_dir.rglob(DOSSIER_NAME)))
        except OSError:
            dossier_paths = ()
            reasons.add("registry-evidence-directory-missing")
        for dossier_path in dossier_paths:
            try:
                payload = json.loads(dossier_path.read_text(encoding="utf-8"))
                metadata = payload.get("profile_metadata")
                owner = metadata.get("owner") if isinstance(metadata, dict) else None
            except (OSError, json.JSONDecodeError):
                reasons.add("registry-dossier-unreadable")
                continue
            if not isinstance(owner, str) or owner not in registry_receipts:
                reasons.add("unexpected-registry-dossier")
                continue
            if owner in dossier_by_owner:
                reasons.add(f"duplicate-registry-dossier:{owner}")
                continue
            dossier_by_owner[owner] = dossier_path.parent
    elif registry_receipts:
        reasons.add("registry-evidence-directory-missing")

    for receipt in receipts:
        source_ok, source_reason = verify_ci_owner_source_identity(
            receipt,
            repo_root=repo_root,
        )
        if not source_ok:
            reasons.add(f"owner-source-invalid:{receipt.owner}:{source_reason}")
            continue
        if receipt.execution_mode == "ci-native-equivalent":
            ok, reason = verify_ci_native_owner_evidence(
                receipt,
                plan=plan,
                ci_plan=ci_plan,
                repo_root=repo_root,
            )
        else:
            evidence_root = dossier_by_owner.get(receipt.owner)
            if evidence_root is None:
                reasons.add(f"registry-dossier-missing:{receipt.owner}")
                continue
            ok, reason = validate_portable_ci_owner_dossier(
                repo_root=repo_root,
                evidence_root=evidence_root,
                owner=receipt.owner,
                plan_digest=plan.digest(),
                ci_plan_digest=ci_plan.digest(),
                source_sha=ci_plan.source_sha,
                full_plan_gate_ids=plan.execution_ids,
                required_check_ids=ci_plan.gate_ids_for_owner(receipt.owner),
                expected_evidence_digests=dict(receipt.evidence_digests),
                target_sha=target_sha,
            )
        if not ok:
            reasons.add(f"owner-evidence-invalid:{receipt.owner}:{reason}")
    return tuple(sorted(reasons))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
