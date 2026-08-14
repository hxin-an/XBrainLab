"""Authoritative file identities for one Data Interpretation materialization."""

from __future__ import annotations

import hashlib
import math
import os
import stat
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .data_interpretation_path_identity import CanonicalPathIdentityScope
from .errors import PreconditionError

if TYPE_CHECKING:
    from .resource_guard import ResourcePreflightResult


RESOURCE_IDENTITY_PROBE_BYTES = 4_096


@dataclass(frozen=True, slots=True)
class AdmittedFileIdentity:
    """Stable filesystem identity captured after authoritative preflight."""

    file_bytes: int
    device: int
    inode: int
    mtime_ns: int
    ctime_ns: int
    content_probe_sha256: str

    def to_diagnostics(self) -> dict[str, int | str]:
        return {
            "file_bytes": self.file_bytes,
            "device": self.device,
            "inode": self.inode,
            "mtime_ns": self.mtime_ns,
            "ctime_ns": self.ctime_ns,
            "content_probe_sha256": self.content_probe_sha256,
        }


@dataclass(frozen=True, slots=True)
class AdmittedRecordingBounds:
    """Continuous-recording bounds obtained by the authoritative preflight."""

    sample_count: int
    sampling_frequency_hz: float


@dataclass(frozen=True, slots=True)
class AdmittedResourceReader:
    """Verify every parser input against one exact preflight-admitted scope."""

    admitted_files: dict[str, AdmittedFileIdentity]
    dependent_files: dict[str, tuple[str, ...]] = field(default_factory=dict)
    recording_bounds: dict[str, AdmittedRecordingBounds] = field(default_factory=dict)
    canonical_path_aliases: dict[str, str] = field(default_factory=dict)
    path_identity_scope: CanonicalPathIdentityScope = field(
        default_factory=lambda: CanonicalPathIdentityScope.from_admitted_paths(()),
    )

    def canonical_key(self, path: str | Path) -> str:
        """Return an admitted canonical path without redundant filesystem walks."""
        resource_path = Path(path)
        lexical_key = _lexical_path_key(resource_path)
        return self.canonical_path_aliases.get(
            lexical_key
        ) or self.path_identity_scope.identity(resource_path)

    def canonical_value(self, path: str | Path) -> str:
        """Return one admitted canonical spelling without another filesystem walk."""
        return self.path_identity_scope.value(path)

    def admits(self, path: str | Path) -> bool:
        """Return whether this exact resolved file belongs to the admitted scope."""
        return self.canonical_key(path) in self.admitted_files

    @classmethod
    def from_resource_preflight(
        cls,
        paths: Iterable[str],
        preflight: ResourcePreflightResult,
        *,
        dependent_files: Mapping[str, Iterable[str | Path]] | None = None,
        path_identity_scope: CanonicalPathIdentityScope | None = None,
    ) -> AdmittedResourceReader:
        requested_paths = [Path(path) for path in paths]
        canonical_paths = [
            (
                path_identity_scope.identity(path)
                if path_identity_scope is not None
                and path_identity_scope.contains(path)
                else _path_key(path)
            )
            for path in requested_paths
        ]
        retained_scope = (
            path_identity_scope
            or CanonicalPathIdentityScope.from_admitted_paths(canonical_paths)
        )
        expected = set(canonical_paths)
        admitted_bytes = _preflight_file_bytes(
            preflight,
            expected,
            path_identity_scope=retained_scope,
        )
        missing = sorted(expected - admitted_bytes.keys())
        if missing:
            raise _resource_error(
                code="interpretation_resource_not_admitted",
                message=(
                    "Data Interpretation materialization was denied because "
                    "resource preflight did not admit every selected file."
                ),
                path=Path(missing[0]),
                parse_started=False,
                details={"missing_paths": missing},
            )

        admitted: dict[str, AdmittedFileIdentity] = {}
        for key, expected_bytes in admitted_bytes.items():
            identity = _current_identity(Path(key))
            if identity.file_bytes != expected_bytes:
                raise _changed_error(
                    Path(key),
                    admitted_bytes=expected_bytes,
                    observed=identity,
                    parse_started=False,
                    purpose="resource admission",
                )
            admitted[key] = identity
        preflight_dependencies = _preflight_dependencies(
            preflight,
            set(admitted),
            path_identity_scope=retained_scope,
        )
        explicit_dependencies = _explicit_dependencies(
            dependent_files,
            admitted=set(admitted),
            path_identity_scope=retained_scope,
        )
        return cls(
            admitted_files=admitted,
            dependent_files=_merge_dependencies(
                preflight_dependencies,
                explicit_dependencies,
            ),
            recording_bounds=_preflight_recording_bounds(
                preflight,
                admitted=set(admitted),
                path_identity_scope=retained_scope,
            ),
            canonical_path_aliases=_canonical_aliases(
                requested_paths,
                canonical_paths,
            ),
            path_identity_scope=retained_scope,
        )

    def with_dependent_files(
        self,
        dependent_files: Mapping[str, Iterable[str | Path]],
    ) -> AdmittedResourceReader:
        """Bind freshly resolved parser dependencies to this admitted scope."""
        explicit_dependencies = _explicit_dependencies(
            dependent_files,
            admitted=set(self.admitted_files),
            path_identity_scope=self.path_identity_scope,
        )
        return AdmittedResourceReader(
            admitted_files=dict(self.admitted_files),
            dependent_files=_merge_dependencies(
                self.dependent_files,
                explicit_dependencies,
            ),
            recording_bounds=dict(self.recording_bounds),
            canonical_path_aliases=dict(self.canonical_path_aliases),
            path_identity_scope=self.path_identity_scope,
        )

    def recording_bounds_for(
        self,
        path: str | Path,
    ) -> AdmittedRecordingBounds | None:
        """Return trustworthy header bounds for an admitted continuous recording."""
        return self.recording_bounds.get(self.canonical_key(path))

    def assert_unchanged(
        self,
        path: str | Path,
        *,
        purpose: str,
        parse_started: bool = False,
    ) -> None:
        """Fail closed when a parser input was not admitted or has changed."""
        resource_path = Path(path)
        key = self.canonical_key(resource_path)
        self._assert_unchanged_now(
            resource_path,
            key=key,
            purpose=purpose,
            parse_started=parse_started,
        )

    def _assert_unchanged_now(
        self,
        resource_path: Path,
        *,
        key: str,
        purpose: str,
        parse_started: bool,
    ) -> None:
        """Perform one non-memoized admitted identity check."""
        admitted = self.admitted_files.get(key)
        if admitted is None:
            raise _resource_error(
                code="interpretation_resource_not_admitted",
                message=(
                    f"Data Interpretation did not admit this file: {resource_path}."
                ),
                path=resource_path,
                parse_started=parse_started,
                details={"purpose": purpose},
            )
        try:
            observed = _current_identity(Path(key))
        except PreconditionError as exc:
            diagnostics = dict(exc.diagnostics)
            diagnostics.update(
                {
                    "code": "interpretation_resource_changed_after_admission",
                    "purpose": purpose,
                    "parse_started": parse_started,
                    "admitted_identity": admitted.to_diagnostics(),
                }
            )
            raise PreconditionError(
                f"A selected Data Interpretation file changed after resource "
                f"admission: {resource_path}.",
                diagnostics=diagnostics,
            ) from exc
        if observed != admitted:
            raise _changed_error(
                resource_path,
                admitted_bytes=admitted.file_bytes,
                observed=observed,
                admitted=admitted,
                parse_started=parse_started,
                purpose=purpose,
            )

    @contextmanager
    def guard(
        self,
        paths: Iterable[str | Path],
        *,
        purpose: str,
    ) -> Iterator[None]:
        """Verify file identity immediately before and after one parser call."""
        resource_paths = self._expanded_guard_paths(paths)
        for path in resource_paths:
            self.assert_unchanged(path, purpose=purpose, parse_started=False)
        # Lazy import keeps the identity reader independent at module import
        # while allowing every admitted parser group to share one freshness
        # boundary with the backend-owned immutable parsed-content cache.
        from .data_interpretation_parsed_cache import (  # noqa: PLC0415
            verified_parsed_content_paths,
        )

        verified_identities: dict[str | Path, object] = {
            path: self.admitted_files[self.canonical_key(path)]
            for path in resource_paths
        }
        with verified_parsed_content_paths(verified_identities):
            yield
        for path in resource_paths:
            self.assert_unchanged(path, purpose=purpose, parse_started=True)

    def _expanded_guard_paths(
        self,
        paths: Iterable[str | Path],
    ) -> tuple[Path, ...]:
        expanded: list[Path] = []
        seen: set[str] = set()
        pending = [Path(path) for path in paths]
        while pending:
            path = pending.pop(0)
            key = self.canonical_key(path)
            if key in seen:
                continue
            seen.add(key)
            expanded.append(Path(key))
            pending.extend(Path(item) for item in self.dependent_files.get(key, ()))
        return tuple(expanded)

    def diagnostics(self) -> dict[str, Any]:
        return {
            "admitted_path_count": len(self.admitted_files),
            "admitted_total_bytes": sum(
                identity.file_bytes for identity in self.admitted_files.values()
            ),
            "dependent_path_count": sum(
                len(paths) for paths in self.dependent_files.values()
            ),
            "recording_bounds_count": len(self.recording_bounds),
            "identity_fields": [
                "file_bytes",
                "device",
                "inode",
                "mtime_ns",
                "ctime_ns",
                "content_probe_sha256",
            ],
        }


