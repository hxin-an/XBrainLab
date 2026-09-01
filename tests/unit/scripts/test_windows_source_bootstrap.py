from __future__ import annotations

import json
import signal
import subprocess
from pathlib import Path

import pytest

from scripts import windows_setup
from scripts.windows_setup import (
    CUDA_MINIMUM_DRIVER_MAJOR,
    POETRY_INSTALLER_COMMIT,
    POETRY_INSTALLER_SHA256,
    POETRY_INSTALLER_URL,
    POETRY_VERSION,
    ComputePlan,
    EnvironmentState,
    SetupError,
    _install_poetry,
    _recover_invalid_environment,
    _setup_environment,
    choose_compute_plan,
    poetry_sync_argv,
    run_model_download,
    select_model_id,
)
from XBrainLab.llm.core.model_catalog import (
    LOWER_MEMORY_LOCAL_MODEL_ID,
    PRIMARY_LOCAL_MODEL_ID,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


class _Signal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self._callbacks):
            callback(*args)


class _Application:
    def __init__(self, on_exec=None) -> None:
        self.exec_calls = 0
        self.quit_calls = 0
        self.on_exec = on_exec

    def exec(self) -> int:
        self.exec_calls += 1
        if self.on_exec is not None:
            self.on_exec()
        return 0

    def quit(self) -> None:
        self.quit_calls += 1


class _Lifecycle:
    def __init__(
        self,
        *,
        ok: bool = True,
        admitted: bool = True,
        synchronous: bool = True,
    ) -> None:
        self.progress = _Signal()
        self.terminal = _Signal()
        self.ok = ok
        self.admitted = admitted
        self.synchronous = synchronous
        self.cancel_calls = 0
        self.requests: list[tuple[str, str]] = []

    def ensure_download(self, model_id: str, cache_dir: str) -> bool:
        self.requests.append((model_id, cache_dir))
        if not self.admitted:
            return False
        if self.synchronous:
            self.finish()
        return True

    def finish(self) -> None:
        self.progress.emit(25, "Downloading")
        self.terminal.emit(self.ok, "done" if self.ok else "failed")

    def request_cancel(self) -> bool:
        self.cancel_calls += 1
        self.terminal.emit(False, "cancelled")
        return True


@pytest.mark.parametrize(
    ("output", "expected_extra"),
    [
        ("", "cpu"),
        ("579.99, NVIDIA Test GPU", "cpu"),
        ("580.10, NVIDIA Test GPU", "cuda"),
        ("600.1, NVIDIA Test GPU", "cuda"),
    ],
)
def test_compute_plan_uses_cuda_13_driver_boundary(
    output: str,
    expected_extra: str,
) -> None:
    plan = choose_compute_plan(output, force_cpu=False)

    assert CUDA_MINIMUM_DRIVER_MAJOR == 580
    assert plan.extra == expected_extra


def test_explicit_cpu_wins_over_compatible_nvidia_driver() -> None:
    plan = choose_compute_plan(
        "600.1, NVIDIA Test GPU",
        force_cpu=True,
    )

    assert plan.extra == "cpu"
    assert plan.forced is True


def test_model_selection_reads_supported_setting_without_rewriting_it(
    tmp_path: Path,
) -> None:
    settings = tmp_path / "settings.json"
    payload = {
        "local": {
            "model_name": LOWER_MEMORY_LOCAL_MODEL_ID,
            "enabled": True,
        }
    }
    settings.write_text(json.dumps(payload), encoding="utf-8")
    original = settings.read_bytes()

    assert select_model_id(settings) == LOWER_MEMORY_LOCAL_MODEL_ID
    assert settings.read_bytes() == original


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not json",
        json.dumps({"local": {"model_name": "microsoft/Phi-4-mini-instruct"}}),
    ],
)
def test_model_selection_falls_back_to_product_default(
    tmp_path: Path,
    payload: str | None,
) -> None:
    settings = tmp_path / "settings.json"
    if payload is not None:
        settings.write_text(payload, encoding="utf-8")

    assert select_model_id(settings) == PRIMARY_LOCAL_MODEL_ID


def test_poetry_sync_uses_one_explicit_windows_variant() -> None:
    executable = Path(r"C:\Tools\Poetry\poetry.exe")

    assert poetry_sync_argv(executable, "cuda") == [
        str(executable),
        "sync",
        "--with",
        "llm",
        "-E",
        "cuda",
        "--no-interaction",
    ]
    with pytest.raises(ValueError, match="cpu or cuda"):
        poetry_sync_argv(executable, "cpu,cuda")


