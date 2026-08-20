from __future__ import annotations

import subprocess

from scripts.dev import run_startup_smoke as smoke


class _Process:
    returncode = None

    def communicate(self, timeout):
        raise subprocess.TimeoutExpired(("python", "run.py"), timeout)


class _Owner:
    def __init__(self) -> None:
        self.closed = False

    def close(self, *, grace_seconds: float) -> None:
        assert grace_seconds == smoke.TERMINATION_GRACE_SECONDS
        self.closed = True


def test_startup_smoke_accepts_initialized_app_that_remains_running(
    monkeypatch,
) -> None:
    process = _Process()
    owner = _Owner()
    monkeypatch.setattr(
        smoke,
        "spawn_owned_process",
        lambda *_args, **_kwargs: (process, owner),
    )
    monkeypatch.setattr(
        smoke,
        "terminate_and_collect",
        lambda *_args, **_kwargs: ("MainWindow initialized\n", ""),
    )

    result = smoke.run_startup_smoke()

    assert result["passed"] is True
    assert result["timed_out"] is True
    assert result["return_code"] == 124
    assert result["saw_main_window_initialized"] is True
    assert owner.closed is True


def test_startup_smoke_fails_when_init_marker_is_absent(monkeypatch) -> None:
    process = _Process()
    owner = _Owner()
    monkeypatch.setattr(
        smoke,
        "spawn_owned_process",
        lambda *_args, **_kwargs: (process, owner),
    )
    monkeypatch.setattr(
        smoke,
        "terminate_and_collect",
        lambda *_args, **_kwargs: ("still loading\n", ""),
    )

    result = smoke.run_startup_smoke()

    assert result["passed"] is False
    assert result["saw_main_window_initialized"] is False
    assert owner.closed is True
