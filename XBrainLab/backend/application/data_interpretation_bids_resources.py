"""Bounded admission and materialization for BIDS events JSON sidecars."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .errors import PreconditionError

if TYPE_CHECKING:
    from .resource_guard import ResourcePreflightResult


BIDS_EVENTS_JSON_READ_BUDGET_BYTES = 1_048_576


def is_bids_events_file(path: Path) -> bool:
    """Return whether a path is a BIDS-style events TSV carrier."""
    name = path.name.lower()
    return name == "events.tsv" or name.endswith("_events.tsv")


def is_bids_events_json_sidecar(path: Path) -> bool:
    """Return whether a path is named like a BIDS events JSON sidecar."""
    name = path.name.lower()
    return name == "events.json" or name.endswith("_events.json")


def bids_events_json_candidates(path: Path) -> list[Path]:
    """Return local-to-dataset-root sidecars in existing lookup order."""
    if not is_bids_events_file(path):
        return []
    names = _bids_event_sidecar_names(path)
    candidates: list[Path] = []
    for directory in _bids_inheritance_directories(path):
        for name in names:
            candidate = directory / name
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def bids_events_json_resource_paths(label_carriers: Iterable[str]) -> list[str]:
    """Return every existing events JSON candidate that preview may read."""
    result: list[str] = []
    seen: set[str] = set()
    for carrier in label_carriers:
        for candidate in bids_events_json_candidates(Path(carrier)):
            try:
                candidate_stat = candidate.stat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise _resource_error(
                    code="events_json_sidecar_unavailable",
                    message=f"BIDS events sidecar could not be inspected: {candidate}.",
                    path=candidate,
                    parse_started=False,
                    details={"os_error": str(exc)},
                ) from exc
            if not stat.S_ISREG(candidate_stat.st_mode):
                continue
            key = _path_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            result.append(key)
    return result


@dataclass
class BidsEventsJsonReadBudget:
    """Track one workflow's aggregate events JSON payload reads."""

    limit_bytes: int = BIDS_EVENTS_JSON_READ_BUDGET_BYTES
    bytes_read: int = 0

    @property
    def remaining_bytes(self) -> int:
        return max(self.limit_bytes - self.bytes_read, 0)

    def record(self, payload_bytes: int) -> None:
        if payload_bytes > self.remaining_bytes:
            raise _resource_error(
                code="events_json_read_budget_exceeded",
                message=(
                    "BIDS events JSON reads exceeded the shared workflow byte limit."
                ),
                parse_started=False,
                details={
                    "payload_bytes": payload_bytes,
                    "bytes_read": self.bytes_read,
                    "read_limit_bytes": self.limit_bytes,
                },
            )
        self.bytes_read += payload_bytes


@dataclass(frozen=True, slots=True)
class _AdmittedFileIdentity:
    """Filesystem identity captured when a bounded sidecar is admitted."""

    file_bytes: int
    device: int
    inode: int
    mtime_ns: int
    ctime_ns: int
    content_sha256: str

    def stat_diagnostics(self) -> dict[str, int]:
        return {
            "file_bytes": self.file_bytes,
            "device": self.device,
            "inode": self.inode,
            "mtime_ns": self.mtime_ns,
            "ctime_ns": self.ctime_ns,
        }

    def to_diagnostics(self) -> dict[str, int | str]:
        return {
            **self.stat_diagnostics(),
            "content_sha256": self.content_sha256,
        }


