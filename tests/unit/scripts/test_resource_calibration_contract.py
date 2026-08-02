from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.dev import resource_calibration_contract as contract


def _source_identity(source_digest: str, **overrides: object) -> dict:
    identity = {
        "branch": "feature/calibration",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "status_available": True,
        "dirty": False,
        "dirty_count": 0,
        "relevant_dirty_paths": [],
        "protected_local_changes": [],
        "source_paths": list(contract.CALIBRATION_SOURCE_PATHS),
        "source_digest": source_digest,
    }
    identity.update(overrides)
    return identity


def test_source_identity_excludes_only_protected_root_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(
        contract,
        "_git_lines",
        lambda _repo_root, *_args: [
            " M settings.json",
            " M XBrainLab/backend/application/resource_guard.py",
        ],
    )
    monkeypatch.setattr(
        contract,
        "_git_value",
        lambda _repo_root, *args: {
            ("branch", "--show-current"): "feature/calibration",
            ("rev-parse", "HEAD"): "a" * 40,
            ("rev-parse", "HEAD^{tree}"): "b" * 40,
        }.get(args, ""),
    )
    monkeypatch.setattr(
        contract,
        "calibration_source_digest",
        lambda _repo_root, _source_paths: "c" * 64,
    )

    identity = contract.collect_calibration_source_identity(tmp_path)

    assert identity["dirty"] is True
    assert identity["dirty_count"] == 1
    assert identity["relevant_dirty_paths"] == [
        "XBrainLab/backend/application/resource_guard.py"
    ]
    assert identity["protected_local_changes"] == ["settings.json"]


def test_source_identity_accepts_unstaged_protected_settings_only(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        contract,
        "_git_lines",
        lambda _repo_root, *_args: [" M settings.json"],
    )
    monkeypatch.setattr(contract, "_git_value", lambda _repo_root, *_args: "a" * 40)
    monkeypatch.setattr(
        contract,
        "calibration_source_digest",
        lambda _repo_root, _source_paths: "c" * 64,
    )

    identity = contract.collect_calibration_source_identity(tmp_path)

    assert identity["dirty"] is False
    assert identity["dirty_count"] == 0
    assert identity["relevant_dirty_paths"] == []
    assert identity["protected_local_changes"] == ["settings.json"]


def test_source_identity_rejects_staged_protected_settings(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        contract,
        "_git_lines",
        lambda _repo_root, *_args: ["M  settings.json"],
    )
    monkeypatch.setattr(contract, "_git_value", lambda _repo_root, *_args: "a" * 40)
    monkeypatch.setattr(
        contract,
        "calibration_source_digest",
        lambda _repo_root, _source_paths: "c" * 64,
    )

    identity = contract.collect_calibration_source_identity(tmp_path)

    assert identity["status_available"] is True
    assert identity["dirty"] is True
    assert identity["dirty_count"] == 1
    assert identity["protected_local_changes"] == []


