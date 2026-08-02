from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

import scripts.dev.run_handoff_validation_manifest as runner
from scripts.dev.handoff_gate_spec import GateSpec


def test_runner_records_every_required_gate_in_registry_order_then_verifies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = (
        GateSpec(
            check_id="first-gate",
            section="1",
            argv=("python", "-c", "print('first')"),
            timeout_seconds=10,
        ),
        GateSpec(
            check_id="second-gate",
            section="2",
            argv=("python", "-c", "print('second')"),
            timeout_seconds=20,
        ),
    )
    monkeypatch.setattr(
        runner,
        "HANDOFF_GATE_SPECS",
        MappingProxyType({spec.check_id: spec for spec in specs}),
    )
    monkeypatch.setattr(
        runner,
        "REQUIRED_HANDOFF_CHECK_IDS",
        tuple(spec.check_id for spec in specs),
    )
    recorded: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []

    def fake_record(**kwargs: Any) -> dict[str, Any]:
        recorded.append(kwargs)
        return {"check_id": kwargs["check_id"], "passed": True}

    def fake_verify(**kwargs: Any) -> tuple[bool, str]:
        verified.append(kwargs)
        return True, ""

    monkeypatch.setattr(runner, "record_handoff_command", fake_record)
    monkeypatch.setattr(runner, "validate_handoff_dossier", fake_verify)
    evidence_root = tmp_path / "external" / ("a" * 40)

    result = runner.run_handoff_manifest(
        repo_root=tmp_path,
        evidence_root=evidence_root,
        model_cache_dir=Path("/mnt/d/XBrainLabCache/models"),
        rag_cache_dir=Path("/mnt/d/XBrainLabCache/rag"),
        expected_branch="test-branch",
        require_upstream=False,
        allow_external_evidence_root=True,
    )

    assert [item["check_id"] for item in recorded] == [
        "first-gate",
        "second-gate",
    ]
    assert recorded[0]["command"] == specs[0].resolve_argv(evidence_root)
    assert recorded[1]["timeout_seconds"] == 20
    assert verified[0]["required_check_ids"] == ("first-gate", "second-gate")
    assert result == {
        "ok": True,
        "reason": "",
        "completed_check_ids": ["first-gate", "second-gate"],
        "required_check_ids": ["first-gate", "second-gate"],
        "dossier_verified": True,
    }


def test_runner_fails_closed_before_verification_when_a_gate_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = GateSpec(
        check_id="failing-gate",
        section="1",
        argv=("python", "-c", "raise SystemExit(1)"),
        timeout_seconds=10,
    )
    monkeypatch.setattr(
        runner,
        "HANDOFF_GATE_SPECS",
        MappingProxyType({spec.check_id: spec}),
    )
    monkeypatch.setattr(runner, "REQUIRED_HANDOFF_CHECK_IDS", (spec.check_id,))
    monkeypatch.setattr(
        runner,
        "record_handoff_command",
        lambda **_kwargs: {
            "check_id": spec.check_id,
            "passed": False,
            "failure_reason": "command failed",
        },
    )
    verified = False

    def fake_verify(**_kwargs: Any) -> tuple[bool, str]:
        nonlocal verified
        verified = True
        return True, ""

    monkeypatch.setattr(runner, "validate_handoff_dossier", fake_verify)

    result = runner.run_handoff_manifest(
        repo_root=tmp_path,
        evidence_root=tmp_path / "external" / ("b" * 40),
        model_cache_dir=Path("/mnt/d/XBrainLabCache/models"),
        rag_cache_dir=Path("/mnt/d/XBrainLabCache/rag"),
        expected_branch="test-branch",
        require_upstream=False,
        allow_external_evidence_root=True,
    )

    assert verified is False
    assert result["ok"] is False
    assert result["completed_check_ids"] == ["failing-gate"]
    assert result["dossier_verified"] is False
    assert result["reason"] == "failing-gate: command failed"


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
        )
