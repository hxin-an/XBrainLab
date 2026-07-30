from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch

from XBrainLab.backend.training.record.artifact_store import (
    SALIENCY_EXPORT_ARTIFACT_TYPE,
    read_json_npz_artifact,
)
from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training.saliency_provenance import (
    SaliencyArtifactContext,
    SaliencyContextError,
    SaliencyProducerIdentity,
    fingerprint_saliency_model_state,
)


class _EpochContext:
    def __init__(self) -> None:
        self.label_map = {0: "left", 1: "right"}
        self.ch_names = ["C3", "C4"]
        self.sfreq = 100.0
        self.tmin = -0.2
        self.data = np.zeros((4, 2, 51), dtype=np.float32)
        self.channel_position = [(-0.04, 0.0, 0.08), (0.04, 0.0, 0.08)]

    def get_model_args(self) -> dict[str, float | int]:
        return {
            "n_classes": 2,
            "channels": 2,
            "samples": 51,
            "sfreq": 100.0,
        }

    def get_channel_names(self) -> list[str]:
        return list(self.ch_names)

    def get_montage_position(self) -> list[tuple[float, float, float]]:
        return list(self.channel_position)


def _producer_identity(
    *,
    dataset: object = "dataset-a",
    split: object = "split-a",
    run: object = "run-a",
    model: object = "model-a",
) -> SaliencyProducerIdentity:
    return SaliencyProducerIdentity.from_components(
        dataset={"identity": dataset},
        split={"identity": split},
        run={"identity": run},
        model={"identity": model},
    )


def _context(
    epoch_data: _EpochContext,
    *,
    producer_identity: SaliencyProducerIdentity | None = None,
) -> SaliencyArtifactContext:
    return SaliencyArtifactContext.from_epoch_data(
        epoch_data,
        class_count=2,
        producer_identity=producer_identity or _producer_identity(),
    )


def _record(*, context: SaliencyArtifactContext | None) -> EvalRecord:
    saliency = {
        0: np.ones((1, 2, 51), dtype=np.float32),
        1: np.ones((1, 2, 51), dtype=np.float32) * 2,
    }
    return EvalRecord(
        np.array([0, 1]),
        np.array([[0.9, 0.1], [0.1, 0.9]]),
        saliency,
        {},
        {},
        {},
        {},
        saliency_context=context,
    )


def _read_eval_manifest(path: Path) -> dict[str, Any]:
    return json.loads((path / "eval").read_text(encoding="utf-8"))


def _write_eval_manifest(path: Path, manifest: dict[str, Any]) -> None:
    (path / "eval").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def test_eval_record_round_trip_preserves_saliency_identity_context(tmp_path) -> None:
    epoch_data = _EpochContext()
    context = _context(epoch_data)
    record = _record(context=context)

    record.export(str(tmp_path))
    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    loaded_context = loaded.saliency_context
    assert loaded_context == context
    assert loaded_context is not None
    assert loaded.saliency_context_status == "verified"
    assert loaded_context.class_map == ((0, "left"), (1, "right"))
    assert loaded_context.channel_names == ("C3", "C4")
    assert loaded_context.sampling_frequency_hz == 100.0
    assert loaded_context.epoch_start_seconds == -0.2
    assert loaded_context.epoch_end_seconds == 0.3
    assert loaded_context.epoch_sample_count == 51
    assert loaded_context.montage_fingerprint
    assert loaded_context.epoch_data_fingerprint
    assert loaded_context.producer_identity == _producer_identity()
    assert loaded_context.context_fingerprint


def test_legacy_saliency_artifact_is_rejected_as_unsafe(
    tmp_path,
) -> None:
    legacy_payload: dict[str, Any] = {
        "label": np.array([0]),
        "output": np.array([[1.0]]),
        "gradient": {0: np.ones((1, 2, 51), dtype=np.float32)},
        "gradient_input": {},
        "smoothgrad": {},
        "smoothgrad_sq": {},
        "vargrad": {},
    }
    torch.save(legacy_payload, tmp_path / "eval")

    with pytest.raises(
        RuntimeError,
        match=r"(?i)unsupported legacy evaluation record.*start a new evaluation",
    ):
        EvalRecord.load(str(tmp_path))


