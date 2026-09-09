"""Shared temporary-path policy for XBrainLab test processes."""

from __future__ import annotations

import os
import tempfile
from hashlib import sha256
from pathlib import Path


def select_test_temp_root(repo_root: Path) -> Path:
    """Choose a fast test root without expanding the WSL system VHD."""
    override = os.environ.get("XBRAINLAB_TEST_TMPDIR")
    if override:
        return Path(override).expanduser().resolve()

    resolved_repo = repo_root.resolve()
    shared_memory_root = Path("/dev/shm")  # noqa: S108 - bounded WSL tmpfs
    if (
        os.environ.get("WSL_DISTRO_NAME")
        and shared_memory_root.is_dir()
        and os.access(shared_memory_root, os.W_OK)
    ):
        repo_digest = sha256(str(resolved_repo).encode("utf-8")).hexdigest()[:12]
        user_id = getattr(os, "getuid", lambda: 0)()
        return shared_memory_root / (f"xbrainlab-pytest-{user_id}-{repo_digest}")
    return resolved_repo / ".test-tmp"


def configure_test_temp_root(repo_root: Path) -> Path:
    """Apply the selected root to Python and child test processes."""
    test_temp_root = select_test_temp_root(repo_root)
    test_temp_root.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(test_temp_root)
    tempfile.tempdir = str(test_temp_root)
    return test_temp_root


def create_owned_pytest_temp_root(test_temp_root: Path) -> Path:
    """Create one runner-owned child root safe to remove after a passed shard."""
    return Path(tempfile.mkdtemp(prefix="pytest-run-", dir=test_temp_root))


def remove_owned_pytest_temp_root(test_temp_root: Path, owned_root: Path) -> None:
    """Remove only a direct, non-symlink child created for this runner."""
    import shutil

    root = test_temp_root.resolve()
    if owned_root.is_symlink() or owned_root.parent.resolve() != root:
        return
    if not owned_root.name.startswith("pytest-run-") or not owned_root.is_dir():
        return
    shutil.rmtree(owned_root)


def matplotlib_cache_root(
    test_temp_root: Path,
    *,
    process_id: int | None = None,
) -> Path:
    """Return a process-owned Matplotlib cache below the test root."""
    owner = os.getpid() if process_id is None else process_id
    return test_temp_root / f"matplotlib-{owner}"
