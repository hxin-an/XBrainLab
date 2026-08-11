from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.dev.run_validation_control_plane import (
    ValidationExecutionError,
    collect_changed_paths,
    execute_validation_plan,
    main,
    resolve_comparison_base,
    verify_validation_evidence,
)
from scripts.dev.validation_control_plane import (
    ChangeDescriptor,
    ChangeIntent,
    ClaimLevel,
    ValidationReceipt,
    VerdictStatus,
    bind_validation_plan,
    evaluate_validation_receipt,
    plan_validation,
)
from scripts.dev.validation_gate_catalog import HANDOFF_VALIDATION_GATE_CATALOG


def _product_backend_plan():
    plan = plan_validation(
        ChangeDescriptor(
            intent=ChangeIntent.BUG_FIX,
            claim_level=ClaimLevel.PRODUCT_PR,
        ),
        ["XBrainLab/backend/utils/logger.py"],
        gate_catalog=HANDOFF_VALIDATION_GATE_CATALOG,
    )
    return bind_validation_plan(plan, source_sha="a" * 40, base_sha="b" * 40)


def _planned_paths(_root: Path, *, base_ref: str):
    assert base_ref == "b" * 40
    return ("XBrainLab/backend/utils/logger.py",)


def test_executor_uses_registry_commands_once_and_emits_complete_receipt(
    tmp_path: Path,
) -> None:
    plan = _product_backend_plan()
    calls: list[str] = []

    def recorder(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs["check_id"])
        return {
            "check_id": kwargs["check_id"],
            "passed": True,
            "return_code": 0,
        }

    receipt = execute_validation_plan(
        plan,
        repo_root=tmp_path,
        evidence_root=tmp_path / ("a" * 40),
        source_sha="a" * 40,
        expected_base_sha="b" * 40,
        expected_branch="refactor/validation-control-plane-v1",
        recorder=recorder,
        dossier_validator=lambda **_kwargs: (True, "ok"),
        changed_path_collector=_planned_paths,
    )

    registry_order = tuple(HANDOFF_VALIDATION_GATE_CATALOG)
    assert calls == sorted(calls, key=registry_order.index)
    assert len(calls) == len(set(calls))
    assert set(calls) == set(plan.execution_ids)
    assert receipt.completed_gate_ids == tuple(calls)
    assert set(receipt.completed_gate_ids) == set(plan.execution_ids)
    assert {gate_id for gate_id, _digest in receipt.evidence_digests} == set(calls)
    assert evaluate_validation_receipt(plan, receipt).status is VerdictStatus.PASSED


def test_executor_stops_on_failure_and_receipt_cannot_pass(tmp_path: Path) -> None:
    plan = _product_backend_plan()
    failing_gate = plan.execution_ids[1]

    def recorder(**kwargs):  # type: ignore[no-untyped-def]
        return {
            "check_id": kwargs["check_id"],
            "passed": kwargs["check_id"] != failing_gate,
            "return_code": 0 if kwargs["check_id"] != failing_gate else 1,
        }

    receipt = execute_validation_plan(
        plan,
        repo_root=tmp_path,
        evidence_root=tmp_path / ("a" * 40),
        source_sha="a" * 40,
        expected_base_sha="b" * 40,
        expected_branch="refactor/validation-control-plane-v1",
        recorder=recorder,
        dossier_validator=lambda **_kwargs: (True, "ok"),
        changed_path_collector=_planned_paths,
    )

    verdict = evaluate_validation_receipt(plan, receipt)
    assert receipt.failed_gate_ids == (failing_gate,)
    assert verdict.status is VerdictStatus.FAILED
    assert len(receipt.completed_gate_ids) < len(plan.execution_ids)


def test_executor_can_attest_an_explicit_partial_ci_owner_without_claiming_plan_pass(
    tmp_path: Path,
) -> None:
    plan = _product_backend_plan()
    selected = plan.execution_ids[:2]
    calls: list[str] = []

    receipt = execute_validation_plan(
        plan,
        repo_root=tmp_path,
        evidence_root=tmp_path / ("a" * 40),
        source_sha="a" * 40,
        expected_base_sha="b" * 40,
        expected_branch="",
        execution_gate_ids=selected,
        recorder=lambda **kwargs: (
            calls.append(kwargs["check_id"])
            or {"check_id": kwargs["check_id"], "passed": True}
        ),
        dossier_validator=lambda **_kwargs: (True, "ok"),
        changed_path_collector=_planned_paths,
    )

    assert tuple(calls) == selected
    assert receipt.completed_gate_ids == selected
    verdict = evaluate_validation_receipt(plan, receipt)
    assert verdict.status is VerdictStatus.BLOCKED
    assert "missing-selected-gates" in verdict.reasons


