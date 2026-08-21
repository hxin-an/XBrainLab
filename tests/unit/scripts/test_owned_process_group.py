from __future__ import annotations

import io
import os
import signal
from types import SimpleNamespace

import pytest

from scripts.dev import owned_process_bootstrap, owned_process_group

POSIX_ONLY = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "killpg") or not hasattr(signal, "SIGKILL"),
    reason="requires the POSIX process-group signal contract",
)


class _FakeProcess:
    def __init__(self, *, running: bool = True) -> None:
        self.pid = 4321
        self.running = running
        self.signals: list[int] = []
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self.running else 0

    def send_signal(self, value: int) -> None:
        self.signals.append(value)

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None):
        del timeout
        self.running = False
        return 0


def test_windows_group_creation_and_graceful_tree_termination_are_scoped(
    monkeypatch,
) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "nt")
    monkeypatch.setattr(
        owned_process_group.shutil,
        "which",
        lambda _name: "taskkill.exe",
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        owned_process_group.subprocess,
        "run",
        lambda argv, **_kwargs: calls.append(list(argv))
        or SimpleNamespace(returncode=0),
    )
    process = _FakeProcess()

    kwargs = owned_process_group.creation_kwargs()
    owned_process_group.signal_owned_group(process, force=False)

    assert kwargs == {
        "creationflags": owned_process_group.WINDOWS_NEW_PROCESS_GROUP,
        "start_new_session": False,
    }
    assert calls == [["taskkill.exe", "/PID", "4321", "/T"]]
    assert process.signals == []
    assert process.terminated is False


def test_windows_graceful_fallback_signals_the_owned_group(monkeypatch) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "nt")
    monkeypatch.setattr(owned_process_group.shutil, "which", lambda _name: None)
    process = _FakeProcess()

    owned_process_group.signal_owned_group(process, force=False)

    assert process.signals == [owned_process_group.WINDOWS_CTRL_BREAK_EVENT]
    assert process.terminated is False


def test_windows_force_uses_exact_pid_tree_not_image_wide_taskkill(monkeypatch) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "nt")
    monkeypatch.setattr(
        owned_process_group.shutil, "which", lambda _name: "taskkill.exe"
    )
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(owned_process_group.subprocess, "run", fake_run)
    process = _FakeProcess()

    owned_process_group.signal_owned_group(process, force=True)

    assert calls == [["taskkill.exe", "/PID", "4321", "/T", "/F"]]
    assert "/IM" not in calls[0]
    assert process.killed is False


def test_windows_force_falls_back_to_direct_owned_process_kill(monkeypatch) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "nt")
    monkeypatch.setattr(owned_process_group.shutil, "which", lambda _name: None)
    process = _FakeProcess()

    owned_process_group.signal_owned_group(process, force=True)

    assert process.killed is True


@pytest.mark.platform_contract
@POSIX_ONLY
def test_posix_force_targets_only_the_owned_session(monkeypatch) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "posix")
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        owned_process_group.os,
        "killpg",
        lambda pid, sig: calls.append((pid, sig)),
        raising=False,
    )
    process = _FakeProcess()

    owned_process_group.signal_owned_group(process, force=True)

    assert owned_process_group.creation_kwargs() == {
        "creationflags": 0,
        "start_new_session": True,
    }
    assert calls == [(4321, signal.SIGKILL)]


@pytest.mark.platform_contract
@POSIX_ONLY
def test_posix_group_is_still_signalled_after_its_leader_exits(monkeypatch) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "posix")
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        owned_process_group.os,
        "killpg",
        lambda pid, sig: calls.append((pid, sig)),
        raising=False,
    )
    process = _FakeProcess(running=False)

    owned_process_group.signal_owned_group(process, force=True)

    assert calls == [(4321, signal.SIGKILL)]


@pytest.mark.platform_contract
@POSIX_ONLY
def test_posix_orphaned_group_permission_error_does_not_escape_or_widen_cleanup(
    monkeypatch,
) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "posix")
    process = _FakeProcess(running=False)
    monkeypatch.setattr(
        owned_process_group.os,
        "killpg",
        lambda _pid, _sig: (_ for _ in ()).throw(PermissionError("orphaned group")),
        raising=False,
    )

    owned_process_group.signal_owned_group(process, force=True)

    assert process.killed is False
    assert process.terminated is False


def test_windows_owner_closes_job_after_parent_already_exited(monkeypatch) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "nt")
    calls: list[str] = []

    class FakeJob:
        def __init__(self, process) -> None:
            assert process.pid == 4321

        def terminate(self) -> None:
            calls.append("terminate")

        def close(self) -> None:
            calls.append("close")

    monkeypatch.setattr(owned_process_group, "_WindowsJobHandle", FakeJob)
    owner = owned_process_group.own_process_group(_FakeProcess(running=False))

    owner.close()

    assert calls == ["terminate", "close"]


