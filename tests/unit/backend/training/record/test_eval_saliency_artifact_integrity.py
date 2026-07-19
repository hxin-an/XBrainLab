from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
import torch

from XBrainLab.backend.training import saliency_provenance as provenance
from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training.saliency_artifact_integrity import (
    SALIENCY_ARTIFACT_MANIFEST_SCHEMA_VERSION,
    SaliencyArtifactIntegrityError,
    SaliencyIntegrityReason,
    build_saliency_artifact_manifest,
)
from XBrainLab.backend.training.saliency_provenance import (
    SaliencyArtifactContext,
    SaliencyProducerIdentity,
)

AttributionPayload = np.ndarray | torch.Tensor


def _context() -> SaliencyArtifactContext:
    producer = SaliencyProducerIdentity.from_components(
        dataset={"identity": "dataset"},
        split={"identity": "test"},
        run={"identity": "run-1"},
        model={"identity": "model-1"},
    )
    return SaliencyArtifactContext(
        class_map=((0, "left"), (1, "right")),
        channel_names=("C3", "C4"),
        sampling_frequency_hz=100.0,
        epoch_start_seconds=0.0,
        epoch_end_seconds=0.01,
        epoch_sample_count=2,
        montage_fingerprint=None,
        epoch_data_fingerprint=producer.dataset_fingerprint,
        producer_identity=producer,
    )


def _record(
    *,
    gradient: dict[int, AttributionPayload] | None = None,
    gradient_input: dict[int, AttributionPayload] | None = None,
    smoothgrad: dict[int, AttributionPayload] | None = None,
    saliency_method_parameters: dict[str, object] | None = None,
    saliency_noise_seeds: dict[str, object] | None = None,
) -> EvalRecord:
    default_gradient: dict[int, AttributionPayload] = {
        0: np.arange(40, dtype=np.float32).reshape(10, 2, 2),
        1: np.arange(40, 80, dtype=np.float32).reshape(10, 2, 2),
    }
    selected_gradient = default_gradient if gradient is None else gradient
    selected_gradient_input = (
        {class_index: values + 100 for class_index, values in default_gradient.items()}
        if gradient_input is None
        else gradient_input
    )
    return EvalRecord(
        label=np.array([0, 1]),
        output=np.array([[0.9, 0.1], [0.1, 0.9]]),
        gradient=selected_gradient,
        gradient_input=selected_gradient_input,
        smoothgrad=smoothgrad or {},
        smoothgrad_sq={},
        vargrad={},
        saliency_context=_context(),
        saliency_method_parameters=saliency_method_parameters,
        saliency_noise_seeds=saliency_noise_seeds,
    )


def _saved_payload(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    _record().export(str(tmp_path))
    path = tmp_path / "eval"
    return path, cast(dict[str, Any], torch.load(path, weights_only=False))


def test_load_rejects_attribution_mutation_outside_old_sentinels(
    tmp_path: Path,
) -> None:
    path, payload = _saved_payload(tmp_path)
    payload["gradient"][0].flat[1] += 1.0
    torch.save(payload, path)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    assert loaded.saliency_context_status == "incompatible"
    assert loaded.saliency_recompute_reason is not None
    assert "payload" in loaded.saliency_recompute_reason.lower()
    assert loaded.saliency_integrity_reason is SaliencyIntegrityReason.PAYLOAD_MUTATION
    assert loaded.saliency_integrity_diagnostics[0].class_index == 0
    np.testing.assert_array_equal(loaded.label, np.array([0, 1]))


def test_load_rejects_method_store_swap(tmp_path: Path) -> None:
    path, payload = _saved_payload(tmp_path)
    payload["gradient"], payload["gradient_input"] = (
        payload["gradient_input"],
        payload["gradient"],
    )
    torch.save(payload, path)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    assert loaded.saliency_context_status == "incompatible"
    assert loaded.saliency_recompute_reason is not None
    assert "method" in loaded.saliency_recompute_reason.lower()
    assert loaded.saliency_integrity_reason is SaliencyIntegrityReason.METHOD_MISMATCH


def test_round_trip_verifies_every_method_class_entry(tmp_path: Path) -> None:
    record = _record()
    expected_manifest = record.saliency_integrity_manifest
    record.export(str(tmp_path))

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    assert loaded.saliency_context_status == "verified"
    assert loaded.saliency_integrity_reason is None
    assert loaded.saliency_integrity_manifest == expected_manifest
    assert loaded.saliency_integrity_manifest is not None
    manifest = cast(dict[str, Any], loaded.saliency_integrity_manifest)
    assert len(manifest["entries"]) == 4
    np.testing.assert_array_equal(loaded.get_gradient(1), record.gradient[1])


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda payload: payload["saliency_method_parameters"].__setitem__(
                "Gradient", {"stdevs": 0.5}
            ),
            SaliencyIntegrityReason.PARAMETER_MISMATCH,
        ),
        (
            lambda payload: payload["saliency_integrity_manifest"]["entries"][0][
                "target"
            ].__setitem__("class_name", "wrong-target"),
            SaliencyIntegrityReason.TARGET_MISMATCH,
        ),
        (
            lambda payload: payload["saliency_integrity_manifest"].__setitem__(
                "manifest_sha256", "f" * 64
            ),
            SaliencyIntegrityReason.MANIFEST_TAMPERED,
        ),
        (
            lambda payload: payload["saliency_integrity_manifest"]["entries"][
                0
            ].__setitem__("schema_version", 0),
            SaliencyIntegrityReason.UNSUPPORTED_SCHEMA,
        ),
        (
            lambda payload: payload["saliency_integrity_manifest"][
                "runtime_contract"
            ].__setitem__("schema_version", 0),
            SaliencyIntegrityReason.RUNTIME_CONTRACT_MISMATCH,
        ),
    ],
)
def test_load_reports_typed_manifest_mismatch(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    reason: SaliencyIntegrityReason,
) -> None:
    path, payload = _saved_payload(tmp_path)
    mutation(payload)
    torch.save(payload, path)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    assert loaded.saliency_context_status == "incompatible"
    assert loaded.saliency_integrity_reason is reason


