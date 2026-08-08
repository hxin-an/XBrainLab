from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

from XBrainLab.backend.utils import filesystem_identity
from XBrainLab.backend.utils.filesystem_identity import (
    FilesystemEntryIdentity,
    FilesystemIdentityError,
    StableDirectoryIdentity,
    capture_directory_identity,
    retain_directory_identity,
)


class _FakeHandle:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_directory_snapshot_rejects_same_path_replacement(tmp_path: Path) -> None:
    target = tmp_path / "output"
    target.mkdir()
    snapshot = capture_directory_identity(target)
    target.rename(tmp_path / "displaced")
    target.mkdir()

    with pytest.raises(FilesystemIdentityError, match="identity changed"):
        retain_directory_identity(target, expected=snapshot)


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory identity contract")
def test_non_windows_directory_identity_revalidates_normally(tmp_path: Path) -> None:
    with retain_directory_identity(tmp_path) as identity:
        identity.assert_matches(tmp_path)

    assert identity.closed is True


def test_simulated_windows_ancestor_replacement_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = filesystem_identity._canonical_directory(tmp_path)
    root = FilesystemEntryIdentity(path="root", device=1, file_id=10)
    target = FilesystemEntryIdentity(path=canonical, device=1, file_id=20)
    replaced_root = FilesystemEntryIdentity(path="root", device=1, file_id=99)
    handle = _FakeHandle()
    snapshots = iter(((root, target), (replaced_root, target)))

    monkeypatch.setattr(filesystem_identity, "_is_windows", lambda: True)
    monkeypatch.setattr(
        filesystem_identity,
        "_retain_windows_identity_chain",
        lambda _path: ((root, target), (handle,)),
    )
    monkeypatch.setattr(
        filesystem_identity,
        "_capture_windows_identity_chain",
        lambda _path: next(snapshots),
    )

    identity = retain_directory_identity(tmp_path)
    assert handle.closed is False

    with pytest.raises(FilesystemIdentityError, match="identity changed"):
        identity.assert_matches(tmp_path)

    assert handle.closed is False
    identity.close()
    assert handle.closed is True


def test_simulated_windows_artifact_open_uses_native_leaf_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"artifact")
    canonical = filesystem_identity._canonical_directory(tmp_path)
    entry = FilesystemEntryIdentity(path=canonical, device=1, file_id=20)
    calls: list[tuple[Path, bool]] = []

    monkeypatch.setattr(
        filesystem_identity,
        "_capture_windows_identity_chain",
        lambda _path: (entry,),
    )

    def open_native(path: Path, *, create_new: bool) -> int:
        calls.append((path, create_new))
        return os.open(path, os.O_RDONLY)

    monkeypatch.setattr(
        filesystem_identity,
        "_open_windows_artifact_descriptor",
        open_native,
    )
    identity = StableDirectoryIdentity(canonical, (entry,), windows=True)

    with identity.open_existing_binary(artifact) as stream:
        assert stream.read() == b"artifact"

    identity.close()
    assert calls == [(artifact, False)]


def test_windows_native_leaf_opener_keeps_reparse_and_hardlink_guards() -> None:
    source = inspect.getsource(filesystem_identity._open_windows_artifact_descriptor)

    assert "file_flag_open_reparse_point" in source
    assert "_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT" in source
    assert "nNumberOfLinks" in source
    assert "open_osfhandle" in source
