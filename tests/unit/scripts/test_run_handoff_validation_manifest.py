from __future__ import annotations

from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

import scripts.dev.run_handoff_validation_manifest as runner
from scripts.dev.handoff_gate_spec import GateSpec
from scripts.dev.validation_control_plane import VerdictStatus


def _install_registry(
    monkeypatch: pytest.MonkeyPatch,
    *gate_ids: str,
) -> None:
    specs = tuple(
        GateSpec(
            check_id=gate_id,
            section=str(index + 1),
            argv=("python", "-c", f"print({gate_id!r})"),
            timeout_seconds=10,
        )
        for index, gate_id in enumerate(gate_ids)
    )
    monkeypatch.setattr(
        runner,
        "HANDOFF_GATE_SPECS",
        MappingProxyType({spec.check_id: spec for spec in specs}),
    )
    monkeypatch.setattr(runner, "REQUIRED_HANDOFF_CHECK_IDS", gate_ids)


def test_compatibility_runner_delegates_to_plan_execute_and_verify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate_ids = ("first-gate", "second-gate")
    _install_registry(monkeypatch, *gate_ids)
    plan = SimpleNamespace(
        execution_ids=gate_ids,
        source_sha="a" * 40,
        base_sha="b" * 40,
        to_json=lambda: '{"plan":true}',
        digest=lambda: "c" * 64,
    )
    receipt = SimpleNamespace(
        completed_gate_ids=gate_ids,
        to_json=lambda: '{"receipt":true}',
        digest=lambda: "d" * 64,
    )
    execute_calls: list[dict[str, object]] = []
    verify_calls: list[dict[str, object]] = []
    monkeypatch.setattr(runner, "_build_handoff_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(
        runner,
        "execute_validation_plan",
        lambda *_args, **kwargs: execute_calls.append(kwargs) or receipt,
    )
    monkeypatch.setattr(
        runner,
        "verify_validation_evidence",
        lambda *_args, **kwargs: verify_calls.append(kwargs)
        or SimpleNamespace(status=VerdictStatus.PASSED, reasons=()),
    )
    evidence_root = tmp_path / "external" / ("a" * 40)

    result = runner.run_handoff_manifest(
        repo_root=tmp_path,
        evidence_root=evidence_root,
        model_cache_dir=Path("/mnt/d/XBrainLabCache/models"),
        rag_cache_dir=Path("/mnt/d/XBrainLabCache/rag"),
        expected_branch="test-branch",
        require_upstream=False,
        allow_external_evidence_root=True,
        target_sha="b" * 40,
    )

    assert execute_calls[0]["expected_base_sha"] == "b" * 40
    assert verify_calls[0]["expected_base_sha"] == "b" * 40
    assert (evidence_root / "validation-plan.json").is_file()
    assert (evidence_root / "validation-receipt.json").is_file()
    assert result == {
        "ok": True,
        "reason": "",
        "completed_check_ids": ["first-gate", "second-gate"],
        "required_check_ids": ["first-gate", "second-gate"],
        "dossier_verified": True,
        "plan_digest": "c" * 64,
        "receipt_digest": "d" * 64,
        "verdict_status": "passed",
    }


def test_compatibility_runner_preserves_failed_verdict_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate_ids = ("failing-gate",)
    _install_registry(monkeypatch, *gate_ids)
    plan = SimpleNamespace(
        execution_ids=gate_ids,
        source_sha="a" * 40,
        base_sha="b" * 40,
        to_json=lambda: "{}",
        digest=lambda: "c" * 64,
    )
    receipt = SimpleNamespace(
        completed_gate_ids=gate_ids,
        to_json=lambda: "{}",
        digest=lambda: "d" * 64,
    )
    monkeypatch.setattr(runner, "_build_handoff_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(
        runner, "execute_validation_plan", lambda *_args, **_kwargs: receipt
    )
    monkeypatch.setattr(
        runner,
        "verify_validation_evidence",
        lambda *_args, **_kwargs: SimpleNamespace(
            status=VerdictStatus.FAILED,
            reasons=("gate-failure",),
        ),
    )

    result = runner.run_handoff_manifest(
        repo_root=tmp_path,
        evidence_root=tmp_path / "external" / ("b" * 40),
        model_cache_dir=Path("/mnt/d/XBrainLabCache/models"),
        rag_cache_dir=Path("/mnt/d/XBrainLabCache/rag"),
        expected_branch="test-branch",
        require_upstream=False,
        allow_external_evidence_root=True,
        target_sha="b" * 40,
    )

    assert result["ok"] is False
    assert result["completed_check_ids"] == ["failing-gate"]
    assert result["dossier_verified"] is False
    assert result["reason"] == "gate-failure"
    assert result["verdict_status"] == "failed"


def test_runner_rejects_registry_required_id_drift(monkeypatch) -> None:
    spec = GateSpec(
        check_id="registered-gate",
        section="1",
        argv=("python", "-c", "print('ok')"),
        timeout_seconds=10,
    )
    monkeypatch.setattr(
        runner,
        "HANDOFF_GATE_SPECS",
        MappingProxyType({spec.check_id: spec}),
    )
    monkeypatch.setattr(runner, "REQUIRED_HANDOFF_CHECK_IDS", ("missing-gate",))

    with pytest.raises(runner.HandoffManifestError, match="registry drift"):
        runner.run_handoff_manifest(
            repo_root=Path("/tmp/repo"),
            evidence_root=Path("/tmp/evidence") / ("c" * 40),
            model_cache_dir=Path("/mnt/d/XBrainLabCache/models"),
            rag_cache_dir=Path("/mnt/d/XBrainLabCache/rag"),
            expected_branch="test-branch",
            require_upstream=False,
            allow_external_evidence_root=True,
            target_sha="b" * 40,
        )


def test_compatibility_cli_requires_explicit_candidate_branch_and_target() -> None:
    parser = runner._build_parser()
    common = [
        "--model-cache-dir",
        "/mnt/d/XBrainLabCache/models",
        "--rag-cache-dir",
        "/mnt/d/XBrainLabCache/rag",
        "--target-sha",
        "b" * 40,
    ]

    with pytest.raises(SystemExit):
        parser.parse_args(common)
    parsed = parser.parse_args([*common, "--expected-branch", "task/validation"])
    assert parsed.expected_branch == "task/validation"