@pytest.mark.parametrize(("ok", "expected"), [(True, 0), (False, 1)])
def test_model_adapter_waits_for_lifecycle_terminal(
    ok: bool,
    expected: int,
) -> None:
    app = _Application()
    lifecycle = _Lifecycle(ok=ok)
    progress: list[str] = []

    result = run_model_download(
        PRIMARY_LOCAL_MODEL_ID,
        r"C:\cache\models",
        lifecycle_factory=lambda: lifecycle,
        application=app,
        emit=progress.append,
    )

    assert result == expected
    assert lifecycle.requests == [(PRIMARY_LOCAL_MODEL_ID, r"C:\cache\models")]
    assert progress == ["25% Downloading", "done" if ok else "failed"]
    # A complete cache may publish terminal synchronously before the Qt loop.
    assert app.exec_calls == 0
    assert app.quit_calls == 1


def test_model_adapter_fails_when_lifecycle_rejects_admission() -> None:
    app = _Application()
    lifecycle = _Lifecycle(admitted=False)

    result = run_model_download(
        PRIMARY_LOCAL_MODEL_ID,
        r"C:\cache\models",
        lifecycle_factory=lambda: lifecycle,
        application=app,
        emit=lambda _message: None,
    )

    assert result == 2
    assert app.exec_calls == 0


def test_model_adapter_runs_event_loop_until_async_terminal() -> None:
    lifecycle = _Lifecycle(synchronous=False)
    app = _Application(on_exec=lifecycle.finish)
    progress: list[str] = []

    result = run_model_download(
        PRIMARY_LOCAL_MODEL_ID,
        r"C:\cache\models",
        lifecycle_factory=lambda: lifecycle,
        application=app,
        emit=progress.append,
    )

    assert result == 0
    assert app.exec_calls == 1
    assert app.quit_calls == 1
    assert progress == ["25% Downloading", "done"]


def test_model_adapter_ctrl_c_requests_owned_cancellation() -> None:
    lifecycle = _Lifecycle(synchronous=False)
    app = _Application(
        on_exec=lambda: signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
    )
    progress: list[str] = []

    result = run_model_download(
        PRIMARY_LOCAL_MODEL_ID,
        r"C:\cache\models",
        lifecycle_factory=lambda: lifecycle,
        application=app,
        emit=progress.append,
    )

    assert result == 1
    assert lifecycle.cancel_calls == 1
    assert app.quit_calls == 1
    assert progress == ["Cancelling model download...", "cancelled"]


def test_declining_plan_does_not_start_mutating_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = EnvironmentState(tmp_path / ".venv", "missing", "create")
    plan = {
        "source_checkout": str(tmp_path),
        "python": "python.exe",
        "compute": {"extra": "cpu", "reason": "test"},
        "poetry": {"action": "install", "version": POETRY_VERSION},
        "environment": {"path": str(environment.path), "action": "create"},
        "model": {
            "id": PRIMARY_LOCAL_MODEL_ID,
            "revision": "revision",
            "provider": "IBM",
            "license": "Apache-2.0",
            "estimated_download_gb": 6.82,
            "download_required": True,
            "cache": str(tmp_path / "models"),
        },
    }
    monkeypatch.setattr(windows_setup, "_validate_bootstrap_python", lambda: None)
    monkeypatch.setattr(windows_setup, "_validate_checkout", lambda _root: None)
    monkeypatch.setattr(windows_setup, "_nvidia_smi_output", lambda _root: "")
    monkeypatch.setattr(
        windows_setup,
        "_inspect_environment",
        lambda _path: environment,
    )
    monkeypatch.setattr(windows_setup, "user_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(windows_setup, "user_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(
        windows_setup,
        "user_model_cache_dir",
        lambda: tmp_path / "models",
    )
    monkeypatch.setattr(
        windows_setup,
        "user_settings_path",
        lambda: tmp_path / "settings.json",
    )
    monkeypatch.setattr(windows_setup, "_resolve_poetry", lambda *_args: None)
    monkeypatch.setattr(windows_setup, "_build_plan", lambda **_kwargs: plan)
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    monkeypatch.setattr(
        windows_setup,
        "_start_log",
        lambda _path: pytest.fail("decline must not create a setup log"),
    )
    monkeypatch.setattr(
        windows_setup,
        "_setup_environment",
        lambda **_kwargs: pytest.fail("decline must not start setup"),
    )

    assert windows_setup.main([]) == 10
    assert not environment.path.exists()
    assert not (tmp_path / "models").exists()


def test_invalid_environment_is_preserved_by_rename(tmp_path: Path) -> None:
    environment = tmp_path / ".venv"
    environment.mkdir()
    marker = environment / "owned.txt"
    marker.write_text("keep", encoding="utf-8")

    _recover_invalid_environment(
        EnvironmentState(environment, "invalid", "rename"),
    )

    backups = list(tmp_path.glob(".venv.invalid-*"))
    assert not environment.exists()
    assert len(backups) == 1
    assert (backups[0] / "owned.txt").read_text(encoding="utf-8") == "keep"


def test_poetry_checksum_failure_never_executes_installer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        windows_setup,
        "_download_poetry_installer",
        lambda _path: (_ for _ in ()).throw(SetupError("checksum mismatch")),
    )
    monkeypatch.setattr(
        windows_setup,
        "_run",
        lambda *_args, **_kwargs: pytest.fail("unverified installer was executed"),
    )

    with pytest.raises(SetupError, match="checksum mismatch"):
        _install_poetry(
            Path("python.exe"),
            tmp_path / "poetry",
            tmp_path,
        )


