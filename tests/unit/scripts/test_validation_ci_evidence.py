from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from scripts.dev.pytest_completion_attestation import (
    SHARDED_PYTEST_RUNNER_ID,
    build_attestation,
    write_attestation,
)
from scripts.dev.validation_ci_evidence import (
    CiCapabilityStatus,
    CiOwnerReceipt,
    evaluate_ci_capability_receipts,
    record_ci_owner_success,
    verify_ci_native_owner_evidence,
)
from scripts.dev.validation_ci_plan import build_ci_validation_plan
from scripts.dev.validation_control_plane import (
    ChangeDescriptor,
    ChangeIntent,
    ClaimLevel,
    Layer,
    bind_validation_plan,
    plan_validation,
)
from scripts.dev.validation_gate_catalog import HANDOFF_VALIDATION_GATE_CATALOG


def test_ci_owner_runner_import_is_dependency_free() -> None:
    completed = subprocess.run(  # noqa: S603 - fixed interpreter import smoke.
        [
            sys.executable,
            "-S",
            "-c",
            "import scripts.dev.run_validation_ci_owner",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr


def _plans(source_sha: str = "a" * 40):
    plan = plan_validation(
        ChangeDescriptor(
            intent=ChangeIntent.BUG_FIX,
            claim_level=ClaimLevel.PRODUCT_PR,
            declared_layers=frozenset({Layer.BACKEND_DOMAIN}),
        ),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )
    plan = bind_validation_plan(
        plan,
        source_sha=source_sha,
        base_sha="b" * 40,
        target_sha="b" * 40,
    )
    return plan, build_ci_validation_plan(plan, source_sha=source_sha)


def _receipt(ci_plan, owner: str, *, source_sha: str = "a" * 40):
    gate_ids = ci_plan.gate_ids_for_owner(owner)
    execution_mode = (
        "ci-native-equivalent" if owner in {"plan", "product"} else "registry"
    )
    return CiOwnerReceipt(
        owner=owner,
        execution_mode=execution_mode,
        plan_digest=ci_plan.plan_digest,
        ci_plan_digest=ci_plan.digest(),
        source_sha=source_sha,
        head_tree_sha="b" * 40,
        completed_gate_ids=gate_ids,
        failed_gate_ids=(),
        evidence_digests=tuple((gate_id, "c" * 64) for gate_id in gate_ids),
        evidence_files=(
            (("build/fake-evidence.json", "d" * 64, 1),)
            if execution_mode == "ci-native-equivalent"
            else ()
        ),
    )


def test_ci_capability_verdict_requires_exact_owner_and_gate_coverage() -> None:
    plan, ci_plan = _plans()
    receipts = tuple(_receipt(ci_plan, owner) for owner in ci_plan.required_owners)

    unverified = evaluate_ci_capability_receipts(plan, ci_plan, receipts)
    verdict = evaluate_ci_capability_receipts(
        plan,
        ci_plan,
        receipts,
        evidence_verified_owner_ids=ci_plan.required_owners,
    )

    assert unverified.status is CiCapabilityStatus.BLOCKED
    assert "owner-evidence-not-verified" in unverified.reasons
    assert verdict.status is CiCapabilityStatus.PASSED
    assert verdict.reasons == ()


def test_ci_capability_verdict_blocks_missing_owner_or_source_replay() -> None:
    plan, ci_plan = _plans()
    receipts = tuple(_receipt(ci_plan, owner) for owner in ci_plan.required_owners)

    missing = evaluate_ci_capability_receipts(plan, ci_plan, receipts[:-1])
    replayed = evaluate_ci_capability_receipts(
        plan,
        ci_plan,
        (
            *receipts[:-1],
            _receipt(ci_plan, ci_plan.required_owners[-1], source_sha="d" * 40),
        ),
    )

    assert missing.status is CiCapabilityStatus.BLOCKED
    assert "missing-owner-receipt" in missing.reasons
    assert replayed.status is CiCapabilityStatus.BLOCKED
    assert "owner-source-sha-mismatch" in replayed.reasons


def test_ci_capability_verdict_fails_on_reported_gate_failure() -> None:
    plan, ci_plan = _plans()
    receipts = [_receipt(ci_plan, owner) for owner in ci_plan.required_owners]
    gate_id = receipts[0].completed_gate_ids[0]
    receipts[0] = CiOwnerReceipt(
        owner=receipts[0].owner,
        execution_mode=receipts[0].execution_mode,
        plan_digest=ci_plan.plan_digest,
        ci_plan_digest=ci_plan.digest(),
        source_sha="a" * 40,
        head_tree_sha=receipts[0].head_tree_sha,
        completed_gate_ids=receipts[0].completed_gate_ids,
        failed_gate_ids=(gate_id,),
        evidence_digests=receipts[0].evidence_digests,
        evidence_files=receipts[0].evidence_files,
    )

    verdict = evaluate_ci_capability_receipts(plan, ci_plan, receipts)

    assert verdict.status is CiCapabilityStatus.FAILED
    assert gate_id in verdict.failed_gate_ids


def _git(repo, *args: str) -> str:
    git = shutil.which("git")
    assert git is not None
    completed = subprocess.run(  # noqa: S603 - resolved git with test-owned args.
        [git, *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _clean_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / ".gitignore").write_text("build/\n", encoding="utf-8")
    (repo / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "initial")
    return repo, _git(repo, "rev-parse", "HEAD")


def _write_plan_evidence(repo, plan, ci_plan):
    evidence_root = repo / "build" / "ci-validation"
    evidence_root.mkdir(parents=True)
    (evidence_root / "git-diff-check.log").write_bytes(b"")
    (evidence_root / "validation-plan.json").write_text(
        plan.to_json() + "\n",
        encoding="utf-8",
    )
    (evidence_root / "ci-plan.json").write_text(
        ci_plan.to_json() + "\n",
        encoding="utf-8",
    )
    return (
        evidence_root / "git-diff-check.log",
        evidence_root / "validation-plan.json",
        evidence_root / "ci-plan.json",
    )


def test_owner_success_receipt_hashes_real_artifact_content(tmp_path) -> None:
    repo, source_sha = _clean_repo(tmp_path)
    plan, ci_plan = _plans(source_sha)
    evidence_paths = _write_plan_evidence(repo, plan, ci_plan)

    receipt = record_ci_owner_success(
        plan,
        ci_plan,
        owner="plan",
        evidence_paths=evidence_paths,
        repo_root=repo,
    )

    assert receipt.completed_gate_ids == ci_plan.gate_ids_for_owner("plan")
    assert {digest for _gate_id, digest in receipt.evidence_digests}
    assert CiOwnerReceipt.from_json(receipt.to_json()) == receipt


def test_ci_native_evidence_is_rehashed_and_rejects_stale_bytes(tmp_path) -> None:
    repo, source_sha = _clean_repo(tmp_path)
    plan, ci_plan = _plans(source_sha)
    evidence_paths = _write_plan_evidence(repo, plan, ci_plan)
    receipt = record_ci_owner_success(
        plan,
        ci_plan,
        owner="plan",
        evidence_paths=evidence_paths,
        repo_root=repo,
    )

    assert verify_ci_native_owner_evidence(
        receipt,
        plan=plan,
        ci_plan=ci_plan,
        repo_root=repo,
    ) == (True, "")

    artifact = repo / "build" / "ci-validation" / "validation-plan.json"
    artifact.write_text("edited\n", encoding="utf-8")
    assert verify_ci_native_owner_evidence(
        receipt,
        plan=plan,
        ci_plan=ci_plan,
        repo_root=repo,
    ) == (
        False,
        "CI plan evidence does not match the canonical plan",
    )


def test_ci_native_evidence_rejects_a_dirty_source_checkout(tmp_path) -> None:
    repo, source_sha = _clean_repo(tmp_path)
    plan, ci_plan = _plans(source_sha)
    evidence_paths = _write_plan_evidence(repo, plan, ci_plan)
    receipt = record_ci_owner_success(
        plan,
        ci_plan,
        owner="plan",
        evidence_paths=evidence_paths,
        repo_root=repo,
    )

    (repo / "source.py").write_text("VALUE = 2\n", encoding="utf-8")

    assert verify_ci_native_owner_evidence(
        receipt,
        plan=plan,
        ci_plan=ci_plan,
        repo_root=repo,
    ) == (
        False,
        "CI owner receipt requires a clean source checkout",
    )


def test_ci_native_record_rejects_arbitrary_owner_evidence(tmp_path) -> None:
    repo, source_sha = _clean_repo(tmp_path)
    plan, ci_plan = _plans(source_sha)
    arbitrary = repo / "build" / "pass.txt"
    arbitrary.parent.mkdir()
    arbitrary.write_text("passed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="evidence paths are not canonical"):
        record_ci_owner_success(
            plan,
            ci_plan,
            owner="plan",
            evidence_paths=(arbitrary,),
            repo_root=repo,
        )


def test_product_owner_requires_aggregate_attestation_and_coverage_schema(
    tmp_path,
) -> None:
    repo, source_sha = _clean_repo(tmp_path)
    plan, ci_plan = _plans(source_sha)
    evidence_root = repo / "build" / "ci-native-product"
    evidence_root.mkdir(parents=True)
    aggregate = evidence_root / "all-regression.json"
    coverage = evidence_root / "coverage.xml"
    write_attestation(
        aggregate,
        build_attestation(
            runner=SHARDED_PYTEST_RUNNER_ID,
            command_args=("all",),
            exit_code=0,
            counts={"collected": 1, "executed": 1, "passed": 1},
        ),
    )
    coverage.write_text('<coverage line-rate="0.5"/>\n', encoding="utf-8")

    receipt = record_ci_owner_success(
        plan,
        ci_plan,
        owner="product",
        evidence_paths=(aggregate, coverage),
        repo_root=repo,
    )

    assert receipt.completed_gate_ids == ("complete-regression",)
    coverage.write_text("not xml\n", encoding="utf-8")
    with pytest.raises(ValueError, match="coverage evidence is malformed"):
        record_ci_owner_success(
            plan,
            ci_plan,
            owner="product",
            evidence_paths=(aggregate, coverage),
            repo_root=repo,
        )
