#!/usr/bin/env python3
"""Compatibility entrypoint for the canonical handoff validation control plane."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.dev.handoff_evidence_recorder import HandoffEvidenceError
from scripts.dev.handoff_gate_spec import (
    HANDOFF_GATE_SPECS,
    REQUIRED_HANDOFF_CHECK_IDS,
)
from scripts.dev.run_validation_control_plane import (
    ValidationExecutionError,
    collect_changed_paths,
    execute_validation_plan,
    resolve_comparison_base,
    verify_validation_evidence,
)
from scripts.dev.validation_control_plane import (
    ChangeDescriptor,
    ChangeIntent,
    ClaimLevel,
    RiskLevel,
    ValidationPlan,
    VerdictStatus,
    bind_validation_plan,
    plan_validation,
)
from scripts.dev.validation_gate_catalog import HANDOFF_VALIDATION_GATE_CATALOG

ROOT = Path(__file__).resolve().parents[2]


class HandoffManifestError(RuntimeError):
    """Raised when the checked-in required-gate registry is inconsistent."""


def run_handoff_manifest(
    *,
    repo_root: Path,
    evidence_root: Path,
    model_cache_dir: Path,
    rag_cache_dir: Path,
    expected_branch: str,
    require_upstream: bool = True,
    allow_external_evidence_root: bool = False,
    intent: ChangeIntent = ChangeIntent.BUG_FIX,
    base_ref: str = "origin/main",
    target_sha: str,
) -> dict[str, Any]:
    """Plan, execute, and verify the full handoff inventory once."""
    registered_ids = tuple(HANDOFF_GATE_SPECS)
    if registered_ids != REQUIRED_HANDOFF_CHECK_IDS:
        raise HandoffManifestError(
            "Required handoff gate registry drifted from its registered command order."
        )

    root = repo_root.expanduser().resolve(strict=True)
    expanded_evidence_root = evidence_root.expanduser()
    output_root = (
        expanded_evidence_root
        if expanded_evidence_root.is_absolute()
        else root / expanded_evidence_root
    ).resolve()
    plan = _build_handoff_plan(
        root,
        intent=intent,
        base_ref=base_ref,
        target_sha=target_sha,
    )
    if plan.execution_ids != REQUIRED_HANDOFF_CHECK_IDS:
        raise HandoffManifestError(
            "Handoff plan does not cover the complete registered inventory."
        )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "validation-plan.json").write_text(
        plan.to_json() + "\n",
        encoding="utf-8",
    )
    receipt = execute_validation_plan(
        plan,
        repo_root=root,
        evidence_root=output_root,
        expected_branch=expected_branch,
        source_sha=plan.source_sha,
        expected_base_sha=plan.base_sha,
        require_upstream=require_upstream,
        model_cache_dir=model_cache_dir,
        rag_cache_dir=rag_cache_dir,
        allow_external_evidence_root=allow_external_evidence_root,
    )
    (output_root / "validation-receipt.json").write_text(
        receipt.to_json() + "\n",
        encoding="utf-8",
    )
    verdict = verify_validation_evidence(
        plan,
        receipt,
        repo_root=root,
        evidence_root=output_root,
        expected_branch=expected_branch,
        source_sha=plan.source_sha,
        expected_base_sha=plan.base_sha,
        require_upstream=require_upstream,
        model_cache_dir=model_cache_dir,
        rag_cache_dir=rag_cache_dir,
        allow_external_evidence_root=allow_external_evidence_root,
    )
    ok = verdict.status is VerdictStatus.PASSED
    return {
        "ok": ok,
        "reason": "" if ok else ", ".join(verdict.reasons),
        "completed_check_ids": list(receipt.completed_gate_ids),
        "required_check_ids": list(REQUIRED_HANDOFF_CHECK_IDS),
        "dossier_verified": ok,
        "plan_digest": plan.digest(),
        "receipt_digest": receipt.digest(),
        "verdict_status": verdict.status.value,
    }


def _build_handoff_plan(
    repo_root: Path,
    *,
    intent: ChangeIntent,
    base_ref: str,
    target_sha: str,
) -> ValidationPlan:
    descriptor = ChangeDescriptor(
        intent=intent,
        claim_level=ClaimLevel.HANDOFF,
        declared_risk=RiskLevel.CRITICAL,
    )
    base_sha = resolve_comparison_base(
        repo_root,
        descriptor,
        base_ref=base_ref,
        authorized_target_sha=target_sha,
    )
    plan = plan_validation(
        descriptor,
        collect_changed_paths(repo_root, base_ref=base_sha),
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )
    plan = bind_validation_plan(
        plan,
        source_sha=_git_head(repo_root),
        base_sha=base_sha,
    )
    if not plan.ready:
        raise HandoffManifestError(
            "Handoff validation plan is blocked by unknown paths or rules."
        )
    return plan


def _git_head(repo_root: Path) -> str:
    git = shutil.which("git")
    if git is None:
        raise HandoffManifestError("git executable is unavailable.")
    completed = subprocess.run(  # noqa: S603 - fixed git identity query.
        [git, "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise HandoffManifestError(f"Could not resolve candidate commit: {detail}")
    return completed.stdout.strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--model-cache-dir", type=Path, required=True)
    parser.add_argument("--rag-cache-dir", type=Path, required=True)
    parser.add_argument("--expected-branch", required=True)
    parser.add_argument("--no-upstream-check", action="store_true")
    parser.add_argument("--allow-external-evidence-root", action="store_true")
    parser.add_argument(
        "--intent",
        choices=[intent.value for intent in ChangeIntent],
        default=ChangeIntent.BUG_FIX.value,
    )
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument(
        "--target-sha",
        required=True,
        help="immutable authorized target tip (normally git rev-parse origin/main)",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        root = args.repo_root.expanduser().resolve(strict=True)
        evidence_root = args.evidence_root
        if evidence_root is None:
            evidence_root = root / "build" / "handoff-evidence" / _git_head(root)
        result = run_handoff_manifest(
            repo_root=root,
            evidence_root=evidence_root,
            model_cache_dir=args.model_cache_dir,
            rag_cache_dir=args.rag_cache_dir,
            expected_branch=args.expected_branch,
            require_upstream=not args.no_upstream_check,
            allow_external_evidence_root=args.allow_external_evidence_root,
            intent=ChangeIntent(args.intent),
            base_ref=args.base_ref,
            target_sha=args.target_sha,
        )
    except (
        HandoffEvidenceError,
        HandoffManifestError,
        ValidationExecutionError,
        OSError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
