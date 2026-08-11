"""Fail-closed CI capability receipts distinct from product claim verdicts."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from xml.etree import ElementTree

from scripts.dev.ci_gate_ownership import (
    CI_NATIVE_OWNER_EVIDENCE_PATHS,
    CI_NATIVE_OWNER_GATE_IDS,
    CI_OWNER_EXECUTION_MODES,
)
from scripts.dev.pytest_completion_attestation import (
    SHARDED_PYTEST_RUNNER_ID,
    validate_attestation,
)
from scripts.dev.validation_ci_plan import CiValidationPlan, build_ci_validation_plan
from scripts.dev.validation_control_plane import ValidationPlan

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_MAX_COVERAGE_XML_BYTES = 64 * 1024 * 1024
_CI_SOURCE_EXCLUDES = (
    ":(exclude,glob)artifacts/**",
    ":(exclude,glob)build/**",
    ":(exclude,literal)coverage.xml",
    ":(exclude,literal)settings.json",
    ":(exclude,glob).pytest_cache/**",
    ":(exclude,glob).mypy_cache/**",
    ":(exclude,glob).ruff_cache/**",
    ":(exclude,glob)XBrainLab/llm/core/models/**",
)


class CiCapabilityStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


def _stable_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


@dataclass(frozen=True, slots=True)
class CiOwnerReceipt:
    """Attestation emitted by exactly one CI execution owner."""

    owner: str
    execution_mode: str
    plan_digest: str
    ci_plan_digest: str
    source_sha: str
    head_tree_sha: str
    completed_gate_ids: tuple[str, ...]
    failed_gate_ids: tuple[str, ...]
    evidence_digests: tuple[tuple[str, str], ...]
    evidence_files: tuple[tuple[str, str, int], ...] = ()

    def __post_init__(self) -> None:
        if not self.owner:
            raise ValueError("CI owner receipt requires an owner")
        if CI_OWNER_EXECUTION_MODES.get(self.owner) != self.execution_mode:
            raise ValueError("CI owner receipt execution mode is not authoritative")
        if not _SHA256.fullmatch(self.plan_digest):
            raise ValueError("CI owner receipt plan digest must be SHA-256")
        if not _SHA256.fullmatch(self.ci_plan_digest):
            raise ValueError("CI owner receipt CI-plan digest must be SHA-256")
        if not _GIT_SHA.fullmatch(self.source_sha):
            raise ValueError("CI owner receipt source SHA must be a Git hash")
        if not _GIT_SHA.fullmatch(self.head_tree_sha):
            raise ValueError("CI owner receipt tree SHA must be a Git hash")
        if len(self.completed_gate_ids) != len(set(self.completed_gate_ids)):
            raise ValueError("CI owner receipt repeats completed gates")
        if not set(self.failed_gate_ids) <= set(self.completed_gate_ids):
            raise ValueError("CI owner failed gates must be completed")
        evidence = dict(self.evidence_digests)
        if len(evidence) != len(self.evidence_digests):
            raise ValueError("CI owner receipt repeats evidence gates")
        if set(evidence) != set(self.completed_gate_ids):
            raise ValueError("CI owner evidence must cover completed gates exactly")
        if any(not _SHA256.fullmatch(digest) for digest in evidence.values()):
            raise ValueError("CI owner evidence digest must be SHA-256")
        evidence_paths: set[str] = set()
        for relative_path, digest, byte_size in self.evidence_files:
            path = Path(relative_path)
            if (
                path.is_absolute()
                or not path.parts
                or ".." in path.parts
                or relative_path in evidence_paths
            ):
                raise ValueError("CI owner evidence file path is unsafe or repeated")
            if not _SHA256.fullmatch(digest) or byte_size < 0:
                raise ValueError("CI owner evidence file identity is invalid")
            evidence_paths.add(relative_path)
        if self.execution_mode == "ci-native-equivalent" and not self.evidence_files:
            raise ValueError("CI-native owner receipt requires evidence files")
        if self.execution_mode == "registry" and self.evidence_files:
            raise ValueError("Registry owner receipt cannot substitute file evidence")

    def to_json(self) -> str:
        return _stable_json(
            {
                "schema_version": 1,
                "owner": self.owner,
                "execution_mode": self.execution_mode,
                "plan_digest": self.plan_digest,
                "ci_plan_digest": self.ci_plan_digest,
                "source_sha": self.source_sha,
                "head_tree_sha": self.head_tree_sha,
                "completed_gate_ids": list(self.completed_gate_ids),
                "failed_gate_ids": list(self.failed_gate_ids),
                "evidence_digests": [list(item) for item in self.evidence_digests],
                "evidence_files": [list(item) for item in self.evidence_files],
            }
        )

    @classmethod
    def from_json(cls, value: str) -> CiOwnerReceipt:
        payload = json.loads(value)
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported CI owner receipt schema version")
        return cls(
            owner=str(payload["owner"]),
            execution_mode=str(payload["execution_mode"]),
            plan_digest=str(payload["plan_digest"]),
            ci_plan_digest=str(payload["ci_plan_digest"]),
            source_sha=str(payload["source_sha"]),
            head_tree_sha=str(payload["head_tree_sha"]),
            completed_gate_ids=tuple(map(str, payload["completed_gate_ids"])),
            failed_gate_ids=tuple(map(str, payload["failed_gate_ids"])),
            evidence_digests=tuple(
                (str(item[0]), str(item[1])) for item in payload["evidence_digests"]
            ),
            evidence_files=tuple(
                (str(item[0]), str(item[1]), int(item[2]))
                for item in payload["evidence_files"]
            ),
        )


@dataclass(frozen=True, slots=True)
class CiCapabilityVerdict:
    """Verdict over CI automation only; never a handoff or product verdict."""

    status: CiCapabilityStatus
    plan_digest: str
    source_sha: str
    missing_owners: tuple[str, ...] = ()
    failed_gate_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def to_json(self) -> str:
        return _stable_json(
            {
                "schema_version": 1,
                "status": self.status.value,
                "scope": "ci-capabilities-only",
                "plan_digest": self.plan_digest,
                "source_sha": self.source_sha,
                "missing_owners": list(self.missing_owners),
                "failed_gate_ids": list(self.failed_gate_ids),
                "reasons": list(self.reasons),
            }
        )


def _path_evidence(
    paths: Iterable[Path],
    *,
    repo_root: Path,
) -> tuple[str, tuple[tuple[str, str, int], ...]]:
    root = repo_root.expanduser().resolve(strict=True)
    records: dict[str, tuple[str, str, int]] = {}
    for supplied in sorted(
        (path.expanduser().resolve(strict=True) for path in paths),
        key=str,
    ):
        files = (
            tuple(sorted(path for path in supplied.rglob("*") if path.is_file()))
            if supplied.is_dir()
            else (supplied,)
        )
        for path in files:
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError as error:
                raise ValueError(
                    "CI owner evidence must remain inside repo root"
                ) from error
            content = path.read_bytes()
            record = (relative, hashlib.sha256(content).hexdigest(), len(content))
            if relative in records:
                raise ValueError("CI owner evidence file is repeated")
            records[relative] = record
    if not records:
        raise ValueError("CI owner receipt requires non-empty evidence")
    ordered = tuple(records[path] for path in sorted(records))
    digest = hashlib.sha256(_stable_json(ordered).encode("utf-8")).hexdigest()
    return digest, ordered


def collect_clean_ci_source_identity(repo_root: Path) -> tuple[str, str]:
    """Return commit/tree identity only when the CI checkout has no source edits."""

    root = repo_root.expanduser().resolve(strict=True)
    git = shutil.which("git")
    if git is None:
        raise ValueError("git executable is unavailable")

    def query(*args: str) -> str:
        completed = subprocess.run(  # noqa: S603 - resolved git, fixed queries.
            [git, *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            raise ValueError("CI owner source identity query failed")
        return completed.stdout.strip()

    source_sha = query("rev-parse", "HEAD")
    head_tree_sha = query("rev-parse", "HEAD^{tree}")
    if query(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        ":(glob)**",
        *_CI_SOURCE_EXCLUDES,
    ):
        raise ValueError("CI owner receipt requires a clean source checkout")
    return source_sha, head_tree_sha


def record_ci_owner_success(
    plan: ValidationPlan,
    ci_plan: CiValidationPlan,
    *,
    owner: str,
    evidence_paths: Iterable[Path],
    repo_root: Path,
) -> CiOwnerReceipt:
    """Attest a successful source-controlled CI-native execution owner."""

    if ci_plan.plan_digest != plan.digest():
        raise ValueError("CI plan digest differs from the validation plan")
    if plan.source_sha is None or ci_plan.source_sha != plan.source_sha:
        raise ValueError("CI plan source differs from the validation plan")
    gate_ids = ci_plan.gate_ids_for_owner(owner)
    if not gate_ids or owner not in ci_plan.required_owners:
        raise ValueError(f"CI owner {owner!r} is not selected")
    execution_mode = CI_OWNER_EXECUTION_MODES.get(owner)
    if execution_mode != "ci-native-equivalent":
        raise ValueError(f"CI owner {owner!r} requires registry execution")
    if gate_ids != CI_NATIVE_OWNER_GATE_IDS.get(owner):
        raise ValueError(f"CI-native owner {owner!r} gate contract is stale")
    source_sha, head_tree_sha = collect_clean_ci_source_identity(repo_root)
    if source_sha != ci_plan.source_sha:
        raise ValueError("CI owner evidence source differs from CI plan")
    digest, evidence_files = _path_evidence(evidence_paths, repo_root=repo_root)
    expected_paths = CI_NATIVE_OWNER_EVIDENCE_PATHS.get(owner)
    actual_paths = tuple(record[0] for record in evidence_files)
    if actual_paths != expected_paths:
        raise ValueError(f"CI-native owner {owner!r} evidence paths are not canonical")
    _validate_ci_native_evidence_schema(
        owner,
        plan=plan,
        ci_plan=ci_plan,
        repo_root=repo_root,
    )
    return CiOwnerReceipt(
        owner=owner,
        execution_mode=execution_mode,
        plan_digest=ci_plan.plan_digest,
        ci_plan_digest=ci_plan.digest(),
        source_sha=ci_plan.source_sha,
        head_tree_sha=head_tree_sha,
        completed_gate_ids=gate_ids,
        failed_gate_ids=(),
        evidence_digests=tuple((gate_id, digest) for gate_id in gate_ids),
        evidence_files=evidence_files,
    )


def verify_ci_native_owner_evidence(
    receipt: CiOwnerReceipt,
    *,
    plan: ValidationPlan,
    ci_plan: CiValidationPlan,
    repo_root: Path,
) -> tuple[bool, str]:
    """Re-hash downloaded CI-native artifacts against one owner receipt."""

    if receipt.execution_mode != "ci-native-equivalent":
        return False, "owner-is-not-ci-native"
    source_ok, source_reason = verify_ci_owner_source_identity(
        receipt,
        repo_root=repo_root,
    )
    if not source_ok:
        return False, source_reason
    if receipt.completed_gate_ids != CI_NATIVE_OWNER_GATE_IDS.get(receipt.owner):
        return False, "native-owner-gate-contract-mismatch"
    if tuple(record[0] for record in receipt.evidence_files) != (
        CI_NATIVE_OWNER_EVIDENCE_PATHS.get(receipt.owner)
    ):
        return False, "native-owner-evidence-path-mismatch"
    try:
        _validate_ci_native_evidence_schema(
            receipt.owner,
            plan=plan,
            ci_plan=ci_plan,
            repo_root=repo_root,
        )
    except (OSError, ValueError) as error:
        return False, str(error)
    root = repo_root.expanduser().resolve(strict=True)
    records: list[tuple[str, str, int]] = []
    for relative_path, expected_digest, expected_size in receipt.evidence_files:
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
            return False, f"evidence-file-missing:{relative_path}"
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != expected_digest or len(content) != expected_size:
            return False, f"evidence-file-stale:{relative_path}"
        records.append((relative_path, digest, len(content)))
    aggregate = hashlib.sha256(_stable_json(tuple(records)).encode("utf-8")).hexdigest()
    if set(dict(receipt.evidence_digests).values()) != {aggregate}:
        return False, "evidence-aggregate-digest-mismatch"
    return True, ""


def _validate_ci_native_evidence_schema(
    owner: str,
    *,
    plan: ValidationPlan,
    ci_plan: CiValidationPlan,
    repo_root: Path,
) -> None:
    root = repo_root.expanduser().resolve(strict=True)
    if owner == "plan":
        diff_log = root / "build/ci-validation/git-diff-check.log"
        plan_path = root / "build/ci-validation/validation-plan.json"
        ci_plan_path = root / "build/ci-validation/ci-plan.json"
        if diff_log.read_bytes():
            raise ValueError("CI plan diff-check evidence must be empty on success")
        if plan_path.read_text(encoding="utf-8").strip() != plan.to_json():
            raise ValueError("CI plan evidence does not match the canonical plan")
        if ci_plan_path.read_text(encoding="utf-8").strip() != ci_plan.to_json():
            raise ValueError("CI plan evidence does not match the canonical CI plan")
        return
    if owner != "product":
        raise ValueError(f"unsupported CI-native owner: {owner!r}")

    aggregate_path = root / "build/ci-native-product/all-regression.json"
    attestation, failure = validate_attestation(
        aggregate_path,
        expected_runner=SHARDED_PYTEST_RUNNER_ID,
        expected_args=("all",),
        expected_exit_code=0,
    )
    if failure is not None or attestation is None:
        raise ValueError(f"CI product aggregate evidence is invalid: {failure}")
    counts = attestation["counts"]
    forbidden = ("failed", "errors", "xfailed", "xpassed", "deselected")
    if counts["executed"] <= 0 or any(counts[name] for name in forbidden):
        raise ValueError("CI product aggregate evidence contains incomplete outcomes")

    coverage_path = root / "build/ci-native-product/coverage.xml"
    try:
        coverage_size = coverage_path.stat().st_size
    except OSError as error:
        raise ValueError("CI product coverage evidence is malformed") from error
    if coverage_size > _MAX_COVERAGE_XML_BYTES:
        raise ValueError("CI product coverage evidence exceeds the size limit")
    try:
        coverage_root = ElementTree.parse(coverage_path).getroot()  # noqa: S314
        line_rate = float(coverage_root.attrib["line-rate"])
    except (ElementTree.ParseError, KeyError, OSError, ValueError) as error:
        raise ValueError("CI product coverage evidence is malformed") from error
    if coverage_root.tag != "coverage" or not 0.0 <= line_rate <= 1.0:
        raise ValueError("CI product coverage evidence is invalid")


def verify_ci_owner_source_identity(
    receipt: CiOwnerReceipt,
    *,
    repo_root: Path,
) -> tuple[bool, str]:
    """Compare one receipt to the final verifier's clean exact checkout."""

    try:
        source_sha, head_tree_sha = collect_clean_ci_source_identity(repo_root)
    except (OSError, ValueError) as error:
        return False, str(error)
    if source_sha != receipt.source_sha:
        return False, "source-sha-mismatch"
    if head_tree_sha != receipt.head_tree_sha:
        return False, "source-tree-mismatch"
    return True, ""


