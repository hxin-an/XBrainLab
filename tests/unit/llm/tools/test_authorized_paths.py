from __future__ import annotations

import ntpath
import os
from pathlib import Path

import pytest

from XBrainLab.backend.utils.filesystem_identity import FilesystemEntryIdentity
from XBrainLab.llm.agent.verifier import PathProvenanceVerifier
from XBrainLab.llm.tools import authorized_paths
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    execute_application_tool_command,
)
from XBrainLab.llm.tools.authorized_paths import (
    AuthorizedPathError,
    FilesystemIdentity,
    PathKind,
    authorize_existing_path,
)


class _FakeDirectoryLease:
    def __init__(self) -> None:
        self.active = False
        self.entries = (
            FilesystemEntryIdentity(path=r"C:\Data\Selected", device=3, file_id=11),
        )

    def __enter__(self):
        self.active = True
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.active = False


@pytest.mark.platform_contract
@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow regression")
@pytest.mark.parametrize("target_kind", ("file", "directory"))
def test_posix_containment_rejects_lexical_descendant_symlink_escape(
    tmp_path: Path,
    target_kind: PathKind,
) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_target = outside / "secret.edf"
    if target_kind == "file":
        outside_target.touch()
    else:
        outside_target.mkdir()
    link = selected / "linked-target"
    try:
        link.symlink_to(outside_target, target_is_directory=target_kind == "directory")
    except OSError as exc:  # pragma: no cover - host privilege boundary
        pytest.skip(f"symlink unavailable: {type(exc).__name__}")

    with pytest.raises(AuthorizedPathError, match="identity"):
        authorize_existing_path(
            link,
            authorized_root=selected,
            expected_kind=target_kind,
        )


@pytest.mark.parametrize("target_kind", ("file", "directory"))
def test_normal_contained_file_and_folder_are_admitted(
    tmp_path: Path,
    target_kind: PathKind,
) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    target = selected / ("recording.edf" if target_kind == "file" else "sub-01")
    if target_kind == "file":
        target.touch()
    else:
        target.mkdir()

    authorized = authorize_existing_path(
        target,
        authorized_root=selected,
        expected_kind=target_kind,
    )

    assert type(authorized) is str
    assert authorized == str(target)


@pytest.mark.parametrize(
    ("actual_kind", "expected_kind"),
    (("file", "directory"), ("directory", "file")),
)
def test_actual_file_and_directory_kind_mismatches_are_rejected(
    tmp_path: Path,
    actual_kind: PathKind,
    expected_kind: PathKind,
) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    target = selected / "candidate"
    if actual_kind == "file":
        target.touch()
    else:
        target.mkdir()

    with pytest.raises(AuthorizedPathError, match=f"requires a {expected_kind}"):
        authorize_existing_path(
            target,
            authorized_root=selected,
            expected_kind=expected_kind,
        )