def test_existing_environment_no_launch_runs_sync_and_model_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = tmp_path / ".venv"
    python = environment / "Scripts" / "python.exe"
    poetry = tmp_path / "poetry.exe"
    commands: list[list[str]] = []

    monkeypatch.setattr(
        windows_setup,
        "_recover_invalid_environment",
        lambda _state: None,
    )
    monkeypatch.setattr(
        windows_setup,
        "_inspect_environment",
        lambda _path: EnvironmentState(environment, "valid", "reuse"),
    )
    monkeypatch.setattr(
        windows_setup,
        "_runtime_probe",
        lambda *_args: {"torch": "2.11.0+cu130", "cuda_available": True},
    )

    def record_run(argv, **_kwargs):
        commands.append([str(item) for item in argv])
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(windows_setup, "_run", record_run)
    _setup_environment(
        repo_root=tmp_path,
        bootstrap_python=Path("python.exe"),
        environment_state=EnvironmentState(environment, "valid", "reuse"),
        poetry=poetry,
        poetry_home=tmp_path / "poetry-home",
        poetry_cache=tmp_path / "poetry-cache",
        model_id=PRIMARY_LOCAL_MODEL_ID,
        model_cache=tmp_path / "models",
        compute=ComputePlan("cuda", False, "600.1", "GPU", "compatible"),
        no_launch=True,
    )

    assert any(command[:2] == [str(poetry), "sync"] for command in commands)
    assert any("--download-model" in command for command in commands)
    assert not any(str(tmp_path / "run.py") in command for command in commands)
    assert commands[-1][0] == str(python)


def test_public_windows_bootstrap_is_repo_relative_and_policy_bounded() -> None:
    cmd = (REPO_ROOT / "setup-windows.cmd").read_text(encoding="utf-8")
    powershell = (
        REPO_ROOT / "scripts" / "launchers" / "xbrainlab_windows_setup.ps1"
    ).read_text(encoding="utf-8")
    python_source = (REPO_ROOT / "scripts" / "windows_setup.py").read_text(
        encoding="utf-8"
    )

    assert "%~dp0" in cmd
    assert "-ExecutionPolicy Bypass" in cmd
    assert '"%XBRAINLAB_SETUP_PS1%" %*' in cmd
    assert "D:\\workspace" not in cmd

    assert "Python.Python.3.12" in powershell
    assert "--scope user" in powershell
    assert "windows_setup.py" in powershell
    assert "git pull" not in powershell.lower()
    assert "nvidia" not in powershell.lower()
    assert "huggingface" not in powershell.lower()

    assert POETRY_VERSION == "2.3.4"
    assert len(POETRY_INSTALLER_SHA256) == 64
    assert POETRY_INSTALLER_COMMIT in POETRY_INSTALLER_URL
    assert "snapshot_download" not in python_source
    assert "ModelDownloadLifecycle" in python_source
    assert "ensure_download" in python_source
    assert "git pull" not in python_source.lower()
    assert "shell=True" not in python_source