def test_windows_owner_observes_job_quiescence_without_terminating(monkeypatch) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "nt")
    calls: list[str] = []

    class FakeJob:
        def __init__(self, _process) -> None:
            pass

        def has_active_processes(self) -> bool:
            calls.append("inspect")
            return False

        def terminate(self) -> None:
            calls.append("terminate")

        def close(self) -> None:
            calls.append("close")

    monkeypatch.setattr(owned_process_group, "_WindowsJobHandle", FakeJob)
    owner = owned_process_group.own_process_group(_FakeProcess(running=False))

    assert owner.wait_for_exit(0) is True
    assert calls == ["inspect"]


@pytest.mark.platform_contract
@POSIX_ONLY
def test_posix_owner_reports_surviving_group_without_signalling(monkeypatch) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "posix")
    monkeypatch.setattr(
        owned_process_group,
        "_posix_group_exists",
        lambda _pid: True,
    )
    process = _FakeProcess(running=False)
    owner = owned_process_group.own_process_group(process)

    assert owner.wait_for_exit(0) is False
    assert process.signals == []
    assert process.terminated is False
    assert process.killed is False


def test_windows_spawn_releases_target_only_after_job_ownership(monkeypatch) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "nt")
    events: list[str] = []

    class Handshake:
        def write(self, value: str) -> int:
            assert value == "1"
            events.append("release")
            return 1

        def flush(self) -> None:
            events.append("flush")

        def close(self) -> None:
            events.append("close-stdin")

    process = _FakeProcess()
    process.stdin = Handshake()  # type: ignore[attr-defined]

    def fake_popen(argv, **kwargs):
        events.append("spawn-bootstrap")
        assert argv[-3:] == ["--", "target.exe", "--value"]
        assert kwargs["stdin"] is owned_process_group.subprocess.PIPE
        return process

    owner = object()

    def fake_own(candidate):
        assert candidate is process
        events.append("own-job")
        return owner

    monkeypatch.setattr(owned_process_group.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(owned_process_group, "own_process_group", fake_own)

    spawned, spawned_owner = owned_process_group.spawn_owned_process(
        ["target.exe", "--value"],
        text=True,
    )

    assert spawned is process
    assert spawned_owner is owner
    assert events == ["spawn-bootstrap", "own-job", "release", "flush", "close-stdin"]
    assert process.stdin is None  # type: ignore[attr-defined]


def test_windows_spawn_never_releases_target_when_job_ownership_fails(
    monkeypatch,
) -> None:
    monkeypatch.setattr(owned_process_group, "_platform_name", lambda: "nt")
    writes: list[str] = []

    class Handshake:
        def write(self, value: str) -> int:
            writes.append(value)
            return 1

        def flush(self) -> None:
            pass

        def close(self) -> None:
            pass

    process = _FakeProcess()
    process.stdin = Handshake()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        owned_process_group.subprocess,
        "Popen",
        lambda *_args, **_kwargs: process,
    )
    monkeypatch.setattr(
        owned_process_group,
        "own_process_group",
        lambda _process: (_ for _ in ()).throw(OSError("job assignment failed")),
    )

    with pytest.raises(OSError, match="job assignment failed"):
        owned_process_group.spawn_owned_process(["target.exe"], text=True)

    assert writes == []
    assert process.terminated or process.killed
    assert process.running is False


def test_windows_bootstrap_refuses_to_start_without_parent_handshake(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        owned_process_bootstrap.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("target must not start"),
    )

    assert (
        owned_process_bootstrap.run_after_handshake(
            ["target.exe"],
            io.BytesIO(b""),
        )
        == owned_process_bootstrap.HANDSHAKE_FAILURE_EXIT_CODE
    )


def test_windows_bootstrap_runs_exact_argv_after_parent_handshake(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        owned_process_bootstrap.subprocess,
        "run",
        lambda argv, **kwargs: calls.append(list(argv))
        or SimpleNamespace(returncode=7),
    )

    assert (
        owned_process_bootstrap.run_after_handshake(
            ["target.exe", "--value"],
            io.BytesIO(b"1"),
        )
        == 7
    )
    assert calls == [["target.exe", "--value"]]


def test_terminate_and_collect_never_uses_unbounded_communicate(monkeypatch) -> None:
    process = _FakeProcess()
    communicate_timeouts: list[float | None] = []

    def communicate(*, timeout=None):
        communicate_timeouts.append(timeout)
        raise owned_process_group.subprocess.TimeoutExpired(
            cmd=["owned-check"],
            timeout=timeout,
            output="partial stdout",
            stderr="partial stderr",
        )

    process.communicate = communicate  # type: ignore[attr-defined]
    process.stdout = None  # type: ignore[attr-defined]
    process.stderr = None  # type: ignore[attr-defined]
    owner = SimpleNamespace(signal=lambda **_kwargs: None)

    stdout, stderr = owned_process_group.terminate_and_collect(
        process,  # type: ignore[arg-type]
        owner,  # type: ignore[arg-type]
        grace_seconds=0.01,
    )

    assert communicate_timeouts == [0.01, 0.01]
    assert stdout == "partial stdout"
    assert stderr == "partial stderr"
