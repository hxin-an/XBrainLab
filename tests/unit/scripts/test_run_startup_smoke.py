from __future__ import annotations

import subprocess

from scripts.dev import run_startup_smoke as smoke


class _TimedOutProcess:
    returncode = None

    def communicate(self, timeout):
        raise subprocess.TimeoutExpired(("python", "run.py"), timeout)


class _Owner:
    def __init__(self, *, quiescent: bool = True) -> None:
        self.closed = False
        self.quiescent = quiescent

    def wait_for_exit(self, timeout_seconds: float) -> bool:
        assert timeout_seconds == smoke.QUIESCENCE_GRACE_SECONDS
        return self.quiescent

    def close(self, *, grace_seconds: float) -> None:
        assert grace_seconds == smoke.TERMINATION_GRACE_SECONDS
        self.closed = True


class _CompletedProcess:
    returncode = 0

    def communicate(self, timeout):
        assert timeout == smoke.TIMEOUT_SECONDS
        return (
            "MainWindow initialized\n"
            "XBrainLab startup smoke platform: windows\n"
            "XBrainLab startup smoke close requested\n",
            "",
        )


def test_startup_smoke_rejects_initialized_app_that_remains_running(
    monkeypatch,
) -> None:
    process = _TimedOutProcess()
    owner = _Owner()
    monkeypatch.setattr(
        smoke,
        "spawn_owned_process",
        lambda *_args, **_kwargs: (process, owner),
    )
    monkeypatch.setattr(
        smoke,
        "terminate_and_collect",
        lambda *_args, **_kwargs: (
            "MainWindow initialized\n"
            "XBrainLab startup smoke platform: windows\n"
            "XBrainLab startup smoke close requested\n",
            "",
        ),
    )

    result = smoke.run_startup_smoke(expected_platform="windows")

    assert result["passed"] is False
    assert result["timed_out"] is True
    assert result["return_code"] == 124
    assert result["saw_main_window_initialized"] is True
    assert result["saw_close_requested"] is True
    assert result["qt_platform"] == "windows"
    assert result["process_tree_quiescent"] is False
    assert owner.closed is True


def test_startup_smoke_accepts_clean_native_close(monkeypatch) -> None:
    process = _CompletedProcess()
    owner = _Owner()
    captured_environment: dict[str, str] = {}

    def spawn(*_args, **kwargs):
        captured_environment.update(kwargs["env"])
        return process, owner

    monkeypatch.setattr(smoke, "spawn_owned_process", spawn)

    result = smoke.run_startup_smoke(expected_platform="windows")

    assert result["passed"] is True
    assert result["timed_out"] is False
    assert result["return_code"] == 0
    assert result["qt_platform"] == "windows"
    assert result["saw_close_requested"] is True
    assert result["process_tree_quiescent"] is True
    assert captured_environment["XBRAINLAB_STARTUP_SMOKE_CLOSE_MS"] == "1000"
    assert owner.closed is True


def test_startup_smoke_rejects_wrong_native_platform(monkeypatch) -> None:
    process = _CompletedProcess()
    owner = _Owner()
    monkeypatch.setattr(
        smoke,
        "spawn_owned_process",
        lambda *_args, **_kwargs: (process, owner),
    )

    result = smoke.run_startup_smoke(expected_platform="cocoa")

    assert result["passed"] is False
    assert result["qt_platform"] == "windows"


def test_startup_smoke_rejects_owned_child_that_survives_parent(monkeypatch) -> None:
    process = _CompletedProcess()
    owner = _Owner(quiescent=False)
    monkeypatch.setattr(
        smoke,
        "spawn_owned_process",
        lambda *_args, **_kwargs: (process, owner),
    )

    result = smoke.run_startup_smoke(expected_platform="windows")

    assert result["passed"] is False
    assert result["timed_out"] is False
    assert result["return_code"] == 0
    assert result["process_tree_quiescent"] is False
    assert owner.closed is True


def test_startup_smoke_fails_when_init_marker_is_absent(monkeypatch) -> None:
    process = _TimedOutProcess()
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