def test_source_identity_fails_closed_when_git_status_is_unavailable(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(contract, "_git_lines", lambda _repo_root, *_args: None)
    monkeypatch.setattr(contract, "_git_value", lambda _repo_root, *_args: "a" * 40)
    monkeypatch.setattr(
        contract,
        "calibration_source_digest",
        lambda _repo_root, _source_paths: "c" * 64,
    )

    identity = contract.collect_calibration_source_identity(tmp_path)

    assert identity["status_available"] is False
    assert identity["dirty"] is None
    assert identity["dirty_count"] is None

    report = _report("c" * 64)
    report["source_identity"] = identity
    failures = contract.strict_calibration_failure_reasons(
        report,
        repo_root=tmp_path,
        validate_source=True,
    )

    assert "calibration source git status is unavailable" in failures


def _report(source_digest: str) -> dict:
    return {
        "schema_version": contract.RESOURCE_CALIBRATION_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_identity": _source_identity(source_digest),
        "command": ["python", "calibrate_resource_guard.py", "--strict"],
        "environment": {
            "python": "3.12.0",
            "torch": "2.0.0",
            "torch_cuda": "12.0",
            "cuda_available": True,
            "gpu_name": "Test GPU",
            "driver_version": "999.0",
        },
        "expected_models": list(contract.EXPECTED_CALIBRATION_MODELS),
        "cuda_probe": {
            "status": "measured",
            "models": [
                {
                    "model": model,
                    "status": "measured",
                    "estimate_covers_observed_peak": True,
                }
                for model in contract.EXPECTED_CALIBRATION_MODELS
            ],
            "all_estimates_cover_observed_peak": True,
        },
    }


def test_strict_contract_detects_source_content_staleness(monkeypatch, tmp_path):
    source = tmp_path / "source.py"
    source.write_text("first\n", encoding="utf-8")
    monkeypatch.setattr(contract, "CALIBRATION_SOURCE_PATHS", ("source.py",))
    digest = contract.calibration_source_digest(tmp_path, ("source.py",))
    report = _report(digest)
    report["source_identity"]["source_paths"] = ["source.py"]

    def current_identity(_repo_root, *, source_paths):
        return {
            **_source_identity(
                contract.calibration_source_digest(tmp_path, source_paths)
            ),
            "source_paths": list(source_paths),
        }

    monkeypatch.setattr(
        contract, "collect_calibration_source_identity", current_identity
    )

    assert (
        contract.strict_calibration_failure_reasons(
            report,
            repo_root=tmp_path,
            validate_source=True,
        )
        == []
    )

    source.write_text("second\n", encoding="utf-8")
    failures = contract.strict_calibration_failure_reasons(
        report,
        repo_root=tmp_path,
        validate_source=True,
    )

    assert "calibration source digest is stale" in failures


@pytest.mark.parametrize(
    ("field", "recorded_value", "expected_failure"),
    (
        ("branch", "feature/stale", "branch is stale"),
        ("commit_sha", "c" * 40, "commit_sha is stale"),
        ("tree_sha", "d" * 40, "tree_sha is stale"),
        ("dirty_count", 1, "dirty_count is stale"),
        (
            "relevant_dirty_paths",
            ["scripts/dev/resource_calibration_contract.py"],
            "relevant_dirty_paths is stale",
        ),
    ),
)
def test_exact_source_validation_rejects_recorded_identity_drift(
    monkeypatch,
    tmp_path,
    field: str,
    recorded_value: object,
    expected_failure: str,
):
    digest = contract.calibration_source_digest(tmp_path)
    current_identity = _source_identity(digest)
    report = _report(digest)
    report["source_identity"][field] = recorded_value
    monkeypatch.setattr(
        contract,
        "collect_calibration_source_identity",
        lambda _repo_root, *, source_paths: current_identity,
    )

    failures = contract.strict_calibration_failure_reasons(
        report,
        repo_root=tmp_path,
        validate_source=True,
    )

    assert f"calibration source {expected_failure}" in failures


def test_exact_source_validation_rejects_dirty_recorded_identity(
    monkeypatch,
    tmp_path,
):
    digest = contract.calibration_source_digest(tmp_path)
    dirty_identity = _source_identity(
        digest,
        dirty=True,
        dirty_count=1,
        relevant_dirty_paths=[],
    )
    report = _report(digest)
    report["source_identity"] = dirty_identity
    monkeypatch.setattr(
        contract,
        "collect_calibration_source_identity",
        lambda _repo_root, *, source_paths: dirty_identity,
    )

    failures = contract.strict_calibration_failure_reasons(
        report,
        repo_root=tmp_path,
        validate_source=True,
    )

    assert "exact-source calibration was recorded from a dirty worktree" in failures


def test_exact_source_validation_rejects_current_dirty_tree(monkeypatch, tmp_path):
    digest = contract.calibration_source_digest(tmp_path)
    report = _report(digest)
    current_identity = _source_identity(
        digest,
        dirty=True,
        dirty_count=1,
        relevant_dirty_paths=[],
    )
    monkeypatch.setattr(
        contract,
        "collect_calibration_source_identity",
        lambda _repo_root, *, source_paths: current_identity,
    )

    failures = contract.strict_calibration_failure_reasons(
        report,
        repo_root=tmp_path,
        validate_source=True,
    )

    assert "exact-source calibration is being checked from a dirty worktree" in failures


def test_exact_source_validation_requires_a_recorded_branch(monkeypatch, tmp_path):
    digest = contract.calibration_source_digest(tmp_path)
    detached_identity = _source_identity(digest, branch="")
    report = _report(digest)
    report["source_identity"] = detached_identity
    monkeypatch.setattr(
        contract,
        "collect_calibration_source_identity",
        lambda _repo_root, *, source_paths: detached_identity,
    )

    failures = contract.strict_calibration_failure_reasons(
        report,
        repo_root=tmp_path,
        validate_source=True,
    )

    assert "calibration source branch is missing" in failures


def test_non_exact_checkpoint_validation_preserves_recorded_identity():
    digest = "e" * 64
    report = _report(digest)
    report["source_identity"].update(
        {
            "branch": "feature/checkpoint",
            "commit_sha": "f" * 40,
            "tree_sha": "1" * 40,
            "dirty": True,
            "dirty_count": 7,
            "relevant_dirty_paths": ["pyproject.toml"],
        }
    )

    failures = contract.strict_calibration_failure_reasons(
        report,
        validate_source=False,
    )

    assert failures == []
