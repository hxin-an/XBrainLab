"""Isolated local-assistant configuration for real UI capture scripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from PIL import Image

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity as collect_guided_source_identity,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.config_paths import CONFIG_DIR_ENV
from XBrainLab.llm.core.model_catalog import (
    PRIMARY_LOCAL_MODEL_ID,
    local_model_spec,
    model_cache_complete,
    model_snapshot_path,
)

ROOT = Path(__file__).resolve().parents[2]
_HEX_GIT = re.compile(r"^[0-9a-f]{40,64}$")
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY_FIELD = "identity_sha256"
_MODEL_LOADER_POLICY = "pinned-local-files-only"


def prepare_capture_config(model_id: str, config_dir: Path) -> LLMConfig:
    """Persist one capture-only runtime selection outside user settings."""
    isolated_dir = config_dir.expanduser().resolve()
    os.environ[CONFIG_DIR_ENV] = str(isolated_dir)
    config = LLMConfig()
    config.apply_runtime_selection(
        "local",
        model_id=model_id,
        ui_active_mode="local",
    )
    config.local_runtime_notice_acknowledged = True
    if not config.save_to_file():
        raise RuntimeError(
            f"Could not persist isolated assistant config under {isolated_dir}."
        )
    return config


def restore_capture_config_env(previous_config_dir: str | None) -> None:
    """Restore the caller's config boundary without touching either file."""
    if previous_config_dir is None:
        os.environ.pop(CONFIG_DIR_ENV, None)
    else:
        os.environ[CONFIG_DIR_ENV] = previous_config_dir


@contextmanager
def isolated_assistant_runtime_config(
    model_id: str,
    *,
    parent_dir: Path,
) -> Iterator[LLMConfig]:
    """Yield an acknowledged local runtime config on the capture filesystem."""
    root = parent_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    previous_config_dir = os.environ.get(CONFIG_DIR_ENV)
    try:
        with tempfile.TemporaryDirectory(
            prefix=".assistant-runtime-",
            dir=root,
        ) as config_dir:
            yield prepare_capture_config(model_id, Path(config_dir))
    finally:
        restore_capture_config_env(previous_config_dir)