@pytest.mark.platform_contract
@pytest.mark.skipif(os.name != "posix", reason="POSIX directory-only open refusal")
def test_actual_non_directory_ancestor_is_rejected(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    ancestor = selected / "not-a-directory"
    ancestor.write_bytes(b"unchanged source")

    with pytest.raises(
        AuthorizedPathError, match="requires a directory for a path component"
    ):
        authorize_existing_path(
            ancestor / "child",
            authorized_root=selected,
            expected_kind="directory",
        )
    assert ancestor.read_bytes() == b"unchanged source"


def test_windows_final_identity_rejects_junction_like_escape(monkeypatch) -> None:
    selected = ntpath.normcase(ntpath.normpath(r"C:\Data\Selected"))
    escaped = ntpath.normcase(ntpath.normpath(r"D:\Private\secret.edf"))

    def _identity(
        path: str,
        *,
        expected_kind: PathKind | None,
    ) -> FilesystemIdentity:
        normalized = ntpath.normcase(ntpath.normpath(path))
        final_path = (
            escaped
            if normalized.endswith(r"\junction\secret.edf")
            else selected
            if normalized == selected
            else normalized
        )
        return FilesystemIdentity(
            platform="windows",
            final_path=final_path,
            object_id=(1, hash(final_path)),
            kind=expected_kind or "file",
        )

    monkeypatch.setattr(authorized_paths, "_native_windows_runtime", lambda: False)
    monkeypatch.setattr(authorized_paths, "_resolve_windows_identity", _identity)

    with pytest.raises(AuthorizedPathError, match="outside"):
        authorize_existing_path(
            r"C:\Data\Selected\junction\secret.edf",
            authorized_root=r"C:\Data\Selected",
            expected_kind="file",
        )


def test_windows_identity_resolution_failure_is_closed(monkeypatch) -> None:
    def _unavailable(
        path: str,
        *,
        expected_kind: PathKind | None,
    ) -> FilesystemIdentity:
        del path, expected_kind
        raise OSError("native identity unavailable")

    monkeypatch.setattr(authorized_paths, "_resolve_windows_identity", _unavailable)

    with pytest.raises(AuthorizedPathError, match="identity"):
        authorize_existing_path(
            r"C:\Data\Selected\sub-01",
            authorized_root=r"C:\Data\Selected",
            expected_kind="directory",
        )


def test_windows_normal_contained_final_identity_is_admitted(monkeypatch) -> None:
    selected = ntpath.normcase(ntpath.normpath(r"C:\Data\Selected"))
    target = ntpath.normcase(ntpath.normpath(r"C:\Data\Selected\sub-01"))
    resolved_root = ntpath.normcase(ntpath.normpath(r"D:\ActualData"))
    resolved_target = ntpath.normcase(ntpath.normpath(r"D:\ActualData\sub-01"))

    def _identity(
        path: str,
        *,
        expected_kind: PathKind | None,
    ) -> FilesystemIdentity:
        normalized = ntpath.normcase(ntpath.normpath(path))
        final_path = resolved_root if normalized == selected else resolved_target
        return FilesystemIdentity(
            platform="windows",
            final_path=final_path,
            object_id=(3, 10 if normalized == selected else 11),
            kind=expected_kind or "directory",
        )

    monkeypatch.setattr(authorized_paths, "_native_windows_runtime", lambda: False)
    monkeypatch.setattr(authorized_paths, "_resolve_windows_identity", _identity)

    authorized = authorize_existing_path(
        target,
        authorized_root=selected,
        expected_kind="directory",
    )

    assert type(authorized) is str
    assert authorized == target


def test_native_windows_directory_lease_is_checked_during_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = ntpath.normcase(ntpath.normpath(r"C:\Data\Selected"))
    identity = FilesystemIdentity(
        platform="windows",
        final_path=selected,
        object_id=(3, 11),
        kind="directory",
    )
    lease = _FakeDirectoryLease()
    checked: list[tuple[bool, FilesystemIdentity]] = []
    require_match = authorized_paths._require_directory_lease_matches

    def _check_held_lease(
        admitted_lease: _FakeDirectoryLease,
        admitted_identity: FilesystemIdentity,
    ) -> None:
        checked.append((admitted_lease.active, admitted_identity))
        require_match(admitted_lease, admitted_identity)  # type: ignore[arg-type]

    monkeypatch.setattr(authorized_paths, "_native_windows_runtime", lambda: True)
    monkeypatch.setattr(
        authorized_paths,
        "_resolve_windows_identity",
        lambda _path, *, expected_kind: identity,
    )
    monkeypatch.setattr(
        authorized_paths,
        "retain_directory_identity",
        lambda _path, *, expected=None: lease,
    )
    monkeypatch.setattr(
        authorized_paths,
        "_require_directory_lease_matches",
        _check_held_lease,
    )

    authorized = authorize_existing_path(
        selected,
        authorized_root=selected,
        expected_kind="directory",
    )

    assert type(authorized) is str
    assert authorized == selected
    assert checked == [(True, identity)]
    assert lease.active is False


@pytest.mark.platform_contract
@pytest.mark.skipif(os.name != "nt", reason="native Windows identity regression")
@pytest.mark.parametrize("replace_root", (True, False), ids=("root", "target"))
def test_native_windows_replaced_directory_is_rejected_during_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replace_root: bool,
) -> None:
    selected = tmp_path / "selected"
    target = selected / "sub-01"
    target.mkdir(parents=True)
    replaced_directory = selected if replace_root else target
    displaced_directory = tmp_path / "displaced-directory"
    target_lexical = os.path.normcase(os.path.normpath(str(target)))
    resolve_identity = authorized_paths._resolve_windows_identity
    replaced = False

    def _resolve_then_replace_root(
        path: str,
        *,
        expected_kind: PathKind | None,
    ) -> FilesystemIdentity:
        nonlocal replaced
        identity = resolve_identity(path, expected_kind=expected_kind)
        if not replaced and os.path.normcase(os.path.normpath(path)) == target_lexical:
            replaced_directory.rename(displaced_directory)
            replaced_directory.mkdir()
            if replace_root:
                target.mkdir()
            replaced = True
        return identity

    monkeypatch.setattr(
        authorized_paths,
        "_resolve_windows_identity",
        _resolve_then_replace_root,
    )

    with pytest.raises(AuthorizedPathError, match="changed during authorization"):
        authorize_existing_path(
            target,
            authorized_root=selected,
            expected_kind="directory",
        )

    assert replaced is True