def test_runtime_context_binds_once_and_rejects_later_channel_reordering() -> None:
    epoch_data = _EpochContext()
    record = _record(context=None)

    bound = record.bind_saliency_context(
        epoch_data,
        producer_identity=_producer_identity(),
    )
    epoch_data.ch_names = ["C4", "C3"]

    assert record.saliency_context == bound
    with pytest.raises(SaliencyContextError, match="channel order"):
        record.bind_saliency_context(epoch_data)


def test_runtime_context_validation_never_binds_missing_identity() -> None:
    epoch_data = _EpochContext()
    record = _record(context=None)

    with pytest.raises(SaliencyContextError, match="not bound"):
        record.validate_saliency_context(epoch_data)

    assert record.saliency_context is None


def test_standalone_saliency_export_contains_identity_envelope(tmp_path) -> None:
    epoch_data = _EpochContext()
    context = _context(epoch_data)
    record = _record(context=context)
    target = tmp_path / "gradient.pt"

    record.export_saliency("Gradient", target_path=str(target))
    artifact, arrays = read_json_npz_artifact(
        target,
        expected_artifact_type=SALIENCY_EXPORT_ARTIFACT_TYPE,
    )

    assert artifact["artifact_schema_version"] == 3
    assert artifact["method"] == "Gradient"
    assert SaliencyArtifactContext.from_payload(artifact["saliency_context"]) == context
    assert artifact["saliency_integrity_manifest"]["manifest_sha256"]
    entries = artifact["saliency_arrays"]
    assert isinstance(entries, list)
    assert {entry["class_index"] for entry in entries} == {0, 1}
    for entry in entries:
        np.testing.assert_array_equal(
            arrays[entry["array"]],
            record.gradient[entry["class_index"]],
        )


def test_standalone_saliency_export_fails_closed_without_identity() -> None:
    with pytest.raises(SaliencyContextError, match="cannot be persisted"):
        _record(context=None).export_saliency("Gradient")


def test_producer_identity_is_stable_for_equivalent_component_order() -> None:
    first = SaliencyProducerIdentity.from_components(
        dataset={"shape": [4, 2, 51], "dtype": "float32"},
        split={"test": "abc", "train": "def"},
        run={"repeat": 0, "seed": 7},
        model={"name": "EEGNet", "params": {"dropout": 0.5, "kern": 64}},
    )
    second = SaliencyProducerIdentity.from_components(
        dataset={"dtype": "float32", "shape": [4, 2, 51]},
        split={"train": "def", "test": "abc"},
        run={"seed": 7, "repeat": 0},
        model={"params": {"kern": 64, "dropout": 0.5}, "name": "EEGNet"},
    )

    assert first == second
    assert first.fingerprint == second.fingerprint


def test_model_state_fingerprint_handles_noncontiguous_tensors() -> None:
    weight = torch.nn.Linear(6, 4, bias=False).weight.detach().transpose(0, 1)
    assert weight.is_contiguous() is False

    first = fingerprint_saliency_model_state({"weight": weight})
    second = fingerprint_saliency_model_state({"weight": weight})
    weight[0, 0] += 1.0
    changed = fingerprint_saliency_model_state({"weight": weight})

    assert first == second
    assert changed != first


@pytest.mark.parametrize(
    ("component", "expected_detail"),
    [
        ("dataset", "dataset identity"),
        ("split", "data split"),
        ("run", "training run"),
        ("model", "model identity"),
    ],
)
def test_validation_rejects_each_producer_identity_mismatch(
    component: str,
    expected_detail: str,
) -> None:
    epoch_data = _EpochContext()
    record = _record(context=_context(epoch_data))
    changed = {component: f"{component}-b"}

    with pytest.raises(
        SaliencyContextError,
        match=rf"{expected_detail}.*Recompute saliency",
    ):
        record.validate_saliency_context(
            epoch_data,
            producer_identity=_producer_identity(**changed),
        )