def test_partial_executor_rejects_unselected_or_duplicate_gate_ids(
    tmp_path: Path,
) -> None:
    plan = _product_backend_plan()
    common = {
        "repo_root": tmp_path,
        "evidence_root": tmp_path / ("a" * 40),
        "source_sha": "a" * 40,
        "expected_base_sha": "b" * 40,
        "expected_branch": "",
        "recorder": lambda **_kwargs: {},
        "dossier_validator": lambda **_kwargs: (True, "ok"),
        "changed_path_collector": _planned_paths,
    }

    with pytest.raises(ValidationExecutionError, match="not selected"):
        execute_validation_plan(
            plan,
            execution_gate_ids=("not-selected",),
            **common,
        )
    with pytest.raises(ValidationExecutionError, match="duplicate"):
        execute_validation_plan(
            plan,
            execution_gate_ids=(plan.execution_ids[0], plan.execution_ids[0]),
            **common,
        )


def test_executor_rejects_a_plan_edited_after_catalog_selection(tmp_path: Path) -> None:
    plan = _product_backend_plan()
    forged = replace(plan, executions=plan.executions[:-1])

    with pytest.raises(ValidationExecutionError, match=r"catalog|stale|edited"):
        execute_validation_plan(
            forged,
            repo_root=tmp_path,
            evidence_root=tmp_path / ("a" * 40),
            source_sha="a" * 40,
            expected_base_sha="b" * 40,
            expected_branch="refactor/validation-control-plane-v1",
            recorder=lambda **_kwargs: {},
            dossier_validator=lambda **_kwargs: (True, "ok"),
            changed_path_collector=_planned_paths,
        )


def test_executor_and_verifier_reject_unauthorized_target_merge_base(
    tmp_path: Path,
) -> None:
    plan = _product_backend_plan()

    with pytest.raises(ValidationExecutionError, match="authorized target merge base"):
        execute_validation_plan(
            plan,
            repo_root=tmp_path,
            evidence_root=tmp_path / ("a" * 40),
            source_sha="a" * 40,
            expected_base_sha="c" * 40,
            expected_branch="branch",
            recorder=lambda **_kwargs: {},
            dossier_validator=lambda **_kwargs: (True, "ok"),
            changed_path_collector=_planned_paths,
        )

    receipt = ValidationReceipt(
        plan_digest=plan.digest(),
        source_sha="a" * 40,
        completed_gate_ids=plan.execution_ids,
        evidence_digests=tuple((gate_id, "d" * 64) for gate_id in plan.execution_ids),
    )
    verdict = verify_validation_evidence(
        plan,
        receipt,
        repo_root=tmp_path,
        evidence_root=tmp_path / ("a" * 40),
        source_sha="a" * 40,
        expected_base_sha="c" * 40,
        expected_branch="branch",
        dossier_validator=lambda **_kwargs: (True, "ok"),
        changed_path_collector=_planned_paths,
    )

    assert verdict.status is VerdictStatus.BLOCKED
    assert "plan-target-base-mismatch" in verdict.reasons


def test_collect_changed_paths_unions_committed_staged_dirty_and_untracked() -> None:
    responses = {
        (
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACDMRTUXB",
            "origin/main...HEAD",
        ): ("XBrainLab/backend/a.py\ndocs/current.md\n"),
        ("diff", "--name-only", "--no-renames", "--diff-filter=ACDMRTUXB"): (
            "XBrainLab/backend/b.py\n"
        ),
        (
            "diff",
            "--cached",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACDMRTUXB",
        ): ("XBrainLab/backend/a.py\n"),
        ("ls-files", "--others", "--exclude-standard"): "tests/unit/test_new.py\n",
    }

    assert collect_changed_paths(
        Path("/repo"),
        base_ref="origin/main",
        git_runner=lambda _root, *args: responses[args],
    ) == (
        "XBrainLab/backend/a.py",
        "XBrainLab/backend/b.py",
        "docs/current.md",
        "tests/unit/test_new.py",
    )


def test_claim_bearing_plan_requires_an_authorized_immutable_target() -> None:
    descriptor = ChangeDescriptor(
        intent=ChangeIntent.BUG_FIX,
        claim_level=ClaimLevel.PRODUCT_PR,
    )
    calls: list[tuple[str, ...]] = []

    base = resolve_comparison_base(
        Path("/repo"),
        descriptor,
        base_ref="origin/main",
        authorized_target_sha="a" * 40,
        git_runner=lambda _root, *args: calls.append(args) or "a" * 40,
    )

    assert base == "a" * 40
    assert calls == [
        ("rev-parse", "origin/main"),
        ("merge-base", "HEAD", "a" * 40),
    ]
    with pytest.raises(ValidationExecutionError, match="authorized target SHA"):
        resolve_comparison_base(
            Path("/repo"),
            descriptor,
            base_ref="origin/main",
            git_runner=lambda _root, *args: "b" * 40,
        )
    with pytest.raises(ValidationExecutionError, match="does not match"):
        resolve_comparison_base(
            Path("/repo"),
            descriptor,
            base_ref="origin/main",
            authorized_target_sha="a" * 40,
            git_runner=lambda _root, *args: "b" * 40,
        )


