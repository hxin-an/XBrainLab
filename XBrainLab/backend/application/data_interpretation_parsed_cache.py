"""Bounded immutable cache for Data Interpretation sidecar projections.

The cache never keys parsed truth by a path or timestamp alone.  Every retained
entry is bound to the complete source bytes, a named parser, and an explicit
schema version.  A path/stat binding is only a freshness shortcut on platforms
where change time is reliable; the retained entry's identity remains SHA-256.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import stat
from collections import OrderedDict
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, TypeAlias, cast

DEFAULT_PARSED_CACHE_MAX_ENTRIES = 128
DEFAULT_PARSED_CACHE_MAX_RETAINED_BYTES = 32 * 1024 * 1024
DEFAULT_PARSED_CACHE_MAX_FILE_BYTES = 4 * 1024 * 1024
PARSED_CONTENT_HASH_ALGORITHM = "sha256"
DELIMITED_TABLE_PARSER_SCHEMA_VERSION = 1
PARSED_CONTENT_PROBE_BYTES = 4096
_STAT_CHANGE_TIME_IS_RELIABLE = os.name != "nt"


class ParsedContentTooLargeError(OSError):
    """Signal that a caller should use its existing streaming fallback."""


@dataclass(frozen=True, slots=True)
class ParsedContentKey:
    """Identity of one parser result over exact complete source bytes."""

    parser_id: str
    schema_version: int
    content_bytes: int
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ParsedDelimitedTable:
    """Immutable delimited rows; callers receive new dictionaries on demand."""

    fieldnames: tuple[str, ...]
    rows: tuple[tuple[tuple[str, str], ...], ...]
    file_bytes: int
    content_sha256: str

    def dict_rows(self) -> list[dict[str, str]]:
        """Return mutable projections without exposing retained cache state."""
        return [dict(row) for row in self.rows]


@dataclass(frozen=True, slots=True)
class _FrozenJsonObject:
    items: tuple[tuple[str, _FrozenJsonValue], ...]


@dataclass(frozen=True, slots=True)
class _FrozenJsonArray:
    items: tuple[_FrozenJsonValue, ...]


_JsonScalar: TypeAlias = str | int | float | bool | None
_FrozenJsonValue: TypeAlias = _JsonScalar | _FrozenJsonObject | _FrozenJsonArray
_CachedValue: TypeAlias = _FrozenJsonValue | ParsedDelimitedTable


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    value: _CachedValue
    retained_bytes: int
    value_kind: str


@dataclass(frozen=True, slots=True)
class _FileIdentity:
    device: int
    inode: int
    file_bytes: int
    mtime_ns: int
    ctime_ns: int
    content_probe_sha256: str


class _FileIdentityLike(Protocol):
    """Structural boundary for identities admitted by the resource guard."""

    device: Any
    inode: Any
    file_bytes: Any
    mtime_ns: Any
    ctime_ns: Any
    content_probe_sha256: Any


_VERIFIED_PARSED_CONTENT_IDENTITIES: ContextVar[
    tuple[tuple[str, _FileIdentity], ...]
] = ContextVar(
    "verified_data_interpretation_parsed_content_identities",
    default=(),
)


@dataclass(frozen=True, slots=True)
class _PathBinding:
    identity: _FileIdentity
    cache_key: ParsedContentKey
    value_kind: str


class ParsedContentCache:
    """Thread-safe LRU of immutable JSON and delimited-table projections."""

    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_PARSED_CACHE_MAX_ENTRIES,
        max_retained_bytes: int = DEFAULT_PARSED_CACHE_MAX_RETAINED_BYTES,
        max_file_bytes: int = DEFAULT_PARSED_CACHE_MAX_FILE_BYTES,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        if max_retained_bytes <= 0:
            raise ValueError("max_retained_bytes must be positive")
        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        self.max_entries = int(max_entries)
        self.max_retained_bytes = int(max_retained_bytes)
        self.max_file_bytes = int(max_file_bytes)
        self._entries: OrderedDict[ParsedContentKey, _CacheEntry] = OrderedDict()
        self._path_bindings: OrderedDict[tuple[str, str, int], _PathBinding] = (
            OrderedDict()
        )
        self._retained_bytes = 0
        self._hit_count = 0
        self._miss_count = 0
        self._parse_count = 0
        self._file_read_count = 0
        self._eviction_count = 0
        self._lock = RLock()

    def clear(self) -> None:
        """Drop all retained projections and diagnostic counters."""
        with self._lock:
            self._entries.clear()
            self._path_bindings.clear()
            self._retained_bytes = 0
            self._hit_count = 0
            self._miss_count = 0
            self._parse_count = 0
            self._file_read_count = 0
            self._eviction_count = 0

    def diagnostics(self) -> dict[str, Any]:
        """Return a bounded, non-content-bearing cache snapshot."""
        with self._lock:
            return {
                "algorithm": PARSED_CONTENT_HASH_ALGORITHM,
                "entry_count": len(self._entries),
                "path_binding_count": len(self._path_bindings),
                "retained_bytes": self._retained_bytes,
                "max_entries": self.max_entries,
                "max_retained_bytes": self.max_retained_bytes,
                "max_file_bytes": self.max_file_bytes,
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "parse_count": self._parse_count,
                "file_read_count": self._file_read_count,
                "eviction_count": self._eviction_count,
            }

    def json_value_from_verified_bytes(
        self,
        payload: bytes,
        *,
        parser_id: str,
        schema_version: int,
        expected_sha256: str | None = None,
    ) -> tuple[Any, ParsedContentKey]:
        """Parse JSON once after binding the complete supplied byte payload."""
        normalized_parser_id, normalized_schema = _parser_contract(
            parser_id,
            schema_version,
        )
        digest = hashlib.sha256(payload).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError("supplied content does not match expected SHA-256")
        key = ParsedContentKey(
            parser_id=normalized_parser_id,
            schema_version=normalized_schema,
            content_bytes=len(payload),
            content_sha256=digest,
        )
        with self._lock:
            cached = self._lookup_locked(key, value_kind="json")
            if cached is not None:
                return _thaw_json(cached), key
            self._miss_count += 1
            parsed = _freeze_json(_parse_json_value(payload))
            self._parse_count += 1
            self._retain_locked(
                key,
                _CacheEntry(
                    value=parsed,
                    retained_bytes=max(len(payload), _estimated_value_bytes(parsed)),
                    value_kind="json",
                ),
            )
            return _thaw_json(parsed), key

    def json_value_from_path(
        self,
        path: str | Path,
        *,
        parser_id: str,
        schema_version: int,
    ) -> tuple[Any, ParsedContentKey]:
        """Return JSON for one stable file, reusing an unchanged path binding."""
        normalized_parser_id, normalized_schema = _parser_contract(
            parser_id,
            schema_version,
        )
        value = self._path_cache_hit(
            Path(path),
            parser_id=normalized_parser_id,
            schema_version=normalized_schema,
            value_kind="json",
        )
        if value is not None:
            frozen, key = value
            return _thaw_json(frozen), key
        payload, identity = self._read_stable_bytes(Path(path))
        parsed, key = self.json_value_from_verified_bytes(
            payload,
            parser_id=normalized_parser_id,
            schema_version=normalized_schema,
        )
        self._bind_path(
            Path(path),
            parser_id=normalized_parser_id,
            schema_version=normalized_schema,
            identity=identity,
            key=key,
            value_kind="json",
        )
        return parsed, key

    def delimited_table_from_path(
        self,
        path: str | Path,
        *,
        delimiter: str,
        parser_id: str,
        schema_version: int = DELIMITED_TABLE_PARSER_SCHEMA_VERSION,
    ) -> ParsedDelimitedTable:
        """Parse a complete small table once and retain immutable rows."""
        if len(delimiter) != 1:
            raise ValueError("delimiter must be one character")
        normalized_parser_id, normalized_schema = _parser_contract(
            f"{parser_id}:delimiter={ord(delimiter)}",
            schema_version,
        )
        value = self._path_cache_hit(
            Path(path),
            parser_id=normalized_parser_id,
            schema_version=normalized_schema,
            value_kind="delimited_table",
        )
        if value is not None:
            table, _key = value
            if not isinstance(table, ParsedDelimitedTable):  # pragma: no cover
                raise TypeError("cached delimited-table value has the wrong type")
            return table
        payload, identity = self._read_stable_bytes(Path(path))
        digest = hashlib.sha256(payload).hexdigest()
        key = ParsedContentKey(
            parser_id=normalized_parser_id,
            schema_version=normalized_schema,
            content_bytes=len(payload),
            content_sha256=digest,
        )
        with self._lock:
            cached = self._lookup_locked(key, value_kind="delimited_table")
            if cached is None:
                self._miss_count += 1
                table = _parse_delimited_table(
                    payload,
                    delimiter=delimiter,
                    content_sha256=digest,
                )
                self._parse_count += 1
                self._retain_locked(
                    key,
                    _CacheEntry(
                        value=table,
                        retained_bytes=max(
                            len(payload),
                            _estimated_value_bytes(table),
                        ),
                        value_kind="delimited_table",
                    ),
                )
            else:
                if not isinstance(cached, ParsedDelimitedTable):  # pragma: no cover
                    raise TypeError("cached delimited-table value has the wrong type")
                table = cached
        self._bind_path(
            Path(path),
            parser_id=normalized_parser_id,
            schema_version=normalized_schema,
            identity=identity,
            key=key,
            value_kind="delimited_table",
        )
        return table

    def _path_cache_hit(
        self,
        path: Path,
        *,
        parser_id: str,
        schema_version: int,
        value_kind: str,
    ) -> tuple[_CachedValue, ParsedContentKey] | None:
        canonical_path = _canonical_path(path)
        verified_identity = dict(_VERIFIED_PARSED_CONTENT_IDENTITIES.get()).get(
            canonical_path
        )
        binding_key = (_canonical_path(path), parser_id, schema_version)
        with self._lock:
            binding = self._path_bindings.get(binding_key)
            if binding is None or binding.value_kind != value_kind:
                self._path_bindings.pop(binding_key, None)
                return None
            freshness_verified = (
                verified_identity is not None and binding.identity == verified_identity
            )
            # An admitted resource guard verifies the same path immediately
            # before and after its parser group, so repeated projections inside
            # that group do not need another descriptor probe each.  Standalone
            # callers retain the conservative per-lookup freshness probe.
            # Windows exposes creation time as ctime.  Even inside an admitted
            # guard, its bounded probe cannot prove that unchanged middle bytes
            # still match the full-SHA cache identity, so force a complete read.
            if not _STAT_CHANGE_TIME_IS_RELIABLE:
                return None
            if not freshness_verified:
                try:
                    identity = _path_identity(path)
                except OSError:
                    return None
                if binding.identity != identity:
                    self._path_bindings.pop(binding_key, None)
                    return None
            cached = self._lookup_locked(
                binding.cache_key,
                value_kind=value_kind,
            )
            if cached is None:
                self._path_bindings.pop(binding_key, None)
                return None
            self._path_bindings.move_to_end(binding_key)
            return cached, binding.cache_key

    def _read_stable_bytes(self, path: Path) -> tuple[bytes, _FileIdentity]:
        payload, identity = _stable_file_bytes(
            path,
            max_file_bytes=self.max_file_bytes,
        )
        with self._lock:
            self._file_read_count += 1
        return payload, identity

    def _bind_path(
        self,
        path: Path,
        *,
        parser_id: str,
        schema_version: int,
        identity: _FileIdentity,
        key: ParsedContentKey,
        value_kind: str,
    ) -> None:
        binding_key = (_canonical_path(path), parser_id, schema_version)
        with self._lock:
            if key not in self._entries:
                return
            self._path_bindings[binding_key] = _PathBinding(
                identity=identity,
                cache_key=key,
                value_kind=value_kind,
            )
            self._path_bindings.move_to_end(binding_key)
            while len(self._path_bindings) > self.max_entries * 2:
                self._path_bindings.popitem(last=False)

    def _lookup_locked(
        self,
        key: ParsedContentKey,
        *,
        value_kind: str,
    ) -> _CachedValue | None:
        entry = self._entries.get(key)
        if entry is None or entry.value_kind != value_kind:
            return None
        self._entries.move_to_end(key)
        self._hit_count += 1
        return entry.value

    def _retain_locked(self, key: ParsedContentKey, entry: _CacheEntry) -> None:
        if entry.retained_bytes > self.max_retained_bytes:
            return
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._retained_bytes -= previous.retained_bytes
        self._entries[key] = entry
        self._retained_bytes += entry.retained_bytes
        while (
            len(self._entries) > self.max_entries
            or self._retained_bytes > self.max_retained_bytes
        ):
            evicted_key, evicted = self._entries.popitem(last=False)
            self._retained_bytes -= evicted.retained_bytes
            self._eviction_count += 1
            stale_bindings = [
                binding_key
                for binding_key, binding in self._path_bindings.items()
                if binding.cache_key == evicted_key
            ]
            for binding_key in stale_bindings:
                self._path_bindings.pop(binding_key, None)


def _parse_json_value(payload: bytes) -> Any:
    return json.loads(payload.decode("utf-8-sig"))


def _parse_delimited_table(
    payload: bytes,
    *,
    delimiter: str,
    content_sha256: str,
) -> ParsedDelimitedTable:
    text = payload.decode("utf-8-sig")
    with io.StringIO(text, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = tuple(str(name) for name in reader.fieldnames or [] if name)
        rows = tuple(
            tuple((str(key), str(value or "")) for key, value in row.items() if key)
            for row in reader
        )
    return ParsedDelimitedTable(
        fieldnames=fieldnames,
        rows=rows,
        file_bytes=len(payload),
        content_sha256=content_sha256,
    )


def _stable_file_bytes(
    path: Path,
    *,
    max_file_bytes: int,
) -> tuple[bytes, _FileIdentity]:
    expanded = path.expanduser()
    entry_stat = expanded.lstat()
    if stat.S_ISLNK(entry_stat.st_mode) or not stat.S_ISREG(entry_stat.st_mode):
        raise OSError(f"parsed content source is not a regular file: {expanded}")
    file_attributes = int(getattr(entry_stat, "st_file_attributes", 0) or 0)
    if file_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400):
        raise OSError(f"parsed content source is a reparse point: {expanded}")
    if int(entry_stat.st_size) > max_file_bytes:
        raise ParsedContentTooLargeError(
            f"parsed content source exceeds {max_file_bytes} bytes: {expanded}"
        )
    descriptor = os.open(
        expanded,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            opened_stat = os.fstat(handle.fileno())
            opened_stat_identity = _identity_from_stat(opened_stat)
            if opened_stat_identity != _identity_from_stat(entry_stat):
                raise OSError(f"parsed content source changed before read: {expanded}")
            payload = handle.read(opened_stat_identity.file_bytes)
            finished_stat_identity = _identity_from_stat(os.fstat(handle.fileno()))
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    final_stat_identity = _identity_from_stat(expanded.lstat())
    if not (
        opened_stat_identity == finished_stat_identity == final_stat_identity
        and len(payload) == opened_stat_identity.file_bytes
    ):
        raise OSError(f"parsed content source changed during read: {expanded}")
    return payload, _identity_with_probe(
        opened_stat_identity,
        _content_probe_for_payload(payload),
    )


def _path_identity(path: Path) -> _FileIdentity:
    expanded = path.expanduser()
    entry_stat = expanded.lstat()
    if stat.S_ISLNK(entry_stat.st_mode) or not stat.S_ISREG(entry_stat.st_mode):
        raise OSError(f"parsed content source is not a regular file: {path}")
    entry_identity = _identity_from_stat(entry_stat)
    descriptor = os.open(
        expanded,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            opened_identity = _identity_from_stat(os.fstat(handle.fileno()))
            if opened_identity != entry_identity:
                raise OSError(f"parsed content source changed before probe: {path}")
            probe = _content_probe_for_handle(handle, entry_identity.file_bytes)
            finished_identity = _identity_from_stat(os.fstat(handle.fileno()))
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    final_identity = _identity_from_stat(expanded.lstat())
    if not (entry_identity == opened_identity == finished_identity == final_identity):
        raise OSError(f"parsed content source changed during probe: {path}")
    return _identity_with_probe(entry_identity, probe)


def _identity_from_stat(value: os.stat_result) -> _FileIdentity:
    return _FileIdentity(
        device=int(value.st_dev),
        inode=int(value.st_ino),
        file_bytes=max(int(value.st_size), 0),
        mtime_ns=int(value.st_mtime_ns),
        ctime_ns=int(value.st_ctime_ns),
        content_probe_sha256="",
    )


def _identity_with_probe(identity: _FileIdentity, probe: str) -> _FileIdentity:
    return _FileIdentity(
        device=identity.device,
        inode=identity.inode,
        file_bytes=identity.file_bytes,
        mtime_ns=identity.mtime_ns,
        ctime_ns=identity.ctime_ns,
        content_probe_sha256=probe,
    )


def _content_probe_for_payload(payload: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(str(len(payload)).encode("ascii"))
    if len(payload) <= PARSED_CONTENT_PROBE_BYTES * 2:
        digest.update(payload)
    else:
        digest.update(payload[:PARSED_CONTENT_PROBE_BYTES])
        digest.update(payload[-PARSED_CONTENT_PROBE_BYTES:])
    return digest.hexdigest()


def _content_probe_for_handle(handle: Any, file_bytes: int) -> str:
    digest = hashlib.sha256()
    digest.update(str(file_bytes).encode("ascii"))
    if file_bytes <= PARSED_CONTENT_PROBE_BYTES * 2:
        digest.update(handle.read())
    else:
        digest.update(handle.read(PARSED_CONTENT_PROBE_BYTES))
        handle.seek(file_bytes - PARSED_CONTENT_PROBE_BYTES)
        digest.update(handle.read(PARSED_CONTENT_PROBE_BYTES))
    return digest.hexdigest()


def _canonical_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path.expanduser())))


def _parser_contract(parser_id: str, schema_version: int) -> tuple[str, int]:
    normalized_parser_id = str(parser_id).strip()
    if not normalized_parser_id:
        raise ValueError("parser_id is required")
    if isinstance(schema_version, bool) or int(schema_version) <= 0:
        raise ValueError("schema_version must be a positive integer")
    return normalized_parser_id, int(schema_version)


def _freeze_json(value: Any) -> _FrozenJsonValue:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, dict):
        return _FrozenJsonObject(
            tuple((str(key), _freeze_json(item)) for key, item in value.items())
        )
    if isinstance(value, list):
        return _FrozenJsonArray(tuple(_freeze_json(item) for item in value))
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def _thaw_json(value: _CachedValue) -> Any:
    if isinstance(value, _FrozenJsonObject):
        return {key: _thaw_json(item) for key, item in value.items}
    if isinstance(value, _FrozenJsonArray):
        return [_thaw_json(item) for item in value.items]
    return value


def _estimated_value_bytes(value: _CachedValue) -> int:
    if value is None:
        return 1
    if isinstance(value, bool | int | float):
        return 16
    if isinstance(value, str):
        return len(value.encode("utf-8")) + 16
    if isinstance(value, _FrozenJsonObject):
        return 32 + sum(
            len(key.encode("utf-8")) + _estimated_value_bytes(item)
            for key, item in value.items
        )
    if isinstance(value, _FrozenJsonArray):
        return 24 + sum(_estimated_value_bytes(item) for item in value.items)
    if isinstance(value, ParsedDelimitedTable):
        return (
            64
            + sum(len(item.encode("utf-8")) + 8 for item in value.fieldnames)
            + sum(
                len(key.encode("utf-8")) + len(item.encode("utf-8")) + 16
                for row in value.rows
                for key, item in row
            )
        )
    raise TypeError(f"unsupported parsed cache value: {type(value).__name__}")


_DEFAULT_PARSED_CONTENT_CACHE = ParsedContentCache()


def default_parsed_content_cache() -> ParsedContentCache:
    """Return the backend-owned bounded cache shared by review projections."""
    return _DEFAULT_PARSED_CONTENT_CACHE


@contextmanager
def verified_parsed_content_paths(
    identities: Mapping[str | Path, object],
) -> Iterator[None]:
    """Bind this parser group to the exact identities its guard admitted."""
    verified = dict(_VERIFIED_PARSED_CONTENT_IDENTITIES.get())
    for path, identity in identities.items():
        verified[_canonical_path(Path(path))] = _verified_file_identity(identity)
    token = _VERIFIED_PARSED_CONTENT_IDENTITIES.set(tuple(verified.items()))
    try:
        yield
    finally:
        _VERIFIED_PARSED_CONTENT_IDENTITIES.reset(token)


def _verified_file_identity(value: object) -> _FileIdentity:
    """Normalize an admission identity without importing its owning guard."""
    identity = cast(_FileIdentityLike, value)
    try:
        return _FileIdentity(
            device=int(identity.device),
            inode=int(identity.inode),
            file_bytes=int(identity.file_bytes),
            mtime_ns=int(identity.mtime_ns),
            ctime_ns=int(identity.ctime_ns),
            content_probe_sha256=str(identity.content_probe_sha256),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise TypeError("verified parsed-content identity is invalid") from exc


def parsed_delimited_table(
    path: str | Path,
    *,
    delimiter: str,
    parser_id: str = "data-interpretation-delimited-table",
    schema_version: int = DELIMITED_TABLE_PARSER_SCHEMA_VERSION,
) -> ParsedDelimitedTable:
    """Use the shared cache for one complete delimited sidecar."""
    return default_parsed_content_cache().delimited_table_from_path(
        path,
        delimiter=delimiter,
        parser_id=parser_id,
        schema_version=schema_version,
    )


def parsed_json_value(
    path: str | Path,
    *,
    parser_id: str,
    schema_version: int,
) -> tuple[Any, ParsedContentKey]:
    """Use the shared cache for one complete JSON sidecar."""
    return default_parsed_content_cache().json_value_from_path(
        path,
        parser_id=parser_id,
        schema_version=schema_version,
    )