@dataclass
class BidsEventsJsonReader:
    """Read admitted sidecars once, with identity checks and a shared budget."""

    admitted_files: dict[str, _AdmittedFileIdentity]
    budget: BidsEventsJsonReadBudget = field(default_factory=BidsEventsJsonReadBudget)
    _cache: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)

    @property
    def admitted_file_bytes(self) -> dict[str, int]:
        """Expose the previous size-only view for diagnostics compatibility."""
        return {
            path: identity.file_bytes for path, identity in self.admitted_files.items()
        }

    def content_identities(
        self,
        paths: Iterable[str] | None = None,
    ) -> dict[str, dict[str, int | str]]:
        """Return exact digests captured by this parser's admission boundary."""
        expected = (
            sorted(self.admitted_files)
            if paths is None
            else sorted({_path_key(Path(path)) for path in paths})
        )
        missing = [path for path in expected if path not in self.admitted_files]
        if missing:
            raise _resource_error(
                code="events_json_sidecar_not_admitted",
                message=(
                    "BIDS events sidecar identity was requested outside the "
                    "admitted parser scope."
                ),
                path=Path(missing[0]),
                parse_started=False,
                details={"missing_paths": missing},
            )
        # Re-enter the parser boundary before exporting an identity. Cached
        # objects recheck available filesystem identity without reopening the
        # file; uncached candidates are parsed once. Every parser read verifies
        # its bytes against the admission digest exported below.
        for path in expected:
            self.read_object(Path(path))
        return {
            path: {
                "file_bytes": self.admitted_files[path].file_bytes,
                "sha256": self.admitted_files[path].content_sha256,
            }
            for path in expected
        }

    def __post_init__(self) -> None:
        admitted_total = sum(
            identity.file_bytes for identity in self.admitted_files.values()
        )
        oversized = [
            (path, identity.file_bytes)
            for path, identity in self.admitted_files.items()
            if identity.file_bytes > self.budget.limit_bytes
        ]
        if oversized:
            path, file_bytes = oversized[0]
            raise _resource_error(
                code="events_json_sidecar_too_large",
                message=(
                    f"BIDS events sidecar exceeds the {self.budget.limit_bytes}-byte "
                    f"read limit: {path}."
                ),
                path=Path(path),
                parse_started=False,
                details={
                    "admitted_bytes": file_bytes,
                    "admitted_total_bytes": admitted_total,
                    "read_limit_bytes": self.budget.limit_bytes,
                },
            )
        if admitted_total > self.budget.limit_bytes:
            raise _resource_error(
                code="events_json_read_budget_exceeded",
                message=(
                    "BIDS events sidecars exceed the shared workflow read limit of "
                    f"{self.budget.limit_bytes} bytes."
                ),
                parse_started=False,
                details={
                    "admitted_total_bytes": admitted_total,
                    "admitted_path_count": len(self.admitted_files),
                    "read_limit_bytes": self.budget.limit_bytes,
                },
            )

    @classmethod
    def from_paths(cls, paths: Iterable[str]) -> BidsEventsJsonReader:
        """Create a bounded standalone reader from current file identities."""
        admitted: dict[str, _AdmittedFileIdentity] = {}
        for raw_path in paths:
            path = Path(raw_path)
            admitted[_path_key(path)] = _admit_file_identity(path)
        return cls(admitted_files=admitted)

    @classmethod
    def from_resource_preflight(
        cls,
        paths: Iterable[str],
        preflight: ResourcePreflightResult,
    ) -> BidsEventsJsonReader:
        """Build a reader only from files recorded by authoritative preflight."""
        expected = {_path_key(Path(path)) for path in paths}
        admitted_bytes: dict[str, int] = {}
        diagnostics = preflight.to_diagnostics()
        file_rows = diagnostics.get("files")
        if isinstance(file_rows, list):
            for row in file_rows:
                if not isinstance(row, dict):
                    continue
                raw_path = str(row.get("path") or "").strip()
                if not raw_path:
                    continue
                key = _path_key(Path(raw_path))
                if key not in expected:
                    continue
                file_bytes = row.get("file_bytes")
                if isinstance(file_bytes, int) and file_bytes >= 0:
                    admitted_bytes[key] = file_bytes
        missing = sorted(expected - admitted_bytes.keys())
        if missing:
            raise _resource_error(
                code="events_json_sidecar_not_admitted",
                message=(
                    "BIDS events sidecar materialization was denied because the "
                    "authoritative resource preflight did not admit every sidecar."
                ),
                path=Path(missing[0]),
                parse_started=False,
                details={
                    "missing_paths": missing,
                    "expected_path_count": len(expected),
                    "admitted_path_count": len(admitted_bytes),
                    "read_limit_bytes": BIDS_EVENTS_JSON_READ_BUDGET_BYTES,
                },
            )
        admitted: dict[str, _AdmittedFileIdentity] = {}
        for key, expected_bytes in admitted_bytes.items():
            path = Path(key)
            identity = _admit_file_identity(path)
            if identity.file_bytes != expected_bytes:
                raise _resource_error(
                    code="events_json_sidecar_changed_after_admission",
                    message=(
                        f"BIDS events sidecar changed after resource admission: {path}."
                    ),
                    path=path,
                    parse_started=False,
                    details={
                        "admitted_bytes": expected_bytes,
                        "observed_bytes": identity.file_bytes,
                        "bytes_read": 0,
                        "read_limit_bytes": BIDS_EVENTS_JSON_READ_BUDGET_BYTES,
                    },
                )
            admitted[key] = identity
        return cls(admitted_files=admitted)

    def read_object(self, path: Path) -> dict[str, Any]:
        """Return one stable admitted JSON object, reusing the parsed object."""
        key = _path_key(path)
        admitted_identity = self.admitted_files.get(key)
        try:
            current_stat = path.stat()
        except FileNotFoundError as exc:
            if admitted_identity is not None:
                raise self._error(
                    code="events_json_sidecar_changed_after_admission",
                    message=(
                        "BIDS events sidecar disappeared after resource admission: "
                        f"{path}."
                    ),
                    path=path,
                    parse_started=False,
                    details={
                        "admitted_bytes": admitted_identity.file_bytes,
                        "observed_bytes": None,
                    },
                ) from exc
            return {}
        except OSError as exc:
            raise self._error(
                code="events_json_sidecar_unavailable",
                message=f"BIDS events sidecar could not be inspected: {path}.",
                path=path,
                parse_started=False,
                details={"os_error": str(exc)},
            ) from exc
        if not stat.S_ISREG(current_stat.st_mode):
            if admitted_identity is None:
                return {}
            raise self._error(
                code="events_json_sidecar_changed_after_admission",
                message=(
                    "BIDS events sidecar is no longer a regular file after resource "
                    f"admission: {path}."
                ),
                path=path,
                parse_started=False,
                details={
                    "admitted_bytes": admitted_identity.file_bytes,
                    "observed_bytes": max(int(current_stat.st_size), 0),
                },
            )
        if admitted_identity is None:
            raise self._error(
                code="events_json_sidecar_not_admitted",
                message=f"BIDS events sidecar was not admitted for reading: {path}.",
                path=path,
                parse_started=False,
                details={"observed_bytes": max(int(current_stat.st_size), 0)},
            )
        admitted_bytes = admitted_identity.file_bytes
        current_identity = self._identity_from_stat(path=path, file_stat=current_stat)
        self._assert_stable_identity(
            path=path,
            admitted=admitted_identity,
            observed=current_identity,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        try:
            with path.open("rb") as handle:
                opened_stat = os.fstat(handle.fileno())
                opened_identity = self._identity_from_stat(
                    path=path,
                    file_stat=opened_stat,
                )
                self._assert_stable_identity(
                    path=path,
                    admitted=admitted_identity,
                    observed=opened_identity,
                )
                encoded = handle.read(admitted_bytes)
                final_stat = os.fstat(handle.fileno())
                final_identity = self._identity_from_stat(
                    path=path,
                    file_stat=final_stat,
                )
        except PreconditionError:
            raise
        except OSError as exc:
            raise self._error(
                code="events_json_sidecar_unavailable",
                message=f"BIDS events sidecar could not be read: {path}.",
                path=path,
                parse_started=False,
                details={"os_error": str(exc)},
            ) from exc
        self._assert_stable_identity(
            path=path,
            admitted=admitted_identity,
            observed=final_identity,
        )
        if len(encoded) != admitted_bytes:
            raise self._error(
                code="events_json_sidecar_changed_after_admission",
                message=(
                    f"BIDS events sidecar changed after resource admission: {path}."
                ),
                path=path,
                parse_started=False,
                details={
                    "admitted_bytes": admitted_bytes,
                    "bytes_read": len(encoded),
                    "observed_bytes": final_identity.file_bytes,
                },
            )
        observed_sha256 = hashlib.sha256(encoded).hexdigest()
        if observed_sha256 != admitted_identity.content_sha256:
            raise self._error(
                code="events_json_sidecar_changed_after_admission",
                message=(
                    f"BIDS events sidecar changed after resource admission: {path}."
                ),
                path=path,
                parse_started=False,
                details={
                    "admitted_bytes": admitted_bytes,
                    "observed_bytes": len(encoded),
                    "bytes_read": 0,
                    "changed_identity_fields": ["content_sha256"],
                },
            )
        self.budget.record(len(encoded))
        try:
            payload = json.loads(encoded.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise self._error(
                code="events_json_sidecar_invalid",
                message=f"BIDS events sidecar is not valid JSON: {path}.",
                path=path,
                parse_started=True,
                details={"parse_error": str(exc)},
            ) from exc
        if not isinstance(payload, dict):
            raise self._error(
                code="events_json_sidecar_not_object",
                message=f"BIDS events sidecar must contain a JSON object: {path}.",
                path=path,
                parse_started=True,
            )
        self._cache[key] = payload
        return payload

    def diagnostics(self) -> dict[str, Any]:
        return {
            "read_limit_bytes": self.budget.limit_bytes,
            "bytes_read": self.budget.bytes_read,
            "admitted_path_count": len(self.admitted_files),
            "cached_path_count": len(self._cache),
        }

    def _identity_from_stat(
        self,
        *,
        path: Path,
        file_stat: os.stat_result,
    ) -> _AdmittedFileIdentity:
        identity = _file_identity(file_stat)
        if identity is not None:
            return identity
        raise self._error(
            code="events_json_sidecar_identity_unavailable",
            message=(
                f"BIDS events sidecar identity could not be verified safely: {path}."
            ),
            path=path,
            parse_started=False,
        )

    def _assert_stable_identity(
        self,
        *,
        path: Path,
        admitted: _AdmittedFileIdentity,
        observed: _AdmittedFileIdentity,
    ) -> None:
        admitted_details = admitted.stat_diagnostics()
        observed_details = observed.stat_diagnostics()
        if observed_details == admitted_details:
            return
        raise self._error(
            code="events_json_sidecar_changed_after_admission",
            message=f"BIDS events sidecar changed after resource admission: {path}.",
            path=path,
            parse_started=False,
            details={
                "admitted_bytes": admitted.file_bytes,
                "observed_bytes": observed.file_bytes,
                "changed_identity_fields": [
                    field_name
                    for field_name in admitted_details
                    if admitted_details[field_name] != observed_details[field_name]
                ],
                "admitted_identity": admitted_details,
                "observed_identity": observed_details,
            },
        )

    def _error(
        self,
        *,
        code: str,
        message: str,
        parse_started: bool,
        path: Path | None = None,
        details: dict[str, Any] | None = None,
    ) -> PreconditionError:
        return _resource_error(
            code=code,
            message=message,
            parse_started=parse_started,
            path=path,
            details={**self.diagnostics(), **dict(details or {})},
        )


def _bids_event_sidecar_names(path: Path) -> list[str]:
    names: list[str] = []
    if path.name.lower().endswith(".tsv"):
        stem = path.name[: -len(".tsv")]
        names.append(f"{stem}.json")
    prefix = path.name.removesuffix(".tsv").removesuffix("_events")
    parts = [part for part in prefix.split("_") if part]
    semantic_parts = [
        part for part in parts if not part.startswith(("sub-", "ses-", "run-"))
    ]
    if semantic_parts:
        names.append("_".join([*semantic_parts, "events"]) + ".json")
    names.append("events.json")
    return list(dict.fromkeys(names))


def _bids_inheritance_directories(path: Path) -> list[Path]:
    """Bound inheritance at the nearest BIDS dataset marker, or stay local."""
    local_directory = path.parent
    directories: list[Path] = []
    for directory in [local_directory, *local_directory.parents]:
        directories.append(directory)
        marker = directory / "dataset_description.json"
        try:
            marker.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return [local_directory]
        return directories
    return [local_directory]


def _admit_file_identity(path: Path) -> _AdmittedFileIdentity:
    try:
        with path.open("rb") as handle:
            file_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise _resource_error(
                    code="events_json_sidecar_unavailable",
                    message=f"BIDS events sidecar is not a regular file: {path}.",
                    path=path,
                    parse_started=False,
                )
            file_bytes = max(int(file_stat.st_size), 0)
            encoded = (
                handle.read(file_bytes)
                if file_bytes <= BIDS_EVENTS_JSON_READ_BUDGET_BYTES
                else b""
            )
            final_stat = os.fstat(handle.fileno())
            if (
                file_bytes <= BIDS_EVENTS_JSON_READ_BUDGET_BYTES
                and len(encoded) != file_bytes
            ):
                raise _resource_error(
                    code="events_json_sidecar_changed_after_admission",
                    message=(
                        "BIDS events sidecar changed while it was being admitted: "
                        f"{path}."
                    ),
                    path=path,
                    parse_started=False,
                    details={
                        "admitted_bytes": file_bytes,
                        "observed_bytes": len(encoded),
                        "bytes_read": 0,
                    },
                )
    except OSError as exc:
        raise _resource_error(
            code="events_json_sidecar_unavailable",
            message=f"BIDS events sidecar could not be admitted: {path}.",
            path=path,
            parse_started=False,
            details={"os_error": str(exc)},
        ) from exc
    identity = _file_identity(
        final_stat,
        content_sha256=(
            hashlib.sha256(encoded).hexdigest()
            if file_bytes <= BIDS_EVENTS_JSON_READ_BUDGET_BYTES
            else ""
        ),
    )
    if identity is None:
        raise _resource_error(
            code="events_json_sidecar_identity_unavailable",
            message=(
                f"BIDS events sidecar identity could not be admitted safely: {path}."
            ),
            path=path,
            parse_started=False,
        )
    return identity


def _file_identity(
    file_stat: os.stat_result,
    *,
    content_sha256: str = "",
) -> _AdmittedFileIdentity | None:
    try:
        identity = _AdmittedFileIdentity(
            file_bytes=max(int(file_stat.st_size), 0),
            device=int(file_stat.st_dev),
            inode=int(file_stat.st_ino),
            mtime_ns=int(file_stat.st_mtime_ns),
            ctime_ns=int(file_stat.st_ctime_ns),
            content_sha256=content_sha256,
        )
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None
    if identity.device < 0 or identity.inode <= 0:
        return None
    return identity


def _path_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def _resource_error(
    *,
    code: str,
    message: str,
    parse_started: bool,
    path: Path | None = None,
    details: dict[str, Any] | None = None,
) -> PreconditionError:
    diagnostics: dict[str, Any] = {
        "risk_level": "blocking",
        "code": code,
        "message": message,
        "json_parsing_started": parse_started,
        "state_preserved": True,
        **dict(details or {}),
    }
    if path is not None:
        diagnostics["path"] = _path_key(path)
    return PreconditionError(
        message,
        diagnostics={"bids_events_json": diagnostics},
    )
