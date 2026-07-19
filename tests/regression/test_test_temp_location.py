"""Regression coverage for keeping test artifacts out of the WSL system VHD."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from scripts.dev.test_runtime_paths import select_test_temp_root


def _expected_test_temp_root() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return select_test_temp_root(repo_root).resolve()


def test_pytest_uses_the_configured_workspace_temp_root() -> None:
    """All test-created temporary files use the selected safe temp root."""
    expected = _expected_test_temp_root()

    assert Path(tempfile.gettempdir()).resolve() == expected
    assert Path(os.environ["TMPDIR"]).resolve() == expected


def test_tmp_path_is_created_under_the_workspace_temp_root(tmp_path: Path) -> None:
    """Pytest's own temporary-directory factory follows the same location."""
    expected = Path(os.environ["TMPDIR"]).resolve()

    assert expected == tmp_path.resolve() or expected in tmp_path.resolve().parents


def test_wsl_test_temp_preserves_sparse_allocation(tmp_path: Path) -> None:
    """Large logical cache fixtures must not allocate their full size on WSL."""
    if not os.environ.get("WSL_DISTRO_NAME"):
        return
    probe = tmp_path / "sparse-cache-probe.bin"
    with probe.open("wb") as stream:
        stream.truncate(16_000_000)

    allocated_blocks = getattr(probe.stat(), "st_blocks", None)
    assert allocated_blocks is not None
    assert allocated_blocks * 512 < 1_000_000