def test_load_rejects_missing_manifest_as_legacy_but_keeps_metrics(
    tmp_path: Path,
) -> None:
    path, payload = _saved_payload(tmp_path)
    payload.pop("saliency_integrity_manifest")
    torch.save(payload, path)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    assert loaded.saliency_integrity_reason is SaliencyIntegrityReason.MISSING_MANIFEST
    np.testing.assert_array_equal(loaded.output, _record().output)


def test_load_rejects_unsupported_manifest_schema(tmp_path: Path) -> None:
    path, payload = _saved_payload(tmp_path)
    payload["saliency_integrity_manifest"]["schema_version"] = 0
    torch.save(payload, path)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    assert (
        loaded.saliency_integrity_reason is SaliencyIntegrityReason.UNSUPPORTED_SCHEMA
    )


def test_load_rejects_partial_class_store(tmp_path: Path) -> None:
    path, payload = _saved_payload(tmp_path)
    payload["gradient"].pop(1)
    torch.save(payload, path)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    assert loaded.saliency_integrity_reason is SaliencyIntegrityReason.PARTIAL_COVERAGE


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (
            np.array([[[1.0, np.nan]]], dtype=np.float32),
            SaliencyIntegrityReason.NON_FINITE_PAYLOAD,
        ),
        (
            np.array([[[1, 2]]], dtype=np.int64),
            SaliencyIntegrityReason.UNSUPPORTED_DTYPE,
        ),
    ],
)
def test_runtime_publication_rejects_invalid_payload_values(
    payload: np.ndarray,
    reason: SaliencyIntegrityReason,
) -> None:
    gradient: dict[int, AttributionPayload] = {
        0: payload,
        1: np.ones_like(payload),
    }

    with pytest.raises(SaliencyArtifactIntegrityError) as error:
        _record(gradient=gradient, gradient_input={})

    assert error.value.reason is reason


def test_runtime_publication_rejects_partial_class_store() -> None:
    with pytest.raises(SaliencyArtifactIntegrityError) as error:
        _record(
            gradient={0: np.ones((1, 2, 2), dtype=np.float32)},
            gradient_input={},
        )

    assert error.value.reason is SaliencyIntegrityReason.PARTIAL_COVERAGE


def test_noncontiguous_numpy_and_torch_payloads_share_logical_identity() -> None:
    numpy_source = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
    numpy_noncontiguous = numpy_source.transpose(0, 2, 1)
    torch_source = torch.arange(  # pyright: ignore[reportPrivateImportUsage]
        24,
        dtype=torch.float32,  # pyright: ignore[reportPrivateImportUsage]
    ).reshape(2, 3, 4)
    torch_noncontiguous = torch_source.transpose(1, 2)
    numpy_contiguous = np.ascontiguousarray(numpy_noncontiguous)
    torch_contiguous = torch_noncontiguous.contiguous()
    assert not numpy_noncontiguous.flags.c_contiguous
    assert not torch_noncontiguous.is_contiguous()

    numpy_manifest = build_saliency_artifact_manifest(
        {
            "Gradient": {
                0: numpy_noncontiguous,
                1: numpy_noncontiguous + 1,
            }
        },
        context=_context(),
        method_parameters={"Gradient": {}},
        noise_seeds={},
        runtime_contract={"schema_version": 1, "runtime": "test"},
    )
    torch_manifest = build_saliency_artifact_manifest(
        {
            "Gradient": {
                0: torch_noncontiguous,
                1: torch_noncontiguous + 1,
            }
        },
        context=_context(),
        method_parameters={"Gradient": {}},
        noise_seeds={},
        runtime_contract={"schema_version": 1, "runtime": "test"},
    )
    numpy_contiguous_manifest = build_saliency_artifact_manifest(
        {
            "Gradient": {
                0: numpy_contiguous,
                1: numpy_contiguous + 1,
            }
        },
        context=_context(),
        method_parameters={"Gradient": {}},
        noise_seeds={},
        runtime_contract={"schema_version": 1, "runtime": "test"},
    )
    torch_contiguous_manifest = build_saliency_artifact_manifest(
        {
            "Gradient": {
                0: torch_contiguous,
                1: torch_contiguous + 1,
            }
        },
        context=_context(),
        method_parameters={"Gradient": {}},
        noise_seeds={},
        runtime_contract={"schema_version": 1, "runtime": "test"},
    )

    numpy_manifest_payload = cast(dict[str, Any], numpy_manifest)
    torch_manifest_payload = cast(dict[str, Any], torch_manifest)
    numpy_contiguous_payload = cast(dict[str, Any], numpy_contiguous_manifest)
    torch_contiguous_payload = cast(dict[str, Any], torch_contiguous_manifest)
    numpy_entries = numpy_manifest_payload["entries"]
    torch_entries = torch_manifest_payload["entries"]
    assert (
        numpy_entries[0]["identity_sha256"]
        == numpy_contiguous_payload["entries"][0]["identity_sha256"]
    )
    assert (
        torch_entries[0]["identity_sha256"]
        == torch_contiguous_payload["entries"][0]["identity_sha256"]
    )


