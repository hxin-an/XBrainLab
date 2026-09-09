"""Reuse one native interpreter and checkout; never install or download on launch.

Run with the retained platform Python, not ``poetry run`` in a new worktree.
Only an explicitly accepted run's generated work/output is disposable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import runpy
import shutil
import stat
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from importlib import metadata
from pathlib import Path


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(  # noqa: S603 - local Git arguments, no shell.
        [shutil.which("git") or "git", "-C", str(source), *args],
        text=True,
        encoding="utf-8",
        stderr=subprocess.PIPE,
    ).strip()


def _sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("An exact lowercase 40-character commit SHA is required")
    return value


def _plain(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink() or (
            item.exists()
            and getattr(item.lstat(), "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise RuntimeError(f"Refusing a link/reparse path: {item}")


def verify_source(source: Path, sha: str) -> str:
    _plain(source)
    if git(source, "rev-parse", "HEAD") != _sha(sha):
        raise RuntimeError("Candidate SHA does not match the checkout")
    if git(source, "status", "--porcelain", "--untracked-files=normal"):
        raise RuntimeError(
            "Candidate source is modified; preserve edits before preparing"
        )
    return sha


def verify_environment(source: Path, sha: str) -> None:
    """Read target dependency metadata before switching the worktree."""
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import canonicalize_name

    project = tomllib.loads(git(source, "show", f"{_sha(sha)}:pyproject.toml"))
    if not SpecifierSet(project["project"].get("requires-python", "")).contains(
        ".".join(map(str, sys.version_info[:3]))
    ):
        raise RuntimeError("Shared Python version is incompatible with the candidate")
    lock = tomllib.loads(git(source, "show", f"{sha}:poetry.lock"))
    locked: dict[str, set[str]] = {}
    for package in lock["package"]:
        locked.setdefault(canonicalize_name(package["name"]), set()).add(
            package["version"]
        )
    required = [Requirement(text) for text in project["project"]["dependencies"]]
    # The manual entrypoint supports the current local Assistant, not just GUI imports.
    llm = project.get("tool", {}).get("poetry", {}).get("group", {}).get("llm", {})
    required.extend(Requirement(name) for name in llm.get("dependencies", {}))
    for requirement in required:
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            installed = metadata.version(requirement.name)
        except metadata.PackageNotFoundError as error:
            raise RuntimeError(
                f"Shared environment is missing {requirement.name}; synchronize it explicitly"
            ) from error
        if installed not in locked.get(canonicalize_name(requirement.name), set()):
            raise RuntimeError(
                f"Shared environment has {requirement.name} {installed}, not the candidate lock"
            )
        if requirement.specifier and not requirement.specifier.contains(installed):
            raise RuntimeError(f"Shared environment violates {requirement}")


def _assert_idle(source: Path) -> None:
    import psutil

    root = source.resolve()
    # Windows venv's redirector stays alive as our Python-named parent.
    own_chain = {os.getpid(), *(parent.pid for parent in psutil.Process().parents())}
    for process in psutil.process_iter(["pid", "name"]):
        if (
            process.pid in own_chain
            or "python" not in (process.info["name"] or "").lower()
        ):
            continue
        try:
            cwd = Path(process.cwd()).resolve()
            arguments = process.cmdline()
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as error:
            raise RuntimeError(
                "Cannot verify whether a Python process uses the source"
            ) from error
        if (
            cwd == root
            or cwd.is_relative_to(root)
            or any(
                str(root).casefold() in argument.casefold() for argument in arguments
            )
        ):
            raise RuntimeError(f"Manual source is in use by Python PID {process.pid}")


@contextmanager
def manual_lock(source: Path):
    """OS-released lease shared by prepare, launch and cleanup (no stale PID removal)."""
    path = source / "build" / "manual.lock"
    _plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("Manual environment is in use") from error
        try:
            _assert_idle(source)
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def prepare(source: Path, sha: str) -> None:
    verify_source(source, git(source, "rev-parse", "HEAD"))
    with manual_lock(source):
        verify_source(source, git(source, "rev-parse", "HEAD"))
        verify_environment(source, sha)
        git(source, "checkout", "--detach", _sha(sha))
        verify_source(source, sha)
    print(f"Prepared {sha} with {sys.executable}; no environment or model created")


def _run_root(source: Path, sha: str) -> Path:
    path = source / "build" / "manual-runs" / _sha(sha)
    _plain(path)
    return path


def _identity(source: Path, sha: str) -> dict[str, str]:
    return {"source": str(source.resolve()), "sha": _sha(sha)}


def _verify_run(source: Path, sha: str) -> Path:
    path = _run_root(source, sha)
    marker = path / "source.json"
    _plain(marker)
    if not marker.is_file() or json.loads(marker.read_text()) != _identity(source, sha):
        raise RuntimeError("Manual run identity is missing or does not match")
    return path


def create_run(source: Path, sha: str) -> Path:
    path = _run_root(source, sha)
    if path.exists():
        return _verify_run(source, sha)
    path.mkdir(parents=True)
    (path / "source.json").write_text(
        json.dumps(_identity(source, sha)), encoding="utf-8"
    )
    (path / "work").mkdir()
    return path


def clean_run(source: Path, sha: str, *, apply: bool, accepted: bool) -> int:
    with manual_lock(source):
        path = _verify_run(source, sha) / "work" / "output"
        _plain(path)
        if not path.exists():
            return 0
        size = 0
        for folder, directories, files in os.walk(path, followlinks=False):
            for name in (*directories, *files):
                child = Path(folder) / name
                _plain(child)
                if not child.is_dir():
                    if not child.is_file():
                        raise RuntimeError("Unknown output entry; refusing cleanup")
                    size += child.stat().st_size
        print(f"{'REMOVE' if apply else 'PREVIEW'} {size} bytes: {path}")
        if apply:
            if not accepted:
                raise RuntimeError(
                    "Explicit manual acceptance is required before cleanup"
                )
            shutil.rmtree(path)
        return size


def runtime_environment(run: Path, cache: Path) -> dict[str, str]:
    """Keep manual state local while sharing only model/embedding caches."""
    return {
        "XBRAINLAB_CONFIG_DIR": str(run / "runtime"),
        "XBRAINLAB_LOG_DIR": str(run / "logs"),
        "XBRAINLAB_DATA_DIR": str(run / "data"),
        "XBRAINLAB_CACHE_DIR": str(run / "cache"),
        "QT_QPA_PLATFORM": "windows",
        "MNE_DONTWRITE_HOME": "true",
        "XBRAINLAB_MODEL_CACHE_DIR": str(cache / "models"),
        "XBRAINLAB_RAG_CACHE_DIR": str(cache / "rag"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }


def launch(source: Path, sha: str, cache: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("Manual GUI handoff requires native Windows Python")
    verify_source(source, sha)
    verify_environment(source, sha)
    with manual_lock(source):
        verify_source(source, sha)
        run = _run_root(source, sha)
        for name in ("runtime", "logs", "data", "cache", "work", "qt-settings"):
            _plain(run / name)
        # Product imports may initialize logging, so establish ownership first.
        create_run(source, sha)
        os.environ.update(runtime_environment(run, cache))
        # Load the existing provenance guard directly: importing the scripts.dev
        # namespace first would merge the shared env's editable checkout path.
        guard = runpy.run_path(str(source / "scripts" / "dev" / "active_checkout.py"))
        guard["assert_active_checkout_import"](source)
        from XBrainLab.llm.core.config import LLMConfig
        from XBrainLab.llm.rag.config import RAGConfig

        if (
            not LLMConfig().has_local_model_cache()
            or not RAGConfig.embedding_cache_ready()
        ):
            raise RuntimeError(
                "Pinned model or embedding cache is missing; no download attempted"
            )
        from PyQt6.QtCore import QSettings

        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            str(run / "qt-settings"),
        )
        os.chdir(run / "work")
        print(
            f"Native Windows manual source: {sha}\nPython: {sys.executable}", flush=True
        )
        print(f"Generated test output: {run / 'work' / 'output'}", flush=True)
        print(
            "Use this PowerShell console as the live log. Export kept results outside this run.",
            flush=True,
        )
        sys.argv = [str(source / "run.py")]
        runpy.run_path(str(source / "run.py"), run_name="__main__")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "launch", "clean"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--cache", type=Path, default=Path("D:/XBrainLabCache"))
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete only the named run's generated output",
    )
    parser.add_argument(
        "--accepted",
        action="store_true",
        help="User accepted this run; kept results have been exported",
    )
    args = parser.parse_args()
    source = args.source.absolute()
    try:
        if args.action == "prepare":
            prepare(source, args.sha)
        elif args.action == "check":
            verify_source(source, args.sha)
            verify_environment(source, args.sha)
            with manual_lock(source):
                print(f"Source/environment ready: {args.sha}; Python: {sys.executable}")
        elif args.action == "launch":
            launch(source, args.sha, args.cache)
        else:
            clean_run(source, args.sha, apply=args.apply, accepted=args.accepted)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Manual environment refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
