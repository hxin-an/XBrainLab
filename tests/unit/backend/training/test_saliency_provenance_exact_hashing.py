from __future__ import annotations

from typing import Any

import numpy as np
import pytest
import torch

from XBrainLab.backend.training import saliency_provenance as provenance
from XBrainLab.backend.training.saliency_provenance import (
    SALIENCY_CONTEXT_SCHEMA_VERSION,
    SALIENCY_PRODUCER_SCHEMA_VERSION,
    SaliencyArtifactContext,
    SaliencyContextError,
    SaliencyProducerIdentity,
    fingerprint_saliency_epoch_data,
    fingerprint_saliency_model_state,
)


class _EpochFingerprintFixture:
    def __init__(self) -> None:
        self.data = np.arange(4000, dtype=np.float32).reshape(1000, 2, 2)
        self.label = np.arange(1000, dtype=np.int64)
        self.subject = np.zeros(1000, dtype=np.int64)
        self.session = np.zeros(1000, dtype=np.int64)
        self.idx = np.arange(1000, dtype=np.int64)
        self.trial_group = np.arange(1000, dtype=np.int64)
        self.label_map = {0: "left", 1: "right"}
        self.subject_map = {0: "subject"}
        self.session_map = {0: "session"}
        self.ch_names = ["C3", "C4"]
        self.sfreq = 100.0
        self.tmin = 0.0
        self.epoch_window_provenance: tuple[object, ...] = ()


class _NoWholeArrayMaterialization(np.ndarray):
    def tobytes(self, *args: Any, **kwargs: Any) -> bytes:
        raise AssertionError("fingerprinting materialized the complete NumPy array")

    def flatten(self, *args: Any, **kwargs: Any) -> np.ndarray:
        raise AssertionError("fingerprinting flattened the complete NumPy array")

    def ravel(self, *args: Any, **kwargs: Any) -> np.ndarray:
        raise AssertionError("fingerprinting raveled the complete NumPy array")

    def copy(self, *args: Any, **kwargs: Any) -> np.ndarray:
        raise AssertionError("fingerprinting copied the complete NumPy array")


class _FakeCudaTensor(torch.Tensor):
    """CPU-backed tensor that exercises CUDA transfer logic without a GPU."""

    transferred_bytes: list[int] | None = None

    @staticmethod
    def __new__(cls, value: torch.Tensor) -> _FakeCudaTensor:
        return torch.Tensor._make_subclass(  # pyright: ignore[reportPrivateUsage]
            cls,
            value,
            value.requires_grad,
        )

    @property
    def device(self) -> torch.device:
        return torch.device("cuda")

    def to(self, *args: Any, **kwargs: Any) -> torch.Tensor:
        device = kwargs.get("device", args[0] if args else None)
        if device is not None and torch.device(device).type == "cpu":
            if self.transferred_bytes is not None:
                self.transferred_bytes.append(self.numel() * self.element_size())
            return self.as_subclass(torch.Tensor)
        return super().to(*args, **kwargs)


def _producer_identity() -> SaliencyProducerIdentity:
    return SaliencyProducerIdentity.from_components(
        dataset={"name": "exact-content"},
        split={"name": "exact-content"},
        run={"name": "exact-content"},
        model={"name": "exact-content"},
    )


def _torch_arange(count: int, *, dtype_name: str) -> torch.Tensor:
    return torch.arange(  # pyright: ignore[reportPrivateImportUsage]
        count,
        dtype=getattr(torch, dtype_name),
    )


def test_exact_content_contract_bumps_context_and_producer_schemas() -> None:
    assert SALIENCY_CONTEXT_SCHEMA_VERSION == 3
    assert SALIENCY_PRODUCER_SCHEMA_VERSION == 2


def test_model_fingerprint_changes_outside_old_sentinel_indices() -> None:
    weight = _torch_arange(1000, dtype_name="float32")
    original = fingerprint_saliency_model_state({"weight": weight})

    weight[1] += 1.0

    assert fingerprint_saliency_model_state({"weight": weight}) != original


def test_model_fingerprint_rejects_ambiguous_normalized_keys() -> None:
    with pytest.raises(SaliencyContextError, match="ambiguous mapping keys"):
        fingerprint_saliency_model_state(
            {
                1: _torch_arange(4, dtype_name="float32"),
                "1": _torch_arange(4, dtype_name="float32") + 10,
            }
        )


@pytest.mark.parametrize("attribute", ["data", "label"])
def test_epoch_fingerprint_changes_outside_old_sentinel_indices(
    attribute: str,
) -> None:
    epoch_data = _EpochFingerprintFixture()
    original = fingerprint_saliency_epoch_data(epoch_data)

    getattr(epoch_data, attribute).flat[1] += 1

    assert fingerprint_saliency_epoch_data(epoch_data) != original


def test_noncontiguous_numpy_array_matches_same_logical_content() -> None:
    source = np.arange(1200, dtype=np.float64).reshape(30, 40)
    noncontiguous = source.T
    contiguous = np.array(noncontiguous, order="C", copy=True)
    assert not noncontiguous.flags.c_contiguous

    expected = fingerprint_saliency_model_state({"weight": contiguous})

    assert fingerprint_saliency_model_state({"weight": noncontiguous}) == expected
    noncontiguous[1, 1] += 1.0
    assert fingerprint_saliency_model_state({"weight": noncontiguous}) != expected


def test_noncontiguous_cpu_tensor_matches_same_logical_content() -> None:
    source = _torch_arange(1200, dtype_name="float64").reshape(30, 40)
    noncontiguous = source.transpose(0, 1)
    contiguous = noncontiguous.contiguous()
    assert not noncontiguous.is_contiguous()

    expected = fingerprint_saliency_model_state({"weight": contiguous})

    assert fingerprint_saliency_model_state({"weight": noncontiguous}) == expected
    noncontiguous[1, 1] += 1.0
    assert fingerprint_saliency_model_state({"weight": noncontiguous}) != expected


