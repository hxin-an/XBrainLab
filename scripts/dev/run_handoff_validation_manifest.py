#!/usr/bin/env python3
"""Run every registered handoff gate and verify the exact-source dossier."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)
from scripts.dev.handoff_evidence_recorder import (
    DEFAULT_BRANCH,
    HandoffEvidenceError,
    persist_handoff_records,
    record_handoff_command,
    validate_handoff_dossier,
)
from scripts.dev.handoff_gate_spec import (
    HANDOFF_GATE_SPECS,
    REQUIRED_HANDOFF_CHECK_IDS,
)

ROOT = Path(__file__).resolve().parents[2]

_SERIAL_GATE_IDS = (
    "git-status",
    "git-head",
    "git-upstream",
    "git-divergence",
    "git-worktrees",
    "git-diff-check",
    "ruff-check",
    "ruff-format-check",
    "basedpyright",
    "mkdocs-strict",
    "architecture-compliance",
    "complete-regression",
)
_DEFERRED_PREREQUISITE_IDS = (
    "fetch-required-ci",
    "verify-required-ci",
)
_POST_REGRESSION_LANES = (
    (
        "command-spine",
        "assistant-security-suite",
        "assistant-frontend-contract",
        "human-like-product",
        "ui-reviewer-fixes",
        "dataset-narrow",
        "visualization-render",
        "chatpanel-dpi",
        "native-lifecycle-tests",
        "preprocess-native-stress",
        "ui-native-render-stress",
        "real-data-interpretation-training",
        "wizard-format-matrix",
        "required-public-io",
    ),
    (
        "data-import-wizard-capture",
        "data-import-wizard-validate",
        "startup-smoke",
        "ui-visual-baseline",
    ),
    (
        "granite-runtime",
        "stable-assistant-model-eval",
        "rag-offline",
        "resource-calibration",
    ),
    (
        "dataset-validation-matrix",
        "data-interpretation-matrix",
        "public-cross-source-training",
    ),
)
_FINAL_GATE_IDS = ("handoff-dashboard",)


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
    manifest_source_identity = collect_source_identity(root, refresh=True)
    if manifest_source_identity.get("error"):
        raise HandoffManifestError(str(manifest_source_identity["error"]))
    if manifest_source_identity.get("dirty") is not False:
        raise HandoffManifestError(
            "Handoff manifest requires a clean full-source identity."
        )
    _validate_fixed_execution_plan(registered_ids)
    completed: list[str] = []

    def record_gate(
        check_id: str,
        *,
        defer_dossier_update: bool,
    ) -> dict[str, Any]:
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
            manifest_source_identity=manifest_source_identity,
            defer_dossier_update=defer_dossier_update,
        )
        return record

    for check_id in _SERIAL_GATE_IDS:
        record = record_gate(check_id, defer_dossier_update=False)
        completed.append(check_id)
        if not record.get("passed"):
            return _failed_result(check_id, record=record, completed=completed)

    deferred_records: list[dict[str, Any]] = []
    for check_id in _DEFERRED_PREREQUISITE_IDS:
        record = record_gate(check_id, defer_dossier_update=True)
        deferred_records.append(record)
        if not record.get("passed"):
            break

    if _POST_REGRESSION_LANES and all(
        record.get("passed") for record in deferred_records
    ):

        def record_lane(check_ids: tuple[str, ...]) -> list[dict[str, Any]]:
            lane_records: list[dict[str, Any]] = []
            for check_id in check_ids:
                record = record_gate(check_id, defer_dossier_update=True)
                lane_records.append(record)
                if not record.get("passed"):
                    break
            return lane_records

        with ThreadPoolExecutor(
            max_workers=len(_POST_REGRESSION_LANES),
            thread_name_prefix="handoff-lane",
        ) as executor:
            futures = [
                executor.submit(record_lane, lane) for lane in _POST_REGRESSION_LANES
            ]
            for future in futures:
                deferred_records.extend(future.result())

    deferred_by_id = {str(record["check_id"]): record for record in deferred_records}
    ordered_deferred = [
        deferred_by_id[check_id]
        for check_id in REQUIRED_HANDOFF_CHECK_IDS
        if check_id in deferred_by_id
    ]
    persist_handoff_records(
        repo_root=root,
        evidence_root=output_root,
        records=ordered_deferred,
        expected_branch=expected_branch,
        require_upstream=require_upstream,
        model_cache_dir=model_cache_dir,
        rag_cache_dir=rag_cache_dir,
        allow_external_evidence_root=allow_external_evidence_root,
        manifest_source_identity=manifest_source_identity,
    )
    completed.extend(str(record["check_id"]) for record in ordered_deferred)
    for record in ordered_deferred:
        if not record.get("passed"):
            return _failed_result(
                str(record["check_id"]),
                record=record,
                completed=completed,
            )

    for check_id in _FINAL_GATE_IDS:
        record = record_gate(check_id, defer_dossier_update=False)
        completed.append(check_id)
        if not record.get("passed"):
            return _failed_result(check_id, record=record, completed=completed)

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


def _validate_fixed_execution_plan(registered_ids: tuple[str, ...]) -> None:
    sequences = (
        _SERIAL_GATE_IDS,
        _DEFERRED_PREREQUISITE_IDS,
        *_POST_REGRESSION_LANES,
        _FINAL_GATE_IDS,
    )
    planned_ids = tuple(check_id for sequence in sequences for check_id in sequence)
    if len(planned_ids) != len(set(planned_ids)) or set(planned_ids) != set(
        registered_ids
    ):
        raise HandoffManifestError(
            "Fixed handoff execution plan drifted from the required gate registry."
        )
    registry_index = {check_id: index for index, check_id in enumerate(registered_ids)}
    for sequence in sequences:
        indexes = tuple(registry_index[check_id] for check_id in sequence)
        if indexes != tuple(sorted(indexes)):
            raise HandoffManifestError(
                "A fixed handoff lane drifted from registry order."
            )


def _failed_result(
    check_id: str,
    *,
    record: dict[str, Any],
    completed: list[str],
) -> dict[str, Any]:
    reason = str(record.get("failure_reason") or "gate did not pass")
    return {
        "ok": False,
        "reason": f"{check_id}: {reason}",
        "completed_check_ids": completed,
        "required_check_ids": list(REQUIRED_HANDOFF_CHECK_IDS),
        "dossier_verified": False,
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
