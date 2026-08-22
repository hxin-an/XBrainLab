from __future__ import annotations

import json
from types import SimpleNamespace

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


@pytest.mark.parametrize("panel_timeout_ms", (0, smoke.MAX_PANEL_TIMEOUT_MS + 1))
def test_native_product_smoke_rejects_unbounded_panel_timeout(
    panel_timeout_ms,
    tmp_path,
) -> None:
    with pytest.raises(ValueError, match="native panel timeout"):
        smoke.run_native_product_smoke(
            expected_platform="cocoa",
            expected_isolated_root=tmp_path,
            panel_timeout_ms=panel_timeout_ms,
        )


def test_main_forwards_explicit_panel_timeout(monkeypatch, tmp_path) -> None:
    output = tmp_path / "native.json"
    observed = {}
    monkeypatch.setattr(
        smoke,
        "_parse_args",
        lambda: SimpleNamespace(
            expected_platform="cocoa",
            expected_isolated_root=tmp_path,
            panel_timeout_ms=45_000,
            output=output,
        ),
    )

    def _run(**kwargs):
        observed.update(kwargs)
        return {"schema_version": 1, "passed": True}

    monkeypatch.setattr(smoke, "run_native_product_smoke", _run)

    assert smoke.main() == 0
    assert observed["panel_timeout_ms"] == 45_000
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] is True