def _preflight_file_bytes(
    preflight: ResourcePreflightResult,
    expected: set[str],
    *,
    path_identity_scope: CanonicalPathIdentityScope,
) -> dict[str, int]:
    admitted: dict[str, int] = {}
    rows = preflight.to_diagnostics().get("files")
    if not isinstance(rows, list):
        return admitted
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_path = str(row.get("path") or "").strip()
        file_bytes = row.get("file_bytes")
        if not raw_path or not isinstance(file_bytes, int) or file_bytes < 0:
            continue
        key = path_identity_scope.identity(raw_path)
        if key in expected:
            admitted[key] = file_bytes
    return admitted


def _preflight_dependencies(
    preflight: ResourcePreflightResult,
    admitted: set[str],
    *,
    path_identity_scope: CanonicalPathIdentityScope,
) -> dict[str, tuple[str, ...]]:
    dependencies: dict[str, list[str]] = {}
    rows = preflight.to_diagnostics().get("files")
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        owner_text = str(row.get("path") or "").strip()
        dependency_text = str(row.get("associated_data_file") or "").strip()
        if not owner_text or not dependency_text:
            continue
        owner = path_identity_scope.identity(owner_text)
        dependency = path_identity_scope.identity(dependency_text)
        if owner not in admitted or dependency not in admitted:
            continue
        dependencies.setdefault(owner, []).append(dependency)
    return {owner: tuple(dict.fromkeys(paths)) for owner, paths in dependencies.items()}


