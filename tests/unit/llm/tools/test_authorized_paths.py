from __future__ import annotations

import ntpath
import os
from pathlib import Path

import pytest

from XBrainLab.backend.utils.filesystem_identity import DirectoryIdentitySnapshot
from XBrainLab.llm.agent.verifier import PathProvenanceVerifier
from XBrainLab.llm.tools import authorized_paths
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    build_load_data_command,
    execute_application_tool_command,
)
from XBrainLab.llm.tools.authorized_paths import (
    AuthorizedPath,
    AuthorizedPathError,
    FilesystemIdentity,
    PathKind,
    authorize_existing_path,
    open_authorized_path,
)
from XBrainLab.llm.tools.real.dataset_real import RealListFilesTool


class _FakeDirectoryLease:
    def __init__(self) -> None:
        self.active = False

    def __enter__(self):
        self.active = True
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.active = False


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
def test_normal_contained_file_and_folder_keep_stable_identity(
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

    assert isinstance(authorized, AuthorizedPath)
    with open_authorized_path(authorized, expected_kind=target_kind) as opened:
        assert opened.identity.kind == target_kind
        assert os.path.normcase(opened.identity.final_path) == os.path.normcase(
            str(target.resolve())
        )


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


def test_windows_normal_contained_identity_is_revalidated(monkeypatch) -> None:
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

    with open_authorized_path(authorized, expected_kind="directory") as opened:
        assert opened.identity.final_path == resolved_target
        assert opened.identity.object_id == (3, 11)


def test_native_windows_directory_lease_spans_the_bounded_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = ntpath.normcase(ntpath.normpath(r"C:\Data\Selected"))
    identity = FilesystemIdentity(
        platform="windows",
        final_path=selected,
        object_id=(3, 11),
        kind="directory",
    )
    snapshot = DirectoryIdentitySnapshot(
        path=selected,
        entries=(),
        windows=True,
    )
    lease = _FakeDirectoryLease()

    monkeypatch.setattr(authorized_paths, "_native_windows_runtime", lambda: True)
    monkeypatch.setattr(
        authorized_paths,
        "_resolve_windows_identity",
        lambda _path, *, expected_kind: identity,
    )
    monkeypatch.setattr(
        authorized_paths,
        "_admit_windows_directory_snapshot",
        lambda _path, _identity: snapshot,
    )
    monkeypatch.setattr(
        authorized_paths,
        "retain_directory_identity",
        lambda _path, *, expected=None: lease,
    )

    authorized = authorize_existing_path(
        selected,
        authorized_root=selected,
        expected_kind="directory",
    )

    assert lease.active is False
    with open_authorized_path(authorized, expected_kind="directory") as opened:
        assert lease.active is True
        assert opened.identity == identity
    assert lease.active is False


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


def test_list_files_revalidates_admitted_identity_before_enumeration(
    tmp_path: Path,
) -> None:
    selected = tmp_path / "selected"
    target = selected / "sub-01"
    target.mkdir(parents=True)
    (target / "safe.gdf").touch()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").touch()
    authorized = authorize_existing_path(
        target,
        authorized_root=selected,
        expected_kind="directory",
    )
    displaced = selected / "displaced"
    target.rename(displaced)
    try:
        target.symlink_to(outside, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - host privilege boundary
        pytest.skip(f"symlink unavailable: {type(exc).__name__}")

    result = RealListFilesTool().execute(object(), directory=authorized)

    assert result.ok is False
    assert result.error_type == "permission"
    assert "private.txt" not in repr(result.payload)


def test_list_files_rejects_plain_path_without_host_identity_grant(
    tmp_path: Path,
) -> None:
    (tmp_path / "private.txt").touch()

    result = RealListFilesTool().execute(object(), directory=str(tmp_path))

    assert result.ok is False
    assert result.error_type == "permission"
    assert "private.txt" not in repr(result.payload)


def test_load_data_builder_rejects_replaced_authorized_directory(
    tmp_path: Path,
) -> None:
    selected = tmp_path / "selected"
    target = selected / "sub-01"
    target.mkdir(parents=True)
    (target / "safe.gdf").touch()
    outside = tmp_path / "outside"
    outside.mkdir()
    private = outside / "private.gdf"
    private.touch()
    authorized = authorize_existing_path(
        target,
        authorized_root=selected,
        expected_kind="directory",
    )
    target.rename(selected / "displaced")
    try:
        target.symlink_to(outside, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - host privilege boundary
        pytest.skip(f"symlink unavailable: {type(exc).__name__}")

    command = build_load_data_command({"paths": [authorized]})

    assert command is None
    assert str(private) not in repr(command)


@pytest.mark.parametrize("target_kind", ("file", "directory"))
def test_load_data_builder_rejects_plain_paths_without_provenance(
    tmp_path: Path,
    target_kind: PathKind,
) -> None:
    target = tmp_path / ("recording.edf" if target_kind == "file" else "session")
    if target_kind == "file":
        target.touch()
    else:
        target.mkdir()
        (target / "recording.edf").touch()

    command = build_load_data_command({"paths": [str(target)]})

    assert command is None


@pytest.mark.parametrize("target_kind", ("file", "directory"))
def test_load_data_builder_does_not_downgrade_grants_to_lexical_paths(
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
        (target / "recording.edf").touch()
    authorized = authorize_existing_path(
        target,
        authorized_root=selected,
        expected_kind=target_kind,
    )

    command = build_load_data_command({"paths": [authorized]})

    assert command is None


class _LoadDataRejectingRuntime:
    def __init__(self) -> None:
        self.commands: list[object] = []

    def get_view_publication(self) -> object:
        raise AssertionError("load_data denial must not read backend publication")

    def execute(self, command: object) -> object:
        self.commands.append(command)
        raise AssertionError("load_data denial must not call ApplicationService")


@pytest.mark.parametrize("with_grant", (False, True))
def test_load_data_executor_fails_closed_before_application_service(
    tmp_path: Path,
    with_grant: bool,
) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    recording = selected / "recording.edf"
    recording.touch()
    path: str = str(recording)
    if with_grant:
        path = authorize_existing_path(
            recording,
            authorized_root=selected,
            expected_kind="file",
        )
    runtime = _LoadDataRejectingRuntime()

    result = execute_application_tool_command(
        object(),
        "load_data",
        {"paths": [path]},
        availability=ToolAvailability(
            tool_name="load_data",
            enabled=True,
            command_name="load_data",
        ),
        state={},
        runtime=runtime,  # type: ignore[arg-type]
    )

    assert result is not None
    assert result.ok is False
    assert result.error_code == "assistant_direct_load_disabled"
    assert runtime.commands == []


def test_verifier_identity_binds_load_file_and_folder_inputs(
    tmp_path: Path,
) -> None:
    recording = tmp_path / "recording.edf"
    recording.touch()
    folder = tmp_path / "session"
    folder.mkdir()
    (folder / "nested.edf").touch()
    params: dict[str, object] = {"paths": [str(recording), str(folder)]}

    verification = PathProvenanceVerifier().validate(
        "load_data",
        params,
        latest_user_text=f"Load `{recording}` and `{folder}`.",
        state=None,
    )

    assert verification.is_valid is True
    paths = params["paths"]
    assert isinstance(paths, list)
    assert all(isinstance(path, AuthorizedPath) for path in paths)


def test_verifier_and_list_files_accept_normal_contained_directory(
    tmp_path: Path,
) -> None:
    selected = tmp_path / "selected"
    nested = selected / "sub-01"
    nested.mkdir(parents=True)
    (nested / "session.gdf").touch()
    state = {
        "interpretation": {
            "source_path": str(selected),
            "source_kind": "folder",
        }
    }
    params: dict[str, str] = {"directory": str(nested)}

    verification = PathProvenanceVerifier().validate(
        "list_files",
        params,
        latest_user_text="Show files from the selected EEG folder",
        state=state,
    )
    result = RealListFilesTool().execute(object(), directory=params["directory"])

    assert verification.is_valid is True
    assert isinstance(params["directory"], AuthorizedPath)
    assert result.ok is True
    assert result.payload == ["session.gdf"]
