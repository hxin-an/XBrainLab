"""Cross-platform filesystem path assertions for backend tests."""

from __future__ import annotations

import os
from collections.abc import Iterable


def filesystem_path_key(path: str | os.PathLike[str]) -> str:
    """Return the platform-equivalent identity used by backend path policies."""
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


def assert_filesystem_paths_equal(
    actual: str | os.PathLike[str],
    expected: str | os.PathLike[str],
) -> None:
    assert filesystem_path_key(actual) == filesystem_path_key(expected)


def assert_filesystem_path_lists_equal(
    actual: Iterable[str | os.PathLike[str]],
    expected: Iterable[str | os.PathLike[str]],
) -> None:
    assert [filesystem_path_key(path) for path in actual] == [
        filesystem_path_key(path) for path in expected
    ]