def test_verifier_uses_final_windows_identity_for_selected_root(
    monkeypatch,
) -> None:
    selected = ntpath.normcase(ntpath.normpath(r"C:\Data\Selected"))
    escaped = ntpath.normcase(ntpath.normpath(r"D:\Private"))

    def _identity(
        path: str,
        *,
        expected_kind: PathKind | None,
    ) -> FilesystemIdentity:
        normalized = ntpath.normcase(ntpath.normpath(path))
        final_path = escaped if normalized.endswith(r"\junction") else selected
        return FilesystemIdentity(
            platform="windows",
            final_path=final_path,
            object_id=(2, hash(final_path)),
            kind=expected_kind or "directory",
        )

    monkeypatch.setattr(authorized_paths, "_resolve_windows_identity", _identity)
    state = {
        "interpretation": {
            "source_path": r"C:\Data\Selected",
            "source_kind": "folder",
        }
    }
    params = {"directory": r"C:\Data\Selected\junction"}

    result = PathProvenanceVerifier().validate(
        "list_files",
        params,
        latest_user_text="Show files from the selected EEG folder",
        state=state,
    )

    assert result.is_valid is False
    assert type(params["directory"]) is str


def test_verifier_authorizes_generic_path_within_selected_root(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    source = selected / "recording.edf"
    source.parent.mkdir()
    source.touch()
    params = {"source_path": str(source)}

    result = PathProvenanceVerifier().validate(
        "scan_source",
        params,
        latest_user_text="Scan the selected source",
        state={
            "interpretation": {
                "source_path": str(selected),
                "source_kind": "folder",
            }
        },
    )

    assert result.is_valid is True
    assert params["source_path"] == str(source)


class _UnregisteredToolRejectingRuntime:
    def __init__(self) -> None:
        self.commands: list[object] = []

    def get_view_publication(self) -> object:
        raise AssertionError(
            "unregistered tool denial must not read backend publication"
        )

    def execute(self, command: object) -> object:
        self.commands.append(command)
        raise AssertionError(
            "unregistered tool denial must not call ApplicationService"
        )


def test_unregistered_tool_has_no_application_command_path() -> None:
    runtime = _UnregisteredToolRejectingRuntime()

    result = execute_application_tool_command(
        object(),
        "unregistered_tool",
        {},
        availability=ToolAvailability(
            tool_name="unregistered_tool",
            enabled=True,
            command_name=None,
        ),
        state={},
        runtime=runtime,  # type: ignore[arg-type]
    )

    assert result is None
    assert runtime.commands == []