def test_evidence_verifier_detects_record_tampering(tmp_path: Path) -> None:
    plan = _product_backend_plan()
    records = {
        gate_id: {"check_id": gate_id, "passed": True, "return_code": 0}
        for gate_id in plan.execution_ids
    }
    import hashlib
    import json

    evidence_digests = tuple(
        (
            gate_id,
            hashlib.sha256(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
        )
        for gate_id, record in records.items()
    )
    receipt = execute_validation_plan(
        plan,
        repo_root=tmp_path,
        evidence_root=tmp_path / ("a" * 40),
        source_sha="a" * 40,
        expected_base_sha="b" * 40,
        expected_branch="refactor/validation-control-plane-v1",
        recorder=lambda **kwargs: records[kwargs["check_id"]],
        dossier_validator=lambda **_kwargs: (True, "ok"),
        changed_path_collector=_planned_paths,
    )
    assert receipt.evidence_digests == tuple(sorted(evidence_digests))
    evidence_root = tmp_path / ("a" * 40)
    evidence_root.mkdir()
    dossier = {
        "checkout": {"commit_sha": "a" * 40},
        "checks": records,
    }
    (evidence_root / "handoff-evidence.json").write_text(
        json.dumps(dossier), encoding="utf-8"
    )

    passed = verify_validation_evidence(
        plan,
        receipt,
        repo_root=tmp_path,
        evidence_root=evidence_root,
        source_sha="a" * 40,
        expected_base_sha="b" * 40,
        expected_branch="refactor/validation-control-plane-v1",
        dossier_validator=lambda **_kwargs: (True, "ok"),
        changed_path_collector=_planned_paths,
    )
    assert passed.status is VerdictStatus.PASSED

    dossier["checks"][plan.execution_ids[0]]["return_code"] = 9
    (evidence_root / "handoff-evidence.json").write_text(
        json.dumps(dossier), encoding="utf-8"
    )
    tampered = verify_validation_evidence(
        plan,
        receipt,
        repo_root=tmp_path,
        evidence_root=evidence_root,
        source_sha="a" * 40,
        expected_base_sha="b" * 40,
        expected_branch="refactor/validation-control-plane-v1",
        dossier_validator=lambda **_kwargs: (True, "ok"),
        changed_path_collector=_planned_paths,
    )
    assert tampered.status is VerdictStatus.BLOCKED
    assert "evidence-digest-mismatch" in tampered.reasons


def test_executor_rejects_source_or_diff_that_changed_after_planning(
    tmp_path: Path,
) -> None:
    plan = _product_backend_plan()

    with pytest.raises(ValidationExecutionError, match="source SHA"):
        execute_validation_plan(
            plan,
            repo_root=tmp_path,
            evidence_root=tmp_path / ("c" * 40),
            source_sha="c" * 40,
            expected_base_sha="b" * 40,
            expected_branch="branch",
            recorder=lambda **_kwargs: {},
            dossier_validator=lambda **_kwargs: (True, "ok"),
            changed_path_collector=_planned_paths,
        )

    with pytest.raises(ValidationExecutionError, match="changed paths"):
        execute_validation_plan(
            plan,
            repo_root=tmp_path,
            evidence_root=tmp_path / ("a" * 40),
            source_sha="a" * 40,
            expected_base_sha="b" * 40,
            expected_branch="branch",
            recorder=lambda **_kwargs: {},
            dossier_validator=lambda **_kwargs: (True, "ok"),
            changed_path_collector=lambda _root, *, base_ref: (
                "XBrainLab/backend/utils/logger.py",
                "XBrainLab/llm/core/model_catalog.py",
            ),
        )


def test_report_never_promotes_structural_receipt_to_verified_pass(
    tmp_path: Path,
    capsys,
) -> None:
    plan = _product_backend_plan()
    receipt = ValidationReceipt(
        plan_digest=plan.digest(),
        source_sha="a" * 40,
        completed_gate_ids=plan.execution_ids,
        evidence_digests=tuple((gate_id, "c" * 64) for gate_id in plan.execution_ids),
    )
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "receipt.json"
    plan_path.write_text(plan.to_json(), encoding="utf-8")
    receipt_path.write_text(receipt.to_json(), encoding="utf-8")

    exit_code = main(
        [
            "report",
            "--plan",
            str(plan_path),
            "--receipt",
            str(receipt_path),
        ]
    )

    assert exit_code == 1
    assert "dossier-verification-not-performed" in capsys.readouterr().out
