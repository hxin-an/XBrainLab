"""Identity-bound filesystem admission for Assistant file tools."""

from __future__ import annotations

import ctypes
import ntpath
import os
import re
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from XBrainLab.backend.utils.filesystem_identity import (
    DirectoryIdentitySnapshot,
    FilesystemIdentityError,
    StableDirectoryIdentity,
    retain_directory_identity,
)

PathKind = Literal["file", "directory"]
PathPlatform = Literal["posix", "windows"]

_WINDOWS_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


class AuthorizedPathError(PermissionError):
    """Raised when a file-tool path cannot be proven safe to access."""


@dataclass(frozen=True, slots=True)
class FilesystemIdentity:
    """Final path and stable object identity observed from the filesystem."""

    platform: PathPlatform
    final_path: str
    object_id: tuple[int, int]
    kind: PathKind


@dataclass(frozen=True, slots=True)
class _AuthorizedPathGrant:
    root_path: str
    root_identity: FilesystemIdentity
    target_identity: FilesystemIdentity
    root_directory_snapshot: DirectoryIdentitySnapshot | None = None
    target_directory_snapshot: DirectoryIdentitySnapshot | None = None


class AuthorizedPath(str):
    """String-compatible path carrying a host-created filesystem grant."""

    grant: _AuthorizedPathGrant

    def __new__(
        cls,
        value: str,
        *,
        grant: _AuthorizedPathGrant,
    ) -> AuthorizedPath:
        instance = str.__new__(cls, value)
        instance.grant = grant
        return instance

    @property
    def admitted_kind(self) -> PathKind:
        """Kind observed when the host admitted this path."""
        return self.grant.target_identity.kind


class DirectoryEntries(Iterator[os.DirEntry[str]], Protocol):
    """Closable directory iterator returned by ``os.scandir``."""

    def close(self) -> None: ...


class _WindowsDllLoader(Protocol):
    def __call__(self, name: str, *, use_last_error: bool) -> Any: ...


class _WindowsErrorFactory(Protocol):
    def __call__(self, error_code: int) -> OSError: ...


class _WindowsLastErrorGetter(Protocol):
    def __call__(self) -> int: ...


def _windows_ctypes_attribute(name: str) -> object:
    return getattr(ctypes, name)


def _load_windows_dll(name: str) -> Any:
    loader = cast(_WindowsDllLoader, _windows_ctypes_attribute("WinDLL"))
    return loader(name, use_last_error=True)


def _get_windows_last_error() -> int:
    getter = cast(
        _WindowsLastErrorGetter,
        _windows_ctypes_attribute("get_last_error"),
    )
    return getter()


def _windows_error(error_code: int) -> OSError:
    factory = cast(_WindowsErrorFactory, _windows_ctypes_attribute("WinError"))
    return factory(error_code)


@dataclass(slots=True)
class OpenedAuthorizedPath:
    """Revalidated path retained for one bounded file-tool operation."""

    identity: FilesystemIdentity
    _descriptor: int | None = None

    def scandir(self) -> DirectoryEntries:
        """Enumerate the retained directory identity where the OS supports it."""
        if self.identity.kind != "directory":
            raise AuthorizedPathError("Authorized filesystem identity is not a folder.")
        path_or_fd: str | int = (
            self._descriptor
            if self._descriptor is not None
            else self.identity.final_path
        )
        return cast(DirectoryEntries, os.scandir(path_or_fd))


@dataclass(slots=True)
class _OpenedPosixIdentity:
    identity: FilesystemIdentity
    descriptor: int

    def close(self) -> None:
        descriptor = self.descriptor
        self.descriptor = -1
        if descriptor >= 0:
            os.close(descriptor)


