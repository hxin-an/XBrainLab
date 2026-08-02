"""Safe, versioned persistence primitives for training artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import torch

from ...utils.filesystem_identity import (
    FilesystemIdentityError,
    StableDirectoryIdentity,
    retain_directory_identity,
)

ARTIFACT_STORE_SCHEMA_VERSION = 1
EVALUATION_RECORD_ARTIFACT_TYPE = "xbrainlab.evaluation_record"
SALIENCY_EXPORT_ARTIFACT_TYPE = "xbrainlab.saliency_export"
TRAINING_RECORD_ARTIFACT_TYPE = "xbrainlab.training_record"

_RESERVED_FLOAT_TAG = "__xbrainlab_nonfinite_float__"
_RESERVED_TUPLE_TAG = "__xbrainlab_tuple__"
_BASE_MANIFEST_KEYS = frozenset(
    {
        "artifact_store_schema_version",
        "artifact_type",
        "arrays",
        "payload",
    }
)


class ArtifactStoreError(RuntimeError):
    """Base error for safe artifact persistence failures."""


class ArtifactIntegrityError(ArtifactStoreError):
    """Raised when a safe artifact is malformed or internally inconsistent."""


class UnsupportedArtifactError(ArtifactStoreError):
    """Raised when an unsafe legacy or unknown artifact cannot be loaded."""


def _sha256(path: Path, identity: StableDirectoryIdentity) -> str:
    digest = hashlib.sha256()
    with identity.open_existing_binary(path) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _temporary_path(target: Path) -> Path:
    return target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")


@contextmanager
def _verified_parent_access(
    target: Path,
    directory_identity: StableDirectoryIdentity | None,
    *,
    create: bool,
) -> Iterator[StableDirectoryIdentity]:
    parent = target.parent
    if directory_identity is not None:
        directory_identity.assert_matches(parent)
        yield directory_identity
        return
    if create:
        parent.mkdir(parents=True, exist_ok=True)
    retained = retain_directory_identity(parent)
    try:
        retained.assert_matches(parent)
        yield retained
    finally:
        retained.close()


def _cleanup_temporary(
    path: Path,
    identity: StableDirectoryIdentity,
) -> None:
    """Remove a temporary only while its parent is still trusted."""
    try:
        identity.assert_matches(path.parent)
    except FilesystemIdentityError:
        return
    identity.unlink_entry(path, missing_ok=True)


def _encode_json_value(value: object, *, location: str) -> object:
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        if math.isnan(value):
            marker = "nan"
        elif value > 0:
            marker = "infinity"
        else:
            marker = "-infinity"
        return {_RESERVED_FLOAT_TAG: marker}
    if isinstance(value, Mapping):
        encoded: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ArtifactStoreError(
                    f"{location} contains a non-string JSON key: {key!r}."
                )
            if key in {_RESERVED_FLOAT_TAG, _RESERVED_TUPLE_TAG}:
                raise ArtifactStoreError(
                    f"{location} uses reserved artifact key {key!r}."
                )
            encoded[key] = _encode_json_value(
                item,
                location=f"{location}.{key}",
            )
        return encoded
    if isinstance(value, tuple):
        return {
            _RESERVED_TUPLE_TAG: [
                _encode_json_value(item, location=f"{location}[{index}]")
                for index, item in enumerate(value)
            ]
        }
    if isinstance(value, list):
        return [
            _encode_json_value(item, location=f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ArtifactStoreError(
        f"{location} contains unsupported value type {type(value).__qualname__}."
    )


def _decode_json_value(value: object, *, location: str) -> object:
    if isinstance(value, list):
        return [
            _decode_json_value(item, location=f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        if set(value) == {_RESERVED_TUPLE_TAG}:
            items = value[_RESERVED_TUPLE_TAG]
            if not isinstance(items, list):
                raise ArtifactIntegrityError(
                    f"{location} contains an invalid tuple envelope."
                )
            return tuple(
                _decode_json_value(item, location=f"{location}[{index}]")
                for index, item in enumerate(items)
            )
        if set(value) == {_RESERVED_FLOAT_TAG}:
            marker = value[_RESERVED_FLOAT_TAG]
            if marker == "nan":
                return float("nan")
            if marker == "infinity":
                return float("inf")
            if marker == "-infinity":
                return float("-inf")
            raise ArtifactIntegrityError(
                f"{location} contains an invalid non-finite float token."
            )
        return {
            key: _decode_json_value(item, location=f"{location}.{key}")
            for key, item in value.items()
        }
    return value


def _numeric_array(value: object, *, name: str) -> np.ndarray:
    if isinstance(value, torch.Tensor):
        tensor = value.detach()
        if tensor.is_conj():
            tensor = tensor.resolve_conj()
        if tensor.is_neg():
            tensor = tensor.resolve_neg()
        value = tensor.cpu().numpy()
    try:
        array = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ArtifactStoreError(
            f"Array {name!r} cannot be converted to NumPy."
        ) from exc
    if array.dtype.hasobject or not (
        np.issubdtype(array.dtype, np.number) or np.issubdtype(array.dtype, np.bool_)
    ):
        raise ArtifactStoreError(
            f"Array {name!r} must use a numeric or boolean dtype, not {array.dtype}."
        )
    return np.ascontiguousarray(array)


def write_json_npz_artifact(
    manifest_path: str | Path,
    *,
    artifact_type: str,
    payload: Mapping[str, object],
    arrays: Mapping[str, object],
    arrays_filename: str | None = None,
    directory_identity: StableDirectoryIdentity | None = None,
) -> None:
    """Atomically write one JSON manifest and one non-pickle NPZ payload."""
    target = Path(manifest_path)
    array_name = arrays_filename or f"{target.name}.npz"
    if Path(array_name).name != array_name:
        raise ArtifactStoreError("Artifact array filename must be a basename.")
    arrays_path = target.with_name(array_name)
    normalized_arrays: dict[str, np.ndarray] = {}
    for name, value in arrays.items():
        if not isinstance(name, str) or not name or "/" in name or "\\" in name:
            raise ArtifactStoreError(f"Invalid artifact array name: {name!r}.")
        normalized_arrays[name] = _numeric_array(value, name=name)

    with _verified_parent_access(
        target,
        directory_identity,
        create=True,
    ) as identity:
        arrays_temp = _temporary_path(arrays_path)
        manifest_temp = _temporary_path(target)
        cleanup_allowed = True
        try:
            identity.assert_matches(target.parent)
            with identity.create_exclusive_binary(arrays_temp) as stream:
                np.savez_compressed(stream, **normalized_arrays)
            manifest = {
                "artifact_store_schema_version": ARTIFACT_STORE_SCHEMA_VERSION,
                "artifact_type": artifact_type,
                "arrays": {
                    "file": arrays_path.name,
                    "sha256": _sha256(arrays_temp, identity),
                    "keys": sorted(normalized_arrays),
                },
                "payload": _encode_json_value(payload, location="payload"),
            }
            encoded_manifest = (
                json.dumps(
                    manifest,
                    ensure_ascii=True,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
            with identity.create_exclusive_binary(manifest_temp) as stream:
                stream.write(encoded_manifest.encode("utf-8"))
            identity.replace_entry(arrays_temp, arrays_path)
            identity.replace_entry(manifest_temp, target)
        except FilesystemIdentityError:
            cleanup_allowed = False
            raise
        finally:
            if cleanup_allowed:
                _cleanup_temporary(arrays_temp, identity)
                _cleanup_temporary(manifest_temp, identity)


def _legacy_message(path: Path, artifact_type: str) -> str:
    if artifact_type == EVALUATION_RECORD_ARTIFACT_TYPE:
        label = "evaluation record"
        action = "Start a new evaluation"
    elif artifact_type == TRAINING_RECORD_ARTIFACT_TYPE:
        label = "training record"
        action = "Start a new training run"
    else:
        label = "artifact"
        action = "Create a new artifact"
    return (
        f"Unsupported legacy {label} at {path}. XBrainLab no longer loads "
        "PyTorch-pickled record artifacts because they can execute arbitrary "
        f"code. {action} and remove or archive this file. Unsafe migration is "
        "not supported."
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-standard JSON constant {value!r} is not allowed.")


def read_json_npz_artifact(
    manifest_path: str | Path,
    *,
    expected_artifact_type: str,
    directory_identity: StableDirectoryIdentity | None = None,
) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    """Read and validate one safe artifact without enabling NumPy pickle."""
    path = Path(manifest_path)
    with _verified_parent_access(
        path,
        directory_identity,
        create=False,
    ) as identity:
        try:
            with identity.open_existing_binary(path) as stream:
                raw = json.loads(
                    stream.read().decode("utf-8"),
                    parse_constant=_reject_json_constant,
                )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise UnsupportedArtifactError(
                _legacy_message(path, expected_artifact_type)
            ) from exc
        if type(raw) is not dict:
            raise ArtifactIntegrityError("Artifact manifest root must be an object.")
        if set(raw) != _BASE_MANIFEST_KEYS:
            raise ArtifactIntegrityError(
                "Artifact manifest fields are incomplete or unrecognized."
            )
        version = raw.get("artifact_store_schema_version")
        if type(version) is not int or version != ARTIFACT_STORE_SCHEMA_VERSION:
            raise UnsupportedArtifactError(
                f"Unsupported artifact store schema version {version!r} at {path}. "
                "Upgrade XBrainLab or create a new artifact; unsafe migration is "
                "not supported."
            )
        if raw.get("artifact_type") != expected_artifact_type:
            raise ArtifactIntegrityError(
                f"Artifact type must be {expected_artifact_type!r}."
            )
        arrays_descriptor = raw.get("arrays")
        if type(arrays_descriptor) is not dict:
            raise ArtifactIntegrityError("Artifact array descriptor is malformed.")
        if set(arrays_descriptor) != {"file", "sha256", "keys"}:
            raise ArtifactIntegrityError(
                "Artifact array descriptor fields are invalid."
            )
        arrays_filename = arrays_descriptor.get("file")
        expected_hash = arrays_descriptor.get("sha256")
        expected_keys = arrays_descriptor.get("keys")
        if (
            not isinstance(arrays_filename, str)
            or Path(arrays_filename).name != arrays_filename
            or not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or not isinstance(expected_keys, list)
            or any(not isinstance(key, str) for key in expected_keys)
            or expected_keys != sorted(set(expected_keys))
        ):
            raise ArtifactIntegrityError(
                "Artifact array descriptor values are invalid."
            )
        arrays_path = path.with_name(arrays_filename)
        if not identity.regular_file_exists(arrays_path):
            raise ArtifactIntegrityError(
                f"Artifact numeric payload is missing: {arrays_path}."
            )
        if _sha256(arrays_path, identity) != expected_hash:
            raise ArtifactIntegrityError(
                f"Artifact numeric payload failed its SHA-256 check: {arrays_path}."
            )
        try:
            with (
                identity.open_existing_binary(arrays_path) as stream,
                np.load(stream, allow_pickle=False) as archive,
            ):
                if sorted(archive.files) != expected_keys:
                    raise ArtifactIntegrityError(
                        "Artifact numeric payload keys do not match the manifest."
                    )
                loaded_arrays = {
                    name: _numeric_array(archive[name], name=name)
                    for name in archive.files
                }
        except ArtifactStoreError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise ArtifactIntegrityError(
                f"Artifact numeric payload is invalid: {arrays_path}."
            ) from exc
        payload = raw.get("payload")
        if type(payload) is not dict:
            raise ArtifactIntegrityError("Artifact JSON payload must be an object.")
        decoded_payload = _decode_json_value(payload, location="payload")
        if type(decoded_payload) is not dict:
            raise ArtifactIntegrityError("Artifact JSON payload must be an object.")
        return decoded_payload, loaded_arrays


def _validated_state_dict(state: object) -> dict[str, torch.Tensor]:
    if not isinstance(state, Mapping):
        raise ArtifactStoreError("Model checkpoint must be a state_dict mapping.")
    normalized: dict[str, torch.Tensor] = {}
    for key, value in state.items():
        if not isinstance(key, str) or not isinstance(value, torch.Tensor):
            raise ArtifactStoreError(
                "Model checkpoint state_dict must contain only string tensor entries."
            )
        normalized[key] = value.detach()
    return normalized


def load_model_state_dict(
    path: str | Path,
    *,
    directory_identity: StableDirectoryIdentity | None = None,
) -> dict[str, torch.Tensor]:
    """Load a tensor-only model state dict with PyTorch safe mode enabled."""
    target = Path(path)
    with _verified_parent_access(
        target,
        directory_identity,
        create=False,
    ) as identity:
        try:
            with identity.open_existing_binary(target) as stream:
                state = torch.load(stream, map_location="cpu", weights_only=True)
        except FilesystemIdentityError:
            raise
        except Exception as exc:
            raise ArtifactIntegrityError(
                f"Model state_dict checkpoint is invalid: {target}."
            ) from exc
        return _validated_state_dict(state)


def save_model_state_dict(
    state: Mapping[str, torch.Tensor],
    path: str | Path,
    *,
    directory_identity: StableDirectoryIdentity | None = None,
) -> None:
    """Atomically write a tensor-only model state dict."""
    target = Path(path)
    normalized = _validated_state_dict(state)
    with _verified_parent_access(
        target,
        directory_identity,
        create=True,
    ) as identity:
        temporary = _temporary_path(target)
        cleanup_allowed = True
        try:
            identity.assert_matches(target.parent)
            with identity.create_exclusive_binary(temporary) as stream:
                torch.save(normalized, stream)
            identity.replace_entry(temporary, target)
        except FilesystemIdentityError:
            cleanup_allowed = False
            raise
        finally:
            if cleanup_allowed:
                _cleanup_temporary(temporary, identity)


__all__ = [
    "ARTIFACT_STORE_SCHEMA_VERSION",
    "EVALUATION_RECORD_ARTIFACT_TYPE",
    "SALIENCY_EXPORT_ARTIFACT_TYPE",
    "TRAINING_RECORD_ARTIFACT_TYPE",
    "ArtifactIntegrityError",
    "ArtifactStoreError",
    "UnsupportedArtifactError",
    "load_model_state_dict",
    "read_json_npz_artifact",
    "save_model_state_dict",
    "write_json_npz_artifact",
]