def _preflight_recording_bounds(
    preflight: ResourcePreflightResult,
    *,
    admitted: set[str],
    path_identity_scope: CanonicalPathIdentityScope,
) -> dict[str, AdmittedRecordingBounds]:
    bounds: dict[str, AdmittedRecordingBounds] = {}
    rows = preflight.to_diagnostics().get("files")
    if not isinstance(rows, list):
        return bounds
    for row in rows:
        if not isinstance(row, dict) or row.get("size_bound_known", True) is not True:
            continue
        raw_path = str(row.get("path") or "").strip()
        sample_count = row.get("time_samples")
        sampling_frequency = row.get("sampling_rate_hz")
        if (
            not raw_path
            or isinstance(sample_count, bool)
            or not isinstance(sample_count, int)
            or sample_count <= 0
            or isinstance(sampling_frequency, bool)
            or not isinstance(sampling_frequency, int | float)
            or not math.isfinite(float(sampling_frequency))
            or float(sampling_frequency) <= 0
            or not _is_continuous_recording(row.get("trials"))
        ):
            continue
        key = path_identity_scope.identity(raw_path)
        if key not in admitted:
            continue
        bounds[key] = AdmittedRecordingBounds(
            sample_count=sample_count,
            sampling_frequency_hz=float(sampling_frequency),
        )
    return bounds