@pytest.mark.parametrize(
    ("component", "expected_detail"),
    [
        ("dataset", "dataset identity"),
        ("split", "data split"),
        ("run", "training run"),
        ("model", "model identity"),
    ],
)
def test_load_rejects_expected_producer_mismatch_without_losing_metrics(
    tmp_path,
    component: str,
    expected_detail: str,
) -> None:
    epoch_data = _EpochContext()
    _record(context=_context(epoch_data)).export(str(tmp_path))
    changed = {component: f"{component}-b"}

    loaded = EvalRecord.load(
        str(tmp_path),
        expected_producer_identity=_producer_identity(**changed),
    )

    assert loaded is not None
    assert loaded.saliency_context_status == "incompatible"
    assert expected_detail in (loaded.saliency_recompute_reason or "")
    np.testing.assert_array_equal(loaded.label, np.array([0, 1]))
    with pytest.raises(SaliencyContextError, match=expected_detail):
        loaded.get_gradient(0)


def test_legacy_context_schema_artifact_is_rejected_as_unsafe(
    tmp_path,
) -> None:
    epoch_data = _EpochContext()
    legacy_context = _context(epoch_data).to_payload()
    legacy_context["schema_version"] = 1
    legacy_context.pop("producer_identity")
    legacy_context.pop("epoch_data_fingerprint")
    legacy_context.pop("context_fingerprint")
    payload = {
        "artifact_schema_version": 2,
        "label": np.array([0, 1]),
        "output": np.array([[0.9, 0.1], [0.1, 0.9]]),
        "gradient": {0: np.ones((1, 2, 51), dtype=np.float32)},
        "gradient_input": {},
        "smoothgrad": {},
        "smoothgrad_sq": {},
        "vargrad": {},
        "saliency_context": legacy_context,
    }
    torch.save(payload, tmp_path / "eval")

    with pytest.raises(
        RuntimeError,
        match=r"(?i)unsupported legacy evaluation record.*start a new evaluation",
    ):
        EvalRecord.load(str(tmp_path))


def test_previous_bounded_hash_artifact_keeps_metrics_but_saliency_fails_closed(
    tmp_path,
) -> None:
    epoch_data = _EpochContext()
    _record(context=_context(epoch_data)).export(str(tmp_path))
    manifest = _read_eval_manifest(tmp_path)
    payload = manifest["payload"]
    payload["saliency_context"]["schema_version"] = 2
    payload["saliency_context"]["producer_identity"]["schema_version"] = 1
    _write_eval_manifest(tmp_path, manifest)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    np.testing.assert_array_equal(loaded.label, np.array([0, 1]))
    assert loaded.saliency_context_status == "incompatible"
    assert "schema version 2" in (loaded.saliency_recompute_reason or "")
    with pytest.raises(SaliencyContextError, match=r"schema version 2"):
        loaded.get_gradient(0)


def test_current_schema_missing_producer_field_fails_closed(tmp_path) -> None:
    epoch_data = _EpochContext()
    _record(context=_context(epoch_data)).export(str(tmp_path))
    manifest = _read_eval_manifest(tmp_path)
    manifest["payload"]["saliency_context"].pop("producer_identity")
    _write_eval_manifest(tmp_path, manifest)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    assert loaded.saliency_context_status == "incompatible"
    assert "incomplete" in (loaded.saliency_recompute_reason or "").lower()


def test_tampered_context_fingerprint_fails_closed(tmp_path) -> None:
    epoch_data = _EpochContext()
    _record(context=_context(epoch_data)).export(str(tmp_path))
    manifest = _read_eval_manifest(tmp_path)
    manifest["payload"]["saliency_context"]["epoch_data_fingerprint"] = "f" * 64
    _write_eval_manifest(tmp_path, manifest)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    assert loaded.saliency_context_status == "incompatible"
    assert "integrity" in (loaded.saliency_recompute_reason or "").lower()


def test_tampered_producer_fingerprint_fails_closed(tmp_path) -> None:
    epoch_data = _EpochContext()
    _record(context=_context(epoch_data)).export(str(tmp_path))
    manifest = _read_eval_manifest(tmp_path)
    manifest["payload"]["saliency_context"]["producer_identity"][
        "model_fingerprint"
    ] = "f" * 64
    _write_eval_manifest(tmp_path, manifest)

    loaded = EvalRecord.load(str(tmp_path))

    assert loaded is not None
    assert loaded.saliency_context_status == "incompatible"
    assert "integrity" in (loaded.saliency_recompute_reason or "").lower()
    with pytest.raises(SaliencyContextError, match=r"integrity.*Recompute saliency"):
        loaded.get_gradient(0)
