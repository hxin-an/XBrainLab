from __future__ import annotations

import os
import stat
from pathlib import Path

from scripts.dev.test_runtime_paths import (
    create_owned_pytest_temp_root,
    matplotlib_cache_root,
    remove_owned_pytest_temp_root,
    select_test_temp_root,
)


def test_explicit_test_temp_override_is_resolved(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XBRAINLAB_TEST_TMPDIR", "relative-test-root")

    selected = select_test_temp_root(tmp_path / "repo")

    assert selected == (tmp_path / "relative-test-root").resolve()


def test_matplotlib_cache_is_process_owned(tmp_path: Path) -> None:
    assert matplotlib_cache_root(tmp_path, process_id=41) == (
        tmp_path / "matplotlib-41"
    )


def test_wsl_default_uses_shared_memory_when_available(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("XBRAINLAB_TEST_TMPDIR", raising=False)
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-Test")

    selected = select_test_temp_root(tmp_path / "repo")

    if Path("/dev/shm").is_dir() and os.access("/dev/shm", os.W_OK):
        assert selected.is_relative_to("/dev/shm")
    else:
        assert selected == (tmp_path / "repo" / ".test-tmp").resolve()


def test_owned_cleanup_retries_readonly_git_fixture_file(tmp_path: Path) -> None:
    root = tmp_path / "test-root"
    root.mkdir()
    owned = create_owned_pytest_temp_root(root)
    git_object = owned / "repo" / ".git" / "objects" / "35" / "object"
    git_object.parent.mkdir(parents=True)
    git_object.write_bytes(b"fixture")
    git_object.chmod(stat.S_IREAD)

    remove_owned_pytest_temp_root(root, owned)

    assert not owned.exists()
