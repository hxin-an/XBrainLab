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


def matplotlib_cache_root(
    test_temp_root: Path,
    *,
    process_id: int | None = None,
) -> Path:
    """Return a process-owned Matplotlib cache below the test root."""
    owner = os.getpid() if process_id is None else process_id
    return test_temp_root / f"matplotlib-{owner}"
