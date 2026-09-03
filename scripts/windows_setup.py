#!/usr/bin/env python3
"""Reproducible one-command bootstrap for a Windows source checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from XBrainLab.llm.core.model_catalog import (
    allowed_local_model_ids,
    default_local_model_id,
    local_model_spec,
    plan_model_download,
)
from XBrainLab.platform_paths import (
    user_cache_dir,
    user_data_dir,
    user_log_dir,
    user_model_cache_dir,
    user_settings_path,
)

POETRY_VERSION = "2.3.4"
POETRY_INSTALLER_COMMIT = (
    "d7fd0502ef807e711f65204b1ab39c1a1e23c69c"  # pragma: allowlist secret
)
POETRY_INSTALLER_URL = (
    "https://raw.githubusercontent.com/python-poetry/"
    f"install.python-poetry.org/{POETRY_INSTALLER_COMMIT}/install-poetry.py"
)
POETRY_INSTALLER_SHA256 = "75745ca71373a7b22fa150953543f03d826a52f8e4bc4350328a33bddd668026"  # pragma: allowlist secret
CUDA_MINIMUM_DRIVER_MAJOR = 580
MINIMUM_NEW_ENV_FREE_BYTES = 6_000_000_000
MAXIMUM_INSTALLER_BYTES = 1_000_000
MAXIMUM_SETUP_LOG_BYTES = 1_000_000
SETUP_LOG_RETENTION = 5
LOGGER = logging.getLogger("xbrainlab.windows_setup")


class SetupError(RuntimeError):
    """A recoverable setup failure with user-facing guidance."""


@dataclass(frozen=True)
class ComputePlan:
    """One explicit Windows PyTorch variant selection."""

    extra: str
    forced: bool
    driver_version: str | None
    gpu_name: str | None
    reason: str


@dataclass(frozen=True)
class EnvironmentState:
    """Inspection of the repository-local Windows virtual environment."""

    path: Path
    status: str
    detail: str


def _start_log(directory: Path) -> Path:
    """Start one bounded coordinator log without capturing child output."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "windows-setup.log"
    handler = RotatingFileHandler(
        path,
        maxBytes=MAXIMUM_SETUP_LOG_BYTES,
        backupCount=SETUP_LOG_RETENTION - 1,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    for existing in LOGGER.handlers:
        existing.close()
    LOGGER.handlers.clear()
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    return path


def choose_compute_plan(
    nvidia_smi_output: str,
    *,
    force_cpu: bool,
) -> ComputePlan:
    """Select CUDA only for an NVIDIA driver compatible with CUDA 13."""
    driver_version: str | None = None
    gpu_name: str | None = None
    first_line = next(
        (line.strip() for line in nvidia_smi_output.splitlines() if line.strip()),
        "",
    )
    if first_line:
        driver_text, separator, name = first_line.partition(",")
        driver_version = driver_text.strip() or None
        gpu_name = name.strip() if separator and name.strip() else None

    if force_cpu:
        return ComputePlan(
            extra="cpu",
            forced=True,
            driver_version=driver_version,
            gpu_name=gpu_name,
            reason="CPU was explicitly requested.",
        )

    try:
        driver_major = int(str(driver_version or "").split(".", maxsplit=1)[0])
    except ValueError:
        driver_major = 0
    if driver_major >= CUDA_MINIMUM_DRIVER_MAJOR:
        return ComputePlan(
            extra="cuda",
            forced=False,
            driver_version=driver_version,
            gpu_name=gpu_name,
            reason=(
                f"NVIDIA driver {driver_version} meets the R"
                f"{CUDA_MINIMUM_DRIVER_MAJOR}+ requirement."
            ),
        )
    if driver_version:
        reason = (
            f"NVIDIA driver {driver_version} is older than R"
            f"{CUDA_MINIMUM_DRIVER_MAJOR}; using CPU."
        )
    else:
        reason = "No compatible NVIDIA driver was detected; using CPU."
    return ComputePlan(
        extra="cpu",
        forced=False,
        driver_version=driver_version,
        gpu_name=gpu_name,
        reason=reason,
    )


def select_model_id(settings_path: Path) -> str:
    """Read a supported persisted model choice without modifying settings."""
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        model_id = str(payload.get("local", {}).get("model_name", "")).strip()
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        model_id = ""
    return (
        model_id if model_id in allowed_local_model_ids() else default_local_model_id()
    )


def poetry_sync_argv(poetry: Path, extra: str) -> list[str]:
    """Build the one supported Poetry sync command for Windows."""
    if extra not in {"cpu", "cuda"}:
        raise ValueError("Windows Poetry extra must be cpu or cuda.")
    return [
        str(poetry),
        "sync",
        "--with",
        "llm",
        "-E",
        extra,
        "--no-interaction",
    ]


def run_model_download(
    model_id: str,
    cache_dir: str,
    *,
    lifecycle_factory: Callable[[], Any] | None = None,
    application: Any | None = None,
    emit: Callable[[str], None] = print,
) -> int:
    """Run the existing application-owned model lifecycle from a CLI process."""
    if lifecycle_factory is None:
        from PyQt6.QtCore import QCoreApplication

        from XBrainLab.llm.core.model_download_lifecycle import (
            ModelDownloadLifecycle,
        )

        lifecycle_factory = ModelDownloadLifecycle
        application = application or QCoreApplication.instance() or QCoreApplication([])
    elif application is None:
        raise ValueError("An application is required with an injected lifecycle.")

    lifecycle = lifecycle_factory()
    terminal: list[bool] = []

    def on_progress(percent: int, message: str) -> None:
        emit(f"{percent}% {message}")

    def on_terminal(ok: bool, message: str) -> None:
        terminal.append(bool(ok))
        emit(message)
        application.quit()

    lifecycle.progress.connect(on_progress)
    lifecycle.terminal.connect(on_terminal)
    if not lifecycle.ensure_download(model_id, cache_dir):
        emit("Model download could not start because the lifecycle is busy.")
        return 2
    if terminal:
        return 0 if terminal[-1] else 1

    previous_handler: Any = None
    can_handle_signal = hasattr(signal, "SIGINT")
    if can_handle_signal:
        previous_handler = signal.getsignal(signal.SIGINT)

        def request_cancel(_signum: int, _frame: Any) -> None:
            emit("Cancelling model download...")
            lifecycle.request_cancel()

        signal.signal(signal.SIGINT, request_cancel)
    try:
        application.exec()
    finally:
        if can_handle_signal:
            signal.signal(signal.SIGINT, previous_handler)
    if not terminal:
        emit("Model download stopped without a terminal result.")
        return 3
    return 0 if terminal[-1] else 1


def _run(
    argv: Sequence[str | Path],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    capture: bool = False,
    stage: str,
) -> subprocess.CompletedProcess[str]:
    command = [str(item) for item in argv]
    print(f"\n[{stage}]")
    LOGGER.info("started: %s", stage)
    result = subprocess.run(  # noqa: S603 - argv is built from owned setup paths.
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=False,
    )
    if result.returncode != 0:
        LOGGER.error("failed (%s): %s", result.returncode, stage)
        detail = ""
        if capture:
            detail = (result.stderr or result.stdout or "").strip()
        suffix = f" {detail}" if detail else ""
        raise SetupError(f"{stage} failed with exit code {result.returncode}.{suffix}")
    LOGGER.info("completed: %s", stage)
    return result


def _nvidia_smi_output(repo_root: Path) -> str:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return ""
    try:
        result = subprocess.run(  # noqa: S603 - executable comes from PATH lookup.
            [
                executable,
                "--query-gpu=driver_version,name",
                "--format=csv,noheader",
            ],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return ""
    return result.stdout if result.returncode == 0 else ""


def _inspect_environment(path: Path) -> EnvironmentState:
    if not path.exists():
        return EnvironmentState(path, "missing", "A new environment will be created.")
    python = path / "Scripts" / "python.exe"
    if not python.is_file():
        return EnvironmentState(
            path,
            "invalid",
            "The existing .venv is not a Windows Python environment.",
        )
    probe = (
        "import json,os,struct,sys;"
        "print(json.dumps({'version':list(sys.version_info[:2]),"
        "'bits':struct.calcsize('P')*8,'os_name':os.name}))"
    )
    try:
        result = subprocess.run(  # noqa: S603 - executable is the owned .venv Python.
            [str(python), "-c", probe],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return EnvironmentState(
            path,
            "invalid",
            "The existing .venv cannot start and will be renamed, not deleted.",
        )
    try:
        payload = json.loads(result.stdout.strip())
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    if (
        result.returncode == 0
        and payload.get("version") == [3, 12]
        and payload.get("bits") == 64
        and payload.get("os_name") == "nt"
    ):
        return EnvironmentState(
            path,
            "valid",
            "Existing Windows Python 3.12 x64 environment will be repaired in place.",
        )
    return EnvironmentState(
        path,
        "invalid",
        "The existing .venv is incompatible and will be renamed, not deleted.",
    )


def _candidate_poetry_paths(tool_home: Path) -> list[Path]:
    candidates = [tool_home / "bin" / "poetry.exe"]
    on_path = shutil.which("poetry")
    if on_path:
        candidates.append(Path(on_path))
    appdata = str(os.environ.get("APPDATA", "")).strip()
    if appdata:
        base = Path(appdata)
        candidates.extend(
            [
                base / "Python" / "Scripts" / "poetry.exe",
                base / "pypoetry" / "venv" / "Scripts" / "poetry.exe",
            ]
        )
    return candidates


def _poetry_version(path: Path, repo_root: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        result = subprocess.run(  # noqa: S603 - resolved Poetry path.
            [str(path), "--version"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    prefix = "Poetry (version "
    return (
        output[len(prefix) : -1]
        if output.startswith(prefix) and output.endswith(")")
        else None
    )


def _resolve_poetry(tool_home: Path, repo_root: Path) -> Path | None:
    seen: set[str] = set()
    for candidate in _candidate_poetry_paths(tool_home):
        key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)
        if _poetry_version(candidate, repo_root) == POETRY_VERSION:
            return candidate
    return None


def _download_poetry_installer(destination: Path) -> None:
    request = urllib.request.Request(  # noqa: S310 - URL is a pinned HTTPS constant.
        POETRY_INSTALLER_URL,
        headers={"User-Agent": "XBrainLab-Windows-Setup/1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        if urllib.parse.urlparse(response.geturl()).scheme.casefold() != "https":
            raise SetupError("The Poetry installer redirect was not HTTPS.")
        payload = response.read(MAXIMUM_INSTALLER_BYTES + 1)
    if len(payload) > MAXIMUM_INSTALLER_BYTES:
        raise SetupError("The Poetry installer exceeded the expected size limit.")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != POETRY_INSTALLER_SHA256:
        raise SetupError(
            "The Poetry installer checksum did not match the pinned official copy."
        )
    destination.write_bytes(payload)


def _install_poetry(
    python: Path,
    tool_home: Path,
    repo_root: Path,
) -> Path:
    tool_home.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="xbrainlab-poetry-") as temporary:
        installer = Path(temporary) / "install-poetry.py"
        print("\n[Install Poetry 2.3.4]")
        LOGGER.info("started: download verified Poetry installer")
        try:
            _download_poetry_installer(installer)
        except Exception:
            LOGGER.exception("failed: download verified Poetry installer")
            raise
        LOGGER.info("completed: download verified Poetry installer")
        install_env = os.environ.copy()
        install_env["POETRY_HOME"] = str(tool_home)
        _run(
            [python, installer, "--version", POETRY_VERSION, "--yes"],
            cwd=repo_root,
            env=install_env,
            stage=f"Install Poetry {POETRY_VERSION}",
        )
    poetry = tool_home / "bin" / "poetry.exe"
    if _poetry_version(poetry, repo_root) != POETRY_VERSION:
        raise SetupError("Poetry 2.3.4 was not available after installation.")
    return poetry


def _recover_invalid_environment(state: EnvironmentState) -> None:
    if state.status != "invalid":
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = state.path.with_name(f"{state.path.name}.invalid-{stamp}")
    suffix = 1
    while candidate.exists():
        candidate = state.path.with_name(f"{state.path.name}.invalid-{stamp}-{suffix}")
        suffix += 1
    state.path.rename(candidate)
    print(f"Preserved incompatible environment at: {candidate}")
    LOGGER.info("renamed incompatible environment to %s", candidate)


def _runtime_probe(
    python: Path, repo_root: Path, compute: ComputePlan
) -> dict[str, Any]:
    probe = """
import json
import torch
import torchaudio
import torchvision
import PyQt6
import transformers
import bitsandbytes
print(json.dumps({
    "python": list(__import__("sys").version_info[:2]),
    "torch": torch.__version__,
    "torchvision": torchvision.__version__,
    "torchaudio": torchaudio.__version__,
    "cuda_runtime": torch.version.cuda,
    "cuda_available": torch.cuda.is_available(),
}))
"""
    result = subprocess.run(  # noqa: S603 - executable is the owned .venv Python.
        [str(python), "-c", probe],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SetupError(f"Runtime import verification failed. {detail}")
    payload: dict[str, Any] | None = None
    for line in reversed(result.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            payload = candidate
            break
    if payload is None:
        raise SetupError("Runtime verification did not return a readable result.")

    suffix = "+cu130" if compute.extra == "cuda" else "+cpu"
    expected = {
        "torch": f"2.11.0{suffix}",
        "torchvision": f"0.26.0{suffix}",
        "torchaudio": f"2.11.0{suffix}",
    }
    if payload.get("python") != [3, 12] or any(
        payload.get(name) != version for name, version in expected.items()
    ):
        raise SetupError(
            "Runtime verification found dependency versions that do not match "
            f"the selected {compute.extra} environment."
        )
    if compute.extra == "cuda":
        if (
            payload.get("cuda_runtime") != "13.0"
            or payload.get("cuda_available") is not True
        ):
            raise SetupError(
                "CUDA 13.0 was installed but the GPU is unavailable. Update the "
                "NVIDIA driver or rerun setup-windows.cmd -Cpu."
            )
    elif payload.get("cuda_available") is not False:
        raise SetupError("The CPU environment unexpectedly exposed CUDA.")
    return payload


def _validate_checkout(repo_root: Path) -> None:
    required = ("pyproject.toml", "poetry.lock", "run.py")
    missing = [name for name in required if not (repo_root / name).is_file()]
    if missing:
        raise SetupError(
            "This command must run from a complete XBrainLab source checkout. "
            f"Missing: {', '.join(missing)}."
        )


def _validate_bootstrap_python() -> None:
    if (
        os.name != "nt"
        or sys.version_info[:2] != (3, 12)
        or struct.calcsize("P") * 8 != 64
    ):
        raise SetupError(
            "Windows CPython 3.12 x64 is required. Run setup-windows.cmd "
            "instead of invoking this script directly."
        )


def _build_plan(
    *,
    repo_root: Path,
    compute: ComputePlan,
    environment: EnvironmentState,
    poetry: Path | None,
    poetry_home: Path,
    model_id: str,
    model_cache: Path,
) -> dict[str, Any]:
    spec = local_model_spec(model_id)
    if spec is None:
        raise SetupError(f"Unsupported local model selection: {model_id}.")
    model_plan = plan_model_download(model_id, str(model_cache))
    if not model_plan.ok:
        raise SetupError(model_plan.message)
    if environment.status != "valid":
        free_bytes = shutil.disk_usage(repo_root).free
        if free_bytes < MINIMUM_NEW_ENV_FREE_BYTES:
            raise SetupError(
                "At least 6 GB of free space is required on the checkout drive "
                "to create the Windows environment."
            )
    return {
        "source_checkout": str(repo_root),
        "python": sys.executable,
        "compute": asdict(compute),
        "poetry": {
            "version": POETRY_VERSION,
            "executable": str(poetry) if poetry is not None else None,
            "action": "reuse" if poetry is not None else "install verified copy",
            "install_location": str(poetry_home),
        },
        "environment": {
            "path": str(environment.path),
            "status": environment.status,
            "action": environment.detail,
        },
        "model": {
            "id": model_id,
            "revision": spec.revision,
            "provider": spec.provider,
            "license": spec.license,
            "estimated_download_gb": spec.estimated_download_gb,
            "download_required": model_plan.estimated_download_bytes > 0,
            "cache": str(model_cache),
        },
    }


def _print_plan(plan: dict[str, Any]) -> None:
    compute = plan["compute"]
    poetry = plan["poetry"]
    environment = plan["environment"]
    model = plan["model"]
    print("\nXBrainLab Windows setup plan")
    print(f"  Source:      {plan['source_checkout']}")
    print(f"  Python:      {plan['python']}")
    print(f"  Compute:     {str(compute['extra']).upper()}")
    print(f"               {compute['reason']}")
    print(f"  Poetry:      {poetry['action']} (version {poetry['version']})")
    print(f"  Environment: {environment['path']}")
    print(f"               {environment['action']}")
    print(f"  Model:       {model['id']}")
    print(f"               revision {model['revision']}")
    print(
        f"               {model['provider']} / {model['license']} / "
        f"up to {model['estimated_download_gb']:.2f} GB"
    )
    print(f"  Model cache: {model['cache']}")
    print("\nDependency downloads and the .venv may require several additional GB.")
    if model["download_required"]:
        print("The selected model is not complete in the cache and will be downloaded.")
    else:
        print(
            "The selected model is already complete; it will not be downloaded again."
        )


def _confirm() -> bool:
    try:
        answer = input("\nContinue with these changes? [y/N]: ")
    except EOFError:
        return False
    return answer.strip().casefold() in {"y", "yes"}


def _setup_environment(
    *,
    repo_root: Path,
    bootstrap_python: Path,
    environment_state: EnvironmentState,
    poetry: Path | None,
    poetry_home: Path,
    poetry_cache: Path,
    model_id: str,
    model_cache: Path,
    compute: ComputePlan,
    no_launch: bool,
) -> None:
    _recover_invalid_environment(environment_state)
    if poetry is None:
        poetry = _install_poetry(
            bootstrap_python,
            poetry_home,
            repo_root,
        )
    else:
        LOGGER.info("reusing Poetry %s", POETRY_VERSION)

    setup_env = os.environ.copy()
    setup_env["POETRY_CACHE_DIR"] = str(poetry_cache)
    setup_env["POETRY_VIRTUALENVS_IN_PROJECT"] = "true"
    setup_env["POETRY_INSTALLER_RE_RESOLVE"] = "true"
    setup_env["XBRAINLAB_MODEL_CACHE_DIR"] = str(model_cache)

    _run(
        [poetry, "config", "virtualenvs.in-project", "true", "--local"],
        cwd=repo_root,
        env=setup_env,
        stage="Configure repository-local environment",
    )
    _run(
        [poetry, "config", "installer.re-resolve", "true", "--local"],
        cwd=repo_root,
        env=setup_env,
        stage="Configure deterministic Poetry resolution",
    )
    _run(
        [poetry, "env", "use", bootstrap_python],
        cwd=repo_root,
        env=setup_env,
        stage="Select Windows Python 3.12",
    )
    _run(
        poetry_sync_argv(poetry, compute.extra),
        cwd=repo_root,
        env=setup_env,
        stage=f"Install XBrainLab dependencies ({compute.extra})",
    )

    environment_python = repo_root / ".venv" / "Scripts" / "python.exe"
    ready_state = _inspect_environment(repo_root / ".venv")
    if ready_state.status != "valid":
        raise SetupError(
            "Poetry finished, but the repository .venv is not a valid "
            "Windows Python 3.12 x64 environment."
        )
    runtime = _runtime_probe(environment_python, repo_root, compute)
    print(
        "\nRuntime verified: "
        f"{runtime['torch']}, CUDA available={runtime['cuda_available']}."
    )
    LOGGER.info(
        "runtime verified: "
        f"{runtime['torch']}, CUDA available={runtime['cuda_available']}"
    )

    _run(
        [
            environment_python,
            Path(__file__).resolve(),
            "--download-model",
            model_id,
            "--cache-dir",
            model_cache,
        ],
        cwd=repo_root,
        env=setup_env,
        stage="Prepare local Assistant model",
    )

    print("\nXBrainLab setup is complete.")
    LOGGER.info("setup complete")
    if no_launch:
        print("Launch later with: .\\.venv\\Scripts\\python.exe run.py --model local")
        return

    _run(
        [environment_python, repo_root / "run.py", "--model", "local"],
        cwd=repo_root,
        env=setup_env,
        stage="Launch XBrainLab",
    )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and launch XBrainLab from a Windows source checkout."
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Use official CPU PyTorch wheels even when a compatible GPU exists.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Accept the displayed setup plan without prompting.",
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Prepare and verify the environment without launching the app.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print the non-mutating setup plan as JSON.",
    )
    parser.add_argument("--download-model", help=argparse.SUPPRESS)
    parser.add_argument("--cache-dir", help=argparse.SUPPRESS)
    return parser


def _run_internal_model_download(model_id: str, cache_dir: str | None) -> int:
    if model_id not in allowed_local_model_ids():
        raise SetupError("The requested model is not in the product catalog.")
    if not cache_dir:
        raise SetupError("The internal model download requires a cache path.")
    return run_model_download(
        model_id,
        str(Path(cache_dir).expanduser().resolve()),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        _validate_bootstrap_python()
        _validate_checkout(REPO_ROOT)
        if args.download_model:
            return _run_internal_model_download(
                args.download_model,
                args.cache_dir,
            )

        compute = choose_compute_plan(
            _nvidia_smi_output(REPO_ROOT),
            force_cpu=bool(args.cpu),
        )
        environment = _inspect_environment(REPO_ROOT / ".venv")
        data_root = user_data_dir()
        poetry_home = data_root / "tools" / f"poetry-{POETRY_VERSION}"
        poetry_cache = user_cache_dir() / "poetry"
        model_cache = user_model_cache_dir()
        model_id = select_model_id(user_settings_path())
        poetry = _resolve_poetry(poetry_home, REPO_ROOT)
        plan = _build_plan(
            repo_root=REPO_ROOT,
            compute=compute,
            environment=environment,
            poetry=poetry,
            poetry_home=poetry_home,
            model_id=model_id,
            model_cache=model_cache,
        )
        if args.plan_only:
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0

        _print_plan(plan)
        if not args.yes and not _confirm():
            print("Setup cancelled. No project environment changes were made.")
            return 10

        log_path = _start_log(user_log_dir())
        print(f"Setup log: {log_path}")
        LOGGER.info("setup accepted")
        try:
            _setup_environment(
                repo_root=REPO_ROOT,
                bootstrap_python=Path(sys.executable),
                environment_state=environment,
                poetry=poetry,
                poetry_home=poetry_home,
                poetry_cache=poetry_cache,
                model_id=model_id,
                model_cache=model_cache,
                compute=compute,
                no_launch=bool(args.no_launch),
            )
        except Exception as exc:
            LOGGER.exception("setup failed: %s: %s", type(exc).__name__, exc)
            raise
        else:
            return 0
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        return 130
    except SetupError as exc:
        print(f"\nSetup error: {exc}", file=sys.stderr)
        print(
            "Fix the reported issue, then run setup-windows.cmd again.", file=sys.stderr
        )
        return 1
    except (OSError, subprocess.SubprocessError) as exc:
        print(
            f"\nSetup error: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        print(
            "The existing downloads were kept; run setup-windows.cmd again.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(
            f"\nUnexpected setup error: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        print(
            "The existing downloads were kept; run setup-windows.cmd again.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(main())
