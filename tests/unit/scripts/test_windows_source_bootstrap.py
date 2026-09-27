from __future__ import annotations

import io
import json
import signal
import subprocess
from pathlib import Path

import pytest

from scripts import windows_setup
from scripts.windows_setup import (
    CUDA_MINIMUM_DRIVER_MAJOR,
    MAXIMUM_INSTALLER_BYTES,
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
        "null",
        "[]",
        json.dumps({"local": None}),
        json.dumps({"local": []}),
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
    if payload is not None:
        assert settings.read_text(encoding="utf-8") == payload
    else:
        assert not settings.exists()


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
        "rag": {
            "id": "sentence-transformers/all-MiniLM-L6-v2",
            "revision": "pinned",
            "source": "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2",
            "license": "Apache-2.0",
            "estimated_download_gb": 0.10,
            "download_required": True,
            "cache": str(tmp_path / "rag" / "models"),
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


@pytest.mark.parametrize(
    ("final_url", "payload", "error", "expected_read_sizes"),
    [
        (
            "http://example.invalid/install-poetry.py",
            b"not read when the redirect is insecure",
            "redirect was not HTTPS",
            [],
        ),
        (
            "https://example.invalid/install-poetry.py",
            b"x" * (MAXIMUM_INSTALLER_BYTES + 1),
            "exceeded the expected size limit",
            [MAXIMUM_INSTALLER_BYTES + 1],
        ),
        (
            "https://example.invalid/install-poetry.py",
            b"wrong checksum fixture",
            "checksum did not match",
            [MAXIMUM_INSTALLER_BYTES + 1],
        ),
    ],
    ids=["insecure-redirect", "oversized-body", "checksum-mismatch"],
)
def test_poetry_installer_rejection_never_writes_or_executes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_url: str,
    payload: bytes,
    error: str,
    expected_read_sizes: list[int],
) -> None:
    class FakeInstallerResponse(io.BytesIO):
        def __init__(self, body: bytes, url: str) -> None:
            super().__init__(body)
            self.url = url
            self.read_sizes: list[int] = []

        def geturl(self) -> str:
            return self.url

        def read(self, size: int = -1) -> bytes:
            self.read_sizes.append(size)
            return super().read(size)

    responses: list[FakeInstallerResponse] = []
    calls: list[tuple[object, int]] = []

    def fake_urlopen(request: object, timeout: int) -> FakeInstallerResponse:
        calls.append((request, timeout))
        response = FakeInstallerResponse(payload, final_url)
        responses.append(response)
        return response

    monkeypatch.setattr(
        windows_setup.urllib.request,
        "urlopen",
        fake_urlopen,
    )
    monkeypatch.setattr(
        windows_setup,
        "_run",
        lambda *_args, **_kwargs: pytest.fail("unverified installer was executed"),
    )
    destination = tmp_path / "install-poetry.py"

    with pytest.raises(SetupError, match=error):
        windows_setup._download_poetry_installer(destination)
    assert not destination.exists()

    with pytest.raises(SetupError, match=error):
        _install_poetry(
            Path("python.exe"),
            tmp_path / "poetry",
            tmp_path,
        )

    assert len(calls) == 2
    assert [timeout for _request, timeout in calls] == [60, 60]
    assert [response.read_sizes for response in responses] == [
        expected_read_sizes,
        expected_read_sizes,
    ]


def test_verified_poetry_installer_fixture_writes_exact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = b"verified installer fixture\n"
    fixture_digest = "c78518d18e57979ae32c87d35c08ee20eb388d98b488c568162e57734dcfab79"  # pragma: allowlist secret - SHA256 of public test bytes

    class FakeInstallerResponse(io.BytesIO):
        def geturl(self) -> str:
            return "https://example.invalid/install-poetry.py"

    response = FakeInstallerResponse(fixture)
    timeouts: list[int] = []

    def fake_urlopen(_request: object, timeout: int) -> FakeInstallerResponse:
        timeouts.append(timeout)
        return response

    monkeypatch.setattr(windows_setup.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(windows_setup, "POETRY_INSTALLER_SHA256", fixture_digest)
    destination = tmp_path / "install-poetry.py"

    windows_setup._download_poetry_installer(destination)

    assert timeouts == [60]
    assert destination.read_bytes() == fixture


def test_existing_environment_no_launch_prepares_both_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = tmp_path / ".venv"
    python = environment / "Scripts" / "python.exe"
    poetry = tmp_path / "poetry.exe"
    commands: list[list[str]] = []
    monkeypatch.setattr(windows_setup, "user_rag_cache_dir", lambda: tmp_path / "rag")

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
    assert any("--prepare-rag" in command for command in commands)
    assert commands[-1][-1] == "--prepare-rag"
    assert not any(str(tmp_path / "run.py") in command for command in commands)
    assert commands[-1][0] == str(python)


def test_setup_plan_exposes_pinned_embedding_without_creating_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rag_root = tmp_path / "RAG 新機 cache"
    monkeypatch.setattr(windows_setup, "user_rag_cache_dir", lambda: rag_root)
    plan = windows_setup._build_plan(
        repo_root=tmp_path,
        compute=ComputePlan("cpu", True, None, None, "test"),
        environment=EnvironmentState(tmp_path / ".venv", "valid", "reuse"),
        poetry=None,
        poetry_home=tmp_path / "poetry",
        model_id=PRIMARY_LOCAL_MODEL_ID,
        model_cache=tmp_path / "models",
    )
    rag = plan["rag"]
    assert rag["revision"] == windows_setup.RAG_EMBEDDING_SPEC.revision
    assert rag["source"].startswith("https://huggingface.co/sentence-transformers/")
    assert rag["license"] == "Apache-2.0"
    assert rag["estimated_download_gb"] == 0.10
    assert rag["download_required"] is True
    assert rag["cache"] == str(rag_root / "models")
    assert not rag_root.exists()


def test_combined_cache_budget_rechecks_actual_growth_across_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rag_root = tmp_path / "rag"
    model_root = tmp_path / "generation"
    monkeypatch.setattr(windows_setup, "user_rag_cache_dir", lambda: rag_root)
    sizes = {
        str(model_root.resolve()): 19_950_000_000,
        str((rag_root / "models").resolve()): 90_000_000,
    }
    monkeypatch.setattr(windows_setup, "cache_usage_bytes", sizes.__getitem__)
    with pytest.raises(SetupError, match=r"Combined.*20 GB"):
        windows_setup._check_combined_cache_budget(model_root)
    sizes[str(model_root.resolve())] = 19_850_000_000
    windows_setup._check_combined_cache_budget(model_root)
    with pytest.raises(SetupError, match=r"Combined.*20 GB"):
        windows_setup._check_combined_cache_budget(
            model_root, pending_download_bytes=100_000_000
        )


def test_rag_setup_verifies_offline_after_successful_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = []
    verification = []
    monkeypatch.setattr(windows_setup, "user_rag_cache_dir", lambda: tmp_path / "RAG")

    def download(model_id, cache):
        requests.append((model_id, cache))
        return 0

    def run(argv, **kwargs):
        verification.append((argv, kwargs))

    monkeypatch.setattr(windows_setup, "run_model_download", download)
    monkeypatch.setattr(windows_setup, "_run", run)
    assert windows_setup.prepare_rag() == 0
    assert requests == [
        ("sentence-transformers/all-MiniLM-L6-v2", str(tmp_path / "RAG" / "models"))
    ]
    argv, options = verification[0]
    assert argv[-1] == "--verify-rag-offline"
    assert Path(argv[-2]).name == "windows_setup.py"
    assert options["env"]["HF_HUB_OFFLINE"] == "1"
    assert options["env"]["TRANSFORMERS_OFFLINE"] == "1"
    assert options["env"]["CUDA_VISIBLE_DEVICES"] == ""
    assert options["timeout"] == 180


@pytest.mark.parametrize("download_result", [1, 2, 3, 130])
def test_rag_setup_does_not_verify_or_succeed_after_download_failure(
    monkeypatch: pytest.MonkeyPatch, download_result: int
) -> None:
    monkeypatch.setattr(
        windows_setup, "run_model_download", lambda *_args: download_result
    )
    monkeypatch.setattr(
        windows_setup, "_run", lambda *_args, **_kwargs: pytest.fail("must stop")
    )
    assert windows_setup.prepare_rag() == download_result


def test_rag_setup_propagates_offline_verification_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(windows_setup, "run_model_download", lambda *_args: 0)

    def reject(*_args, **_kwargs):
        raise SetupError("Offline RAG verification failed")

    monkeypatch.setattr(windows_setup, "_run", reject)
    with pytest.raises(SetupError, match="Offline RAG"):
        windows_setup.prepare_rag()


def test_offline_install_probe_rejects_missing_cache_without_creating_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "empty RAG cache"
    monkeypatch.setenv("XBRAINLAB_RAG_CACHE_DIR", str(root))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    with pytest.raises(SetupError, match="Pinned RAG embedding"):
        windows_setup.verify_rag_offline()
    assert not root.exists()


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