def evaluate_ci_capability_receipts(
    plan: ValidationPlan,
    ci_plan: CiValidationPlan,
    receipts: Iterable[CiOwnerReceipt],
    *,
    evidence_verified_owner_ids: Iterable[str] = (),
) -> CiCapabilityVerdict:
    """Require one exact receipt for every selected CI execution owner."""

    receipt_list = tuple(receipts)
    by_owner = {receipt.owner: receipt for receipt in receipt_list}
    reasons: set[str] = set()
    try:
        canonical_ci_plan = build_ci_validation_plan(
            plan,
            source_sha=ci_plan.source_sha,
        )
    except ValueError:
        canonical_ci_plan = None
    if canonical_ci_plan != ci_plan:
        reasons.add("ci-plan-not-canonical")
    if len(by_owner) != len(receipt_list):
        reasons.add("duplicate-owner-receipt")
    if ci_plan.plan_digest != plan.digest():
        reasons.add("ci-plan-digest-mismatch")
    if ci_plan.selected_gate_ids != plan.execution_ids:
        reasons.add("ci-plan-gate-selection-mismatch")
    if plan.source_sha is None or ci_plan.source_sha != plan.source_sha:
        reasons.add("ci-plan-source-sha-mismatch")
    expected_owners = set(ci_plan.required_owners)
    verified_owners = set(evidence_verified_owner_ids)
    if verified_owners != expected_owners:
        reasons.add("owner-evidence-not-verified")
    missing_owners = tuple(sorted(expected_owners.difference(by_owner)))
    extra_owners = set(by_owner).difference(expected_owners)
    if missing_owners:
        reasons.add("missing-owner-receipt")
    if extra_owners:
        reasons.add("unselected-owner-receipt")

    failed: set[str] = set()
    for owner, receipt in by_owner.items():
        expected_gates = ci_plan.gate_ids_for_owner(owner)
        if receipt.plan_digest != ci_plan.plan_digest:
            reasons.add("owner-plan-digest-mismatch")
        if receipt.ci_plan_digest != ci_plan.digest():
            reasons.add("owner-ci-plan-digest-mismatch")
        if receipt.source_sha != ci_plan.source_sha:
            reasons.add("owner-source-sha-mismatch")
        if receipt.completed_gate_ids != expected_gates:
            reasons.add("owner-gate-coverage-mismatch")
        failed.update(receipt.failed_gate_ids)

    if failed:
        status = CiCapabilityStatus.FAILED
        reasons.add("ci-gate-failure")
    elif reasons:
        status = CiCapabilityStatus.BLOCKED
    else:
        status = CiCapabilityStatus.PASSED
    return CiCapabilityVerdict(
        status=status,
        plan_digest=plan.digest(),
        source_sha=ci_plan.source_sha,
        missing_owners=missing_owners,
        failed_gate_ids=tuple(sorted(failed)),
        reasons=tuple(sorted(reasons)),
    )