def authorize_existing_path(
    path: str | os.PathLike[str],
    *,
    authorized_root: str | os.PathLike[str],
    expected_kind: PathKind | None = None,
) -> AuthorizedPath:
    """Bind an existing path to an authorized root's final identity."""
    target_text = os.fspath(path)
    root_text = os.fspath(authorized_root)
    platform = _path_platform(target_text)
    if _path_platform(root_text) != platform:
        raise AuthorizedPathError(
            "Filesystem identity does not match the authorized root platform."
        )
    root_directory_snapshot: DirectoryIdentitySnapshot | None = None
    target_directory_snapshot: DirectoryIdentitySnapshot | None = None
    try:
        target_lexical = _normalize_lexical_path(target_text, platform)
        root_lexical = _normalize_lexical_path(root_text, platform)
        _require_lexically_contained(target_lexical, root_lexical, platform)

        if platform == "windows":
            root_kind = expected_kind if target_lexical == root_lexical else "directory"
            root_identity = _resolve_windows_identity(
                root_lexical,
                expected_kind=root_kind,
            )
            target_identity = _resolve_windows_identity(
                target_lexical,
                expected_kind=expected_kind,
            )
            if _native_windows_runtime():
                if root_identity.kind == "directory":
                    root_directory_snapshot = _admit_windows_directory_snapshot(
                        root_lexical,
                        root_identity,
                    )
                if target_identity.kind == "directory":
                    if target_lexical == root_lexical:
                        target_directory_snapshot = root_directory_snapshot
                    else:
                        target_directory_snapshot = _admit_windows_directory_snapshot(
                            target_lexical,
                            target_identity,
                        )
        else:
            root, target = _open_posix_pair(
                root_lexical,
                target_lexical,
                expected_kind=expected_kind,
            )
            try:
                root_identity = root.identity
                target_identity = target.identity
            finally:
                target.close()
                root.close()
        _require_contained_final_identity(target_identity, root_identity)
    except AuthorizedPathError:
        raise
    except (FilesystemIdentityError, OSError, ValueError) as exc:
        raise AuthorizedPathError(
            "Filesystem identity could not be established safely."
        ) from exc

    return AuthorizedPath(
        target_text,
        grant=_AuthorizedPathGrant(
            root_path=root_text,
            root_identity=root_identity,
            target_identity=target_identity,
            root_directory_snapshot=root_directory_snapshot,
            target_directory_snapshot=target_directory_snapshot,
        ),
    )


@contextmanager
def open_authorized_path(
    path: str | os.PathLike[str],
    *,
    expected_kind: PathKind | None = None,
) -> Iterator[OpenedAuthorizedPath]:
    """Revalidate a host grant and retain the admitted target for immediate IO."""
    if not isinstance(path, AuthorizedPath):
        raise AuthorizedPathError(
            "Assistant file access is missing an identity-bound authorization."
        )

    grant = path.grant
    target_text = os.fspath(path)
    try:
        platform = grant.target_identity.platform
        target_lexical = _normalize_lexical_path(target_text, platform)
        root_lexical = _normalize_lexical_path(grant.root_path, platform)
        _require_lexically_contained(target_lexical, root_lexical, platform)
    except AuthorizedPathError:
        raise
    except (OSError, ValueError) as exc:
        raise AuthorizedPathError(
            "Filesystem identity could not be re-established safely."
        ) from exc

    if platform == "windows":
        with ExitStack() as leases:
            try:
                if _native_windows_runtime():
                    snapshot = _require_windows_directory_snapshot(grant)
                    leases.enter_context(
                        retain_directory_identity(
                            snapshot.path,
                            expected=snapshot,
                        )
                    )
                root_kind = (
                    expected_kind if target_lexical == root_lexical else "directory"
                )
                root_identity = _resolve_windows_identity(
                    root_lexical,
                    expected_kind=root_kind,
                )
                target_identity = _resolve_windows_identity(
                    target_lexical,
                    expected_kind=expected_kind,
                )
                _require_unchanged_identity(root_identity, grant.root_identity)
                _require_unchanged_identity(target_identity, grant.target_identity)
                _require_contained_final_identity(target_identity, root_identity)
            except AuthorizedPathError:
                raise
            except (FilesystemIdentityError, OSError, ValueError) as exc:
                raise AuthorizedPathError(
                    "Filesystem identity could not be re-established safely."
                ) from exc
            yield OpenedAuthorizedPath(identity=target_identity)
        return

    root: _OpenedPosixIdentity | None = None
    target: _OpenedPosixIdentity | None = None
    try:
        root, target = _open_posix_pair(
            root_lexical,
            target_lexical,
            expected_kind=expected_kind,
        )
        _require_unchanged_identity(root.identity, grant.root_identity)
        _require_unchanged_identity(target.identity, grant.target_identity)
        _require_contained_final_identity(target.identity, root.identity)
    except AuthorizedPathError:
        if target is not None:
            target.close()
        if root is not None:
            root.close()
        raise
    except (OSError, ValueError) as exc:
        if target is not None:
            target.close()
        if root is not None:
            root.close()
        raise AuthorizedPathError(
            "Filesystem identity could not be re-established safely."
        ) from exc
    if root is None or target is None:  # pragma: no cover - defensive narrowing
        raise AuthorizedPathError(
            "Filesystem identity could not be re-established safely."
        )
    try:
        yield OpenedAuthorizedPath(
            identity=target.identity,
            _descriptor=target.descriptor,
        )
    finally:
        target.close()
        root.close()


