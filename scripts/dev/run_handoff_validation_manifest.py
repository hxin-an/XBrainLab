#!/usr/bin/env python3
"""Run every registered handoff gate and verify the exact-source dossier."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.dev.handoff_evidence_recorder import (
    DEFAULT_BRANCH,
    HandoffEvidenceError,
    record_handoff_command,
    validate_handoff_dossier,
)
from scripts.dev.handoff_gate_spec import (
    HANDOFF_GATE_SPECS,
    REQUIRED_HANDOFF_CHECK_IDS,
)

ROOT = Path(__file__).resolve().parents[2]


class HandoffManifestError(RuntimeError):
    """Raised when the checked-in required-gate registry is inconsistent."""


def run_handoff_manifest(
    *,
    repo_root: Path,
    evidence_root: Path,
    model_cache_dir: Path,
    rag_cache_dir: Path,
    expected_branch: str = DEFAULT_BRANCH,
    require_upstream: bool = True,
    allow_external_evidence_root: bool = False,
) -> dict[str, Any]:
    """Record all required gates in order, then verify the complete dossier."""
    registered_ids = tuple(HANDOFF_GATE_SPECS)
    if registered_ids != REQUIRED_HANDOFF_CHECK_IDS:
        raise HandoffManifestError(
            "Required handoff gate registry drifted from its registered command order."
        )

    root = repo_root.expanduser().resolve()
    expanded_evidence_root = evidence_root.expanduser()
    output_root = (
        expanded_evidence_root
        if expanded_evidence_root.is_absolute()
        else root / expanded_evidence_root
    ).resolve()
    completed: list[str] = []
    for check_id in REQUIRED_HANDOFF_CHECK_IDS:
        spec = HANDOFF_GATE_SPECS[check_id]
        print(
            f"[handoff] section {spec.section}: {check_id}",
            file=sys.stderr,
            flush=True,
        )
        record = record_handoff_command(
            repo_root=root,
            evidence_root=output_root,
            section=spec.section,
            check_id=check_id,
            command=spec.resolve_argv(output_root),
            timeout_seconds=spec.timeout_seconds,
            expected_branch=expected_branch,
            require_upstream=require_upstream,
            model_cache_dir=model_cache_dir,
            rag_cache_dir=rag_cache_dir,
            allow_external_evidence_root=allow_external_evidence_root,
        )
        completed.append(check_id)
        if not record.get("passed"):
            reason = str(record.get("failure_reason") or "gate did not pass")
            return {
                "ok": False,
                "reason": f"{check_id}: {reason}",
                "completed_check_ids": completed,
                "required_check_ids": list(REQUIRED_HANDOFF_CHECK_IDS),
                "dossier_verified": False,
            }

    ok, reason = validate_handoff_dossier(
        repo_root=root,
        evidence_root=output_root,
        required_check_ids=REQUIRED_HANDOFF_CHECK_IDS,
        expected_branch=expected_branch,
        require_upstream=require_upstream,
        model_cache_dir=model_cache_dir,
        rag_cache_dir=rag_cache_dir,
        allow_external_evidence_root=allow_external_evidence_root,
    )
    return {
        "ok": ok,
        "reason": reason,
        "completed_check_ids": completed,
        "required_check_ids": list(REQUIRED_HANDOFF_CHECK_IDS),
        "dossier_verified": ok,
    }


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
    parser.add_argument("--expected-branch", default=DEFAULT_BRANCH)
    parser.add_argument("--no-upstream-check", action="store_true")
    parser.add_argument("--allow-external-evidence-root", action="store_true")
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
        )
    except (HandoffEvidenceError, HandoffManifestError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