def test_noncontiguous_cuda_tensor_matches_cpu_logical_content() -> None:
    cpu_source = _torch_arange(1200, dtype_name="float32").reshape(30, 40)
    cpu_noncontiguous = cpu_source.transpose(0, 1)
    fake_cuda_noncontiguous = _FakeCudaTensor(cpu_noncontiguous)
    assert not fake_cuda_noncontiguous.is_contiguous()

    expected = fingerprint_saliency_model_state({"weight": cpu_noncontiguous})

    assert (
        fingerprint_saliency_model_state({"weight": fake_cuda_noncontiguous})
        == expected
    )
    fake_cuda_noncontiguous[1, 1] += 1.0
    assert (
        fingerprint_saliency_model_state({"weight": fake_cuda_noncontiguous})
        != expected
    )


def test_cuda_hashing_transfers_only_bounded_chunks(monkeypatch) -> None:
    chunk_bytes = 64
    source = _torch_arange(4096, dtype_name="float32").reshape(64, 64)
    seen_transfer_bytes: list[int] = []
    source = _FakeCudaTensor(source.transpose(0, 1))

    monkeypatch.setattr(provenance, "_ARRAY_HASH_CHUNK_BYTES", chunk_bytes)
    monkeypatch.setattr(_FakeCudaTensor, "transferred_bytes", seen_transfer_bytes)

    fingerprint_saliency_model_state({"weight": source})

    assert len(seen_transfer_bytes) > 1
    assert max(seen_transfer_bytes) <= chunk_bytes


def test_numpy_hashing_materializes_only_bounded_chunks(monkeypatch) -> None:
    chunk_bytes = 64
    source = np.arange(4096, dtype=np.float32).reshape(64, 64).T
    guarded = source.view(_NoWholeArrayMaterialization)
    seen_chunk_bytes: list[int] = []
    original_chunk_view = provenance._numpy_chunk_as_byte_view

    def checked_chunk_view(chunk: np.ndarray) -> memoryview:
        seen_chunk_bytes.append(int(chunk.nbytes))
        assert chunk.nbytes <= chunk_bytes
        return original_chunk_view(chunk)

    monkeypatch.setattr(provenance, "_ARRAY_HASH_CHUNK_BYTES", chunk_bytes)
    monkeypatch.setattr(
        provenance,
        "_numpy_chunk_as_byte_view",
        checked_chunk_view,
    )

    fingerprint_saliency_model_state({"weight": guarded})

    assert len(seen_chunk_bytes) > 1
    assert max(seen_chunk_bytes) <= chunk_bytes


def test_torch_hashing_materializes_only_bounded_chunks(monkeypatch) -> None:
    chunk_bytes = 64
    source = _torch_arange(4096, dtype_name="float32").reshape(64, 64)
    source = source.transpose(0, 1)
    seen_chunk_bytes: list[int] = []
    original_chunk_view = provenance._torch_chunk_as_byte_view
    original_contiguous = torch.Tensor.contiguous
    original_numpy = torch.Tensor.numpy
    original_reshape = torch.Tensor.reshape

    def checked_chunk_view(chunk: torch.Tensor) -> memoryview:
        size_bytes = chunk.numel() * chunk.element_size()
        seen_chunk_bytes.append(size_bytes)
        assert size_bytes <= chunk_bytes
        return original_chunk_view(chunk)

    def guarded_contiguous(tensor: torch.Tensor, *args: Any, **kwargs: Any):
        assert tensor.numel() * tensor.element_size() <= chunk_bytes
        return original_contiguous(tensor, *args, **kwargs)

    def guarded_numpy(tensor: torch.Tensor, *args: Any, **kwargs: Any):
        assert tensor.numel() <= chunk_bytes
        return original_numpy(tensor, *args, **kwargs)

    def guarded_reshape(tensor: torch.Tensor, *args: Any, **kwargs: Any):
        assert tensor.numel() * tensor.element_size() <= chunk_bytes
        return original_reshape(tensor, *args, **kwargs)

    monkeypatch.setattr(provenance, "_ARRAY_HASH_CHUNK_BYTES", chunk_bytes)
    monkeypatch.setattr(provenance, "_torch_chunk_as_byte_view", checked_chunk_view)
    monkeypatch.setattr(torch.Tensor, "contiguous", guarded_contiguous)
    monkeypatch.setattr(torch.Tensor, "numpy", guarded_numpy)
    monkeypatch.setattr(torch.Tensor, "reshape", guarded_reshape)

    fingerprint_saliency_model_state({"weight": source})

    assert len(seen_chunk_bytes) > 1
    assert max(seen_chunk_bytes) <= chunk_bytes


def test_previous_bounded_hash_schemas_fail_closed() -> None:
    epoch_data = _EpochFingerprintFixture()
    context = SaliencyArtifactContext.from_epoch_data(
        epoch_data,
        class_count=2,
        producer_identity=_producer_identity(),
    )
    previous_context_payload = context.to_payload()
    previous_context_payload["schema_version"] = 2
    previous_producer_payload = context.producer_identity.to_payload()
    previous_producer_payload["schema_version"] = 1

    with pytest.raises(SaliencyContextError, match="schema version 2"):
        SaliencyArtifactContext.from_payload(previous_context_payload)
    with pytest.raises(SaliencyContextError, match="schema version 1"):
        SaliencyProducerIdentity.from_payload(previous_producer_payload)
