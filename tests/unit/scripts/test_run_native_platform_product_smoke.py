from __future__ import annotations

import json

import pytest

from scripts.dev import run_native_platform_product_smoke as smoke


def _set_isolated_environment(monkeypatch, root) -> None:
    for index, variable in enumerate(smoke.REQUIRED_ISOLATED_ENV):
        monkeypatch.setenv(variable, str(root / f"path {index}"))


def test_isolated_environment_requires_space_and_non_ascii_root(
    monkeypatch,
    tmp_path,
) -> None:
    root = tmp_path / "plain-root"
    _set_isolated_environment(monkeypatch, root)

    with pytest.raises(ValueError, match="space and non-ASCII"):
        smoke.validate_isolated_environment(root)


def test_isolated_environment_rejects_mutable_path_outside_owned_root(
    monkeypatch,
    tmp_path,
) -> None:
    root = tmp_path / "Native 測試"
    _set_isolated_environment(monkeypatch, root)
    monkeypatch.setenv("TEMP", str(tmp_path / "outside"))

    with pytest.raises(ValueError, match="escapes"):
        smoke.validate_isolated_environment(root)


def test_isolated_environment_returns_all_owned_paths(monkeypatch, tmp_path) -> None:
    root = tmp_path / "Native 測試"
    _set_isolated_environment(monkeypatch, root)

    resolved = smoke.validate_isolated_environment(root)

    assert set(resolved) == set(smoke.REQUIRED_ISOLATED_ENV)
    assert all(path.startswith(str(root.resolve())) for path in resolved.values())


@pytest.mark.parametrize(
    ("change", "value"),
    (
        ("application_closed", False),
        ("pre_close_application_idle", False),
        ("pre_close_remaining_workers", 1),
        ("pre_close_remaining_subprocesses", 1),
        ("close_attempt_id", ""),
    ),
)
def test_shutdown_snapshot_rejects_incomplete_or_leaked_state(change, value) -> None:
    snapshot = {
        "close_attempt_id": "attempt-1",
        "pre_close_application_idle": True,
        "pre_close_remaining_workers": 0,
        "pre_close_remaining_subprocesses": 0,
        "application_closed": True,
    }
    snapshot[change] = value

    assert smoke._shutdown_snapshot_is_clean(snapshot) is False


def test_native_smoke_artifact_is_atomic_json(tmp_path) -> None:
    output = tmp_path / "artifact" / "native.json"
    payload = {"schema_version": 1, "passed": True}

    smoke._write_artifact(output, payload)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert not output.with_suffix(".json.tmp").exists()