def seal_evidence_identity(
    kind: str,
    value: Mapping[str, object],
) -> dict[str, object]:
    """Bind a redacted evidence mapping to one deterministic SHA-256 digest."""
    payload = {str(key): item for key, item in value.items() if key != _IDENTITY_FIELD}
    encoded = json.dumps(
        {"kind": kind, "value": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    payload[_IDENTITY_FIELD] = hashlib.sha256(encoded).hexdigest()
    return payload


def collect_capture_source_identity(
    repo_root: Path = ROOT,
    *,
    refresh: bool = True,
) -> dict[str, object]:
    """Collect exact source identity without publishing the private checkout path."""
    raw = collect_guided_source_identity(repo_root, refresh=refresh)
    if raw.get("error"):
        return seal_evidence_identity(
            "source",
            {"error": str(raw.get("error") or "source identity unavailable")},
        )
    return seal_evidence_identity(
        "source",
        {
            "branch": str(raw.get("branch") or ""),
            "commit_sha": str(raw.get("commit_sha") or ""),
            "head_tree_sha": str(raw.get("head_tree_sha") or ""),
            "dirty": bool(raw.get("dirty")),
            "dirty_fingerprint": str(raw.get("dirty_digest") or ""),
            "source_content_sha256": str(raw.get("source_content_digest") or ""),
        },
    )


def collect_model_identity(
    *,
    requested_model_id: str,
    loaded_model_id: str,
    cache_dir: str,
) -> dict[str, object]:
    """Record the exact pinned model and a path-free cache snapshot manifest."""
    spec = local_model_spec(loaded_model_id)
    snapshot = model_snapshot_path(cache_dir, loaded_model_id)
    manifest_sha256, file_count, total_bytes = _snapshot_manifest_identity(
        snapshot,
        cache_root=Path(cache_dir),
    )
    return seal_evidence_identity(
        "model",
        {
            "requested_model_id": requested_model_id,
            "loaded_model_id": loaded_model_id,
            "loaded_revision": spec.revision if spec is not None else "",
            "snapshot_manifest_sha256": manifest_sha256,
            "snapshot_file_count": file_count,
            "snapshot_total_bytes": total_bytes,
            "cache_complete": bool(
                loaded_model_id and model_cache_complete(cache_dir, loaded_model_id)
            ),
            "loader_policy": _MODEL_LOADER_POLICY,
        },
    )


def collect_screenshot_evidence(
    screenshot_paths: Mapping[str, object],
    *,
    artifact_root: Path,
) -> dict[str, object]:
    """Hash screenshots while retaining only paths relative to the artifact root."""
    root = artifact_root.expanduser().resolve()
    artifacts: dict[str, dict[str, object]] = {}
    for name, raw_path in sorted(screenshot_paths.items()):
        path = Path(str(raw_path or "")).expanduser()
        record: dict[str, object] = {
            "relative_path": path.name if str(raw_path or "") else "",
            "sha256": "",
            "byte_size": 0,
            "dimensions": [],
        }
        try:
            resolved = path.resolve(strict=True)
            relative = resolved.relative_to(root)
            content = resolved.read_bytes()
            with Image.open(resolved) as image:
                dimensions = [int(image.width), int(image.height)]
                image.verify()
            record = {
                "relative_path": relative.as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "byte_size": len(content),
                "dimensions": dimensions,
            }
        except (OSError, ValueError):
            pass
        artifacts[str(name)] = record
    aggregate = seal_evidence_identity("screenshots", artifacts)[_IDENTITY_FIELD]
    return {"artifacts": artifacts, "aggregate_sha256": aggregate}


def collect_runtime_input_evidence(
    input_paths: Mapping[str, Path],
    *,
    kinds: Mapping[str, str] | None = None,
    retained: bool,
) -> dict[str, object]:
    """Hash runtime inputs without retaining private filesystem locations."""
    input_kinds = dict(kinds or {})
    artifacts: dict[str, dict[str, object]] = {}
    for name, raw_path in sorted(input_paths.items()):
        path = Path(raw_path).expanduser()
        record: dict[str, object] = {
            "kind": str(input_kinds.get(name) or "runtime-input"),
            "display_name": path.name,
            "sha256": "",
            "byte_size": 0,
            "retained": bool(retained),
        }
        try:
            content_sha256, byte_size = _stable_regular_file_identity(path)
            record.update(
                {
                    "sha256": content_sha256,
                    "byte_size": byte_size,
                }
            )
        except (OSError, ValueError):
            pass
        artifacts[str(name)] = record
    aggregate = seal_evidence_identity("runtime-inputs", artifacts)[_IDENTITY_FIELD]
    return {"artifacts": artifacts, "aggregate_sha256": aggregate}


def finalize_strict_capture_evidence(
    payload: dict[str, Any],
    *,
    requested_model_id: str,
    runtime_snapshot: Mapping[str, object] | None,
    cache_dir: str,
    artifact_root: Path,
    source_identity_at_start: Mapping[str, object],
    host_actions: Sequence[str],
    runtime_input_paths: Mapping[str, Path] | None = None,
    runtime_input_kinds: Mapping[str, str] | None = None,
    runtime_input_evidence_at_start: Mapping[str, object] | None = None,
) -> tuple[bool, str]:
    """Attach strict local-runtime provenance and validate the completed artifact."""
    snapshot = dict(runtime_snapshot or {})
    loaded_model_id = (
        str(snapshot.get("model_id") or "")
        if snapshot.get("phase") == "ready" and snapshot.get("initialized") is True
        else ""
    )
    runtime = payload.get("runtime")
    runtime_payload = dict(runtime) if isinstance(runtime, Mapping) else {}
    runtime_payload.pop("cache_dir", None)
    runtime_payload["cache_location"] = "<local-model-cache>"
    runtime_payload["requested_model_id"] = requested_model_id
    runtime_payload["loaded_model_id"] = loaded_model_id
    runtime_payload["model_identity"] = collect_model_identity(
        requested_model_id=requested_model_id,
        loaded_model_id=loaded_model_id,
        cache_dir=cache_dir,
    )
    payload["runtime"] = runtime_payload

    completed_source = collect_capture_source_identity(refresh=True)
    payload["source_identity"] = completed_source
    started_digest = str(source_identity_at_start.get(_IDENTITY_FIELD) or "")
    completed_digest = str(completed_source.get(_IDENTITY_FIELD) or "")
    payload["capture_source"] = {
        "identity_at_start": started_digest,
        "identity_at_completion": completed_digest,
        "stable": bool(started_digest and started_digest == completed_digest),
    }
    payload["host_assistance"] = {
        "classification": "host-assisted" if host_actions else "model-only",
        "used": bool(host_actions),
        "actions": list(host_actions),
    }
    payload["screenshot_artifacts"] = collect_screenshot_evidence(
        _walkthrough_screenshot_paths(payload),
        artifact_root=artifact_root,
    )
    runtime_inputs = dict(runtime_input_paths or {})
    if runtime_inputs:
        completed_inputs = collect_runtime_input_evidence(
            runtime_inputs,
            kinds=runtime_input_kinds,
            retained=False,
        )
        payload["runtime_input_artifacts"] = completed_inputs
        started_inputs = _mapping(runtime_input_evidence_at_start)
        started_digest = str(started_inputs.get("aggregate_sha256") or "")
        completed_digest = str(completed_inputs.get("aggregate_sha256") or "")
        payload["capture_runtime_inputs"] = {
            "identity_at_start": started_digest,
            "identity_at_completion": completed_digest,
            "stable": bool(started_digest and started_digest == completed_digest),
        }
    payload.pop("source_path", None)
    payload.pop("_private_source_path", None)
    return validate_strict_capture_evidence(
        payload,
        current_source_identity=completed_source,
        current_model_identity=_mapping(runtime_payload.get("model_identity")),
        artifact_root=artifact_root,
    )


def validate_strict_capture_evidence(
    payload: Mapping[str, object],
    *,
    current_source_identity: Mapping[str, object] | None = None,
    current_model_identity: Mapping[str, object] | None = None,
    artifact_root: Path | None = None,
    required_runtime_inputs: Sequence[str] = (),
) -> tuple[bool, str]:
    """Fail closed on stale, incomplete, or tampered local Granite evidence."""
    if any(
        key in payload
        for key in ("source_path", "_private_source_path", "absolute_source_path")
    ):
        return False, "Strict capture evidence exposes a private runtime source path."
    runtime = _mapping(payload.get("runtime"))
    requested = str(runtime.get("requested_model_id") or "")
    loaded = str(runtime.get("loaded_model_id") or "")
    if requested != PRIMARY_LOCAL_MODEL_ID or loaded != PRIMARY_LOCAL_MODEL_ID:
        return False, "Requested and actually loaded models must be exact Granite."

    model = _mapping(runtime.get("model_identity"))
    ok, reason = _validate_sealed_identity("model", model)
    if not ok:
        return False, f"Model identity is invalid: {reason}"
    spec = local_model_spec(PRIMARY_LOCAL_MODEL_ID)
    if spec is None or model.get("loaded_revision") != spec.revision:
        return False, "Model identity does not contain the pinned Granite revision."
    if (
        model.get("requested_model_id") != requested
        or model.get("loaded_model_id") != loaded
        or model.get("loader_policy") != _MODEL_LOADER_POLICY
        or model.get("cache_complete") is not True
        or not _HEX_SHA256.fullmatch(str(model.get("snapshot_manifest_sha256") or ""))
        or int(model.get("snapshot_file_count") or 0) <= 0
        or int(model.get("snapshot_total_bytes") or 0) <= 0
    ):
        return False, "Model identity is incomplete or inconsistent."
    if any(key in model for key in ("cache_dir", "snapshot_path", "absolute_path")):
        return False, "Model identity exposes a private cache path."
    if current_model_identity is not None:
        current_model = _mapping(current_model_identity)
        current_ok, current_reason = _validate_sealed_identity(
            "model",
            current_model,
        )
        if not current_ok:
            return False, f"Current model identity is invalid: {current_reason}"
        if current_model.get(_IDENTITY_FIELD) != model.get(_IDENTITY_FIELD):
            return False, "Model cache snapshot identity is stale."

    source = _mapping(payload.get("source_identity"))
    ok, reason = _validate_sealed_identity("source", source)
    if not ok:
        return False, f"Source identity is invalid: {reason}"
    if (
        not _HEX_GIT.fullmatch(str(source.get("commit_sha") or ""))
        or not _HEX_GIT.fullmatch(str(source.get("head_tree_sha") or ""))
        or not _HEX_SHA256.fullmatch(str(source.get("dirty_fingerprint") or ""))
        or not _HEX_SHA256.fullmatch(str(source.get("source_content_sha256") or ""))
    ):
        return False, "Source identity is incomplete."
    if any(key in source for key in ("repo_root", "worktree", "absolute_path")):
        return False, "Source identity exposes a private checkout path."
    if source.get("dirty") is not False:
        return False, "Strict capture evidence requires a clean source checkout."
    if current_source_identity is not None:
        current = _mapping(current_source_identity)
        current_ok, current_reason = _validate_sealed_identity("source", current)
        if not current_ok:
            return False, f"Current source identity is invalid: {current_reason}"
        if current.get(_IDENTITY_FIELD) != source.get(_IDENTITY_FIELD):
            return False, "Source identity is stale."

    capture_source = _mapping(payload.get("capture_source"))
    source_digest = str(source.get(_IDENTITY_FIELD) or "")
    if (
        capture_source.get("stable") is not True
        or capture_source.get("identity_at_start") != source_digest
        or capture_source.get("identity_at_completion") != source_digest
    ):
        return False, "Capture source identity changed during execution."

    assistance = _mapping(payload.get("host_assistance"))
    actions = assistance.get("actions")
    if (
        assistance.get("classification") not in {"host-assisted", "model-only"}
        or not isinstance(assistance.get("used"), bool)
        or not isinstance(actions, list)
        or assistance.get("used") is not bool(actions)
    ):
        return False, "Host assistance identity is missing or inconsistent."

    screenshots = _mapping(payload.get("screenshot_artifacts"))
    artifacts = _mapping(screenshots.get("artifacts"))
    if not artifacts:
        return False, "Screenshot identity is missing."
    for name, raw_record in artifacts.items():
        record = _mapping(raw_record)
        dimensions = record.get("dimensions")
        if (
            not str(record.get("relative_path") or "")
            or Path(str(record.get("relative_path"))).is_absolute()
            or not _HEX_SHA256.fullmatch(str(record.get("sha256") or ""))
            or int(record.get("byte_size") or 0) <= 0
            or not isinstance(dimensions, list)
            or len(dimensions) != 2
            or any(int(value) <= 0 for value in dimensions)
        ):
            return False, f"Screenshot identity is invalid: {name}."
    expected_aggregate = seal_evidence_identity("screenshots", artifacts)[
        _IDENTITY_FIELD
    ]
    if screenshots.get("aggregate_sha256") != expected_aggregate:
        return False, "Screenshot aggregate identity is inconsistent."
    if artifact_root is not None:
        root = artifact_root.expanduser().resolve()
        for name, raw_record in artifacts.items():
            record = _mapping(raw_record)
            relative_path = Path(str(record.get("relative_path") or ""))
            try:
                screenshot_path = (root / relative_path).resolve(strict=True)
                screenshot_path.relative_to(root)
                content = screenshot_path.read_bytes()
                with Image.open(screenshot_path) as image:
                    dimensions = [int(image.width), int(image.height)]
                    image.verify()
            except (OSError, ValueError):
                return False, f"Screenshot artifact is missing or unreadable: {name}."
            if (
                hashlib.sha256(content).hexdigest() != record.get("sha256")
                or len(content) != record.get("byte_size")
                or dimensions != record.get("dimensions")
            ):
                return False, f"Screenshot artifact was mutated: {name}."

    runtime_input_evidence = _mapping(payload.get("runtime_input_artifacts"))
    runtime_input_artifacts = _mapping(runtime_input_evidence.get("artifacts"))
    if required_runtime_inputs and not runtime_input_artifacts:
        return False, "Required runtime input identity is missing."
    if runtime_input_artifacts:
        for required_name in required_runtime_inputs:
            if required_name not in runtime_input_artifacts:
                return False, f"Required runtime input is missing: {required_name}."
        for name, raw_record in runtime_input_artifacts.items():
            record = _mapping(raw_record)
            display_name = str(record.get("display_name") or "")
            if (
                not str(record.get("kind") or "")
                or not display_name
                or Path(display_name).is_absolute()
                or Path(display_name).name != display_name
                or not _HEX_SHA256.fullmatch(str(record.get("sha256") or ""))
                or int(record.get("byte_size") or 0) <= 0
                or not isinstance(record.get("retained"), bool)
                or any(
                    key in record
                    for key in ("path", "source_path", "absolute_path", "directory")
                )
            ):
                return False, f"Runtime input identity is invalid: {name}."
        expected_input_aggregate = seal_evidence_identity(
            "runtime-inputs",
            runtime_input_artifacts,
        )[_IDENTITY_FIELD]
        if runtime_input_evidence.get("aggregate_sha256") != expected_input_aggregate:
            return False, "Runtime input aggregate identity is inconsistent."
        capture_inputs = _mapping(payload.get("capture_runtime_inputs"))
        if (
            capture_inputs.get("stable") is not True
            or capture_inputs.get("identity_at_start") != expected_input_aggregate
            or capture_inputs.get("identity_at_completion") != expected_input_aggregate
        ):
            return False, "Runtime input identity changed during execution."
    elif payload.get("capture_runtime_inputs") is not None:
        return False, "Runtime input capture identity has no artifacts."

    offline = _mapping(payload.get("hf_offline"))
    if (
        offline.get("HF_HUB_OFFLINE") != "1"
        or offline.get("TRANSFORMERS_OFFLINE") != "1"
    ):
        return False, "Strict local evidence did not enforce offline model loading."
    if _mapping(payload.get("shutdown")).get("status") != "completed":
        return False, "Strict local evidence did not reach terminal shutdown."
    return True, ""


def _validate_sealed_identity(
    kind: str,
    value: Mapping[str, object],
) -> tuple[bool, str]:
    digest = str(value.get(_IDENTITY_FIELD) or "")
    if not _HEX_SHA256.fullmatch(digest):
        return False, "identity digest is missing"
    if seal_evidence_identity(kind, value).get(_IDENTITY_FIELD) != digest:
        return False, "identity digest does not match its fields"
    return True, ""


def _snapshot_manifest_identity(
    snapshot: Path | None,
    *,
    cache_root: Path,
) -> tuple[str, int, int]:
    if snapshot is None:
        return "", 0, 0
    try:
        root = cache_root.expanduser().resolve(strict=True)
        resolved_snapshot = snapshot.expanduser().resolve(strict=True)
        resolved_snapshot.relative_to(root)
    except (OSError, ValueError):
        return "", 0, 0
    if not resolved_snapshot.is_dir():
        return "", 0, 0
    records: list[dict[str, object]] = []
    content_hashes: dict[tuple[int, int, int, int, int], str] = {}
    total_bytes = 0
    try:
        for path in sorted(resolved_snapshot.rglob("*")):
            path_lstat = path.lstat()
            if stat.S_ISDIR(path_lstat.st_mode):
                continue
            relative = path.relative_to(resolved_snapshot).as_posix()
            if stat.S_ISLNK(path_lstat.st_mode):
                target = path.resolve(strict=True)
                target.relative_to(root)
                target_stat = target.stat()
                if not stat.S_ISREG(target_stat.st_mode):
                    return "", 0, 0
                content_identity = _cached_regular_file_sha256(
                    target,
                    file_stat=target_stat,
                    cache=content_hashes,
                )
                size = target_stat.st_size
                kind = "regular-file-symlink"
            elif stat.S_ISREG(path_lstat.st_mode):
                content_identity = _cached_regular_file_sha256(
                    path,
                    file_stat=path_lstat,
                    cache=content_hashes,
                )
                size = path_lstat.st_size
                kind = "regular-file"
            else:
                return "", 0, 0
            total_bytes += size
            records.append(
                {
                    "path": relative,
                    "kind": kind,
                    "bytes": size,
                    "content_identity": content_identity,
                }
            )
    except (OSError, ValueError):
        return "", 0, 0
    if not records:
        return "", 0, 0
    encoded = json.dumps(
        records,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest(), len(records), total_bytes


def _cached_regular_file_sha256(
    path: Path,
    *,
    file_stat: os.stat_result,
    cache: dict[tuple[int, int, int, int, int], str],
) -> str:
    """Hash each stable regular inode once per manifest scan."""
    key = _regular_file_stat_key(file_stat)
    cached = cache.get(key)
    if cached is not None:
        return cached
    digest = _file_sha256(path)
    completed_stat = path.stat()
    if not stat.S_ISREG(completed_stat.st_mode):
        raise ValueError("Snapshot artifact stopped being a regular file.")
    if _regular_file_stat_key(completed_stat) != key:
        raise OSError("Snapshot artifact changed while it was being hashed.")
    cache[key] = digest
    return digest


def _regular_file_stat_key(
    file_stat: os.stat_result,
) -> tuple[int, int, int, int, int]:
    return (
        int(file_stat.st_dev),
        int(file_stat.st_ino),
        int(file_stat.st_size),
        int(file_stat.st_mtime_ns),
        int(file_stat.st_ctime_ns),
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_regular_file_identity(path: Path) -> tuple[str, int]:
    initial_stat = path.lstat()
    if not stat.S_ISREG(initial_stat.st_mode):
        raise ValueError("Runtime input is not a regular file.")
    content_sha256 = _file_sha256(path)
    completed_stat = path.stat()
    if not stat.S_ISREG(completed_stat.st_mode) or _regular_file_stat_key(
        completed_stat
    ) != _regular_file_stat_key(initial_stat):
        raise OSError("Runtime input changed while it was being hashed.")
    return content_sha256, int(completed_stat.st_size)


def _walkthrough_screenshot_paths(payload: Mapping[str, object]) -> dict[str, object]:
    paths = {
        str(name): path
        for name, path in _mapping(payload.get("screenshots")).items()
        if path
    }
    turns = payload.get("turns")
    if isinstance(turns, list):
        for index, turn in enumerate(turns, start=1):
            screenshot = _mapping(turn).get("screenshot")
            if screenshot:
                paths[f"turn_{index:02d}"] = screenshot
    confirmations = payload.get("confirmation_events")
    if isinstance(confirmations, list):
        for index, event in enumerate(confirmations, start=1):
            screenshot = _mapping(event).get("screenshot")
            if screenshot:
                paths[f"confirmation_{index:02d}"] = screenshot
    return paths


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