def _is_continuous_recording(raw_trials: Any) -> bool:
    if raw_trials is None:
        return True
    if isinstance(raw_trials, bool) or not isinstance(raw_trials, int | float):
        return False
    return math.isfinite(float(raw_trials)) and float(raw_trials) == 1.0


def _explicit_dependencies(
    dependencies: Mapping[str, Iterable[str | Path]] | None,
    *,
    admitted: set[str],
    path_identity_scope: CanonicalPathIdentityScope,
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for raw_owner, raw_dependencies in (dependencies or {}).items():
        owner = path_identity_scope.identity(raw_owner)
        dependency_paths = tuple(
            dict.fromkeys(
                path_identity_scope.identity(path) for path in raw_dependencies
            )
        )
        missing = [path for path in (owner, *dependency_paths) if path not in admitted]
        if missing:
            raise _resource_error(
                code="interpretation_resource_not_admitted",
                message=(
                    "Data Interpretation parser dependencies were not all admitted "
                    "by resource preflight."
                ),
                path=Path(missing[0]),
                parse_started=False,
                details={
                    "owner_path": owner,
                    "missing_paths": missing,
                },
            )
        if dependency_paths:
            result[owner] = dependency_paths
    return result


def _merge_dependencies(
    *dependency_maps: Mapping[str, Iterable[str]],
) -> dict[str, tuple[str, ...]]:
    merged: dict[str, list[str]] = {}
    for dependency_map in dependency_maps:
        for owner, dependencies in dependency_map.items():
            owner_dependencies = merged.setdefault(owner, [])
            for dependency in dependencies:
                if dependency not in owner_dependencies:
                    owner_dependencies.append(dependency)
    return {owner: tuple(dependencies) for owner, dependencies in merged.items()}


def _current_identity(path: Path) -> AdmittedFileIdentity:
    try:
        entry_stat = path.lstat()
    except OSError as exc:
        raise _resource_error(
            code="interpretation_resource_unavailable",
            message=f"A selected Data Interpretation file is unavailable: {path}.",
            path=path,
            parse_started=False,
            details={"os_error": str(exc)},
        ) from exc
    file_attributes = int(getattr(entry_stat, "st_file_attributes", 0) or 0)
    if stat.S_ISLNK(entry_stat.st_mode) or (
        file_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    ):
        raise _resource_error(
            code="interpretation_resource_unavailable",
            message=(
                "A selected Data Interpretation file was replaced by a symbolic "
                f"link or reparse point: {path}."
            ),
            path=path,
            parse_started=False,
        )
    if not stat.S_ISREG(entry_stat.st_mode):
        raise _resource_error(
            code="interpretation_resource_unavailable",
            message=f"A selected Data Interpretation path is not a file: {path}.",
            path=path,
            parse_started=False,
        )

    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            file_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise _resource_error(
                    code="interpretation_resource_unavailable",
                    message=(
                        f"A selected Data Interpretation path is not a file: {path}."
                    ),
                    path=path,
                    parse_started=False,
                )
            if _filesystem_identity(entry_stat) != _filesystem_identity(file_stat):
                raise _identity_changed_while_verifying_error(path)
            content_probe_sha256 = _content_probe_sha256(
                handle,
                max(int(file_stat.st_size), 0),
            )
            finished_stat = os.fstat(handle.fileno())
        final_entry_stat = path.lstat()
    except PreconditionError:
        raise
    except OSError as exc:
        raise _resource_error(
            code="interpretation_resource_unavailable",
            message=f"A selected Data Interpretation file is unavailable: {path}.",
            path=path,
            parse_started=False,
            details={"os_error": str(exc)},
        ) from exc
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
    if not (
        _filesystem_identity(entry_stat)
        == _filesystem_identity(file_stat)
        == _filesystem_identity(finished_stat)
        == _filesystem_identity(final_entry_stat)
    ):
        raise _identity_changed_while_verifying_error(path)
    try:
        identity = AdmittedFileIdentity(
            file_bytes=max(int(file_stat.st_size), 0),
            device=int(file_stat.st_dev),
            inode=int(file_stat.st_ino),
            mtime_ns=int(file_stat.st_mtime_ns),
            ctime_ns=int(file_stat.st_ctime_ns),
            content_probe_sha256=content_probe_sha256,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise _resource_error(
            code="interpretation_resource_identity_unavailable",
            message=(
                "A selected Data Interpretation file could not be identified "
                f"safely: {path}."
            ),
            path=path,
            parse_started=False,
        ) from exc
    if identity.device < 0 or identity.inode <= 0:
        raise _resource_error(
            code="interpretation_resource_identity_unavailable",
            message=(
                "A selected Data Interpretation file could not be identified "
                f"safely: {path}."
            ),
            path=path,
            parse_started=False,
        )
    return identity


def _filesystem_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_size),
        int(value.st_mtime_ns),
        int(value.st_ctime_ns),
    )


