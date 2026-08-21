"""Bounded termination helpers for only the process tree a gate starts."""

from __future__ import annotations

import ctypes
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from contextlib import suppress
from ctypes import Structure, byref, c_size_t, c_ulonglong, sizeof, wintypes
from pathlib import Path
from typing import Any, Protocol

WINDOWS_NEW_PROCESS_GROUP = int(
    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
)
WINDOWS_CTRL_BREAK_EVENT = int(getattr(signal, "CTRL_BREAK_EVENT", 1))
WINDOWS_TASKKILL_TIMEOUT_SECONDS = 15
WINDOWS_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
WINDOWS_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
WINDOWS_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
DEFAULT_TERMINATION_GRACE_SECONDS = 5.0


class OwnedProcess(Protocol):
    """Small subprocess surface needed by the termination policy."""

    pid: int

    def poll(self) -> int | None: ...

    def send_signal(self, sig: int) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


class _JobObjectBasicLimitInformation(Structure):
    _fields_ = (
        ("PerProcessUserTimeLimit", c_ulonglong),
        ("PerJobUserTimeLimit", c_ulonglong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", c_size_t),
        ("MaximumWorkingSetSize", c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    )


class _IoCounters(Structure):
    _fields_ = (
        ("ReadOperationCount", c_ulonglong),
        ("WriteOperationCount", c_ulonglong),
        ("OtherOperationCount", c_ulonglong),
        ("ReadTransferCount", c_ulonglong),
        ("WriteTransferCount", c_ulonglong),
        ("OtherTransferCount", c_ulonglong),
    )


class _JobObjectExtendedLimitInformation(Structure):
    _fields_ = (
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", c_size_t),
        ("JobMemoryLimit", c_size_t),
        ("PeakProcessMemoryUsed", c_size_t),
        ("PeakJobMemoryUsed", c_size_t),
    )


class _JobObjectBasicAccountingInformation(Structure):
    _fields_ = (
        ("TotalUserTime", c_ulonglong),
        ("TotalKernelTime", c_ulonglong),
        ("ThisPeriodTotalUserTime", c_ulonglong),
        ("ThisPeriodTotalKernelTime", c_ulonglong),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    )


class _WindowsJobHandle:
    """Own one Windows process tree until the handle is explicitly closed."""

    def __init__(self, process: OwnedProcess) -> None:
        windows_dll = getattr(ctypes, "WinDLL", None)
        if windows_dll is None:
            raise OSError("Windows Job Objects are unavailable on this platform.")
        kernel32 = windows_dll("kernel32", use_last_error=True)
        create_job = kernel32.CreateJobObjectW
        create_job.restype = wintypes.HANDLE
        handle = create_job(None, None)
        if not handle:
            raise OSError("Could not create a Windows Job Object for a gate process.")

        self._kernel32 = kernel32
        self._handle = handle
        self._closed = False
        limits = _JobObjectExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = (
            WINDOWS_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        set_information = kernel32.SetInformationJobObject
        configured = bool(
            set_information(
                handle,
                WINDOWS_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                byref(limits),
                sizeof(limits),
            )
        )
        process_handle = getattr(process, "_handle", None)
        assigned = bool(
            process_handle and kernel32.AssignProcessToJobObject(handle, process_handle)
        )
        if not configured or not assigned:
            kernel32.CloseHandle(handle)
            self._closed = True
            raise OSError("Could not contain the gate process in a Windows Job Object.")

    def terminate(self) -> None:
        if not self._closed:
            self._kernel32.TerminateJobObject(self._handle, 1)

    def has_active_processes(self) -> bool:
        if self._closed:
            return False
        accounting = _JobObjectBasicAccountingInformation()
        returned_length = wintypes.DWORD()
        queried = bool(
            self._kernel32.QueryInformationJobObject(
                self._handle,
                WINDOWS_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                byref(accounting),
                sizeof(accounting),
                byref(returned_length),
            )
        )
        if not queried:
            raise OSError("Could not inspect the gate process Job Object.")
        return bool(accounting.ActiveProcesses)

    def close(self) -> None:
        if self._closed:
            return
        self._kernel32.CloseHandle(self._handle)
        self._closed = True


class OwnedProcessGroup:
    """Lifetime owner for the exact process tree started by one validation gate."""

    def __init__(self, process: OwnedProcess) -> None:
        self.process = process
        self._windows_job = (
            _WindowsJobHandle(process) if _platform_name() == "nt" else None
        )
        self._closed = False

    def signal(self, *, force: bool) -> None:
        if self._windows_job is not None:
            self._windows_job.terminate()
            return
        signal_owned_group(self.process, force=force)

    def wait_for_exit(self, timeout_seconds: float) -> bool:
        """Observe a naturally quiescent owned tree without terminating it."""
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            if self._windows_job is not None:
                active = self._windows_job.has_active_processes()
            elif _platform_name() == "posix":
                active = _posix_group_exists(self.process.pid)
            else:
                active = self.process.poll() is None
            if not active:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def close(
        self, *, grace_seconds: float = DEFAULT_TERMINATION_GRACE_SECONDS
    ) -> None:
        """Bound and reap descendants even when their parent already exited."""
        if self._closed:
            return
        self._closed = True
        if self._windows_job is not None:
            self._windows_job.terminate()
            self._windows_job.close()
            return
        if _platform_name() == "posix":
            signal_owned_group(self.process, force=False)
            if _wait_for_posix_group_exit(self.process.pid, grace_seconds):
                return
            signal_owned_group(self.process, force=True)
            _wait_for_posix_group_exit(self.process.pid, grace_seconds)
            return
        if self.process.poll() is None:
            self.process.terminate()


def own_process_group(process: OwnedProcess) -> OwnedProcessGroup:
    """Attach the platform-specific ownership boundary immediately after spawn."""
    return OwnedProcessGroup(process)


def spawn_owned_process(
    argv: Sequence[str],
    **popen_kwargs: Any,
) -> tuple[subprocess.Popen[Any], OwnedProcessGroup]:
    """Spawn one command without allowing a Windows child before containment."""
    command = [str(part) for part in argv]
    if not command:
        raise ValueError("An owned process command cannot be empty.")
    reserved = {"creationflags", "start_new_session"}.intersection(popen_kwargs)
    if reserved:
        names = ", ".join(sorted(reserved))
        raise ValueError(
            f"Owned process creation options are managed internally: {names}."
        )

    if _platform_name() == "nt":
        if "stdin" in popen_kwargs:
            raise ValueError("Windows owned-process bootstrap reserves stdin.")
        bootstrap = Path(__file__).with_name("owned_process_bootstrap.py")
        process = subprocess.Popen(  # noqa: S603 - exact source-controlled bootstrap.
            [sys.executable, str(bootstrap), "--", *command],
            stdin=subprocess.PIPE,
            **popen_kwargs,
            **creation_kwargs(),
        )
        try:
            owner = own_process_group(process)
        except BaseException:
            _abort_waiting_bootstrap(process)
            raise
        try:
            _release_windows_bootstrap(
                process,
                text_mode=bool(
                    popen_kwargs.get("text") or popen_kwargs.get("universal_newlines")
                ),
            )
        except BaseException:
            owner.close()
            _wait_for_exact_process(process)
            raise
        return process, owner

    process = subprocess.Popen(  # noqa: S603 - caller supplies an exact argv sequence.
        command,
        **popen_kwargs,
        **creation_kwargs(),
    )
    try:
        return process, own_process_group(process)
    except BaseException:
        signal_owned_group(process, force=True)
        _wait_for_exact_process(process)
        raise


def _platform_name() -> str:
    return os.name


def creation_kwargs() -> dict[str, Any]:
    """Create an independently addressable process group/session."""
    if _platform_name() == "nt":
        return {
            "creationflags": WINDOWS_NEW_PROCESS_GROUP,
            "start_new_session": False,
        }
    return {"creationflags": 0, "start_new_session": True}


def _release_windows_bootstrap(
    process: subprocess.Popen[Any],
    *,
    text_mode: bool,
) -> None:
    stream = process.stdin
    if stream is None:
        raise OSError("Windows owned-process bootstrap has no handshake stream.")
    try:
        stream.write("1" if text_mode else b"1")
        stream.flush()
    finally:
        stream.close()
        process.stdin = None


def _abort_waiting_bootstrap(process: subprocess.Popen[Any]) -> None:
    stream = process.stdin
    if stream is not None:
        with suppress(OSError, ValueError):
            stream.close()
        process.stdin = None
    if process.poll() is None:
        with suppress(OSError):
            process.terminate()
    _wait_for_exact_process(process)


def _wait_for_exact_process(
    process: subprocess.Popen[Any],
    *,
    grace_seconds: float = DEFAULT_TERMINATION_GRACE_SECONDS,
) -> None:
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        with suppress(OSError):
            process.kill()
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=grace_seconds)


def signal_owned_group(process: OwnedProcess, *, force: bool) -> None:
    """Signal only one gate-owned process session or exact Windows PID tree."""
    platform = _platform_name()
    if platform == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            return
        except PermissionError:
            # macOS can report EPERM for an orphaned process group after its
            # session leader exits. The group is still the only safe target;
            # do not widen cleanup to unrelated processes.
            return
        return
    if platform == "nt":
        if _taskkill_exact_pid_tree(process.pid, force=force):
            return
        if not force:
            if process.poll() is not None:
                return
            try:
                process.send_signal(WINDOWS_CTRL_BREAK_EVENT)
            except (OSError, ValueError):
                pass
            else:
                return
    if process.poll() is not None:
        return
    if force:
        process.kill()
    else:
        process.terminate()


def terminate_and_collect(
    process: subprocess.Popen[str],
    owner: OwnedProcessGroup,
    *,
    grace_seconds: float = DEFAULT_TERMINATION_GRACE_SECONDS,
) -> tuple[str, str]:
    """Terminate one owned tree and collect output without an unbounded wait."""
    owner.signal(force=False)
    try:
        return process.communicate(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        owner.signal(force=True)
        try:
            return process.communicate(timeout=grace_seconds)
        except subprocess.TimeoutExpired as error:
            stdout = _timeout_text(error.output)
            stderr = _timeout_text(error.stderr)
            _close_capture_streams(process)
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=grace_seconds)
            return stdout, stderr


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _close_capture_streams(process: subprocess.Popen[str]) -> None:
    for stream in (process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            stream.close()


def _wait_for_posix_group_exit(pid: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        if not _posix_group_exists(pid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)


def _posix_group_exists(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _taskkill_exact_pid_tree(pid: int, *, force: bool) -> bool:
    executable = shutil.which("taskkill.exe") or shutil.which("taskkill")
    if executable is None:
        return False
    argv = [executable, "/PID", str(pid), "/T"]
    if force:
        argv.append("/F")
    try:
        completed = subprocess.run(  # noqa: S603 - exact owned PID, no shell.
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=WINDOWS_TASKKILL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0
