from __future__ import annotations

from pathlib import Path
from threading import Barrier
from types import MappingProxyType
from typing import Any

import pytest

import scripts.dev.run_handoff_validation_manifest as runner
from scripts.dev.handoff_gate_spec import GateSpec


def _install_serial_plan(
    monkeypatch: pytest.MonkeyPatch,
    *check_ids: str,
) -> None:
    monkeypatch.setattr(runner, "_SERIAL_GATE_IDS", tuple(check_ids))
    monkeypatch.setattr(runner, "_DEFERRED_PREREQUISITE_IDS", ())
    monkeypatch.setattr(runner, "_POST_REGRESSION_LANES", ())
    monkeypatch.setattr(runner, "_FINAL_GATE_IDS", ())
    monkeypatch.setattr(
        runner,
        "handoff_profile_check_ids",
        lambda profile: tuple(check_ids)
        if profile == "handoff"
        else (_ for _ in ()).throw(ValueError("unsupported test profile")),
    )


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
    _install_serial_plan(monkeypatch, *(spec.check_id for spec in specs))
    source_identity = {"source_digest": "a" * 64, "dirty": False}
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
    monkeypatch.setattr(
        runner,
        "collect_source_identity",
        lambda *_args, **_kwargs: source_identity,
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
    )

    assert [item["check_id"] for item in recorded] == [
        "first-gate",
        "second-gate",
    ]
    assert recorded[0]["command"] == specs[0].resolve_argv(evidence_root)
    assert recorded[1]["timeout_seconds"] == 20
    assert recorded[0]["manifest_source_identity"] == source_identity
    assert recorded[1]["manifest_source_identity"] == source_identity
    assert verified[0]["required_check_ids"] == ("first-gate", "second-gate")
    assert result == {
        "ok": True,
        "reason": "",
        "completed_check_ids": ["first-gate", "second-gate"],
        "required_check_ids": ["first-gate", "second-gate"],
        "release_profile": "handoff",
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
    _install_serial_plan(monkeypatch, spec.check_id)
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
    monkeypatch.setattr(
        runner,
        "collect_source_identity",
        lambda *_args, **_kwargs: {
            "source_digest": "b" * 64,
            "dirty": False,
        },
    )

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
    _install_serial_plan(monkeypatch, "registered-gate")

    monkeypatch.setattr(
        runner,
        "handoff_profile_check_ids",
        lambda _profile: ("missing-gate",),
    )
    with pytest.raises(runner.HandoffManifestError, match="release profile drift"):
        runner.run_handoff_manifest(
            repo_root=Path("/tmp/repo"),
            evidence_root=Path("/tmp/evidence") / ("c" * 40),
            model_cache_dir=Path("/mnt/d/XBrainLabCache/models"),
            rag_cache_dir=Path("/mnt/d/XBrainLabCache/rag"),
            expected_branch="test-branch",
            require_upstream=False,
            allow_external_evidence_root=True,
        )


def test_desktop_source_profile_replaces_only_assistant_and_dashboard_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_ids = (
        "bounded-assistant-model-eval",
        "desktop-source-handoff-dashboard",
    )
    specs = tuple(
        GateSpec(
            check_id=check_id,
            section="4" if check_id.startswith("bounded") else "8",
            argv=("python", "-c", f"print('{check_id}')"),
            timeout_seconds=10,
        )
        for check_id in check_ids
    )
    monkeypatch.setattr(
        runner,
        "HANDOFF_GATE_SPECS",
        MappingProxyType({spec.check_id: spec for spec in specs}),
    )
    monkeypatch.setattr(
        runner,
        "HANDOFF_RELEASE_PROFILES",
        MappingProxyType(
            {
                "handoff": (
                    "stable-assistant-model-eval",
                    "handoff-dashboard",
                ),
                "desktop-source": check_ids,
            }
        ),
    )
    monkeypatch.setattr(
        runner,
        "handoff_profile_check_ids",
        lambda profile: check_ids
        if profile == "desktop-source"
        else (_ for _ in ()).throw(ValueError("unsupported test profile")),
    )
    monkeypatch.setattr(runner, "_SERIAL_GATE_IDS", ())
    monkeypatch.setattr(runner, "_DEFERRED_PREREQUISITE_IDS", ())
    monkeypatch.setattr(
        runner,
        "_POST_REGRESSION_LANES",
        (("stable-assistant-model-eval",),),
    )
    monkeypatch.setattr(runner, "_FINAL_GATE_IDS", ("handoff-dashboard",))
    source_identity = {"source_digest": "f" * 64, "dirty": False}
    recorded: list[dict[str, Any]] = []
    persisted: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    monkeypatch.setattr(
        runner,
        "record_handoff_command",
        lambda **kwargs: recorded.append(kwargs)
        or {"check_id": kwargs["check_id"], "passed": True},
    )
    monkeypatch.setattr(
        runner,
        "persist_handoff_records",
        lambda **kwargs: persisted.append(kwargs),
    )
    monkeypatch.setattr(
        runner,
        "validate_handoff_dossier",
        lambda **kwargs: verified.append(kwargs) or (True, ""),
    )
    monkeypatch.setattr(
        runner,
        "collect_source_identity",
        lambda *_args, **_kwargs: source_identity,
    )

    result = runner.run_handoff_manifest(
        repo_root=tmp_path,
        evidence_root=tmp_path / "external" / ("f" * 40),
        model_cache_dir=Path("/mnt/d/XBrainLabCache/models"),
        rag_cache_dir=Path("/mnt/d/XBrainLabCache/rag"),
        expected_branch="test-branch",
        require_upstream=False,
        allow_external_evidence_root=True,
        release_profile="desktop-source",
    )

    assert [item["check_id"] for item in recorded] == list(check_ids)
    assert all(item["release_profile"] == "desktop-source" for item in recorded)
    assert persisted[0]["release_profile"] == "desktop-source"
    assert verified[0]["release_profile"] == "desktop-source"
    assert result["release_profile"] == "desktop-source"
    assert "stable-assistant-model-eval" not in result["completed_check_ids"]
    assert "handoff-dashboard" not in result["completed_check_ids"]


def test_post_regression_lanes_run_concurrently_then_persist_in_registry_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_ids = (
        "serial-gate",
        "lane-a-first",
        "lane-a-second",
        "lane-b",
        "fetch-gate",
        "dashboard-gate",
    )
    specs = tuple(
        GateSpec(
            check_id=check_id,
            section="1",
            argv=("python", "-c", f"print('{check_id}')"),
            timeout_seconds=10,
        )
        for check_id in check_ids
    )
    monkeypatch.setattr(
        runner,
        "HANDOFF_GATE_SPECS",
        MappingProxyType({spec.check_id: spec for spec in specs}),
    )
    monkeypatch.setattr(runner, "REQUIRED_HANDOFF_CHECK_IDS", check_ids)
    monkeypatch.setattr(runner, "_SERIAL_GATE_IDS", ("serial-gate",))
    monkeypatch.setattr(runner, "_DEFERRED_PREREQUISITE_IDS", ("fetch-gate",))
    monkeypatch.setattr(
        runner,
        "_POST_REGRESSION_LANES",
        (("lane-a-first", "lane-a-second"), ("lane-b",)),
    )
    monkeypatch.setattr(runner, "_FINAL_GATE_IDS", ("dashboard-gate",))
    monkeypatch.setattr(
        runner,
        "handoff_profile_check_ids",
        lambda _profile: check_ids,
    )
    source_identity = {"source_digest": "d" * 64, "dirty": False}
    first_lane_barrier = Barrier(2)
    events: list[str] = []
    persisted: list[str] = []

    def fake_record(**kwargs: Any) -> dict[str, Any]:
        check_id = kwargs["check_id"]
        events.append(f"start:{check_id}")
        if check_id in {"lane-a-first", "lane-b"}:
            first_lane_barrier.wait(timeout=2)
        events.append(f"end:{check_id}")
        return {"check_id": check_id, "passed": True}

    def fake_persist(**kwargs: Any) -> None:
        persisted.extend(record["check_id"] for record in kwargs["records"])
        events.append("persist")

    monkeypatch.setattr(runner, "record_handoff_command", fake_record)
    monkeypatch.setattr(runner, "persist_handoff_records", fake_persist)
    monkeypatch.setattr(
        runner,
        "validate_handoff_dossier",
        lambda **_kwargs: (True, ""),
    )
    monkeypatch.setattr(
        runner,
        "collect_source_identity",
        lambda *_args, **_kwargs: source_identity,
    )
    evidence_root = tmp_path / "external" / ("d" * 40)

    result = runner.run_handoff_manifest(
        repo_root=tmp_path,
        evidence_root=evidence_root,
        model_cache_dir=Path("/mnt/d/XBrainLabCache/models"),
        rag_cache_dir=Path("/mnt/d/XBrainLabCache/rag"),
        expected_branch="test-branch",
        require_upstream=False,
        allow_external_evidence_root=True,
    )

    assert result["ok"] is True
    assert events.index("end:fetch-gate") < events.index("start:lane-a-first")
    assert events.index("end:fetch-gate") < events.index("start:lane-b")
    assert events.index("end:lane-a-first") < events.index("start:lane-a-second")
    assert persisted == [
        "lane-a-first",
        "lane-a-second",
        "lane-b",
        "fetch-gate",
    ]
    assert events.index("persist") < events.index("start:dashboard-gate")


def test_failed_parallel_lane_prevents_final_gate_and_dossier_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_ids = ("serial-gate", "lane-a", "lane-b", "dashboard-gate")
    specs = tuple(
        GateSpec(
            check_id=check_id,
            section="1",
            argv=("python", "-c", f"print('{check_id}')"),
            timeout_seconds=10,
        )
        for check_id in check_ids
    )
    monkeypatch.setattr(
        runner,
        "HANDOFF_GATE_SPECS",
        MappingProxyType({spec.check_id: spec for spec in specs}),
    )
    monkeypatch.setattr(runner, "REQUIRED_HANDOFF_CHECK_IDS", check_ids)
    monkeypatch.setattr(runner, "_SERIAL_GATE_IDS", ("serial-gate",))
    monkeypatch.setattr(runner, "_DEFERRED_PREREQUISITE_IDS", ())
    monkeypatch.setattr(
        runner,
        "_POST_REGRESSION_LANES",
        (("lane-a",), ("lane-b",)),
    )
    monkeypatch.setattr(runner, "_FINAL_GATE_IDS", ("dashboard-gate",))
    monkeypatch.setattr(
        runner,
        "handoff_profile_check_ids",
        lambda _profile: check_ids,
    )
    source_identity = {"source_digest": "e" * 64, "dirty": False}
    executed: list[str] = []
    verified = False

    def fake_record(**kwargs: Any) -> dict[str, Any]:
        check_id = kwargs["check_id"]
        executed.append(check_id)
        return {
            "check_id": check_id,
            "passed": check_id != "lane-a",
            "failure_reason": "lane failed" if check_id == "lane-a" else "",
        }

    def fake_verify(**_kwargs: Any) -> tuple[bool, str]:
        nonlocal verified
        verified = True
        return True, ""

    monkeypatch.setattr(runner, "record_handoff_command", fake_record)
    monkeypatch.setattr(runner, "persist_handoff_records", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "validate_handoff_dossier", fake_verify)
    monkeypatch.setattr(
        runner,
        "collect_source_identity",
        lambda *_args, **_kwargs: source_identity,
    )

    result = runner.run_handoff_manifest(
        repo_root=tmp_path,
        evidence_root=tmp_path / "external" / ("e" * 40),
        model_cache_dir=Path("/mnt/d/XBrainLabCache/models"),
        rag_cache_dir=Path("/mnt/d/XBrainLabCache/rag"),
        expected_branch="test-branch",
        require_upstream=False,
        allow_external_evidence_root=True,
    )

    assert result["ok"] is False
    assert "dashboard-gate" not in executed
    assert verified is False
    assert result["reason"] == "lane-a: lane failed"