def _identity_changed_while_verifying_error(path: Path) -> PreconditionError:
    return _resource_error(
        code="interpretation_resource_unavailable",
        message=(
            "A selected Data Interpretation file changed while its identity "
            f"was being verified: {path}."
        ),
        path=path,
        parse_started=False,
    )


def _content_probe_sha256(handle: Any, file_bytes: int) -> str:
    """Hash a bounded content probe without materializing the whole EEG file."""
    digest = hashlib.sha256()
    digest.update(str(file_bytes).encode("ascii"))
    if file_bytes <= RESOURCE_IDENTITY_PROBE_BYTES * 2:
        digest.update(handle.read())
        return digest.hexdigest()
    digest.update(handle.read(RESOURCE_IDENTITY_PROBE_BYTES))
    handle.seek(file_bytes - RESOURCE_IDENTITY_PROBE_BYTES)
    digest.update(handle.read(RESOURCE_IDENTITY_PROBE_BYTES))
    return digest.hexdigest()


def _changed_error(
    path: Path,
    *,
    admitted_bytes: int,
    observed: AdmittedFileIdentity,
    parse_started: bool,
    purpose: str,
    admitted: AdmittedFileIdentity | None = None,
) -> PreconditionError:
    details: dict[str, Any] = {
        "admitted_bytes": admitted_bytes,
        "observed_bytes": observed.file_bytes,
        "observed_identity": observed.to_diagnostics(),
        "purpose": purpose,
    }
    if admitted is not None:
        details["admitted_identity"] = admitted.to_diagnostics()
        details["changed_fields"] = [
            field_name
            for field_name, admitted_value in admitted.to_diagnostics().items()
            if observed.to_diagnostics()[field_name] != admitted_value
        ]
    return _resource_error(
        code="interpretation_resource_changed_after_admission",
        message=(
            "A selected Data Interpretation file changed after resource admission: "
            f"{path}."
        ),
        path=path,
        parse_started=parse_started,
        details=details,
    )


def _resource_error(
    *,
    code: str,
    message: str,
    path: Path,
    parse_started: bool,
    details: dict[str, Any] | None = None,
) -> PreconditionError:
    diagnostics = {
        "code": code,
        "path": str(path),
        "parse_started": parse_started,
        **dict(details or {}),
    }
    return PreconditionError(message, diagnostics=diagnostics)


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve()))


def _lexical_path_key(path: Path) -> str:
    """Normalize path text without querying filesystem metadata."""
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))


def _canonical_aliases(
    requested_paths: Iterable[Path],
    canonical_paths: Iterable[str],
) -> dict[str, str]:
    """Cache only paths already canonical; symlink aliases remain re-resolved."""
    aliases: dict[str, str] = {}
    for requested_path, canonical_path in zip(
        requested_paths,
        canonical_paths,
        strict=True,
    ):
        lexical_path = _lexical_path_key(requested_path)
        if lexical_path == canonical_path:
            aliases[lexical_path] = canonical_path
    return aliases
