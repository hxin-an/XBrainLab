"""Filesystem identities and contained directory creation for backend outputs."""

from __future__ import annotations

import errno
import hashlib
import os
import re
import stat
import unicodedata
from contextlib import suppress
from pathlib import Path

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


class LegacyOutputNamespaceError(RuntimeError):
    """Raised when a pre-SEC-02 output namespace would be silently abandoned."""


class ContainedOutputDirectory:
    """Stable output directory identity retained for artifact IO."""

    __slots__ = ("_directory_fd", "io_path", "path")

    def __init__(
        self,
        *,
        path: Path,
        io_path: Path,
        directory_fd: int | None,
    ) -> None:
        self.path = path
        self.io_path = io_path
        self._directory_fd = directory_fd

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
    )


def _require_contained(candidate: Path, authorized_root: Path) -> None:
    try:
        candidate.relative_to(authorized_root)
    except ValueError as exc:
        raise ValueError(
            "Resolved training output path escapes the authorized root."
        ) from exc