def _path_platform(path: str) -> PathPlatform:
    if not isinstance(path, str) or not path or "\x00" in path:
        raise AuthorizedPathError("Filesystem identity requires a valid absolute path.")
    if _WINDOWS_ABSOLUTE_PATH.match(path):
        return "windows"
    if os.path.isabs(path):
        return "posix"
    raise AuthorizedPathError("Filesystem identity requires an absolute path.")


def _normalize_lexical_path(path: str, platform: PathPlatform) -> str:
    if platform == "windows":
        normalized = ntpath.normcase(ntpath.normpath(path))
        if not ntpath.isabs(normalized):
            raise AuthorizedPathError("Filesystem identity requires an absolute path.")
        return normalized
    return os.path.normpath(os.path.abspath(path))


def _require_lexically_contained(
    target: str,
    root: str,
    platform: PathPlatform,
) -> None:
    path_module = ntpath if platform == "windows" else os.path
    try:
        contained = path_module.commonpath((target, root)) == root
    except ValueError as exc:
        raise AuthorizedPathError(
            "Requested path is outside the authorized root."
        ) from exc
    if not contained:
        raise AuthorizedPathError("Requested path is outside the authorized root.")


def _require_contained_final_identity(
    target: FilesystemIdentity,
    root: FilesystemIdentity,
) -> None:
    """Require containment using paths obtained from final object identities."""
    if target.platform != root.platform:
        raise AuthorizedPathError("Resolved target is outside the authorized root.")
    path_module = ntpath if target.platform == "windows" else os.path
    try:
        contained = (
            path_module.commonpath((target.final_path, root.final_path))
            == root.final_path
        )
    except ValueError as exc:
        raise AuthorizedPathError(
            "Resolved target is outside the authorized root."
        ) from exc
    if not contained:
        raise AuthorizedPathError("Resolved target is outside the authorized root.")


def _require_unchanged_identity(
    current: FilesystemIdentity,
    admitted: FilesystemIdentity,
) -> None:
    if current != admitted:
        raise AuthorizedPathError(
            "Filesystem identity changed after authorization; access was blocked."
        )


def _native_windows_runtime() -> bool:
    return os.name == "nt"


def _require_windows_directory_snapshot(
    grant: _AuthorizedPathGrant,
) -> DirectoryIdentitySnapshot:
    snapshot = grant.target_directory_snapshot or grant.root_directory_snapshot
    if snapshot is None:
        raise AuthorizedPathError(
            "Windows directory access is missing a retained identity."
        )
    return snapshot


def _require_directory_lease_matches(
    lease: StableDirectoryIdentity,
    admitted: FilesystemIdentity,
) -> None:
    if not lease.entries:
        raise AuthorizedPathError("Windows directory identity is incomplete.")
    final_entry = lease.entries[-1]
    if (final_entry.device, final_entry.file_id) != admitted.object_id:
        raise AuthorizedPathError(
            "Filesystem identity changed during authorization; access was blocked."
        )


def _admit_windows_directory_snapshot(
    path: str,
    admitted: FilesystemIdentity,
) -> DirectoryIdentitySnapshot:
    """Bind a Windows directory snapshot while anti-replacement handles are held."""
    with retain_directory_identity(path) as lease:
        _require_directory_lease_matches(lease, admitted)
        return lease.snapshot()


def _posix_open_flags(*, directory: bool) -> int:
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if not no_follow or os.open not in os.supports_dir_fd:
        raise AuthorizedPathError(
            "Filesystem identity cannot enforce POSIX no-follow access."
        )
    flags = os.O_RDONLY if directory else getattr(os, "O_PATH", os.O_RDONLY)
    flags |= no_follow
    flags |= getattr(os, "O_CLOEXEC", 0)
    if directory:
        directory_flag = getattr(os, "O_DIRECTORY", 0)
        if not directory_flag:
            raise AuthorizedPathError(
                "Filesystem identity cannot enforce directory-only access."
            )
        flags |= directory_flag
    return flags


