"""Filesystem identities and contained directory creation for backend outputs."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import importlib
import os
import re
import stat
import unicodedata
from contextlib import suppress
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast

_SLUG_MAX_LENGTH = 48
_HASH_HEX_LENGTH = 12
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "aux",
        "clock$",
        "con",
        "conin$",
        "conout$",
        "nul",
        "prn",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
)
_SAFE_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = getattr(
    stat,
    "FILE_ATTRIBUTE_REPARSE_POINT",
    0x0400,
)


class _WindowsDllLoader(Protocol):
    def __call__(self, name: str, *, use_last_error: bool) -> Any: ...


class _WindowsErrorFactory(Protocol):
    def __call__(self, error_code: int) -> OSError: ...


class _WindowsLastErrorGetter(Protocol):
    def __call__(self) -> int: ...


class _MsvcrtApi(Protocol):
    def open_osfhandle(self, handle: int, flags: int) -> int: ...


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


class LegacyOutputNamespaceError(RuntimeError):
    """Raised when a pre-SEC-02 output namespace would be silently abandoned."""


class FilesystemIdentityError(RuntimeError):
    """Raised when a directory no longer has its admitted filesystem identity."""


@dataclass(frozen=True, slots=True)
class FilesystemEntryIdentity:
    """Stable identity for one resolved directory path component."""

    path: str
    device: int
    file_id: int


@dataclass(frozen=True, slots=True)
class DirectoryIdentitySnapshot:
    """Handle-free directory identity retained between bounded IO operations."""

    path: str
    entries: tuple[FilesystemEntryIdentity, ...]
    windows: bool


class StableDirectoryIdentity:
    """Short-lived directory identity lease used during one filesystem operation."""

    __slots__ = (
        "_closed",
        "_directory_fd",
        "_retained_handles",
        "_windows",
        "entries",
        "path",
    )

    def __init__(
        self,
        path: str,
        entries: tuple[FilesystemEntryIdentity, ...],
        *,
        directory_fd: int | None = None,
        retained_handles: tuple[Any, ...] = (),
        windows: bool,
    ) -> None:
        self.path = path
        self.entries = entries
        self._directory_fd = directory_fd
        self._retained_handles = retained_handles
        self._windows = windows
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def snapshot(self) -> DirectoryIdentitySnapshot:
        """Return the handle-free identity represented by this lease."""
        return DirectoryIdentitySnapshot(
            path=self.path,
            entries=self.entries,
            windows=self._windows,
        )

    def assert_matches(
        self,
        directory: str | os.PathLike[str] | None = None,
    ) -> None:
        """Fail unless the path still resolves to this full identity chain."""
        if self._closed:
            raise FilesystemIdentityError("Directory identity lease is closed.")
        candidate = _canonical_directory(directory or self.path)
        if _path_key(candidate) != _path_key(self.path):
            raise FilesystemIdentityError(
                "Directory path no longer resolves to the admitted location."
            )
        try:
            observed = (
                _capture_windows_identity_chain(candidate)
                if self._windows
                else _capture_stat_identity_chain(candidate)
            )
        except OSError as exc:
            raise FilesystemIdentityError(
                "Directory or ancestor identity changed before filesystem use."
            ) from exc
        if observed != self.entries:
            raise FilesystemIdentityError(
                "Directory or ancestor identity changed before filesystem use."
            )

    def close(self) -> None:
        """Release retained native handles."""
        if self._closed:
            return
        self._closed = True
        directory_fd = self._directory_fd
        self._directory_fd = None
        if directory_fd is not None:
            with suppress(OSError):
                os.close(directory_fd)
        for handle in reversed(self._retained_handles):
            with suppress(Exception):  # pragma: no cover - native cleanup fallback
                handle.close()
        self._retained_handles = ()

    def open_existing_binary(
        self,
        path: str | os.PathLike[str],
    ) -> BinaryIO:
        """Open one regular, single-link artifact without following reparse entries."""
        candidate, name = self._artifact_entry(path)
        if self._windows:
            descriptor = _open_windows_artifact_descriptor(
                candidate,
                create_new=False,
            )
        else:
            descriptor = self._open_posix_artifact_descriptor(
                name,
                flags=os.O_RDONLY | getattr(os, "O_NONBLOCK", 0),
            )
        try:
            _require_regular_single_link(descriptor, candidate)
            self.assert_matches(candidate.parent)
            return os.fdopen(descriptor, "rb")
        except Exception:
            with suppress(OSError):
                os.close(descriptor)
            raise

    def create_exclusive_binary(
        self,
        path: str | os.PathLike[str],
    ) -> BinaryIO:
        """Create one private temporary artifact without following an existing entry."""
        candidate, name = self._artifact_entry(path)
        try:
            if self._windows:
                descriptor = _open_windows_artifact_descriptor(
                    candidate,
                    create_new=True,
                )
            else:
                descriptor = self._open_posix_artifact_descriptor(
                    name,
                    flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    mode=0o600,
                )
        except FileExistsError as exc:
            raise FilesystemIdentityError(
                "Artifact temporary entry already exists and was not opened."
            ) from exc
        try:
            _require_regular_single_link(descriptor, candidate)
            self.assert_matches(candidate.parent)
            return os.fdopen(descriptor, "wb")
        except Exception:
            with suppress(OSError):
                os.close(descriptor)
            raise

    def regular_file_exists(self, path: str | os.PathLike[str]) -> bool:
        """Return whether a trusted regular artifact exists, rejecting substitutions."""
        try:
            stream = self.open_existing_binary(path)
        except FileNotFoundError:
            return False
        stream.close()
        return True

    def replace_entry(
        self,
        source: str | os.PathLike[str],
        target: str | os.PathLike[str],
    ) -> None:
        """Atomically publish one entry inside this retained directory."""
        source_path, source_name = self._artifact_entry(source)
        target_path, target_name = self._artifact_entry(target)
        self.assert_matches(source_path.parent)
        if self._directory_fd is not None:
            os.replace(
                source_name,
                target_name,
                src_dir_fd=self._directory_fd,
                dst_dir_fd=self._directory_fd,
            )
        else:
            os.replace(source_path, target_path)
        self.assert_matches(target_path.parent)

    def unlink_entry(
        self,
        path: str | os.PathLike[str],
        *,
        missing_ok: bool,
    ) -> None:
        """Remove one directory entry without following its target."""
        candidate, name = self._artifact_entry(path)
        self.assert_matches(candidate.parent)
        try:
            if self._directory_fd is not None:
                os.unlink(name, dir_fd=self._directory_fd)
            else:
                candidate.unlink()
        except FileNotFoundError:
            if not missing_ok:
                raise

    def _artifact_entry(
        self,
        path: str | os.PathLike[str],
    ) -> tuple[Path, str]:
        if self._closed:
            raise FilesystemIdentityError("Directory identity lease is closed.")
        candidate = Path(path)
        name = candidate.name
        if not name or name in {".", ".."} or Path(name).name != name:
            raise FilesystemIdentityError("Artifact path must use one file basename.")
        self.assert_matches(candidate.parent)
        return candidate, name

    def _open_posix_artifact_descriptor(
        self,
        name: str,
        *,
        flags: int,
        mode: int = 0o600,
    ) -> int:
        directory_fd = self._directory_fd
        if directory_fd is None:
            raise FilesystemIdentityError(
                "POSIX artifact access is missing its retained directory descriptor."
            )
        no_follow = getattr(os, "O_NOFOLLOW", 0)
        if not no_follow or os.open not in os.supports_dir_fd:
            raise FilesystemIdentityError(
                "This POSIX runtime cannot enforce no-follow artifact access."
            )
        try:
            return os.open(
                name,
                flags | no_follow | getattr(os, "O_CLOEXEC", 0),
                mode,
                dir_fd=directory_fd,
            )
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.EMLINK, errno.ENOTDIR}:
                raise FilesystemIdentityError(
                    "Artifact path must resolve to one regular artifact file "
                    "without symbolic links or reparse points."
                ) from exc
            raise

    def __enter__(self) -> StableDirectoryIdentity:
        self.assert_matches()
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - interpreter cleanup fallback
        with suppress(Exception):
            self.close()


class ContainedOutputDirectory:
    """Stable output directory identity retained for artifact IO."""

    __slots__ = ("_directory_fd", "_identity_snapshot", "io_path", "path")

    def __init__(
        self,
        *,
        path: Path,
        io_path: Path,
        directory_fd: int | None,
        identity_snapshot: DirectoryIdentitySnapshot | None = None,
    ) -> None:
        self.path = path
        self.io_path = io_path
        self._directory_fd = directory_fd
        self._identity_snapshot = identity_snapshot

    def retain_identity(self) -> StableDirectoryIdentity:
        """Retain and verify this output identity for one bounded IO operation."""
        identity_path = self.io_path if self._identity_snapshot is None else self.path
        return retain_directory_identity(
            identity_path,
            expected=self._identity_snapshot,
            directory_fd=self._directory_fd,
        )

    def close(self) -> None:
        """Release the retained POSIX directory descriptor, if any."""
        directory_fd = self._directory_fd
        if directory_fd is None:
            return
        self._directory_fd = None
        with suppress(OSError):
            os.close(directory_fd)

    def __del__(self) -> None:
        self.close()


def _is_windows() -> bool:
    return os.name == "nt"


def _canonical_directory(path: str | os.PathLike[str]) -> str:
    return os.path.normpath(os.path.realpath(os.path.abspath(os.fspath(path))))


def _path_key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _directory_chain(path: str) -> tuple[Path, ...]:
    target = Path(path)
    return tuple(reversed((target, *target.parents)))


def _entry_from_stat(path: Path) -> FilesystemEntryIdentity:
    result = path.stat()
    if not stat.S_ISDIR(result.st_mode):
        raise NotADirectoryError(str(path))
    return FilesystemEntryIdentity(
        path=_path_key(str(path)),
        device=int(result.st_dev),
        file_id=int(result.st_ino),
    )


def _capture_stat_identity_chain(path: str) -> tuple[FilesystemEntryIdentity, ...]:
    return tuple(_entry_from_stat(component) for component in _directory_chain(path))


class _WindowsDirectoryHandle:
    """Owner for one native Windows directory handle."""

    __slots__ = ("value",)

    def __init__(self, value: int) -> None:
        self.value = value

    def close(self) -> None:
        if self.value:
            _close_windows_handle(self.value)
            self.value = 0


def _open_windows_directory_handle(
    path: Path,
    *,
    prevent_replacement: bool,
) -> _WindowsDirectoryHandle:
    file_read_attributes = 0x0080
    file_share_read = 0x0001
    file_share_write = 0x0002
    file_share_delete = 0x0004
    open_existing = 3
    file_flag_backup_semantics = 0x02000000

    kernel32 = _load_windows_dll("kernel32")
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    share_mode = file_share_read | file_share_write
    if not prevent_replacement:
        share_mode |= file_share_delete
    handle = create_file(
        str(path),
        file_read_attributes,
        share_mode,
        None,
        open_existing,
        file_flag_backup_semantics,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in {None, invalid_handle}:
        raise _windows_error(_get_windows_last_error())
    return _WindowsDirectoryHandle(int(handle))


def _close_windows_handle(handle: int) -> None:
    kernel32 = _load_windows_dll("kernel32")
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    if not close_handle(handle):
        raise _windows_error(_get_windows_last_error())


def _windows_handle_identity(
    path: Path,
    handle: _WindowsDirectoryHandle,
) -> FilesystemEntryIdentity:
    file_attribute_directory = 0x0010

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = (
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        )

    class FileId128(ctypes.Structure):
        _fields_ = (("identifier", ctypes.c_ubyte * 16),)

    class FileIdInformation(ctypes.Structure):
        _fields_ = (
            ("volume_serial_number", ctypes.c_ulonglong),
            ("file_id", FileId128),
        )

    kernel32 = _load_windows_dll("kernel32")
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ByHandleFileInformation),
    )
    get_information.restype = wintypes.BOOL
    information = ByHandleFileInformation()
    if not get_information(handle.value, ctypes.byref(information)):
        raise _windows_error(_get_windows_last_error())
    if not information.dwFileAttributes & file_attribute_directory:
        raise NotADirectoryError(str(path))

    get_information_ex = kernel32.GetFileInformationByHandleEx
    get_information_ex.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    get_information_ex.restype = wintypes.BOOL
    file_id_information = FileIdInformation()
    if not get_information_ex(
        handle.value,
        18,  # FileIdInfo
        ctypes.byref(file_id_information),
        ctypes.sizeof(file_id_information),
    ):
        raise _windows_error(_get_windows_last_error())
    return FilesystemEntryIdentity(
        path=_path_key(str(path)),
        device=int(file_id_information.volume_serial_number),
        file_id=int.from_bytes(
            bytes(file_id_information.file_id.identifier),
            byteorder="little",
        ),
    )


def _retain_windows_identity_chain(
    path: str,
) -> tuple[tuple[FilesystemEntryIdentity, ...], tuple[Any, ...]]:
    identities: list[FilesystemEntryIdentity] = []
    handles: list[_WindowsDirectoryHandle] = []
    try:
        for component in _directory_chain(path):
            handle = _open_windows_directory_handle(
                component,
                prevent_replacement=True,
            )
            handles.append(handle)
            identities.append(_windows_handle_identity(component, handle))
    except Exception:
        for handle in reversed(handles):
            handle.close()
        raise
    return tuple(identities), tuple(handles)


def _capture_windows_identity_chain(
    path: str,
) -> tuple[FilesystemEntryIdentity, ...]:
    identities: list[FilesystemEntryIdentity] = []
    for component in _directory_chain(path):
        handle = _open_windows_directory_handle(
            component,
            prevent_replacement=False,
        )
        try:
            identities.append(_windows_handle_identity(component, handle))
        finally:
            handle.close()
    return tuple(identities)


def _require_regular_single_link(descriptor: int, path: Path) -> None:
    """Reject directories, devices, pipes, and hard-linked artifact entries."""
    status = os.fstat(descriptor)
    if not stat.S_ISREG(status.st_mode):
        raise FilesystemIdentityError(
            f"Artifact path must resolve to one regular artifact file: {path}."
        )
    if int(status.st_nlink) != 1:
        raise FilesystemIdentityError(
            f"Artifact file must not have multiple hard links: {path}."
        )


def _open_windows_artifact_descriptor(
    path: Path,
    *,
    create_new: bool,
) -> int:
    """Open a leaf artifact by native handle without following reparse points."""
    generic_read = 0x80000000
    generic_write = 0x40000000
    file_share_read = 0x0001
    create_new_disposition = 1
    open_existing = 3
    file_attribute_normal = 0x0080
    file_flag_open_reparse_point = 0x00200000
    file_attribute_directory = 0x0010

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = (
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        )

    kernel32 = _load_windows_dll("kernel32")
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        generic_write if create_new else generic_read,
        0 if create_new else file_share_read,
        None,
        create_new_disposition if create_new else open_existing,
        file_attribute_normal | file_flag_open_reparse_point,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in {None, invalid_handle}:
        error_code = _get_windows_last_error()
        if create_new and error_code in {80, 183}:
            raise FileExistsError(str(path))
        if not create_new and error_code in {2, 3}:
            raise FileNotFoundError(str(path))
        raise _windows_error(error_code)

    owned_handle = _WindowsDirectoryHandle(int(handle))
    try:
        get_information = kernel32.GetFileInformationByHandle
        get_information.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ByHandleFileInformation),
        )
        get_information.restype = wintypes.BOOL
        information = ByHandleFileInformation()
        if not get_information(owned_handle.value, ctypes.byref(information)):
            raise _windows_error(_get_windows_last_error())
        if information.dwFileAttributes & (
            file_attribute_directory | _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise FilesystemIdentityError(
                "Artifact path must resolve to one regular artifact file "
                "without symbolic links or reparse points."
            )
        if int(information.nNumberOfLinks) != 1:
            raise FilesystemIdentityError(
                f"Artifact file must not have multiple hard links: {path}."
            )
        msvcrt = cast(_MsvcrtApi, importlib.import_module("msvcrt"))
        descriptor_flags = getattr(os, "O_BINARY", 0)
        descriptor_flags |= os.O_WRONLY if create_new else os.O_RDONLY
        descriptor = int(msvcrt.open_osfhandle(owned_handle.value, descriptor_flags))
        owned_handle.value = 0
        return descriptor
    finally:
        owned_handle.close()


def capture_directory_identity(
    directory: str | os.PathLike[str],
) -> DirectoryIdentitySnapshot:
    """Capture a handle-free identity for later path replacement checks."""
    canonical = _canonical_directory(directory)
    windows = _is_windows()
    entries = (
        _capture_windows_identity_chain(canonical)
        if windows
        else _capture_stat_identity_chain(canonical)
    )
    return DirectoryIdentitySnapshot(canonical, entries, windows)


def retain_directory_identity(
    directory: str | os.PathLike[str],
    *,
    expected: DirectoryIdentitySnapshot | None = None,
    directory_fd: int | None = None,
) -> StableDirectoryIdentity:
    """Retain one operation-scoped identity, denying Windows replacement."""
    canonical = _canonical_directory(directory)
    windows = _is_windows()
    if windows:
        if directory_fd is not None:
            raise FilesystemIdentityError(
                "A POSIX directory descriptor cannot be used on Windows."
            )
        entries, handles = _retain_windows_identity_chain(canonical)
        retained_directory_fd = None
    else:
        entries = _capture_stat_identity_chain(canonical)
        handles = ()
        retained_directory_fd = (
            os.dup(directory_fd)
            if directory_fd is not None
            else os.open(canonical, _directory_open_flags())
        )
        retained_status = os.fstat(retained_directory_fd)
        final_identity = entries[-1]
        if (
            int(retained_status.st_dev),
            int(retained_status.st_ino),
        ) != (final_identity.device, final_identity.file_id):
            os.close(retained_directory_fd)
            raise FilesystemIdentityError(
                "Directory identity changed while retaining filesystem access."
            )
    identity = StableDirectoryIdentity(
        canonical,
        entries,
        directory_fd=retained_directory_fd,
        retained_handles=handles,
        windows=windows,
    )
    try:
        _require_expected_identity(expected, identity)
        identity.assert_matches(canonical)
    except Exception:
        identity.close()
        raise
    return identity


def _require_expected_identity(
    expected: DirectoryIdentitySnapshot | None,
    identity: StableDirectoryIdentity,
) -> None:
    if expected is None:
        return
    observed = identity.snapshot()
    if (
        expected.windows != observed.windows
        or _path_key(expected.path) != _path_key(observed.path)
        or expected.entries != observed.entries
    ):
        raise FilesystemIdentityError(
            "Directory or ancestor identity changed before filesystem use."
        )


def validate_filesystem_metadata(value: str, *, field: str) -> str:
    """Validate untrusted display metadata before deriving an output identity."""
    if not isinstance(value, str):
        raise ValueError(f"{field} for training output must be text.")

    normalized_raw = unicodedata.normalize("NFKC", value)
    if "/" in normalized_raw or "\\" in normalized_raw:
        raise ValueError(
            f"{field} for training output must not contain path separators."
        )
    if any(unicodedata.category(char).startswith("C") for char in normalized_raw):
        raise ValueError(
            f"{field} for training output must not contain control characters."
        )

    normalized = normalized_raw.strip()
    if not normalized:
        raise ValueError(f"{field} for training output must not be empty.")
    if normalized in {".", ".."}:
        raise ValueError(f"{field} for training output must not be a dot path segment.")

    windows_stem = normalized.rstrip(" .").split(".", maxsplit=1)[0].rstrip(" ")
    if windows_stem.casefold() in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"{field} for training output uses a Windows reserved name.")
    return normalized


def filesystem_safe_identity(value: str, *, field: str) -> str:
    """Return ``ASCII slug + stable SHA-256 prefix`` for display metadata."""
    normalized = validate_filesystem_metadata(value, field=field)
    ascii_value = (
        unicodedata.normalize("NFKD", normalized)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")
    slug = slug[:_SLUG_MAX_LENGTH].rstrip("-") or "item"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:_HASH_HEX_LENGTH]
    return f"{slug}-{digest}"


def create_contained_output_directory(
    authorized_root: str | Path,
    *components: str,
    exclusive: bool,
    legacy_components: tuple[str, ...] = (),
) -> ContainedOutputDirectory:
    """Create a contained output directory with a stable IO identity."""
    if not components:
        raise ValueError("Training output path requires at least one component.")
    for component in components:
        _validate_generated_component(component)
    for component in legacy_components:
        _validate_legacy_component(component)

    root = _absolute_root(authorized_root)
    if os.name == "posix":
        return _create_posix_output_directory(
            root,
            components,
            exclusive=exclusive,
            legacy_components=legacy_components,
        )
    return _create_fallback_output_directory(
        root,
        components,
        exclusive=exclusive,
        legacy_components=legacy_components,
    )


def _absolute_root(authorized_root: str | Path) -> Path:
    raw_root = os.fspath(Path(authorized_root).expanduser())
    if "\x00" in raw_root:
        raise ValueError("Training output root contains a null byte.")
    return Path(os.path.abspath(raw_root))


def _validate_generated_component(component: str) -> None:
    """Reject unsafe or platform-ambiguous generated path components."""
    if (
        not isinstance(component, str)
        or component in {"", ".", ".."}
        or "/" in component
        or "\\" in component
        or any(unicodedata.category(char).startswith("C") for char in component)
        or _SAFE_COMPONENT_PATTERN.fullmatch(component) is None
    ):
        raise ValueError("Unsafe generated training output path component.")
    windows_stem = component.rstrip(" .").split(".", maxsplit=1)[0].rstrip(" ")
    if windows_stem.casefold() in _WINDOWS_RESERVED_NAMES:
        raise ValueError("Unsafe generated training output path component.")


def _validate_legacy_component(component: str) -> None:
    if (
        not isinstance(component, str)
        or component in {"", ".", ".."}
        or "/" in component
        or "\\" in component
        or any(unicodedata.category(char).startswith("C") for char in component)
    ):
        raise ValueError("Unsafe legacy training output path component.")


def _directory_open_flags() -> int:
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not no_follow or not directory:
        raise RuntimeError(
            "This POSIX runtime cannot enforce no-follow training output access."
        )
    return os.O_RDONLY | no_follow | directory | getattr(os, "O_CLOEXEC", 0)


def _open_directory_at(parent_fd: int, component: str, *, label: str) -> int:
    try:
        return os.open(
            component,
            _directory_open_flags(),
            dir_fd=parent_fd,
        )
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError(
                f"{label} must not contain symlinks or non-directory components."
            ) from exc
        raise


def _open_or_create_directory_at(
    parent_fd: int,
    component: str,
    *,
    label: str,
) -> int:
    try:
        return _open_directory_at(parent_fd, component, label=label)
    except FileNotFoundError:
        with suppress(FileExistsError):
            _mkdir_at(parent_fd, component)
        return _open_directory_at(parent_fd, component, label=label)


def _mkdir_at(parent_fd: int, component: str) -> None:
    os.mkdir(component, dir_fd=parent_fd)


def _open_or_create_posix_root(root: Path) -> int:
    if os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd:
        raise RuntimeError(
            "This POSIX runtime cannot enforce dir-fd training output access."
        )
    anchor = root.anchor or os.sep
    current_fd = os.open(anchor, _directory_open_flags())
    try:
        for component in root.parts[1:]:
            next_fd = _open_or_create_directory_at(
                current_fd,
                component,
                label="Training output root",
            )
            os.close(current_fd)
            current_fd = next_fd
    except BaseException:
        os.close(current_fd)
        raise
    else:
        return current_fd


def _legacy_namespace_exists_at(
    root_fd: int,
    components: tuple[str, ...],
) -> bool:
    if not components:
        return False
    current_fd = os.dup(root_fd)
    try:
        for index, component in enumerate(components):
            try:
                entry = os.stat(
                    component,
                    dir_fd=current_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                return False
            if index == len(components) - 1:
                return True
            if not stat.S_ISDIR(entry.st_mode) or stat.S_ISLNK(entry.st_mode):
                return True
            next_fd = _open_directory_at(
                current_fd,
                component,
                label="Legacy training output namespace",
            )
            os.close(current_fd)
            current_fd = next_fd
        return True
    finally:
        os.close(current_fd)


def _fd_access_path(directory_fd: int) -> Path:
    identity = os.fstat(directory_fd)
    for base in (Path("/proc/self/fd"), Path("/dev/fd")):
        candidate = base / str(directory_fd)
        try:
            observed = os.stat(candidate)
        except OSError:
            continue
        if (observed.st_dev, observed.st_ino) == (identity.st_dev, identity.st_ino):
            return candidate
    raise RuntimeError(
        "This POSIX runtime has no stable directory-fd path for artifact writers."
    )


def _raise_legacy_namespace_error() -> None:
    raise LegacyOutputNamespaceError(
        "A pre-SEC-02 training output namespace exists under the selected output "
        "root. XBrainLab will not migrate or resume it implicitly; archive or "
        "remove that legacy directory and start a new training run."
    )


def _create_posix_output_directory(
    root: Path,
    components: tuple[str, ...],
    *,
    exclusive: bool,
    legacy_components: tuple[str, ...],
) -> ContainedOutputDirectory:
    current_fd = _open_or_create_posix_root(root)
    try:
        _fd_access_path(current_fd)
        if _legacy_namespace_exists_at(current_fd, legacy_components):
            _raise_legacy_namespace_error()

        for index, component in enumerate(components):
            is_final = index == len(components) - 1
            try:
                _mkdir_at(current_fd, component)
            except FileExistsError as exc:
                if is_final and exclusive:
                    raise FileExistsError(
                        "Training output directory already exists; implicit resume "
                        "is not supported."
                    ) from exc
            next_fd = _open_directory_at(
                current_fd,
                component,
                label="Training output path",
            )
            os.close(current_fd)
            current_fd = next_fd

        io_path = _fd_access_path(current_fd)
        output_directory = ContainedOutputDirectory(
            path=root.joinpath(*components),
            io_path=io_path,
            directory_fd=current_fd,
            identity_snapshot=None,
        )
        current_fd = -1
        return output_directory
    finally:
        if current_fd >= 0:
            os.close(current_fd)


def _create_fallback_output_directory(
    root: Path,
    components: tuple[str, ...],
    *,
    exclusive: bool,
    legacy_components: tuple[str, ...],
) -> ContainedOutputDirectory:
    os.makedirs(root, exist_ok=True)
    resolved_root = root.resolve(strict=False)
    if legacy_components:
        legacy_candidate = resolved_root.joinpath(*legacy_components)
        if os.path.lexists(legacy_candidate):
            _raise_legacy_namespace_error()

    candidate = resolved_root.joinpath(*components).resolve(strict=False)
    _require_contained(candidate, resolved_root)
    try:
        os.makedirs(candidate, exist_ok=not exclusive)
    except FileExistsError as exc:
        raise FileExistsError(
            "Training output directory already exists; implicit resume is not "
            "supported."
        ) from exc
    resolved_candidate = candidate.resolve(strict=False)
    _require_contained(resolved_candidate, resolved_root)
    return ContainedOutputDirectory(
        path=resolved_candidate,
        io_path=resolved_candidate,
        directory_fd=None,
        identity_snapshot=capture_directory_identity(resolved_candidate),
    )


def _require_contained(candidate: Path, authorized_root: Path) -> None:
    try:
        candidate.relative_to(authorized_root)
    except ValueError as exc:
        raise ValueError(
            "Resolved training output path escapes the authorized root."
        ) from exc
