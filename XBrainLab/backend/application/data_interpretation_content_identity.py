"""Content identity binding for reviewed Data Interpretation parser inputs."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Iterable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from pathlib import Path
from threading import Lock
from typing import Any

from .data_interpretation_path_identity import (
    CanonicalPathIdentityScope,
    deduplicate_resolved_paths,
    resolved_path_identity,
    resolved_path_value,
)
from .data_interpretation_resource_reader import AdmittedResourceReader
from .errors import PreconditionError
from .owned_work import (
    CapturedOwnedWork,
    bind_captured_owned_work,
    capture_owned_work,
    owned_work_checkpoint,
)

CONTENT_IDENTITY_VERSION = 3
CONTENT_IDENTITY_ALGORITHM = "sha256"
CONTENT_HASH_CHUNK_BYTES = 1_048_576
CONTENT_IDENTITY_HASH_WORKERS = 4
CONTENT_IDENTITY_HASH_STAGE = "Hashing reviewed import content"
CONTENT_IDENTITY_VERIFY_STAGE = "Verifying reviewed import content"
CONTENT_IDENTITY_FINALIZE_STAGE = "Finalizing reviewed import content"
CONTENT_IDENTITY_SCOPE = (
    "selected_eeg_parser_dependencies_label_carriers_and_local_bids_sidecars"
)


class _ContentHashProgress:
    """Serialize aggregate byte progress shared by independent hash workers."""

    def __init__(
        self,
        *,
        expected_sizes: Mapping[str, int],
        total_bytes: int | None,
    ) -> None:
        self._expected_sizes = dict(expected_sizes)
        self._total_bytes = total_bytes
        self._completed_bytes = 0
        self._lock = Lock()

    def start(self) -> None:
        with self._lock:
            self._checkpoint_locked()

    def begin_file(self, path: Path, *, file_bytes: int) -> None:
        with self._lock:
            expected = self._expected_sizes.get(str(path))
            if expected is None or expected != file_bytes:
                self._total_bytes = None
            self._checkpoint_locked()

    def advance(self, chunk_bytes: int) -> None:
        with self._lock:
            self._completed_bytes += max(int(chunk_bytes), 0)
            if (
                self._total_bytes is not None
                and self._completed_bytes > self._total_bytes
            ):
                self._total_bytes = None
            if self._completed_bytes == self._total_bytes:
                owned_work_checkpoint(CONTENT_IDENTITY_VERIFY_STAGE)
                return
            self._checkpoint_locked()

    def finalizing(self) -> None:
        with self._lock:
            owned_work_checkpoint(CONTENT_IDENTITY_FINALIZE_STAGE)

    def _checkpoint_locked(self) -> None:
        if self._total_bytes is None or self._total_bytes <= 0:
            owned_work_checkpoint(CONTENT_IDENTITY_HASH_STAGE)
            return
        owned_work_checkpoint(
            CONTENT_IDENTITY_HASH_STAGE,
            completed=self._completed_bytes,
            total=self._total_bytes,
        )


_CURRENT_CONTENT_HASH_PROGRESS: ContextVar[_ContentHashProgress | None] = ContextVar(
    "xbrainlab_content_hash_progress",
    default=None,
)

_PLAN_BINDING_FIELDS = (
    "format",
    "selected_target_file",
    "selected_label_field",
    "selected_anchor",
    "selected_duration_field",
    "time_model",
    "placement_method",
    "granularity",
    "role",
)


def build_review_content_identity(
    *,
    label_carrier_plan: Iterable[Mapping[str, Any]],
    selected_eeg_files: Iterable[str] = (),
    eeg_parser_dependencies: Mapping[str, Iterable[str]] | None = None,
    bids_events_json_files: Iterable[str] = (),
    bids_channels_files: Iterable[str] = (),
    admitted_file_identities: Mapping[str, Mapping[str, Any]] | None = None,
    class_map: Mapping[str, Any] | None = None,
    event_roles: Mapping[str, Any] | None = None,
    run_event_mappings: Mapping[str, Mapping[str, Any]] | None = None,
    resource_reader: AdmittedResourceReader | None = None,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> dict[str, Any]:
    """Bind every reviewed parser input and the choices interpreting those bytes."""
    if resource_reader is not None:
        path_identity_scope = resource_reader.path_identity_scope
    bindings = _normalized_bindings(
        label_carrier_plan,
        path_identity_scope=path_identity_scope,
    )
    selected_paths = _normalized_paths(
        selected_eeg_files,
        path_identity_scope=path_identity_scope,
    )
    parser_dependencies = _normalized_parser_dependencies(
        eeg_parser_dependencies,
        path_identity_scope=path_identity_scope,
    )
    roles_by_identity = {
        _path_key(path, path_identity_scope=path_identity_scope): (
            path,
            "selected_eeg",
        )
        for path in selected_paths
    }
    for dependency_binding in parser_dependencies:
        for path in dependency_binding["dependencies"]:
            roles_by_identity.setdefault(
                _path_key(path, path_identity_scope=path_identity_scope),
                (path, "eeg_parser_dependency"),
            )
    for binding in bindings:
        path = binding["path"]
        roles_by_identity.setdefault(
            _path_key(path, path_identity_scope=path_identity_scope),
            (path, "label_carrier"),
        )
    for raw_path in bids_events_json_files:
        path = _path_value(raw_path, path_identity_scope=path_identity_scope)
        roles_by_identity.setdefault(
            _path_key(path, path_identity_scope=path_identity_scope),
            (path, "bids_events_json"),
        )
    for raw_path in bids_channels_files:
        path = _path_value(raw_path, path_identity_scope=path_identity_scope)
        roles_by_identity.setdefault(
            _path_key(path, path_identity_scope=path_identity_scope),
            (path, "bids_channels"),
        )
    admitted_identities = _normalized_admitted_file_identities(
        admitted_file_identities,
        path_identity_scope=path_identity_scope,
    )

    identity_requests: list[tuple[Path, str, Mapping[str, Any] | None]] = []
    for path_identity in sorted(roles_by_identity):
        path, role = roles_by_identity[path_identity]
        identity_requests.append(
            (Path(path), role, admitted_identities.get(path_identity))
        )
    files = _content_file_identities(
        identity_requests,
        resource_reader=resource_reader,
        path_identity_scope=path_identity_scope,
    )
    interpretation_contract = {
        "selected_eeg_files": selected_paths,
        "parser_dependencies": parser_dependencies,
        "bindings": bindings,
        "class_map": _normalized_string_mapping(class_map),
        "event_roles": _normalized_string_mapping(event_roles),
        "run_event_mappings": _normalized_nested_mapping(run_event_mappings),
    }
    identity_files = _files_identity_payload(
        files,
        path_identity_scope=path_identity_scope,
    )
    identity_contract = _contract_identity_payload(
        interpretation_contract,
        path_identity_scope=path_identity_scope,
    )
    content_sha256 = _canonical_sha256(identity_files)
    review_contract_sha256 = _canonical_sha256(identity_contract)
    scope_sha256 = _canonical_sha256(
        {
            "version": CONTENT_IDENTITY_VERSION,
            "files": identity_files,
            "interpretation_contract": identity_contract,
        }
    )
    return {
        "version": CONTENT_IDENTITY_VERSION,
        "algorithm": CONTENT_IDENTITY_ALGORITHM,
        "scope": CONTENT_IDENTITY_SCOPE,
        "scope_sha256": scope_sha256,
        "content_sha256": content_sha256,
        "review_contract_sha256": review_contract_sha256,
        "files": files,
        "selected_eeg_files": selected_paths,
        "parser_dependencies": parser_dependencies,
        "bindings": bindings,
    }


def assert_review_content_unchanged(
    *,
    expected: Mapping[str, Any] | None,
    label_carrier_plan: Iterable[Mapping[str, Any]],
    selected_eeg_files: Iterable[str] | None = None,
    class_map: Mapping[str, Any] | None = None,
    event_roles: Mapping[str, Any] | None = None,
    run_event_mappings: Mapping[str, Mapping[str, Any]] | None = None,
    resource_reader: AdmittedResourceReader | None = None,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    """Rebuild one reviewed identity and fail closed when it no longer matches."""
    expected_identity = dict(expected or {})
    raw_expected_files = expected_identity.get("files")
    admitted_paths = (
        [
            str(row.get("path") or "").strip()
            for row in raw_expected_files
            if isinstance(row, Mapping) and str(row.get("path") or "").strip()
        ]
        if isinstance(raw_expected_files, list)
        else []
    )
    path_identity_scope = CanonicalPathIdentityScope.from_admitted_paths(
        admitted_paths,
    )
    expected_files = _identity_files(
        expected_identity,
        path_identity_scope=path_identity_scope,
    )
    bindings = _normalized_bindings(
        label_carrier_plan,
        path_identity_scope=path_identity_scope,
    )
    selected_paths = (
        _normalized_paths(
            selected_eeg_files,
            path_identity_scope=path_identity_scope,
        )
        if selected_eeg_files is not None
        else _identity_selected_eeg_files(
            expected_identity,
            path_identity_scope=path_identity_scope,
        )
    )
    if not expected_identity:
        if bindings or selected_paths:
            raise _content_changed_error(
                expected=expected_identity,
                observed={},
                changed_paths=sorted(
                    {
                        *selected_paths,
                        *(binding["path"] for binding in bindings),
                    }
                ),
                reason="reviewed_content_identity_missing",
                candidate_id=candidate_id,
            )
        return {}

    size_changed_paths = _size_changed_paths(expected_files)
    if size_changed_paths:
        raise _content_changed_error(
            expected=expected_identity,
            observed={},
            changed_paths=size_changed_paths,
            reason="reviewed_content_size_changed",
            candidate_id=candidate_id,
        )

    selected_eeg_files = selected_paths
    parser_dependencies = _identity_parser_dependencies(
        expected_identity,
        path_identity_scope=path_identity_scope,
    )

    sidecar_paths = [
        row["path"] for row in expected_files if row.get("role") == "bids_events_json"
    ]
    channels_paths = [
        row["path"] for row in expected_files if row.get("role") == "bids_channels"
    ]
    try:
        observed = build_review_content_identity(
            label_carrier_plan=bindings,
            selected_eeg_files=selected_eeg_files,
            eeg_parser_dependencies=parser_dependencies,
            bids_events_json_files=sidecar_paths,
            bids_channels_files=channels_paths,
            class_map=class_map,
            event_roles=event_roles,
            run_event_mappings=run_event_mappings,
            resource_reader=resource_reader,
            path_identity_scope=path_identity_scope,
        )
    except PreconditionError as exc:
        changed_path = str(exc.diagnostics.get("path") or "").strip()
        raise _content_changed_error(
            expected=expected_identity,
            observed={},
            changed_paths=[changed_path] if changed_path else [],
            reason="reviewed_content_unavailable",
            cause=exc,
            candidate_id=candidate_id,
        ) from exc

    if (
        expected_identity.get("version") != CONTENT_IDENTITY_VERSION
        or expected_identity.get("algorithm") != CONTENT_IDENTITY_ALGORITHM
        or expected_identity.get("scope_sha256") != observed["scope_sha256"]
    ):
        raise _content_changed_error(
            expected=expected_identity,
            observed=observed,
            changed_paths=_changed_paths(expected_files, observed["files"]),
            reason="reviewed_content_or_contract_changed",
            candidate_id=candidate_id,
        )
    return observed


def identity_paths(identity: Mapping[str, Any] | None) -> list[str]:
    """Return the exact reviewed file scope stored in a content identity."""
    return [row["path"] for row in _identity_files(identity)]


def _content_file_identity(
    *,
    path: Path,
    role: str,
    resource_reader: AdmittedResourceReader | None,
    admitted_identity: Mapping[str, Any] | None = None,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> dict[str, Any]:
    path_identity = (
        resource_reader.canonical_key(path)
        if resource_reader is not None and resource_reader.admits(path)
        else _path_key(path, path_identity_scope=path_identity_scope)
    )
    path_value = _path_value(
        path,
        path_identity_scope=(
            resource_reader.path_identity_scope
            if resource_reader is not None
            else path_identity_scope
        ),
    )
    if admitted_identity is not None:
        return {
            "path": path_value,
            "role": role,
            "file_bytes": int(admitted_identity["file_bytes"]),
            "sha256": str(admitted_identity["sha256"]),
        }
    # BIDS events JSON sidecars have their own bounded admission reader.  The
    # general reader intentionally excludes them, so only use its guard for
    # files that belong to its exact admitted scope.
    guard = (
        resource_reader.guard([path], purpose="reviewed label content fingerprint")
        if resource_reader is not None
        and path_identity in resource_reader.admitted_files
        else nullcontext()
    )
    try:
        with guard:
            file_bytes, sha256 = _stable_stream_sha256(path)
    except PreconditionError:
        raise
    except OSError as exc:
        raise PreconditionError(
            f"A reviewed Data Interpretation file could not be fingerprinted: {path}.",
            diagnostics={
                "code": "interpretation_content_identity_unavailable",
                "path": str(path),
                "os_error": str(exc),
            },
        ) from exc
    return {
        "path": path_value,
        "role": role,
        "file_bytes": file_bytes,
        "sha256": sha256,
    }


def _content_file_identities(
    requests: list[tuple[Path, str, Mapping[str, Any] | None]],
    *,
    resource_reader: AdmittedResourceReader | None,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> list[dict[str, Any]]:
    """Fingerprint independent admitted files with bounded parallel I/O."""

    captured_work = capture_owned_work()
    progress = _content_hash_progress(requests, captured_work=captured_work)
    if progress is not None:
        progress.start()

    def _build(
        request: tuple[Path, str, Mapping[str, Any] | None],
    ) -> dict[str, Any]:
        path, role, admitted_identity = request
        return _content_file_identity(
            path=path,
            role=role,
            resource_reader=resource_reader,
            admitted_identity=admitted_identity,
            path_identity_scope=path_identity_scope,
        )

    def _build_with_context(
        request: tuple[Path, str, Mapping[str, Any] | None],
    ) -> dict[str, Any]:
        with (
            bind_captured_owned_work(captured_work),
            _bind_content_hash_progress(progress),
        ):
            return _build(request)

    worker_count = min(CONTENT_IDENTITY_HASH_WORKERS, len(requests))
    if worker_count <= 1:
        identities = [_build_with_context(request) for request in requests]
    else:
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="interpretation-content-identity",
        ) as executor:
            identities = list(executor.map(_build_with_context, requests))
    if progress is not None:
        progress.finalizing()
    return identities


def _content_hash_progress(
    requests: Iterable[tuple[Path, str, Mapping[str, Any] | None]],
    *,
    captured_work: CapturedOwnedWork | None,
) -> _ContentHashProgress | None:
    """Build progress only when these hashes belong to an admitted operation."""
    if captured_work is None:
        return None
    expected_sizes: dict[str, int] = {}
    total_bytes = 0
    total_known = True
    for path, _role, admitted_identity in requests:
        if admitted_identity is not None:
            continue
        try:
            observed = path.stat()
        except OSError:
            total_known = False
            continue
        if not stat.S_ISREG(observed.st_mode):
            total_known = False
            continue
        file_bytes = max(int(observed.st_size), 0)
        expected_sizes[str(path)] = file_bytes
        total_bytes += file_bytes
    if not expected_sizes and total_known:
        return None
    return _ContentHashProgress(
        expected_sizes=expected_sizes,
        total_bytes=total_bytes if total_known and total_bytes > 0 else None,
    )


@contextmanager
def _bind_content_hash_progress(
    progress: _ContentHashProgress | None,
) -> Iterator[None]:
    if progress is None:
        yield
        return
    token = _CURRENT_CONTENT_HASH_PROGRESS.set(progress)
    try:
        yield
    finally:
        _CURRENT_CONTENT_HASH_PROGRESS.reset(token)


def _normalized_admitted_file_identities(
    identities: Mapping[str, Mapping[str, Any]] | None,
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> dict[str, dict[str, int | str]]:
    result: dict[str, dict[str, int | str]] = {}
    for raw_path, identity in (identities or {}).items():
        path = _path_value(raw_path, path_identity_scope=path_identity_scope)
        path_identity = _path_key(
            path,
            path_identity_scope=path_identity_scope,
        )
        file_bytes = identity.get("file_bytes")
        sha256 = str(identity.get("sha256") or "").strip().lower()
        if (
            not isinstance(file_bytes, int)
            or isinstance(file_bytes, bool)
            or file_bytes < 0
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
        ):
            raise PreconditionError(
                f"An admitted content identity is invalid: {path}.",
                diagnostics={
                    "code": "interpretation_content_identity_invalid",
                    "path": path,
                },
            )
        result[path_identity] = {"file_bytes": file_bytes, "sha256": sha256}
    return result


def _stable_stream_sha256(path: Path) -> tuple[int, str]:
    """Hash the opened regular file and report the bytes actually consumed."""
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise PreconditionError(
                f"A reviewed Data Interpretation path is not a regular file: {path}.",
                diagnostics={
                    "code": "interpretation_content_identity_unavailable",
                    "path": str(path),
                },
            )
        progress = _CURRENT_CONTENT_HASH_PROGRESS.get()
        if progress is not None:
            progress.begin_file(path, file_bytes=max(int(opened.st_size), 0))
        while chunk := handle.read(CONTENT_HASH_CHUNK_BYTES):
            total += len(chunk)
            digest.update(chunk)
            if progress is not None:
                progress.advance(len(chunk))
    return total, digest.hexdigest()


def _normalized_bindings(
    plans: Iterable[Mapping[str, Any]],
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for plan in plans:
        raw_path = str(plan.get("path") or "").strip()
        if not raw_path:
            continue
        binding: dict[str, Any] = {
            "path": _path_value(
                raw_path,
                path_identity_scope=path_identity_scope,
            )
        }
        for field in _PLAN_BINDING_FIELDS:
            value = str(plan.get(field) or "").strip()
            if not value:
                continue
            if field == "selected_target_file":
                value = _path_value(
                    value,
                    path_identity_scope=path_identity_scope,
                )
            binding[field] = value
        target_files = _normalized_paths(
            (
                str(item)
                for item in plan.get("selected_target_files", []) or []
                if str(item).strip()
            ),
            path_identity_scope=path_identity_scope,
        )
        if target_files:
            binding["selected_target_files"] = target_files
        target_codes = sorted(
            {
                str(item).strip()
                for item in plan.get("selected_target_event_codes", []) or []
                if str(item).strip()
            }
        )
        if target_codes:
            binding["selected_target_event_codes"] = target_codes
        run_class_map = _normalized_string_mapping(plan.get("run_class_map"))
        if run_class_map:
            binding["run_class_map"] = run_class_map
        value_decisions = _normalized_value_decisions(plan.get("value_decisions"))
        if value_decisions:
            binding["value_decisions"] = value_decisions
        result.append(binding)
    return sorted(result, key=lambda item: item["path"])


def _normalized_paths(
    paths: Iterable[str],
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> list[str]:
    if path_identity_scope is not None:
        deduplicated = list(
            dict.fromkeys(
                path_identity_scope.value(path)
                for raw_path in paths
                if (path := str(raw_path).strip())
            )
        )
    else:
        deduplicated = deduplicate_resolved_paths(
            path for raw_path in paths if (path := str(raw_path).strip())
        )
    return sorted(
        deduplicated,
        key=lambda path: (
            _path_key(path, path_identity_scope=path_identity_scope),
            path,
        ),
    )


def _normalized_parser_dependencies(
    dependencies: Mapping[str, Iterable[str]] | None,
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw_owner, raw_dependencies in (dependencies or {}).items():
        owner = str(raw_owner).strip()
        if not owner:
            continue
        dependency_paths = _normalized_paths(
            raw_dependencies,
            path_identity_scope=path_identity_scope,
        )
        if not dependency_paths:
            continue
        result.append(
            {
                "path": _path_value(
                    owner,
                    path_identity_scope=path_identity_scope,
                ),
                "dependencies": dependency_paths,
            }
        )
    return sorted(result, key=lambda item: item["path"])


def _identity_selected_eeg_files(
    identity: Mapping[str, Any],
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> list[str]:
    rows = identity.get("selected_eeg_files")
    if isinstance(rows, list):
        selected = _normalized_paths(
            (str(item) for item in rows),
            path_identity_scope=path_identity_scope,
        )
        if selected:
            return selected
    return [
        row["path"]
        for row in _identity_files(
            identity,
            path_identity_scope=path_identity_scope,
        )
        if row.get("role") == "selected_eeg"
    ]


def _identity_parser_dependencies(
    identity: Mapping[str, Any],
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> dict[str, list[str]]:
    rows = identity.get("parser_dependencies")
    if not isinstance(rows, list):
        return {}
    result: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        owner = str(row.get("path") or "").strip()
        raw_dependencies = row.get("dependencies")
        if not owner or not isinstance(raw_dependencies, list):
            continue
        normalized = _normalized_paths(
            (str(item) for item in raw_dependencies),
            path_identity_scope=path_identity_scope,
        )
        if normalized:
            result[_path_value(owner, path_identity_scope=path_identity_scope)] = (
                normalized
            )
    return result


def _identity_files(
    identity: Mapping[str, Any] | None,
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(identity, Mapping):
        return []
    rows = identity.get("files")
    if not isinstance(rows, list):
        return []
    result: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        path = str(row.get("path") or "").strip()
        if not path:
            continue
        path_value = _path_value(
            path,
            path_identity_scope=path_identity_scope,
        )
        path_identity = _path_key(
            path_value,
            path_identity_scope=path_identity_scope,
        )
        if path_identity in seen:
            continue
        seen.add(path_identity)
        normalized = {
            "path": path_value,
            "role": str(row.get("role") or "label_carrier"),
            "file_bytes": row.get("file_bytes"),
            "sha256": str(row.get("sha256") or ""),
        }
        result.append((path_identity, normalized))
    return [
        row
        for _identity, row in sorted(
            result,
            key=lambda item: (item[0], item[1]["path"]),
        )
    ]


def _changed_paths(
    expected_files: Iterable[Mapping[str, Any]],
    observed_files: Iterable[Mapping[str, Any]],
) -> list[str]:
    expected_rows = list(expected_files)
    observed_rows = list(observed_files)
    expected = {
        _path_key(str(row.get("path") or "")): _file_identity_payload(row)
        for row in expected_rows
        if str(row.get("path") or "").strip()
    }
    observed = {
        _path_key(str(row.get("path") or "")): _file_identity_payload(row)
        for row in observed_rows
        if str(row.get("path") or "").strip()
    }
    display_paths = {
        _path_key(str(row.get("path") or "")): _path_value(str(row.get("path") or ""))
        for row in [*expected_rows, *observed_rows]
        if str(row.get("path") or "").strip()
    }
    return sorted(
        display_paths[identity]
        for identity in set(expected) | set(observed)
        if expected.get(identity) != observed.get(identity)
    )


def _size_changed_paths(expected_files: Iterable[Mapping[str, Any]]) -> list[str]:
    changed: list[str] = []
    for row in expected_files:
        path = Path(str(row.get("path") or ""))
        expected_bytes = row.get("file_bytes")
        try:
            observed = path.stat()
        except OSError:
            changed.append(_path_value(path))
            continue
        if (
            not isinstance(expected_bytes, int)
            or isinstance(expected_bytes, bool)
            or not stat.S_ISREG(observed.st_mode)
            or max(int(observed.st_size), 0) != expected_bytes
        ):
            changed.append(_path_value(path))
    return sorted(set(changed))


def _content_changed_error(
    *,
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
    changed_paths: list[str],
    reason: str,
    cause: PreconditionError | None = None,
    candidate_id: str | None = None,
) -> PreconditionError:
    diagnostics: dict[str, Any] = {
        "code": "interpretation_content_changed_after_review",
        "reason": reason,
        "changed_paths": sorted({path for path in changed_paths if path}),
        "expected_scope_sha256": str(expected.get("scope_sha256") or ""),
        "observed_scope_sha256": str(observed.get("scope_sha256") or ""),
        "next_action": "preview_and_review_again",
    }
    if candidate_id:
        diagnostics["candidate_id"] = candidate_id
    if cause is not None:
        diagnostics["cause"] = dict(cause.diagnostics)
    return PreconditionError(
        "Reviewed Data Interpretation content changed after preview. Preview and "
        "review the Data Interpretation again before applying it.",
        diagnostics=diagnostics,
    )


def _normalized_string_mapping(payload: Any) -> dict[str, str]:
    if not isinstance(payload, Mapping):
        return {}
    return {
        str(key): str(value).strip()
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
        if str(value).strip()
    }


def _normalized_nested_mapping(payload: Any) -> dict[str, dict[str, str]]:
    if not isinstance(payload, Mapping):
        return {}
    return {
        str(key): normalized
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
        if (normalized := _normalized_string_mapping(value))
    }


def _normalized_value_decisions(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return {}
    fields = (
        "role",
        "keep_event",
        "use_as_class",
        "class_name",
        "suggested_name",
        "decision",
        "decision_source",
        "provenance",
        "count",
    )
    result: dict[str, dict[str, Any]] = {}
    for raw_value, raw_decision in sorted(
        payload.items(), key=lambda item: str(item[0])
    ):
        if not isinstance(raw_decision, Mapping):
            continue
        decision = {
            field: raw_decision[field] for field in fields if field in raw_decision
        }
        if decision:
            result[str(raw_value)] = decision
    return result


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_identity_payload(
    row: Mapping[str, Any],
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> dict[str, Any]:
    payload = dict(row)
    payload["path"] = _path_key(
        str(row.get("path") or ""),
        path_identity_scope=path_identity_scope,
    )
    return payload


def _files_identity_payload(
    files: Iterable[Mapping[str, Any]],
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> list[dict[str, Any]]:
    return sorted(
        (
            _file_identity_payload(
                row,
                path_identity_scope=path_identity_scope,
            )
            for row in files
        ),
        key=lambda row: str(row["path"]),
    )


def _contract_identity_payload(
    contract: Mapping[str, Any],
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> dict[str, Any]:
    bindings: list[dict[str, Any]] = []
    for raw_binding in contract.get("bindings", []) or []:
        binding = dict(raw_binding)
        binding["path"] = _path_key(
            str(binding.get("path") or ""),
            path_identity_scope=path_identity_scope,
        )
        if binding.get("selected_target_file"):
            binding["selected_target_file"] = _path_key(
                str(binding["selected_target_file"]),
                path_identity_scope=path_identity_scope,
            )
        if binding.get("selected_target_files"):
            binding["selected_target_files"] = sorted(
                _path_key(
                    str(path),
                    path_identity_scope=path_identity_scope,
                )
                for path in binding["selected_target_files"]
            )
        bindings.append(binding)
    parser_dependencies = [
        {
            **dict(row),
            "path": _path_key(
                str(row.get("path") or ""),
                path_identity_scope=path_identity_scope,
            ),
            "dependencies": sorted(
                _path_key(
                    str(path),
                    path_identity_scope=path_identity_scope,
                )
                for path in row.get("dependencies", [])
            ),
        }
        for row in contract.get("parser_dependencies", []) or []
    ]
    return {
        **dict(contract),
        "selected_eeg_files": sorted(
            _path_key(str(path), path_identity_scope=path_identity_scope)
            for path in contract.get("selected_eeg_files", []) or []
        ),
        "parser_dependencies": sorted(
            parser_dependencies,
            key=lambda row: str(row["path"]),
        ),
        "bindings": sorted(bindings, key=lambda row: str(row["path"])),
    }


def _path_key(
    path: str | Path,
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> str:
    if path_identity_scope is not None:
        return path_identity_scope.identity(path)
    return resolved_path_identity(path)


def _path_value(
    path: str | Path,
    *,
    path_identity_scope: CanonicalPathIdentityScope | None = None,
) -> str:
    if path_identity_scope is not None:
        return path_identity_scope.value(path)
    return resolved_path_value(path)
