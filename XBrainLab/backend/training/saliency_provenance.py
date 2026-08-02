"""Saliency artifact provenance and deterministic identity fingerprints."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import product
from typing import Any, cast

import numpy as np
import torch

__all__ = [
    "SALIENCY_CONTEXT_SCHEMA_VERSION",
    "SALIENCY_PRODUCER_SCHEMA_VERSION",
    "SaliencyArtifactContext",
    "SaliencyContextError",
    "SaliencyProducerIdentity",
    "canonicalize_saliency_identity",
    "describe_saliency_array",
    "fingerprint_saliency_epoch_data",
    "fingerprint_saliency_identity",
    "fingerprint_saliency_model_state",
    "fingerprint_saliency_split_mask",
]


SALIENCY_CONTEXT_SCHEMA_VERSION = 3
SALIENCY_PRODUCER_SCHEMA_VERSION = 2
_ARRAY_CONTENT_HASH_SCHEMA_VERSION = 1
_ARRAY_HASH_CHUNK_BYTES = 4 * 1024 * 1024
_IDENTITY_SAMPLE_LIMIT = 64
_SHA256_HEX_LENGTH = 64


class SaliencyContextError(ValueError):
    """Raised when saliency cannot be tied to the current EEG identity."""


def _canonical_identity_value(value: object) -> object:
    """Convert provenance metadata into deterministic JSON values."""
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"float": "nan"}
        if math.isinf(value):
            return {"float": "+inf" if value > 0 else "-inf"}
        return {"float_hex": value.hex()}
    if isinstance(value, Enum):
        cls = value.__class__
        return {"enum": f"{cls.__module__}.{cls.__qualname__}.{value.name}"}
    if isinstance(value, type):
        return {"type": f"{value.__module__}.{value.__qualname__}"}
    if type(value).__module__ == "torch" and type(value).__name__ in {
        "dtype",
        "device",
    }:
        return {"torch_value": str(value)}
    if isinstance(value, os.PathLike):
        return {"path": os.path.normcase(os.path.normpath(os.fspath(value)))}
    if isinstance(value, np.ndarray) or torch.is_tensor(value):
        return {"array": _exact_array_descriptor(value)}
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in normalized:
                raise SaliencyContextError(
                    "Saliency provenance contains ambiguous mapping keys."
                )
            normalized[key_text] = _canonical_identity_value(item)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, (set, frozenset)):
        normalized_items = [_canonical_identity_value(item) for item in value]
        return sorted(
            normalized_items,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_canonical_identity_value(item) for item in value]
    raise SaliencyContextError(
        "Saliency provenance contains an unsupported value of type "
        f"{type(value).__module__}.{type(value).__qualname__}."
    )


def _fingerprint_identity_payload(value: object) -> str:
    canonical = json.dumps(
        _canonical_identity_value(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256_fingerprint(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _bounded_indices(
    element_count: int,
    *,
    limit: int = _IDENTITY_SAMPLE_LIMIT,
) -> tuple[int, ...]:
    sample_count = min(max(element_count, 0), max(int(limit), 0))
    if sample_count <= 0:
        return ()
    if sample_count == 1:
        return (0,)
    last_index = element_count - 1
    return tuple(
        (sample_index * last_index) // (sample_count - 1)
        for sample_index in range(sample_count)
    )


def _exact_array_descriptor(
    value: object,
    *,
    require_finite_float: bool = False,
) -> dict[str, object] | None:
    """Describe array metadata and exact logical content with bounded memory."""
    if value is None:
        return None
    raw_shape = getattr(value, "shape", None)
    if raw_shape is None:
        return None
    try:
        shape = tuple(int(item) for item in raw_shape)
        element_count = math.prod(shape)
    except (TypeError, ValueError):
        return None
    descriptor: dict[str, object] = {
        "shape": shape,
        "dtype": str(getattr(value, "dtype", "unknown")),
        "element_count": element_count,
        "content_hash_schema_version": _ARRAY_CONTENT_HASH_SCHEMA_VERSION,
        "logical_order": "C",
    }
    if isinstance(value, np.ndarray):
        if require_finite_float and not np.issubdtype(value.dtype, np.floating):
            raise SaliencyContextError(
                "Saliency attribution payloads require a floating NumPy dtype."
            )
        descriptor["content_sha256"] = _fingerprint_numpy_array_content(
            value,
            require_finite=require_finite_float,
        )
    elif torch.is_tensor(value):
        if require_finite_float and not value.is_floating_point():
            raise SaliencyContextError(
                "Saliency attribution payloads require a floating Torch dtype."
            )
        descriptor["content_sha256"] = _fingerprint_torch_tensor_content(
            value,
            require_finite=require_finite_float,
        )
    else:
        raise SaliencyContextError(
            "Exact saliency provenance supports only NumPy arrays and Torch tensors; "
            f"received {type(value).__module__}.{type(value).__qualname__}."
        )
    return descriptor


def _fingerprint_numpy_array_content(
    value: np.ndarray,
    *,
    require_finite: bool = False,
) -> str:
    """Hash NumPy content in logical C order without materializing the full array."""
    if value.dtype.hasobject or value.dtype.fields is not None:
        raise SaliencyContextError(
            "Exact saliency provenance does not support object or structured NumPy "
            "arrays."
        )
    item_size = max(int(value.dtype.itemsize), 1)
    if item_size > _ARRAY_HASH_CHUNK_BYTES:
        raise SaliencyContextError(
            "A NumPy provenance element exceeds the bounded hashing memory budget."
        )
    buffer_elements = max(1, _ARRAY_HASH_CHUNK_BYTES // item_size)
    digest = hashlib.sha256()
    iterator = cast(
        Iterator[np.ndarray],
        np.nditer(
            value,
            flags=["buffered", "external_loop", "zerosize_ok"],
            # NumPy accepts ``contig`` here although its typing omits the flag.
            op_flags=cast(Any, [["readonly", "contig"]]),
            order="C",
            buffersize=buffer_elements,
        ),
    )
    for chunk in iterator:
        if require_finite and not bool(np.isfinite(chunk).all()):
            raise SaliencyContextError(
                "Saliency attribution payloads must contain only finite values."
            )
        digest.update(_numpy_chunk_as_byte_view(chunk))
    return digest.hexdigest()


def _numpy_chunk_as_byte_view(chunk: np.ndarray) -> memoryview:
    """Expose one bounded, contiguous NumPy iterator chunk without copying it."""
    if not chunk.flags.c_contiguous:
        raise SaliencyContextError(
            "Internal NumPy provenance chunk is unexpectedly non-contiguous."
        )
    return memoryview(chunk).cast("B")


def _fingerprint_torch_tensor_content(
    value: torch.Tensor,
    *,
    require_finite: bool = False,
) -> str:
    """Hash dense Torch content in logical C order through bounded tensor slices."""
    if str(value.layout) != "torch.strided" or value.device.type == "meta":
        raise SaliencyContextError(
            "Exact saliency provenance requires a materialized dense Torch tensor."
        )
    if value.is_quantized:
        raise SaliencyContextError(
            "Exact saliency provenance does not support quantized Torch tensors."
        )
    element_size = max(int(value.element_size()), 1)
    chunk_elements = max(1, _ARRAY_HASH_CHUNK_BYTES // element_size)
    digest = hashlib.sha256()
    for chunk in _iter_torch_tensor_chunks(value.detach(), chunk_elements):
        if require_finite and not bool(chunk.isfinite().all().item()):
            raise SaliencyContextError(
                "Saliency attribution payloads must contain only finite values."
            )
        digest.update(_torch_chunk_as_byte_view(chunk))
    return digest.hexdigest()


def canonicalize_saliency_identity(value: object) -> object:
    """Return the one canonical identity representation used by saliency."""
    return _canonical_identity_value(value)


def fingerprint_saliency_identity(value: object) -> str:
    """Hash one saliency identity through the shared canonical JSON contract."""
    return _fingerprint_identity_payload(value)


def describe_saliency_array(
    value: object,
    *,
    require_finite_float: bool = False,
) -> dict[str, object]:
    """Describe exact logical C-order array content with bounded working memory."""
    descriptor = _exact_array_descriptor(
        value,
        require_finite_float=require_finite_float,
    )
    if descriptor is None:
        raise SaliencyContextError(
            "Saliency attribution payloads must be NumPy arrays or Torch tensors."
        )
    return descriptor


def _iter_torch_tensor_chunks(
    value: torch.Tensor,
    chunk_elements: int,
) -> Iterator[torch.Tensor]:
    """Yield row-major logical slabs whose element count is bounded."""
    if value.numel() == 0:
        return
    if value.ndim == 0:
        yield value
        return

    shape = tuple(int(size) for size in value.shape)
    trailing_elements = 1
    split_dimension = value.ndim - 1
    while split_dimension >= 0:
        dimension_elements = trailing_elements * shape[split_dimension]
        if dimension_elements > chunk_elements:
            break
        trailing_elements = dimension_elements
        split_dimension -= 1

    if split_dimension < 0:
        yield value
        return

    slice_length = max(1, chunk_elements // trailing_elements)
    prefix_ranges = (range(size) for size in shape[:split_dimension])
    prefixes = product(*prefix_ranges) if split_dimension > 0 else ((),)
    trailing_slices = (slice(None),) * (value.ndim - split_dimension - 1)
    for prefix in prefixes:
        for start in range(0, shape[split_dimension], slice_length):
            prefix_indices = tuple(int(index) for index in prefix)
            selection: tuple[int | slice, ...] = (
                *prefix_indices,
                slice(start, min(start + slice_length, shape[split_dimension])),
                *trailing_slices,
            )
            yield value[selection]


def _torch_chunk_as_byte_view(chunk: torch.Tensor) -> memoryview:
    """Move and materialize only one bounded Torch chunk as CPU bytes."""
    detached = chunk.detach()
    if detached.is_conj():
        detached = detached.resolve_conj()
    if detached.is_neg():
        detached = detached.resolve_neg()
    if detached.device.type == "cpu":
        cpu_chunk = detached
    else:
        transfer_chunk = detached if detached.is_contiguous() else detached.contiguous()
        cpu_chunk = transfer_chunk.to(device="cpu")
    if not cpu_chunk.is_contiguous():
        cpu_chunk = cpu_chunk.contiguous()
    byte_tensor = cpu_chunk.reshape(-1).view(
        torch.uint8,  # pyright: ignore[reportPrivateImportUsage]
    )
    return memoryview(byte_tensor.numpy()).cast("B")


def _bounded_sequence_descriptor(
    values: Sequence[object] | None,
    *,
    fields: tuple[str, ...],
) -> dict[str, object]:
    if values is None:
        return {"count": 0, "sentinels": []}
    count = len(values)
    sentinels = []
    for index in _bounded_indices(count):
        item = values[index]
        sentinels.append(
            {
                "index": index,
                "value": {
                    field: _canonical_identity_value(getattr(item, field, None))
                    for field in fields
                },
            }
        )
    return {"count": count, "sentinels": sentinels}


def _plain_identity_value(value: object) -> object:
    """Return a stable torch-serializable scalar for a class identity."""
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise SaliencyContextError(
        "Saliency class keys must be scalar strings or numbers; "
        f"received {type(value).__qualname__}."
    )


def _read_epoch_model_args(epoch_data: Any) -> dict[str, Any]:
    getter = getattr(epoch_data, "get_model_args", None)
    if not callable(getter):
        return {}
    value = getter()
    return dict(value) if isinstance(value, dict) else {}


def _read_channel_names(epoch_data: Any) -> tuple[str, ...]:
    getter = getattr(epoch_data, "get_channel_names", None)
    values: Any = (
        getter() if callable(getter) else getattr(epoch_data, "ch_names", None)
    )
    if values is None:
        raise SaliencyContextError("EEG channel names are unavailable.")
    names = tuple(str(value) for value in values)
    if not names or any(not name.strip() for name in names):
        raise SaliencyContextError("EEG channel names must be non-empty.")
    if len(names) != len(set(names)):
        raise SaliencyContextError("EEG channel names must be unique.")
    return names


def _read_montage_fingerprint(
    epoch_data: Any,
    channel_names: tuple[str, ...],
) -> str | None:
    getter = getattr(epoch_data, "get_montage_position", None)
    positions: Any = (
        getter()
        if callable(getter)
        else getattr(
            epoch_data,
            "channel_position",
            None,
        )
    )
    if positions is None:
        return None
    position_array = np.asarray(positions, dtype=float)
    if position_array.size == 0:
        return None
    if position_array.ndim != 2 or position_array.shape != (len(channel_names), 3):
        raise SaliencyContextError(
            "Montage positions must contain one x/y/z coordinate per EEG channel."
        )
    if not np.isfinite(position_array).all():
        raise SaliencyContextError("Montage positions must contain finite values.")
    payload = [
        [name, *[float(coordinate).hex() for coordinate in position]]
        for name, position in zip(channel_names, position_array, strict=True)
    ]
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_saliency_epoch_data(epoch_data: Any) -> str:
    """Fingerprint all EEG array content and bounded auxiliary metadata.

    Array content is streamed completely in logical C order. Source-window
    provenance remains bounded to stable metadata sentinels so fingerprinting
    does not construct an unbounded JSON payload.
    """
    if epoch_data is None:
        raise SaliencyContextError("Epoch data is unavailable.")

    def read_array(attribute: str, getter_name: str) -> object | None:
        value = getattr(epoch_data, attribute, None)
        if value is not None:
            return value
        getter = getattr(epoch_data, getter_name, None)
        return getter() if callable(getter) else None

    provenance_getter = getattr(epoch_data, "get_epoch_window_provenance", None)
    provenance = (
        provenance_getter()
        if callable(provenance_getter)
        else getattr(epoch_data, "epoch_window_provenance", ())
    )
    if not isinstance(provenance, Sequence):
        provenance = ()

    payload = {
        "model_args": _read_epoch_model_args(epoch_data),
        "class_map": getattr(epoch_data, "label_map", None),
        "subject_map": getattr(epoch_data, "subject_map", None),
        "session_map": getattr(epoch_data, "session_map", None),
        "channel_names": _read_channel_names(epoch_data),
        "sampling_frequency_hz": getattr(epoch_data, "sfreq", None),
        "epoch_start_seconds": getattr(epoch_data, "tmin", None),
        "data": _exact_array_descriptor(read_array("data", "get_data")),
        "labels": _exact_array_descriptor(read_array("label", "get_label_list")),
        "subjects": _exact_array_descriptor(read_array("subject", "get_subject_list")),
        "sessions": _exact_array_descriptor(read_array("session", "get_session_list")),
        "epoch_indices": _exact_array_descriptor(read_array("idx", "get_idx_list")),
        "trial_groups": _exact_array_descriptor(
            read_array("trial_group", "get_trial_group_list")
        ),
        "source_windows": _bounded_sequence_descriptor(
            provenance,
            fields=(
                "source_recording_id",
                "event_sample",
                "window_start_sample",
                "window_end_sample_exclusive",
                "source_sfreq",
                "epoch_sfreq",
                "source_coordinates_verified",
            ),
        ),
    }
    return _fingerprint_identity_payload(payload)


def fingerprint_saliency_split_mask(mask: object) -> str:
    """Return an exact, deterministic fingerprint for one boolean split mask."""
    array = np.asarray(mask)
    if array.ndim != 1:
        raise SaliencyContextError("Saliency split masks must be one-dimensional.")
    if array.dtype != np.bool_:
        raise SaliencyContextError("Saliency split masks must contain booleans.")
    boolean_mask = np.ascontiguousarray(array, dtype=np.bool_)
    digest = hashlib.sha256()
    digest.update(str(boolean_mask.shape).encode("ascii"))
    digest.update(boolean_mask.tobytes(order="C"))
    return digest.hexdigest()


def fingerprint_saliency_model_state(state: object) -> str:
    """Fingerprint complete model state content with bounded working memory."""
    if not isinstance(state, Mapping) or not state:
        raise SaliencyContextError(
            "Selected model state is unavailable for saliency provenance."
        )
    return _fingerprint_identity_payload(state)


@dataclass(frozen=True, slots=True)
class SaliencyProducerIdentity:
    """Stable dataset/split/run/model identity of one saliency producer."""

    dataset_fingerprint: str
    split_fingerprint: str
    run_fingerprint: str
    model_fingerprint: str
    fingerprint: str = ""
    schema_version: int = SALIENCY_PRODUCER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        component_payload = self._component_payload()
        expected = _fingerprint_identity_payload(component_payload)
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", expected)
        self._validate(expected)

    @classmethod
    def from_components(
        cls,
        *,
        dataset: object,
        split: object,
        run: object,
        model: object,
    ) -> SaliencyProducerIdentity:
        """Build one identity from deterministic, structured producer components."""
        return cls(
            dataset_fingerprint=_fingerprint_identity_payload(dataset),
            split_fingerprint=_fingerprint_identity_payload(split),
            run_fingerprint=_fingerprint_identity_payload(run),
            model_fingerprint=_fingerprint_identity_payload(model),
        )

    def _component_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_fingerprint": self.dataset_fingerprint,
            "split_fingerprint": self.split_fingerprint,
            "run_fingerprint": self.run_fingerprint,
            "model_fingerprint": self.model_fingerprint,
        }

    def _validate(self, expected_fingerprint: str) -> None:
        if self.schema_version != SALIENCY_PRODUCER_SCHEMA_VERSION:
            raise SaliencyContextError(
                f"Unsupported saliency producer schema version {self.schema_version}."
            )
        for label, value in (
            ("dataset", self.dataset_fingerprint),
            ("split", self.split_fingerprint),
            ("run", self.run_fingerprint),
            ("model", self.model_fingerprint),
            ("aggregate", self.fingerprint),
        ):
            if not _is_sha256_fingerprint(value):
                raise SaliencyContextError(
                    f"Saliency {label} provenance fingerprint is malformed."
                )
        if self.fingerprint != expected_fingerprint:
            raise SaliencyContextError(
                "Saliency producer provenance failed its integrity check."
            )

    def to_payload(self) -> dict[str, object]:
        return {**self._component_payload(), "fingerprint": self.fingerprint}

    @classmethod
    def from_payload(cls, payload: object) -> SaliencyProducerIdentity:
        if not isinstance(payload, dict):
            raise SaliencyContextError(
                "Saliency producer provenance is incomplete or malformed."
            )
        try:
            return cls(
                dataset_fingerprint=str(payload["dataset_fingerprint"]),
                split_fingerprint=str(payload["split_fingerprint"]),
                run_fingerprint=str(payload["run_fingerprint"]),
                model_fingerprint=str(payload["model_fingerprint"]),
                fingerprint=str(payload["fingerprint"]),
                schema_version=int(payload["schema_version"]),
            )
        except SaliencyContextError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise SaliencyContextError(
                "Saliency producer provenance is incomplete or malformed."
            ) from exc

    def mismatch_details(
        self,
        current: SaliencyProducerIdentity,
    ) -> tuple[str, ...]:
        differences: list[str] = []
        if self.dataset_fingerprint != current.dataset_fingerprint:
            differences.append("dataset identity")
        if self.split_fingerprint != current.split_fingerprint:
            differences.append("data split")
        if self.run_fingerprint != current.run_fingerprint:
            differences.append("training run")
        if self.model_fingerprint != current.model_fingerprint:
            differences.append("model identity")
        return tuple(differences)


@dataclass(frozen=True, slots=True)
class SaliencyArtifactContext:
    """Immutable EEG identity required to interpret class-indexed saliency."""

    class_map: tuple[tuple[object, str], ...]
    channel_names: tuple[str, ...]
    sampling_frequency_hz: float
    epoch_start_seconds: float
    epoch_end_seconds: float
    epoch_sample_count: int
    montage_fingerprint: str | None
    epoch_data_fingerprint: str
    producer_identity: SaliencyProducerIdentity
    context_fingerprint: str = ""
    schema_version: int = SALIENCY_CONTEXT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        expected_fingerprint = _fingerprint_identity_payload(self._identity_payload())
        if not self.context_fingerprint:
            object.__setattr__(self, "context_fingerprint", expected_fingerprint)
        self._validate_self()
        if self.context_fingerprint != expected_fingerprint:
            raise SaliencyContextError(
                "Saliency identity context failed its integrity check."
            )

    @classmethod
    def from_epoch_data(
        cls,
        epoch_data: Any,
        *,
        class_count: int | None = None,
        producer_identity: SaliencyProducerIdentity,
    ) -> SaliencyArtifactContext:
        """Capture EEG axes and the exact producer identity of active data."""
        if epoch_data is None:
            raise SaliencyContextError("Epoch data is unavailable.")
        if not isinstance(producer_identity, SaliencyProducerIdentity):
            raise SaliencyContextError(
                "Saliency producer provenance is required. Recompute saliency "
                "for the current dataset."
            )

        raw_class_map = getattr(epoch_data, "label_map", None)
        if not isinstance(raw_class_map, dict) or not raw_class_map:
            raise SaliencyContextError("EEG class map is unavailable.")
        class_map = tuple(
            (_plain_identity_value(key), str(name))
            for key, name in raw_class_map.items()
        )
        if class_count is not None and len(class_map) != int(class_count):
            raise SaliencyContextError(
                "EEG class map does not match the trained model output: "
                f"expected {int(class_count)} classes, found {len(class_map)}."
            )
        class_key_tokens = {
            (type(key).__qualname__, repr(key)) for key, _name in class_map
        }
        if len(class_key_tokens) != len(class_map):
            raise SaliencyContextError("EEG class keys must be unique.")
        if len({name for _key, name in class_map}) != len(class_map):
            raise SaliencyContextError("EEG class names must be unique.")

        model_args = _read_epoch_model_args(epoch_data)
        channel_names = _read_channel_names(epoch_data)
        sfreq_value = model_args.get(
            "sfreq",
            getattr(epoch_data, "sfreq", None),
        )
        if sfreq_value is None:
            raise SaliencyContextError("EEG sampling frequency is unavailable.")
        try:
            sfreq = float(sfreq_value)
            sample_count = int(
                model_args.get(
                    "samples",
                    np.asarray(getattr(epoch_data, "data", np.array([]))).shape[-1],
                )
            )
            epoch_start = float(epoch_data.tmin)
        except (IndexError, TypeError, ValueError) as exc:
            raise SaliencyContextError(
                "EEG sampling frequency or epoch window is unavailable."
            ) from exc
        if not math.isfinite(sfreq) or sfreq <= 0:
            raise SaliencyContextError("EEG sampling frequency must be positive.")
        if sample_count <= 0:
            raise SaliencyContextError("EEG epoch sample count must be positive.")
        if not math.isfinite(epoch_start):
            raise SaliencyContextError("EEG epoch start must be finite.")
        epoch_end = epoch_start + (sample_count - 1) / sfreq

        return cls(
            class_map=class_map,
            channel_names=channel_names,
            sampling_frequency_hz=sfreq,
            epoch_start_seconds=epoch_start,
            epoch_end_seconds=epoch_end,
            epoch_sample_count=sample_count,
            montage_fingerprint=_read_montage_fingerprint(epoch_data, channel_names),
            epoch_data_fingerprint=fingerprint_saliency_epoch_data(epoch_data),
            producer_identity=producer_identity,
        )

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "class_map": list(self.class_map),
            "channel_names": list(self.channel_names),
            "sampling_frequency_hz": self.sampling_frequency_hz,
            "epoch_start_seconds": self.epoch_start_seconds,
            "epoch_end_seconds": self.epoch_end_seconds,
            "epoch_sample_count": self.epoch_sample_count,
            "montage_fingerprint": self.montage_fingerprint,
            "epoch_data_fingerprint": self.epoch_data_fingerprint,
            "producer_identity": self.producer_identity.to_payload(),
        }

    def to_payload(self) -> dict[str, Any]:
        """Return a plain serialization payload for ``torch.save``."""
        return {
            **self._identity_payload(),
            "context_fingerprint": self.context_fingerprint,
        }

    @classmethod
    def from_payload(cls, payload: object) -> SaliencyArtifactContext:
        """Validate and reconstruct a serialized context payload."""
        if not isinstance(payload, dict):
            raise SaliencyContextError("Saliency identity context is malformed.")
        try:
            version = int(payload.get("schema_version", 0))
        except (TypeError, ValueError) as exc:
            raise SaliencyContextError(
                "Saliency identity context is incomplete or malformed."
            ) from exc
        if version != SALIENCY_CONTEXT_SCHEMA_VERSION:
            raise SaliencyContextError(
                f"Unsupported saliency identity schema version {version}."
            )
        try:
            class_map = tuple(
                (_plain_identity_value(item[0]), str(item[1]))
                for item in payload["class_map"]
            )
            channel_names = tuple(str(name) for name in payload["channel_names"])
            sfreq = float(payload["sampling_frequency_hz"])
            epoch_start = float(payload["epoch_start_seconds"])
            epoch_end = float(payload["epoch_end_seconds"])
            sample_count = int(payload["epoch_sample_count"])
            montage = payload.get("montage_fingerprint")
            if montage is not None:
                montage = str(montage)
            epoch_data_fingerprint = str(payload["epoch_data_fingerprint"])
            producer_identity = SaliencyProducerIdentity.from_payload(
                payload["producer_identity"]
            )
            context_fingerprint = str(payload["context_fingerprint"])
        except SaliencyContextError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise SaliencyContextError(
                "Saliency identity context is incomplete or malformed."
            ) from exc
        context = cls(
            class_map=class_map,
            channel_names=channel_names,
            sampling_frequency_hz=sfreq,
            epoch_start_seconds=epoch_start,
            epoch_end_seconds=epoch_end,
            epoch_sample_count=sample_count,
            montage_fingerprint=montage,
            epoch_data_fingerprint=epoch_data_fingerprint,
            producer_identity=producer_identity,
            context_fingerprint=context_fingerprint,
            schema_version=version,
        )
        return context

    def _validate_self(self) -> None:
        if self.schema_version != SALIENCY_CONTEXT_SCHEMA_VERSION:
            raise SaliencyContextError(
                f"Unsupported saliency identity schema version {self.schema_version}."
            )
        if not self.class_map:
            raise SaliencyContextError("Saliency class map is empty.")
        class_keys = {
            (type(key).__qualname__, repr(key)) for key, _name in self.class_map
        }
        class_names = {name for _key, name in self.class_map}
        if len(class_keys) != len(self.class_map) or len(class_names) != len(
            self.class_map
        ):
            raise SaliencyContextError("Saliency class keys and names must be unique.")
        if not self.channel_names or len(self.channel_names) != len(
            set(self.channel_names)
        ):
            raise SaliencyContextError("Saliency channel names are empty or ambiguous.")
        if not _is_sha256_fingerprint(self.epoch_data_fingerprint):
            raise SaliencyContextError(
                "Saliency epoch-data provenance fingerprint is malformed."
            )
        if not isinstance(self.producer_identity, SaliencyProducerIdentity):
            raise SaliencyContextError(
                "Saliency producer provenance is incomplete or malformed."
            )
        if not _is_sha256_fingerprint(self.context_fingerprint):
            raise SaliencyContextError(
                "Saliency identity context fingerprint is malformed."
            )
        if (
            not math.isfinite(self.sampling_frequency_hz)
            or self.sampling_frequency_hz <= 0
        ):
            raise SaliencyContextError("Saliency sampling frequency must be positive.")
        if self.epoch_sample_count <= 0:
            raise SaliencyContextError("Saliency epoch sample count must be positive.")
        if not math.isfinite(self.epoch_start_seconds) or not math.isfinite(
            self.epoch_end_seconds
        ):
            raise SaliencyContextError("Saliency epoch window must be finite.")
        expected_end = (
            self.epoch_start_seconds
            + (self.epoch_sample_count - 1) / self.sampling_frequency_hz
        )
        if not math.isclose(
            self.epoch_end_seconds,
            expected_end,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise SaliencyContextError(
                "Saliency epoch window is internally inconsistent."
            )

    def mismatch_details(self, current: SaliencyArtifactContext) -> tuple[str, ...]:
        """Return human-readable identity differences from current epoch data."""
        differences: list[str] = []
        if self.class_map != current.class_map:
            differences.append("class map")
        if self.channel_names != current.channel_names:
            if set(self.channel_names) == set(current.channel_names):
                differences.append("channel order")
            else:
                differences.append("channel names")
        if not math.isclose(
            self.sampling_frequency_hz,
            current.sampling_frequency_hz,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            differences.append("sampling frequency")
        if self.epoch_sample_count != current.epoch_sample_count or not (
            math.isclose(
                self.epoch_start_seconds,
                current.epoch_start_seconds,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                self.epoch_end_seconds,
                current.epoch_end_seconds,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            differences.append("epoch window")
        if self.montage_fingerprint is not None and (
            self.montage_fingerprint != current.montage_fingerprint
        ):
            differences.append("montage")
        if self.epoch_data_fingerprint != current.epoch_data_fingerprint:
            differences.append("dataset content")
        differences.extend(
            self.producer_identity.mismatch_details(current.producer_identity)
        )
        return tuple(differences)