def _identity_from_posix_descriptor(
    descriptor: int,
    *,
    final_path: str,
    expected_kind: PathKind | None,
) -> FilesystemIdentity:
    status = os.fstat(descriptor)
    if stat.S_ISLNK(status.st_mode):
        raise AuthorizedPathError(
            "Filesystem identity rejected a symlink in the authorized path."
        )
    if stat.S_ISDIR(status.st_mode):
        kind: PathKind = "directory"
    elif stat.S_ISREG(status.st_mode):
        kind = "file"
    else:
        raise AuthorizedPathError(
            "Filesystem identity requires a regular file or directory."
        )
    if expected_kind is not None and kind != expected_kind:
        raise AuthorizedPathError(
            f"Filesystem identity requires a {expected_kind}, got {kind}."
        )
    return FilesystemIdentity(
        platform="posix",
        final_path=final_path,
        object_id=(status.st_dev, status.st_ino),
        kind=kind,
    )


def _open_posix_absolute(
    path: str,
    *,
    expected_kind: PathKind | None,
) -> _OpenedPosixIdentity:
    normalized = os.path.normpath(os.path.abspath(path))
    anchor = os.path.abspath(os.sep)
    current_fd = os.open(anchor, _posix_open_flags(directory=True))
    current_path = anchor
    try:
        parts = [part for part in normalized.split(os.sep) if part]
        if not parts:
            identity = _identity_from_posix_descriptor(
                current_fd,
                final_path=anchor,
                expected_kind=expected_kind,
            )
            opened = _OpenedPosixIdentity(identity, current_fd)
            current_fd = -1
            return opened
        for index, component in enumerate(parts):
            final = index == len(parts) - 1
            next_fd = os.open(
                component,
                _posix_open_flags(directory=not final or expected_kind == "directory"),
                dir_fd=current_fd,
            )
            next_path = os.path.join(current_path, component)
            try:
                _identity_from_posix_descriptor(
                    next_fd,
                    final_path=next_path,
                    expected_kind=expected_kind if final else "directory",
                )
            except BaseException:
                os.close(next_fd)
                raise
            os.close(current_fd)
            current_fd = next_fd
            current_path = next_path
        identity = _identity_from_posix_descriptor(
            current_fd,
            final_path=normalized,
            expected_kind=expected_kind,
        )
        opened = _OpenedPosixIdentity(identity, current_fd)
        current_fd = -1
        return opened
    finally:
        if current_fd >= 0:
            os.close(current_fd)


def _open_posix_relative(
    root: _OpenedPosixIdentity,
    relative_path: str,
    *,
    final_path: str,
    expected_kind: PathKind | None,
) -> _OpenedPosixIdentity:
    if relative_path in {"", "."}:
        descriptor = os.dup(root.descriptor)
        try:
            identity = _identity_from_posix_descriptor(
                descriptor,
                final_path=final_path,
                expected_kind=expected_kind,
            )
        except BaseException:
            os.close(descriptor)
            raise
        return _OpenedPosixIdentity(identity, descriptor)

    parts = relative_path.split(os.sep)
    if any(part in {"", ".", ".."} for part in parts):
        raise AuthorizedPathError("Requested path is outside the authorized root.")
    current_fd = os.dup(root.descriptor)
    try:
        for index, component in enumerate(parts):
            final = index == len(parts) - 1
            next_fd = os.open(
                component,
                _posix_open_flags(directory=not final or expected_kind == "directory"),
                dir_fd=current_fd,
            )
            try:
                identity = _identity_from_posix_descriptor(
                    next_fd,
                    final_path=(
                        final_path
                        if final
                        else os.path.join(root.identity.final_path, *parts[: index + 1])
                    ),
                    expected_kind=expected_kind if final else "directory",
                )
            except BaseException:
                os.close(next_fd)
                raise
            os.close(current_fd)
            current_fd = next_fd
        opened = _OpenedPosixIdentity(identity, current_fd)
        current_fd = -1
        return opened
    finally:
        if current_fd >= 0:
            os.close(current_fd)