def test_noise_manifest_covers_effective_parameters_seed_and_runtime_contract() -> None:
    smoothgrad: dict[int, AttributionPayload] = {
        0: np.ones((1, 2, 2), dtype=np.float32),
        1: np.ones((1, 2, 2), dtype=np.float32) * 2,
    }
    record = _record(
        gradient={},
        gradient_input={},
        smoothgrad=smoothgrad,
        saliency_method_parameters={
            "SmoothGrad": {
                "nt_samples": 7,
                "nt_samples_batch_size": 2,
                "stdevs": 0.25,
            }
        },
        saliency_noise_seeds={"SmoothGrad": 1234},
    )

    assert record.saliency_integrity_manifest is not None
    manifest = cast(dict[str, Any], record.saliency_integrity_manifest)
    assert manifest["schema_version"] == SALIENCY_ARTIFACT_MANIFEST_SCHEMA_VERSION
    assert manifest["noise_seeds"] == {"SmoothGrad": 1234}
    assert manifest["method_parameters"]["SmoothGrad"]["stdevs"] == 0.25
    assert manifest["runtime_contract"]["torch_version"]
    assert manifest["runtime_contract"]["captum_version"]
    assert all(entry["noise_seed"] == 1234 for entry in manifest["entries"])
    assert all(
        entry["producer_contract"]["producer_fingerprint"]
        == _context().producer_identity.fingerprint
        for entry in manifest["entries"]
    )


def test_load_rejects_noise_seed_mismatch(tmp_path: Path) -> None:
    smoothgrad: dict[int, AttributionPayload] = {
        0: np.ones((1, 2, 2), dtype=np.float32),
        1: np.ones((1, 2, 2), dtype=np.float32) * 2,
    }
    record = _record(
        gradient={},
        gradient_input={},
        smoothgrad=smoothgrad,
        saliency_method_parameters={"SmoothGrad": {}},
        saliency_noise_seeds={"SmoothGrad": 1234},
    )
    record.export(str(tmp_path))
    path = tmp_path / "eval"
    payload = cast(dict[str, Any], torch.load(path, weights_only=False))
    payload["saliency_noise_seeds"]["SmoothGrad"] = 5678
    torch.save(payload, path)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    assert (
        loaded.saliency_integrity_reason is SaliencyIntegrityReason.NOISE_SEED_MISMATCH
    )


def test_noise_payload_without_seed_fails_closed_before_publication() -> None:
    smoothgrad: dict[int, AttributionPayload] = {
        0: np.ones((1, 2, 2), dtype=np.float32),
        1: np.ones((1, 2, 2), dtype=np.float32) * 2,
    }

    with pytest.raises(SaliencyArtifactIntegrityError) as error:
        _record(
            gradient={},
            gradient_input={},
            smoothgrad=smoothgrad,
            saliency_method_parameters={"SmoothGrad": {}},
        )

    assert error.value.reason is SaliencyIntegrityReason.NOISE_SEED_MISMATCH


def test_untrusted_parameter_object_keeps_metrics_but_closes_saliency(
    tmp_path: Path,
) -> None:
    path, payload = _saved_payload(tmp_path)
    payload["saliency_method_parameters"]["Gradient"] = {"value": object()}
    torch.save(payload, path)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    np.testing.assert_array_equal(loaded.label, np.array([0, 1]))
    assert (
        loaded.saliency_integrity_reason is SaliencyIntegrityReason.PARAMETER_MISMATCH
    )


def test_payload_manifest_uses_bounded_exact_hash_chunks(monkeypatch) -> None:
    chunk_bytes = 64
    source = np.arange(4096, dtype=np.float32).reshape(64, 64).T
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

    build_saliency_artifact_manifest(
        {"Gradient": {0: source, 1: source + 1}},
        context=_context(),
        method_parameters={"Gradient": {}},
        noise_seeds={},
        runtime_contract={"schema_version": 1, "runtime": "test"},
    )

    assert len(seen_chunk_bytes) > 2
    assert max(seen_chunk_bytes) <= chunk_bytes
