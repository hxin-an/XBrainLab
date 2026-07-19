"""Bounded parser reader for preflight-admitted external label files."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from io import UnsupportedOperation
from pathlib import Path
from typing import Any

from XBrainLab.backend.exceptions import FileCorruptedError
from XBrainLab.backend.load_data import label_loader

from .data_interpretation_resource_reader import (
    AdmittedFileIdentity,
    AdmittedResourceReader,
)
from .errors import PreconditionError


class _BoundedBinaryReader:
    """Read/seek proxy that cannot cross the size admitted by preflight."""

    def __init__(self, handle: Any, *, limit_bytes: int) -> None:
        self._handle = handle
        self._limit_bytes = max(int(limit_bytes), 0)

    @property
    def name(self) -> str:
        return str(self._handle.name)

    @property
    def closed(self) -> bool:
        return bool(self._handle.closed)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def fileno(self) -> int:
        raise UnsupportedOperation(
            "Raw file descriptors are unavailable on bounded label streams."
        )

    def tell(self) -> int:
        return int(self._handle.tell())

    def read(self, size: int = -1) -> bytes:
        remaining = max(self._limit_bytes - self.tell(), 0)
        bounded_size = remaining if size is None or size < 0 else min(size, remaining)
        return self._handle.read(bounded_size)

    def readline(self, size: int = -1) -> bytes:
        remaining = max(self._limit_bytes - self.tell(), 0)
        bounded_size = remaining if size is None or size < 0 else min(size, remaining)
        return self._handle.readline(bounded_size)

    def readinto(self, buffer: Any) -> int:
        payload = self.read(len(buffer))
        buffer[: len(payload)] = payload
        return len(payload)

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            target = int(offset)
        elif whence == os.SEEK_CUR:
            target = self.tell() + int(offset)
        elif whence == os.SEEK_END:
            target = self._limit_bytes + int(offset)
        else:
            raise ValueError(f"Unsupported seek mode: {whence}")
        if target < 0 or target > self._limit_bytes:
            raise PreconditionError(
                "A label parser attempted to read outside its admitted file bound.",
                diagnostics={
                    "code": "label_resource_read_out_of_bounds",
                    "requested_offset": target,
                    "admitted_bytes": self._limit_bytes,
                },
            )
        return int(self._handle.seek(target, os.SEEK_SET))

    def __iter__(self) -> _BoundedBinaryReader:
        return self

    def __next__(self) -> bytes:
        line = self.readline()
        if not line:
            raise StopIteration
        return line


class AdmittedLabelResourceReader:
    """Materialize only specs in one exact admitted label-resource scope."""

    def __init__(
        self,
        resource_reader: AdmittedResourceReader,
        *,
        admitted_specs: dict[str, dict[str, Any]],
    ) -> None:
        self._resource_reader = resource_reader
        self._admitted_specs = dict(admitted_specs)

    def load(
        self,
        path: str,
        *,
        label_field: str | None = None,
        anchor: str | None = None,
        duration_field: str | None = None,
        sequence_only: bool = False,
    ) -> Any:
        """Load one exact admitted path/config through the bounded stream."""
        key = _path_key(path)
        requested = {
            "path": key,
            "label_field": _optional_text(label_field),
            "anchor": _optional_text(anchor),
            "duration_field": _optional_text(duration_field),
            "sequence_only": bool(sequence_only),
        }
        admitted = self._admitted_specs.get(key)
        if admitted != requested:
            raise PreconditionError(
                "Label parser configuration was not admitted by resource preflight.",
                diagnostics={
                    "code": "label_resource_configuration_not_admitted",
                    "path": key,
                },
            )
        try:
            return label_loader.load_label_file(
                key,
                label_field=label_field,
                anchor=anchor,
                duration_field=duration_field,
                sequence_only=sequence_only,
                resource_reader=self,
            )
        except (PreconditionError, FileCorruptedError):
            raise
        except (EOFError, OSError, TypeError, ValueError) as exc:
            raise FileCorruptedError(key, str(exc)) from exc

    @contextmanager
    def open_binary(self, path: str, *, purpose: str) -> Iterator[_BoundedBinaryReader]:
        """Open a stable file descriptor capped at its admitted byte length."""
        key = _path_key(path)
        identity = self._resource_reader.admitted_files.get(key)
        if identity is None:
            raise PreconditionError(
                f"Label resource was not admitted: {path}.",
                diagnostics={
                    "code": "label_resource_not_admitted",
                    "path": key,
                    "parse_started": False,
                },
            )
        with self._resource_reader.guard([key], purpose=purpose):
            try:
                with open(key, "rb") as handle:
                    _assert_open_identity(handle, identity, path=key)
                    yield _BoundedBinaryReader(
                        handle,
                        limit_bytes=identity.file_bytes,
                    )
            except OSError as exc:
                raise PreconditionError(
                    f"Admitted label resource is no longer available: {path}.",
                    diagnostics={
                        "code": "label_resource_changed_after_admission",
                        "path": key,
                        "parse_started": False,
                    },
                ) from exc

    def diagnostics(self) -> dict[str, Any]:
        return self._resource_reader.diagnostics()

    def assert_current(self, paths: list[str], *, purpose: str) -> None:
        """Verify admitted identities without exposing or rereading file payloads."""
        normalized = [_path_key(path) for path in paths]
        with self._resource_reader.guard(normalized, purpose=purpose):
            return


def _assert_open_identity(
    handle: Any,
    admitted: AdmittedFileIdentity,
    *,
    path: str,
) -> None:
    opened = os.fstat(handle.fileno())
    observed = {
        "file_bytes": int(opened.st_size),
        "device": int(opened.st_dev),
        "inode": int(opened.st_ino),
        "mtime_ns": int(opened.st_mtime_ns),
        "ctime_ns": int(opened.st_ctime_ns),
    }
    expected = admitted.to_diagnostics()
    changed = [key for key, value in observed.items() if expected[key] != value]
    if changed:
        raise PreconditionError(
            f"A label resource changed after admission: {path}.",
            diagnostics={
                "code": "label_resource_changed_after_admission",
                "path": path,
                "parse_started": False,
                "changed_fields": changed,
            },
        )


def _path_key(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
