"""Private filesystem boundary for bounded XBrainLab diagnostic logs."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from XBrainLab.backend.utils.public_diagnostics import (
    DiagnosticDisclosure,
    DiagnosticTextLayout,
    public_diagnostic_text,
)
from XBrainLab.backend.utils.windows_private_acl import (
    secure_private_windows_directory,
    secure_private_windows_file_descriptor,
)

_OWNER_READ_WRITE = 0o600
_OWNER_DIRECTORY_MODE = 0o700
_LOG_PRIVACY_FORMAT_MARKER = b"xbrainlab-public-diagnostics-v1\n"
_TRUNCATED_RECORD_MARKER = " [TRUNCATED]"


def prepare_log_file(log_file: str, *, backup_count: int) -> None:
    """Create and harden one active log plus its bounded backup family."""
    descriptor = open_regular_log_descriptor(
        os.path.abspath(log_file),
        os.O_APPEND | os.O_CREAT | os.O_WRONLY,
    )
    os.close(descriptor)
    remove_excess_numeric_backups(log_file, backup_count)
    secure_log_family(log_file, backup_count)


def prepare_secure_log_directory(log_dir: str) -> None:
    """Create a private log directory or fail if privacy cannot be enforced."""
    os.makedirs(log_dir, mode=_OWNER_DIRECTORY_MODE, exist_ok=True)
    _require_directory_chain_without_links(log_dir)
    if os.name == "nt":
        secure_private_windows_directory(log_dir)
        return

    descriptor = os.open(
        log_dir,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fchmod(descriptor, _OWNER_DIRECTORY_MODE)
        status = os.fstat(descriptor)
        if (
            stat.S_IMODE(status.st_mode) != _OWNER_DIRECTORY_MODE
            or status.st_uid != os.geteuid()
        ):
            raise OSError(
                "Log directory does not enforce owner-only access; "
                "file logging is unavailable."
            )
    finally:
        os.close(descriptor)


def secure_log_family(log_file: str, backup_count: int) -> None:
    """Revalidate owner-only access across active, marker, and backup files."""
    absolute_log_file = os.path.abspath(log_file)
    candidates = {
        absolute_log_file,
        _log_privacy_marker_path(absolute_log_file),
        *(f"{absolute_log_file}.{index}" for index in range(1, backup_count + 1)),
        *(path for _index, path in _numeric_log_backup_paths(absolute_log_file)),
    }
    for candidate in candidates:
        if os.path.lexists(candidate):
            _set_owner_only(candidate)


def remove_excess_numeric_backups(log_file: str, backup_count: int) -> None:
    """Remove malformed and out-of-retention numeric backup names."""
    for index, candidate in _numeric_log_backup_paths(log_file):
        if index < 1 or index > backup_count:
            os.remove(candidate)


def sanitize_legacy_log_family(
    log_file: str,
    *,
    sanitizer_input_bytes: int,
) -> None:
    """Sanitize existing content before public-safe logging starts."""
    absolute_log_file = os.path.abspath(log_file)
    marker_path = _log_privacy_marker_path(absolute_log_file)

    candidates = {
        absolute_log_file,
        *(path for _index, path in _numeric_log_backup_paths(absolute_log_file)),
    }
    for candidate in candidates:
        if not os.path.lexists(candidate):
            continue
        file_status = os.lstat(candidate)
        if not stat.S_ISREG(file_status.st_mode):
            if candidate == absolute_log_file:
                raise OSError("Log path must be a regular file without links.")
            continue
        _sanitize_existing_log_file(
            candidate,
            sanitizer_input_bytes=sanitizer_input_bytes,
        )

    descriptor = open_regular_log_descriptor(
        marker_path,
        os.O_CREAT | os.O_TRUNC | os.O_WRONLY,
    )
    try:
        os.write(descriptor, _LOG_PRIVACY_FORMAT_MARKER)
    finally:
        os.close(descriptor)


def flags_for_log_mode(mode: str) -> int:
    """Translate a text file mode into secure low-level open flags."""
    flags = os.O_CREAT
    flags |= os.O_RDWR if "+" in mode else os.O_WRONLY
    if "a" in mode:
        return flags | os.O_APPEND
    if "w" in mode:
        return flags | os.O_TRUNC
    if "x" in mode:
        return flags | os.O_EXCL
    raise ValueError(f"Unsupported log file mode: {mode!r}")


def open_regular_log_descriptor(log_file: str, flags: int) -> int:
    """Open one regular non-link file and verify owner-only platform access."""
    absolute_log_file = os.path.abspath(log_file)
    log_directory = os.path.dirname(absolute_log_file)
    _require_directory_chain_without_links(log_directory)
    if os.name == "nt":
        secure_private_windows_directory(log_directory)
    if os.path.lexists(absolute_log_file):
        existing = os.lstat(absolute_log_file)
        _require_regular_unlinked_status(existing)

    descriptor = os.open(
        absolute_log_file,
        flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        _OWNER_READ_WRITE,
    )
    try:
        _require_regular_descriptor(descriptor)
        if os.name == "nt":
            secure_private_windows_file_descriptor(descriptor)
        else:
            os.fchmod(descriptor, _OWNER_READ_WRITE)
            _require_owner_only_descriptor(descriptor)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def truncate_log_file_to_bytes(log_file: str, limit: int) -> None:
    """Keep the most recent complete UTF-8 suffix within one byte budget."""
    if limit <= 0:
        return
    descriptor = open_regular_log_descriptor(log_file, os.O_RDWR)
    with os.fdopen(descriptor, "rb+") as stream:
        if os.fstat(stream.fileno()).st_size <= limit:
            return
        stream.seek(-limit, os.SEEK_END)
        payload = stream.read(limit)
        while payload and payload[0] & 0xC0 == 0x80:
            payload = payload[1:]
        stream.seek(0)
        stream.write(payload)
        stream.truncate()


def _require_directory_chain_without_links(directory: str) -> None:
    current = Path(os.path.abspath(directory))
    for candidate in (current, *current.parents):
        try:
            status = os.lstat(candidate)
        except FileNotFoundError:
            continue
        is_junction = bool(
            getattr(os.path, "isjunction", lambda _path: False)(candidate)
        )
        if stat.S_ISLNK(status.st_mode) or is_junction:
            raise OSError("Log directory chain must not contain links or junctions.")
        if candidate == current and not stat.S_ISDIR(status.st_mode):
            raise OSError("Log directory path must resolve to a directory.")


def _numeric_log_backup_paths(log_file: str) -> list[tuple[int, str]]:
    absolute_log_file = os.path.abspath(log_file)
    directory = os.path.dirname(absolute_log_file)
    prefix = f"{os.path.basename(absolute_log_file)}."
    backups: list[tuple[int, str]] = []
    for name in os.listdir(directory):
        if not name.startswith(prefix):
            continue
        suffix = name[len(prefix) :]
        if not suffix.isascii() or not suffix.isdecimal():
            continue
        index = (
            int(suffix)
            if len(suffix) <= 9 and (suffix == "0" or not suffix.startswith("0"))
            else -1
        )
        backups.append((index, os.path.join(directory, name)))
    return sorted(backups)


def _sanitize_existing_log_file(
    log_file: str,
    *,
    sanitizer_input_bytes: int,
) -> None:
    descriptor = open_regular_log_descriptor(log_file, os.O_RDWR)
    try:
        status = os.fstat(descriptor)
        read_size = min(status.st_size, sanitizer_input_bytes)
        if read_size:
            os.lseek(descriptor, -read_size, os.SEEK_END)
            payload = os.read(descriptor, read_size)
        else:
            payload = b""
        sanitized = public_diagnostic_text(
            payload.decode("utf-8", errors="replace"),
            disclosure=DiagnosticDisclosure.PUBLIC,
            layout=DiagnosticTextLayout.PRESERVE_LINES,
        )
        encoded = _truncate_text_to_bytes(
            sanitized,
            sanitizer_input_bytes,
        ).encode("utf-8")
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.write(descriptor, encoded)
        os.ftruncate(descriptor, len(encoded))
    finally:
        os.close(descriptor)


def _log_privacy_marker_path(log_file: str) -> str:
    absolute_log_file = os.path.abspath(log_file)
    directory = os.path.dirname(absolute_log_file)
    basename = os.path.basename(absolute_log_file)
    return os.path.join(directory, f".{basename}.privacy-v1")


def _require_regular_descriptor(descriptor: int) -> None:
    _require_regular_unlinked_status(os.fstat(descriptor))


def _require_regular_unlinked_status(status: os.stat_result) -> None:
    if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
        raise OSError("Log path must be a regular file without links.")


def _require_owner_only_descriptor(descriptor: int) -> None:
    status = os.fstat(descriptor)
    if (
        stat.S_IMODE(status.st_mode) != _OWNER_READ_WRITE
        or status.st_uid != os.geteuid()
    ):
        raise OSError(
            "Log file does not enforce owner-only access; file logging is unavailable."
        )


def _set_owner_only(log_file: str) -> None:
    descriptor = open_regular_log_descriptor(log_file, os.O_RDONLY)
    os.close(descriptor)


def _truncate_text_to_bytes(text: str, budget: int) -> str:
    if budget <= 0:
        return ""
    candidate = text if len(text) <= budget else text[:budget]
    encoded = candidate.encode("utf-8", errors="replace")
    if candidate is text and len(encoded) <= budget:
        return text
    marker = _TRUNCATED_RECORD_MARKER.encode()
    if budget <= len(marker):
        return marker[:budget].decode(errors="ignore")
    prefix = encoded[: budget - len(marker)].decode(errors="ignore")
    return f"{prefix}{_TRUNCATED_RECORD_MARKER}"