def _open_posix_pair(
    root_path: str,
    target_path: str,
    *,
    expected_kind: PathKind | None,
) -> tuple[_OpenedPosixIdentity, _OpenedPosixIdentity]:
    same_path = target_path == root_path
    root = _open_posix_absolute(
        root_path,
        expected_kind=expected_kind if same_path else "directory",
    )
    try:
        relative = os.path.relpath(target_path, root_path)
        target = _open_posix_relative(
            root,
            relative,
            final_path=target_path,
            expected_kind=expected_kind,
        )
    except BaseException:
        root.close()
        raise
    return root, target


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = (
        ("file_attributes", ctypes.c_uint32),
        ("creation_time_low", ctypes.c_uint32),
        ("creation_time_high", ctypes.c_uint32),
        ("last_access_time_low", ctypes.c_uint32),
        ("last_access_time_high", ctypes.c_uint32),
        ("last_write_time_low", ctypes.c_uint32),
        ("last_write_time_high", ctypes.c_uint32),
        ("volume_serial_number", ctypes.c_uint32),
        ("file_size_high", ctypes.c_uint32),
        ("file_size_low", ctypes.c_uint32),
        ("number_of_links", ctypes.c_uint32),
        ("file_index_high", ctypes.c_uint32),
        ("file_index_low", ctypes.c_uint32),
    )


class _FileId128(ctypes.Structure):
    _fields_ = (("identifier", ctypes.c_ubyte * 16),)


class _FileIdInformation(ctypes.Structure):
    _fields_ = (
        ("volume_serial_number", ctypes.c_uint64),
        ("file_id", _FileId128),
    )


def _resolve_windows_identity(
    path: str,
    *,
    expected_kind: PathKind | None,
) -> FilesystemIdentity:
    """Resolve junctions/reparse points through a native Windows file handle."""
    if os.name != "nt":
        raise OSError("Native Windows filesystem identity is unavailable.")

    kernel32 = _load_windows_dll("kernel32")
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    create_file.restype = ctypes.c_void_p
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
    )
    get_final_path.restype = ctypes.c_uint32
    get_file_information = kernel32.GetFileInformationByHandle
    get_file_information.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_ByHandleFileInformation),
    )
    get_file_information.restype = ctypes.c_int32
    get_file_information_ex = kernel32.GetFileInformationByHandleEx
    get_file_information_ex.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    )
    get_file_information_ex.restype = ctypes.c_int32
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    close_handle.restype = ctypes.c_int32

    handle = create_file(
        path,
        0x0080,  # FILE_READ_ATTRIBUTES
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,  # OPEN_EXISTING
        0x02000000,  # FILE_FLAG_BACKUP_SEMANTICS; follow reparse targets
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in {None, invalid_handle}:
        raise _windows_error(_get_windows_last_error())
    try:
        required = get_final_path(handle, None, 0, 0)
        if required == 0:
            raise _windows_error(_get_windows_last_error())
        buffer = ctypes.create_unicode_buffer(required + 1)
        written = get_final_path(handle, buffer, len(buffer), 0)
        if written == 0 or written >= len(buffer):
            raise _windows_error(_get_windows_last_error())

        information = _ByHandleFileInformation()
        if not get_file_information(handle, ctypes.byref(information)):
            raise _windows_error(_get_windows_last_error())
        file_id_information = _FileIdInformation()
        if not get_file_information_ex(
            handle,
            18,  # FileIdInfo
            ctypes.byref(file_id_information),
            ctypes.sizeof(file_id_information),
        ):
            raise _windows_error(_get_windows_last_error())
    finally:
        close_handle(handle)

    final_path = _normalize_windows_final_path(buffer.value)
    directory_attribute = 0x00000010
    kind: PathKind = (
        "directory" if information.file_attributes & directory_attribute else "file"
    )
    if expected_kind is not None and kind != expected_kind:
        raise AuthorizedPathError(
            f"Filesystem identity requires a {expected_kind}, got {kind}."
        )
    file_id = int.from_bytes(
        bytes(file_id_information.file_id.identifier),
        byteorder="little",
    )
    return FilesystemIdentity(
        platform="windows",
        final_path=final_path,
        object_id=(int(file_id_information.volume_serial_number), file_id),
        kind=kind,
    )


def _normalize_windows_final_path(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        path = f"\\\\{path[8:]}"
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return ntpath.normcase(ntpath.normpath(path))
