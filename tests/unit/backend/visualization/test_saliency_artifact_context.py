from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast
from unittest.mock import patch

import numpy as np
import pytest

from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training.saliency_provenance import (
    SaliencyArtifactContext,
    SaliencyContextError,
    SaliencyProducerIdentity,
)
from XBrainLab.backend.visualization.base import Visualizer
from XBrainLab.backend.visualization.saliency_3d_engine import Saliency3DEngine


class _EpochContext:
    def __init__(self) -> None:
        self.label_map = {0: "left", 1: "right"}
        self.event_id = {"left": 0, "right": 1}
        self.ch_names = ["C3", "C4"]
        self.sfreq = 100.0
        self.tmin = -0.2
        self.data = np.zeros((4, 2, 51), dtype=np.float32)
        self.channel_position = [(-0.04, 0.0, 0.08), (0.04, 0.0, 0.08)]

    def get_model_args(self) -> dict[str, float | int]:
        return {
            "n_classes": 2,
            "channels": len(self.ch_names),
            "samples": self.data.shape[-1],
            "sfreq": self.sfreq,
        }

    def get_channel_names(self) -> list[str]:
        return list(self.ch_names)

    def get_montage_position(self) -> list[tuple[float, float, float]]:
        return list(self.channel_position)


def _record(epoch_data: _EpochContext) -> EvalRecord:
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
        saliency_context=SaliencyArtifactContext.from_epoch_data(
            epoch_data,
            class_count=2,
            producer_identity=SaliencyProducerIdentity.from_components(
                dataset={"name": "visualizer"},
                split={"name": "visualizer"},
                run={"name": "visualizer"},
                model={"name": "visualizer"},
            ),
        ),
    )


@pytest.mark.parametrize(
    ("mutate", "expected_detail"),
    [
        (
            lambda epoch: setattr(epoch, "label_map", {0: "right", 1: "left"}),
            "class map",
        ),
        (
            lambda epoch: setattr(epoch, "ch_names", ["C4", "C3"]),
            "channel order",
        ),
        (
            lambda epoch: setattr(epoch, "sfreq", 200.0),
            "sampling frequency",
        ),
        (
            lambda epoch: setattr(epoch, "tmin", -0.1),
            "epoch window",
        ),
        (
            lambda epoch: setattr(
                epoch,
                "channel_position",
                [(-0.05, 0.0, 0.08), (0.05, 0.0, 0.08)],
            ),
            "montage",
        ),
    ],
)
def test_visualizer_rejects_context_drift_instead_of_rebinding_indices(
    mutate: Callable[[_EpochContext], None],
    expected_detail: str,
) -> None:
    epoch_data = _EpochContext()
    record = _record(epoch_data)
    mutate(epoch_data)
    visualizer = Visualizer(record, cast(Any, epoch_data))

    with pytest.raises(SaliencyContextError, match=expected_detail):
        visualizer.iter_saliency_by_label("Gradient")


def test_visualizer_rejects_safe_artifact_without_identity_context(tmp_path) -> None:
    epoch_data = _EpochContext()
    _record(epoch_data).export(str(tmp_path))
    manifest_path = tmp_path / "eval"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["payload"]["saliency_context"] = None
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    loaded = EvalRecord.load(str(tmp_path))
    assert loaded is not None
    assert loaded.saliency_context_status == "legacy_missing"

    with pytest.raises(SaliencyContextError, match=r"legacy.*identity context"):
        Visualizer(loaded, cast(Any, epoch_data)).iter_saliency_by_label("Gradient")


def test_visualizer_uses_persisted_class_identity_after_round_trip(tmp_path) -> None:
    epoch_data = _EpochContext()
    record = _record(epoch_data)
    record.export(str(tmp_path))
    loaded = EvalRecord.load(str(tmp_path))
    assert loaded is not None

    labels = Visualizer(loaded, cast(Any, epoch_data)).iter_saliency_by_label(
        "Gradient"
    )

    assert [(key, name) for key, name, _values in labels] == [
        (0, "left"),
        (1, "right"),
    ]


def test_visualizer_validates_without_rebinding_artifact_identity() -> None:
    epoch_data = _EpochContext()
    record = _record(epoch_data)

    with patch.object(
        record,
        "bind_saliency_context",
        side_effect=AssertionError("renderer must not bind artifact identity"),
    ):
        labels = Visualizer(record, cast(Any, epoch_data)).iter_saliency_by_label(
            "Gradient"
        )

    assert [(key, name) for key, name, _values in labels] == [
        (0, "left"),
        (1, "right"),
    ]


def test_3d_engine_cannot_bypass_channel_identity_validation(monkeypatch) -> None:
    epoch_data = _EpochContext()
    record = _record(epoch_data)
    epoch_data.ch_names = ["C4", "C3"]
    monkeypatch.setattr(Saliency3DEngine, "_load_models", lambda _self: None)
    engine = Saliency3DEngine()

    with pytest.raises(SaliencyContextError, match="channel order"):
        engine.process_data(record, epoch_data, "left")
